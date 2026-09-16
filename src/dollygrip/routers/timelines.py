from __future__ import annotations

from fastapi import APIRouter, Depends

from ..bridge import NotFound, ResolveBridge
from ..deps import resolve_session
from ..schemas import AddTrack, AppendItems, CreateTimeline, SetCurrentTimeline

router = APIRouter(prefix="/timelines", tags=["timelines"])


@router.get("")
def list_timelines(bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    current = project.GetCurrentTimeline()
    current_name = current.GetName() if current else None
    out = []
    for i in range(1, int(project.GetTimelineCount()) + 1):
        tl = project.GetTimelineByIndex(i)
        if tl:
            out.append({"index": i, "name": tl.GetName(), "is_current": tl.GetName() == current_name})
    return {"timelines": out}


@router.get("/current")
def current_timeline(bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    return {
        "name": tl.GetName(),
        "start_frame": int(tl.GetStartFrame()),
        "end_frame": int(tl.GetEndFrame()),
        "frame_rate": tl.GetSetting("timelineFrameRate"),
        "video_tracks": int(tl.GetTrackCount("video")),
        "audio_tracks": int(tl.GetTrackCount("audio")),
    }


@router.post("/current")
def set_current_timeline(body: SetCurrentTimeline, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.timeline_by_name(body.name)
    ok = bridge.current_project().SetCurrentTimeline(tl)
    return {"ok": bool(ok), "name": body.name}


@router.post("")
def create_timeline(body: CreateTimeline, bridge: ResolveBridge = Depends(resolve_session)):
    """Create an empty timeline; per-timeline custom settings applied in the
    order Resolve requires (useCustomSettings first, then resolution/fps)."""
    mp = bridge.media_pool()
    tl = mp.CreateEmptyTimeline(body.name)
    if not tl:
        raise NotFound(f"Could not create timeline {body.name!r} (duplicate name?)")
    bridge.current_project().SetCurrentTimeline(tl)
    if body.width or body.height or body.fps:
        tl.SetSetting("useCustomSettings", "1")
        if body.width:
            tl.SetSetting("timelineResolutionWidth", str(body.width))
        if body.height:
            tl.SetSetting("timelineResolutionHeight", str(body.height))
        if body.fps:
            fps = body.fps
            tl.SetSetting("timelineFrameRate", str(int(fps) if float(fps).is_integer() else fps))
    for _ in range(body.extra_video_tracks):
        tl.AddTrack("video")
    for _ in range(body.extra_audio_tracks):
        tl.AddTrack("audio", "stereo")
    return {"ok": True, "name": tl.GetName(), "start_frame": int(tl.GetStartFrame())}


@router.post("/current/tracks")
def add_track(body: AddTrack, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    ok = tl.AddTrack(body.track_type, body.subtype) if body.subtype else tl.AddTrack(body.track_type)
    return {"ok": bool(ok), "video_tracks": int(tl.GetTrackCount("video")), "audio_tracks": int(tl.GetTrackCount("audio"))}


@router.post("/current/append")
def append_items(body: AppendItems, bridge: ResolveBridge = Depends(resolve_session)):
    """Append clips at exact timeline positions.

    Notes carried over from production use:
    - start/end frames are in SOURCE fps frames, not timeline fps;
    - record_frame here is 0-based from the timeline start (the gateway adds
      Resolve's internal start-frame offset);
    - overlapping items on ONE track get pushed by Resolve - put overlapping
      elements on separate tracks;
    - image sequences and stills are unreliable through this API - convert
      overlays to exact-length movs first (see docs/GOTCHAS.md).
    """
    mp = bridge.media_pool()
    tl = bridge.current_timeline()
    start = int(tl.GetStartFrame())
    results = []
    for item in body.items:
        clip = bridge.clip_by_name(item.clip_name)
        info = {"mediaPoolItem": clip, "trackIndex": item.track_index}
        if item.start_frame is not None:
            info["startFrame"] = item.start_frame
        if item.end_frame is not None:
            info["endFrame"] = item.end_frame
        if item.record_frame is not None:
            info["recordFrame"] = start + item.record_frame
        if item.media_type:
            info["mediaType"] = 1 if item.media_type == "video" else 2
        appended = mp.AppendToTimeline([info])
        results.append({"clip": item.clip_name, "ok": bool(appended and appended[0])})
    return {"results": results, "all_ok": all(r["ok"] for r in results)}
