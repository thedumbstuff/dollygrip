"""Recipes: run a whole pipeline (import -> assemble -> title -> grade ->
render) as one ordered list of steps, each step being any DollyGrip operation
by name (the operationId you see in /docs and as MCP tool names).

Later steps can reference earlier results with `{{ steps.<name>.<path> }}`
templates, e.g. `{{ steps.assemble.results[0].item_id }}`. A `dry_run` returns
the resolved plan without touching Resolve. Steps are dispatched in-process
through the same FastAPI app, so every gateway guarantee (lock, reconnect,
error mapping) applies.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI

from .mcp_server import Dispatcher, ToolSpec, build_tool_specs

_TEMPLATE = re.compile(r"\{\{\s*(.*?)\s*\}\}")
_INDEX = re.compile(r"^([^\[\]]*)((?:\[\d+\])*)$")


class RecipeError(ValueError):
    """Bad recipe (unknown op, bad template) - reported per step, never a 500."""


def tool_specs(app: FastAPI) -> Dict[str, ToolSpec]:
    """Operation name -> spec, cached on the app."""
    cache = getattr(app.state, "recipe_specs", None)
    if cache is None:
        cache = {t.name: t for t in build_tool_specs(app)}
        app.state.recipe_specs = cache
    return cache


def _lookup(path: str, context: Dict[str, Any]) -> Any:
    """Resolve 'steps.name.results[0].item_id' against the context dict."""
    current: Any = context
    for raw in path.split("."):
        m = _INDEX.match(raw)
        if not m:
            raise RecipeError(f"bad template path segment {raw!r}")
        key, indexes = m.group(1), m.group(2)
        if key:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list) and key.isdigit():
                current = current[int(key)]
            else:
                raise RecipeError(f"template path {path!r}: no key {key!r}")
        for idx in re.findall(r"\[(\d+)\]", indexes):
            try:
                current = current[int(idx)]
            except (IndexError, KeyError, TypeError) as e:
                raise RecipeError(f"template path {path!r}: index [{idx}] out of range") from e
    return current


def render(value: Any, context: Dict[str, Any]) -> Any:
    """Substitute templates anywhere inside a JSON value. A string that is
    exactly one template yields the referenced value unchanged (any type)."""
    if isinstance(value, str):
        full = _TEMPLATE.fullmatch(value.strip())
        if full:
            return _lookup(full.group(1), context)
        return _TEMPLATE.sub(lambda m: str(_lookup(m.group(1), context)), value)
    if isinstance(value, list):
        return [render(v, context) for v in value]
    if isinstance(value, dict):
        return {k: render(v, context) for k, v in value.items()}
    return value


async def run_recipe(
    app: FastAPI,
    steps: List[Dict[str, Any]],
    dry_run: bool = False,
    stop_on_error: bool = True,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    specs = tool_specs(app)
    dispatcher = Dispatcher(app, token)
    context: Dict[str, Any] = {"steps": {}}
    report: List[Dict[str, Any]] = []
    ok = True
    try:
        for i, step in enumerate(steps):
            name = step.get("name") or f"step{i + 1}"
            op = step.get("op")
            entry: Dict[str, Any] = {"name": name, "op": op}
            spec = specs.get(op or "")
            if spec is None:
                entry.update(status="error", error=f"unknown operation {op!r}")
            else:
                try:
                    args = render(step.get("args") or {}, context)
                    entry["args"] = args
                    if dry_run:
                        entry["status"] = "planned"
                        # let later templates resolve against a placeholder
                        context["steps"][name] = {"_planned": True}
                    else:
                        started = time.monotonic()
                        result = await dispatcher.call(spec, args)
                        entry["ms"] = int((time.monotonic() - started) * 1000)
                        if "status" in result and "error" in result and len(result) == 2:
                            entry.update(status="error", error=result["error"], http_status=result["status"])
                        else:
                            entry.update(status="ok", result=result)
                            context["steps"][name] = result
                            context["last"] = result
                except RecipeError as e:
                    entry.update(status="error", error=str(e))
            report.append(entry)
            if entry["status"] == "error":
                ok = False
                if stop_on_error:
                    for j, rest in enumerate(steps[i + 1 :], start=i + 1):
                        report.append({"name": rest.get("name") or f"step{j + 1}", "op": rest.get("op"), "status": "skipped"})
                    break
    finally:
        await dispatcher.aclose()
    return {"ok": ok, "dry_run": dry_run, "steps": report}


def run_recipe_sync(app: FastAPI, steps, dry_run=False, stop_on_error=True, token=None) -> Dict[str, Any]:
    """Blocking wrapper for use from sync code (the HTTP endpoint runs in a
    worker thread with no event loop of its own; the CLI has none either)."""
    return asyncio.run(run_recipe(app, steps, dry_run, stop_on_error, token))
