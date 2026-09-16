"""Resolve-level: health, info, page switching, UI layout presets, user
preference presets, background tasks, quit - plus Media Storage browsing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import discovery
from ..bridge import ResolveBridge, require
from ..deps import get_bridge, resolve_session
from ..schemas import Confirm, ExportPreset, ImportPreset, NamedPreset, SetPage, StoragePath, StoragePaths
from ..serialize import clip_summary, safe

router = APIRouter(tags=["system"])


@router.get("/health")
def health(bridge: ResolveBridge = Depends(get_bridge)):
    """Gateway liveness + Resolve reachability. Never raises."""
    with bridge.lock:
        connected = bridge.connected
        out = {"gateway": "ok", "resolve": "connected" if connected else "disconnected"}
        if connected:
            r = bridge.ensure()
            out["product"] = r.GetProductName()
            out["version"] = r.GetVersionString()
        else:
            out["hint"] = (
                "Start DaVinci Resolve (Studio edition) and enable Preferences > "
                "System > General > External scripting = Local. "
                "Run `dollygrip doctor` for a full diagnosis."
            )
        return out


@router.get("/system/info")
def system_info(bridge: ResolveBridge = Depends(resolve_session)):
    r = bridge.ensure()
    pm = r.GetProjectManager()
    project = pm.GetCurrentProject() if pm else None
    return {
        "product": r.GetProductName(),
        "version": r.GetVersionString(),
        "version_fields": safe(r.GetVersion),
        "current_page": r.GetCurrentPage(),
        "current_project": project.GetName() if project else None,
        "database": safe(pm.GetCurrentDatabase) if pm else None,
        "scripting_paths": discovery.probe(),
    }


@router.get("/system/constants")
def system_constants(prefix: str = Query(default="", description="Filter, e.g. EXPORT_ or MARKER_"), bridge: ResolveBridge = Depends(resolve_session)):
    """The `resolve.*` enum constants this build exposes (values you can pass to /exec)."""
    r = bridge.ensure()
    out = {}
    for name in dir(r):
        if name.isupper() and name.startswith(prefix):
            value = getattr(r, name, None)
            if isinstance(value, (int, float, str, bool)):
                out[name] = value
    return {"constants": out}


@router.post("/system/page")
def open_page(body: SetPage, bridge: ResolveBridge = Depends(resolve_session)):
    ok = bridge.ensure().OpenPage(body.page)
    return {"ok": bool(ok), "page": body.page}


@router.post("/system/quit")
def quit_resolve(body: Confirm, bridge: ResolveBridge = Depends(resolve_session)):
    """Quit Resolve. Requires {"confirm": true}. Save the project first."""
    require(body.confirm, "Send {\"confirm\": true} to quit Resolve")
    bridge.ensure().Quit()
    return {"ok": True}


@router.post("/system/background-tasks/disable")
def disable_background_tasks(bridge: ResolveBridge = Depends(resolve_session)):
    """Disable Resolve's background tasks for this session (faster scripted batches)."""
    bridge.ensure().DisableBackgroundTasksForCurrentResolveSession()
    return {"ok": True}


@router.get("/system/fairlight-presets")
def fairlight_presets(bridge: ResolveBridge = Depends(resolve_session)):
    return {"presets": bridge.ensure().GetFairlightPresets() or []}


# -- UI layout presets ----------------------------------------------------------


@router.get("/system/layouts")
def layout_presets(bridge: ResolveBridge = Depends(resolve_session)):
    return {"presets": bridge.ensure().GetLayoutPresetList() or []}


@router.post("/system/layouts")
def save_layout_preset(body: NamedPreset, bridge: ResolveBridge = Depends(resolve_session)):
    """Save the current UI layout under a name."""
    require(bridge.ensure().SaveLayoutPreset(body.name), f"Could not save layout {body.name!r}")
    return {"ok": True}


@router.post("/system/layouts/{name}/load")
def load_layout_preset(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().LoadLayoutPreset(name), f"Layout preset {name!r} not found")
    return {"ok": True}


@router.put("/system/layouts/{name}")
def update_layout_preset(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Overwrite a preset with the current layout."""
    require(bridge.ensure().UpdateLayoutPreset(name), f"Layout preset {name!r} not found")
    return {"ok": True}


@router.delete("/system/layouts/{name}")
def delete_layout_preset(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().DeleteLayoutPreset(name), f"Layout preset {name!r} not found")
    return {"ok": True}


@router.post("/system/layouts/import")
def import_layout_preset(body: ImportPreset, bridge: ResolveBridge = Depends(resolve_session)):
    r = bridge.ensure()
    ok = r.ImportLayoutPreset(body.path, body.name) if body.name else r.ImportLayoutPreset(body.path)
    require(ok, f"Resolve refused layout file {body.path!r}")
    return {"ok": True}


@router.post("/system/layouts/{name}/export")
def export_layout_preset(name: str, body: ExportPreset, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().ExportLayoutPreset(name, body.path), f"Layout preset {name!r} not found")
    return {"ok": True, "path": body.path}


# -- user preference presets -----------------------------------------------------


@router.get("/system/preferences/presets")
def preference_presets(bridge: ResolveBridge = Depends(resolve_session)):
    return {"presets": bridge.ensure().GetUserPreferencesPresetList() or []}


@router.post("/system/preferences/presets")
def save_preference_preset(body: NamedPreset, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().SaveUserPreferencesPreset(body.name), f"Could not save preferences preset {body.name!r}")
    return {"ok": True}


@router.post("/system/preferences/presets/{name}/load")
def load_preference_preset(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().LoadUserPreferencesPreset(name), f"Preferences preset {name!r} not found")
    return {"ok": True}


@router.delete("/system/preferences/presets/{name}")
def delete_preference_preset(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().DeleteUserPreferencesPreset(name), f"Preferences preset {name!r} not found")
    return {"ok": True}


@router.post("/system/preferences/presets/import")
def import_preference_preset(body: ImportPreset, bridge: ResolveBridge = Depends(resolve_session)):
    r = bridge.ensure()
    ok = r.ImportUserPreferencesPreset(body.path, body.name) if body.name else r.ImportUserPreferencesPreset(body.path)
    require(ok, f"Resolve refused preferences file {body.path!r}")
    return {"ok": True}


@router.post("/system/preferences/presets/{name}/export")
def export_preference_preset(name: str, body: ExportPreset, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().ExportUserPreferencesPreset(name, body.path), f"Preferences preset {name!r} not found")
    return {"ok": True, "path": body.path}


# -- media storage (the Media page's file browser) --------------------------------------


@router.get("/storage/volumes")
def storage_volumes(bridge: ResolveBridge = Depends(resolve_session)):
    return {"volumes": bridge.media_storage().GetMountedVolumeList() or []}


@router.get("/storage/folders")
def storage_folders(path: str = Query(description="Absolute folder path"), bridge: ResolveBridge = Depends(resolve_session)):
    return {"path": path, "folders": bridge.media_storage().GetSubFolderList(path) or []}


@router.get("/storage/files")
def storage_files(path: str = Query(description="Absolute folder path"), bridge: ResolveBridge = Depends(resolve_session)):
    """Media listings as Resolve sees them (image sequences come back consolidated)."""
    return {"path": path, "files": bridge.media_storage().GetFileList(path) or []}


@router.post("/storage/reveal")
def storage_reveal(body: StoragePath, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.media_storage().RevealInStorage(body.path), f"Resolve could not reveal {body.path!r}")
    return {"ok": True}


@router.post("/storage/add-to-mediapool")
def storage_add_to_mediapool(body: StoragePaths, bridge: ResolveBridge = Depends(resolve_session)):
    """Add files/folders (or {media,start_frame,end_frame} subclips) from Media Storage to the current bin."""
    items = [it if isinstance(it, str) else {"media": it.media, "startFrame": it.start_frame, "endFrame": it.end_frame} for it in body.items]
    clips = bridge.media_storage().AddItemListToMediaPool(items) or []
    return {"imported": [clip_summary(c) for c in clips]}
