from __future__ import annotations

from fastapi import APIRouter, Depends

from ..bridge import NotFound, ResolveBridge
from ..deps import resolve_session
from ..schemas import OpenProject, ProjectSettings

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(bridge: ResolveBridge = Depends(resolve_session)):
    pm = bridge.project_manager()
    current = pm.GetCurrentProject()
    return {
        "projects": pm.GetProjectListInCurrentFolder() or [],
        "current": current.GetName() if current else None,
    }


@router.get("/current")
def current_project(bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    tl = project.GetCurrentTimeline()
    return {
        "name": project.GetName(),
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


@router.post("/current/save")
def save_project(bridge: ResolveBridge = Depends(resolve_session)):
    bridge.current_project()  # 409 if nothing open
    return {"ok": bool(bridge.project_manager().SaveProject())}


@router.get("/current/settings")
def get_settings(bridge: ResolveBridge = Depends(resolve_session)):
    return {"settings": bridge.current_project().GetSetting() or {}}


@router.patch("/current/settings")
def patch_settings(body: ProjectSettings, bridge: ResolveBridge = Depends(resolve_session)):
    project = bridge.current_project()
    results = {k: bool(project.SetSetting(k, v)) for k, v in body.settings.items()}
    return {"results": results}
