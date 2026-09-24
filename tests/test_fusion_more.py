import json

from conftest import item_ids, make_client

from dollygrip import fusion_templates

V1 = "/api/v1"
F = f"{V1}/fusion"


def _title(client):
    r = client.post(f"{V1}/timelines/current/generators", json={"kind": "fusion_title", "name": "Text+"})
    return r.json()["item_id"]


def test_templates_scan(tmp_path, monkeypatch):
    base = tmp_path / "Templates" / "Edit"
    (base / "Titles" / "Lower Thirds").mkdir(parents=True)
    (base / "Titles" / "Text+.setting").write_text("{}")
    (base / "Titles" / "Lower Thirds" / "Clean Bar.setting").write_text("{}")
    (base / "Generators").mkdir()
    (base / "Generators" / "Solid Color.setting").write_text("{}")
    env = {"DOLLYGRIP_FUSION_TEMPLATE_DIRS": str(tmp_path / "Templates")}
    items = fusion_templates.list_templates(env=env)
    assert {(i["kind"], i["name"], i["category"]) for i in items} == {("titles", "Text+", ""), ("titles", "Clean Bar", "Lower Thirds"), ("generators", "Solid Color", "")}
    monkeypatch.setenv("DOLLYGRIP_FUSION_TEMPLATE_DIRS", str(tmp_path / "Templates"))
    from fake_resolve import FakeResolve

    client = make_client(FakeResolve())
    assert client.get(f"{F}/templates", params={"kind": "titles"}).json()["count"] == 2
    assert client.get(f"{F}/templates", params={"kind": "nope"}).status_code == 404


def test_fonts(client):
    r = client.get(f"{F}/fonts")
    assert r.status_code == 200 and "Segoe UI Symbol" in r.json()["fonts"]
    assert client.get(f"{F}/fonts", params={"contains": "comic"}).json()["fonts"] == ["Comic Sans MS"]


def test_comp_attrs_undo_save(client, timeline):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    assert client.get(f"{comp}/attrs").json()["render_end"] == 149
    r = client.patch(f"{comp}/attrs", json={"current_time": 40, "render_end": 300, "hiq": False, "raw": {"COMPB_MotionBlur": True}})
    assert r.status_code == 200 and r.json()["set"] == {"COMPN_CurrentTime": 40, "COMPN_RenderEnd": 300, "COMPB_HiQ": False, "COMPB_MotionBlur": True}
    assert client.get(f"{comp}/attrs").json()["current_time"] == 40
    assert client.patch(f"{comp}/attrs", json={}).status_code == 422
    assert client.post(f"{comp}/undo", json={"action": "start", "name": "batch"}).json()["ok"]
    assert client.post(f"{comp}/undo", json={"action": "end"}).json()["ok"]
    fake_comp = [it for it in timeline._all_items() if it.GetName() == "Text+"][0].comps[0]
    assert fake_comp.undo == [("start", "batch"), ("end", True)]
    assert client.post(f"{comp}/save", json={"path": "D:/c.comp"}).json()["ok"] and fake_comp.saved_to == "D:/c.comp"


def test_graph_lists_edges_and_positions(client):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    client.post(f"{comp}/tools", json={"tool_id": "Background", "name": "BG"})
    client.post(f"{comp}/tools", json={"tool_id": "Merge", "name": "M1"})
    client.post(f"{comp}/tools/M1/connect", json={"input": "Background", "source_tool": "BG"})
    client.post(f"{comp}/tools/M1/connect", json={"input": "Foreground", "source_tool": "Template"})
    client.patch(f"{comp}/tools/M1", json={"position": [3, 1.5]})
    g = client.get(f"{comp}/graph").json()
    names = {n["name"] for n in g["nodes"]}
    assert {"MediaIn1", "MediaOut1", "Template", "BG", "M1"} <= names
    assert next(n for n in g["nodes"] if n["name"] == "M1")["position"] == [3, 1.5]
    assert g["outputs"] == ["MediaOut1"]


def test_patch_tool_lock_color_and_type_filter(client, timeline):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    r = client.patch(f"{comp}/tools/Template", json={"locked": True, "tile_color": [1, 0.5, 0]})
    assert r.status_code == 200
    fake_comp = [it for it in timeline._all_items() if it.GetName() == "Text+"][0].comps[0]
    assert fake_comp.tools["Template"].locked is True and fake_comp.tools["Template"].TileColor == {"R": 1, "G": 0.5, "B": 0}
    assert client.patch(f"{comp}/tools/Template", json={"tile_color": []}).status_code == 200 and fake_comp.tools["Template"].TileColor is None
    assert [t["name"] for t in client.get(f"{comp}/tools", params={"type": "TextPlus"}).json()["tools"]] == ["Template"]


def test_paste_settings_with_overrides(client):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    table = {"Tools": {"Lower": {"__ctor": "TextPlus", "Inputs": {"StyledText": "Name", "Size": 0.05}}, "Bar": {"__ctor": "Background", "Inputs": {"TopLeftRed": 1}}}}
    r = client.post(f"{comp}/paste", json={"settings": table, "inputs": {"TextPlus2": {"StyledText": "Ada Lovelace"}}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert sorted(t["id"] for t in body["tools"]) == ["Background", "TextPlus"]
    assert body["overrides"] == {"TextPlus2": {"StyledText": True}}
    assert client.get(f"{comp}/tools/TextPlus2").json()["inputs"]["StyledText"] == "Ada Lovelace"
    assert client.post(f"{comp}/paste", json={}).status_code == 422


def test_paste_from_file_uses_settings_reader(fake_resolve, tmp_path):
    from dollygrip.bridge import ResolveBridge
    from dollygrip.server import Settings, create_app
    from fastapi.testclient import TestClient

    read = lambda path: {"Tools": {"Glow": {"__ctor": "Background", "Inputs": {"TopLeftBlue": 1}}}} if path.endswith(".setting") else None  # noqa: E731
    app = create_app(Settings(), bridge=ResolveBridge(connector=lambda: fake_resolve, settings_reader=read))
    client = TestClient(app)
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    r = client.post(f"{comp}/paste", json={"path": "D:/fx/glow.setting"})
    assert r.status_code == 200 and r.json()["tools"][0]["id"] == "Background"
    assert client.post(f"{comp}/paste", json={"path": "D:/fx/nope.txt"}).status_code == 404


def test_duplicate_and_presets(client, timeline):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    client.patch(f"{comp}/tools/Template/inputs", json={"inputs": {"StyledText": "One", "Size": 0.2}})
    client.post(f"{comp}/tools/Template/keyframes", json={"input": "Size", "keyframes": [{"frame": 0, "value": 0.0}, {"frame": 10, "value": 0.2}]})
    r = client.post(f"{comp}/tools/Template/duplicate", json={"name": "Two", "inputs": {"StyledText": "Two"}})
    assert r.status_code == 200, r.text
    assert r.json()["tool"]["name"] == "Two" and r.json()["tool"]["inputs"]["StyledText"] == "Two"
    fake_comp = [it for it in timeline._all_items() if it.GetName() == "Text+"][0].comps[0]
    assert fake_comp.tools["Two"].keyframes["Size"] == {0: 0.0, 10: 0.2}  # animation travels with the copy
    client.patch(f"{comp}/tools/Template/inputs", json={"inputs": {"Size": 0.2}})
    assert client.post(f"{comp}/tools/Template/settings/save", json={"path": "D:/presets/title.setting"}).json()["ok"]
    client.patch(f"{comp}/tools/Two/inputs", json={"inputs": {"Size": 0.9}})
    assert client.post(f"{comp}/tools/Two/settings/load", json={"path": "D:/presets/title.setting"}).json()["tool"]["inputs"]["Size"] == 0.2
    assert client.post(f"{comp}/tools/Two/settings/load", json={"path": "D:/nope.setting"}).status_code == 422


def test_keyframes_read_and_clear(client, timeline):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    assert client.get(f"{comp}/tools/Template/keyframes", params={"input": "Size"}).json() == {"input": "Size", "animated": False, "value": 0.08, "keyframes": {}}
    client.post(f"{comp}/tools/Template/keyframes", json={"input": "Size", "keyframes": [{"frame": 0, "value": 0.05}, {"frame": 24, "value": 0.12}]})
    r = client.get(f"{comp}/tools/Template/keyframes", params={"input": "Size"}).json()
    assert r["animated"] is True and r["keyframes"] == {"0": 0.05, "24": 0.12} and r["modifier"] == "BezierSpline"
    r = client.delete(f"{comp}/tools/Template/keyframes", params={"input": "Size", "value": 0.3}).json()
    assert r["was_animated"] is True and r["value"] == 0.3
    assert client.get(f"{comp}/tools/Template/keyframes", params={"input": "Size"}).json()["animated"] is False
    assert client.get(f"{comp}/tools/Template/keyframes", params={"input": "Nope"}).status_code in (200, 404)


def test_modifiers(client, timeline):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    r = client.post(f"{comp}/tools/Template/modifier", json={"input": "Center", "modifier": "Shake", "inputs": {"Smoothness": 0.5, "XMinimum": 0.4}})
    assert r.status_code == 200, r.text
    assert r.json()["modifier"]["id"] == "Shake" and r.json()["inputs_set"] == {"Smoothness": True, "XMinimum": True}
    fake_comp = [it for it in timeline._all_items() if it.GetName() == "Text+"][0].comps[0]
    assert fake_comp.tools["Template"].splines["Center"].kind == "Shake"
    assert client.post(f"{comp}/tools/Template/modifier", json={"input": "Center", "modifier": "Offset"}).status_code == 422  # not in the fake


def test_text_plus_style_extras(client, timeline):
    iid = _title(client)
    r = client.post(f"{F}/items/{iid}/text-plus", json={"text": "Hi", "shadow": True, "outline": [0, 0, 0], "outline_thickness": 0.02, "tracking": 1.1, "line_spacing": 0.9})
    assert r.status_code == 200
    inputs = [it for it in timeline._all_items() if it.GetName() == "Text+"][0].comps[0].tools["Template"].inputs
    assert inputs["Enabled3"] == 1 and inputs["Enabled2"] == 1 and inputs["Thickness2"] == 0.02 and inputs["CharacterSpacing"] == 1.1 and inputs["LineSpacing"] == 0.9
