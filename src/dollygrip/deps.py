"""FastAPI dependencies: bridge access and per-request serialization.

`resolve_session` is the workhorse - it hands routers the bridge while
holding its lock, so concurrent HTTP requests never interleave calls into
the (not-thread-safe) fusionscript handle.
"""

from __future__ import annotations

from typing import Iterator

from fastapi import Request

from .bridge import ResolveBridge


def get_bridge(request: Request) -> ResolveBridge:
    return request.app.state.bridge


def resolve_session(request: Request) -> Iterator[ResolveBridge]:
    bridge: ResolveBridge = request.app.state.bridge
    with bridge.lock:
        bridge.ensure()
        yield bridge
