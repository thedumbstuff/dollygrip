from conftest import make_client


def test_home_page(client):
    r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "Watchtower" in r.text and "/api/v1/health" in r.text and "disabled" in r.text


def test_watchtower_renders_markdown(client):
    r = client.get("/watchtower")
    assert r.status_code == 200
    assert "<h1" in r.text and "DollyGrip Watchtower" in r.text and "<table>" in r.text  # tables extension on


def test_doc_pages_and_404(client):
    for name in ("craft", "gotchas", "roadmap", "readme"):
        assert client.get(f"/pages/{name}").status_code == 200, name
    assert client.get("/pages/nope").status_code == 404


def test_pages_stay_open_with_token(fake_resolve):
    client = make_client(fake_resolve, token="s3cret")
    assert client.get("/").status_code == 200
    assert client.get("/watchtower").status_code == 200
    assert client.get("/pages/gotchas").status_code == 200
    assert client.get("/api/v1/projects/current").status_code == 401  # the API itself is still guarded


def test_pages_not_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/watchtower" not in paths and "/" not in paths


def test_home_has_render_queue_panel(client):
    t = client.get("/").text
    assert 'id="render-queue"' in t and 'id="rq-body"' in t and "Render queue" in t
    # the panel's poller, SSE follower, hidden-tab pause and ?token= hand-off
    assert "/api/v1/render/jobs" in t and "/events?poll=1" in t and "setInterval(tick,3000)" in t
    assert "visibilitychange" in t and "get('token')" in t and "Bearer " in t


def test_render_panel_endpoints_against_fake(fake_resolve, project, timeline):
    client = make_client(fake_resolve)
    job = client.post("/api/v1/render/jobs", json={"start": False}).json()["job_id"]
    listed = client.get("/api/v1/render/jobs").json()
    assert [j["JobId"] for j in listed["jobs"]] == [job] and listed["rendering"] is False
    status = client.get(f"/api/v1/render/jobs/{job}").json()
    assert status["JobStatus"] == "Ready" and status["CompletionPercentage"] == 0
    # the panel follows a rendering job over SSE
    project.jobs[job] = {"JobStatus": "Complete", "CompletionPercentage": 100}
    with client.stream("GET", f"/api/v1/render/jobs/{job}/events?poll=1") as r:
        body = "".join(r.iter_text())
    assert r.headers["content-type"].startswith("text/event-stream") and "event: done" in body and '"CompletionPercentage": 100' in body
    assert client.get("/api/v1/render/jobs/nope").status_code == 404


def test_render_panel_reasons_when_nothing_open_or_token(fake_resolve):
    # no project open -> 409 with a detail the panel shows
    fake_resolve.pm.current = None
    client = make_client(fake_resolve)
    r = client.get("/api/v1/render/jobs")
    assert r.status_code == 409 and r.json()["detail"]
    # Resolve unreachable -> 503
    from dollygrip.bridge import ResolveBridge
    from dollygrip.server import Settings, create_app
    from fastapi.testclient import TestClient

    down = TestClient(create_app(Settings(), bridge=ResolveBridge(connector=lambda: None)))
    r = down.get("/api/v1/render/jobs")
    assert r.status_code == 503 and r.json()["detail"]
    # with a token the page stays open and the header the panel forwards is accepted
    guarded = make_client(fake_resolve, token="s3cret")
    assert guarded.get("/?token=s3cret").status_code == 200
    assert guarded.get("/api/v1/render/jobs").status_code == 401
    assert guarded.get("/api/v1/render/jobs", headers={"Authorization": "Bearer s3cret"}).status_code == 409
