"""Fusion, third part: comp markers, the active tool, undo/redo history, key
time navigation, tool selection, cutting connections, output listing, the
tool registry, input reset and a multi-line Text+ convenience.

UNVERIFIED on live Resolve (the live-probe pass must check these; the fake
mirrors the shapes assumed here):

- comp.GetMarkers() -> {frame: {Name, Note, Color}} and comp.SetMarker(frame,
  table | None) - marker names/shape are a guess from Fusion 9+ docs.
- comp.ActiveTool (attribute) and comp.SetActiveTool(tool | None).
- comp.GetUndoStack() / comp.GetRedoStack() (table shape unknown: strings or
  {Name=...}); comp.Undo(n) / comp.Redo(n) / comp.ClearUndo() are documented.
- comp.GetNextKeyTime(t) / comp.GetPrevKeyTime(t): what "no key" returns
  (nil, the same time, or a +-1e9 sentinel) is unknown - all are read as
  "not found".
- tool.SetAttrs({TOOLB_Selected}) may be read-only; FlowView.Select() (only
  when the comp is loaded on the Fusion page) is used as well.
- tool.GetOutputList() / output.GetConnectedInputs() / input.GetTool().
- fusion.GetRegSummary() - shape unknown, parsed defensively.
- INPN_Default in input attrs (numeric inputs).

Same rule as fusion.py: every Fusion call is wrapped so an unsupported one
answers 422 (or 404 for a missing thing), never a 500."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query

from ..bridge import NotFound, Rejected, ResolveBridge
from ..deps import resolve_session
from ..schemas import CompHistoryStep, CompMarker, DisconnectInput, ResetInput, SelectTools, SetActiveTool, TextPlusLines
from ..serialize import jsonable, safe, tool_summary
from .fusion import _comp, _tool, _tools, set_text_plus

router = APIRouter(prefix="/fusion", tags=["fusion"])

# Sources that are modifiers (animation / derived values), not upstream image tools.
_MODIFIER_IDS = {"BezierSpline", "PolyPath", "Path", "XYPath", "Shake", "Calculation", "Offset", "Expression", "Probe", "KeyStretcher", "Perturb", "Follower", "LUTBezier"}
_NO_KEY = 1e8  # GetNext/PrevKeyTime sentinels beyond this mean "no key"


def _frame_label(frame) -> Any:
    try:
        f = float(frame)
    except (TypeError, ValueError):
        return frame
    return int(f) if f.is_integer() else f


def _values(table) -> list:
    """A Fusion 1-based table (dict) or a list -> list of values in order."""
    if isinstance(table, dict):
        return [table[k] for k in sorted(table, key=lambda k: (not isinstance(k, (int, float)), k if isinstance(k, (int, float)) else str(k)))]
    if isinstance(table, (list, tuple)):
        return list(table)
    return []


# -- comp markers -------------------------------------------------------------------


def _markers(comp) -> List[Dict[str, Any]]:
    try:
        raw = comp.GetMarkers() or {}
    except Exception as e:
        raise Rejected(f"comp.GetMarkers failed: {e}") from e
    out = []
    for frame, m in (raw.items() if isinstance(raw, dict) else []):
        m = m if isinstance(m, dict) else {}
        out.append({"frame": _frame_label(frame), "name": m.get("Name"), "note": m.get("Note"), "color": m.get("Color")})
    return sorted(out, key=lambda x: float(x["frame"]) if isinstance(x["frame"], (int, float)) else 0)


@router.get("/items/{item_id}/comps/{comp}/markers")
def fusion_comp_markers(item_id: str, comp: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Markers on the comp's own time ruler (comp.GetMarkers). These are
    Fusion comp markers, not timeline or clip markers (see /markers routes)."""
    return {"markers": _markers(_comp(bridge, item_id, comp))}


@router.put("/items/{item_id}/comps/{comp}/markers")
def set_fusion_comp_marker(item_id: str, comp: str, body: CompMarker, bridge: ResolveBridge = Depends(resolve_session)):
    """Add or replace the comp marker at `frame` (comp.SetMarker(frame, {Name, Note, Color}))."""
    c = _comp(bridge, item_id, comp)
    marker = {"Name": body.name, "Note": body.note or "", **({"Color": body.color} if body.color else {})}
    try:
        ok = c.SetMarker(body.frame, marker)
    except Exception as e:
        raise Rejected(f"comp.SetMarker failed: {e}") from e
    if ok is False:
        raise Rejected(f"Fusion refused the marker at frame {body.frame}")
    return {"ok": True, "markers": _markers(c)}


@router.delete("/items/{item_id}/comps/{comp}/markers")
def delete_fusion_comp_marker(item_id: str, comp: str, frame: int = Query(description="Frame of the marker to remove"), bridge: ResolveBridge = Depends(resolve_session)):
    """Remove the comp marker at `frame` (comp.SetMarker(frame, nil)); 404 when there is none."""
    c = _comp(bridge, item_id, comp)
    if not any(m["frame"] == frame for m in _markers(c)):
        raise NotFound(f"No comp marker at frame {frame}")
    try:
        c.SetMarker(frame, None)
    except Exception as e:
        raise Rejected(f"comp.SetMarker(frame, nil) failed: {e}") from e
    return {"ok": True, "markers": _markers(c)}


# -- active tool --------------------------------------------------------------------


@router.get("/items/{item_id}/comps/{comp}/active-tool")
def get_active_tool(item_id: str, comp: str, bridge: ResolveBridge = Depends(resolve_session)):
    """The tool shown in the Inspector (comp.ActiveTool); `tool` is null when none."""
    c = _comp(bridge, item_id, comp)
    active = safe(lambda: c.ActiveTool)
    return {"tool": tool_summary(active) if active else None}


@router.put("/items/{item_id}/comps/{comp}/active-tool")
def set_active_tool(item_id: str, comp: str, body: SetActiveTool, bridge: ResolveBridge = Depends(resolve_session)):
    """Make a tool the active one (comp.SetActiveTool). Only visible in the UI
    when the comp is open on the Fusion page."""
    c = _comp(bridge, item_id, comp)
    t = _tool(c, body.tool)
    try:
        c.SetActiveTool(t)
    except Exception as e:
        raise Rejected(f"comp.SetActiveTool failed: {e}") from e
    active = safe(lambda: c.ActiveTool)
    return {"ok": True, "tool": tool_summary(active) if active else None}


@router.delete("/items/{item_id}/comps/{comp}/active-tool")
def clear_active_tool(item_id: str, comp: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Clear the active tool (comp.SetActiveTool(nil))."""
    c = _comp(bridge, item_id, comp)
    try:
        c.SetActiveTool(None)
    except Exception as e:
        raise Rejected(f"comp.SetActiveTool(nil) failed: {e}") from e
    return {"ok": True, "tool": None}


# -- undo / redo history ---------------------------------------------------------------


def _stack_names(table) -> List[str]:
    names = []
    for entry in _values(table):
        if isinstance(entry, dict):
            names.append(str(entry.get("Name") or entry.get("Note") or entry.get(1) or ""))
        elif entry is not None:
            names.append(str(entry))
    return names


def _history(comp) -> Dict[str, Any]:
    errors = []
    stacks = {}
    for key, getter in (("undo", "GetUndoStack"), ("redo", "GetRedoStack")):
        try:
            stacks[key] = _stack_names(getattr(comp, getter)())
        except Exception as e:
            errors.append(f"comp.{getter} failed: {e}")
            stacks[key] = None
    if len(errors) == 2:
        raise Rejected("; ".join(errors))
    return stacks


@router.get("/items/{item_id}/comps/{comp}/history")
def comp_history(item_id: str, comp: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Undo and redo stacks as lists of step names, oldest first
    (comp.GetUndoStack / GetRedoStack). A stack that cannot be read is null."""
    return _history(_comp(bridge, item_id, comp))


@router.post("/items/{item_id}/comps/{comp}/history")
def comp_history_step(item_id: str, comp: str, body: CompHistoryStep, bridge: ResolveBridge = Depends(resolve_session)):
    """Undo or redo `count` steps (comp.Undo(n) / comp.Redo(n)). Trap: this is
    the comp's own history, not Resolve's edit-page undo."""
    c = _comp(bridge, item_id, comp)
    try:
        (c.Undo if body.action == "undo" else c.Redo)(body.count)
    except Exception as e:
        raise Rejected(f"comp.{body.action.capitalize()} failed: {e}") from e
    return {"ok": True, "action": body.action, "count": body.count, **_history(c)}


@router.delete("/items/{item_id}/comps/{comp}/history")
def clear_comp_history(item_id: str, comp: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Forget the comp's undo history (comp.ClearUndo); cannot be undone."""
    c = _comp(bridge, item_id, comp)
    try:
        c.ClearUndo()
    except Exception as e:
        raise Rejected(f"comp.ClearUndo failed: {e}") from e
    return {"ok": True}


# -- key time navigation ----------------------------------------------------------------


@router.get("/items/{item_id}/comps/{comp}/key-times")
def comp_key_time(
    item_id: str,
    comp: str,
    from_: float = Query(alias="from", description="Comp frame to search from (exclusive)"),
    direction: Literal["next", "prev"] = Query(default="next"),
    bridge: ResolveBridge = Depends(resolve_session),
):
    """The next / previous keyframe time across the comp (comp.GetNextKeyTime /
    GetPrevKeyTime). `found` is false when Fusion answers nothing, the same
    time or a +-1e9 sentinel."""
    c = _comp(bridge, item_id, comp)
    try:
        t = (c.GetNextKeyTime if direction == "next" else c.GetPrevKeyTime)(from_)
    except Exception as e:
        raise Rejected(f"comp.Get{'Next' if direction == 'next' else 'Prev'}KeyTime failed: {e}") from e
    try:
        t = float(t) if t is not None else None
    except (TypeError, ValueError):
        t = None
    if t is None or abs(t) >= _NO_KEY or t == float(from_) or (direction == "next" and t < from_) or (direction == "prev" and t > from_):
        return {"from": _frame_label(from_), "direction": direction, "frame": None, "found": False}
    return {"from": _frame_label(from_), "direction": direction, "frame": _frame_label(t), "found": True}


# -- selection ------------------------------------------------------------------------


def _selected(comp) -> list:
    try:
        listed = comp.GetToolList(True) or {}
    except Exception as e:
        raise Rejected(f"comp.GetToolList(true) failed: {e}") from e
    return [tool_summary(t) for t in _values(listed)]


@router.get("/items/{item_id}/comps/{comp}/selection")
def comp_selection(item_id: str, comp: str, bridge: ResolveBridge = Depends(resolve_session)):
    """The selected tools (comp.GetToolList(true))."""
    return {"tools": _selected(_comp(bridge, item_id, comp))}


@router.post("/items/{item_id}/comps/{comp}/tools/select")
def select_tools(item_id: str, comp: str, body: SelectTools, bridge: ResolveBridge = Depends(resolve_session)):
    """Select tools (TOOLB_Selected, plus FlowView.Select when the comp is open
    on the Fusion page). `exclusive` deselects everything else first. Returns
    the selection as Fusion reports it afterwards - check it, since selection
    attrs may be read-only on some builds."""
    c = _comp(bridge, item_id, comp)
    targets = [_tool(c, name) for name in body.tools]
    flow = safe(lambda: c.CurrentFrame.FlowView)
    try:
        if body.exclusive:
            cleared = False
            if flow is not None:
                try:
                    flow.Select()
                    cleared = True
                except Exception:
                    cleared = False
            if not cleared:
                for t in _tools(c):
                    t.SetAttrs({"TOOLB_Selected": False})
        for t in targets:
            t.SetAttrs({"TOOLB_Selected": True})
            if flow is not None:
                safe(flow.Select, t, True)
    except Exception as e:
        raise Rejected(f"Selecting tools failed: {e}") from e
    return {"ok": True, "tools": _selected(c)}


# -- connections: disconnect, outputs -----------------------------------------------------


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/disconnect")
def disconnect_tool_input(item_id: str, comp: str, tool: str, body: DisconnectInput, bridge: ResolveBridge = Depends(resolve_session)):
    """Cut the upstream tool connection into an input (input.ConnectTo(nil)).
    422 when the input is not connected, or when it is driven by a modifier
    (spline, Shake, ...) - remove those with DELETE .../keyframes instead."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    inp = safe(getattr, t, body.input)
    if inp is None:
        raise NotFound(f"No input {body.input!r} on {tool}")
    out = safe(inp.GetConnectedOutput)
    if out is None:
        raise Rejected(f"{tool}.{body.input} is not connected")
    src = safe(out.GetTool)
    src_info = (safe(tool_summary, src) if src is not None else None) or {"name": safe(lambda: src.Name), "id": safe(lambda: src.ID)}
    if src_info["id"] in _MODIFIER_IDS:
        raise Rejected(f"{tool}.{body.input} is driven by a {src_info['id']} modifier, not a tool; use DELETE .../keyframes?input={body.input}")
    try:
        inp.ConnectTo(None)
    except Exception as e:
        raise Rejected(f"ConnectTo(nil) failed: {e}") from e
    if safe(inp.GetConnectedOutput) is not None:
        raise Rejected(f"Fusion kept {tool}.{body.input} connected")
    return {"ok": True, "input": body.input, "was_connected_to": src_info["name"]}


@router.get("/items/{item_id}/comps/{comp}/tools/{tool}/outputs")
def list_tool_outputs(item_id: str, comp: str, tool: str, bridge: ResolveBridge = Depends(resolve_session)):
    """The tool's outputs and, for each, the tool inputs it feeds
    (tool.GetOutputList / output.GetConnectedInputs)."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    try:
        outputs = _values(t.GetOutputList() or {})
    except Exception as e:
        raise Rejected(f"tool.GetOutputList failed: {e}") from e
    rows = []
    for out in outputs:
        attrs = safe(out.GetAttrs, default={}) or {}
        connected = []
        for inp in _values(safe(out.GetConnectedInputs, default={}) or {}):
            dest = safe(inp.GetTool)
            iattrs = safe(inp.GetAttrs, default={}) or {}
            connected.append({"tool": tool_summary(dest)["name"] if dest is not None else None, "input": iattrs.get("INPS_ID") or iattrs.get("INPS_Name")})
        rows.append({"id": attrs.get("OUTS_ID"), "name": attrs.get("OUTS_Name"), "data_type": attrs.get("OUTS_DataType"), "connected_to": connected})
    return {"tool": tool_summary(t), "outputs": rows}


# -- registry -------------------------------------------------------------------------


@router.get("/registry")
def fusion_registry(
    type: Optional[str] = Query(default=None, description="tool | modifier - filters on Category when the build reports one"),
    contains: Optional[str] = Query(default=None, description="Case-insensitive substring on id / name"),
    bridge: ResolveBridge = Depends(resolve_session),
):
    """Tool RegIDs Fusion knows (fusion.GetRegSummary), for POST .../tools
    {tool_id}. UNVERIFIED shape: values may be tables or plain strings; both
    are accepted. 422 when the build answers nothing."""
    fu = bridge.fusion()
    try:
        summary = fu.GetRegSummary()
    except Exception as e:
        raise Rejected(f"fusion.GetRegSummary failed: {e}") from e
    if not summary or not isinstance(summary, dict):
        raise Rejected("fusion.GetRegSummary returned nothing on this build")
    rows = []
    for key, value in summary.items():
        if isinstance(value, dict):
            rid = value.get("ID") or value.get("REGS_ID") or key
            rows.append({"id": str(rid), "name": value.get("Name") or value.get("REGS_Name") or str(rid), "category": value.get("Category") or value.get("REGS_Category")})
        elif isinstance(value, str):
            rows.append({"id": str(key), "name": value, "category": None})
    if type:
        want = type.lower()
        rows = [r for r in rows if r["category"] is None or ("modifier" in str(r["category"]).lower()) == (want == "modifier")]
    if contains:
        c = contains.lower()
        rows = [r for r in rows if c in r["id"].lower() or c in str(r["name"]).lower()]
    rows.sort(key=lambda r: r["id"].lower())
    return {"count": len(rows), "tools": rows}


# -- input reset ------------------------------------------------------------------------


@router.post("/items/{item_id}/comps/{comp}/tools/{tool}/reset-input")
def reset_tool_input(item_id: str, comp: str, tool: str, body: ResetInput, bridge: ResolveBridge = Depends(resolve_session)):
    """Set a numeric input back to its default (INPN_Default from the input's
    attrs). 422 when no default is known (text, points, images). Does not
    remove animation - clear keyframes first if the input is animated."""
    t = _tool(_comp(bridge, item_id, comp), tool)
    inp = safe(getattr, t, body.input)
    attrs = (safe(inp.GetAttrs, default={}) or {}) if inp is not None else {}
    if not attrs:
        raise NotFound(f"No input {body.input!r} on {tool}")
    default = attrs.get("INPN_Default")
    if not isinstance(default, (int, float)):
        raise Rejected(f"No default known for {tool}.{body.input} (data type {attrs.get('INPS_DataType')!r})")
    try:
        t.SetInput(body.input, default)
    except Exception as e:
        raise Rejected(f"SetInput failed: {e}") from e
    return {"ok": True, "input": body.input, "value": jsonable(safe(t.GetInput, body.input))}


# -- Text+ lines ------------------------------------------------------------------------


@router.post("/items/{item_id}/text-plus/lines")
def text_plus_lines(item_id: str, body: TextPlusLines, bridge: ResolveBridge = Depends(resolve_session)):
    """Set a multi-line Text+ in one call: lines are joined with newlines into
    StyledText. For font/size/colour use POST /items/{item_id}/text-plus."""
    return set_text_plus(bridge, bridge.item(item_id), "\n".join(body.lines), body.comp, body.tool)
