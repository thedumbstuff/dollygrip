"""Timelines: create/list/switch, tracks, assembly, playhead, marks,
interchange import/export, generators & titles, compound/Fusion clips,
stills, auto-subtitles, scene detection, voice isolation."""

from __future__ import annotations

import base64
import struct
import zlib

from fastapi import APIRouter, Depends, Query, Response

from ..bridge import NotFound, ResolveBridge, require
from ..deps import resolve_session
from ..schemas import (
    AddTrack,
    AppendItems,
    AutoSubtitles,
    CompoundClip,
    CreateTimeline,
    DeleteItems,
    DolbyVision,
    DuplicateTimeline,
    ExportTimeline,
    GrabStills,
    ImportIntoTimeline,
    ImportTimelineFile,
    InsertGenerator,
    ItemIds,
    LinkItems,
    MarkInOut,
    PatchTimeline,
    PatchTrack,
    ProjectSettings,
    RippleInsert,
    SetCurrentTimeline,
    Timecode,
    TimelineFromClips,
    TrackType,
    VoiceIsolation,
)
from ..serialize import item_summary, safe, timeline_summary, track_summary
from .items import relocate_one
from .markers import mount_markers
from .tools import timecode_to_frames

router = APIRouter(prefix="/timelines", tags=["timelines"])


# -- listing / switching -----------------------------------------------------


@router.get("")
def list_timelines(bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    current = project.GetCurrentTimeline()
    current_name = current.GetName() if current else None
    out = []
    for i, tl in enumerate(bridge.timelines(), start=1):
        summary = timeline_summary(tl, current_name)
        summary["index"] = i
        out.append(summary)
    return {"timelines": out}


@router.get("/current")
def current_timeline(bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    out = timeline_summary(tl, tl.GetName())
    out["playhead"] = safe(tl.GetCurrentTimecode)
    out["mark_in_out"] = safe(tl.GetMarkInOut, default={})
    return out


@router.post("/current")
def set_current_timeline(body: SetCurrentTimeline, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.timeline_by_name(body.name)
    ok = bridge.current_project().SetCurrentTimeline(tl)
    return {"ok": bool(ok), "name": tl.GetName()}


@router.patch("/current")
def patch_timeline(body: PatchTimeline, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    results = {}
    if body.name is not None:
        results["name"] = bool(tl.SetName(body.name))
    if body.start_timecode is not None:
        results["start_timecode"] = bool(tl.SetStartTimecode(body.start_timecode))
    return {"results": results, "timeline": timeline_summary(tl, tl.GetName())}


@router.post("")
def create_timeline(body: CreateTimeline, bridge: ResolveBridge = Depends(resolve_session)):
    """Create an empty timeline; per-timeline custom settings applied in the
    order Resolve requires (useCustomSettings first, then resolution/fps)."""
    mp = bridge.media_pool()
    tl = mp.CreateEmptyTimeline(body.name)
    if not tl:
        raise NotFound(f"Could not create timeline {body.name!r} (duplicate name?)")
    bridge.current_project().SetCurrentTimeline(tl)
    _apply_custom_settings(tl, body.width, body.height, body.fps)
    if body.start_timecode:
        tl.SetStartTimecode(body.start_timecode)
    for _ in range(body.extra_video_tracks):
        tl.AddTrack("video")
    for _ in range(body.extra_audio_tracks):
        tl.AddTrack("audio", "stereo")
    return {"ok": True, "name": tl.GetName(), "start_frame": int(tl.GetStartFrame()), "id": safe(tl.GetUniqueId)}


def _apply_custom_settings(tl, width, height, fps):
    if width or height or fps:
        tl.SetSetting("useCustomSettings", "1")
        if width:
            tl.SetSetting("timelineResolutionWidth", str(width))
        if height:
            tl.SetSetting("timelineResolutionHeight", str(height))
        if fps:
            tl.SetSetting("timelineFrameRate", str(int(fps) if float(fps).is_integer() else fps))


@router.post("/from-clips")
def timeline_from_clips(body: TimelineFromClips, bridge: ResolveBridge = Depends(resolve_session)):
    """CreateTimelineFromClips: a new timeline pre-filled with clips in order.
    Same source-fps frame semantics as append; record_frame is honoured too."""
    mp = bridge.media_pool()
    infos = []
    for item in body.items:
        info = {"mediaPoolItem": bridge.clip(item.clip_name)}
        if item.start_frame is not None:
            info["startFrame"] = item.start_frame
        if item.end_frame is not None:
            info["endFrame"] = item.end_frame
        if item.record_frame is not None:
            info["recordFrame"] = item.record_frame
        infos.append(info)
    tl = mp.CreateTimelineFromClips(body.name, infos)
    if not tl:
        raise NotFound(f"Could not create timeline {body.name!r} from clips (duplicate name?)")
    bridge.current_project().SetCurrentTimeline(tl)
    return {"ok": True, "timeline": timeline_summary(tl, tl.GetName())}


@router.post("/import")
def import_timeline(body: ImportTimelineFile, bridge: ResolveBridge = Depends(resolve_session)):
    """ImportTimelineFromFile: AAF / EDL / XML / FCPXML / DRT / ADL / OTIO."""
    options = {"importSourceClips": body.import_source_clips}
    if body.timeline_name:
        options["timelineName"] = body.timeline_name
    if body.source_clips_path:
        options["sourceClipsPath"] = body.source_clips_path
    if body.source_clips_bins:
        options["sourceClipsFolders"] = [bridge.folder_by_path(p) for p in body.source_clips_bins]
    if body.interlace_processing is not None:
        options["interlaceProcessing"] = body.interlace_processing
    tl = bridge.media_pool().ImportTimelineFromFile(body.path, options)
    if not tl:
        raise NotFound(f"Resolve could not import a timeline from {body.path!r}")
    bridge.current_project().SetCurrentTimeline(tl)
    return {"ok": True, "timeline": timeline_summary(tl, tl.GetName())}


@router.post("/current/duplicate")
def duplicate_timeline(body: DuplicateTimeline, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    dup = tl.DuplicateTimeline(body.name) if body.name else tl.DuplicateTimeline()
    if not dup:
        raise NotFound(f"Could not duplicate {tl.GetName()!r} (name {body.name!r} taken?)")
    return {"ok": True, "timeline": timeline_summary(dup)}


@router.delete("/{name}")
def delete_timeline(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Delete a timeline by name (or unique id). Refuses 'current' - name it."""
    if name == "current":
        raise NotFound("Name the timeline explicitly to delete it")
    tl = bridge.timeline_by_name(name)
    return {"ok": bool(bridge.media_pool().DeleteTimelines([tl]))}


@router.get("/current/settings")
def timeline_settings(bridge: ResolveBridge = Depends(resolve_session)):
    return {"settings": bridge.current_timeline().GetSetting() or {}}


@router.patch("/current/settings")
def patch_timeline_settings(body: ProjectSettings, bridge: ResolveBridge = Depends(resolve_session)):
    """Set timeline settings. Custom values only stick after useCustomSettings=1,
    which the gateway sets for you when you pass anything else."""
    tl = bridge.current_timeline()
    if any(k != "useCustomSettings" for k in body.settings):
        tl.SetSetting("useCustomSettings", body.settings.get("useCustomSettings", "1"))
    return {"results": {k: bool(tl.SetSetting(k, v)) for k, v in body.settings.items()}}


# -- tracks ------------------------------------------------------------------


@router.get("/current/tracks")
def list_tracks(bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    tracks = []
    for tt in ("video", "audio", "subtitle"):
        for idx in range(1, int(tl.GetTrackCount(tt) or 0) + 1):
            tracks.append(track_summary(tl, tt, idx))
    return {"tracks": tracks}


@router.post("/current/tracks")
def add_track(body: AddTrack, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    if body.index is not None:
        options = {"index": body.index}
        if body.subtype:
            options["audioType"] = body.subtype
        ok = tl.AddTrack(body.track_type, options)
    elif body.subtype:
        ok = tl.AddTrack(body.track_type, body.subtype)
    else:
        ok = tl.AddTrack(body.track_type)
    require(ok, f"Resolve refused to add a {body.track_type} track")
    return {
        "ok": True,
        "video_tracks": int(tl.GetTrackCount("video")),
        "audio_tracks": int(tl.GetTrackCount("audio")),
        "subtitle_tracks": int(tl.GetTrackCount("subtitle")),
    }


@router.patch("/current/tracks/{track_type}/{index}")
def patch_track(track_type: TrackType, index: int, body: PatchTrack, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    if not 1 <= index <= int(tl.GetTrackCount(track_type) or 0):
        raise NotFound(f"No {track_type} track {index}")
    results = {}
    if body.name is not None:
        results["name"] = bool(tl.SetTrackName(track_type, index, body.name))
    if body.enabled is not None:
        results["enabled"] = bool(tl.SetTrackEnable(track_type, index, body.enabled))
    if body.locked is not None:
        results["locked"] = bool(tl.SetTrackLock(track_type, index, body.locked))
    return {"results": results, "track": track_summary(tl, track_type, index)}


@router.delete("/current/tracks/{track_type}/{index}")
def delete_track(track_type: TrackType, index: int, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    require(tl.DeleteTrack(track_type, index), f"Could not delete {track_type} track {index}")
    return {"ok": True, "remaining": int(tl.GetTrackCount(track_type))}


# -- assembly ----------------------------------------------------------------


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
        clip = bridge.clip(item.clip_name)
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
        created = appended[0] if appended else None
        results.append(
            {
                "clip": item.clip_name,
                "ok": bool(created),
                "item_id": safe(created.GetUniqueId) if created else None,
            }
        )
    return {"results": results, "all_ok": all(r["ok"] for r in results)}


def playhead_rel(tl) -> int:
    """Playhead position as a 0-based frame from the timeline start."""
    tc = tl.GetCurrentTimecode() or tl.GetStartTimecode()
    fps_setting = str(tl.GetSetting("timelineFrameRate") or "30")
    drop = ";" in tc or "DF" in fps_setting.upper()
    fps = float(fps_setting.upper().replace("DF", "").strip() or 30)
    return timecode_to_frames(tc, fps, drop) - int(tl.GetStartFrame())


@router.post("/current/ripple-insert")
def ripple_insert(body: RippleInsert, bridge: ResolveBridge = Depends(resolve_session)):
    """Insert a clip at a frame (default: the playhead) and push everything at
    or after that frame later by the clip's length - the Edit page's ripple
    insert, which the API lacks. Items are moved right-to-left via the same
    machinery as `relocate` (properties/markers/Fusion comps kept; grades kept
    only for items whose new position does not overlap their old one)."""
    mp = bridge.media_pool()
    tl = bridge.current_timeline()
    start_abs = int(tl.GetStartFrame())
    at = playhead_rel(tl) if body.record_frame is None else body.record_frame
    clip = bridge.clip(body.clip_name)
    if body.start_frame is not None and body.end_frame is not None:
        length = body.end_frame - body.start_frame
    else:
        frames = float(clip.GetClipProperty("Frames") or 0)
        clip_fps = float(clip.GetClipProperty("FPS") or 0) or None
        tl_fps = float(str(tl.GetSetting("timelineFrameRate") or "30").upper().replace("DF", "").strip() or 30)
        length = int(round(frames * (tl_fps / clip_fps))) if clip_fps else int(frames)
    if length <= 0:
        raise Rejected("Could not determine the clip length - pass start_frame/end_frame")

    track_type = "audio" if body.media_type == "audio" else "video"
    affected = []
    for tt, idx, item in bridge.iter_items(tl):
        if tt == "subtitle":
            continue
        if not body.all_tracks and (tt != track_type or idx != body.track_index):
            continue
        rel = int(item.GetStart()) - start_abs
        if rel >= at:
            affected.append((rel, item))
    moved = []
    for rel, item in sorted(affected, key=lambda x: -x[0]):
        r = relocate_one(bridge, tl, item, rel + length)
        moved.append({"id": r["item"]["id"], "start_rel": r["item"]["start_rel"], "grade_copied": r["grade_copied"]})

    info = {"mediaPoolItem": clip, "trackIndex": body.track_index, "recordFrame": start_abs + at}
    if body.start_frame is not None:
        info["startFrame"] = body.start_frame
    if body.end_frame is not None:
        info["endFrame"] = body.end_frame
    if body.media_type:
        info["mediaType"] = 1 if body.media_type == "video" else 2
    appended = mp.AppendToTimeline([info])
    new = appended[0] if appended else None
    if not new:
        raise Rejected("Items were shifted but Resolve refused to append the clip at the insertion point")
    tt, idx = safe(new.GetTrackTypeAndIndex, default=[track_type, body.track_index]) or [track_type, body.track_index]
    return {"ok": True, "inserted": item_summary(tt, idx, new, start_abs), "shift": length, "moved": moved}


@router.post("/current/delete-items")
def delete_items(body: DeleteItems, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    items = bridge.items(body.item_ids, tl)
    return {"ok": bool(tl.DeleteClips(items, body.ripple)), "deleted": len(items)}


@router.post("/current/link")
def link_items(body: LinkItems, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    return {"ok": bool(tl.SetClipsLinked(bridge.items(body.item_ids, tl), body.linked))}


@router.post("/current/compound")
def create_compound_clip(body: CompoundClip, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    info = {}
    if body.name:
        info["name"] = body.name
    if body.start_timecode:
        info["startTimecode"] = body.start_timecode
    item = tl.CreateCompoundClip(bridge.items(body.item_ids, tl), info)
    if not item:
        raise NotFound("Resolve could not create the compound clip")
    return {"ok": True, "item": item_summary(*(safe(item.GetTrackTypeAndIndex, default=[None, None]) or [None, None]), item, int(tl.GetStartFrame()))}


@router.post("/current/fusion-clip")
def create_fusion_clip(body: ItemIds, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    item = tl.CreateFusionClip(bridge.items(body.item_ids, tl))
    if not item:
        raise NotFound("Resolve could not create the Fusion clip")
    return {"ok": True, "item_id": safe(item.GetUniqueId), "name": safe(item.GetName)}


@router.post("/current/generators")
def insert_generator(body: InsertGenerator, bridge: ResolveBridge = Depends(resolve_session)):
    """Insert a generator / title / Fusion title / OFX generator / empty Fusion
    composition at the playhead on the current track. For `fusion_title`
    with `text`, the Text+ contents are set immediately (data-driven titles)."""
    tl = bridge.current_timeline()
    kind = body.kind
    if kind == "fusion_composition":
        item = tl.InsertFusionCompositionIntoTimeline()
    else:
        if not body.name:
            raise NotFound(f"`name` is required for kind {kind!r}")
        fn = {
            "generator": tl.InsertGeneratorIntoTimeline,
            "fusion_generator": tl.InsertFusionGeneratorIntoTimeline,
            "ofx_generator": tl.InsertOFXGeneratorIntoTimeline,
            "title": tl.InsertTitleIntoTimeline,
            "fusion_title": tl.InsertFusionTitleIntoTimeline,
        }[kind]
        item = fn(body.name)
    if not item:
        raise NotFound(f"Resolve could not insert {kind} {body.name!r} (exact name as in the Effects Library?)")
    out = {"ok": True, "item_id": safe(item.GetUniqueId), "name": safe(item.GetName)}
    if body.text is not None and kind in ("fusion_title", "fusion_generator"):
        from .fusion import set_text_plus

        out["text"] = set_text_plus(bridge, item, body.text)
    return out


# -- playhead / marks ---------------------------------------------------------


@router.get("/current/playhead")
def get_playhead(bridge: ResolveBridge = Depends(resolve_session)):
    return {"timecode": bridge.current_timeline().GetCurrentTimecode()}


@router.put("/current/playhead")
def set_playhead(body: Timecode, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    require(tl.SetCurrentTimecode(body.timecode), f"Resolve refused timecode {body.timecode!r} (format HH:MM:SS:FF, on Cut/Edit/Color/Fairlight/Deliver page)")
    return {"timecode": tl.GetCurrentTimecode()}


@router.get("/current/mark-in-out")
def get_mark_in_out(bridge: ResolveBridge = Depends(resolve_session)):
    return {"marks": bridge.current_timeline().GetMarkInOut() or {}}


@router.put("/current/mark-in-out")
def set_mark_in_out(body: MarkInOut, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    require(tl.SetMarkInOut(body.in_frame, body.out_frame, body.type), "Resolve refused the in/out range")
    return {"marks": tl.GetMarkInOut() or {}}


@router.delete("/current/mark-in-out")
def clear_mark_in_out(type: str = Query(default="all"), bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    tl.ClearMarkInOut(type)
    return {"marks": tl.GetMarkInOut() or {}}


# -- interchange -------------------------------------------------------------


@router.post("/current/export")
def export_timeline(body: ExportTimeline, bridge: ResolveBridge = Depends(resolve_session)):
    """Timeline.Export - AAF, EDL, FCP XML, FCPXML, DRT, OTIO, ALE, CSV, HDR10 / Dolby Vision metadata."""
    tl = bridge.current_timeline()
    export_type = bridge.const("EXPORT_" + body.type.upper())
    if body.type in ("aaf", "edl") and body.subtype is None:
        raise NotFound(f"`subtype` is required for {body.type} exports")
    subtype = bridge.const("EXPORT_" + body.subtype.upper()) if body.subtype else bridge.const("EXPORT_NONE")
    require(tl.Export(body.path, export_type, subtype), f"Resolve refused to export to {body.path!r}")
    return {"ok": True, "path": body.path}


@router.post("/current/import-aaf")
def import_into_timeline(body: ImportIntoTimeline, bridge: ResolveBridge = Depends(resolve_session)):
    """Timeline.ImportIntoTimeline - merge an AAF into the current timeline."""
    tl = bridge.current_timeline()
    require(tl.ImportIntoTimeline(body.path, dict(body.options)), f"Resolve refused to import {body.path!r}")
    return {"ok": True}


# -- stills / thumbnails ----------------------------------------------------


@router.post("/current/stills")
def grab_stills(body: GrabStills, bridge: ResolveBridge = Depends(resolve_session)):
    """Grab gallery stills (current clip, or every clip at first/middle frame)."""
    tl = bridge.current_timeline()
    if body.all_clips:
        stills = tl.GrabAllStills(1 if body.frame_source == "first" else 2) or []
        return {"ok": bool(stills), "count": len(stills)}
    still = tl.GrabStill()
    return {"ok": bool(still), "count": 1 if still else 0}


@router.get("/current/thumbnail")
def current_thumbnail(bridge: ResolveBridge = Depends(resolve_session)):
    """Raw thumbnail of the current clip (Color page): width/height/format + base64 RGB data."""
    data = bridge.current_timeline().GetCurrentClipThumbnailImage()
    if not data:
        raise NotFound("No current clip thumbnail (open the Color page with a clip selected)")
    return data


@router.get("/current/thumbnail.png")
def current_thumbnail_png(bridge: ResolveBridge = Depends(resolve_session)):
    """The same thumbnail, encoded as PNG for anything that can show an image."""
    data = bridge.current_timeline().GetCurrentClipThumbnailImage()
    if not data:
        raise NotFound("No current clip thumbnail (open the Color page with a clip selected)")
    png = _rgb_to_png(base64.b64decode(data["data"]), int(data["width"]), int(data["height"]))
    return Response(content=png, media_type="image/png")


def _rgb_to_png(rgb: bytes, width: int, height: int) -> bytes:
    """Minimal PNG encoder (RGB8, no deps) for the thumbnail endpoint."""
    raw = b"".join(b"\x00" + rgb[y * width * 3 : (y + 1) * width * 3] for y in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


# -- AI / analysis -------------------------------------------------------------


@router.post("/current/subtitles/auto")
def auto_subtitles(body: AutoSubtitles, bridge: ResolveBridge = Depends(resolve_session)):
    """Studio: CreateSubtitlesFromAudio (speech-to-text captions on a new subtitle track)."""
    tl = bridge.current_timeline()
    settings = {}
    if body.language:
        settings[bridge.const("SUBTITLE_LANGUAGE")] = bridge.const("AUTO_CAPTION_" + body.language.upper())
    if body.preset:
        settings[bridge.const("SUBTITLE_CAPTION_PRESET")] = bridge.const("AUTO_CAPTION_" + body.preset)
    if body.chars_per_line is not None:
        settings[bridge.const("SUBTITLE_CHARS_PER_LINE")] = body.chars_per_line
    if body.line_break:
        settings[bridge.const("SUBTITLE_LINE_BREAK")] = bridge.const("AUTO_CAPTION_LINE_" + body.line_break)
    if body.gap is not None:
        settings[bridge.const("SUBTITLE_GAP")] = body.gap
    require(tl.CreateSubtitlesFromAudio(settings) if settings else tl.CreateSubtitlesFromAudio(), "Resolve refused (Studio + speech model required)")
    return {"ok": True, "subtitle_tracks": int(tl.GetTrackCount("subtitle"))}


@router.post("/current/scene-cuts")
def detect_scene_cuts(bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.current_timeline().DetectSceneCuts())}


@router.post("/current/stereo")
def convert_to_stereo(bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.current_timeline().ConvertTimelineToStereo())}


@router.post("/current/dolby-vision")
def analyze_dolby_vision(body: DolbyVision, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    items = bridge.items(body.item_ids, tl) if body.item_ids else []
    if body.blend_shots:
        ok = tl.AnalyzeDolbyVision(items, bridge.const("DLB_BLEND_SHOTS"))
    else:
        ok = tl.AnalyzeDolbyVision(items)
    return {"ok": bool(ok)}


@router.get("/current/voice-isolation/{track_index}")
def track_voice_isolation(track_index: int, bridge: ResolveBridge = Depends(resolve_session)):
    return {"track_index": track_index, "state": bridge.current_timeline().GetVoiceIsolationState(track_index)}


@router.put("/current/voice-isolation/{track_index}")
def set_track_voice_isolation(track_index: int, body: VoiceIsolation, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    require(
        tl.SetVoiceIsolationState(track_index, {"isEnabled": body.enabled, "amount": body.amount}),
        f"Resolve refused voice isolation on audio track {track_index} (Studio feature; track exists?)",
    )
    return {"track_index": track_index, "state": tl.GetVoiceIsolationState(track_index)}


mount_markers(router, "/current/markers", lambda bridge: bridge.current_timeline(), scope="timeline")
