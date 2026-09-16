from conftest import item_ids

V1 = "/api/v1"
F = f"{V1}/fusion"


def _title(client):
    r = client.post(f"{V1}/timelines/current/generators", json={"kind": "fusion_title", "name": "Text+"})
    return r.json()["item_id"]


def test_comps_crud(client, timeline):
    iid = item_ids(client, "video")[0]
    assert client.get(f"{F}/items/{iid}/comps").json() == {"count": 0, "comps": []}
    assert client.get(f"{F}/items/{iid}/comps/1/tools").status_code == 404  # no comp yet
    assert client.post(f"{F}/items/{iid}/comps", json={}).json()["comps"] == ["Composition 1"]
    assert client.post(f"{F}/items/{iid}/comps", json={"import_path": "D:/fx/glow.comp"}).json()["comps"] == ["Composition 1", "glow"]
    assert client.patch(f"{F}/items/{iid}/comps/glow", json={"name": "Glow FX"}).json()["comps"] == ["Composition 1", "Glow FX"]
    assert client.post(f"{F}/items/{iid}/comps/Glow FX/load").json()["ok"]
    assert client.post(f"{F}/items/{iid}/comps/Glow FX/export", json={"path": "D:/fx/out.comp"}).json()["ok"]
    assert timeline.tracks["video"][0]["items"][0].comps[1].saved_to == "D:/fx/out.comp"
    assert client.post(f"{F}/items/{iid}/comps/ghost/export", json={"path": "x"}).status_code == 404
    assert client.delete(f"{F}/items/{iid}/comps/Glow FX").json()["comps"] == ["Composition 1"]
    assert client.delete(f"{F}/items/{iid}/comps/ghost").status_code == 422


def test_tools_inputs_connect_keyframes(client, timeline):
    iid = _title(client)
    tools = client.get(f"{F}/items/{iid}/comps/1/tools").json()
    assert [t["name"] for t in tools["tools"]] == ["MediaIn1", "MediaOut1", "Template"] and tools["attrs"]["COMPN_RenderEnd"] == 149
    r = client.post(f"{F}/items/{iid}/comps/1/tools", json={"tool_id": "Background", "name": "BG", "inputs": {"TopLeftRed": 1.0}})
    assert r.status_code == 200 and r.json()["tool"]["name"] == "BG" and r.json()["inputs_set"] == {"TopLeftRed": True}
    r = client.post(f"{F}/items/{iid}/comps/1/tools", json={"tool_id": "Merge"})
    assert r.json()["tool"]["name"] == "Merge1"
    assert client.post(f"{F}/items/{iid}/comps/1/tools/Merge1/connect", json={"input": "Background", "source_tool": "BG"}).json()["ok"]
    assert client.post(f"{F}/items/{iid}/comps/1/tools/Merge1/connect", json={"input": "Foreground", "source_tool": "ghost"}).status_code == 404
    comp = [it for it in timeline._all_items() if it.GetName() == "Text+"][0].comps[0]
    assert comp.tools["Merge1"].connections == {"Background": "BG"}
    r = client.patch(f"{F}/items/{iid}/comps/1/tools/Template/inputs", json={"inputs": {"StyledText": "Hi", "Center": [0.5, 0.8]}})
    assert r.json()["results"] == {"StyledText": True, "Center": True} and comp.tools["Template"].inputs["Center"] == {1: 0.5, 2: 0.8}
    assert client.get(f"{F}/items/{iid}/comps/1/tools/Template").json()["inputs"]["StyledText"] == "Hi"
    r = client.post(f"{F}/items/{iid}/comps/1/tools/Template/keyframes", json={"input": "Size", "keyframes": [{"frame": 0, "value": 0.05}, {"frame": 24, "value": 0.12}]})
    assert r.json()["all_ok"] and comp.tools["Template"].keyframes["Size"] == {0: 0.05, 24: 0.12}
    assert client.patch(f"{F}/items/{iid}/comps/1/tools/Template/inputs", json={"inputs": {"Size": 0.2}, "frame": 48}).json()["results"] == {"Size": True}
    assert comp.tools["Template"].keyframes["Size"][48] == 0.2
    assert client.delete(f"{F}/items/{iid}/comps/1/tools/BG").json()["ok"] and "BG" not in comp.tools
    assert client.get(f"{F}/items/{iid}/comps/1/tools/BG").status_code == 404


def test_text_plus_convenience(client, timeline):
    iid = _title(client)
    r = client.post(f"{F}/items/{iid}/text-plus", json={"text": "Lower third", "font": "Inter", "style": "Bold", "size": 0.06, "color": [1, 0.8, 0, 1], "center": [0.5, 0.2]})
    assert r.status_code == 200, r.text
    assert r.json()["tool"] == "Template"
    comp = [it for it in timeline._all_items() if it.GetName() == "Text+"][0].comps[0]
    inputs = comp.tools["Template"].inputs
    assert inputs["StyledText"] == "Lower third" and inputs["Font"] == "Inter" and inputs["Green1"] == 0.8 and inputs["Alpha1"] == 1 and inputs["Center"] == {1: 0.5, 2: 0.2}
    # an item whose comp has no Text+ -> 404
    plain = item_ids(client, "video")[0]
    client.post(f"{F}/items/{plain}/comps", json={})
    assert client.post(f"{F}/items/{plain}/text-plus", json={"text": "x"}).status_code == 404


def test_current_comp(client, fake_resolve):
    r = client.get(f"{F}/current-comp")
    assert r.status_code == 200 and [t["id"] for t in r.json()["tools"]] == ["MediaIn", "MediaOut", "TextPlus"]
    assert client.patch(f"{F}/current-comp/tools/Template/inputs", json={"inputs": {"StyledText": "Live"}}).json()["results"] == {"StyledText": True}
    assert fake_resolve._fusion.current_comp.tools["Template"].inputs["StyledText"] == "Live"


def test_input_discovery_expressions_and_bypass(client, timeline):
    iid = _title(client)
    r = client.get(f"{F}/items/{iid}/comps/1/tools/Template/inputs")
    assert r.status_code == 200, r.text
    rows = {i["id"]: i for i in r.json()["inputs"]}
    assert rows["StyledText"]["control"] == "TextEditControl" and rows["StyledText"]["value"] == "Title" and rows["Size"]["max"] == 1.0
    assert all(i["page"] == "Text" for i in client.get(f"{F}/items/{iid}/comps/1/tools/Template/inputs", params={"page": "text"}).json()["inputs"])
    r = client.put(f"{F}/items/{iid}/comps/1/tools/Template/expression", json={"input": "Size", "expression": "time/30"})
    assert r.status_code == 200 and r.json()["expression"] == "time/30"
    rows = {i["id"]: i for i in client.get(f"{F}/items/{iid}/comps/1/tools/Template/inputs").json()["inputs"]}
    assert rows["Size"]["expression"] == "time/30"
    assert client.put(f"{F}/items/{iid}/comps/1/tools/Template/expression", json={"input": "Size", "expression": None}).json()["expression"] is None
    r = client.patch(f"{F}/items/{iid}/comps/1/tools/Template", json={"pass_through": True, "name": "Title1"})
    assert r.json()["tool"] == {"name": "Title1", "id": "TextPlus", "pass_through": True, "selected": False}
    assert client.get(f"{F}/items/{iid}/comps/1/tools/Title1").status_code == 200
    assert client.get(f"{F}/items/{iid}/comps/1/tools/Template").status_code == 404
