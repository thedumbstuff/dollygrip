"""Timeline items (clips on tracks) - addressed by the unique id returned
from GET /timelines/current/items. 'current' addresses the video item under
the playhead."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..bridge import NotFound, Rejected, ResolveBridge, require
from ..deps import resolve_session
from ..schemas import AddTake, CacheSettings, Flag, ItemProperties, MagicMask, NamedPreset, PatchItem, RelocateItem, SplitItem, TrackType, VoiceIsolation
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


@router.post("/{item_id}/relocate")
def relocate_item(item_id: str, body: RelocateItem, bridge: ResolveBridge = Depends(resolve_session)):
    """Move and/or trim an item. Resolve's API cannot edit an item in place, so
    this re-appends the same source range at the new position, copies the
    grade (CopyGrades) and Fusion comps (export/import) onto the new item,
    restores Inspector properties/name/color/markers, then deletes the old
    one. Caveats: same-track moves that overlap the old position are done
    delete-first (grade is lost - Resolve has no grade read-back); linked
    audio is not moved with a video item (relocate it separately)."""
    import os
    import tempfile

    tl = bridge.current_timeline()
    old = bridge.item(item_id, tl)
    snap = _snapshot(bridge, old, tl)
    record_rel = snap["record_rel"] if body.record_frame is None else body.record_frame
    track_index = snap["track_index"] if body.track_index is None else body.track_index
    source_start = snap["source_start"] if body.start_frame is None else body.start_frame
    source_end = snap["source_end"] if body.end_frame is None else body.end_frame
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
        require(tl.DeleteClips([old], body.ripple), "Resolve refused to delete the original item")
        new = _reappend(bridge, tl, snap, record_rel, track_index, source_start, source_end)
    else:
        new = _reappend(bridge, tl, snap, record_rel, track_index, source_start, source_end)
        grade_copied = bool(safe(old.CopyGrades, [new]))
        require(tl.DeleteClips([old], body.ripple), "Re-appended, but Resolve refused to delete the original item")

    comps_restored = 0
    for name, path in comp_files:
        comp = safe(new.ImportFusionComp, path)
        if comp:
            comps_restored += 1
            imported_name = safe(lambda: comp.GetAttrs().get("COMPS_Name")) or safe(lambda: comp.name)
            if imported_name and imported_name != name:
                safe(new.RenameFusionCompByName, imported_name, name)
    return {
        "ok": True,
        "item": _summary(bridge, new, tl),
        "grade_copied": grade_copied,
        "fusion_comps_restored": comps_restored,
        "note": None if not overlaps else "same-track overlap: deleted first, grade not preserved",
    }


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
