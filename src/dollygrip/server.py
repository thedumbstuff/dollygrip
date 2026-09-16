from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .bridge import NothingOpen, NotFound, Rejected, ResolveBridge, ResolveUnavailable
from .routers import color, exec_, fusion, items, mediapool, projects, recipes, render, stock, system, timelines, tools

API_PREFIX = "/api/v1"


@dataclass
class Settings:
    allow_exec: bool = False
    token: Optional[str] = None
    media_dir: Optional[str] = None  # where stock downloads land (default ~/DollyGrip/stock)
    open_paths: tuple = field(default=("/api/v1/health", "/docs", "/openapi.json", "/redoc"))


def create_app(settings: Optional[Settings] = None, bridge: Optional[ResolveBridge] = None, stock_client=None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="DollyGrip",
        # operationIds = endpoint function names: stable, readable, and what
        # the MCP server uses as tool names (a test enforces uniqueness).
        generate_unique_id_function=lambda route: route.name,
        version=__version__,
        description="A local REST gateway for the DaVinci Resolve scripting API. "
        "Interactive docs below; the machine running this gateway must also be "
        "running DaVinci Resolve Studio.",
    )
    app.state.settings = settings
    app.state.bridge = bridge or ResolveBridge()
    app.state.stock = stock_client  # StockClient; created lazily from settings when None

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

    @app.exception_handler(Rejected)
    async def _rejected(request: Request, exc: Rejected):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    for r in (
        system.router,
        projects.router,
        mediapool.router,
        timelines.router,
        items.router,
        color.router,
        fusion.router,
        render.router,
        tools.router,
        recipes.router,
        stock.router,
        exec_.router,
    ):
        app.include_router(r, prefix=API_PREFIX)

    return app
