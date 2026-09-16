from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import discovery
from ..bridge import ResolveBridge
from ..deps import get_bridge, resolve_session
from ..schemas import SetPage

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
    return {
        "product": r.GetProductName(),
        "version": r.GetVersionString(),
        "current_page": r.GetCurrentPage(),
        "scripting_paths": discovery.probe(),
    }


@router.post("/system/page")
def open_page(body: SetPage, bridge: ResolveBridge = Depends(resolve_session)):
    ok = bridge.ensure().OpenPage(body.page)
    return {"ok": bool(ok), "page": body.page}
