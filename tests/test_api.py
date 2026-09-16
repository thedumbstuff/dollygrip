from conftest import make_client


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["resolve"] == "connected"
    assert "fake" in body["product"]


def test_health_disconnected():
    def failing_connector():
        raise ConnectionError("Resolve is not running")

    from dollygrip.bridge import ResolveBridge
    from dollygrip.server import Settings, create_app
    from fastapi.testclient import TestClient

    app = create_app(Settings(), bridge=ResolveBridge(connector=failing_connector))
    r = TestClient(app).get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["resolve"] == "disconnected"


def test_resolve_down_gives_503():
    def failing_connector():
        raise ConnectionError("nope")

    from dollygrip.bridge import ResolveBridge
    from dollygrip.server import Settings, create_app
    from fastapi.testclient import TestClient

    app = create_app(Settings(), bridge=ResolveBridge(connector=failing_connector))
    r = TestClient(app).get("/api/v1/projects/current")
    assert r.status_code == 503


def test_current_project(client):
    r = client.get("/api/v1/projects/current")
    assert r.status_code == 200
    assert r.json()["name"] == "TutorBee"
    assert r.json()["frame_rate"] == "30"


def test_unknown_project_404(client):
    r = client.post("/api/v1/projects/current", json={"name": "NoSuch"})
    assert r.status_code == 404


def test_mediapool_navigation_and_clips(client):
    r = client.post("/api/v1/mediapool/folders", json={"path": "R3-auto"})
    assert r.status_code == 200 and r.json()["current"] == "R3-auto"
    r = client.get("/api/v1/mediapool/clips")
    names = [c["name"] for c in r.json()["clips"]]
    assert "spokes.mp4" in names


def test_mediapool_missing_folder_404_and_create(client):
    assert client.post("/api/v1/mediapool/folders", json={"path": "nope"}).status_code == 404
    r = client.post("/api/v1/mediapool/folders", json={"path": "nope", "create": True})
    assert r.status_code == 200 and r.json()["current"] == "nope"


def test_create_timeline_with_custom_settings(fake_resolve):
    client = make_client(fake_resolve)
    r = client.post(
        "/api/v1/timelines",
        json={"name": "vertical", "width": 1080, "height": 1920, "fps": 30, "extra_video_tracks": 2},
    )
    assert r.status_code == 200
    tl = fake_resolve.pm.current.current_timeline
    assert tl.settings["useCustomSettings"] == "1"
    assert tl.settings["timelineResolutionHeight"] == "1920"
    assert tl.settings["timelineFrameRate"] == "30"
    assert tl.tracks["video"] == 3


def test_duplicate_timeline_404(client):
    assert client.post("/api/v1/timelines", json={"name": "R8-final-art2b"}).status_code == 404


def test_append_adds_start_offset(fake_resolve):
    client = make_client(fake_resolve)
    client.post("/api/v1/mediapool/folders", json={"path": "R3-auto"})
    r = client.post(
        "/api/v1/timelines/current/append",
        json={"items": [{"clip_name": "spokes.mp4", "start_frame": 0, "end_frame": 432, "record_frame": 0},
                        {"clip_name": "art.mov", "track_index": 2, "record_frame": 10, "media_type": "audio"}]},
    )
    assert r.status_code == 200 and r.json()["all_ok"]
    appended = fake_resolve.pm.current.pool.appended
    assert appended[0]["recordFrame"] == 108000  # timeline start added for the caller
    assert appended[1]["recordFrame"] == 108010
    assert appended[1]["mediaType"] == 2


def test_append_unknown_clip_404(client):
    client.post("/api/v1/mediapool/folders", json={"path": "R3-auto"})
    r = client.post("/api/v1/timelines/current/append", json={"items": [{"clip_name": "ghost.mov"}]})
    assert r.status_code == 404


def test_render_roundtrip(client):
    r = client.post(
        "/api/v1/render/jobs",
        json={"format": "mp4", "codec": "H264", "settings": {"CustomName": "out"}, "start": True},
    )
    assert r.status_code == 200
    job = r.json()
    assert job["started"] is True
    status = client.get(f"/api/v1/render/jobs/{job['job_id']}").json()
    assert status["JobStatus"] == "Complete"


def test_render_bad_codec_404(client):
    r = client.post("/api/v1/render/jobs", json={"format": "mp4", "codec": "NOPE"})
    assert r.status_code == 404


def test_exec_disabled_by_default(client):
    assert client.post("/api/v1/exec", json={"code": "result = 1"}).status_code == 403


def test_exec_enabled(fake_resolve):
    client = make_client(fake_resolve, allow_exec=True)
    r = client.post("/api/v1/exec", json={"code": "print('hi'); result = project.GetName()"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["result"] == "TutorBee" and body["stdout"] == "hi\n"


def test_exec_error_is_reported_not_500(fake_resolve):
    client = make_client(fake_resolve, allow_exec=True)
    r = client.post("/api/v1/exec", json={"code": "raise ValueError('boom')"})
    assert r.status_code == 200 and r.json()["ok"] is False and "boom" in r.json()["error"]


def test_token_auth(fake_resolve):
    client = make_client(fake_resolve, token="s3cret")
    assert client.get("/api/v1/projects/current").status_code == 401
    assert client.get("/api/v1/health").status_code == 200  # health stays open
    ok = client.get("/api/v1/projects/current", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_page_switch(client):
    r = client.post("/api/v1/system/page", json={"page": "deliver"})
    assert r.status_code == 200 and r.json()["ok"]
    bad = client.post("/api/v1/system/page", json={"page": "kitchen"})
    assert bad.status_code == 422
