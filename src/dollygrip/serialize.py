"""Turn Resolve objects into JSON-friendly dicts.

Resolve hands back live proxies (TimelineItem, MediaPoolItem, ...) that an
HTTP client cannot hold, so every summary carries the stable identifier the
client uses to address the object again (`id` = GetUniqueId()).

Every getter is wrapped: the fields the running Resolve build lacks come back
as null instead of taking the whole response down.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def safe(fn: Callable, *args, default=None):
    try:
        return fn(*args)
    except Exception:
        return default


def jsonable(value: Any) -> Any:
    """Best-effort conversion of Resolve return values to JSON types."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return repr(value)


def item_summary(track_type: str, track_index: int, item, start_offset: int = 0) -> Dict:
    """Timeline item as the client sees it. `start`/`end` are absolute
    timeline frames as Resolve reports them; `start_rel`/`end_rel` subtract
    the timeline start (the 0-based frames the append endpoint speaks)."""
    start = safe(item.GetStart)
    end = safe(item.GetEnd)
    mpi = safe(item.GetMediaPoolItem)
    return {
        "id": safe(item.GetUniqueId),
        "name": safe(item.GetName),
        "track_type": track_type,
        "track_index": track_index,
        "start": start,
        "end": end,
        "start_rel": None if start is None else int(start) - start_offset,
        "end_rel": None if end is None else int(end) - start_offset,
        "duration": safe(item.GetDuration),
        "source_start": safe(item.GetSourceStartFrame),
        "source_end": safe(item.GetSourceEndFrame),
        "left_offset": safe(item.GetLeftOffset),
        "right_offset": safe(item.GetRightOffset),
        "enabled": safe(item.GetClipEnabled),
        "color": safe(item.GetClipColor),
        "flags": safe(item.GetFlagList, default=[]),
        "fusion_comps": safe(item.GetFusionCompCount, default=0),
        "media_pool_clip": safe(mpi.GetName) if mpi else None,
        "media_pool_clip_id": safe(mpi.GetUniqueId) if mpi else None,
    }


def clip_summary(clip, folder_name: Optional[str] = None) -> Dict:
    props = safe(clip.GetClipProperty, default={}) or {}
    out = {
        "id": safe(clip.GetUniqueId),
        "media_id": safe(clip.GetMediaId),
        "name": safe(clip.GetName),
        "duration": props.get("Duration"),
        "frames": props.get("Frames"),
        "fps": props.get("FPS"),
        "resolution": props.get("Resolution"),
        "type": props.get("Type"),
        "file_path": props.get("File Path"),
        "color": safe(clip.GetClipColor),
        "flags": safe(clip.GetFlagList, default=[]),
        "is_timeline": bool(safe(clip.GetTimeline)) if props.get("Type") == "Timeline" else False,
    }
    if folder_name is not None:
        out["bin"] = folder_name
    return out


def marker_list(obj) -> List[Dict]:
    """GetMarkers() returns {frame: {...}} - flatten into a sorted list."""
    markers = safe(obj.GetMarkers, default={}) or {}
    out = []
    for frame, info in markers.items():
        info = info or {}
        out.append(
            {
                "frame": int(float(frame)),
                "color": info.get("color"),
                "name": info.get("name"),
                "note": info.get("note"),
                "duration": info.get("duration"),
                "custom_data": info.get("customData"),
            }
        )
    return sorted(out, key=lambda m: m["frame"])


def timeline_summary(tl, current_name: Optional[str] = None) -> Dict:
    name = safe(tl.GetName)
    return {
        "id": safe(tl.GetUniqueId),
        "name": name,
        "is_current": name == current_name if current_name is not None else None,
        "start_frame": safe(tl.GetStartFrame),
        "end_frame": safe(tl.GetEndFrame),
        "start_timecode": safe(tl.GetStartTimecode),
        "frame_rate": safe(tl.GetSetting, "timelineFrameRate"),
        "width": safe(tl.GetSetting, "timelineResolutionWidth"),
        "height": safe(tl.GetSetting, "timelineResolutionHeight"),
        "video_tracks": safe(tl.GetTrackCount, "video"),
        "audio_tracks": safe(tl.GetTrackCount, "audio"),
        "subtitle_tracks": safe(tl.GetTrackCount, "subtitle"),
    }


def track_summary(tl, track_type: str, index: int) -> Dict:
    return {
        "type": track_type,
        "index": index,
        "name": safe(tl.GetTrackName, track_type, index),
        "enabled": safe(tl.GetIsTrackEnabled, track_type, index),
        "locked": safe(tl.GetIsTrackLocked, track_type, index),
        "subtype": safe(tl.GetTrackSubType, track_type, index) if track_type == "audio" else None,
        "item_count": len(safe(tl.GetItemListInTrack, track_type, index, default=[]) or []),
    }


def tool_summary(tool) -> Dict:
    attrs = safe(tool.GetAttrs, default={}) or {}
    return {
        "name": attrs.get("TOOLS_Name") or safe(lambda: tool.Name),
        "id": attrs.get("TOOLS_RegID") or safe(lambda: tool.ID),
        "pass_through": attrs.get("TOOLB_PassThrough"),
        "selected": attrs.get("TOOLB_Selected"),
    }
