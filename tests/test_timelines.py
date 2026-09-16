from conftest import item_ids

V1 = "/api/v1"


def test_list_and_current_timeline(client):
    r = client.get(f"{V1}/timelines")
    assert r.status_code == 200
    tls = r.json()["timelines"]
    assert tls[0]["name"] == "R8-final-art2b" and tls[0]["is_current"] and tls[0]["index"] == 1
    cur = client.get(f"{V1}/timelines/current").json()
    assert cur["start_frame"] == 108000 and cur["video_tracks"] == 2 and cur["playhead"] == "01:00:00:00"


def test_patch_timeline_name_and_start_tc(client, timeline):
    r = client.patch(f"{V1}/timelines/current", json={"name": "R8-v2", "start_timecode": "00:00:00:00"})
    assert r.status_code == 200 and r.json()["results"] == {"name": True, "start_timecode": True}
    assert timeline.GetName() == "R8-v2" and timeline.GetStartTimecode() == "00:00:00:00"


def test_create_with_start_timecode(client, project):
    r = client.post(f"{V1}/timelines", json={"name": "clean", "fps": 25, "start_timecode": "00:00:00:00"})
    assert r.status_code == 200 and r.json()["id"]
    tl = project.current_timeline
    assert tl.GetName() == "clean" and tl.settings["timelineFrameRate"] == "25" and tl.start_tc == "00:00:00:00"


def test_timeline_from_clips(client, project):
    r = client.post(
        f"{V1}/timelines/from-clips",
        json={"name": "auto", "items": [{"clip_name": "spokes.mp4", "start_frame": 0, "end_frame": 100}, {"clip_name": "art.mov"}]},
    )
    assert r.status_code == 200, r.text
    tl = project.current_timeline
    assert tl.GetName() == "auto" and len(tl.GetItemListInTrack("video", 1)) == 2
    assert client.post(f"{V1}/timelines/from-clips", json={"name": "auto", "items": []}).status_code == 404


def test_import_and_export_timeline(client, project, timeline):
    r = client.post(f"{V1}/timelines/import", json={"path": "D:/cut/edit.otio", "timeline_name": "from-otio", "source_clips_bins": ["R3-auto"]})
    assert r.status_code == 200 and r.json()["timeline"]["name"] == "from-otio"
    assert project.current_timeline.imported_from[1]["sourceClipsFolders"][0].GetName() == "R3-auto"
    r = client.post(f"{V1}/timelines/current/export", json={"path": "D:/out/x.aaf", "type": "aaf", "subtype": "aaf_new"})
    assert r.status_code == 200
    assert project.current_timeline.exported == ("D:/out/x.aaf", 0, 101)
    # aaf without subtype is a client error, not a Resolve call
    assert client.post(f"{V1}/timelines/current/export", json={"path": "x.aaf", "type": "aaf"}).status_code == 404
    r = client.post(f"{V1}/timelines/current/export", json={"path": "D:/out/x.otio", "type": "otio"})
    assert r.status_code == 200 and project.current_timeline.exported[1] == 14


def test_import_aaf_into_timeline(client, timeline):
    assert client.post(f"{V1}/timelines/current/import-aaf", json={"path": "D:/x.aaf"}).status_code == 200
    assert client.post(f"{V1}/timelines/current/import-aaf", json={"path": "D:/x.xml"}).status_code == 422


def test_duplicate_and_delete_timeline(client, project):
    r = client.post(f"{V1}/timelines/current/duplicate", json={"name": "dup"})
    assert r.status_code == 200 and r.json()["timeline"]["name"] == "dup"
    assert client.post(f"{V1}/timelines/current/duplicate", json={"name": "dup"}).status_code == 404
    assert client.delete(f"{V1}/timelines/dup").status_code == 200
    assert [t.GetName() for t in project.timelines] == ["R8-final-art2b"]
    assert client.delete(f"{V1}/timelines/current").status_code == 404
    assert client.delete(f"{V1}/timelines/ghost").status_code == 404


def test_timeline_settings_force_custom_flag(client, timeline):
    r = client.patch(f"{V1}/timelines/current/settings", json={"settings": {"timelineResolutionWidth": "3840"}})
    assert r.status_code == 200
    assert timeline.settings["useCustomSettings"] == "1" and timeline.settings["timelineResolutionWidth"] == "3840"
    assert client.get(f"{V1}/timelines/current/settings").json()["settings"]["timelineResolutionWidth"] == "3840"


def test_tracks_crud(client, timeline):
    tracks = client.get(f"{V1}/timelines/current/tracks").json()["tracks"]
    assert [t["type"] for t in tracks] == ["video", "video", "audio"]
    assert tracks[2]["subtype"] == "stereo" and tracks[0]["item_count"] == 1
    r = client.post(f"{V1}/timelines/current/tracks", json={"track_type": "audio", "subtype": "5.1", "index": 1})
    assert r.status_code == 200 and r.json()["audio_tracks"] == 2
    assert timeline.tracks["audio"][0]["subtype"] == "5.1"
    r = client.patch(f"{V1}/timelines/current/tracks/video/2", json={"name": "GFX", "locked": True, "enabled": False})
    assert r.json()["track"] == {"type": "video", "index": 2, "name": "GFX", "enabled": False, "locked": True, "subtype": None, "item_count": 1}
    assert client.patch(f"{V1}/timelines/current/tracks/video/9", json={"name": "x"}).status_code == 404
    assert client.delete(f"{V1}/timelines/current/tracks/video/2").json()["remaining"] == 1
    assert client.delete(f"{V1}/timelines/current/tracks/video/7").status_code == 422
    assert client.post(f"{V1}/timelines/current/tracks", json={"track_type": "subtitle"}).json()["subtitle_tracks"] == 1


def test_append_returns_item_ids_and_finds_clips_anywhere(client, project):
    # music.wav lives in the root bin while the current bin is Master too; art.mov is in R3-auto (not current)
    r = client.post(f"{V1}/timelines/current/append", json={"items": [{"clip_name": "art.mov", "track_index": 3, "record_frame": 0}]})
    assert r.status_code == 200 and r.json()["all_ok"] and r.json()["results"][0]["item_id"].startswith("ti-")
    assert project.pool.appended[-1]["recordFrame"] == 108000


def test_delete_and_link_items(client, timeline):
    ids = item_ids(client, "video")
    r = client.post(f"{V1}/timelines/current/link", json={"item_ids": ids, "linked": False})
    assert r.status_code == 200 and timeline.linked_calls[0][1] is False
    r = client.post(f"{V1}/timelines/current/delete-items", json={"item_ids": [ids[0]], "ripple": True})
    assert r.json()["deleted"] == 1 and timeline.last_ripple is True
    assert len(item_ids(client, "video")) == 1
    assert client.post(f"{V1}/timelines/current/delete-items", json={"item_ids": ["nope"]}).status_code == 404


def test_compound_and_fusion_clip(client, timeline):
    ids = item_ids(client, "video")
    r = client.post(f"{V1}/timelines/current/compound", json={"item_ids": ids, "name": "CC"})
    assert r.status_code == 200 and r.json()["item"]["name"] == "CC"
    assert len(item_ids(client, "video")) == 1
    r = client.post(f"{V1}/timelines/current/fusion-clip", json={"item_ids": item_ids(client, "video")})
    assert r.status_code == 200 and r.json()["name"] == "Fusion Clip 1"
    assert client.post(f"{V1}/timelines/current/compound", json={"item_ids": []}).status_code == 404


def test_generators_and_data_driven_title(client, timeline):
    r = client.post(f"{V1}/timelines/current/generators", json={"kind": "generator", "name": "Solid Color"})
    assert r.status_code == 200 and r.json()["name"] == "Solid Color"
    r = client.post(f"{V1}/timelines/current/generators", json={"kind": "fusion_title", "name": "Text+", "text": "Hello, world"})
    assert r.status_code == 200, r.text
    assert r.json()["text"]["results"] == {"StyledText": True}
    title = [it for it in timeline._all_items() if it.GetName() == "Text+"][0]
    assert title.comps[0].tools["Template"].inputs["StyledText"] == "Hello, world"
    assert client.post(f"{V1}/timelines/current/generators", json={"kind": "fusion_title", "name": "Nope"}).status_code == 404
    assert client.post(f"{V1}/timelines/current/generators", json={"kind": "title"}).status_code == 404
    assert client.post(f"{V1}/timelines/current/generators", json={"kind": "fusion_composition"}).status_code == 200


def test_playhead_and_marks(client, timeline):
    assert client.put(f"{V1}/timelines/current/playhead", json={"timecode": "01:00:05:00"}).json()["timecode"] == "01:00:05:00"
    assert client.get(f"{V1}/timelines/current/playhead").json()["timecode"] == "01:00:05:00"
    r = client.put(f"{V1}/timelines/current/mark-in-out", json={"in": 10, "out": 200, "type": "video"})
    assert r.json()["marks"] == {"video": {"in": 10, "out": 200}}
    assert client.delete(f"{V1}/timelines/current/mark-in-out").json()["marks"] == {}


def test_stills_and_thumbnail(client, project):
    assert client.post(f"{V1}/timelines/current/stills", json={}).json()["count"] == 1
    assert client.post(f"{V1}/timelines/current/stills", json={"all_clips": True, "frame_source": "first"}).json()["count"] == 1
    assert len(project.gallery.current.stills) == 3
    assert client.get(f"{V1}/timelines/current/thumbnail").json()["width"] == 2
    png = client.get(f"{V1}/timelines/current/thumbnail.png")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png" and png.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_ai_endpoints(client, timeline):
    r = client.post(f"{V1}/timelines/current/subtitles/auto", json={"language": "english", "preset": "NETFLIX", "chars_per_line": 32, "line_break": "DOUBLE"})
    assert r.status_code == 200 and r.json()["subtitle_tracks"] == 1
    assert timeline.subtitles == {"SUBTITLE_LANGUAGE": 203, "SUBTITLE_CAPTION_PRESET": 302, "SUBTITLE_CHARS_PER_LINE": 32, "SUBTITLE_LINE_BREAK": 311}
    assert client.post(f"{V1}/timelines/current/scene-cuts").json()["ok"] and timeline.scene_cuts
    assert client.post(f"{V1}/timelines/current/stereo").json()["ok"]
    ids = item_ids(client, "video")
    assert client.post(f"{V1}/timelines/current/dolby-vision", json={"item_ids": ids[:1], "blend_shots": True}).json()["ok"]
    assert timeline.dolby[1] == 600
    r = client.put(f"{V1}/timelines/current/voice-isolation/1", json={"enabled": True, "amount": 80})
    assert r.json()["state"] == {"isEnabled": True, "amount": 80}
    assert client.get(f"{V1}/timelines/current/voice-isolation/1").json()["state"]["amount"] == 80
    assert client.put(f"{V1}/timelines/current/voice-isolation/9", json={"enabled": True}).status_code == 422


def test_timeline_markers(client, timeline):
    r = client.post(f"{V1}/timelines/current/markers", json={"frame": 48, "color": "Red", "name": "hook", "duration": 12, "custom_data": "beat-1"})
    assert r.status_code == 200 and r.json()["markers"][0] == {"frame": 48, "color": "Red", "name": "hook", "note": "", "duration": 12.0, "custom_data": "beat-1"}
    assert client.post(f"{V1}/timelines/current/markers", json={"frame": 48}).status_code == 422  # duplicate frame
    client.post(f"{V1}/timelines/current/markers", json={"frame": 96, "color": "Blue"})
    assert client.get(f"{V1}/timelines/current/markers/by-custom-data/beat-1").json()["marker"]["name"] == "hook"
    assert client.get(f"{V1}/timelines/current/markers/by-custom-data/nope").status_code == 404
    assert client.patch(f"{V1}/timelines/current/markers/96/custom-data", json={"custom_data": "beat-2"}).json()["custom_data"] == "beat-2"
    assert client.delete(f"{V1}/timelines/current/markers", params={"color": "Red"}).json()["markers"][0]["frame"] == 96
    assert client.delete(f"{V1}/timelines/current/markers", params={"custom_data": "beat-2"}).json()["markers"] == []
    assert client.delete(f"{V1}/timelines/current/markers").status_code == 404


def test_ripple_insert_at_playhead_shifts_everything(client, timeline):
    # playhead 01:00:01:00 at 30fps -> rel 30; art.mov (60 frames) at V2 rel 30 must shift; spokes at 0 must not
    client.put(f"{V1}/timelines/current/playhead", json={"timecode": "01:00:01:00"})
    r = client.post(f"{V1}/timelines/current/ripple-insert", json={"clip_name": "art.mov", "track_index": 1, "start_frame": 0, "end_frame": 45, "media_type": "video"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["shift"] == 45 and body["inserted"]["start_rel"] == 30 and body["inserted"]["track_index"] == 1
    starts = sorted((i["track_type"], i["track_index"], i["start_rel"]) for i in client.get(f"{V1}/timelines/current/items").json()["items"])
    assert ("video", 2, 75) in starts and ("video", 1, 0) in starts and ("video", 1, 30) in starts
    assert len(body["moved"]) == 1


def test_ripple_insert_length_from_clip_and_single_track(client, timeline):
    # music.wav: 240 frames @24fps on a 30fps timeline -> 300 timeline frames; only the audio track shifts
    r = client.post(f"{V1}/timelines/current/ripple-insert", json={"clip_name": "music.wav", "track_index": 1, "record_frame": 0, "media_type": "audio", "all_tracks": False})
    assert r.status_code == 200, r.text
    assert r.json()["shift"] == 300 and r.json()["moved"][0]["start_rel"] == 300
    video_starts = [i["start_rel"] for i in client.get(f"{V1}/timelines/current/items", params={"track_type": "video"}).json()["items"]]
    assert sorted(video_starts) == [0, 30]  # video untouched
    assert client.post(f"{V1}/timelines/current/ripple-insert", json={"clip_name": "ghost"}).status_code == 404
