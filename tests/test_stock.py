import json

import pytest

from dollygrip.broll import plan_shots, total_duration
from dollygrip.stock import Material, StockClient, StockError, keys_from_env

PEXELS = {
    "videos": [
        {"id": 1, "width": 1080, "height": 1920, "duration": 12, "url": "https://pexels.com/v/1", "user": {"name": "Ann"},
         "video_files": [
             {"id": 11, "file_type": "video/mp4", "width": 720, "height": 1280, "fps": 30, "link": "https://cdn/1-720.mp4"},
             {"id": 12, "file_type": "video/mp4", "width": 1080, "height": 1920, "fps": 30, "link": "https://cdn/1-1080.mp4"},
             {"id": 13, "file_type": "video/mp4", "width": 2160, "height": 3840, "fps": 30, "link": "https://cdn/1-4k.mp4"},
         ]},
        {"id": 2, "width": 1920, "height": 1080, "duration": 9, "url": "", "user": {},
         "video_files": [{"id": 21, "file_type": "video/mp4", "width": 1920, "height": 1080, "link": "https://cdn/2.mp4"}]},  # landscape - filtered out
        {"id": 3, "width": 720, "height": 1280, "duration": 2, "url": "", "user": {},
         "video_files": [{"id": 31, "file_type": "video/mp4", "width": 720, "height": 1280, "link": "https://cdn/3.mp4"}]},  # too short
        {"id": 4, "width": 720, "height": 1280, "duration": 7, "url": "", "user": {},
         "video_files": [{"id": 41, "file_type": "video/mp4", "width": 720, "height": 1280, "link": "https://cdn/4.mp4"}]},  # only a small rendition - kept, largest
    ]
}
PIXABAY = {"hits": [{"id": 77, "pageURL": "https://pixabay.com/v/77", "duration": 15, "user": "Bob",
                     "videos": {"large": {"url": "https://px/77-l.mp4", "width": 1080, "height": 1920},
                                "medium": {"url": "https://px/77-m.mp4", "width": 720, "height": 1280}}}]}
COVERR = {"hits": [{"id": "c1", "urls": {"mp4": "https://coverr/c1.mp4"}, "max_width": 1080, "max_height": 1920, "duration": 8, "url": "https://coverr.co/c1"}]}


def make_client(tmp_path, calls=None, keys=None):
    calls = calls if calls is not None else []

    def fetch(url, params, headers):
        calls.append((url, params, headers))
        if "pexels" in url:
            return PEXELS
        if "pixabay" in url:
            return PIXABAY
        return COVERR

    def download(url, dest):
        dest.write_bytes(b"\x00" * 16)

    return StockClient(media_dir=tmp_path, keys=keys or {"pexels": ["k1", "k2"], "pixabay": ["p"], "coverr": ["c"]}, fetch=fetch, download=download)


def test_keys_from_env():
    assert keys_from_env("pexels", {"PEXELS_API_KEY": "a"}) == ["a"]
    assert keys_from_env("pexels", {"DOLLYGRIP_PEXELS_KEYS": "a, b"}) == ["a", "b"]
    assert keys_from_env("coverr", {}) == []


def test_pexels_search_filters_and_picks_rendition(tmp_path):
    calls = []
    c = make_client(tmp_path, calls)
    mats = c.search("city night", "pexels", "portrait", min_duration=3)
    assert [m.id for m in mats] == ["1", "4"]
    assert mats[0].url == "https://cdn/1-1080.mp4" and mats[0].width == 1080 and mats[0].fps == 30 and mats[0].author == "Ann"
    assert mats[1].width == 720  # best available when nothing reaches 1080
    assert calls[0][1] == {"query": "city night", "per_page": 20, "orientation": "portrait"} and calls[0][2] == {"Authorization": "k1"}
    # cache: second identical search makes no HTTP call; keys rotate on new terms
    c.search("city night", "pexels", "portrait", min_duration=3)
    assert len(calls) == 1
    c.search("rain", "pexels", "portrait", min_duration=3)
    assert calls[1][2] == {"Authorization": "k2"}
    # cache persists on disk
    assert (tmp_path / ".dollygrip-stock-cache.json").is_file()
    again = make_client(tmp_path, calls)
    again.search("city night", "pexels", "portrait", min_duration=3)
    assert len(calls) == 2


def test_pixabay_and_coverr(tmp_path):
    c = make_client(tmp_path)
    px = c.search("forest", "pixabay", "portrait", 3)
    assert px[0].url == "https://px/77-l.mp4" and px[0].author == "Bob" and px[0].duration == 15
    cv = c.search("ocean", "coverr", "portrait", 3)
    assert cv[0].url == "https://coverr/c1.mp4" and cv[0].aspect == "portrait"
    assert c.providers() == {"pexels": True, "pixabay": True, "coverr": True}


def test_missing_key_and_bad_args(tmp_path):
    c = make_client(tmp_path, keys={"pexels": [], "pixabay": [], "coverr": []})
    with pytest.raises(StockError, match="PEXELS_API_KEY"):
        c.search("x", "pexels")
    with pytest.raises(StockError):
        c.search("x", "vimeo")
    with pytest.raises(StockError):
        c.search("x", "pexels", aspect="wide")


def test_search_many_dedups_and_download_records(tmp_path):
    c = make_client(tmp_path)
    by_term = c.search_many(["a", "b"], "pexels", "portrait", 3)
    assert [m.id for m in by_term["a"]] == ["1", "4"] and by_term["b"] == []  # same fake results -> deduped away
    m = c.download(by_term["a"][0])
    assert m.file.endswith("pexels-1-1080x1920.mp4") and (tmp_path / "pexels-1-1080x1920.json").is_file()
    record = json.loads((tmp_path / "pexels-1-1080x1920.json").read_text())
    assert record["provider"] == "pexels" and record["term"] == "a" and "file" not in record
    # second download is a no-op (file exists)
    c.download(by_term["a"][0])


def _mats(spec):
    """spec: list of (term, id, duration)"""
    out = {}
    for term, mid, dur in spec:
        out.setdefault(term, []).append(Material("pexels", str(mid), term, f"u{mid}", 1080, 1920, dur, file=f"/m/{mid}.mp4"))
    return out


def test_plan_script_order_round_robins_and_covers_audio():
    shots = plan_shots(_mats([("intro", 1, 12), ("intro", 2, 4), ("middle", 3, 7), ("end", 4, 6)]), audio_duration=30, max_clip_duration=5, mode="script_order")
    # primaries first, round-robin across terms: intro(1) middle(3) end(4) intro(2) then overflow segments
    assert [s.material_id for s in shots[:4]] == ["1", "3", "4", "2"]
    assert shots[0].source_in == 0 and shots[0].source_out == 5 and shots[0].record_at == 0
    assert shots[1].record_at == 5
    assert total_duration(shots) == pytest.approx(30.1, abs=1e-6)  # audio + 0.1 padding
    assert all(s.duration <= 5 for s in shots) and shots[-1].duration < 5  # last one trimmed to the end
    # record positions are contiguous
    for a, b in zip(shots, shots[1:]):
        assert b.record_at == pytest.approx(a.record_at + a.duration)


def test_plan_random_is_seeded_and_loops_when_short():
    mats = _mats([("a", 1, 4), ("b", 2, 3)])
    s1 = plan_shots(mats, audio_duration=20, mode="random", seed=7)
    s2 = plan_shots(mats, audio_duration=20, mode="random", seed=7)
    assert [x.material_id for x in s1] == [x.material_id for x in s2]
    assert any(s.looped for s in s1) and total_duration(s1) == pytest.approx(20.1)
    assert {s.material_id for s in s1[:2]} == {"1", "2"}  # both sources appear before any repeat


def test_plan_keeps_tails_and_validates():
    shots = plan_shots(_mats([("a", 1, 6.5)]), audio_duration=6, max_clip_duration=5)
    # 6.5 s source -> one 6.5 s segment (1.5 s tail merged because it is < min_tail? no: 1.5 >= 1.0 -> two segments)
    assert [(s.source_in, s.source_out) for s in shots] == [(0, 5), (5, 6.1)]
    shots = plan_shots(_mats([("a", 1, 5.5)]), audio_duration=5.4, max_clip_duration=5)
    assert [(s.source_in, s.source_out) for s in shots] == [(0, 5.5)]  # 0.5 s tail merged into the segment
    assert plan_shots({}, audio_duration=5) == []
    with pytest.raises(ValueError):
        plan_shots(_mats([("a", 1, 5)]), audio_duration=0)
    with pytest.raises(ValueError):
        plan_shots(_mats([("a", 1, 5)]), audio_duration=5, mode="chaos")
