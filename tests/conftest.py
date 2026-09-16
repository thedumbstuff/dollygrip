"""Shared fixtures: every test drives the real FastAPI app against
`fake_resolve.FakeResolve`, an in-memory model of the scripting object graph."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))

from fake_resolve import FakeResolve  # noqa: E402

from dollygrip.bridge import ResolveBridge  # noqa: E402
from dollygrip.server import Settings, create_app  # noqa: E402


@pytest.fixture
def fake_resolve():
    return FakeResolve()


def make_client(fake, **settings_kwargs):
    bridge = ResolveBridge(connector=lambda: fake)
    app = create_app(Settings(**settings_kwargs), bridge=bridge)
    return TestClient(app)


@pytest.fixture
def client(fake_resolve):
    return make_client(fake_resolve)


@pytest.fixture
def project(fake_resolve):
    return fake_resolve.pm.current


@pytest.fixture
def timeline(project):
    return project.current_timeline


def item_ids(client, track_type=None):
    """Helper: ids of the current timeline's items (optionally one track type)."""
    r = client.get("/api/v1/timelines/current/items", params={"track_type": track_type} if track_type else None)
    assert r.status_code == 200, r.text
    return [i["id"] for i in r.json()["items"]]
