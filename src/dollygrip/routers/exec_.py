"""The escape hatch: run raw Python against the live scripting objects.

Typed endpoints will always lag behind the full Resolve API surface; this
keeps the gateway useful in the meantime. It is OFF by default - enable
with `dollygrip serve --allow-exec` - and, like everything else, it should
only ever listen on localhost. Treat it as what it is: arbitrary code
execution on the machine running Resolve.
"""

from __future__ import annotations

import contextlib
import io

from fastapi import APIRouter, Depends, HTTPException, Request

from ..bridge import ResolveBridge
from ..deps import resolve_session
from ..schemas import ExecCode

router = APIRouter(tags=["exec"])


@router.post("/exec")
def exec_code(body: ExecCode, request: Request, bridge: ResolveBridge = Depends(resolve_session)):
    if not request.app.state.settings.allow_exec:
        raise HTTPException(
            status_code=403,
            detail="The /exec escape hatch is disabled. Start the gateway with "
            "`dollygrip serve --allow-exec` to enable it.",
        )
    resolve = bridge.ensure()
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject() if pm else None
    namespace = {
        "resolve": resolve,
        "fusion": _quiet(resolve.Fusion),
        "media_storage": _quiet(resolve.GetMediaStorage),
        "project_manager": pm,
        "project": project,
        "media_pool": project.GetMediaPool() if project else None,
        "timeline": project.GetCurrentTimeline() if project else None,
        "gallery": _quiet(project.GetGallery) if project else None,
        "result": None,
    }
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            exec(compile(body.code, "<dollygrip-exec>", "exec"), namespace)  # noqa: S102 - the point of the endpoint
    except Exception as e:  # surface the traceback message, not a 500
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "stdout": stdout.getvalue()}
    result = namespace.get("result")
    return {"ok": True, "result": result if _jsonable(result) else repr(result), "stdout": stdout.getvalue()}


def _quiet(fn):
    try:
        return fn()
    except Exception:
        return None


def _jsonable(value) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_jsonable(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _jsonable(v) for k, v in value.items())
    return False
