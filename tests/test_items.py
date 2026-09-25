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


def test_relocate_moves_and_trims(client, timeline):
    ids = item_ids(client, "video")
    client.patch(f"{ITEMS}/{ids[1]}", json={"name": "art-renamed", "properties": {"Opacity": 40.0}})
    client.post(f"{ITEMS}/{ids[1]}/markers", json={"frame": 5, "color": "Pink", "name": "m"})
    old = timeline.tracks["video"][1]["items"][0]
    old.AddFusionComp()
    r = client.post(f"{ITEMS}/{ids[1]}/relocate", json={"record_frame": 200, "track_index": 3, "start_frame": 10, "end_frame": 40})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["grade_copied"] is True and body["fusion_comps_restored"] == 1 and body["note"] is None
    new = body["item"]
    assert new["track_index"] == 3 and new["start_rel"] == 200 and new["duration"] == 30 and new["source_start"] == 10
    assert new["name"] == "art-renamed" and old.grades_copied_to
    assert ids[1] not in item_ids(client, "video")
    moved = timeline.tracks["video"][2]["items"][0]
    assert moved.props["Opacity"] == 40.0 and 5.0 in moved.markers and len(moved.comps) == 1


def test_relocate_same_track_overlap_deletes_first(client, timeline):
    iid = item_ids(client, "video")[0]  # spokes on V1 at 0..240
    r = client.post(f"{ITEMS}/{iid}/relocate", json={"record_frame": 10})
    assert r.status_code == 200 and r.json()["grade_copied"] is False and "overlap" in r.json()["note"]
    assert r.json()["item"]["start_rel"] == 10 and len(timeline.tracks["video"][0]["items"]) == 1


def test_relocate_rejects_generators_and_bad_ranges(client):
    tid = client.post(f"{V1}/timelines/current/generators", json={"kind": "generator", "name": "Solid Color"}).json()["item_id"]
    assert client.post(f"{ITEMS}/{tid}/relocate", json={"record_frame": 5}).status_code == 422
    iid = item_ids(client, "video")[0]
    assert client.post(f"{ITEMS}/{iid}/relocate", json={"start_frame": 50, "end_frame": 10}).status_code == 422
    assert client.post(f"{ITEMS}/nope/relocate", json={}).status_code == 404


def test_split_item(client, timeline):
    iid = item_ids(client, "video")[0]  # 240 frames at rel 0, source 0..240 (exclusive end)
    r = client.post(f"{ITEMS}/{iid}/split", json={"frame": 100})
    assert r.status_code == 200, r.text
    left, right = r.json()["items"]
    assert left["start_rel"] == 0 and left["duration"] == 100 and left["source_start"] == 0
    assert right["start_rel"] == 100 and right["source_start"] == 100 and right["end_rel"] == 240
    assert client.post(f"{ITEMS}/{right['id']}/split", json={"frame": 100}).status_code == 422  # on the boundary
    assert client.post(f"{ITEMS}/{right['id']}/split", json={"frame": 999}).status_code == 422


def test_relocate_with_linked_audio(client, timeline):
    # an A/V append (no media_type) creates linked video + audio items on V3/A3
    r = client.post(f"{V1}/timelines/current/append", json={"items": [{"clip_name": "spokes.mp4", "track_index": 3, "record_frame": 50}]})
    vid = r.json()["results"][0]["item_id"]
    assert client.get(f"{ITEMS}/{vid}/linked").json()["items"][0]["track_type"] == "audio"
    r = client.post(f"{ITEMS}/{vid}/relocate", json={"record_frame": 300, "with_linked": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item"]["start_rel"] == 300 and len(body["linked_items"]) == 1
    assert body["linked_items"][0]["track_type"] == "audio" and body["linked_items"][0]["start_rel"] == 300
    assert not any(it.GetStart() == 108050 for it in timeline._all_items())


def test_retime_fit_inserts_timespeed(client, timeline):
    iid = item_ids(client, "video")[0]  # 240 frames at 0
    r = client.post(f"{ITEMS}/{iid}/retime", json={"speed": 0.5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "fit" and body["duration_after"] == 240 and body["created"] is True and body["holds"] == {"first": 0, "last": 1}
    item = timeline.tracks["video"][0]["items"][0]
    comp = item.comps[0]
    ts = comp.tools["DollyGripRetime"]
    assert ts.reg_id == "TimeSpeed" and ts.inputs["Speed"] == 0.5 and ts.inputs["InterpolateBetweenFrames"] == 1
    # inserted between MediaIn and MediaOut
    assert ts.connections["Input"] == "MediaIn1" and comp.tools["MediaOut1"].connections["Input"] == "DollyGripRetime"
    # delay solves comp frame 0 -> the item's in point: in * (1 - 1/speed) with in = source_start
    assert abs(body["delay"] - (item.source_start * (1 - 1 / 0.5))) < 1e-6
    # second call updates in place
    r2 = client.post(f"{ITEMS}/{iid}/retime", json={"speed": 2.0, "interpolate": False})
    assert r2.status_code == 200 and r2.json()["created"] is False and ts.inputs["Speed"] == 2.0 and ts.inputs["InterpolateBetweenFrames"] == 0
    assert r2.json()["holds"]["last"] > 0  # 2x needs 480 frames after the in point; the fake clip is shorter


def test_retime_ripple_changes_length_and_shifts(client, timeline):
    ids = item_ids(client, "video")
    first = timeline.tracks["video"][0]["items"][0]
    dur, start_rel = first.duration, 0
    r = client.post(f"{ITEMS}/{ids[0]}/retime", json={"speed": 2.0, "mode": "ripple"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["duration_after"] == dur // 2 and body["item"]["duration"] == dur // 2 and body["item"]["start_rel"] == start_rel
    assert body["source_window"] == [first.source_start, first.source_start + dur // 2]
    assert "DollyGripRetime" in timeline.tracks["video"][0]["items"][0].comps[0].tools


def test_retime_rejects(client):
    iid = item_ids(client, "video")[0]
    assert client.post(f"{ITEMS}/{iid}/retime", json={"speed": 0}).status_code == 422
    tid = client.post(f"{V1}/timelines/current/generators", json={"kind": "generator", "name": "Solid Color"}).json()["item_id"]
    assert client.post(f"{ITEMS}/{tid}/retime", json={"speed": 0.5}).status_code == 422
    assert client.post(f"{ITEMS}/nope/retime", json={"speed": 0.5}).status_code == 404


def test_dissolve_before_cut_moves_incoming_up_with_fade(client, timeline):
    ids = item_ids(client, "video")
    a = timeline.tracks["video"][0]["items"][0]  # 0..240 on V1
    # make B adjacent on V1 with 30 frames of head handle
    r = client.post(f"{V1}/timelines/current/append", json={"items": [{"clip_name": "spokes.mp4", "track_index": 1, "record_frame": 240, "start_frame": 30, "end_frame": 90, "media_type": "video"}]})
    assert r.json()["all_ok"], r.text
    r = client.post(f"{ITEMS}/{ids[0]}/dissolve", json={"frames": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["align"] == "before_cut" and body["cut_rel"] == 240 and len(body["pieces"]) == 1
    piece = body["pieces"][0]
    assert piece["role"] == "incoming" and piece["item"]["start_rel"] == 220 and piece["item"]["source_start"] == 10 and piece["track_index"] >= 2
    moved = [it for tr in timeline.tracks["video"] for it in tr["items"] if it.GetUniqueId() == body["incoming"]][0]
    comp = moved.comps[0]
    assert comp.tools["DollyGripFade"].connections == {"Background": "DollyGripFadeBG", "Foreground": "MediaIn1"}
    assert comp.tools["MediaOut1"].connections["Input"] == "DollyGripFade"
    assert comp.tools["DollyGripFade"].keyframes["Blend"] == {0: 0.0, 19: 1.0}
    assert comp.tools["DollyGripFadeBG"].inputs["TopLeftAlpha"] == 0.0


def test_dissolve_after_cut_adds_outgoing_tail(client, timeline):
    # A2 = spokes 0..100 at 300 (140 frames of tail handle), B2 adjacent with NO head handle
    r = client.post(f"{V1}/timelines/current/append", json={"items": [
        {"clip_name": "spokes.mp4", "track_index": 1, "record_frame": 300, "start_frame": 0, "end_frame": 100, "media_type": "video"},
        {"clip_name": "spokes.mp4", "track_index": 1, "record_frame": 400, "start_frame": 0, "end_frame": 60, "media_type": "video"}]})
    assert r.json()["all_ok"], r.text
    a2 = [i for i in client.get(f"{ITEMS}").json()["items"] if i["start_rel"] == 300][0]["id"]
    r = client.post(f"{ITEMS}/{a2}/dissolve", json={"frames": 12})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["align"] == "after_cut" and body["pieces"][0]["role"] == "outgoing_tail"
    tail = body["pieces"][0]["item"]
    assert tail["start_rel"] == 400 and tail["duration"] == 12 and tail["source_start"] == 100 and body["pieces"][0]["fade_out"] == 12
    assert body["pieces"][0]["keys"] == {"0": 1.0, "11": 0.0}


def test_dissolve_rejects(client, timeline):
    ids = item_ids(client, "video")
    assert client.post(f"{ITEMS}/{ids[0]}/dissolve", json={"frames": 10}).status_code == 404  # nothing follows
    client.post(f"{V1}/timelines/current/append", json={"items": [{"clip_name": "spokes.mp4", "track_index": 1, "record_frame": 300, "start_frame": 0, "end_frame": 60, "media_type": "video"}]})
    nxt = [i for i in client.get(f"{ITEMS}").json()["items"] if i["start_rel"] == 300][0]["id"]
    assert client.post(f"{ITEMS}/{ids[0]}/dissolve", json={"to": nxt, "frames": 10}).status_code == 422  # not adjacent
