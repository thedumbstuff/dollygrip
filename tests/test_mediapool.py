V1 = "/api/v1"
MP = f"{V1}/mediapool"


def test_folder_tree_has_ids_and_bin_ops(client, project):
    tree = client.get(f"{MP}/folders").json()
    assert tree["root"]["name"] == "Master" and tree["root"]["folders"][0]["name"] == "R3-auto" and tree["root"]["id"]
    assert client.post(f"{MP}/folders", json={"path": "R3-auto/sub", "create": True}).json()["current"] == "sub"
    assert client.post(f"{MP}/folders/move", json={"paths": ["R3-auto/sub"], "target": "Archive"}).json()["ok"]
    assert [f.GetName() for f in project.pool.root.subfolders] == ["R3-auto", "Archive"]
    assert client.post(f"{MP}/folders/delete", json={"paths": ["Archive"]}).json()["deleted"] == 1
    assert client.post(f"{MP}/folders/delete", json={"paths": ["ghost"]}).status_code == 404
    assert client.post(f"{MP}/folders/refresh").json()["ok"]
    assert client.post(f"{MP}/folders/export", json={"path": "R3-auto", "file": "D:/bins/r3.drb"}).json()["ok"]
    assert project.pool.root.subfolders[0].exported_to == "D:/bins/r3.drb"
    assert client.post(f"{MP}/folders/import", json={"file": "D:/bins/other.drb"}).json()["ok"]


def test_list_clips_by_bin_and_recursive(client):
    assert [c["name"] for c in client.get(f"{MP}/clips").json()["clips"]] == ["music.wav"]
    r = client.get(f"{MP}/clips", params={"bin": "R3-auto"}).json()
    assert r["bin"] == "R3-auto" and [c["name"] for c in r["clips"]] == ["spokes.mp4", "art.mov"]
    names = [c["name"] for c in client.get(f"{MP}/clips", params={"recursive": "true"}).json()["clips"]]
    assert names == ["music.wav", "spokes.mp4", "art.mov"]
    assert client.get(f"{MP}/clips", params={"bin": "nope"}).status_code == 404


def test_get_and_patch_clip_by_name_or_id(client, project):
    clip = client.get(f"{MP}/clips/art.mov").json()  # not in the current bin - found anywhere
    assert clip["name"] == "art.mov" and clip["properties"]["FPS"] == "24" and clip["id"].startswith("mpi-")
    by_id = client.get(f"{MP}/clips/{clip['id']}").json()
    assert by_id["name"] == "art.mov"
    r = client.patch(
        f"{MP}/clips/{clip['id']}",
        json={"name": "art-v2.mov", "color": "Teal", "properties": {"Super Scale": "2"}, "metadata": {"Description": "overlay"}, "third_party_metadata": {"shot": "12A"}},
    )
    assert r.status_code == 200 and all(v is True or v == {"Super Scale": True} for v in r.json()["results"].values())
    art = project.pool.root.subfolders[0].clips[1]
    assert art.GetName() == "art-v2.mov" and art.metadata["Description"] == "overlay" and art.third_party["shot"] == "12A"
    assert client.get(f"{MP}/clips/art-v2.mov/metadata").json()["third_party_metadata"] == {"shot": "12A"}
    assert client.get(f"{MP}/clips/art-v2.mov/properties").json()["properties"]["Super Scale"] == "2"
    assert client.get(f"{MP}/clips/ghost").status_code == 404


def test_clip_bulk_ops(client, project):
    assert client.post(f"{MP}/clips/move", json={"clips": ["art.mov"], "target": "Overlays"}).json()["target"] == "Overlays"
    assert [c.GetName() for c in project.pool.root.subfolders[-1].clips] == ["art.mov"]
    assert client.post(f"{MP}/clips/relink", json={"clips": ["spokes.mp4"], "folder_path": "E:/moved"}).json()["relinked"] == 1
    assert project.pool.relinked[0][1] == "E:/moved"
    assert client.post(f"{MP}/clips/unlink", json={"clips": ["spokes.mp4"]}).json()["unlinked"] == 1
    assert client.post(f"{MP}/clips/delete", json={"clips": ["music.wav"]}).json()["deleted"] == 1
    assert project.pool.root.clips == []
    assert client.post(f"{MP}/clips/delete", json={"clips": ["ghost"]}).status_code == 404


def test_clip_flags_marks_proxy_replace(client, project):
    assert client.post(f"{MP}/clips/spokes.mp4/flags", json={"color": "Red"}).json()["flags"] == ["Red"]
    assert client.delete(f"{MP}/clips/spokes.mp4/flags", params={"color": "Red"}).json()["flags"] == []
    assert client.put(f"{MP}/clips/spokes.mp4/mark-in-out", json={"in": 5, "out": 50}).json()["marks"] == {"video": {"in": 5, "out": 50}, "audio": {"in": 5, "out": 50}}
    assert client.get(f"{MP}/clips/spokes.mp4/mark-in-out").json()["marks"]["video"]["out"] == 50
    assert client.delete(f"{MP}/clips/spokes.mp4/mark-in-out", params={"type": "audio"}).json()["marks"] == {"video": {"in": 5, "out": 50}}
    spokes = project.pool.root.subfolders[0].clips[0]
    assert client.post(f"{MP}/clips/spokes.mp4/proxy", json={"path": "D:/proxy/spokes.mov"}).json()["ok"] and spokes.proxy == "D:/proxy/spokes.mov"
    assert client.delete(f"{MP}/clips/spokes.mp4/proxy").json()["ok"] and spokes.proxy is None
    assert client.post(f"{MP}/clips/spokes.mp4/full-resolution", json={"path": "D:/full/spokes.mp4"}).json()["ok"]
    assert client.post(f"{MP}/clips/spokes.mp4/replace", json={"path": "D:/v2.mp4", "preserve_subclip": True}).json()["ok"]
    assert spokes.replaced_with == ("preserve", "D:/v2.mp4")
    assert client.post(f"{MP}/clips/spokes.mp4/monitor-growing").json()["ok"]
    assert "track_mapping" in client.get(f"{MP}/clips/spokes.mp4/audio-mapping").json()["mapping"]


def test_import_paths_sequences_and_subclips(client, project):
    r = client.post(f"{MP}/import", json={"paths": ["D:/a.mov"], "sequences": [{"file_path": "D:/frames/f_%03d.png", "start_index": 1, "end_index": 100}]})
    assert r.status_code == 200 and [c["name"] for c in r.json()["imported"]] == ["a.mov", "f_[001-100].png"] and r.json()["requested"] == 2
    r = client.post(f"{MP}/subclips", json={"items": [{"media": "D:/long.mov", "start_frame": 100, "end_frame": 200}]})
    assert r.json()["imported"][0]["name"] == "long.mov"
    assert project.pool.root.clips[-1].GetClipProperty("End") == "200"


def test_stereo_sync_selection_metadata(client, project):
    assert client.post(f"{MP}/stereo", json={"left": "spokes.mp4", "right": "art.mov"}).json()["clip"]["name"] == "spokes.mp4_3D"
    r = client.post(f"{MP}/sync-audio", json={"clips": ["spokes.mp4", "music.wav"], "mode": "waveform", "channel": -1})
    assert r.status_code == 200 and project.pool.synced[1] == {"AUDIO_SYNC_MODE": 400, "AUDIO_SYNC_RETAIN_EMBEDDED_AUDIO": False, "AUDIO_SYNC_RETAIN_VIDEO_METADATA": False, "AUDIO_SYNC_CHANNEL_NUMBER": -1}
    assert client.post(f"{MP}/sync-audio", json={"clips": ["spokes.mp4"]}).status_code == 422
    assert client.put(f"{MP}/selection", json={"clips": ["art.mov"]}).json()["clips"][0]["name"] == "art.mov"
    assert client.get(f"{MP}/selection").json()["clips"][0]["name"] == "art.mov"
    assert client.put(f"{MP}/selection", json={"clips": []}).status_code == 404
    assert client.post(f"{MP}/metadata/export", json={"file": "D:/meta.csv", "clips": ["art.mov"]}).json()["ok"]
    assert project.pool.exported_metadata[0] == "D:/meta.csv" and len(project.pool.exported_metadata[1]) == 1
    assert client.post(f"{MP}/metadata/export", json={"file": "D:/all.csv"}).json()["ok"]


def test_mattes(client, project):
    assert client.post(f"{MP}/clips/spokes.mp4/mattes", json={"paths": ["D:/m1.png"], "stereo_eye": "left"}).json()["mattes"] == ["D:/m1.png"]
    assert client.get(f"{MP}/clips/spokes.mp4/mattes").json()["mattes"] == ["D:/m1.png"]
    assert client.request("DELETE", f"{MP}/clips/spokes.mp4/mattes", json={"paths": ["D:/m1.png"]}).json()["mattes"] == []
    assert client.post(f"{MP}/mattes", json={"paths": ["D:/tm.mov"]}).json()["mattes"][0]["name"] == "tm.mov"
    assert client.get(f"{MP}/mattes").json()["mattes"][0]["name"] == "tm.mov"


def test_ai_on_clips_and_bins(client, project):
    spokes = project.pool.root.subfolders[0].clips[0]
    assert client.post(f"{MP}/clips/spokes.mp4/transcribe", json={"speaker_detection": True}).json()["ok"] and spokes.transcribed
    assert client.delete(f"{MP}/clips/spokes.mp4/transcribe").json()["ok"] and not spokes.transcribed
    assert client.post(f"{MP}/folders/transcribe", params={"bin": "R3-auto"}, json={}).json()["bin"] == "R3-auto"
    assert client.delete(f"{MP}/folders/transcribe", params={"bin": "R3-auto"}).json()["ok"]
    assert client.post(f"{MP}/clips/spokes.mp4/audio-classification").json()["ok"] and spokes.classified
    assert client.delete(f"{MP}/clips/spokes.mp4/audio-classification").json()["ok"]
    assert client.post(f"{MP}/folders/audio-classification").json()["ok"]
    assert client.delete(f"{MP}/folders/audio-classification").json()["ok"]
    assert client.post(f"{MP}/clips/spokes.mp4/deblur", json={"options": {"Format": "mov"}}).json()["clip"]["name"] == "spokes_deblur.mov"
    assert len(client.post(f"{MP}/folders/deblur", params={"bin": "R3-auto"}, json={}).json()["pairs"]) == 2
    assert client.post(f"{MP}/clips/spokes.mp4/intellisearch", json={"identify_faces": True}).json()["ok"]
    assert client.post(f"{MP}/folders/intellisearch", json={}).json()["ok"]
    assert client.post(f"{MP}/clips/spokes.mp4/slate", json={"marker_color": "green"}).json()["ok"]
    assert client.post(f"{MP}/folders/slate", json={}).json()["ok"]
    assert client.post(f"{MP}/clips/spokes.mp4/slate", json={"marker_color": "plaid"}).status_code == 404


def test_clip_markers(client):
    r = client.post(f"{MP}/clips/spokes.mp4/markers", json={"frame": 24, "color": "Yellow", "name": "sync"})
    assert r.status_code == 200 and r.json()["markers"][0]["name"] == "sync"
    assert client.get(f"{MP}/clips/spokes.mp4/markers").json()["markers"][0]["frame"] == 24
    assert client.delete(f"{MP}/clips/spokes.mp4/markers", params={"color": "All"}).json()["markers"] == []
