"""Timeline items (clips on tracks) - addressed by the unique id returned
from GET /timelines/current/items. 'current' addresses the video item under
the playhead."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..bridge import NotFound, Rejected, ResolveBridge, require
from ..deps import resolve_session
from ..schemas import AddTake, CacheSettings, Flag, ItemProperties, MagicMask, NamedPreset, DissolveItem, PatchItem, RelocateItem, RetimeItem, SplitItem, TrackType, VoiceIsolation
from ..serialize import item_summary, jsonable, safe
from .markers import mount_markers

router = APIRouter(prefix="/timelines/current/items", tags=["timeline items"])


def _summary(bridge: ResolveBridge, item, tl=None):
    tl = tl or bridge.current_timeline()
    tt, idx = safe(item.GetTrackTypeAndIndex, default=[None, None]) or [None, None]
    return item_summary(tt, idx, item, int(tl.GetStartFrame()))


@router.get("")
def list_items(
    bridge: ResolveBridge = Depends(resolve_session),
    track_type: Optional[TrackType] = Query(default=None),
    track_index: Optional[int] = Query(default=None, ge=1),
):
    """Every item on the current timeline with its id, track, and frame range.
    `start`/`end` are absolute Resolve frames; `start_rel`/`end_rel` are
    0-based from the timeline start (what the append endpoint speaks)."""
    tl = bridge.current_timeline()
    start = int(tl.GetStartFrame())
    items = [item_summary(tt, idx, it, start) for tt, idx, it in bridge.iter_items(tl, track_type, track_index)]
    return {"timeline": tl.GetName(), "start_frame": start, "items": items}


@router.get("/selected")
def selected_items(bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    return {"items": [_summary(bridge, it, tl) for it in tl.GetSelectedClips() or []]}


@router.get("/{item_id}")
def get_item(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    out = _summary(bridge, item)
    out["properties"] = jsonable(safe(item.GetProperty, default={}))
    out["current_version"] = safe(item.GetCurrentVersion)
    out["fusion_comp_names"] = safe(item.GetFusionCompNameList, default=[])
    out["takes"] = safe(item.GetTakesCount, default=0)
    group = safe(item.GetColorGroup)
    out["color_group"] = safe(group.GetName) if group else None
    return out


@router.patch("/{item_id}")
def patch_item(item_id: str, body: PatchItem, bridge: ResolveBridge = Depends(resolve_session)):
    """Rename, enable/disable, recolor, and/or set Inspector properties
    (Pan/Tilt/Zoom/Rotation/Crop/Opacity/CompositeMode/Retime/Scaling...)."""
    item = bridge.item(item_id)
    results = {}
    if body.name is not None:
        results["name"] = bool(item.SetName(body.name))
    if body.enabled is not None:
        results["enabled"] = bool(item.SetClipEnabled(body.enabled))
    if body.color is not None:
        results["color"] = bool(item.ClearClipColor() if body.color == "" else item.SetClipColor(body.color))
    if body.properties:
        results["properties"] = {k: bool(item.SetProperty(k, v)) for k, v in body.properties.items()}
    return {"results": results, "item": _summary(bridge, item)}


@router.delete("/{item_id}")
def delete_item(item_id: str, ripple: bool = Query(default=False), bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    item = bridge.item(item_id, tl)
    return {"ok": bool(tl.DeleteClips([item], ripple))}


@router.get("/{item_id}/properties")
def item_properties(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"properties": jsonable(bridge.item(item_id).GetProperty() or {})}


@router.put("/{item_id}/properties")
def set_item_properties(item_id: str, body: ItemProperties, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    return {"results": {k: bool(item.SetProperty(k, v)) for k, v in body.properties.items()}}


@router.post("/{item_id}/flags")
def add_item_flag(item_id: str, body: Flag, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    require(item.AddFlag(body.color), f"Resolve refused flag color {body.color!r}")
    return {"flags": item.GetFlagList()}


@router.delete("/{item_id}/flags")
def clear_item_flags(item_id: str, color: str = Query(default="All"), bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    item.ClearFlags(color)
    return {"flags": item.GetFlagList()}


@router.get("/{item_id}/linked")
def linked_items(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    return {"items": [_summary(bridge, it, tl) for it in bridge.item(item_id, tl).GetLinkedItems() or []]}


@router.get("/{item_id}/audio-mapping")
def item_audio_mapping(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    import json

    raw = bridge.item(item_id).GetSourceAudioChannelMapping()
    try:
        return {"mapping": json.loads(raw) if isinstance(raw, str) else raw}
    except ValueError:
        return {"mapping_raw": raw}


# -- composite edits the API lacks natively -----------------------------------


def _snapshot(bridge: ResolveBridge, item, tl):
    tt, idx = safe(item.GetTrackTypeAndIndex, default=[None, None]) or [None, None]
    start = int(tl.GetStartFrame())
    return {
        "mpi": safe(item.GetMediaPoolItem),
        "track_type": tt,
        "track_index": idx,
        "record_rel": int(item.GetStart()) - start,
        "source_start": safe(item.GetSourceStartFrame),
        "source_end": safe(item.GetSourceEndFrame),
        "name": safe(item.GetName),
        "color": safe(item.GetClipColor),
        "enabled": safe(item.GetClipEnabled),
        "properties": safe(item.GetProperty, default={}) or {},
        "markers": safe(item.GetMarkers, default={}) or {},
        "comp_names": safe(item.GetFusionCompNameList, default=[]) or [],
    }


def _reappend(bridge: ResolveBridge, tl, snap: dict, record_rel: int, track_index: int, source_start: int, source_end: int):
    """Re-create an item from a snapshot; restores properties, name, color,
    enabled state and markers. Returns the new item or raises."""
    if snap["mpi"] is None:
        raise Rejected("Only media-pool-backed items can be relocated (generators/titles have no source clip)")
    info = {
        "mediaPoolItem": snap["mpi"],
        "trackIndex": track_index,
        "recordFrame": int(tl.GetStartFrame()) + record_rel,
        "startFrame": source_start,
        "endFrame": source_end,
        "mediaType": 1 if snap["track_type"] == "video" else 2,
    }
    created = bridge.media_pool().AppendToTimeline([info])
    new = created[0] if created else None
    if not new:
        raise Rejected("Resolve refused to re-append the item at the new position (locked track? overlap on the same track?)")
    if snap["properties"]:
        safe(new.SetProperty, dict(snap["properties"]))
    if snap["name"]:
        safe(new.SetName, snap["name"])
    if snap["color"]:
        safe(new.SetClipColor, snap["color"])
    if snap["enabled"] is False:
        safe(new.SetClipEnabled, False)
    for frame, m in snap["markers"].items():
        safe(new.AddMarker, int(float(frame)), m.get("color", "Blue"), m.get("name", ""), m.get("note", ""), m.get("duration", 1), m.get("customData", ""))
    return new


def relocate_one(bridge: ResolveBridge, tl, old, record_rel=None, track_index=None, source_start=None, source_end=None, ripple=False) -> dict:
    """Re-create `old` at a new position/trim; copies grade + Fusion comps when
    the new placement does not overlap the old one on the same track."""
    import os
    import tempfile

    snap = _snapshot(bridge, old, tl)
    record_rel = snap["record_rel"] if record_rel is None else record_rel
    track_index = snap["track_index"] if track_index is None else track_index
    source_start = snap["source_start"] if source_start is None else source_start
    source_end = snap["source_end"] if source_end is None else source_end
    if source_end is not None and source_start is not None and source_end < source_start:
        raise Rejected("end_frame must be >= start_frame")
    new_len = (source_end - source_start) if None not in (source_start, source_end) else int(old.GetDuration())
    old_end_rel = snap["record_rel"] + int(old.GetDuration())
    same_track = track_index == snap["track_index"]
    overlaps = same_track and record_rel < old_end_rel and record_rel + new_len > snap["record_rel"]

    comp_files = []
    tmpdir = tempfile.mkdtemp(prefix="dollygrip-comps-") if snap["comp_names"] else None
    for i, name in enumerate(snap["comp_names"], start=1):
        path = os.path.join(tmpdir, f"{i}.comp")
        if safe(old.ExportFusionComp, path, i):
            comp_files.append((name, path))

    grade_copied = False
    if overlaps:
        require(tl.DeleteClips([old], ripple), "Resolve refused to delete the original item")
        new = _reappend(bridge, tl, snap, record_rel, track_index, source_start, source_end)
    else:
        new = _reappend(bridge, tl, snap, record_rel, track_index, source_start, source_end)
        grade_copied = bool(safe(old.CopyGrades, [new]))
        require(tl.DeleteClips([old], ripple), "Re-appended, but Resolve refused to delete the original item")

    comps_restored = 0
    for name, path in comp_files:
        comp = safe(new.ImportFusionComp, path)
        if comp:
            comps_restored += 1
            imported_name = safe(lambda: comp.GetAttrs().get("COMPS_Name")) or safe(lambda: comp.name)
            if imported_name and imported_name != name:
                safe(new.RenameFusionCompByName, imported_name, name)
    summary = _summary(bridge, new, tl)
    notes = []
    if overlaps:
        notes.append("same-track overlap: deleted first, grade not preserved")
    if summary.get("start_rel") is not None and summary["start_rel"] != record_rel:
        notes.append(f"Resolve pushed the item to frame {summary['start_rel']} (requested {record_rel}) - something else occupies that range on the track")
    if summary.get("duration") is not None and summary["duration"] != new_len:
        notes.append(f"Resolve trimmed the item to {summary['duration']} frames (requested {new_len}) - collision on the track")
    return {
        "ok": True,
        "item": summary,
        "grade_copied": grade_copied,
        "fusion_comps_restored": comps_restored,
        "placed_as_requested": not any("pushed" in n or "trimmed" in n for n in notes),
        "note": "; ".join(notes) if notes else None,
        "_delta": record_rel - snap["record_rel"],
    }


@router.post("/{item_id}/relocate")
def relocate_item(item_id: str, body: RelocateItem, bridge: ResolveBridge = Depends(resolve_session)):
    """Move and/or trim an item. Resolve's API cannot edit an item in place, so
    this re-appends the same source range at the new position, copies the
    grade (CopyGrades) and Fusion comps (export/import) onto the new item,
    restores Inspector properties/name/color/markers, then deletes the old
    one. Caveats: same-track moves that overlap the old position are done
    delete-first (grade is lost - Resolve has no grade read-back). With
    `with_linked` the linked items (the audio of an A/V clip) move by the
    same offset and get the same trim."""
    tl = bridge.current_timeline()
    old = bridge.item(item_id, tl)
    linked = list(safe(old.GetLinkedItems, default=[]) or []) if body.with_linked else []
    result = relocate_one(bridge, tl, old, body.record_frame, body.track_index, body.start_frame, body.end_frame, body.ripple)
    delta = result.pop("_delta")
    moved_linked = []
    for item in linked:
        rel = int(item.GetStart()) - int(tl.GetStartFrame())
        r = relocate_one(bridge, tl, item, rel + delta, None, body.start_frame, body.end_frame, body.ripple)
        r.pop("_delta", None)
        moved_linked.append(r["item"])
    result["linked_items"] = moved_linked
    return result


@router.post("/{item_id}/split")
def split_item(item_id: str, body: SplitItem, bridge: ResolveBridge = Depends(resolve_session)):
    """Cut an item in two at a timeline frame (re-appends both halves with the
    same source mapping; properties/name/color restored). Returns both new
    item ids. Grades are not preserved (no grade read-back in the API)."""
    tl = bridge.current_timeline()
    old = bridge.item(item_id, tl)
    snap = _snapshot(bridge, old, tl)
    dur = int(old.GetDuration())
    offset = body.frame - snap["record_rel"]
    if not 0 < offset < dur:
        raise Rejected(f"frame {body.frame} is not strictly inside the item ({snap['record_rel']}..{snap['record_rel'] + dur})")
    ss, se = snap["source_start"], snap["source_end"]
    if None in (ss, se):
        raise Rejected("Item has no source range to split")
    # source frames per timeline frame (retimed or mixed-fps items are not 1:1)
    scale = (se - ss) / dur if dur else 1
    cut_src = ss + int(round(offset * scale))
    require(tl.DeleteClips([old], False), "Resolve refused to delete the original item")
    left = _reappend(bridge, tl, snap, snap["record_rel"], snap["track_index"], ss, cut_src)  # endFrame is exclusive
    right = _reappend(bridge, tl, snap, body.frame, snap["track_index"], cut_src, se)
    return {"ok": True, "items": [_summary(bridge, left, tl), _summary(bridge, right, tl)]}


# -- takes -----------------------------------------------------------------


# -- retime (composite: the API has RetimeProcess but no speed setter) -----------------

RETIME_TOOL = "DollyGripRetime"


def _shift_after(bridge: ResolveBridge, tl, from_rel: int, delta: int, exclude_id: str) -> list:
    """Move every media-backed item that starts at/after `from_rel` by `delta`
    frames (right-to-left when pushing, left-to-right when pulling)."""
    start_abs = int(tl.GetStartFrame())
    affected = []
    for tt, idx, item in bridge.iter_items(tl):
        if tt == "subtitle" or safe(item.GetUniqueId) == exclude_id:
            continue
        rel = int(item.GetStart()) - start_abs
        if rel >= from_rel and safe(item.GetMediaPoolItem) is not None:
            affected.append((rel, item))
    moved = []
    for rel, item in sorted(affected, key=lambda x: -x[0] if delta > 0 else x[0]):
        r = relocate_one(bridge, tl, item, rel + delta)
        moved.append({"id": r["item"]["id"], "start_rel": r["item"]["start_rel"]})
    return moved


def _insert_timespeed(bridge: ResolveBridge, item, speed: float, delay: float, interpolate: bool, hold_first: int, hold_last: int) -> dict:
    """Put (or update) a TimeSpeed between MediaIn and whatever it fed in the
    item's first Fusion comp; creates the comp when there is none."""
    from .fusion import _tool, _tools
    from .fusion_more import graph_of

    if int(item.GetFusionCompCount() or 0) == 0:
        require(item.AddFusionComp(), "Resolve could not add a Fusion composition to the item")
    comp = bridge.fusion_comp(item, None)
    tools = _tools(comp)
    by_id = {}
    for t in tools:
        attrs = safe(t.GetAttrs, default={}) or {}
        by_id.setdefault(attrs.get("TOOLS_RegID"), []).append(attrs.get("TOOLS_Name"))
    media_in = (by_id.get("MediaIn") or [None])[0]
    if media_in is None:
        raise Rejected("The item's Fusion comp has no MediaIn tool")
    existing = safe(comp.FindTool, RETIME_TOOL)
    if existing is None:
        graph = graph_of(comp)
        consumers = [e for e in graph["edges"] if e["from"] == media_in]
        ts = comp.AddTool("TimeSpeed", -32768, -32768)
        require(ts, "Fusion refused to add a TimeSpeed tool")
        ts.SetAttrs({"TOOLS_Name": RETIME_TOOL})
        ts = _tool(comp, RETIME_TOOL)
        ts.ConnectInput("Input", _tool(comp, media_in))
        if not consumers and by_id.get("MediaOut"):
            consumers = [{"to": by_id["MediaOut"][0], "input": "Input"}]
        for e in consumers:
            _tool(comp, e["to"]).ConnectInput(e["input"], ts)
        created = True
    else:
        ts = existing
        created = False
    ts.SetInput("Speed", float(speed))
    ts.SetInput("Delay", float(delay))
    ts.SetInput("InterpolateBetweenFrames", 1 if interpolate else 0)
    mi = _tool(comp, media_in)
    safe(mi.SetInput, "HoldFirstFrame", int(hold_first))
    safe(mi.SetInput, "HoldLastFrame", int(hold_last))
    return {"comp": safe(lambda: comp.GetAttrs().get("COMPS_Name")) or "1", "tool": RETIME_TOOL, "created": created, "media_in": media_in}


@router.post("/{item_id}/retime")
def retime_item(item_id: str, body: RetimeItem, bridge: ResolveBridge = Depends(resolve_session)):
    """Change an item's playback speed - the Edit page's Change Clip Speed,
    which the scripting API lacks (it exposes RetimeProcess only). Composite:
    a TimeSpeed tool goes into the item's Fusion comp right after MediaIn.

    Live facts it is built on (Resolve Studio 21.0.4): the comp's MediaIn spans
    the WHOLE source clip (GlobalIn = -in_point, GlobalOut = clip_end), so the
    speed change can reach frames beyond the item's trim; and TimeSpeed maps
    input_time = P + (t - GlobalStart - Delay) * Speed with P = GlobalStart for
    forward speeds and P = GlobalEnd + 1 for reverse, so Delay is solved here
    to make comp frame 0 play the item's own in point (or, in reverse, its
    last frame).

    `fit` keeps the item where it is and as long as it is: 0.5 shows the first
    half of the trimmed range in slow motion, 2 needs twice the source after
    the in point (held on the last frame when the clip ends). `ripple`
    rebuilds the item at duration / |speed| (source window extended after the
    in point, or shifted earlier when the clip has no tail) and pushes or
    pulls every later item, like a ripple trim. Linked audio is not retimed."""
    if body.speed == 0:
        raise Rejected("speed must not be 0 (use a freeze frame via the comp instead)")
    tl = bridge.current_timeline()
    item = bridge.item(item_id, tl)
    snap = _snapshot(bridge, item, tl)
    if snap["mpi"] is None:
        raise Rejected("Only media-backed items can be retimed (generators/titles have no source)")
    duration = int(item.GetDuration())
    src_in, src_out = snap["source_start"], snap["source_end"]
    if duration <= 0 or src_in is None or src_out is None:
        raise Rejected("Could not read the item's duration / source range")
    ratio = max((src_out - src_in) / duration, 1e-6)  # source frames per timeline frame
    clip_frames = int(float(safe(snap["mpi"].GetClipProperty, "Frames") or 0) or 0)
    speed = float(body.speed)
    s_abs = abs(speed)
    moved = []
    new_item = item
    win_in_src = src_in  # source in-point of the (possibly rebuilt) item
    if body.mode == "ripple":
        new_len = max(1, int(round(duration / s_abs)))
        need_src = int(round(new_len * ratio))
        if clip_frames and src_in + need_src > clip_frames:
            win_in_src = max(0, clip_frames - need_src)  # no tail: slide the window earlier
            if win_in_src + need_src > clip_frames:
                raise Rejected(f"The clip has only {clip_frames} source frames; a {new_len}-frame item at speed {speed} needs {need_src}")
        delta = new_len - duration
        old_end_rel = snap["record_rel"] + duration
        if delta > 0:
            moved = _shift_after(bridge, tl, old_end_rel, delta, item_id)
        r = relocate_one(bridge, tl, item, snap["record_rel"], None, win_in_src, win_in_src + need_src)
        new_item = bridge.item(r["item"]["id"], tl)
        if delta < 0:
            moved = _shift_after(bridge, tl, old_end_rel, delta, r["item"]["id"])
        duration_after = new_len
    else:
        duration_after = duration
    # comp geometry in timeline frames (what the comp's time axis uses)
    gs = -win_in_src / ratio  # GlobalStart
    ge = ((clip_frames - win_in_src) / ratio - 1) if clip_frames else (duration_after - 1)  # GlobalEnd
    orig_offset = (src_in - win_in_src) / ratio  # where the original in point sits in the new comp
    if speed > 0:
        pivot, r0 = gs, orig_offset
        needed = orig_offset + duration_after * s_abs
        available = ge + 1
        hold_last = int(round(max(0.0, needed - available) * ratio)) if body.hold_edges else 0
        hold_first = 0
    else:
        pivot, r0 = ge + 1, orig_offset + duration - 1  # reverse: start on the original last frame
        needed_back = duration_after * s_abs - duration  # frames before the original in point
        hold_first = int(round(max(0.0, needed_back - orig_offset - (-gs)) * ratio)) if body.hold_edges else 0
        hold_last = 0
    delay = -gs - (r0 - pivot) / speed
    if body.hold_edges:
        # interpolation samples one frame past the range at the edges: the reverse item's last
        # frame rendered black (live) until MediaIn held its first frame
        if speed < 0:
            hold_first = max(hold_first, 1)
        else:
            hold_last = max(hold_last, 1)
    comp_info = _insert_timespeed(bridge, new_item, speed, delay, body.interpolate, hold_first, hold_last)
    return {
        "ok": True,
        "item": _summary(bridge, new_item, tl),
        "speed": speed,
        "mode": body.mode,
        "duration_before": duration,
        "duration_after": duration_after,
        "delay": round(delay, 3),
        "source_window": [win_in_src, win_in_src + int(round(duration_after * ratio))] if body.mode == "ripple" else [src_in, src_out],
        "holds": {"first": hold_first, "last": hold_last},
        "moved": moved,
        **comp_info,
    }


# -- cross dissolve (composite: the API has no transitions) ----------------------------

FADE_MERGE, FADE_BG = "DollyGripFade", "DollyGripFadeBG"


def _fade_comp(bridge: ResolveBridge, item, fade_in: int = 0, fade_out: int = 0) -> dict:
    """Ramp the item's opacity inside its Fusion comp: a transparent Background
    merged under whatever fed MediaOut, Blend keyed 0->1 over the first
    `fade_in` frames and 1->0 over the last `fade_out`."""
    from .fusion import _tool, _tools, animate_input
    from .fusion_more import graph_of

    if int(item.GetFusionCompCount() or 0) == 0:
        require(item.AddFusionComp(), "Resolve could not add a Fusion composition to the item")
    comp = bridge.fusion_comp(item, None)
    by_id = {}
    for t in _tools(comp):
        attrs = safe(t.GetAttrs, default={}) or {}
        by_id.setdefault(attrs.get("TOOLS_RegID"), []).append(attrs.get("TOOLS_Name"))
    media_out = (by_id.get("MediaOut") or [None])[0]
    if media_out is None:
        raise Rejected("The item's Fusion comp has no MediaOut tool")
    if safe(comp.FindTool, FADE_MERGE) is None:
        feeding = [e["from"] for e in graph_of(comp)["edges"] if e["to"] == media_out and e["input"] == "Input"]
        source = feeding[0] if feeding else (by_id.get("MediaIn") or [None])[0]
        if source is None:
            raise Rejected("Nothing feeds MediaOut in the item's comp")
        bg = comp.AddTool("Background", -32768, -32768)
        require(bg, "Fusion refused to add a Background")
        bg.SetAttrs({"TOOLS_Name": FADE_BG})
        bg = _tool(comp, FADE_BG)
        for k, v in (("UseFrameFormatSettings", 1), ("TopLeftRed", 0.0), ("TopLeftGreen", 0.0), ("TopLeftBlue", 0.0), ("TopLeftAlpha", 0.0)):
            safe(bg.SetInput, k, v)
        m = comp.AddTool("Merge", -32768, -32768)
        require(m, "Fusion refused to add a Merge")
        m.SetAttrs({"TOOLS_Name": FADE_MERGE})
        m = _tool(comp, FADE_MERGE)
        m.ConnectInput("Background", bg)
        m.ConnectInput("Foreground", _tool(comp, source))
        _tool(comp, media_out).ConnectInput("Input", m)
    m = _tool(comp, FADE_MERGE)
    total = int(item.GetDuration())
    keys = {}
    if fade_in > 0:
        keys.update({0: 0.0, min(fade_in, total) - 1: 1.0})
    if fade_out > 0:
        keys.update({max(total - fade_out, 0): 1.0, total - 1: 0.0})
    if keys:
        animate_input(comp, m, "Blend", keys, True)
    return {"tool": FADE_MERGE, "keys": {str(k): v for k, v in keys.items()}}


def _next_on_track(bridge: ResolveBridge, tl, item):
    tt, idx = safe(item.GetTrackTypeAndIndex, default=[None, None]) or [None, None]
    end = int(item.GetEnd())
    following = [it for it2, idx2, it in bridge.iter_items(tl, tt, idx) if int(it.GetStart()) >= end]
    following.sort(key=lambda it: int(it.GetStart()))
    return following[0] if following else None


def _free_track(bridge: ResolveBridge, tl, above: int, start_abs: int, end_abs: int, wanted: Optional[int]) -> int:
    """A video track (index) with nothing in [start_abs, end_abs); adds one when needed."""
    count = int(tl.GetTrackCount("video") or 0)
    candidates = [wanted] if wanted else list(range(above + 1, count + 1)) + [count + 1]
    for idx in candidates:
        if idx > count:
            require(tl.AddTrack("video"), "Resolve refused to add a video track")
            count += 1
        busy = any(int(it.GetStart()) < end_abs and int(it.GetEnd()) > start_abs for _, _, it in bridge.iter_items(tl, "video", idx))
        if not busy:
            return idx
    raise Rejected(f"Track V{wanted} is occupied in the dissolve range")


@router.post("/{item_id}/dissolve")
def dissolve_item(item_id: str, body: DissolveItem, bridge: ResolveBridge = Depends(resolve_session)):
    """Cross-dissolve from this item into the next one - the Edit page
    transition the API lacks. Composite on two tracks: with `before_cut` the
    incoming item is re-created one track up, starting `frames` early from
    its head handles, with a Fusion comp that ramps its opacity 0 -> 1 up to
    the cut; with `after_cut` a `frames`-long tail piece of the outgoing clip
    (its handles past the out point) is placed one track up over the incoming
    item and fades 1 -> 0. `center` does half of each; `auto` picks by the
    handles available. Grades and comps travel with the moved item (see
    relocate). Audio is untouched (no crossfade)."""
    tl = bridge.current_timeline()
    a = bridge.item(item_id, tl)
    b = bridge.item(body.to, tl) if body.to else _next_on_track(bridge, tl, a)
    if b is None:
        raise NotFound("No item follows this one on its track (pass `to`)")
    tt, idx = safe(a.GetTrackTypeAndIndex, default=[None, None]) or [None, None]
    if tt != "video":
        raise Rejected("Dissolves are for video items")
    if int(b.GetStart()) != int(a.GetEnd()):
        raise Rejected(f"The items are not adjacent (A ends at {int(a.GetEnd())}, B starts at {int(b.GetStart())})")
    snap_a, snap_b = _snapshot(bridge, a, tl), _snapshot(bridge, b, tl)
    if snap_a["mpi"] is None or snap_b["mpi"] is None:
        raise Rejected("Both items must be media-backed (generators/titles have no handles)")
    ratio_a = max((snap_a["source_end"] - snap_a["source_start"]) / max(int(a.GetDuration()), 1), 1e-6)
    ratio_b = max((snap_b["source_end"] - snap_b["source_start"]) / max(int(b.GetDuration()), 1), 1e-6)
    frames_a = int(float(safe(snap_a["mpi"].GetClipProperty, "Frames") or 0) or 0)
    head_b = int(snap_b["source_start"] / ratio_b)  # timeline frames of handle before B's in point
    tail_a = int((frames_a - snap_a["source_end"]) / ratio_a) if frames_a else 0
    n = body.frames
    align = body.align
    if align == "auto":
        if head_b >= n:
            align = "before_cut"
        elif tail_a >= n:
            align = "after_cut"
        elif head_b + tail_a >= n:
            align = "center"
        else:
            raise Rejected(f"Not enough handles for a {n}-frame dissolve: B has {head_b} before its in point, A has {tail_a} after its out point")
    need_b = {"before_cut": n, "after_cut": 0, "center": n // 2}[align]
    need_a = {"before_cut": 0, "after_cut": n, "center": n - n // 2}[align]
    if need_b > head_b or need_a > tail_a:
        raise Rejected(f"{align} needs {need_b} head frames on B (has {head_b}) and {need_a} tail frames on A (has {tail_a})")
    start_abs = int(tl.GetStartFrame())
    cut_abs = int(a.GetEnd())
    result = {"ok": True, "align": align, "frames": n, "cut_rel": cut_abs - start_abs, "pieces": []}
    if need_b:
        track = _free_track(bridge, tl, idx, cut_abs - need_b, int(b.GetEnd()), body.track_index)
        r = relocate_one(bridge, tl, b, snap_b["record_rel"] - need_b, track, int(round(snap_b["source_start"] - need_b * ratio_b)), snap_b["source_end"])
        b_new = bridge.item(r["item"]["id"], tl)
        fade = _fade_comp(bridge, b_new, fade_in=need_b)
        result["pieces"].append({"role": "incoming", "item": r["item"], "track_index": track, "fade_in": need_b, "grade_copied": r["grade_copied"], **fade})
        result["incoming"] = r["item"]["id"]
    if need_a:
        track = _free_track(bridge, tl, idx, cut_abs, cut_abs + need_a, body.track_index)
        info = {"mediaPoolItem": snap_a["mpi"], "trackIndex": track, "recordFrame": cut_abs, "startFrame": snap_a["source_end"], "endFrame": int(round(snap_a["source_end"] + need_a * ratio_a)), "mediaType": 1}
        created = bridge.media_pool().AppendToTimeline([info])
        piece = created[0] if created else None
        if not piece:
            raise Rejected("Resolve refused to append the outgoing clip's tail piece")
        if snap_a["properties"]:
            safe(piece.SetProperty, dict(snap_a["properties"]))
        grade = bool(safe(a.CopyGrades, [piece]))
        fade = _fade_comp(bridge, piece, fade_out=need_a)
        result["pieces"].append({"role": "outgoing_tail", "item": _summary(bridge, piece, tl), "track_index": track, "fade_out": need_a, "grade_copied": grade, **fade})
    return result


@router.get("/{item_id}/takes")
def list_takes(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    count = int(item.GetTakesCount() or 0)
    takes = []
    for i in range(1, count + 1):
        info = item.GetTakeByIndex(i) or {}
        mpi = info.get("mediaPoolItem")
        takes.append({"index": i, "start_frame": info.get("startFrame"), "end_frame": info.get("endFrame"), "clip": safe(mpi.GetName) if mpi else None})
    return {"count": count, "selected": int(item.GetSelectedTakeIndex() or 0), "takes": takes}


@router.post("/{item_id}/takes")
def add_take(item_id: str, body: AddTake, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    clip = bridge.clip(body.clip)
    args = [clip] + ([body.start_frame, body.end_frame] if body.start_frame is not None and body.end_frame is not None else [])
    require(item.AddTake(*args), "Resolve refused to add the take")
    return {"ok": True, "count": int(item.GetTakesCount())}


@router.post("/{item_id}/takes/{index}/select")
def select_take(item_id: str, index: int, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    require(item.SelectTakeByIndex(index), f"No take {index}")
    return {"ok": True, "selected": int(item.GetSelectedTakeIndex())}


@router.delete("/{item_id}/takes/{index}")
def delete_take(item_id: str, index: int, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    require(item.DeleteTakeByIndex(index), f"No take {index}")
    return {"ok": True, "count": int(item.GetTakesCount())}


@router.post("/{item_id}/takes/finalize")
def finalize_take(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.item(item_id).FinalizeTake())}


# -- analysis / AI ---------------------------------------------------------


@router.post("/{item_id}/stabilize")
def stabilize_item(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.item(item_id).Stabilize())}


@router.post("/{item_id}/smart-reframe")
def smart_reframe_item(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Studio: AI Smart Reframe (e.g. 16:9 -> 9:16 subject tracking)."""
    return {"ok": bool(bridge.item(item_id).SmartReframe())}


@router.post("/{item_id}/magic-mask")
def create_magic_mask(item_id: str, body: MagicMask, bridge: ResolveBridge = Depends(resolve_session)):
    """Studio: create a Magic Mask (F forward, B backward, BI both directions)."""
    return {"ok": bool(bridge.item(item_id).CreateMagicMask(body.mode))}


@router.post("/{item_id}/magic-mask/regenerate")
def regenerate_magic_mask(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.item(item_id).RegenerateMagicMask())}


@router.get("/{item_id}/voice-isolation")
def item_voice_isolation(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"state": bridge.item(item_id).GetVoiceIsolationState()}


@router.put("/{item_id}/voice-isolation")
def set_item_voice_isolation(item_id: str, body: VoiceIsolation, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    require(item.SetVoiceIsolationState({"isEnabled": body.enabled, "amount": body.amount}), "Resolve refused (Studio feature)")
    return {"state": item.GetVoiceIsolationState()}


@router.get("/{item_id}/cache")
def item_cache(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    return {"color_output": item.GetIsColorOutputCacheEnabled(), "fusion_output": item.GetIsFusionOutputCacheEnabled()}


@router.put("/{item_id}/cache")
def set_item_cache(item_id: str, body: CacheSettings, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    results = {}
    if body.color_output is not None:
        results["color_output"] = bool(item.SetColorOutputCache(body.color_output))
    if body.fusion_output is not None:
        results["fusion_output"] = bool(item.SetFusionOutputCache({"auto": -1, "off": 0, "on": 1}[body.fusion_output]))
    return {"results": results}


@router.post("/{item_id}/burn-in-preset")
def item_burn_in_preset(item_id: str, body: NamedPreset, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.item(item_id).LoadBurnInPreset(body.name), f"Burn-in preset {body.name!r} not found")
    return {"ok": True}


@router.post("/{item_id}/sidecar")
def update_sidecar(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Write the BRAW sidecar / R3D RMD for the clip."""
    return {"ok": bool(bridge.item(item_id).UpdateSidecar())}


def _item_resolver(bridge: ResolveBridge, item_id: str):
    return bridge.item(item_id)


mount_markers(router, "/{item_id}/markers", _item_resolver, scope="item")

__all__ = ["router", "NotFound"]
