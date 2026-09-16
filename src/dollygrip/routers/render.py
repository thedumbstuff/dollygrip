"""Deliver page: formats/codecs/resolutions, render presets, the queue,
start/stop/wait, quick export, burn-in presets."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query, Request

from ..bridge import NotFound, ResolveBridge, require
from ..deps import get_bridge, resolve_session
from ..schemas import ExportPreset, ImportPreset, NamedPreset, QuickExport, RenderJob, RenderMode, StartRender

router = APIRouter(prefix="/render", tags=["render"])

_MODES = {"individual": 0, "single": 1}
_MODE_NAMES = {0: "individual", 1: "single"}


@router.get("/formats")
def render_formats(bridge: ResolveBridge = Depends(resolve_session)):
    return {"formats": bridge.current_project().GetRenderFormats() or {}}


@router.get("/formats/{fmt}/codecs")
def render_codecs(fmt: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"codecs": bridge.current_project().GetRenderCodecs(fmt) or {}}


@router.get("/resolutions")
def render_resolutions(
    format: str = Query(default=None), codec: str = Query(default=None), bridge: ResolveBridge = Depends(resolve_session)
):
    project = bridge.current_project()
    res = project.GetRenderResolutions(format, codec) if format and codec else project.GetRenderResolutions()
    return {"resolutions": res or []}


@router.get("/current")
def current_render_setup(bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    fc = project.GetCurrentRenderFormatAndCodec() or {}
    return {
        "format": fc.get("format"),
        "codec": fc.get("codec"),
        "mode": _MODE_NAMES.get(project.GetCurrentRenderMode()),
        "rendering": bool(project.IsRenderingInProgress()),
    }


@router.get("/mode")
def render_mode(bridge: ResolveBridge = Depends(resolve_session)):
    return {"mode": _MODE_NAMES.get(bridge.current_project().GetCurrentRenderMode())}


@router.put("/mode")
def set_render_mode(body: RenderMode, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.current_project().SetCurrentRenderMode(_MODES[body.mode]), "Resolve refused the render mode")
    return {"mode": body.mode}


# -- presets ----------------------------------------------------------------


@router.get("/presets")
def render_presets(bridge: ResolveBridge = Depends(resolve_session)):
    return {"presets": bridge.current_project().GetRenderPresetList() or []}


@router.post("/presets/{name}/load")
def load_render_preset(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.current_project().LoadRenderPreset(name), f"Render preset {name!r} not found")
    return {"ok": True, "preset": name}


@router.post("/presets")
def save_render_preset(body: NamedPreset, bridge: ResolveBridge = Depends(resolve_session)):
    """Save the CURRENT render settings as a new preset."""
    require(bridge.current_project().SaveAsNewRenderPreset(body.name), f"Could not save preset {body.name!r} (name taken?)")
    return {"ok": True, "preset": body.name}


@router.delete("/presets/{name}")
def delete_render_preset(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.current_project().DeleteRenderPreset(name), f"Render preset {name!r} not found")
    return {"ok": True}


@router.post("/presets/import")
def import_render_preset(body: ImportPreset, bridge: ResolveBridge = Depends(resolve_session)):
    """Import a render preset file and make it current."""
    require(bridge.ensure().ImportRenderPreset(body.path), f"Resolve refused preset file {body.path!r}")
    return {"ok": True}


@router.post("/presets/{name}/export")
def export_render_preset(name: str, body: ExportPreset, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().ExportRenderPreset(name, body.path), f"Render preset {name!r} not found")
    return {"ok": True, "path": body.path}


# -- queue --------------------------------------------------------------------


@router.post("/jobs")
def add_job(body: RenderJob, bridge: ResolveBridge = Depends(resolve_session)):
    """Queue a render of the current timeline: optional preset, then
    format/codec, then mode, then settings - the order Resolve needs."""
    project = bridge.current_project()
    bridge.current_timeline()  # a render needs an open timeline - fail with 409 early
    if body.preset:
        require(project.LoadRenderPreset(body.preset), f"Render preset {body.preset!r} not found")
    if body.format and body.codec:
        if not project.SetCurrentRenderFormatAndCodec(body.format, body.codec):
            raise NotFound(f"Format/codec pair {body.format!r}/{body.codec!r} rejected by Resolve")
    if body.mode:
        project.SetCurrentRenderMode(_MODES[body.mode])
    if body.settings:
        require(project.SetRenderSettings(dict(body.settings)), "Resolve rejected the render settings")
    job_id = project.AddRenderJob()
    if not job_id:
        raise NotFound("AddRenderJob failed - check render settings")
    started = bool(project.StartRendering([job_id])) if body.start else False
    return {"job_id": job_id, "started": started}


@router.get("/jobs")
def list_jobs(bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    return {"jobs": project.GetRenderJobList() or [], "rendering": bool(project.IsRenderingInProgress())}


@router.delete("/jobs")
def delete_all_jobs(bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.current_project().DeleteAllRenderJobs())}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    status = bridge.current_project().GetRenderJobStatus(job_id)
    if not status:
        raise NotFound(f"Render job {job_id!r} not found")
    return {"job_id": job_id, **status}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.current_project().DeleteRenderJob(job_id))}


@router.post("/start")
def start_rendering(body: StartRender, bridge: ResolveBridge = Depends(resolve_session)):
    """Start specific jobs, or every queued job when job_ids is empty."""
    project = bridge.current_project()
    if body.job_ids:
        ok = project.StartRendering(list(body.job_ids), body.interactive) if body.interactive else project.StartRendering(list(body.job_ids))
    else:
        ok = project.StartRendering(body.interactive) if body.interactive else project.StartRendering()
    return {"ok": bool(ok), "rendering": bool(project.IsRenderingInProgress())}


@router.post("/stop")
def stop_rendering(bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    project.StopRendering()
    return {"ok": True, "rendering": bool(project.IsRenderingInProgress())}


@router.get("/active")
def rendering_active(bridge: ResolveBridge = Depends(resolve_session)):
    return {"rendering": bool(bridge.current_project().IsRenderingInProgress())}


@router.post("/jobs/{job_id}/wait")
def wait_for_job(
    job_id: str,
    request: Request,
    timeout: float = Query(default=600, ge=0, le=86400, description="Seconds to wait before giving up"),
    poll: float = Query(default=2.0, ge=0.2, le=60, description="Seconds between status checks"),
    bridge: ResolveBridge = Depends(get_bridge),
):
    """Block until the job completes/fails/cancels (or the timeout passes).
    The bridge lock is released between polls so other calls keep flowing."""
    deadline = time.monotonic() + timeout
    while True:
        with bridge.lock:
            bridge.ensure()
            status = bridge.current_project().GetRenderJobStatus(job_id)
        if not status:
            raise NotFound(f"Render job {job_id!r} not found")
        state = str(status.get("JobStatus", ""))
        if state in ("Complete", "Failed", "Cancelled") or time.monotonic() >= deadline:
            return {"job_id": job_id, "done": state in ("Complete", "Failed", "Cancelled"), "timed_out": state not in ("Complete", "Failed", "Cancelled"), **status}
        time.sleep(poll)


# -- quick export -------------------------------------------------------------


@router.get("/quick-export/presets")
def quick_export_presets(bridge: ResolveBridge = Depends(resolve_session)):
    return {"presets": bridge.current_project().GetQuickExportRenderPresets() or []}


@router.post("/quick-export")
def quick_export(body: QuickExport, bridge: ResolveBridge = Depends(resolve_session)):
    """RenderWithQuickExport: one call, blocks until Resolve finishes."""
    params = {}
    if body.target_dir is not None:
        params["TargetDir"] = body.target_dir
    if body.custom_name is not None:
        params["CustomName"] = body.custom_name
    if body.video_quality is not None:
        params["VideoQuality"] = body.video_quality
    if body.enable_upload is not None:
        params["EnableUpload"] = body.enable_upload
    result = bridge.current_project().RenderWithQuickExport(body.preset, params)
    if not isinstance(result, dict):
        raise NotFound(f"Quick export failed: {result!r}")
    return {"ok": True, **result}


# -- burn-in presets -----------------------------------------------------------


@router.get("/burn-in/presets")
def burn_in_presets(bridge: ResolveBridge = Depends(resolve_session)):
    return {"presets": bridge.ensure().GetBurnInPresetList() or []}


@router.post("/burn-in/presets/{name}/load")
def load_burn_in_preset(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    """Apply a data burn-in preset to the current project."""
    require(bridge.current_project().LoadBurnInPreset(name), f"Burn-in preset {name!r} not found")
    return {"ok": True}


@router.delete("/burn-in/presets/{name}")
def delete_burn_in_preset(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().DeleteBurnInPreset(name), f"Burn-in preset {name!r} not found")
    return {"ok": True}


@router.post("/burn-in/presets/import")
def import_burn_in_preset(body: ImportPreset, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().ImportBurnInPreset(body.path), f"Resolve refused {body.path!r}")
    return {"ok": True}


@router.post("/burn-in/presets/{name}/export")
def export_burn_in_preset(name: str, body: ExportPreset, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().ExportBurnInPreset(name, body.path), f"Burn-in preset {name!r} not found")
    return {"ok": True, "path": body.path}
