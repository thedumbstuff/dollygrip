V1 = "/api/v1"
P = f"{V1}/projects"


def test_list_and_attributes(client):
    body = client.get(P).json()
    assert body["projects"] == ["TutorBee"] and body["folders"] == ["Archive"] and body["current"] == "TutorBee"
    assert "lastModifiedDate" in client.get(f"{P}/attributes").json()["projects"]["TutorBee"]


def test_create_rename_close_delete(client, fake_resolve):
    r = client.post(P, json={"name": "New", "media_location_path": "D:/media"})
    assert r.status_code == 200 and r.json()["name"] == "New" and r.json()["id"]
    assert client.post(P, json={"name": "New"}).status_code == 404
    assert client.patch(f"{P}/current", json={"name": "Renamed"}).json()["name"] == "Renamed"
    assert client.get(f"{P}/current").json()["name"] == "Renamed"
    assert client.delete(f"{P}/New").status_code == 422  # it is open (under its new name key... still current)
    assert client.delete(f"{P}/TutorBee").json()["ok"]
    assert client.post(f"{P}/current/close").json()["ok"]
    assert client.get(f"{P}/current").status_code == 409


def test_presets_and_luts(client):
    assert [p["Name"] for p in client.get(f"{P}/current/presets").json()["presets"]] == ["Default", "Vertical"]
    assert client.post(f"{P}/current/presets/Vertical/load").json()["ok"]
    assert client.post(f"{P}/current/presets/Nope/load").status_code == 422
    assert client.post(f"{P}/current/luts/refresh").json()["ok"]


def test_import_export_archive_restore(client, fake_resolve):
    pm = fake_resolve.pm
    assert client.post(f"{P}/current/export", json={"path": "D:/tb.drp", "with_stills_and_luts": False}).json()["ok"]
    assert pm.exports == [("TutorBee", "D:/tb.drp", False)]
    assert client.post(f"{P}/current/archive", json={"path": "D:/tb.dra", "proxy_media": True}).json()["ok"]
    assert pm.archives == [("TutorBee", "D:/tb.dra", True, True, True)]
    assert client.post(f"{P}/import", json={"path": "D:/other.drp", "name": "Other"}).json()["ok"]
    assert "Other" in pm.projects
    assert client.post(f"{P}/restore", json={"path": "D:/third.dra"}).json()["ok"]
    assert "third" in pm.projects
    assert client.post(f"{P}/import", json={"path": "D:/other.drp", "name": "Other"}).status_code == 422


def test_project_folders(client, fake_resolve):
    assert client.post(f"{P}/folders", json={"name": "Clients"}).json()["ok"]
    assert client.get(f"{P}/folders").json()["folders"] == ["Archive", "Clients"]
    assert client.post(f"{P}/folders/open", json={"name": "Clients"}).json()["folder"] == "Clients"
    assert client.post(f"{P}/folders/open", json={"name": ".."}).json()["folder"] == ""
    assert client.post(f"{P}/folders/open", json={"name": "/"}).json()["projects"] == ["TutorBee"]
    assert client.post(f"{P}/folders/open", json={"name": "ghost"}).status_code == 422
    assert client.delete(f"{P}/folders/Clients").json()["ok"]
    assert client.delete(f"{P}/folders/Clients").status_code == 422


def test_databases(client, fake_resolve):
    body = client.get(f"{P}/databases").json()
    assert body["current"]["DbName"] == "Local Database" and len(body["databases"]) == 2
    r = client.put(f"{P}/databases/current", json={"db_type": "PostgreSQL", "db_name": "studio", "ip_address": "10.0.0.5"})
    assert r.status_code == 200 and r.json()["current"] == {"DbType": "PostgreSQL", "DbName": "studio", "IpAddress": "10.0.0.5"}
    assert client.get(f"{P}/current").status_code == 409  # switching closes the project


def test_fairlight_speech_audio(client, fake_resolve):
    project = fake_resolve.pm.current
    assert client.post(f"{P}/current/fairlight-preset", json={"name": "Podcast"}).json()["ok"] and project.fairlight_preset == "Podcast"
    assert client.post(f"{P}/current/audio-at-playhead", json={"path": "D:/sfx.wav", "duration_samples": 48000}).json()["ok"]
    r = client.post(f"{P}/current/speech", json={"text": "Welcome to TutorBee", "voice_model": "Male 1", "filename": "vo1", "add_to_timeline": True, "audio_track": 2, "timecode": "01:00:02:00"})
    assert r.status_code == 200 and r.json()["clip"]["name"] == "vo1.wav"
    settings, tc = project.speech[0]
    assert settings["TextInput"] == "Welcome to TutorBee" and settings["AudioTrack"] == 2 and tc == "01:00:02:00"
    assert client.post(f"{P}/current/intellisearch/reset").json()["ok"]
