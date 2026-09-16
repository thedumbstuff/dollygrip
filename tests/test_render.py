V1 = "/api/v1"
R = f"{V1}/render"


def test_setup_queries(client):
    assert client.get(f"{R}/formats").json()["formats"]["MP4"] == "mp4"
    assert client.get(f"{R}/formats/mp4/codecs").json()["codecs"] == {"H.264": "H264"}
    assert len(client.get(f"{R}/resolutions", params={"format": "mp4", "codec": "H264"}).json()["resolutions"]) == 2
    assert client.get(f"{R}/current").json() == {"format": "mp4", "codec": "H264", "mode": "single", "rendering": False}
    assert client.put(f"{R}/mode", json={"mode": "individual"}).json()["mode"] == "individual"
    assert client.get(f"{R}/mode").json()["mode"] == "individual"


def test_presets(client, project, fake_resolve):
    assert client.get(f"{R}/presets").json()["presets"] == ["YouTube 1080p", "H.264 Master"]
    assert client.post(f"{R}/presets/YouTube 1080p/load").json()["ok"] and project.current_preset == "YouTube 1080p"
    assert client.post(f"{R}/presets/nope/load").status_code == 422
    assert client.post(f"{R}/presets", json={"name": "Reels"}).json()["ok"]
    assert client.post(f"{R}/presets", json={"name": "Reels"}).status_code == 422
    assert client.delete(f"{R}/presets/Reels").json()["ok"]
    assert client.post(f"{R}/presets/import", json={"path": "D:/p.xml"}).json()["ok"] and fake_resolve.imported_render_preset == "D:/p.xml"
    assert client.post(f"{R}/presets/H.264 Master/export", json={"path": "D:/out.xml"}).json()["ok"]
    assert client.post(f"{R}/presets/ghost/export", json={"path": "D:/out.xml"}).status_code == 422


def test_add_job_with_preset_and_mode(client, project):
    r = client.post(f"{R}/jobs", json={"preset": "H.264 Master", "mode": "individual", "settings": {"TargetDir": "D:/out"}, "start": False})
    assert r.status_code == 200 and r.json()["started"] is False
    assert project.current_preset == "H.264 Master" and project.render_mode == 0 and project.render_settings["TargetDir"] == "D:/out"
    assert client.post(f"{R}/jobs", json={"preset": "ghost"}).status_code == 422
    job_id = r.json()["job_id"]
    assert client.get(f"{R}/jobs/{job_id}").json()["JobStatus"] == "Ready"
    assert client.post(f"{R}/start", json={"job_ids": [job_id]}).json()["ok"]
    assert client.get(f"{R}/jobs/{job_id}").json()["JobStatus"] == "Complete"


def test_start_all_stop_delete_all(client, project):
    client.post(f"{R}/jobs", json={"start": False})
    client.post(f"{R}/jobs", json={"start": False})
    assert client.post(f"{R}/start", json={"interactive": True}).json()["ok"]
    assert all(j["JobStatus"] == "Complete" for j in client.get(f"{R}/jobs").json()["jobs"])
    assert client.post(f"{R}/stop").json()["ok"] and project.stopped
    assert client.delete(f"{R}/jobs").json()["ok"] and client.get(f"{R}/jobs").json()["jobs"] == []


def test_wait_for_job(client):
    job_id = client.post(f"{R}/jobs", json={"start": True}).json()["job_id"]
    r = client.post(f"{R}/jobs/{job_id}/wait", params={"timeout": 5, "poll": 0.2})
    assert r.status_code == 200 and r.json()["done"] is True and r.json()["JobStatus"] == "Complete"
    assert client.post(f"{R}/jobs/ghost/wait", params={"timeout": 1}).status_code == 404


def test_wait_times_out(client, project):
    job_id = client.post(f"{R}/jobs", json={"start": False}).json()["job_id"]
    r = client.post(f"{R}/jobs/{job_id}/wait", params={"timeout": 0, "poll": 0.2})
    assert r.json()["done"] is False and r.json()["timed_out"] is True


def test_quick_export(client):
    assert client.get(f"{R}/quick-export/presets").json()["presets"] == ["H.264", "YouTube", "TikTok"]
    r = client.post(f"{R}/quick-export", json={"preset": "TikTok", "target_dir": "D:/out", "custom_name": "reel"})
    assert r.status_code == 200 and r.json()["JobStatus"] == "Complete"
    assert client.post(f"{R}/quick-export", json={"preset": "Nope"}).status_code == 404


def test_burn_in_presets(client, project, fake_resolve):
    assert client.get(f"{R}/burn-in/presets").json()["presets"] == ["Dailies"]
    assert client.post(f"{R}/burn-in/presets/Dailies/load").json()["ok"] and project.burn_in == "Dailies"
    assert client.post(f"{R}/burn-in/presets/import", json={"path": "D:/b.xml"}).json()["ok"]
    assert client.post(f"{R}/burn-in/presets/Dailies/export", json={"path": "D:/d.xml"}).json()["ok"]
    assert client.delete(f"{R}/burn-in/presets/Dailies").json()["ok"]
    assert client.delete(f"{R}/burn-in/presets/Dailies").status_code == 422
