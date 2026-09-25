"""Every recipe in recipes/ (and the JSON recipes in examples/) must dry-run
clean: each op exists in the OpenAPI catalogue, every argument name is valid,
required arguments are present and every template resolves."""

import json
from pathlib import Path

import pytest

from dollygrip import cli

V1 = "/api/v1"
ROOT = Path(__file__).resolve().parent.parent
LIBRARY = sorted((ROOT / "recipes").glob("*.json"))
EXAMPLES = sorted((ROOT / "examples").glob("recipe_*.json"))


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)


def test_library_has_the_four_recipes():
    assert {p.stem for p in LIBRARY} >= {"vertical_reel", "podcast_clip", "dailies_burnin", "music_video_overlay"}


@pytest.mark.parametrize("path", LIBRARY + EXAMPLES, ids=lambda p: p.name)
def test_recipe_dry_runs_clean(client, path):
    recipe = json.loads(path.read_text(encoding="utf-8"))
    ops = {o["op"] for o in client.get(f"{V1}/recipes/operations").json()["operations"]}
    for step in recipe["steps"]:
        assert step["op"] in ops, f"{path.name}: unknown op {step['op']!r}"
    if path.parent.name == "recipes":
        assert recipe.get("description") and isinstance(recipe.get("inputs"), dict) and recipe["inputs"]

    r = client.post(f"{V1}/recipes/run", json={**recipe, "dry_run": True})
    assert r.status_code == 200, r.text
    body = r.json()
    bad = [(s["name"], s.get("error")) for s in body["steps"] if s["status"] != "planned"]
    assert body["ok"] is True and not bad, f"{path.name}: {bad}"
    for step in body["steps"]:
        for text in _strings(step["args"]):
            assert "{{" not in text and "}}" not in text, f"{path.name}/{step['name']}: unresolved {text!r}"
            assert "<inputs." not in text


def test_inputs_resolve_to_real_values_and_step_refs_to_placeholders(client):
    recipe = json.loads((ROOT / "recipes" / "vertical_reel.json").read_text(encoding="utf-8"))
    body = client.post(f"{V1}/recipes/run", json={**recipe, "dry_run": True}).json()
    steps = {s["name"]: s for s in body["steps"]}
    assert steps["import"]["args"]["paths"] == recipe["inputs"]["clip_paths"]
    assert steps["cut"]["args"]["items"] == recipe["inputs"]["clips"]
    assert steps["style"]["args"]["item_id"] == "<steps.title.item_id>"
    assert steps["wait"]["args"]["job_id"] == "<steps.render.job_id>"


def test_dry_run_rejects_bad_args_and_unknown_step_refs(client):
    r = client.post(f"{V1}/recipes/run", json={"dry_run": True, "stop_on_error": False, "steps": [
        {"name": "a", "op": "create_timeline", "args": {"name": "x", "widht": 1080}},
        {"name": "b", "op": "wait_for_job", "args": {"timeout": 5}},
        {"name": "c", "op": "get_item", "args": {"item_id": "{{ steps.nope.item_id }}"}},
        {"name": "d", "op": "get_item", "args": {"item_id": "{{ inputs.missing }}"}},
    ]})
    steps = r.json()["steps"]
    assert [s["status"] for s in steps] == ["error"] * 4
    assert "widht" in steps[0]["error"] and "job_id" in steps[1]["error"]


def test_cli_dry_run_is_offline_and_takes_input_overrides(capsys):
    path = ROOT / "recipes" / "podcast_clip.json"
    assert cli.main(["run", str(path), "--dry-run", "--input", "source_in=100", "--input", "guest_name=Sam"]) == 0
    out = capsys.readouterr().out
    report = json.loads(out[out.index("{"):])
    cut = next(s for s in report["steps"] if s["name"] == "cut")
    assert cut["args"]["items"][0]["start_frame"] == 100
    lower = next(s for s in report["steps"] if s["name"] == "lower_third")
    assert lower["args"]["text"].startswith("Sam\n")
    assert cli.main(["run", str(path), "--dry-run", "--input", "no-equals-sign"]) == 2
