"""Fusion, second half: discovery (templates, fonts), comp attributes and
undo grouping, the node graph, macro paste with overrides, tool duplication
and presets, keyframe read-back and removal, modifiers, node layout.

Same rules as fusion.py: every Fusion call is wrapped so an unsupported one
answers 422 with the reason, never a 500."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from ..bridge import NotFound, Rejected, ResolveBridge, require
from ..deps import resolve_session
from ..fusion_templates import KINDS, list_templates
from ..schemas import (
    CompAttrs,
    CompExport,
    CompUndo,
    DuplicateTool,
    PasteSettings,
    ToolModifier,
    ToolSettingsPath,
)
from ..serialize import jsonable, safe, tool_summary
from .fusion import _comp, _fusion_value, _set_inputs, _tool, _tool_detail, _tools

router = APIRouter(prefix="/fusion", tags=["fusion"])

MODIFIERS = ("BezierSpline", "Path", "XYPath", "Shake", "Perturb", "Follower", "Calculation", "Offset", "Anim Curves")
_ATTR_KEYS = {
    "current_time": "COMPN_CurrentTime",
    "render_start": "COMPN_RenderStart",
    "render_end": "COMPN_RenderEnd",
    "global_start": "COMPN_GlobalStart",
    "global_end": "COMPN_GlobalEnd",
    "hiq": "COMPB_HiQ",
    "motion_blur": "COMPB_MotionBlur",
    "proxy": "COMPB_Proxy",
}


# -- discovery ----------------------------------------------------------------


@router.get("/templates")
def fusion_templates(kind: Optional[str] = Query(default=None, description="titles | generators | effects | transitions")):
    """The Fusion templates Resolve can insert by name (Effects Library), scanned
    from the system and user template folders. Use `name` with
    POST /timelines/current/generators (kind fusion_title / fusion_generator)."""
    if kind and kind not in KINDS:
        raise NotFound(f"kind must be one of {KINDS}")
    items = list_templates(kind)
    return {"count": len(items), "templates": items}


@router.get("/fonts")
def fusion_fonts(contains: Optional[str] = Query(default=None, description="Case-insensitive substring filter"), bridge: ResolveBridge = Depends(resolve_session)):
    """Fonts Fusion can render (Text+ `Font` input). Check glyph coverage
    before choosing one: symbol fonts (Segoe UI Symbol) carry ★ ☀ ♫."""
    fu = bridge.fusion()
    try:
        fm = fu.FontManager
        fm = fm() if callable(fm) else fm
        listed = fm.GetFontList() or {}
    except Exception as e:
        raise Rejected(f"FontManager.GetFontList failed: {e}") from e
    names = sorted(listed.keys()) if isinstance(listed, dict) else sorted(str(x) for x in listed)
    if contains:
        names = [n for n in names if contains.lower() in n.lower()]
    return {"count": len(names), "fonts": names}


# -- comp attributes, undo, save ------------------------------------------------


@router.get("/items/{item_id}/comps/{comp}/attrs")
def comp_attrs(item_id: str, comp: str, bridge: ResolveBridge = Depends(resolve_session)):
    c = _comp(bridge, item_id, comp)
    attrs = jsonable(safe(c.GetAttrs, default={}) or {})
    return {"attrs": attrs, **{k: attrs.get(v) for k, v in _ATTR_KEYS.items()}}


@router.patch("/items/{item_id}/comps/{comp}/attrs")
def set_comp_attrs(item_id: str, comp: str, body: CompAttrs, bridge: ResolveBridge = Depends(resolve_session)):
    """Set comp time / render range / quality flags (COMPN_*, COMPB_*)."""
    c = _comp(bridge, item_id, comp)
    attrs = {_ATTR_KEYS[k]: v for k, v in body.model_dump(exclude_none=True).items() if k in _ATTR_KEYS}
    attrs.update(body.raw or {})
    if not attrs:
        raise Rejected("Nothing to set")
    try:
        c.SetAttrs(attrs)
    except Exception as e:
        raise Rejected(f"comp.SetAttrs failed: {e}") from e
    return {"ok": True, "set": attrs}


@router.post("/items/{item_id}/comps/{comp}/undo")
def comp_undo(item_id: str, comp: str, body: CompUndo, bridge: ResolveBridge = Depends(resolve_session)):
    """Group the following edits into one undo step: start, make calls, end."""
    c = _comp(bridge, item_id, comp)
    try:
        if body.action == "start":
            c.StartUndo(body.name or "DollyGrip")
        else:
            c.EndUndo(body.keep)
    except Exception as e:
        raise Rejected(f"undo {body.action} failed: {e}") from e
    return {"ok": True, "action": body.action}


@router.post("/items/{item_id}/comps/{comp}/save")
def save_comp_file(item_id: str, comp: str, body: CompExport, bridge: ResolveBridge = Depends(resolve_session)):
    """comp.Save(path) - write the composition to a .comp file."""
    c = _comp(bridge, item_id, comp)
    require(safe(c.Save, body.path), f"comp.Save refused {body.path!r}")
    return {"ok": True, "path": body.path}


# -- graph ------------------------------------------------------------------------


def _flow(comp):
    try:
        frame = comp.CurrentFrame
        return frame.FlowView if frame is not None else None
    except Exception:
        return None


def graph_of(comp) -> Dict[str, Any]:
    tools = _tools(comp)
    flow = _flow(comp)
    nodes, edges = [], []
    for t in tools:
        info = tool_summary(t)
        pos = None
        if flow is not None:
            try:
                p = flow.GetPosTable(t)
                if p:
                    pos = [p.get(1), p.get(2)] if isinstance(p, dict) else list(p)
            except Exception:
                pos = None
        info["position"] = pos
        nodes.append(info)
        try:
            for inp in (t.GetInputList() or {}).values():
                out = safe(inp.GetConnectedOutput)
                if out is None:
                    continue
                src = safe(out.GetTool)
                attrs = safe(inp.GetAttrs, default={}) or {}
                edges.append({"from": safe(lambda: src.Name) if src else None, "to": info["name"], "input": attrs.get("INPS_ID") or attrs.get("INPS_Name")})
        except Exception:
            pass
    # the comp's output is whatever feeds MediaOut
    outputs = [n["name"] for n in nodes if n["id"] == "MediaOut"]
    return {"nodes": nodes, "edges": edges, "outputs": outputs}


@router.get("/items/{item_id}/comps/{comp}/graph")
def comp_graph(item_id: str, comp: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Nodes (with flow positions) and edges (which tool feeds which input)."""
    return graph_of(_comp(bridge, item_id, comp))


# -- paste settings / macros / templates --------------------------------------------


def _read_settings(bridge: ResolveBridge, body: PasteSettings) -> Any:
    if body.settings is not None:
        return body.settings
    if body.path:
        reader = bridge.settings_reader()
        if reader is None:
            raise Rejected("This gateway cannot parse .setting files (no fusionscript readfile); pass `settings` as a table instead")
        table = safe(reader, body.path)
        if not table:
            raise NotFound(f"Could not read a settings table from {body.path!r}")
        return table
    raise Rejected("Give `path` (a .setting / .comp file) or `settings`")


@router.post("/items/{item_id}/comps/{comp}/paste")
def paste_settings(item_id: str, comp: str, body: PasteSettings, bridge: ResolveBridge = Depends(resolve_session)):
    """Paste a settings table (a Fusion macro / Effects Library .setting file /
    tool preset) into the comp, then apply per-tool input overrides. Returns
    the tools that appeared."""
    c = _comp(bridge, item_id, comp)
    before = {tool_summary(t)["name"] for t in _tools(c)}
    table = _read_settings(bridge, body)
    try:
        c.Paste(table)
    except Exception as e:
        raise Rejected(f"comp.Paste failed: {e}") from e
    new = [t for t in _tools(c) if tool_summary(t)["name"] not in before]
    applied = {}
    for name, inputs in (body.inputs or {}).items():
        target = next((t for t in new if tool_summary(t)["name"] == name), None) or safe(c.FindTool, name)
        if target is None:
            applied[name] = "tool not found after paste"
            continue
        applied[name] = _set_inputs(target, inputs)
    return {"ok": True, "tools": [_tool_detail(t) if body.detail else tool_summary(t) for t in new], "overrides": applied}


# -- tool duplication and presets ---------------------------------------------------


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/duplicate")
def duplicate_tool(item_id: str, comp: str, tool: str, body: DuplicateTool, bridge: ResolveBridge = Depends(resolve_session)):
    """Copy a tool with all its inputs/animation (SaveSettings -> Paste)."""
    c = _comp(bridge, item_id, comp)
    t = _tool(c, tool)
    before = {tool_summary(x)["name"] for x in _tools(c)}
    try:
        table = t.SaveSettings()
        c.Paste(table)
    except Exception as e:
        raise Rejected(f"duplicate failed: {e}") from e
    new = [x for x in _tools(c) if tool_summary(x)["name"] not in before]
    if not new:
        raise Rejected("Paste produced no new tool")
    dup = new[0]
    if body.name:
        safe(dup.SetAttrs, {"TOOLS_Name": body.name})
    if body.inputs:
        _set_inputs(dup, body.inputs)
    return {"ok": True, "tool": _tool_detail(dup)}


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/settings/save")
def save_tool_settings(item_id: str, comp: str, tool: str, body: ToolSettingsPath, bridge: ResolveBridge = Depends(resolve_session)):
    """Write a tool preset (.setting) to disk."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    require(safe(t.SaveSettings, body.path), f"SaveSettings refused {body.path!r}")
    return {"ok": True, "path": body.path}


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/settings/load")
def load_tool_settings(item_id: str, comp: str, tool: str, body: ToolSettingsPath, bridge: ResolveBridge = Depends(resolve_session)):
    """Apply a tool preset (.setting) onto an existing tool."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    require(safe(t.LoadSettings, body.path), f"LoadSettings refused {body.path!r}")
    return {"ok": True, "tool": _tool_detail(t)}


# -- keyframes: read back / remove --------------------------------------------------


def _spline_of(tool, input_name: str):
    inp = getattr(tool, input_name)
    out = safe(inp.GetConnectedOutput)
    return inp, (safe(out.GetTool) if out else None)


@router.get("/items/{item_id}/comps/{comp}/tools/{tool}/keyframes")
def get_tool_keyframes(item_id: str, comp: str, tool: str, input: str = Query(description="Input name, e.g. Size, Blend, Center"), bridge: ResolveBridge = Depends(resolve_session)):
    """Keys on the input's spline: {frame: value}; `animated` false when static."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    try:
        inp, spline = _spline_of(t, input)
    except Exception as e:
        raise NotFound(f"No input {input!r} on {tool}: {e}") from e
    if spline is None or not hasattr(spline, "GetKeyFrames"):
        return {"input": input, "animated": False, "value": jsonable(safe(t.GetInput, input)), "keyframes": {}}
    keys = safe(spline.GetKeyFrames, default={}) or {}
    flat = {}
    for frame, val in keys.items():
        if isinstance(val, dict):
            nums = {k: v for k, v in val.items() if isinstance(k, (int, float))}
            flat[str(int(frame)) if float(frame).is_integer() else str(frame)] = nums.get(1) if set(nums) == {1} else jsonable(nums)
        else:
            flat[str(frame)] = jsonable(val)
    return {"input": input, "animated": True, "modifier": safe(lambda: spline.ID), "keyframes": flat, "expression": safe(inp.GetExpression)}


@router.delete("/items/{item_id}/comps/{comp}/tools/{tool}/keyframes")
def clear_tool_keyframes(item_id: str, comp: str, tool: str, input: str = Query(), value: Optional[float] = Query(default=None, description="Static value to leave behind (default: value at the comp's current time)"), bridge: ResolveBridge = Depends(resolve_session)):
    """Remove the animation/modifier from an input and leave a static value."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    try:
        inp, spline = _spline_of(t, input)
        current = value if value is not None else safe(t.GetInput, input)
        if spline is not None:
            inp.ConnectTo(None)
        if current is not None:
            t.SetInput(input, _fusion_value(current))
    except Exception as e:
        raise Rejected(f"Could not clear keyframes on {tool}.{input}: {e}") from e
    return {"ok": True, "input": input, "was_animated": spline is not None, "value": jsonable(safe(t.GetInput, input))}


# -- modifiers ----------------------------------------------------------------------


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/modifier")
def add_tool_modifier(item_id: str, comp: str, tool: str, body: ToolModifier, bridge: ResolveBridge = Depends(resolve_session)):
    """Drive an input with a modifier: Path / XYPath (motion paths), Shake,
    Perturb (organic wobble), Follower (text animation), Calculation, Offset.
    Returns the modifier tool's name so its own inputs can be set via the
    tools endpoints (e.g. Shake: `Random Seed`, `Smoothness`, `X Min/Max`)."""
    c = _comp(bridge, item_id, comp)
    t = _tool(c, tool)
    kind = body.modifier
    factory = getattr(c, kind.replace(" ", ""), None)
    if factory is None:
        raise Rejected(f"This Fusion has no modifier factory {kind!r} (known: {MODIFIERS})")
    try:
        modifier = factory()
        setattr(t, body.input, modifier)
        inp = getattr(t, body.input)
        out = safe(inp.GetConnectedOutput)
        mod_tool = safe(out.GetTool) if out else modifier
    except Exception as e:
        raise Rejected(f"Attaching {kind} to {tool}.{body.input} failed: {e}") from e
    applied = _set_inputs(mod_tool, body.inputs) if body.inputs else {}
    return {"ok": True, "input": body.input, "modifier": tool_summary(mod_tool), "inputs_set": applied}
