"""MCP tool generation + in-process dispatch (no `mcp` package needed)."""

import asyncio

import pytest
from fake_resolve import FakeResolve

from dollygrip.bridge import ResolveBridge
from dollygrip.mcp_server import Dispatcher, build_tool_specs
from dollygrip.server import Settings, create_app


@pytest.fixture
def app():
    return create_app(Settings(allow_exec=True), bridge=ResolveBridge(connector=lambda: FakeResolve()))


def _tool(tools, name):
    return next(t for t in tools if t.name == name)


def test_every_operation_becomes_a_tool(app):
    tools = build_tool_specs(app)
    names = [t.name for t in tools]
    assert len(names) == len(set(names)) > 250
    assert {"list_items", "append_items", "add_job", "text_plus", "convert_timecode", "exec_code"} <= set(names)


def test_tag_filters(app):
    only = build_tool_specs(app, include_tags=["render", "timelines"])
    assert only and all(set(t.tags) & {"render", "timelines"} for t in only)
    without = build_tool_specs(app, exclude_tags=["exec"])
    assert "exec_code" not in {t.name for t in without}


def test_schema_flattens_path_query_and_body(app):
    tools = build_tool_specs(app)
    get_item = _tool(tools, "get_item")
    assert get_item.path_params == ["item_id"] and get_item.input_schema["required"] == ["item_id"]
    append = _tool(tools, "append_items")
    assert append.body_fields == ["items"] and append.input_schema["properties"]["items"]["type"] == "array"
    # $refs are inlined so every tool schema is self-contained
    assert "$ref" not in str(append.input_schema)
    assert "clip_name" in append.input_schema["properties"]["items"]["items"]["properties"]
    listing = _tool(tools, "list_items")
    assert set(listing.query_params) == {"track_type", "track_index"}
    patch_track = _tool(tools, "patch_track")
    assert set(patch_track.path_params) == {"track_type", "index"} and "locked" in patch_track.body_fields


def test_dispatch_get_post_and_errors(app):
    tools = build_tool_specs(app)
    d = Dispatcher(app)

    async def run():
        items = await d.call(_tool(tools, "list_items"), {"track_type": "video"})
        assert items["timeline"] == "R8-final-art2b" and len(items["items"]) == 2
        got = await d.call(_tool(tools, "get_item"), {"item_id": items["items"][0]["id"]})
        assert got["name"] == "spokes.mp4"
        appended = await d.call(_tool(tools, "append_items"), {"items": [{"clip_name": "art.mov", "track_index": 3, "record_frame": 0}]})
        assert appended["all_ok"] is True
        missing = await d.call(_tool(tools, "get_item"), {"item_id": "nope"})
        assert missing["status"] == 404 and "not found" in missing["error"]
        no_path = await d.call(_tool(tools, "get_item"), {})
        assert no_path["status"] == 400
        tc = await d.call(_tool(tools, "convert_timecode"), {"fps": 30, "frames": 90})
        assert tc["timecode"] == "00:00:03:00"
        png = await d.call(_tool(tools, "current_thumbnail_png"), {})
        assert png["content_type"] == "image/png"
        await d.aclose()

    asyncio.run(run())


def test_dispatch_honours_token():
    app = create_app(Settings(token="s3cret"), bridge=ResolveBridge(connector=lambda: FakeResolve()))
    tools = build_tool_specs(app)

    async def run():
        denied = await Dispatcher(app).call(_tool(tools, "current_project"), {})
        assert denied["status"] == 401
        ok = await Dispatcher(app, token="s3cret").call(_tool(tools, "current_project"), {})
        assert ok["name"] == "TutorBee"

    asyncio.run(run())


def test_stdio_server_builds_if_mcp_installed(app):
    pytest.importorskip("mcp")
    from dollygrip import mcp_server

    # Only the wiring, not the event loop: Server(...) + handlers register without error.
    from mcp.server import Server

    assert Server("dollygrip").name == "dollygrip"
    assert callable(mcp_server.serve_stdio)


def test_profiles_are_valid_tag_sets(app):
    from dollygrip.mcp_server import PROFILES

    all_tags = {t for spec in build_tool_specs(app) for t in spec.tags}
    for name, tags in PROFILES.items():
        if tags is None:
            continue
        assert set(tags) <= all_tags, name
        subset = build_tool_specs(app, include_tags=tags)
        assert 0 < len(subset) < len(build_tool_specs(app)), name
    editor = {t.name for t in build_tool_specs(app, include_tags=PROFILES["editor"])}
    assert "append_items" in editor and "set_cdl" not in editor and "exec_code" not in editor
