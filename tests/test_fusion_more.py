import json
import zipfile

from conftest import make_client

from dollygrip import fusion_templates

V1 = "/api/v1"
F = f"{V1}/fusion"


def _title(client):
    r = client.post(f"{V1}/timelines/current/generators", json={"kind": "fusion_title", "name": "Text+"})
    return r.json()["item_id"]


def _fake_comp(timeline):
    return [it for it in timeline._all_items() if it.GetName() == "Text+"][0].comps[0]


def _template_root(tmp_path):
    """A template root with loose .setting files AND a .drfx bundle, like a real install."""
    base = tmp_path / "Templates" / "Edit"
    (base / "Titles" / "Lower Thirds").mkdir(parents=True)
    (base / "Titles" / "Text+.setting").write_text(json.dumps({"Tools": {"Text1": {"__ctor": "TextPlus", "Inputs": {"StyledText": "Title"}}}}))
    (base / "Titles" / "Lower Thirds" / "Clean Bar.setting").write_text("{}")
    (base / "Generators").mkdir()
    (base / "Generators" / "Solid Color.setting").write_text("{}")
    with zipfile.ZipFile(tmp_path / "Templates" / "Templates.drfx", "w") as z:
        z.writestr("Edit/Titles/Fade On.setting", json.dumps({"Tools": {"FadeOn": {"__ctor": "GroupOperator"}, "Text1": {"__ctor": "TextPlus", "Inputs": {"StyledText": "Fade"}}}}))
        z.writestr("Edit/Transitions/Cross Dissolve.setting", "{}")
        z.writestr("Fusion/Particles/Snow.setting", json.dumps({"Tools": {"pEmitter1": {"__ctor": "pEmitter"}}}))
        z.writestr("Fusion/Particles/Snow.png", "not a setting")
        z.writestr("__MACOSX/Edit/Titles/._Fade On.setting", "junk")
    return tmp_path / "Templates"


def test_templates_scan_loose_and_bundled(tmp_path, monkeypatch):
    root = _template_root(tmp_path)
    env = {"DOLLYGRIP_FUSION_TEMPLATE_DIRS": str(root)}
    items = fusion_templates.list_templates(env=env)
    assert {(i["kind"], i["name"], i["category"]) for i in items} == {
        ("titles", "Text+", ""),
        ("titles", "Clean Bar", "Lower Thirds"),
        ("generators", "Solid Color", ""),
        ("titles", "Fade On", ""),
        ("transitions", "Cross Dissolve", ""),
        ("fusion", "Snow", "Particles"),
    }
    snow = fusion_templates.find_template("fusion/Particles/Snow", env=env)
    assert snow["bundle"].endswith("Templates.drfx")
    extracted = fusion_templates.extract(snow, cache_dir=tmp_path / "cache")
    assert json.load(open(extracted))["Tools"]["pEmitter1"]["__ctor"] == "pEmitter"
    assert fusion_templates.find_template("fade on", env=env)["kind"] == "titles"
    assert fusion_templates.find_template("titles/Snow", env=env) is None
    monkeypatch.setenv("DOLLYGRIP_FUSION_TEMPLATE_DIRS", str(root))
    from fake_resolve import FakeResolve

    client = make_client(FakeResolve())
    r = client.get(f"{F}/templates", params={"kind": "titles"}).json()
    assert r["count"] == 3 and r["by_kind"] == {"titles": 3}
    assert client.get(f"{F}/templates", params={"contains": "particles"}).json()["templates"][0]["name"] == "Snow"
    assert client.get(f"{F}/templates", params={"kind": "nope"}).status_code == 404


def test_fonts(client):
    r = client.get(f"{F}/fonts")
    assert r.status_code == 200 and "Segoe UI Symbol" in r.json()["fonts"]
    assert client.get(f"{F}/fonts", params={"contains": "comic"}).json()["fonts"] == ["Comic Sans MS"]


def test_comp_attrs_undo_save(client, timeline):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    first = client.get(f"{comp}/attrs").json()
    assert first["render_end"] == 149 and first["loaded"] is False
    r = client.patch(f"{comp}/attrs", json={"current_time": 40, "render_end": 300, "global_end": 400, "hiq": False, "raw": {"COMPB_MotionBlur": True}})
    assert r.status_code == 200 and r.json()["now"]["COMPN_RenderEnd"] == 300 and r.json()["now"]["COMPN_GlobalEnd"] == 400
    assert client.get(f"{comp}/attrs").json()["current_time"] == 40
    assert client.patch(f"{comp}/attrs", json={}).status_code == 422
    assert client.post(f"{comp}/undo", json={"action": "start", "name": "batch"}).json()["ok"]
    assert client.post(f"{comp}/undo", json={"action": "end"}).json()["ok"]
    fake_comp = _fake_comp(timeline)
    assert fake_comp.undo == [("start", "batch"), ("end", True)]
    assert client.post(f"{comp}/save", json={"path": "D:/c.comp"}).json()["ok"] and fake_comp.saved_to == "D:/c.comp"


def test_graph_lists_edges_and_positions(client, timeline):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    client.post(f"{comp}/tools", json={"tool_id": "Background", "name": "BG"})
    client.post(f"{comp}/tools", json={"tool_id": "Merge", "name": "M1"})
    client.post(f"{comp}/tools/M1/connect", json={"input": "Background", "source_tool": "BG"})
    client.post(f"{comp}/tools/M1/connect", json={"input": "Foreground", "source_tool": "Template"})
    assert client.patch(f"{comp}/tools/M1", json={"position": [3, 1.5]}).status_code == 200  # auto-loads the comp
    assert _fake_comp(timeline).CurrentFrame is not None
    g = client.get(f"{comp}/graph").json()
    names = {n["name"] for n in g["nodes"]}
    assert {"MediaIn1", "MediaOut1", "Template", "BG", "M1"} <= names
    assert next(n for n in g["nodes"] if n["name"] == "M1")["position"] == [3, 1.5]
    assert next(n for n in g["nodes"] if n["name"] == "BG")["position"] is None
    assert g["outputs"] == ["MediaOut1"]


def test_patch_tool_lock_color_and_type_filter(client, timeline):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    r = client.patch(f"{comp}/tools/Template", json={"locked": True, "tile_color": [1, 0.5, 0]})
    assert r.status_code == 200
    fake_comp = _fake_comp(timeline)
    assert fake_comp.tools["Template"].locked is True and fake_comp.tools["Template"].TileColor == {"R": 1, "G": 0.5, "B": 0}
    assert client.patch(f"{comp}/tools/Template", json={"tile_color": []}).status_code == 200 and fake_comp.tools["Template"].TileColor is None
    assert [t["name"] for t in client.get(f"{comp}/tools", params={"type": "TextPlus"}).json()["tools"]] == ["Template"]


def test_paste_template_with_overrides(client, timeline, tmp_path, monkeypatch):
    monkeypatch.setenv("DOLLYGRIP_FUSION_TEMPLATE_DIRS", str(_template_root(tmp_path)))
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    r = client.post(f"{comp}/paste", json={"template": "titles/Fade On", "inputs": {"TextPlus2": {"StyledText": "Ada Lovelace"}}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert sorted(t["id"] for t in body["tools"]) == ["GroupOperator", "TextPlus"]
    assert body["overrides"] == {"TextPlus2": {"StyledText": True}}
    assert body["source"].endswith("Fade On.setting")
    assert client.get(f"{comp}/tools/TextPlus2").json()["inputs"]["StyledText"] == "Ada Lovelace"
    assert _fake_comp(timeline).CurrentFrame is not None  # paste loaded the comp
    assert client.post(f"{comp}/paste", json={"template": "titles/Nope"}).status_code == 404
    assert client.post(f"{comp}/paste", json={}).status_code == 422
    # a file that is not a settings table -> Fusion's own error surfaces as 422
    bad = client.post(f"{comp}/paste", json={"template": "titles/Clean Bar"})
    assert bad.status_code == 422 and "readfile" in bad.json()["detail"]


def test_paste_path_and_text(client, tmp_path):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    f = tmp_path / "glow.setting"
    f.write_text(json.dumps({"Tools": {"Glow": {"__ctor": "Background", "Inputs": {"TopLeftBlue": 1}}}}))
    r = client.post(f"{comp}/paste", json={"path": str(f)})
    assert r.status_code == 200 and r.json()["tools"][0]["id"] == "Background"
    assert client.post(f"{comp}/paste", json={"path": str(tmp_path / "missing.setting")}).status_code == 404
    r = client.post(f"{comp}/paste", json={"settings_text": json.dumps({"Tools": {"T": {"__ctor": "Transform"}}}), "detail": True})
    assert r.status_code == 200 and r.json()["tools"][0]["id"] == "Transform" and "inputs" in r.json()["tools"][0]


def test_duplicate_and_presets(client, timeline, tmp_path):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    client.patch(f"{comp}/tools/Template/inputs", json={"inputs": {"StyledText": "One", "Size": 0.2}})
    client.post(f"{comp}/tools/Template/keyframes", json={"input": "Size", "keyframes": [{"frame": 0, "value": 0.0}, {"frame": 10, "value": 0.2}]})
    r = client.post(f"{comp}/tools/Template/duplicate", json={"name": "Two", "inputs": {"StyledText": "Two"}})
    assert r.status_code == 200, r.text
    assert r.json()["tool"]["name"] == "Two" and r.json()["tool"]["inputs"]["StyledText"] == "Two" and r.json()["also_created"] == []
    fake_comp = _fake_comp(timeline)
    assert fake_comp.tools["Two"].keyframes["Size"] == {0: 0.0, 10: 0.2}  # animation travels with the copy
    assert client.post(f"{comp}/tools/Nope/duplicate", json={}).status_code == 404
    preset = tmp_path / "title.setting"
    client.patch(f"{comp}/tools/Template/inputs", json={"inputs": {"Size": 0.2}})
    assert client.post(f"{comp}/tools/Template/settings/save", json={"path": str(preset)}).json()["ok"]
    client.patch(f"{comp}/tools/Two/inputs", json={"inputs": {"Size": 0.9}})
    preset.write_text("{}")  # the fake serves the in-memory table for a path it saved; the file must merely exist
    assert client.post(f"{comp}/tools/Two/settings/load", json={"path": str(preset)}).json()["tool"]["inputs"]["Size"] == 0.2
    assert client.post(f"{comp}/tools/Two/settings/load", json={"path": str(tmp_path / "nope.setting")}).status_code == 404


def test_keyframes_read_and_clear(client, timeline):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    r = client.get(f"{comp}/tools/Template/keyframes", params={"input": "Size"}).json()
    assert r["animated"] is False and r["value"] == 0.08 and r["keyframes"] == {}
    client.post(f"{comp}/tools/Template/keyframes", json={"input": "Size", "keyframes": [{"frame": 0, "value": 0.05}, {"frame": 24, "value": 0.12}]})
    r = client.get(f"{comp}/tools/Template/keyframes", params={"input": "Size"}).json()
    assert r["animated"] is True and r["keyframes"] == {"0": 0.05, "24": 0.12} and r["modifier"] == "BezierSpline"
    r = client.delete(f"{comp}/tools/Template/keyframes", params={"input": "Size", "value": 0.3}).json()
    assert r["was_animated"] is True and r["value"] == 0.3
    assert client.get(f"{comp}/tools/Template/keyframes", params={"input": "Size"}).json()["animated"] is False
    assert client.delete(f"{comp}/tools/Template/keyframes", params={"input": "Size"}).json()["was_animated"] is False


def test_modifiers(client, timeline):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    r = client.post(f"{comp}/tools/Template/modifier", json={"input": "Center", "modifier": "Shake", "inputs": {"Smoothness": 0.5, "XMinimum": 0.4}})
    assert r.status_code == 200, r.text
    assert r.json()["modifier"]["id"] == "Shake" and r.json()["inputs_set"] == {"Smoothness": True, "XMinimum": True}
    fake_comp = _fake_comp(timeline)
    assert fake_comp.tools["Template"].splines["Center"].kind == "Shake"
    kf = client.get(f"{comp}/tools/Template/keyframes", params={"input": "Center"}).json()
    assert kf["animated"] is False and kf["modifier"] == "Shake"
    # a modifier-driven input is never evaluated with GetInput (deadlocks Resolve) - reported as driven_by
    detail = client.get(f"{comp}/tools/Template").json()["inputs"]["Center"]
    assert detail == {"driven_by": "Shake1", "driver": "Shake"}
    rows = client.get(f"{comp}/tools/Template/inputs").json()["inputs"]
    center = next(r for r in rows if r.get("id") == "Center")
    assert center["driven_by"] == "Shake1" and "value" not in center
    assert client.post(f"{comp}/tools/Template/modifier", json={"input": "Center", "modifier": "Perturb"}).status_code == 422  # no constructor on Resolve 21
    fake_comp.Shake = None
    assert client.post(f"{comp}/tools/Template/modifier", json={"input": "Size", "modifier": "Shake"}).status_code == 422


def test_text_plus_style_extras(client, timeline):
    iid = _title(client)
    r = client.post(f"{F}/items/{iid}/text-plus", json={"text": "Hi", "shadow": True, "outline": [0, 0, 0], "outline_thickness": 0.02, "tracking": 1.1, "line_spacing": 0.9})
    assert r.status_code == 200
    inputs = _fake_comp(timeline).tools["Template"].inputs
    assert inputs["Enabled3"] == 1 and inputs["Enabled2"] == 1 and inputs["Thickness2"] == 0.02 and inputs["CharacterSpacing"] == 1.1 and inputs["LineSpacing"] == 0.9
