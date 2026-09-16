from conftest import make_client, make_stock

V1 = "/api/v1"


def test_providers_and_search(fake_resolve, tmp_path):
    client = make_client(fake_resolve, stock=make_stock(tmp_path))
    prov = client.get(f"{V1}/stock/providers").json()
    assert prov["providers"] == {"pexels": True, "pixabay": False, "coverr": False} and prov["media_dir"] == str(tmp_path)
    r = client.post(f"{V1}/stock/search", json={"terms": ["city", "rain"], "aspect": "portrait"})
    assert r.status_code == 200 and r.json()["count"] == 2 and [m["id"] for m in r.json()["results"]["city"]] == ["101", "102"]
    assert client.post(f"{V1}/stock/search", json={"terms": ["x"], "provider": "pixabay"}).status_code == 422  # no key


def test_download_and_plan(fake_resolve, tmp_path):
    client = make_client(fake_resolve, stock=make_stock(tmp_path))
    mats = client.post(f"{V1}/stock/search", json={"terms": ["city"]}).json()["results"]["city"]
    r = client.post(f"{V1}/stock/download", json={"materials": mats})
    assert r.status_code == 200 and r.json()["materials"][0]["file"].endswith("pexels-101-1080x1920.mp4")
    r = client.post(f"{V1}/stock/plan", json={"terms": ["city"], "audio_duration": 20, "max_clip_duration": 5})
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["total_duration"] == 20.1 and all(s["file"] for s in plan["shots"]) and len(plan["attribution"]) == 2
    assert [s["material_id"] for s in plan["shots"][:2]] == ["101", "102"]  # unique sources first
    assert client.post(f"{V1}/stock/plan", json={"terms": ["x"], "provider": "coverr", "audio_duration": 5}).status_code == 422


def test_assemble_converts_seconds_with_clip_fps(fake_resolve, tmp_path, project, timeline):
    client = make_client(fake_resolve, stock=make_stock(tmp_path))
    plan = client.post(f"{V1}/stock/plan", json={"terms": ["city"], "audio_duration": 12, "max_clip_duration": 5}).json()
    vo = tmp_path / "vo.wav"
    vo.write_bytes(b"\x00" * 8)
    r = client.post(f"{V1}/stock/assemble", json={"shots": plan["shots"], "track_index": 3, "bin": "stock", "fit": "fill", "voiceover": {"path": str(vo), "track_index": 2}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["all_ok"] and len(body["items"]) == len(plan["shots"]) and body["voiceover"]["item_id"]
    # fake clips are 24 fps, timeline 30 fps: 5 s shot -> source 0..120 frames, record 150 frames later for the second shot
    infos = [i for i in project.pool.appended if i.get("mediaType") == 1][-len(plan["shots"]):]
    assert infos[0]["startFrame"] == 0 and infos[0]["endFrame"] == 120 and infos[0]["recordFrame"] == 108000 and infos[0]["trackIndex"] == 3
    assert infos[1]["recordFrame"] == 108000 + 150
    items = timeline.tracks["video"][2]["items"]
    assert items and all(it.props.get("Scaling") == 3 for it in items)
    assert [f.GetName() for f in project.pool.root.subfolders][-1] == "stock"
    assert client.post(f"{V1}/stock/assemble", json={"shots": [{"file": "x", "source_in": 2, "source_out": 1, "record_at": 0}]}).status_code == 422


def test_b_roll_one_call_measures_voiceover(fake_resolve, tmp_path, project, timeline):
    client = make_client(fake_resolve, stock=make_stock(tmp_path))
    vo = tmp_path / "vo.wav"
    vo.write_bytes(b"\x00" * 8)
    r = client.post(f"{V1}/stock/b-roll", json={"terms": ["city", "rain"], "voiceover_path": str(vo), "voiceover_track": 2, "track_index": 3, "fit": "fit", "max_clip_duration": 4})
    assert r.status_code == 200, r.text
    body = r.json()
    # the fake reports item durations in source frames (240 @ 30 fps timeline = 8 s); real Resolve converts to timeline frames
    assert body["voiceover"]["seconds"] == 8.0 and body["plan"]["audio_duration"] == 8.0 and body["plan"]["total_duration"] == 8.1
    assert body["all_ok"] and body["shots"] >= 3 and all(it.props.get("Scaling") == 2 for it in timeline.tracks["video"][2]["items"])
    assert client.post(f"{V1}/stock/b-roll", json={"terms": ["city"]}).status_code == 422
    r = client.post(f"{V1}/stock/b-roll", json={"terms": ["city"], "audio_duration": 7, "mode": "random", "seed": 1})
    assert r.status_code == 200 and r.json()["plan"]["total_duration"] == 7.1
