from conftest import item_ids

V1 = "/api/v1"
ITEMS = f"{V1}/timelines/current/items"


def test_list_items_with_relative_frames(client):
    r = client.get(ITEMS)
    assert r.status_code == 200
    body = r.json()
    assert body["start_frame"] == 108000
    v1 = [i for i in body["items"] if i["track_type"] == "video" and i["track_index"] == 1][0]
    assert v1["name"] == "spokes.mp4" and v1["start"] == 108000 and v1["start_rel"] == 0 and v1["duration"] == 240
    v2 = [i for i in body["items"] if i["track_index"] == 2][0]
    assert v2["start_rel"] == 30 and v2["media_pool_clip"] == "art.mov"
    assert len(client.get(ITEMS, params={"track_type": "audio"}).json()["items"]) == 1
    assert client.get(ITEMS, params={"track_type": "video", "track_index": 2}).json()["items"][0]["name"] == "art.mov"


def test_get_item_and_current(client):
    iid = item_ids(client, "video")[0]
    r = client.get(f"{ITEMS}/{iid}")
    assert r.status_code == 200 and r.json()["properties"]["ZoomX"] == 1.0 and r.json()["current_version"]["versionName"] == "Version 1"
    assert client.get(f"{ITEMS}/current").json()["id"] == iid
    assert client.get(f"{ITEMS}/nope").status_code == 404
    assert client.get(f"{ITEMS}/selected").json()["items"][0]["id"] == iid


def test_patch_item(client, timeline):
    iid = item_ids(client, "video")[0]
    r = client.patch(f"{ITEMS}/{iid}", json={"name": "hero", "enabled": False, "color": "Orange", "properties": {"ZoomX": 1.2, "Opacity": 50}})
    assert r.status_code == 200
    assert r.json()["results"] == {"name": True, "enabled": True, "color": True, "properties": {"ZoomX": True, "Opacity": True}}
    item = timeline.tracks["video"][0]["items"][0]
    assert item.GetName() == "hero" and item.enabled is False and item.props["Opacity"] == 50
    assert client.patch(f"{ITEMS}/{iid}", json={"color": ""}).json()["item"]["color"] == ""
    assert client.get(f"{ITEMS}/{iid}/properties").json()["properties"]["ZoomX"] == 1.2
    assert client.put(f"{ITEMS}/{iid}/properties", json={"properties": {"Pan": 100}}).json()["results"] == {"Pan": True}


def test_delete_item(client, timeline):
    iid = item_ids(client, "video")[1]
    assert client.delete(f"{ITEMS}/{iid}", params={"ripple": "true"}).json()["ok"]
    assert timeline.last_ripple is True and len(item_ids(client, "video")) == 1


def test_flags_linked_audio_mapping(client):
    iid = item_ids(client, "video")[0]
    assert client.post(f"{ITEMS}/{iid}/flags", json={"color": "Green"}).json()["flags"] == ["Green"]
    assert client.delete(f"{ITEMS}/{iid}/flags").json()["flags"] == []
    assert client.get(f"{ITEMS}/{iid}/linked").json()["items"] == []  # spokes has no audio twin in the seed
    assert "track_mapping" in client.get(f"{ITEMS}/{iid}/audio-mapping").json()["mapping"]


def test_takes(client):
    iid = item_ids(client, "video")[0]
    assert client.get(f"{ITEMS}/{iid}/takes").json() == {"count": 0, "selected": 0, "takes": []}
    r = client.post(f"{ITEMS}/{iid}/takes", json={"clip": "art.mov", "start_frame": 0, "end_frame": 50})
    assert r.status_code == 200 and r.json()["count"] == 1
    client.post(f"{ITEMS}/{iid}/takes", json={"clip": "music.wav"})
    takes = client.get(f"{ITEMS}/{iid}/takes").json()
    assert takes["count"] == 2 and takes["takes"][0]["clip"] == "art.mov" and takes["takes"][0]["end_frame"] == 50
    assert client.post(f"{ITEMS}/{iid}/takes/1/select").json()["selected"] == 1
    assert client.post(f"{ITEMS}/{iid}/takes/9/select").status_code == 422
    assert client.delete(f"{ITEMS}/{iid}/takes/2").json()["count"] == 1
    assert client.post(f"{ITEMS}/{iid}/takes/finalize").json()["ok"]
    assert client.post(f"{ITEMS}/{iid}/takes", json={"clip": "ghost"}).status_code == 404


def test_ai_and_cache(client, timeline):
    iid = item_ids(client, "video")[0]
    item = timeline.tracks["video"][0]["items"][0]
    assert client.post(f"{ITEMS}/{iid}/stabilize").json()["ok"] and item.stabilized
    assert client.post(f"{ITEMS}/{iid}/smart-reframe").json()["ok"] and item.reframed
    assert client.post(f"{ITEMS}/{iid}/magic-mask", json={"mode": "F"}).json()["ok"]
    assert client.post(f"{ITEMS}/{iid}/magic-mask/regenerate").json()["ok"]
    assert client.put(f"{ITEMS}/{iid}/voice-isolation", json={"enabled": True, "amount": 30}).json()["state"] == {"isEnabled": True, "amount": 30}
    assert client.get(f"{ITEMS}/{iid}/voice-isolation").json()["state"]["amount"] == 30
    r = client.put(f"{ITEMS}/{iid}/cache", json={"color_output": True, "fusion_output": "on"})
    assert r.json()["results"] == {"color_output": True, "fusion_output": True}
    assert client.get(f"{ITEMS}/{iid}/cache").json() == {"color_output": True, "fusion_output": 1}
    assert client.post(f"{ITEMS}/{iid}/burn-in-preset", json={"name": "Dailies"}).json()["ok"] and item.burn_in == "Dailies"
    assert client.post(f"{ITEMS}/{iid}/sidecar").json()["ok"]


def test_item_markers(client, timeline):
    iid = item_ids(client, "video")[0]
    r = client.post(f"{ITEMS}/{iid}/markers", json={"frame": 10, "color": "Cyan", "name": "beat"})
    assert r.status_code == 200 and r.json()["markers"][0]["frame"] == 10
    assert client.get(f"{ITEMS}/{iid}/markers").json()["markers"][0]["color"] == "Cyan"
    assert client.delete(f"{ITEMS}/{iid}/markers", params={"frame": 10}).json()["markers"] == []
    assert client.post(f"{ITEMS}/nope/markers", json={"frame": 1}).status_code == 404
