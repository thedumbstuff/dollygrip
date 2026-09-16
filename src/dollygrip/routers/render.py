from __future__ import annotations

from fastapi import APIRouter, Depends

from ..bridge import NotFound, ResolveBridge
from ..deps import resolve_session
from ..schemas import RenderJob

router = APIRouter(prefix="/render", tags=["render"])


@router.get("/formats")
def render_formats(bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    formats = project.GetRenderFormats() or {}
    return {"formats": formats}


@router.get("/formats/{fmt}/codecs")
def render_codecs(fmt: str, bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    return {"codecs": project.GetRenderCodecs(fmt) or {}}


@router.post("/jobs")
def add_job(body: RenderJob, bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    bridge.current_timeline()  # a render needs an open timeline - fail with 409 early
    if body.format and body.codec:
        if not project.SetCurrentRenderFormatAndCodec(body.format, body.codec):
            raise NotFound(f"Format/codec pair {body.format!r}/{body.codec!r} rejected by Resolve")
    if body.settings:
        project.SetRenderSettings(dict(body.settings))
    job_id = project.AddRenderJob()
    if not job_id:
        raise NotFound("AddRenderJob failed - check render settings")
    started = bool(project.StartRendering(job_id)) if body.start else False
    return {"job_id": job_id, "started": started}


@router.get("/jobs")
def list_jobs(bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    return {"jobs": project.GetRenderJobList() or [], "rendering": bool(project.IsRenderingInProgress())}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    status = project.GetRenderJobStatus(job_id)
    if not status:
        raise NotFound(f"Render job {job_id!r} not found")
    return {"job_id": job_id, **status}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    return {"ok": bool(project.DeleteRenderJob(job_id))}


@router.get("/active")
def rendering_active(bridge: ResolveBridge = Depends(resolve_session)):
    return {"rendering": bool(bridge.current_project().IsRenderingInProgress())}
