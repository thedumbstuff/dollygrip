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


def make_client(fake, stock=None, **settings_kwargs):
    bridge = ResolveBridge(connector=lambda: fake)
    app = create_app(Settings(**settings_kwargs), bridge=bridge, stock_client=stock)
    return TestClient(app)


CANNED_PEXELS = {
    "videos": [
        {"id": 101, "width": 1080, "height": 1920, "duration": 12, "url": "https://pexels.com/v/101", "user": {"name": "Ann"},
         "video_files": [{"id": 1, "file_type": "video/mp4", "width": 1080, "height": 1920, "fps": 24, "link": "https://cdn/101.mp4"}]},
        {"id": 102, "width": 1080, "height": 1920, "duration": 6, "url": "https://pexels.com/v/102", "user": {"name": "Bo"},
         "video_files": [{"id": 2, "file_type": "video/mp4", "width": 1080, "height": 1920, "fps": 24, "link": "https://cdn/102.mp4"}]},
    ]
}


def make_stock(media_dir, calls=None):
    """A StockClient with canned Pexels answers and downloads that write tiny files."""
    from dollygrip.stock import StockClient

    calls = calls if calls is not None else []

    def fetch(url, params, headers):
        calls.append((url, params))
        return CANNED_PEXELS if "pexels" in url else {"hits": []}

    def download(url, dest):
        dest.write_bytes(b"\x00" * 8)

    return StockClient(media_dir=media_dir, keys={"pexels": ["k"], "pixabay": [], "coverr": []}, fetch=fetch, download=download)


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


@pytest.fixture(autouse=True)
def _no_fusion_settle(monkeypatch, tmp_path):
    """The fake comp is ready instantly; skip the real-Resolve settle sleep.
    Template extraction goes to a per-test folder, never the machine's real
    cache (a test once poisoned it with fake JSON and live pastes went silent)."""
    from dollygrip.routers import fusion_more

    monkeypatch.setattr(fusion_more, "SETTLE_SECONDS", 0)
    monkeypatch.setenv("DOLLYGRIP_TEMPLATE_CACHE", str(tmp_path / "template-cache"))
