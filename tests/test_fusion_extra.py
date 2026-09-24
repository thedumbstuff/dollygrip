from conftest import item_ids

V1 = "/api/v1"
F = f"{V1}/fusion"


def _title(client):
    r = client.post(f"{V1}/timelines/current/generators", json={"kind": "fusion_title", "name": "Text+"})
    return r.json()["item_id"]


def _fake_comp(timeline):
    return [it for it in timeline._all_items() if it.GetName() == "Text+"][0].comps[0]


def test_comp_markers(client, timeline):
    comp = f"{F}/items/{_title(client)}/comps/1"
    assert client.get(f"{comp}/markers").json() == {"markers": []}
    r = client.put(f"{comp}/markers", json={"frame": 24, "name": "Hit", "note": "beat", "color": "Red"})
    assert r.status_code == 200 and r.json()["markers"] == [{"frame": 24, "name": "Hit", "note": "beat", "color": "Red"}]
    client.put(f"{comp}/markers", json={"frame": 5, "name": "Start"})
    assert [m["frame"] for m in client.get(f"{comp}/markers").json()["markers"]] == [5, 24]
    assert client.delete(f"{comp}/markers", params={"frame": 24}).json()["markers"] == [{"frame": 5, "name": "Start", "note": "", "color": ""}]
    assert client.delete(f"{comp}/markers", params={"frame": 99}).status_code == 404
    assert client.put(f"{F}/items/{_title(client)}/comps/ghost/markers", json={"frame": 1, "name": "x"}).status_code == 404


def test_comp_markers_rejected(client, timeline):
    comp = f"{F}/items/{_title(client)}/comps/1"
    fake = _fake_comp(timeline)

    def boom(*a):
        raise RuntimeError("no markers here")

    fake.GetMarkers = boom
    r = client.get(f"{comp}/markers")
    assert r.status_code == 422 and "no markers here" in r.json()["detail"]


def test_active_tool(client, timeline):
    comp = f"{F}/items/{_title(client)}/comps/1"
    assert client.get(f"{comp}/active-tool").json() == {"tool": None}
    r = client.put(f"{comp}/active-tool", json={"tool": "Template"})
    assert r.status_code == 200 and r.json()["tool"]["name"] == "Template"
    assert client.get(f"{comp}/active-tool").json()["tool"]["id"] == "TextPlus"
    assert client.put(f"{comp}/active-tool", json={"tool": "ghost"}).status_code == 404
    assert client.delete(f"{comp}/active-tool").json() == {"ok": True, "tool": None}
    assert _fake_comp(timeline).ActiveTool is None


def test_history_undo_redo_clear(client, timeline):
    comp = f"{F}/items/{_title(client)}/comps/1"
    for name in ("one", "two", "three"):
        client.post(f"{comp}/undo", json={"action": "start", "name": name})
        client.post(f"{comp}/undo", json={"action": "end"})
    assert client.get(f"{comp}/history").json() == {"undo": ["one", "two", "three"], "redo": []}
    r = client.post(f"{comp}/history", json={"action": "undo", "count": 2}).json()
    assert r["undo"] == ["one"] and r["redo"] == ["three", "two"]
    assert client.post(f"{comp}/history", json={"action": "redo"}).json()["undo"] == ["one", "two"]
    assert client.post(f"{comp}/history", json={"action": "undo", "count": 0}).status_code == 422
    assert client.delete(f"{comp}/history").json()["ok"]
    assert client.get(f"{comp}/history").json() == {"undo": [], "redo": []}


def test_history_unreadable_is_422(client, timeline):
    comp = f"{F}/items/{_title(client)}/comps/1"
    fake = _fake_comp(timeline)

    def boom():
        raise AttributeError("GetUndoStack")

    fake.GetUndoStack = boom
    assert client.get(f"{comp}/history").json() == {"undo": None, "redo": []}  # one stack readable
    fake.GetRedoStack = boom
    assert client.get(f"{comp}/history").status_code == 422
    fake.ClearUndo = boom
    assert client.delete(f"{comp}/history").status_code == 422


def test_key_times(client, timeline):
    comp = f"{F}/items/{_title(client)}/comps/1"
    client.post(f"{comp}/tools/Template/keyframes", json={"input": "Size", "keyframes": [{"frame": 10, "value": 0.1}, {"frame": 30, "value": 0.2}]})
    assert client.get(f"{comp}/key-times", params={"from": 0}).json() == {"from": 0, "direction": "next", "frame": 10, "found": True}
    assert client.get(f"{comp}/key-times", params={"from": 10}).json()["frame"] == 30
    assert client.get(f"{comp}/key-times", params={"from": 20, "direction": "prev"}).json()["frame"] == 10
    assert client.get(f"{comp}/key-times", params={"from": 30}).json() == {"from": 30, "direction": "next", "frame": None, "found": False}
    _fake_comp(timeline).GetNextKeyTime = lambda t, tool=None: 1e9  # the sentinel some builds answer
    assert client.get(f"{comp}/key-times", params={"from": 0}).json()["found"] is False
    assert client.get(f"{comp}/key-times", params={"from": 0, "direction": "sideways"}).status_code == 422


def test_select_and_selection(client, timeline):
    comp = f"{F}/items/{_title(client)}/comps/1"
    assert client.get(f"{comp}/selection").json() == {"tools": []}
    r = client.post(f"{comp}/tools/select", json={"tools": ["Template", "MediaIn1"]})
    assert r.status_code == 200 and {t["name"] for t in r.json()["tools"]} == {"Template", "MediaIn1"}
    r = client.post(f"{comp}/tools/select", json={"tools": ["MediaOut1"], "exclusive": True})
    assert [t["name"] for t in r.json()["tools"]] == ["MediaOut1"]
    assert [t["name"] for t in client.get(f"{comp}/selection").json()["tools"]] == ["MediaOut1"]
    assert client.post(f"{comp}/tools/select", json={"tools": ["ghost"]}).status_code == 404
    assert client.post(f"{comp}/tools/select", json={"tools": []}).status_code == 422


def test_select_exclusive_uses_flowview_when_loaded(client, timeline):
    iid = _title(client)
    comp = f"{F}/items/{iid}/comps/1"
    client.patch(f"{comp}/tools/Template", json={"position": [1, 1]})  # loads the comp on the Fusion page
    fake = _fake_comp(timeline)
    assert fake.CurrentFrame is not None
    client.post(f"{comp}/tools/select", json={"tools": ["Template", "MediaIn1"]})
    r = client.post(f"{comp}/tools/select", json={"tools": ["MediaIn1"], "exclusive": True}).json()
    assert [t["name"] for t in r["tools"]] == ["MediaIn1"] and fake.tools["Template"].selected is False


def test_disconnect(client, timeline):
    comp = f"{F}/items/{_title(client)}/comps/1"
    client.post(f"{comp}/tools", json={"tool_id": "Background", "name": "BG"})
    client.post(f"{comp}/tools", json={"tool_id": "Merge", "name": "M1"})
    client.post(f"{comp}/tools/M1/connect", json={"input": "Background", "source_tool": "BG"})
    r = client.post(f"{comp}/tools/M1/disconnect", json={"input": "Background"})
    assert r.status_code == 200 and r.json() == {"ok": True, "input": "Background", "was_connected_to": "BG"}
    assert _fake_comp(timeline).tools["M1"].connections == {}
    r = client.post(f"{comp}/tools/M1/disconnect", json={"input": "Background"})
    assert r.status_code == 422 and "not connected" in r.json()["detail"]


def test_disconnect_refuses_modifiers(client, timeline):
    comp = f"{F}/items/{_title(client)}/comps/1"
    client.post(f"{comp}/tools/Template/keyframes", json={"input": "Size", "keyframes": [{"frame": 0, "value": 0.1}, {"frame": 10, "value": 0.2}]})
    r = client.post(f"{comp}/tools/Template/disconnect", json={"input": "Size"})
    assert r.status_code == 422 and "BezierSpline" in r.json()["detail"]
    assert client.post(f"{comp}/tools/ghost/disconnect", json={"input": "Size"}).status_code == 404


def test_outputs(client, timeline):
    comp = f"{F}/items/{_title(client)}/comps/1"
    client.post(f"{comp}/tools", json={"tool_id": "Merge", "name": "M1"})
    client.post(f"{comp}/tools/M1/connect", json={"input": "Foreground", "source_tool": "Template"})
    r = client.get(f"{comp}/tools/Template/outputs")
    assert r.status_code == 200
    assert r.json()["outputs"] == [{"id": "Output", "name": "Output", "data_type": "Image", "connected_to": [{"tool": "M1", "input": "Foreground"}]}]
    assert client.get(f"{comp}/tools/M1/outputs").json()["outputs"][0]["connected_to"] == []
    assert client.get(f"{comp}/tools/ghost/outputs").status_code == 404


def test_registry(client, fake_resolve):
    r = client.get(f"{F}/registry").json()
    assert r["count"] == 4 and r["tools"][0] == {"id": "Background", "name": "Background", "category": "Generators"}
    assert [t["id"] for t in client.get(f"{F}/registry", params={"contains": "text+"}).json()["tools"]] == ["TextPlus"]
    assert client.get(f"{F}/registry", params={"type": "modifier"}).json()["count"] == 0
    fake_resolve._fusion.reg_summary = {"Shake": "Shake", "Blur": {"Name": "Blur"}}  # plain strings / tables without ID
    assert {t["id"] for t in client.get(f"{F}/registry").json()["tools"]} == {"Shake", "Blur"}
    fake_resolve._fusion.reg_summary = {}
    r = client.get(f"{F}/registry")
    assert r.status_code == 422 and "GetRegSummary" in r.json()["detail"]


def test_reset_input(client, timeline):
    comp = f"{F}/items/{_title(client)}/comps/1"
    client.patch(f"{comp}/tools/Template/inputs", json={"inputs": {"Size": 0.5}})
    r = client.post(f"{comp}/tools/Template/reset-input", json={"input": "Size"})
    assert r.status_code == 200 and r.json() == {"ok": True, "input": "Size", "value": 0.08}
    r = client.post(f"{comp}/tools/Template/reset-input", json={"input": "StyledText"})
    assert r.status_code == 422 and "No default" in r.json()["detail"]


def test_text_plus_lines(client, timeline):
    iid = _title(client)
    r = client.post(f"{F}/items/{iid}/text-plus/lines", json={"lines": ["Line one", "Line two"]})
    assert r.status_code == 200 and r.json()["tool"] == "Template"
    assert _fake_comp(timeline).tools["Template"].inputs["StyledText"] == "Line one\nLine two"
    assert client.post(f"{F}/items/{iid}/text-plus/lines", json={"lines": []}).status_code == 422
    video = item_ids(client, "video")[0]
    client.post(f"{F}/items/{video}/comps", json={})
    assert client.post(f"{F}/items/{video}/text-plus/lines", json={"lines": ["x"]}).status_code == 404  # no Text+ tool
