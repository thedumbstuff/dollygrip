from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .bridge import NothingOpen, NotFound, ResolveBridge, ResolveUnavailable
from .routers import exec_, mediapool, projects, render, system, timelines

API_PREFIX = "/api/v1"


@dataclass
class Settings:
    allow_exec: bool = False
    token: Optional[str] = None
    open_paths: tuple = field(default=("/api/v1/health", "/docs", "/openapi.json", "/redoc"))


def create_app(settings: Optional[Settings] = None, bridge: Optional[ResolveBridge] = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="DollyGrip",
        version=__version__,
        description="A local REST gateway for the DaVinci Resolve scripting API. "
        "Interactive docs below; the machine running this gateway must also be "
        "running DaVinci Resolve Studio.",
    )
    app.state.settings = settings
    app.state.bridge = bridge or ResolveBridge()

    # -- optional bearer-token auth (health and docs stay open) -----------
    @app.middleware("http")
    async def token_auth(request: Request, call_next):
        if settings.token and request.url.path not in settings.open_paths:
            supplied = request.headers.get("authorization", "")
            if supplied != f"Bearer {settings.token}":
                return JSONResponse(status_code=401, content={"detail": "Missing or bad bearer token"})
        return await call_next(request)

    # -- domain errors -> HTTP -------------------------------------------
    @app.exception_handler(ResolveUnavailable)
    async def _unavailable(request: Request, exc: ResolveUnavailable):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(NothingOpen)
    async def _nothing_open(request: Request, exc: NothingOpen):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(NotFound)
    async def _not_found(request: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    for r in (system.router, projects.router, mediapool.router, timelines.router, render.router, exec_.router):
        app.include_router(r, prefix=API_PREFIX)

    return app
