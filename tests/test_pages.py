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
