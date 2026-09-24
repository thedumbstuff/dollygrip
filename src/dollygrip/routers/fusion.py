"""Fusion compositions on timeline items: comps CRUD, tools, inputs,
connections, keyframes, and a Text+ convenience for data-driven titles.

The comp/tool surface is Fusion's own scripting API (not in Blackmagic's
Resolve README): comp.GetToolList / AddTool / FindTool, tool.GetInput /
SetInput / ConnectInput / GetAttrs, `tool.Input[frame] = value` keyframes.
Everything here is wrapped so an unsupported call answers 422, never 500.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from ..bridge import NotFound, Rejected, ResolveBridge, require
from ..deps import resolve_session
from ..schemas import AddComp, AddTool, CompExport, ConnectInput, PatchTool, RenameComp, TextPlus, ToolExpression, ToolInputs, ToolKeyframes
from ..serialize import jsonable, safe, tool_summary

router = APIRouter(prefix="/fusion", tags=["fusion"])


def _comp(bridge: ResolveBridge, item_id: str, comp: Optional[str]):
    return bridge.fusion_comp(bridge.item(item_id), comp)


def _tools(comp) -> list:
    try:
        listed = comp.GetToolList(False) or {}
    except Exception as e:  # pragma: no cover - depends on the live build
        raise Rejected(f"comp.GetToolList failed: {e}") from e
    return list(listed.values()) if isinstance(listed, dict) else list(listed)


def _tool(comp, name: str):
    tool = safe(comp.FindTool, name)
    if tool is None:
        for t in _tools(comp):
            if tool_summary(t)["name"] == name:
                return t
        raise NotFound(f"Tool {name!r} not found in the composition (have {[tool_summary(t)['name'] for t in _tools(comp)]})")
    return tool


def _fusion_value(value: Any):
    """Points arrive as [x, y]; Fusion wants a 1-based table {1: x, 2: y}."""
    if isinstance(value, (list, tuple)) and len(value) in (2, 3, 4) and all(isinstance(v, (int, float)) for v in value):
        return {i + 1: float(v) for i, v in enumerate(value)}
    return value


def _set_inputs(tool, inputs: dict, frame: Optional[int] = None) -> dict:
    results = {}
    for name, value in inputs.items():
        try:
            if frame is None:
                tool.SetInput(name, _fusion_value(value))
            else:
                tool.SetInput(name, _fusion_value(value), frame)
            results[name] = True
        except Exception as e:
            results[name] = f"{type(e).__name__}: {e}"
    return results


def _tool_detail(tool) -> dict:
    out = tool_summary(tool)
    inputs = {}
    try:
        for inp in (tool.GetInputList() or {}).values():
            attrs = safe(inp.GetAttrs, default={}) or {}
            key = attrs.get("INPS_ID") or attrs.get("INPS_Name")
            if key:
                inputs[key] = jsonable(safe(tool.GetInput, key))
    except Exception:
        pass
    out["inputs"] = inputs
    return out


# -- comps -----------------------------------------------------------------------


@router.get("/items/{item_id}/comps")
def list_comps(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    return {"count": int(item.GetFusionCompCount() or 0), "comps": item.GetFusionCompNameList() or []}


@router.post("/items/{item_id}/comps")
def add_comp(item_id: str, body: AddComp, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    comp = item.ImportFusionComp(body.import_path) if body.import_path else item.AddFusionComp()
    if not comp:
        raise NotFound("Resolve could not add the composition" + (f" from {body.import_path!r}" if body.import_path else ""))
    return {"ok": True, "comps": item.GetFusionCompNameList() or []}


@router.delete("/items/{item_id}/comps/{comp}")
def delete_comp(item_id: str, comp: str, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    require(item.DeleteFusionCompByName(comp), f"Composition {comp!r} not found")
    return {"ok": True, "comps": item.GetFusionCompNameList() or []}


@router.patch("/items/{item_id}/comps/{comp}")
def rename_comp(item_id: str, comp: str, body: RenameComp, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    require(item.RenameFusionCompByName(comp, body.name), f"Composition {comp!r} not found")
    return {"ok": True, "comps": item.GetFusionCompNameList() or []}


@router.post("/items/{item_id}/comps/{comp}/load")
def load_comp(item_id: str, comp: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Make the named comp the active one for the item."""
    item = bridge.item(item_id)
    require(item.LoadFusionCompByName(comp), f"Composition {comp!r} not found")
    return {"ok": True}


@router.post("/items/{item_id}/comps/{comp}/export")
def export_comp(item_id: str, comp: str, body: CompExport, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    names = item.GetFusionCompNameList() or []
    index = int(comp) if comp.isdigit() else (names.index(comp) + 1 if comp in names else None)
    if index is None:
        raise NotFound(f"Composition {comp!r} not found")
    require(item.ExportFusionComp(body.path, index), f"Resolve refused to export the comp to {body.path!r}")
    return {"ok": True, "path": body.path}


# -- tools --------------------------------------------------------------------------


@router.get("/items/{item_id}/comps/{comp}/tools")
def list_tools(item_id: str, comp: str, type: Optional[str] = Query(default=None, description="Only tools of this RegID, e.g. TextPlus, Merge, Background"), bridge: ResolveBridge = Depends(resolve_session)):
    c = _comp(bridge, item_id, comp)
    tools = [t for t in _tools(c) if type is None or tool_summary(t)["id"] == type]
    return {"attrs": jsonable(safe(c.GetAttrs, default={})), "tools": [tool_summary(t) for t in tools]}


@router.post("/items/{item_id}/comps/{comp}/tools")
def add_tool(item_id: str, comp: str, body: AddTool, bridge: ResolveBridge = Depends(resolve_session)):
    c = _comp(bridge, item_id, comp)
    try:
        tool = c.AddTool(body.tool_id, body.x, body.y) if body.x is not None and body.y is not None else c.AddTool(body.tool_id)
    except Exception as e:
        raise Rejected(f"comp.AddTool({body.tool_id!r}) failed: {e}") from e
    if not tool:
        raise Rejected(f"Fusion did not create a {body.tool_id!r} tool (unknown RegID?)")
    if body.name:
        safe(tool.SetAttrs, {"TOOLS_Name": body.name})
    results = _set_inputs(tool, body.inputs) if body.inputs else {}
    return {"ok": True, "tool": _tool_detail(tool), "inputs_set": results}


@router.get("/items/{item_id}/comps/{comp}/tools/{tool}")
def get_tool(item_id: str, comp: str, tool: str, bridge: ResolveBridge = Depends(resolve_session)):
    return _tool_detail(_tool(_comp(bridge, item_id, comp), tool))


_INPUT_ATTRS = {
    "INPS_Name": "name",
    "INPS_ID": "id",
    "INPID_InputControl": "control",
    "INPS_DataType": "data_type",
    "INPN_MinScale": "min",
    "INPN_MaxScale": "max",
    "INPN_MinAllowed": "min_allowed",
    "INPN_MaxAllowed": "max_allowed",
    "INPN_Default": "default",
    "INPS_Default": "default",
    "INPB_Connected": "connected",
    "INPS_ICS_ControlPage": "page",
    "INPB_Integer": "integer",
    "INPB_Visible": "visible",
}


@router.get("/items/{item_id}/comps/{comp}/tools/{tool}/inputs")
def list_tool_inputs(item_id: str, comp: str, tool: str, page: Optional[str] = Query(default=None, description="Only inputs on this Inspector page (INPS_ICS_ControlPage), e.g. 'Text', 'Layout', 'Shading', 'Settings'"), bridge: ResolveBridge = Depends(resolve_session)):
    """Parameter discovery for any tool - including macros/templates from the
    Effects Library: every input with its control type, range, default,
    current value and expression. This is how an agent learns what a
    template exposes before setting it."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    out = []
    try:
        inputs = t.GetInputList() or {}
    except Exception as e:
        raise Rejected(f"GetInputList failed: {e}") from e
    for inp in inputs.values():
        attrs = safe(inp.GetAttrs, default={}) or {}
        row = {alias: jsonable(attrs[key]) for key, alias in _INPUT_ATTRS.items() if key in attrs}
        key = row.get("id") or row.get("name")
        if not key:
            continue
        if page and str(row.get("page", "")).lower() != page.lower():
            continue
        row["value"] = jsonable(safe(t.GetInput, key))
        expr = safe(inp.GetExpression)
        if expr:
            row["expression"] = expr
        out.append(row)
    return {"tool": tool_summary(t), "inputs": out}


@router.put("/items/{item_id}/comps/{comp}/tools/{tool}/expression")
def set_tool_expression(item_id: str, comp: str, tool: str, body: ToolExpression, bridge: ResolveBridge = Depends(resolve_session)):
    """Drive an input by a Fusion expression (e.g. `time/30`, `Transform1.Angle*2`); null removes it."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    try:
        inp = getattr(t, body.input)
        inp.SetExpression(body.expression)
        current = safe(inp.GetExpression)
    except Exception as e:
        raise Rejected(f"SetExpression on {body.input!r} failed: {e}") from e
    return {"ok": True, "input": body.input, "expression": current}


@router.patch("/items/{item_id}/comps/{comp}/tools/{tool}")
def patch_tool(item_id: str, comp: str, tool: str, body: PatchTool, bridge: ResolveBridge = Depends(resolve_session)):
    """Rename a tool or toggle bypass (pass-through)."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    attrs = {}
    if body.name is not None:
        attrs["TOOLS_Name"] = body.name
    if body.pass_through is not None:
        attrs["TOOLB_PassThrough"] = body.pass_through
    if body.locked is not None:
        attrs["TOOLB_Locked"] = body.locked
    if attrs:
        try:
            t.SetAttrs(attrs)
        except Exception as e:
            raise Rejected(f"SetAttrs failed: {e}") from e
    if body.tile_color is not None:
        try:
            if body.tile_color:
                r, g, b = body.tile_color[:3]
                t.TileColor = {"R": r, "G": g, "B": b}
            else:
                t.TileColor = None
        except Exception as e:
            raise Rejected(f"TileColor failed: {e}") from e
    if body.position is not None:
        c = _comp(bridge, item_id, comp)
        try:
            flow = c.CurrentFrame.FlowView
            flow.SetPos(t, float(body.position[0]), float(body.position[1]))
        except Exception as e:
            raise Rejected(f"FlowView.SetPos failed: {e}") from e
    return {"ok": True, "tool": tool_summary(t)}


@router.delete("/items/{item_id}/comps/{comp}/tools/{tool}")
def delete_tool(item_id: str, comp: str, tool: str, bridge: ResolveBridge = Depends(resolve_session)):
    t = _tool(_comp(bridge, item_id, comp), tool)
    try:
        t.Delete()
    except Exception as e:
        raise Rejected(f"tool.Delete failed: {e}") from e
    return {"ok": True}


@router.patch("/items/{item_id}/comps/{comp}/tools/{tool}/inputs")
def set_tool_inputs(item_id: str, comp: str, tool: str, body: ToolInputs, bridge: ResolveBridge = Depends(resolve_session)):
    """Set tool inputs (optionally at a frame = keyframe). Lists of 2-4 numbers become Fusion point/color tables."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    results = _set_inputs(t, body.inputs, body.frame)
    return {"results": results, "tool": _tool_detail(t)}


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/connect")
def connect_tool_input(item_id: str, comp: str, tool: str, body: ConnectInput, bridge: ResolveBridge = Depends(resolve_session)):
    c = _comp(bridge, item_id, comp)
    t, src = _tool(c, tool), _tool(c, body.source_tool)
    try:
        ok = t.ConnectInput(body.input, src)
    except Exception as e:
        raise Rejected(f"ConnectInput failed: {e}") from e
    require(ok is not False, f"Fusion refused to connect {body.source_tool} -> {tool}.{body.input}")
    return {"ok": True}


def animate_input(comp, tool, input_name: str, keyframes: dict, replace: bool = True) -> dict:
    """Keyframe `tool.<input>` properly. A bare `tool.Input[frame] = value`
    writes a STATIC value unless a spline is attached, and attaching one adds a
    stray key at the comp's current time - so: attach a BezierSpline if the
    input is not animated, then set all keys wholesale with SetKeyFrames."""
    keys = {float(frame): (value if isinstance(value, dict) else {1: value}) for frame, value in keyframes.items()}
    inp = getattr(tool, input_name)
    out = safe(inp.GetConnectedOutput)
    if out is None:
        # Attaching a spline drops a key at the comp's CURRENT time holding the
        # OLD static value, and SetKeyFrames(replace=True) does not remove it.
        # So: make the static value equal the first key, and park the comp time
        # on the first key's frame - the stray key then coincides with ours.
        first_frame = min(keys)
        first_value = keys[first_frame]
        safe(tool.SetInput, input_name, first_value[1] if set(first_value) == {1} else first_value)
        safe(comp.SetAttrs, {"COMPN_CurrentTime": first_frame})
        setattr(tool, input_name, comp.BezierSpline())
        inp = getattr(tool, input_name)
        out = safe(inp.GetConnectedOutput)
    spline = safe(out.GetTool) if out else None
    if spline is not None and hasattr(spline, "SetKeyFrames"):
        spline.SetKeyFrames(keys, replace)
        return {"mode": "spline", "keys": len(keys)}
    for frame, value in keyframes.items():  # last resort: frame-indexed writes
        inp[frame] = value
    return {"mode": "indexed", "keys": len(keys)}


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/keyframes")
def set_tool_keyframes(item_id: str, comp: str, tool: str, body: ToolKeyframes, bridge: ResolveBridge = Depends(resolve_session)):
    """Animate an input with real keyframes: attaches a BezierSpline when the
    input is static and sets all keys at once (replacing existing ones by
    default). Lists of 2-4 numbers become point/colour keys. Tip: for simple
    fades an expression is just as good - see PUT .../expression."""
    c = _comp(bridge, item_id, comp)
    t = _tool(c, tool)
    try:
        info = animate_input(c, t, body.input, {kf.frame: _fusion_value(kf.value) for kf in body.keyframes}, body.replace)
    except Exception as e:
        raise Rejected(f"Could not keyframe {tool}.{body.input}: {type(e).__name__}: {e}") from e
    values = {kf.frame: jsonable(safe(t.GetInput, body.input, kf.frame)) for kf in body.keyframes}
    return {"ok": True, **info, "values_at_keys": values, "all_ok": True, "results": [{"frame": kf.frame, "ok": True} for kf in body.keyframes]}


# -- Text+ ------------------------------------------------------------------------------


def set_text_plus(bridge: ResolveBridge, item, text: str, comp: Optional[str] = None, tool: Optional[str] = None, **inputs) -> dict:
    """Set StyledText (and optional font/size/color/center) on a Text+ tool.
    Used by the fusion_title insert too."""
    c = bridge.fusion_comp(item, comp)
    if tool:
        t = _tool(c, tool)
    else:
        candidates = [x for x in _tools(c) if tool_summary(x)["id"] == "TextPlus"]
        if not candidates:
            raise NotFound("No Text+ (TextPlus) tool in the composition")
        t = candidates[0]
    values = {"StyledText": text, **inputs}
    return {"tool": tool_summary(t)["name"], "results": _set_inputs(t, values)}


@router.post("/items/{item_id}/text-plus")
def text_plus(item_id: str, body: TextPlus, comp: Optional[str] = Query(default=None), bridge: ResolveBridge = Depends(resolve_session)):
    """Data-driven titles: set the text/font/size/color/position of a Text+ tool
    on a Fusion title or Fusion clip. Insert one first with
    POST /timelines/current/generators {kind: fusion_title, name: 'Text+'}."""
    inputs: dict = dict(body.extra_inputs)
    if body.font:
        inputs["Font"] = body.font
    if body.style:
        inputs["Style"] = body.style
    if body.size is not None:
        inputs["Size"] = body.size
    if body.color:
        r, g, b = body.color[:3]
        inputs.update({"Red1": r, "Green1": g, "Blue1": b})
        if len(body.color) > 3:
            inputs["Alpha1"] = body.color[3]
    if body.center:
        inputs["Center"] = body.center
    if body.shadow is not None:
        inputs["Enabled3"] = 1 if body.shadow else 0
    if body.outline:
        r, g, b = body.outline[:3]
        inputs.update({"Enabled2": 1, "Red2": r, "Green2": g, "Blue2": b})
        if body.outline_thickness is not None:
            inputs["Thickness2"] = body.outline_thickness
    if body.tracking is not None:
        inputs["CharacterSpacing"] = body.tracking
    if body.line_spacing is not None:
        inputs["LineSpacing"] = body.line_spacing
    return set_text_plus(bridge, bridge.item(item_id), body.text, comp, body.tool, **inputs)


# -- the Fusion page's current comp ---------------------------------------------------------


@router.get("/current-comp")
def current_comp(bridge: ResolveBridge = Depends(resolve_session)):
    """Tools of the comp open on the Fusion page (fusion.GetCurrentComp())."""
    c = bridge.fusion().GetCurrentComp()
    if not c:
        raise NotFound("No composition is open on the Fusion page")
    return {"attrs": jsonable(safe(c.GetAttrs, default={})), "tools": [tool_summary(t) for t in _tools(c)]}


@router.patch("/current-comp/tools/{tool}/inputs")
def set_current_comp_inputs(tool: str, body: ToolInputs, bridge: ResolveBridge = Depends(resolve_session)):
    c = bridge.fusion().GetCurrentComp()
    if not c:
        raise NotFound("No composition is open on the Fusion page")
    t = _tool(c, tool)
    return {"results": _set_inputs(t, body.inputs, body.frame), "tool": _tool_detail(t)}
