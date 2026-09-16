"""`dollygrip mcp` - the same gateway as MCP tools for AI agents.

Every REST operation becomes one MCP tool, generated from the OpenAPI
document (tool name = operationId = the endpoint's function name, input
schema = path + query params + flattened request body). Calls are dispatched
IN-PROCESS through the FastAPI app (httpx ASGI transport), so there is no
second server to run - the MCP process owns the Resolve bridge itself.

The `mcp` package is optional (`pip install dollygrip[mcp]`); everything but
`serve_stdio` works without it so the tool-spec builder stays testable.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from fastapi import FastAPI

MAX_DESCRIPTION = 900

# Curated tag sets so an agent does not have to carry all ~290 tools.
PROFILES = {
    "all": None,
    "editor": ["system", "projects", "mediapool", "timelines", "timeline items", "render", "tools"],
    "colorist": ["system", "projects", "timelines", "timeline items", "color", "render", "tools"],
    "motion": ["system", "projects", "timelines", "timeline items", "fusion", "render", "tools"],
    "delivery": ["system", "projects", "timelines", "render", "tools"],
    "core": ["system", "projects", "mediapool", "timelines", "timeline items", "tools"],
}


@dataclass
class ToolSpec:
    name: str
    description: str
    method: str
    path: str
    path_params: List[str] = field(default_factory=list)
    query_params: List[str] = field(default_factory=list)
    body_fields: List[str] = field(default_factory=list)
    body_is_object: bool = True
    input_schema: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


def _deref(schema: Any, components: Dict[str, Any]) -> Any:
    """Inline `$ref`s (recursively) so each tool schema is self-contained."""
    if isinstance(schema, dict):
        if "$ref" in schema:
            name = schema["$ref"].rsplit("/", 1)[-1]
            return _deref(components.get(name, {}), components)
        return {k: _deref(v, components) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_deref(v, components) for v in schema]
    return schema


def build_tool_specs(
    app: FastAPI, include_tags: Optional[Iterable[str]] = None, exclude_tags: Optional[Iterable[str]] = None
) -> List[ToolSpec]:
    spec = app.openapi()
    components = spec.get("components", {}).get("schemas", {})
    include = {t.lower() for t in include_tags} if include_tags else None
    exclude = {t.lower() for t in exclude_tags} if exclude_tags else set()
    tools: List[ToolSpec] = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            tags = [t.lower() for t in op.get("tags", [])]
            if include is not None and not (set(tags) & include):
                continue
            if set(tags) & exclude:
                continue
            props: Dict[str, Any] = {}
            required: List[str] = []
            path_params, query_params = [], []
            for p in op.get("parameters", []):
                schema = _deref(p.get("schema", {}), components)
                if p.get("description"):
                    schema["description"] = p["description"]
                props[p["name"]] = schema
                (path_params if p["in"] == "path" else query_params).append(p["name"])
                if p.get("required"):
                    required.append(p["name"])
            body_fields: List[str] = []
            body_is_object = True
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            if body:
                body_schema = _deref(body, components)
                if body_schema.get("type") == "object" and "properties" in body_schema:
                    for name, sub in body_schema["properties"].items():
                        props[name] = sub
                        body_fields.append(name)
                    required += [r for r in body_schema.get("required", []) if r not in required]
                else:
                    props["body"] = body_schema
                    body_fields = ["body"]
                    body_is_object = False
                    required.append("body")
            description = " ".join(x for x in (op.get("summary"), op.get("description")) if x) or f"{method.upper()} {path}"
            if len(description) > MAX_DESCRIPTION:
                description = description[: MAX_DESCRIPTION - 3] + "..."
            tools.append(
                ToolSpec(
                    name=op["operationId"],
                    description=description,
                    method=method.upper(),
                    path=path,
                    path_params=path_params,
                    query_params=query_params,
                    body_fields=body_fields,
                    body_is_object=body_is_object,
                    input_schema={"type": "object", "properties": props, "required": sorted(set(required))},
                    tags=tags,
                )
            )
    return tools


class Dispatcher:
    """Calls the FastAPI app in-process for a tool invocation."""

    def __init__(self, app: FastAPI, token: Optional[str] = None):
        import httpx

        self._client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://dollygrip.local")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def call(self, tool: ToolSpec, arguments: Dict[str, Any]) -> Dict[str, Any]:
        arguments = dict(arguments or {})
        path = tool.path
        for name in tool.path_params:
            if name not in arguments:
                return {"status": 400, "error": f"missing path parameter {name!r}"}
            path = path.replace("{" + name + "}", str(arguments.pop(name)))
        params = {k: arguments.pop(k) for k in tool.query_params if k in arguments and arguments[k] is not None}
        body: Any = None
        if tool.body_fields:
            body = arguments.get("body") if not tool.body_is_object else {k: v for k, v in arguments.items() if k in tool.body_fields}
        response = await self._client.request(tool.method, path, params=params, json=body, headers=self._headers)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            payload = response.json()
        elif content_type.startswith("image/"):
            payload = {"content_type": content_type, "bytes": len(response.content)}
        else:
            payload = response.text
        if response.status_code >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else payload
            return {"status": response.status_code, "error": detail}
        return payload if isinstance(payload, dict) else {"result": payload}

    async def aclose(self):
        await self._client.aclose()


def serve_stdio(app: FastAPI, include_tags=None, exclude_tags=None, token: Optional[str] = None) -> None:
    """Run the MCP server over stdio (what Claude Code / Claude Desktop spawn)."""
    try:
        import mcp.types as types
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
    except ImportError as e:  # pragma: no cover - depends on the extra being installed
        raise SystemExit(
            "The MCP server needs the optional dependency: `uv tool install 'dollygrip[mcp]'` "
            "or `uv sync --extra mcp` in a checkout."
        ) from e

    tools = build_tool_specs(app, include_tags, exclude_tags)
    by_name = {t.name: t for t in tools}
    dispatcher = Dispatcher(app, token)
    mcp_tools = [types.Tool(name=t.name, description=t.description, inputSchema=t.input_schema) for t in tools]

    async def _call(name: str, arguments: Dict[str, Any]) -> str:
        tool = by_name.get(name)
        if tool is None:
            result: Dict[str, Any] = {"status": 404, "error": f"unknown tool {name!r}"}
        else:
            result = await dispatcher.call(tool, arguments)
        return json.dumps(result, default=str)

    if hasattr(Server, "list_tools"):  # mcp 1.x: decorator registration
        server = Server("dollygrip")

        @server.list_tools()
        async def _list_tools_v1() -> List[types.Tool]:
            return mcp_tools

        @server.call_tool()
        async def _call_tool_v1(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            return [types.TextContent(type="text", text=await _call(name, arguments or {}))]

    else:  # mcp 2.x: handlers passed to the constructor, (ctx, params) signature

        async def _list_tools_v2(ctx, params):
            return types.ListToolsResult(tools=mcp_tools)

        async def _call_tool_v2(ctx, params):
            text = await _call(params.name, dict(params.arguments or {}))
            is_error = text.startswith('{"status"')
            return types.CallToolResult(content=[types.TextContent(type="text", text=text)], isError=is_error)

        server = Server(
            "dollygrip",
            instructions="Drive the running DaVinci Resolve Studio. Start with health, current_project, list_timelines, list_items.",
            on_list_tools=_list_tools_v2,
            on_call_tool=_call_tool_v2,
        )

    async def _run():
        print(f"dollygrip mcp: {len(tools)} tools over stdio", file=sys.stderr)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(_run())
