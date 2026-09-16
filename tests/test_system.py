V1 = "/api/v1"
S = f"{V1}/system"


def test_info_and_constants(client):
    info = client.get(f"{S}/info").json()
    assert info["version_fields"] == [21, 0, 4, 5, "b"] and info["current_project"] == "TutorBee" and info["database"]["DbType"] == "Disk"
    consts = client.get(f"{S}/constants", params={"prefix": "EXPORT_A"}).json()["constants"]
    assert consts == {"EXPORT_AAF": 0, "EXPORT_AAF_NEW": 101, "EXPORT_AAF_EXISTING": 102, "EXPORT_ALE": 15, "EXPORT_ALE_CDL": 16}


def test_quit_needs_confirm(client, fake_resolve):
    assert client.post(f"{S}/quit", json={"confirm": False}).status_code == 422
    assert not fake_resolve.quit_called
    assert client.post(f"{S}/quit", json={"confirm": True}).json()["ok"] and fake_resolve.quit_called


def test_background_tasks_and_fairlight(client):
    assert client.post(f"{S}/background-tasks/disable").json()["ok"]
    assert client.get(f"{S}/fairlight-presets").json()["presets"] == ["Podcast", "Dialogue Cleanup"]


def test_layout_presets(client, fake_resolve):
    assert client.get(f"{S}/layouts").json()["presets"] == ["Default", "Editing"]
    assert client.post(f"{S}/layouts", json={"name": "Grading"}).json()["ok"]
    assert client.post(f"{S}/layouts/Grading/load").json()["ok"]
    assert client.post(f"{S}/layouts/ghost/load").status_code == 422
    assert client.put(f"{S}/layouts/Grading").json()["ok"]
    assert client.post(f"{S}/layouts/import", json={"path": "D:/l.preset", "name": "Imported"}).json()["ok"]
    assert client.post(f"{S}/layouts/Imported/export", json={"path": "D:/out.preset"}).json()["ok"]
    assert ("layout", "Imported", "D:/out.preset") in fake_resolve.exported
    assert client.delete(f"{S}/layouts/Imported").json()["ok"]
    assert client.delete(f"{S}/layouts/Imported").status_code == 422


def test_preference_presets(client, fake_resolve):
    assert client.get(f"{S}/preferences/presets").json()["presets"] == ["Default"]
    assert client.post(f"{S}/preferences/presets", json={"name": "Laptop"}).json()["ok"]
    assert client.post(f"{S}/preferences/presets/Laptop/load").json()["ok"]
    assert client.post(f"{S}/preferences/presets/import", json={"path": "D:/p.prefs"}).json()["ok"]
    assert client.post(f"{S}/preferences/presets/Laptop/export", json={"path": "D:/l.prefs"}).json()["ok"]
    assert client.delete(f"{S}/preferences/presets/Laptop").json()["ok"]
    assert client.post(f"{S}/preferences/presets/Laptop/load").status_code == 422


def test_media_storage(client, fake_resolve, project):
    assert client.get(f"{V1}/storage/volumes").json()["volumes"] == ["C:/", "D:/"]
    assert client.get(f"{V1}/storage/folders", params={"path": "D:/"}).json()["folders"] == ["D:/shoot", "D:/audio"]
    assert client.get(f"{V1}/storage/files", params={"path": "D:/shoot"}).json()["files"][0] == "D:/shoot/a.mov"
    assert client.post(f"{V1}/storage/reveal", json={"path": "D:/shoot"}).json()["ok"] and fake_resolve.storage.revealed == "D:/shoot"
    r = client.post(f"{V1}/storage/add-to-mediapool", json={"items": ["D:/shoot/a.mov", {"media": "D:/shoot/b.mov", "start_frame": 10, "end_frame": 20}]})
    assert [c["name"] for c in r.json()["imported"]] == ["a.mov", "b.mov"]
    assert project.pool.root.clips[-1].GetClipProperty("Start") == "10"


def test_timecode_tool(client):
    r = client.post(f"{V1}/tools/timecode", json={"fps": 30, "frames": 108000})
    assert r.json()["timecode"] == "01:00:00:00" and r.json()["seconds"] == 3600
    assert client.post(f"{V1}/tools/timecode", json={"fps": 25, "timecode": "00:01:00:05"}).json()["frames"] == 1505
    assert client.post(f"{V1}/tools/timecode", json={"fps": 29.97, "frames": 17982, "drop_frame": True}).json()["timecode"] == "00:10:00;00"
    assert client.post(f"{V1}/tools/timecode", json={"fps": 29.97, "timecode": "00:10:00;00", "drop_frame": True}).json()["frames"] == 17982
    assert client.post(f"{V1}/tools/timecode", json={"fps": 30}).status_code == 422
    assert client.post(f"{V1}/tools/timecode", json={"fps": 30, "timecode": "bad"}).status_code == 422


def test_exec_namespace_has_fusion_and_storage(fake_resolve):
    from conftest import make_client

    client = make_client(fake_resolve, allow_exec=True)
    r = client.post(f"{V1}/exec", json={"code": "result = [fusion is not None, media_storage.GetMountedVolumeList(), gallery is not None]"})
    assert r.json()["result"] == [True, ["C:/", "D:/"], True]
