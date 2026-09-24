"""Fusion, second half: discovery (templates, fonts), comp attributes and
undo grouping, the node graph, macro / template paste with overrides, tool
duplication and presets, keyframe read-back and removal, modifiers.

Live-verified facts this file is built on (Resolve Studio 21.0.4, see GOTCHAS):

- `comp.Paste(table)` from Python returns True and pastes NOTHING: nested
  settings tables do not survive the Python bridge (`tool.SaveSettings()`
  comes back as `{'Tools': None}`). Paste must run inside Fusion's Lua:
  `comp:Paste(bmd.readfile(path))` via `comp.Execute`. Errors inside that Lua
  are captured with pcall and handed back through `comp:SetData`.
- Paste only lands when the comp has been LOADED on the Fusion page at least
  once; `comp.CurrentFrame` (and so FlowView) is None until then. `_loaded()`
  loads it and restores the page the user was on.
- `COMPN_RenderEnd` is clamped to `COMPN_GlobalEnd`; set the globals first.
- Modifier factories that exist on this build: BezierSpline, Path, XYPath,
  Shake, Calculation, Offset, Expression, Probe, KeyStretcher. Perturb and
  Follower have no scripting constructor. A factory call without attaching
  leaves an orphan modifier in the comp, so only create when attaching.

Same rule as fusion.py: every Fusion call is wrapped so an unsupported one
answers 422 with the reason, never a 500."""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from ..bridge import NotFound, Rejected, ResolveBridge, require
from ..deps import resolve_session
from ..fusion_templates import KINDS, extract, find_template, list_templates
from ..schemas import CompAttrs, CompExport, CompUndo, DuplicateTool, PasteSettings, ToolModifier, ToolSettingsPath
from ..serialize import jsonable, safe, tool_summary
from .fusion import _comp, _fusion_value, _set_inputs, _tool, _tool_detail, _tools

router = APIRouter(prefix="/fusion", tags=["fusion"])

MODIFIERS = ("BezierSpline", "Path", "XYPath", "Shake", "Calculation", "Offset", "Expression", "Probe", "KeyStretcher")
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
_GLOBAL_FIRST = ("COMPN_GlobalStart", "COMPN_GlobalEnd")
SETTLE_SECONDS = 1.0  # after a comp first appears on the Fusion page, before it accepts pastes


# -- Lua bridge -------------------------------------------------------------------


def _lua_path(path: str) -> str:
    return path.replace("\\", "/")


def lua(comp, body: str, wait: float = 20.0) -> Any:
    """Run Lua inside the comp's process; raise Rejected with Fusion's own
    error text when it fails. `body` may call `comp:SetData("dg_out", ...)`
    to hand a value back; that value is returned. `comp.Execute` returns
    before heavy scripts (a particle-system paste) finish, so completion is
    polled through the status key for up to `wait` seconds."""
    key = f"dg_{uuid.uuid4().hex[:8]}"
    script = f'local ok, err = pcall(function() {body} end) comp:SetData("{key}", ok and "ok" or tostring(err))'
    try:
        comp.Execute(script)
    except Exception as e:
        raise Rejected(f"comp.Execute failed: {e}") from e
    deadline = time.monotonic() + wait
    status = safe(comp.GetData, key)
    while status is None and time.monotonic() < deadline:
        time.sleep(0.1)
        status = safe(comp.GetData, key)
    if status != "ok":
        raise Rejected(f"Fusion Lua failed: {status or f'no response from comp.Execute within {wait:g}s'}")
    out = safe(comp.GetData, "dg_out")
    safe(comp.SetData, key, None)
    return out


def _loaded(bridge: ResolveBridge, item, comp, settle: float = 6.0) -> Optional[Dict[str, Any]]:
    """Paste / FlowView only work once the comp has been opened on the Fusion
    page. Load it (once): park the playhead on the item, load the comp, open
    the Fusion page, wait until Fusion reports a frame for it and answers a
    Lua round trip. The page and playhead are deliberately LEFT there:
    switching back to Edit and moving the playhead right after a paste froze
    Resolve hard (GOTCHAS, 2026-09-24); the response reports what moved so the
    caller can switch pages later with POST /system/page. Returns None when
    nothing had to be loaded."""
    if safe(lambda: comp.CurrentFrame) is not None:
        return None
    names = item.GetFusionCompNameList() or []
    name = safe(lambda: comp.GetAttrs().get("COMPS_Name")) or (names[0] if names else None)
    resolve = bridge.ensure()
    page = safe(resolve.GetCurrentPage)
    # The Fusion page shows the clip UNDER THE PLAYHEAD, so park the playhead
    # on the item first (and put it back afterwards).
    tl = bridge.current_timeline()
    playhead = safe(tl.GetCurrentTimecode)
    start = safe(item.GetStart)
    if start is not None:
        from .tools import frames_to_timecode

        fps_setting = str(tl.GetSetting("timelineFrameRate") or "30").upper()
        fps = float(fps_setting.replace("DF", "").strip() or 30)
        safe(tl.SetCurrentTimecode, frames_to_timecode(int(start) + 1, fps, "DF" in fps_setting))
    # Resolve has frozen hard on Fusion writes while its background renders
    # ran (GOTCHAS); opening a comp is the moment to switch them off.
    safe(resolve.DisableBackgroundTasksForCurrentResolveSession)
    time.sleep(SETTLE_SECONDS * 0.5)
    if name:
        safe(item.LoadFusionCompByName, name)
    time.sleep(SETTLE_SECONDS * 0.5)
    safe(resolve.OpenPage, "fusion")
    time.sleep(SETTLE_SECONDS)  # do not hammer the comp while the page is loading (Resolve froze twice)
    deadline = time.monotonic() + settle
    while safe(lambda: comp.CurrentFrame) is None and time.monotonic() < deadline:
        time.sleep(0.5)
    if safe(lambda: comp.CurrentFrame) is None:
        raise Rejected("Could not open the composition on the Fusion page (needed for paste / node layout); open it once in the UI and retry")
    time.sleep(SETTLE_SECONDS)  # the frame appears before the comp accepts pastes
    try:
        lua(comp, 'comp:SetData("dg_out", 1)', wait=5.0)
    except Rejected:
        pass
    return {"page_before": page, "page_now": "fusion", "playhead_before": playhead, "playhead_now": safe(tl.GetCurrentTimecode)}


def _names(comp) -> List[str]:
    return [tool_summary(t)["name"] for t in _tools(comp)]


# -- discovery ----------------------------------------------------------------


@router.get("/templates")
def fusion_templates(
    kind: Optional[str] = Query(default=None, description="titles | generators | effects | transitions | fusion (Fusion-page presets: particles, shaders, ...)"),
    contains: Optional[str] = Query(default=None, description="Case-insensitive substring filter on name / category"),
):
    """The Fusion templates Resolve can insert by name (Effects Library), scanned
    from the system and user template folders and `.drfx` bundles. Use
    `name` with POST /timelines/current/generators (kind fusion_title /
    fusion_generator), or `kind/name` as `template` in POST .../comps/{comp}/paste."""
    if kind and kind not in KINDS:
        raise NotFound(f"kind must be one of {KINDS}")
    items = list_templates(kind)
    if contains:
        c = contains.lower()
        items = [t for t in items if c in t["name"].lower() or c in (t["category"] or "").lower()]
    by_kind: Dict[str, int] = {}
    for t in items:
        by_kind[t["kind"]] = by_kind.get(t["kind"], 0) + 1
    return {"count": len(items), "by_kind": by_kind, "templates": items}


@router.get("/fonts")
def fusion_fonts(contains: Optional[str] = Query(default=None, description="Case-insensitive substring filter"), bridge: ResolveBridge = Depends(resolve_session)):
    """Fonts Fusion can render (Text+ `Font` input). Check glyph coverage
    before choosing one: symbol fonts (Segoe UI Symbol) carry ★ ☀ ♫."""
    fu = bridge.fusion()
    try:
        fm = fu.FontManager
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
    return {"attrs": attrs, "loaded": safe(lambda: c.CurrentFrame) is not None, **{k: attrs.get(v) for k, v in _ATTR_KEYS.items()}}


@router.patch("/items/{item_id}/comps/{comp}/attrs")
def set_comp_attrs(item_id: str, comp: str, body: CompAttrs, bridge: ResolveBridge = Depends(resolve_session)):
    """Set comp time / render range / quality flags (COMPN_*, COMPB_*). The
    global range is applied before the render range because Fusion clamps
    RenderEnd to GlobalEnd."""
    c = _comp(bridge, item_id, comp)
    attrs = {_ATTR_KEYS[k]: v for k, v in body.model_dump(exclude_none=True).items() if k in _ATTR_KEYS}
    attrs.update(body.raw or {})
    if not attrs:
        raise Rejected("Nothing to set")
    first = {k: v for k, v in attrs.items() if k in _GLOBAL_FIRST}
    rest = {k: v for k, v in attrs.items() if k not in _GLOBAL_FIRST}
    try:
        if first:
            c.SetAttrs(first)
        if rest:
            c.SetAttrs(rest)
    except Exception as e:
        raise Rejected(f"comp.SetAttrs failed: {e}") from e
    after = safe(c.GetAttrs, default={}) or {}
    return {"ok": True, "set": attrs, "now": {k: jsonable(after.get(k)) for k in attrs}}


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

_POS_LUA = (
    "local p = {} for _, tool in ipairs(comp:GetToolList(false)) do "
    "local s = tool:SaveSettings() local vi = s and s.Tools and s.Tools[tool.Name] and s.Tools[tool.Name].ViewInfo "
    "p[tool.Name] = vi and vi.Pos or false end comp:SetData(\"dg_out\", p)"
)


def _pair(pos) -> Optional[List[float]]:
    if isinstance(pos, dict):
        return [pos.get(1) if 1 in pos else pos.get(1.0), pos.get(2) if 2 in pos else pos.get(2.0)]
    return None


def _positions(comp, tools) -> (Dict[str, Optional[List[float]]], str):
    """Node positions. Preferred: FlowView grid units (what PATCH position
    sets) when the comp is open on the Fusion page. Fallback: the ViewInfo.Pos
    stored in each tool's settings (different units) via one Lua round trip."""
    flow = safe(lambda: comp.CurrentFrame.FlowView)
    if flow is not None:
        return {tool_summary(t)["name"]: _pair(safe(flow.GetPosTable, t)) for t in tools}, "flow"
    try:
        table = lua(comp, _POS_LUA) or {}
    except Rejected:
        return {}, "unavailable"
    return {str(name): _pair(pos) for name, pos in (table.items() if isinstance(table, dict) else [])}, "settings"


def graph_of(comp) -> Dict[str, Any]:
    tools = _tools(comp)
    positions, units = _positions(comp, tools)
    nodes, edges = [], []
    for t in tools:
        info = tool_summary(t)
        info["position"] = positions.get(info["name"])
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
    outputs = [n["name"] for n in nodes if n["id"] == "MediaOut"]
    return {"nodes": nodes, "edges": edges, "outputs": outputs, "position_units": units}


@router.get("/items/{item_id}/comps/{comp}/graph")
def comp_graph(item_id: str, comp: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Nodes (with flow positions) and edges (which tool feeds which input).
    Modifiers (splines, Shake, ...) appear as nodes without a position."""
    return graph_of(_comp(bridge, item_id, comp))


# -- paste settings / macros / templates --------------------------------------------


def _settings_path(body: PasteSettings) -> str:
    if body.template:
        found = find_template(body.template)
        if found is None:
            raise NotFound(f"No Fusion template {body.template!r} (GET /fusion/templates lists them; use name or kind/name)")
        return extract(found)
    if body.path:
        if not os.path.exists(body.path):
            raise NotFound(f"No such file on the Resolve machine: {body.path}")
        return body.path
    if body.settings_text:
        target = Path(tempfile.gettempdir()) / "dollygrip" / "paste" / f"{uuid.uuid4().hex}.setting"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.settings_text, encoding="utf-8")
        return str(target)
    raise Rejected("Give `template` (kind/name from GET /fusion/templates), `path` (a .setting / .comp / macro file) or `settings_text`")


def _paste_file(bridge: ResolveBridge, item, comp, path: str):
    moved = _loaded(bridge, item, comp)
    before = set(_names(comp))
    lua(comp, f'local t = bmd.readfile([[{_lua_path(path)}]]) if not t then error("bmd.readfile could not parse the settings file") end comp:Paste(t)')
    return [t for t in _tools(comp) if tool_summary(t)["name"] not in before], moved


@router.post("/items/{item_id}/comps/{comp}/paste")
def paste_settings(item_id: str, comp: str, body: PasteSettings, bridge: ResolveBridge = Depends(resolve_session)):
    """Paste a Fusion macro / Effects Library template / tool preset into the
    comp, then apply per-tool input overrides. Returns the tools that
    appeared (a template usually pastes a group operator plus its inner
    tools; override the inner `Text1`-style tools or the group's published
    inputs). Loads the comp on the Fusion page first if needed."""
    item = bridge.item(item_id)
    c = bridge.fusion_comp(item, comp)
    path = _settings_path(body)
    new, moved = _paste_file(bridge, item, c, path)
    if not new:
        raise Rejected(f"Paste of {path!r} added no tools (is it a Fusion .setting / macro file?)")
    applied = {}
    for name, inputs in (body.inputs or {}).items():
        target = next((t for t in new if tool_summary(t)["name"] == name), None) or safe(c.FindTool, name)
        if target is None:
            applied[name] = "tool not found after paste"
            continue
        applied[name] = _set_inputs(target, inputs)
    return {"ok": True, "source": path, "tools": [_tool_detail(t) if body.detail else tool_summary(t) for t in new], "overrides": applied, "loaded": moved}


# -- tool duplication and presets ---------------------------------------------------


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/duplicate")
def duplicate_tool(item_id: str, comp: str, tool: str, body: DuplicateTool, bridge: ResolveBridge = Depends(resolve_session)):
    """Copy a tool with all its inputs and animation (Lua
    `comp:Paste(tool:SaveSettings())`; the Python-side table is lossy)."""
    item = bridge.item(item_id)
    c = bridge.fusion_comp(item, comp)
    t = _tool(c, tool)
    src_name = tool_summary(t)["name"]
    moved = _loaded(bridge, item, c)
    before = set(_names(c))
    lua(c, f'comp:Paste(comp:FindTool("{src_name}"):SaveSettings())')
    new = [x for x in _tools(c) if tool_summary(x)["name"] not in before]
    if not new:
        raise Rejected("Paste produced no new tool")
    dup = next((x for x in new if tool_summary(x)["id"] == tool_summary(t)["id"]), new[0])
    if body.name:
        safe(dup.SetAttrs, {"TOOLS_Name": body.name})
    if body.inputs:
        _set_inputs(dup, body.inputs)
    return {"ok": True, "tool": _tool_detail(dup), "also_created": [tool_summary(x)["name"] for x in new if x is not dup], "loaded": moved}


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/settings/save")
def save_tool_settings(item_id: str, comp: str, tool: str, body: ToolSettingsPath, bridge: ResolveBridge = Depends(resolve_session)):
    """Write a tool preset (.setting) to disk - reusable via .../paste {path}
    or .../settings/load."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    require(safe(t.SaveSettings, body.path), f"SaveSettings refused {body.path!r}")
    return {"ok": True, "path": body.path}


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/settings/load")
def load_tool_settings(item_id: str, comp: str, tool: str, body: ToolSettingsPath, bridge: ResolveBridge = Depends(resolve_session)):
    """Apply a tool preset (.setting) onto an existing tool of the same type."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    if not os.path.exists(body.path):
        raise NotFound(f"No such file on the Resolve machine: {body.path}")
    require(safe(t.LoadSettings, body.path), f"LoadSettings refused {body.path!r}")
    return {"ok": True, "tool": _tool_detail(t)}


# -- keyframes: read back / remove --------------------------------------------------


def _spline_of(tool, input_name: str):
    inp = getattr(tool, input_name)
    out = safe(inp.GetConnectedOutput)
    return inp, (safe(out.GetTool) if out else None)


@router.get("/items/{item_id}/comps/{comp}/tools/{tool}/keyframes")
def get_tool_keyframes(item_id: str, comp: str, tool: str, input: str = Query(description="Input name, e.g. Size, Blend, Center"), bridge: ResolveBridge = Depends(resolve_session)):
    """Keys on the input's spline as {frame: value}; `animated` false when
    static or driven by a non-spline modifier (then `modifier` says which)."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    try:
        inp, spline = _spline_of(t, input)
    except Exception as e:
        raise NotFound(f"No input {input!r} on {tool}: {e}") from e
    if spline is None:  # static: GetInput is safe (never call it on a Calculation/AnimCurves-driven input)
        return {"input": input, "animated": False, "modifier": None, "value": jsonable(safe(t.GetInput, input)), "keyframes": {}, "expression": safe(inp.GetExpression)}
    modifier = safe(lambda: spline.ID)
    # Only splines hold keys; Shake & co answer GetKeyFrames with their valid range (+-1e9), not keys.
    keys = (safe(spline.GetKeyFrames, default={}) or {}) if modifier in (None, "BezierSpline", "PolyPath") else {}
    flat = {}
    for frame, val in keys.items():
        label = str(int(frame)) if float(frame).is_integer() else str(frame)
        if isinstance(val, dict):
            nums = {k: v for k, v in val.items() if isinstance(k, (int, float))}  # drops the RH/LH handle tables
            flat[label] = nums.get(1) if set(nums) == {1} else jsonable(nums)
        else:
            flat[label] = jsonable(val)
    return {"input": input, "animated": bool(flat), "modifier": modifier, "keyframes": flat, "expression": safe(inp.GetExpression)}


@router.delete("/items/{item_id}/comps/{comp}/tools/{tool}/keyframes")
def clear_tool_keyframes(
    item_id: str,
    comp: str,
    tool: str,
    input: str = Query(),
    value: Optional[float] = Query(default=None, description="Static value to leave behind (default: the animated value at the comp's current time)"),
    bridge: ResolveBridge = Depends(resolve_session),
):
    """Detach the spline/modifier from an input (`input:ConnectTo(nil)`) and
    leave a static value."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    try:
        inp, spline = _spline_of(t, input)
        driver = safe(lambda: spline.ID) if spline is not None else None
        if value is not None:
            current = value
        elif driver in (None, "BezierSpline", "PolyPath"):
            current = safe(t.GetInput, input)  # safe: static or spline (GetInput on other modifiers freezes Resolve)
        else:
            current = None
        if spline is not None:
            inp.ConnectTo(None)
        if current is None and value is None and driver not in (None, "BezierSpline", "PolyPath"):
            current = safe(t.GetInput, input)  # now static, safe to read
        if current is not None:
            t.SetInput(input, _fusion_value(current))
    except Exception as e:
        raise Rejected(f"Could not clear keyframes on {tool}.{input}: {e}") from e
    return {"ok": True, "input": input, "was_animated": spline is not None, "value": jsonable(safe(t.GetInput, input))}


# -- modifiers ----------------------------------------------------------------------


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/modifier")
def add_tool_modifier(item_id: str, comp: str, tool: str, body: ToolModifier, bridge: ResolveBridge = Depends(resolve_session)):
    """Drive an input with a modifier: Shake (handheld wobble), Path / XYPath
    (motion paths), Calculation / Offset / Expression (derived values),
    Probe (sample another image), KeyStretcher. Returns the modifier tool's
    name so its own inputs can be set via the tools endpoints (Shake:
    RandomSeed, Smoothness, XMinimum/XMaximum, YMinimum/YMaximum, LockXY)."""
    c = _comp(bridge, item_id, comp)
    t = _tool(c, tool)
    kind = body.modifier
    factory = getattr(c, kind, None)
    if factory is None:
        raise Rejected(f"This Fusion build has no modifier constructor {kind!r} (available: {MODIFIERS})")
    try:
        modifier = factory()
        if modifier is None:
            raise Rejected(f"comp.{kind}() returned nothing")
        setattr(t, body.input, modifier)
        inp = getattr(t, body.input)
        out = safe(inp.GetConnectedOutput)
        mod_tool = safe(out.GetTool) if out else modifier
    except Rejected:
        raise
    except Exception as e:
        raise Rejected(f"Attaching {kind} to {tool}.{body.input} failed: {e}") from e
    applied = _set_inputs(mod_tool, body.inputs) if body.inputs else {}
    return {"ok": True, "input": body.input, "modifier": tool_summary(mod_tool), "inputs_set": applied}
