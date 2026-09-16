from conftest import item_ids

V1 = "/api/v1"
C = f"{V1}/color"


def test_versions(client):
    iid = item_ids(client, "video")[0]
    assert client.get(f"{C}/items/{iid}/versions").json() == {"current": {"versionName": "Version 1", "versionType": 0}, "local": ["Version 1"], "remote": []}
    assert client.post(f"{C}/items/{iid}/versions", json={"name": "Warm", "type": "remote"}).json()["ok"]
    assert client.post(f"{C}/items/{iid}/versions", json={"name": "Warm", "type": "remote"}).status_code == 422
    assert client.post(f"{C}/items/{iid}/versions/Warm/load", params={"type": "remote"}).json()["current"]["versionName"] == "Warm"
    assert client.post(f"{C}/items/{iid}/versions/Warm/load").status_code == 422  # not a local version
    assert client.patch(f"{C}/items/{iid}/versions/Warm", json={"new_name": "Warmer", "type": "remote"}).json()["ok"]
    assert client.delete(f"{C}/items/{iid}/versions/Warmer", params={"type": "remote"}).json()["ok"]
    assert client.get(f"{C}/items/{iid}/versions").json()["remote"] == []


def test_cdl_copy_grades_lut_export(client, timeline):
    ids = item_ids(client, "video")
    item = timeline.tracks["video"][0]["items"][0]
    r = client.put(f"{C}/items/{ids[0]}/cdl", json={"node_index": 1, "slope": "0.5 0.4 0.2", "saturation": "0.65"})
    assert r.status_code == 200 and item.cdl["Slope"] == "0.5 0.4 0.2" and item.cdl["NodeIndex"] == "1"
    assert client.post(f"{C}/items/{ids[0]}/copy-grades", json={"target_item_ids": ids[1:]}).json()["copied_to"] == 1
    assert client.post(f"{C}/items/{ids[0]}/lut/export", json={"path": "D:/look.cube", "size": "65"}).json()["ok"]
    assert item.exported_lut == (502, "D:/look.cube")
    assert client.post(f"{C}/items/{ids[0]}/reset-node-colors").json()["ok"]


def test_clip_graph_ops(client, timeline):
    iid = item_ids(client, "video")[0]
    item = timeline.tracks["video"][0]["items"][0]
    g = client.get(f"{C}/items/{iid}/graph").json()
    assert g["num_nodes"] == 2 and g["nodes"][0] == {"index": 1, "label": "Node 1", "lut": "", "cache_mode": "off", "tools": ["Primaries"]}
    assert client.put(f"{C}/items/{iid}/graph/nodes/2/lut", json={"path": "Film Looks/Kodak.cube"}).json()["lut"] == "Film Looks/Kodak.cube"
    assert client.put(f"{C}/items/{iid}/graph/nodes/9/lut", json={"path": "x.cube"}).status_code == 422
    assert client.put(f"{C}/items/{iid}/graph/nodes/1/cache", json={"mode": "on"}).json()["cache_mode"] == "on"
    assert client.put(f"{C}/items/{iid}/graph/nodes/1/enabled", json={"enabled": False}).json()["enabled"] is False
    assert item.graphs[1].nodes[0]["enabled"] is False
    assert client.post(f"{C}/items/{iid}/graph/drx", json={"path": "D:/look.drx", "mode": "start_frames_aligned"}).json()["ok"]
    assert item.graphs[1].applied_drx == ("D:/look.drx", 2)
    assert client.post(f"{C}/items/{iid}/graph/drx", json={"path": "D:/look.png"}).status_code == 422
    assert client.post(f"{C}/items/{iid}/graph/arri-cdl-lut").json()["ok"]
    assert client.post(f"{C}/items/{iid}/graph/reset").json()["ok"] and item.graphs[1].reset
    assert client.get(f"{C}/items/{iid}/graph/layers/2").json()["num_nodes"] == 2


def test_timeline_and_group_graphs(client, timeline):
    assert client.get(f"{C}/timeline/graph").json()["num_nodes"] == 1
    assert client.put(f"{C}/timeline/graph/nodes/1/lut", json={"path": "out.cube"}).json()["ok"]
    assert timeline.graph.nodes[0]["lut"] == "out.cube"
    client.post(f"{C}/groups", json={"name": "Interviews"})
    assert client.get(f"{C}/groups/Interviews/pre-graph").json()["num_nodes"] == 1
    assert client.post(f"{C}/groups/Interviews/post-graph/reset").json()["ok"]
    assert client.get(f"{C}/groups/ghost/pre-graph").status_code == 404


def test_color_groups(client, timeline):
    ids = item_ids(client, "video")
    assert client.get(f"{C}/groups").json()["groups"] == []
    assert client.post(f"{C}/groups", json={"name": "Interviews"}).json()["name"] == "Interviews"
    assert client.post(f"{C}/groups", json={"name": "Interviews"}).status_code == 404
    assert client.post(f"{C}/groups/Interviews/clips", json={"item_ids": ids}).json()["results"] == {ids[0]: True, ids[1]: True}
    assert [i["id"] for i in client.get(f"{C}/groups/Interviews/clips").json()["items"]] == ids
    assert client.delete(f"{C}/items/{ids[1]}/group").json()["ok"]
    assert len(client.get(f"{C}/groups/Interviews/clips").json()["items"]) == 1
    assert client.get(f"{V1}/timelines/current/items/{ids[0]}").json()["color_group"] == "Interviews"
    assert client.patch(f"{C}/groups/Interviews", json={"name": "Talking heads"}).json()["ok"]
    assert client.delete(f"{C}/groups/Talking heads").json()["ok"]
    assert client.get(f"{C}/groups").json()["groups"] == []


def test_gallery(client, project):
    albums = client.get(f"{C}/gallery/albums").json()
    assert albums["current"] == "Stills" and albums["still_albums"][0]["still_count"] == 1 and albums["powergrade_albums"][0]["name"] == "PowerGrade 1"
    assert client.post(f"{C}/gallery/albums", json={"kind": "still", "name": "Reel looks"}).json()["name"] == "Reel looks"
    assert client.post(f"{C}/gallery/albums", json={"kind": "powergrade"}).json()["kind"] == "powergrade"
    assert client.patch(f"{C}/gallery/albums/Reel looks", json={"name": "Looks"}).json()["ok"]
    assert client.post(f"{C}/gallery/albums/Looks/current").json()["current"] == "Looks"
    assert client.post(f"{C}/gallery/albums/current/stills/import", json={"paths": ["D:/a.drx", "D:/b.drx"]}).json()["still_count"] == 2
    stills = client.get(f"{C}/gallery/albums/2/stills").json()["stills"]
    assert stills == [{"index": 1, "label": "a.drx"}, {"index": 2, "label": "b.drx"}]
    assert client.patch(f"{C}/gallery/albums/Looks/stills/1", json={"label": "warm"}).json()["label"] == "warm"
    assert client.post(f"{C}/gallery/albums/Looks/stills/export", json={"folder": "D:/stills", "format": "drx", "indices": [2]}).json()["exported"] == 1
    assert project.gallery.still_albums[1].exported[3] == "drx"
    assert client.post(f"{C}/gallery/albums/Looks/stills/export", json={"folder": "D:/x", "indices": [9]}).status_code == 404
    assert client.post(f"{C}/gallery/albums/Looks/stills/delete", json={"indices": [1]}).json()["still_count"] == 1
    assert client.get(f"{C}/gallery/albums/1/stills", params={"kind": "powergrade"}).json()["stills"] == []
    assert client.get(f"{C}/gallery/albums/ghost/stills").status_code == 404


def test_export_frame_and_keyframe_mode(client, project, fake_resolve):
    assert client.post(f"{C}/export-frame", json={"path": "D:/frame.png"}).json()["ok"] and project.exported_still == "D:/frame.png"
    assert client.get(f"{C}/keyframe-mode").json()["mode"] == "all"
    assert client.put(f"{C}/keyframe-mode", json={"mode": "sizing"}).json()["mode"] == "sizing" and fake_resolve.keyframe_mode == 2
