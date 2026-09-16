"""Marker CRUD, mounted three times: timeline markers, timeline-item markers,
media-pool-clip markers. All three Resolve objects share one marker API, so
one factory builds identical routes for each scope.

Frames are offsets from the start of the object (timeline start / clip
start), exactly as Resolve reports them in GetMarkers().
"""

from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, Depends, Query

from ..bridge import NotFound, ResolveBridge, require
from ..deps import resolve_session
from ..schemas import AddMarker, MarkerCustomData
from ..serialize import marker_list


def mount_markers(router: APIRouter, prefix: str, resolver: Callable, scope: str) -> None:
    """Add marker routes under `prefix` on `router`.

    `resolver(bridge, **path_params)` returns the Resolve object owning the
    markers. Route function names are suffixed with `scope` so operationIds
    (and MCP tool names) stay unique across the three mounts.
    """

    def _list(bridge: ResolveBridge = Depends(resolve_session), **params):
        obj = resolver(bridge, **params)
        return {"markers": marker_list(obj)}

    def _add(body: AddMarker, bridge: ResolveBridge = Depends(resolve_session), **params):
        obj = resolver(bridge, **params)
        require(
            obj.AddMarker(body.frame, body.color, body.name, body.note, body.duration, body.custom_data),
            f"Resolve refused the marker at frame {body.frame} (a marker already there? frame out of range?)",
        )
        return {"ok": True, "markers": marker_list(obj)}

    def _delete(
        bridge: ResolveBridge = Depends(resolve_session),
        frame: Optional[int] = Query(default=None, description="Delete the marker at this frame"),
        color: Optional[str] = Query(default=None, description="Delete all markers of this color ('All' = every marker)"),
        custom_data: Optional[str] = Query(default=None, description="Delete the first marker carrying this custom data"),
        **params,
    ):
        obj = resolver(bridge, **params)
        if frame is not None:
            ok = obj.DeleteMarkerAtFrame(frame)
        elif color is not None:
            ok = obj.DeleteMarkersByColor(color)
        elif custom_data is not None:
            ok = obj.DeleteMarkerByCustomData(custom_data)
        else:
            raise NotFound("Give one of ?frame=, ?color= (or 'All'), ?custom_data=")
        return {"ok": bool(ok), "markers": marker_list(obj)}

    def _by_custom_data(custom_data: str, bridge: ResolveBridge = Depends(resolve_session), **params):
        obj = resolver(bridge, **params)
        info = obj.GetMarkerByCustomData(custom_data)
        if not info:
            raise NotFound(f"No marker with custom data {custom_data!r}")
        return {"marker": info}

    def _set_custom_data(frame: int, body: MarkerCustomData, bridge: ResolveBridge = Depends(resolve_session), **params):
        obj = resolver(bridge, **params)
        require(obj.UpdateMarkerCustomData(frame, body.custom_data), f"No marker at frame {frame}")
        return {"ok": True, "frame": frame, "custom_data": obj.GetMarkerCustomData(frame)}

    # FastAPI needs the path params in the signature: build thin wrappers per scope.
    for fn, method, path, name in (
        (_list, "GET", "", f"list_markers_{scope}"),
        (_add, "POST", "", f"add_marker_{scope}"),
        (_delete, "DELETE", "", f"delete_markers_{scope}"),
        (_by_custom_data, "GET", "/by-custom-data/{custom_data}", f"marker_by_custom_data_{scope}"),
        (_set_custom_data, "PATCH", "/{frame}/custom-data", f"set_marker_custom_data_{scope}"),
    ):
        router.add_api_route(
            prefix + path,
            _with_path_params(fn, prefix),
            methods=[method],
            name=name,
            summary=name.replace("_", " "),
        )


def _with_path_params(fn, prefix: str):
    """Rewrite `fn(**params)` into a function whose signature declares the
    `{...}` path parameters found in `prefix`, so FastAPI injects them."""
    import inspect
    import typing

    names = [p[1:-1] for p in prefix.split("/") if p.startswith("{") and p.endswith("}")]
    sig = inspect.signature(fn)
    # `from __future__ import annotations` leaves strings; resolve them against
    # the wrapped function's module, not this one's.
    hints = typing.get_type_hints(fn, include_extras=True)
    params = [
        p.replace(annotation=hints.get(p.name, p.annotation))
        for p in sig.parameters.values()
        if p.kind is not inspect.Parameter.VAR_KEYWORD
    ]
    path_params = [inspect.Parameter(n, inspect.Parameter.KEYWORD_ONLY, annotation=str) for n in names]

    def wrapper(**kwargs):
        return fn(**kwargs)

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    wrapper.__signature__ = sig.replace(parameters=params + path_params)  # type: ignore[attr-defined]
    return wrapper
