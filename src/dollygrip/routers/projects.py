"""Project manager + project: open/create/close/delete, project folders,
import/export/archive/restore, databases, project presets & settings,
Fairlight presets, AI speech generation."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..bridge import NotFound, ResolveBridge, require
from ..deps import resolve_session
from ..schemas import (
    ArchiveProjectFile,
    AudioAtPlayhead,
    CreateProject,
    DatabaseInfo,
    ExportProjectFile,
    ImportProjectFile,
    NamedPreset,
    OpenProject,
    OpenProjectFolder,
    ProjectFolder,
    ProjectSettings,
    RenameProject,
    SpeechGeneration,
)
from ..serialize import clip_summary, safe

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(bridge: ResolveBridge = Depends(resolve_session)):
    pm = bridge.project_manager()
    current = pm.GetCurrentProject()
    return {
        "projects": pm.GetProjectListInCurrentFolder() or [],
        "folders": pm.GetFolderListInCurrentFolder() or [],
        "folder": pm.GetCurrentFolder() or "",
        "current": current.GetName() if current else None,
    }


@router.get("/attributes")
def project_attributes(bridge: ResolveBridge = Depends(resolve_session)):
    """Per-project attributes in the current folder (lastModifiedDate, creationDate, notes, ...)."""
    return {"projects": bridge.project_manager().GetProjectAttributesInCurrentFolder() or {}}


@router.post("")
def create_project(body: CreateProject, bridge: ResolveBridge = Depends(resolve_session)):
    pm = bridge.project_manager()
    project = pm.CreateProject(body.name, body.media_location_path) if body.media_location_path else pm.CreateProject(body.name)
    if not project:
        raise NotFound(f"Could not create project {body.name!r} (name taken in this folder?)")
    return {"ok": True, "name": project.GetName(), "id": safe(project.GetUniqueId)}


@router.delete("/{name}")
def delete_project(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Delete a project in the current folder (not the one that is open)."""
    require(bridge.project_manager().DeleteProject(name), f"Could not delete {name!r} (open, or not in this folder?)")
    return {"ok": True}


@router.get("/current")
def current_project(bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    tl = project.GetCurrentTimeline()
    return {
        "name": project.GetName(),
        "id": safe(project.GetUniqueId),
        "timeline_count": int(project.GetTimelineCount()),
        "current_timeline": tl.GetName() if tl else None,
        "frame_rate": project.GetSetting("timelineFrameRate"),
        "width": project.GetSetting("timelineResolutionWidth"),
        "height": project.GetSetting("timelineResolutionHeight"),
    }


@router.post("/current")
def open_project(body: OpenProject, bridge: ResolveBridge = Depends(resolve_session)):
    pm = bridge.project_manager()
    project = pm.LoadProject(body.name)
    if not project:
        raise NotFound(f"Project {body.name!r} not found in the current project folder")
    return {"ok": True, "name": project.GetName()}


@router.patch("/current")
def rename_project(body: RenameProject, bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    require(project.SetName(body.name), f"Could not rename to {body.name!r} (name taken?)")
    return {"ok": True, "name": project.GetName()}


@router.post("/current/save")
def save_project(bridge: ResolveBridge = Depends(resolve_session)):
    bridge.current_project()  # 409 if nothing open
    return {"ok": bool(bridge.project_manager().SaveProject())}


@router.post("/current/close")
def close_project(bridge: ResolveBridge = Depends(resolve_session)):
    """Close WITHOUT saving (call /save first if you want the changes)."""
    project = bridge.current_project()
    return {"ok": bool(bridge.project_manager().CloseProject(project))}


@router.get("/current/settings")
def get_settings(bridge: ResolveBridge = Depends(resolve_session)):
    return {"settings": bridge.current_project().GetSetting() or {}}


@router.patch("/current/settings")
def patch_settings(body: ProjectSettings, bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    return {"results": {k: bool(project.SetSetting(k, v)) for k, v in body.settings.items()}}


@router.get("/current/presets")
def project_presets(bridge: ResolveBridge = Depends(resolve_session)):
    return {"presets": bridge.current_project().GetPresetList() or []}


@router.post("/current/presets/{name}/load")
def load_project_preset(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.current_project().SetPreset(name), f"Project preset {name!r} not found")
    return {"ok": True}


@router.post("/current/luts/refresh")
def refresh_luts(bridge: ResolveBridge = Depends(resolve_session)):
    """Re-scan the LUT folders (needed before SetLUT can see a new file)."""
    return {"ok": bool(bridge.current_project().RefreshLUTList())}


# -- interchange --------------------------------------------------------------


@router.post("/import")
def import_project(body: ImportProjectFile, bridge: ResolveBridge = Depends(resolve_session)):
    pm = bridge.project_manager()
    ok = pm.ImportProject(body.path, body.name) if body.name else pm.ImportProject(body.path)
    require(ok, f"Resolve refused to import {body.path!r}")
    return {"ok": True}


@router.post("/restore")
def restore_project(body: ImportProjectFile, bridge: ResolveBridge = Depends(resolve_session)):
    """Restore from a .dra archive."""
    pm = bridge.project_manager()
    ok = pm.RestoreProject(body.path, body.name) if body.name else pm.RestoreProject(body.path)
    require(ok, f"Resolve refused to restore {body.path!r}")
    return {"ok": True}


@router.post("/current/export")
def export_project(body: ExportProjectFile, bridge: ResolveBridge = Depends(resolve_session)):
    """Export the open project as .drp."""
    project = bridge.current_project()
    require(bridge.project_manager().ExportProject(project.GetName(), body.path, body.with_stills_and_luts), f"Resolve refused to export to {body.path!r}")
    return {"ok": True, "path": body.path}


@router.post("/current/archive")
def archive_project(body: ArchiveProjectFile, bridge: ResolveBridge = Depends(resolve_session)):
    """Archive the open project (.dra) with media/cache/proxy options."""
    project = bridge.current_project()
    require(
        bridge.project_manager().ArchiveProject(project.GetName(), body.path, body.source_media, body.render_cache, body.proxy_media),
        f"Resolve refused to archive to {body.path!r}",
    )
    return {"ok": True, "path": body.path}


# -- project folders -----------------------------------------------------------


@router.get("/folders")
def project_folders(bridge: ResolveBridge = Depends(resolve_session)):
    pm = bridge.project_manager()
    return {"folder": pm.GetCurrentFolder() or "", "folders": pm.GetFolderListInCurrentFolder() or []}


@router.post("/folders")
def create_project_folder(body: ProjectFolder, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.project_manager().CreateFolder(body.name), f"Could not create folder {body.name!r}")
    return {"ok": True}


@router.delete("/folders/{name}")
def delete_project_folder(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.project_manager().DeleteFolder(name), f"Could not delete folder {name!r}")
    return {"ok": True}


@router.post("/folders/open")
def open_project_folder(body: OpenProjectFolder, bridge: ResolveBridge = Depends(resolve_session)):
    """Navigate the project library: a folder name, '..' for parent, '/' for root."""
    pm = bridge.project_manager()
    if body.name == "/":
        ok = pm.GotoRootFolder()
    elif body.name == "..":
        ok = pm.GotoParentFolder()
    else:
        ok = pm.OpenFolder(body.name)
    require(ok, f"Could not open folder {body.name!r}")
    return {"ok": True, "folder": pm.GetCurrentFolder() or "", "projects": pm.GetProjectListInCurrentFolder() or []}


# -- databases ---------------------------------------------------------------------


@router.get("/databases")
def databases(bridge: ResolveBridge = Depends(resolve_session)):
    pm = bridge.project_manager()
    return {"current": pm.GetCurrentDatabase() or {}, "databases": pm.GetDatabaseList() or []}


@router.put("/databases/current")
def set_database(body: DatabaseInfo, bridge: ResolveBridge = Depends(resolve_session)):
    """Switch database - closes any open project."""
    info = {"DbType": body.db_type, "DbName": body.db_name}
    if body.ip_address:
        info["IpAddress"] = body.ip_address
    require(bridge.project_manager().SetCurrentDatabase(info), f"Resolve could not switch to database {body.db_name!r}")
    return {"ok": True, "current": bridge.project_manager().GetCurrentDatabase() or {}}


# -- fairlight / AI -----------------------------------------------------------------------


@router.post("/current/fairlight-preset")
def apply_fairlight_preset(body: NamedPreset, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.current_project().ApplyFairlightPresetToCurrentTimeline(body.name), f"Fairlight preset {body.name!r} not found")
    return {"ok": True}


@router.post("/current/audio-at-playhead")
def insert_audio_at_playhead(body: AudioAtPlayhead, bridge: ResolveBridge = Depends(resolve_session)):
    """Fairlight page: insert an audio file on the selected track at the playhead."""
    require(
        bridge.current_project().InsertAudioToCurrentTrackAtPlayhead(body.path, body.start_offset_samples, body.duration_samples),
        "Resolve refused (be on the Fairlight page with a track selected)",
    )
    return {"ok": True}


@router.post("/current/speech")
def generate_speech(body: SpeechGeneration, bridge: ResolveBridge = Depends(resolve_session)):
    """Studio: AI Speech Generator - text to a voice clip in the media pool
    (optionally placed on the timeline at `timecode`)."""
    settings = {"TextInput": body.text, "VoiceModel": body.voice_model, "AddToTimeline": body.add_to_timeline}
    for key, value in (
        ("CustomVoiceFile", body.custom_voice_file),
        ("Speed", body.speed),
        ("Variation", body.variation),
        ("Pitch", body.pitch),
        ("GenerationID", body.generation_id),
        ("Filename", body.filename),
        ("AudioTrack", body.audio_track),
    ):
        if value is not None:
            settings[key] = value
    project = bridge.current_project()
    clip = project.GenerateSpeech(settings, body.timecode) if body.timecode else project.GenerateSpeech(settings)
    if not clip:
        raise NotFound("Resolve did not generate speech (AI Speech Generator package installed?)")
    return {"ok": True, "clip": clip_summary(clip)}


@router.post("/current/intellisearch/reset")
def reset_intellisearch(bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.current_project().ResetIntellisearchAnalysis())}
