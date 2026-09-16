from conftest import make_client

from dollygrip.recipes import RecipeError, render

V1 = "/api/v1"


def test_render_templates():
    ctx = {"steps": {"a": {"results": [{"item_id": "ti-9"}], "n": 3}}, "last": {"x": 1}}
    assert render("{{ steps.a.results[0].item_id }}", ctx) == "ti-9"
    assert render("id={{steps.a.results[0].item_id}}!", ctx) == "id=ti-9!"
    assert render({"k": ["{{ steps.a.n }}", 2]}, ctx) == {"k": [3, 2]}
    assert render("{{ last.x }}", ctx) == 1
    for bad in ("{{ steps.zzz }}", "{{ steps.a.results[5] }}", "{{ steps.a.results[0].nope }}"):
        try:
            render(bad, ctx)
        except RecipeError:
            continue
        raise AssertionError(bad)


def test_recipe_runs_pipeline_with_templates(client, project):
    recipe = {
        "steps": [
            {"name": "bin", "op": "set_current_folder", "args": {"path": "R3-auto"}},
            {"name": "tl", "op": "create_timeline", "args": {"name": "recipe-tl", "fps": 30, "extra_video_tracks": 1}},
            {"name": "cut", "op": "append_items", "args": {"items": [{"clip_name": "spokes.mp4", "record_frame": 0}, {"clip_name": "art.mov", "track_index": 2, "record_frame": 15}]}},
            {"name": "look", "op": "patch_item", "args": {"item_id": "{{ steps.cut.results[1].item_id }}", "properties": {"Opacity": 50}}},
            {"name": "title", "op": "insert_generator", "args": {"kind": "fusion_title", "name": "Text+", "text": "From a recipe"}},
            {"name": "render", "op": "add_job", "args": {"format": "mp4", "codec": "H264", "settings": {"CustomName": "recipe"}}},
            {"name": "wait", "op": "wait_for_job", "args": {"job_id": "{{ steps.render.job_id }}", "timeout": 5, "poll": 0.2}},
        ]
    }
    r = client.post(f"{V1}/recipes/run", json=recipe)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and [s["status"] for s in body["steps"]] == ["ok"] * 7
    assert body["steps"][3]["args"]["item_id"].startswith("ti-")
    assert body["steps"][6]["result"]["JobStatus"] == "Complete"
    tl = project.current_timeline
    assert tl.GetName() == "recipe-tl" and tl.tracks["video"][1]["items"][0].props["Opacity"] == 50


def test_recipe_dry_run_and_errors(client):
    r = client.post(f"{V1}/recipes/run", json={"dry_run": True, "steps": [{"op": "create_timeline", "args": {"name": "x"}}, {"op": "nope"}]})
    body = r.json()
    assert body["dry_run"] and body["steps"][0]["status"] == "planned" and body["steps"][1]["status"] == "error"
    r = client.post(f"{V1}/recipes/run", json={"steps": [
        {"name": "a", "op": "get_item", "args": {"item_id": "ghost"}},
        {"name": "b", "op": "list_items"},
    ]})
    body = r.json()
    assert body["ok"] is False and body["steps"][0]["status"] == "error" and body["steps"][0]["http_status"] == 404
    assert body["steps"][1]["status"] == "skipped"
    r = client.post(f"{V1}/recipes/run", json={"stop_on_error": False, "steps": [
        {"name": "a", "op": "get_item", "args": {"item_id": "ghost"}},
        {"name": "b", "op": "list_items"},
    ]})
    assert [s["status"] for s in r.json()["steps"]] == ["error", "ok"]
    r = client.post(f"{V1}/recipes/run", json={"steps": [{"name": "t", "op": "list_items", "args": {"track_type": "{{ steps.missing.x }}"}}]})
    assert r.json()["steps"][0]["status"] == "error" and "template" in r.json()["steps"][0]["error"]


def test_recipe_forwards_token(fake_resolve):
    client = make_client(fake_resolve, token="s3cret")
    recipe = {"steps": [{"op": "current_project"}]}
    assert client.post(f"{V1}/recipes/run", json=recipe).status_code == 401
    r = client.post(f"{V1}/recipes/run", json=recipe, headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200 and r.json()["steps"][0]["result"]["name"] == "TutorBee"


def test_recipe_operations_listing(client):
    ops = {o["op"]: o for o in client.get(f"{V1}/recipes/operations").json()["operations"]}
    assert "append_items" in ops and "items" in ops["append_items"]["args"]
    assert ops["get_item"]["required"] == ["item_id"]
