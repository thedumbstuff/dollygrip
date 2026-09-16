"""Media pool: bins, clips, import (files, image sequences, subclips),
metadata/properties, proxies, relinking, mattes, audio sync, and the Studio
AI analyses that live on clips and bins."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..bridge import NotFound, ResolveBridge, require
from ..deps import resolve_session
from ..schemas import (
    ClipMattes,
    ClipRefs,
    Deblur,
    ExportBin,
    ExportMetadata,
    Flag,
    FolderPaths,
    ImportBin,
    ImportMedia,
    Intellisearch,
    MarkInOut,
    MoveClips,
    MoveFolders,
    PatchClip,
    ProxyPath,
    RelinkClips,
    ReplaceClip,
    SetFolder,
    SlateAnalysis,
    StereoClip,
    Subclips,
    SyncAudio,
    Transcribe,
)
from ..serialize import clip_summary, jsonable, safe
from .markers import mount_markers

router = APIRouter(prefix="/mediapool", tags=["mediapool"])

_MAX_DEPTH = 8


def _tree(folder, depth: int = 0):
    node = {"name": folder.GetName(), "id": safe(folder.GetUniqueId), "clip_count": len(folder.GetClipList() or [])}
    if depth < _MAX_DEPTH:
        node["folders"] = [_tree(f, depth + 1) for f in folder.GetSubFolderList() or []]
    return node


# -- bins ------------------------------------------------------------------


@router.get("/folders")
def folder_tree(bridge: ResolveBridge = Depends(resolve_session)):
    mp = bridge.media_pool()
    return {"root": _tree(mp.GetRootFolder()), "current": mp.GetCurrentFolder().GetName()}


@router.post("/folders")
def set_current_folder(body: SetFolder, bridge: ResolveBridge = Depends(resolve_session)):
    """Walk (and optionally create) a bin path from the root, set it current."""
    folder = bridge.folder_by_path(body.path, create=body.create)
    bridge.media_pool().SetCurrentFolder(folder)
    return {"ok": True, "current": folder.GetName(), "id": safe(folder.GetUniqueId)}


@router.post("/folders/delete")
def delete_folders(body: FolderPaths, bridge: ResolveBridge = Depends(resolve_session)):
    folders = [bridge.folder_by_path(p) for p in body.paths]
    return {"ok": bool(bridge.media_pool().DeleteFolders(folders)), "deleted": len(folders)}


@router.post("/folders/move")
def move_folders(body: MoveFolders, bridge: ResolveBridge = Depends(resolve_session)):
    folders = [bridge.folder_by_path(p) for p in body.paths]
    target = bridge.folder_by_path(body.target, create=True)
    return {"ok": bool(bridge.media_pool().MoveFolders(folders, target))}


@router.post("/folders/refresh")
def refresh_folders(bridge: ResolveBridge = Depends(resolve_session)):
    """Collaboration mode: pull other users' bin changes."""
    return {"ok": bool(bridge.media_pool().RefreshFolders())}


@router.post("/folders/export")
def export_bin(body: ExportBin, bridge: ResolveBridge = Depends(resolve_session)):
    """Export a bin as a .drb file."""
    folder = bridge.folder_by_path(body.path) if body.path else bridge.media_pool().GetCurrentFolder()
    require(folder.Export(body.file), f"Resolve refused to export bin {folder.GetName()!r}")
    return {"ok": True, "file": body.file}


@router.post("/folders/import")
def import_bin(body: ImportBin, bridge: ResolveBridge = Depends(resolve_session)):
    """Import a .drb bin into the current bin."""
    require(bridge.media_pool().ImportFolderFromFile(body.file, body.source_clips_path), f"Resolve refused to import {body.file!r}")
    return {"ok": True}


# -- clips ------------------------------------------------------------------


@router.get("/clips")
def list_clips(
    bridge: ResolveBridge = Depends(resolve_session),
    bin: Optional[str] = Query(default=None, description="Bin path; default = current bin"),
    recursive: bool = Query(default=False, description="Include sub-bins"),
):
    folder = bridge.folder_by_path(bin) if bin else bridge.media_pool().GetCurrentFolder()
    folders = list(bridge.walk_folders(folder)) if recursive else [folder]
    clips = [clip_summary(c, f.GetName()) for f in folders for c in f.GetClipList() or []]
    return {"bin": folder.GetName(), "clips": clips}


@router.get("/clips/{ref}")
def get_clip(ref: str, bridge: ResolveBridge = Depends(resolve_session)):
    clip = bridge.clip(ref)
    out = clip_summary(clip)
    out["properties"] = jsonable(clip.GetClipProperty() or {})
    out["metadata"] = jsonable(clip.GetMetadata() or {})
    out["mark_in_out"] = safe(clip.GetMarkInOut, default={})
    return out


@router.patch("/clips/{ref}")
def patch_clip(ref: str, body: PatchClip, bridge: ResolveBridge = Depends(resolve_session)):
    clip = bridge.clip(ref)
    results = {}
    if body.name is not None:
        results["name"] = bool(clip.SetName(body.name))
    if body.color is not None:
        results["color"] = bool(clip.ClearClipColor() if body.color == "" else clip.SetClipColor(body.color))
    if body.properties:
        results["properties"] = {k: bool(clip.SetClipProperty(k, v)) for k, v in body.properties.items()}
    if body.metadata:
        results["metadata"] = bool(clip.SetMetadata(dict(body.metadata)))
    if body.third_party_metadata:
        results["third_party_metadata"] = bool(clip.SetThirdPartyMetadata(dict(body.third_party_metadata)))
    return {"results": results, "clip": clip_summary(clip)}


@router.post("/clips/delete")
def delete_clips(body: ClipRefs, bridge: ResolveBridge = Depends(resolve_session)):
    clips = bridge.clips(body.clips)
    return {"ok": bool(bridge.media_pool().DeleteClips(clips)), "deleted": len(clips)}


@router.post("/clips/move")
def move_clips(body: MoveClips, bridge: ResolveBridge = Depends(resolve_session)):
    clips = bridge.clips(body.clips)
    target = bridge.folder_by_path(body.target, create=True)
    return {"ok": bool(bridge.media_pool().MoveClips(clips, target)), "moved": len(clips), "target": target.GetName()}


@router.post("/clips/relink")
def relink_clips(body: RelinkClips, bridge: ResolveBridge = Depends(resolve_session)):
    clips = bridge.clips(body.clips)
    require(bridge.media_pool().RelinkClips(clips, body.folder_path), "Resolve could not relink the clips to that folder")
    return {"ok": True, "relinked": len(clips)}


@router.post("/clips/unlink")
def unlink_clips(body: ClipRefs, bridge: ResolveBridge = Depends(resolve_session)):
    clips = bridge.clips(body.clips)
    return {"ok": bool(bridge.media_pool().UnlinkClips(clips)), "unlinked": len(clips)}


@router.get("/clips/{ref}/metadata")
def clip_metadata(ref: str, bridge: ResolveBridge = Depends(resolve_session)):
    clip = bridge.clip(ref)
    return {"metadata": jsonable(clip.GetMetadata() or {}), "third_party_metadata": jsonable(safe(clip.GetThirdPartyMetadata, default={}) or {})}


@router.get("/clips/{ref}/properties")
def clip_properties(ref: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"properties": jsonable(bridge.clip(ref).GetClipProperty() or {})}


@router.get("/clips/{ref}/audio-mapping")
def clip_audio_mapping(ref: str, bridge: ResolveBridge = Depends(resolve_session)):
    raw = bridge.clip(ref).GetAudioMapping()
    try:
        return {"mapping": json.loads(raw) if isinstance(raw, str) else raw}
    except ValueError:
        return {"mapping_raw": raw}


@router.post("/clips/{ref}/flags")
def add_clip_flag(ref: str, body: Flag, bridge: ResolveBridge = Depends(resolve_session)):
    clip = bridge.clip(ref)
    require(clip.AddFlag(body.color), f"Resolve refused flag color {body.color!r}")
    return {"flags": clip.GetFlagList()}


@router.delete("/clips/{ref}/flags")
def clear_clip_flags(ref: str, color: str = Query(default="All"), bridge: ResolveBridge = Depends(resolve_session)):
    clip = bridge.clip(ref)
    clip.ClearFlags(color)
    return {"flags": clip.GetFlagList()}


@router.get("/clips/{ref}/mark-in-out")
def clip_mark_in_out(ref: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"marks": bridge.clip(ref).GetMarkInOut() or {}}


@router.put("/clips/{ref}/mark-in-out")
def set_clip_mark_in_out(ref: str, body: MarkInOut, bridge: ResolveBridge = Depends(resolve_session)):
    clip = bridge.clip(ref)
    require(clip.SetMarkInOut(body.in_frame, body.out_frame, body.type), "Resolve refused the in/out range")
    return {"marks": clip.GetMarkInOut() or {}}


@router.delete("/clips/{ref}/mark-in-out")
def clear_clip_mark_in_out(ref: str, type: str = Query(default="all"), bridge: ResolveBridge = Depends(resolve_session)):
    clip = bridge.clip(ref)
    clip.ClearMarkInOut(type)
    return {"marks": clip.GetMarkInOut() or {}}


@router.post("/clips/{ref}/proxy")
def link_proxy(ref: str, body: ProxyPath, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.clip(ref).LinkProxyMedia(body.path), f"Resolve refused proxy {body.path!r}")
    return {"ok": True}


@router.delete("/clips/{ref}/proxy")
def unlink_proxy(ref: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.clip(ref).UnlinkProxyMedia())}


@router.post("/clips/{ref}/full-resolution")
def link_full_resolution(ref: str, body: ProxyPath, bridge: ResolveBridge = Depends(resolve_session)):
    """For a proxy-first clip: link its full-resolution media."""
    require(bridge.clip(ref).LinkFullResolutionMedia(body.path), f"Resolve refused {body.path!r}")
    return {"ok": True}


@router.post("/clips/{ref}/replace")
def replace_clip(ref: str, body: ReplaceClip, bridge: ResolveBridge = Depends(resolve_session)):
    clip = bridge.clip(ref)
    ok = clip.ReplaceClipPreserveSubClip(body.path) if body.preserve_subclip else clip.ReplaceClip(body.path)
    require(ok, f"Resolve refused to replace with {body.path!r}")
    return {"ok": True, "clip": clip_summary(clip)}


@router.post("/clips/{ref}/monitor-growing")
def monitor_growing_file(ref: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.clip(ref).MonitorGrowingFile())}


# -- import ------------------------------------------------------------------


@router.post("/import")
def import_media(body: ImportMedia, bridge: ResolveBridge = Depends(resolve_session)):
    """Import files/folders (and numbered image sequences as single clips) into the CURRENT bin.
    Paths are as seen by the Resolve machine."""
    mp = bridge.media_pool()
    imported = []
    if body.paths:
        imported += mp.ImportMedia(list(body.paths)) or []
    if body.sequences:
        infos = [{"FilePath": s.file_path, "StartIndex": s.start_index, "EndIndex": s.end_index} for s in body.sequences]
        imported += mp.ImportMedia(infos) or []
    return {"imported": [clip_summary(c) for c in imported], "requested": len(body.paths) + len(body.sequences)}


@router.post("/subclips")
def import_subclips(body: Subclips, bridge: ResolveBridge = Depends(resolve_session)):
    """Create subclips straight from disk: MediaStorage.AddItemListToMediaPool
    with {media, startFrame, endFrame} lands a trimmed clip in the current bin."""
    infos = [{"media": s.media, "startFrame": s.start_frame, "endFrame": s.end_frame} for s in body.items]
    clips = bridge.media_storage().AddItemListToMediaPool(infos) or []
    return {"imported": [clip_summary(c) for c in clips]}


@router.post("/stereo")
def create_stereo_clip(body: StereoClip, bridge: ResolveBridge = Depends(resolve_session)):
    clip = bridge.media_pool().CreateStereoClip(bridge.clip(body.left), bridge.clip(body.right))
    if not clip:
        raise NotFound("Resolve could not create the stereo clip (Studio feature)")
    return {"ok": True, "clip": clip_summary(clip)}


@router.post("/sync-audio")
def sync_audio(body: SyncAudio, bridge: ResolveBridge = Depends(resolve_session)):
    """AutoSyncAudio: at least one video + one audio clip, by timecode or waveform."""
    clips = bridge.clips(body.clips)
    settings = {
        bridge.const("AUDIO_SYNC_MODE"): bridge.const("AUDIO_SYNC_WAVEFORM" if body.mode == "waveform" else "AUDIO_SYNC_TIMECODE"),
        bridge.const("AUDIO_SYNC_RETAIN_EMBEDDED_AUDIO"): body.retain_embedded_audio,
        bridge.const("AUDIO_SYNC_RETAIN_VIDEO_METADATA"): body.retain_video_metadata,
    }
    if body.channel is not None:
        settings[bridge.const("AUDIO_SYNC_CHANNEL_NUMBER")] = body.channel
    require(bridge.media_pool().AutoSyncAudio(clips, settings), "Resolve could not sync (need >= 2 clips incl. video + audio)")
    return {"ok": True, "synced": len(clips)}


# -- mattes ----------------------------------------------------------------


@router.get("/clips/{ref}/mattes")
def clip_mattes(ref: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"mattes": bridge.media_pool().GetClipMatteList(bridge.clip(ref)) or []}


@router.post("/clips/{ref}/mattes")
def add_clip_mattes(ref: str, body: ClipMattes, bridge: ResolveBridge = Depends(resolve_session)):
    clip = bridge.clip(ref)
    ms = bridge.media_storage()
    ok = ms.AddClipMattesToMediaPool(clip, list(body.paths), body.stereo_eye) if body.stereo_eye else ms.AddClipMattesToMediaPool(clip, list(body.paths))
    require(ok, "Resolve refused the mattes")
    return {"mattes": bridge.media_pool().GetClipMatteList(clip) or []}


@router.delete("/clips/{ref}/mattes")
def delete_clip_mattes(ref: str, body: ClipMattes, bridge: ResolveBridge = Depends(resolve_session)):
    clip = bridge.clip(ref)
    require(bridge.media_pool().DeleteClipMattes(clip, list(body.paths)), "Resolve refused to delete the mattes")
    return {"mattes": bridge.media_pool().GetClipMatteList(clip) or []}


@router.get("/mattes")
def timeline_mattes(bin: Optional[str] = Query(default=None), bridge: ResolveBridge = Depends(resolve_session)):
    folder = bridge.folder_by_path(bin) if bin else bridge.media_pool().GetCurrentFolder()
    return {"bin": folder.GetName(), "mattes": [clip_summary(c) for c in bridge.media_pool().GetTimelineMatteList(folder) or []]}


@router.post("/mattes")
def add_timeline_mattes(body: ClipMattes, bridge: ResolveBridge = Depends(resolve_session)):
    clips = bridge.media_storage().AddTimelineMattesToMediaPool(list(body.paths)) or []
    return {"mattes": [clip_summary(c) for c in clips]}


# -- metadata / selection -------------------------------------------------------


@router.post("/metadata/export")
def export_metadata(body: ExportMetadata, bridge: ResolveBridge = Depends(resolve_session)):
    mp = bridge.media_pool()
    ok = mp.ExportMetadata(body.file, bridge.clips(body.clips)) if body.clips else mp.ExportMetadata(body.file)
    require(ok, f"Resolve refused to export metadata to {body.file!r}")
    return {"ok": True, "file": body.file}


@router.get("/selection")
def selected_clips(bridge: ResolveBridge = Depends(resolve_session)):
    return {"clips": [clip_summary(c) for c in bridge.media_pool().GetSelectedClips() or []]}


@router.put("/selection")
def select_clip(body: ClipRefs, bridge: ResolveBridge = Depends(resolve_session)):
    """Resolve exposes single selection only: the first ref becomes the selected clip."""
    if not body.clips:
        raise NotFound("Give one clip ref")
    clip = bridge.clip(body.clips[0])
    require(bridge.media_pool().SetSelectedClip(clip), "Resolve refused the selection")
    return {"clips": [clip_summary(c) for c in bridge.media_pool().GetSelectedClips() or []]}


# -- Studio AI on clips and bins ----------------------------------------------------


def _target(bridge: ResolveBridge, ref: Optional[str], bin: Optional[str]):
    if ref:
        return bridge.clip(ref), f"clip {ref!r}"
    folder = bridge.folder_by_path(bin) if bin else bridge.media_pool().GetCurrentFolder()
    return folder, f"bin {folder.GetName()!r}"


@router.post("/clips/{ref}/transcribe")
def transcribe_clip(ref: str, body: Transcribe, bridge: ResolveBridge = Depends(resolve_session)):
    """Studio: audio transcription (used by text-based editing and auto-subtitles)."""
    clip = bridge.clip(ref)
    ok = clip.TranscribeAudio(body.speaker_detection) if body.speaker_detection is not None else clip.TranscribeAudio()
    require(ok, "Resolve refused to transcribe (Studio + language model required)")
    return {"ok": True}


@router.delete("/clips/{ref}/transcribe")
def clear_clip_transcription(ref: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.clip(ref).ClearTranscription())}


@router.post("/folders/transcribe")
def transcribe_bin(body: Transcribe, bin: Optional[str] = Query(default=None), bridge: ResolveBridge = Depends(resolve_session)):
    folder, label = _target(bridge, None, bin)
    ok = folder.TranscribeAudio(body.speaker_detection) if body.speaker_detection is not None else folder.TranscribeAudio()
    require(ok, f"Resolve refused to transcribe {label}")
    return {"ok": True, "bin": folder.GetName()}


@router.delete("/folders/transcribe")
def clear_bin_transcription(bin: Optional[str] = Query(default=None), bridge: ResolveBridge = Depends(resolve_session)):
    folder, _ = _target(bridge, None, bin)
    return {"ok": bool(folder.ClearTranscription())}


@router.post("/clips/{ref}/audio-classification")
def classify_clip_audio(ref: str, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.clip(ref).PerformAudioClassification(), "Resolve refused (Studio feature)")
    return {"ok": True}


@router.delete("/clips/{ref}/audio-classification")
def clear_clip_audio_classification(ref: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.clip(ref).ClearAudioClassification())}


@router.post("/folders/audio-classification")
def classify_bin_audio(bin: Optional[str] = Query(default=None), bridge: ResolveBridge = Depends(resolve_session)):
    folder, label = _target(bridge, None, bin)
    require(folder.PerformAudioClassification(), f"Resolve refused for {label}")
    return {"ok": True}


@router.delete("/folders/audio-classification")
def clear_bin_audio_classification(bin: Optional[str] = Query(default=None), bridge: ResolveBridge = Depends(resolve_session)):
    folder, _ = _target(bridge, None, bin)
    return {"ok": bool(folder.ClearAudioClassification())}


@router.post("/clips/{ref}/deblur")
def deblur_clip(ref: str, body: Deblur, bridge: ResolveBridge = Depends(resolve_session)):
    """Studio: AI motion deblur - renders a NEW clip next to the original."""
    new = bridge.clip(ref).RemoveMotionBlur(dict(body.options))
    if not new:
        raise NotFound("Resolve did not produce a deblurred clip (Studio feature; check options)")
    return {"ok": True, "clip": clip_summary(new)}


@router.post("/folders/deblur")
def deblur_bin(body: Deblur, bin: Optional[str] = Query(default=None), bridge: ResolveBridge = Depends(resolve_session)):
    folder, _ = _target(bridge, None, bin)
    pairs = folder.RemoveMotionBlur(dict(body.options)) or []
    return {"pairs": [{"original": clip_summary(o), "deblurred": clip_summary(n)} for o, n in pairs]}


@router.post("/clips/{ref}/intellisearch")
def intellisearch_clip(ref: str, body: Intellisearch, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.clip(ref).AnalyzeForIntellisearch(body.identify_faces, body.better_mode), "Resolve refused (AI IntelliSearch package installed?)")
    return {"ok": True}


@router.post("/folders/intellisearch")
def intellisearch_bin(body: Intellisearch, bin: Optional[str] = Query(default=None), bridge: ResolveBridge = Depends(resolve_session)):
    folder, _ = _target(bridge, None, bin)
    require(folder.AnalyzeForIntellisearch(body.identify_faces, body.better_mode), "Resolve refused (AI IntelliSearch package installed?)")
    return {"ok": True}


@router.post("/clips/{ref}/slate")
def analyze_clip_slate(ref: str, body: SlateAnalysis, bridge: ResolveBridge = Depends(resolve_session)):
    """Studio: AI Slate ID - detects slates and drops markers of the given color."""
    require(bridge.clip(ref).AnalyzeForSlate(bridge.const("MARKER_" + body.marker_color.upper())), "Resolve refused (AI Slate ID package installed?)")
    return {"ok": True}


@router.post("/folders/slate")
def analyze_bin_slate(body: SlateAnalysis, bin: Optional[str] = Query(default=None), bridge: ResolveBridge = Depends(resolve_session)):
    folder, _ = _target(bridge, None, bin)
    require(folder.AnalyzeForSlate(bridge.const("MARKER_" + body.marker_color.upper())), "Resolve refused (AI Slate ID package installed?)")
    return {"ok": True}


mount_markers(router, "/clips/{ref}/markers", lambda bridge, ref: bridge.clip(ref), scope="clip")
