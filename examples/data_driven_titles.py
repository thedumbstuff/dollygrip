"""Data-driven titles: one Text+ Fusion title per caption, placed on the
current timeline at the given timecodes, then rendered.

Shows the Fusion surface without any Fusion scripting on your side:
  1. set the playhead
  2. insert a Fusion title (Text+) with the caption text
  3. style it (font/size/color/position) and animate the size in

Run with the gateway up:  uv run dollygrip serve
Then:                     python examples/data_driven_titles.py
"""

import httpx

BASE = "http://127.0.0.1:4747/api/v1"
CAPTIONS = [
    ("00:00:00:15", "Homework, but with a tutor"),
    ("00:00:02:15", "Snap the question"),
    ("00:00:04:15", "Buzz explains, never answers"),
]

with httpx.Client(base_url=BASE, timeout=120) as c:
    for timecode, text in CAPTIONS:
        c.put("/timelines/current/playhead", json={"timecode": timecode}).raise_for_status()
        item = c.post(
            "/timelines/current/generators",
            json={"kind": "fusion_title", "name": "Text+", "text": text},
        ).json()
        item_id = item["item_id"]
        c.post(
            f"/fusion/items/{item_id}/text-plus",
            json={"text": text, "font": "Inter", "style": "Bold", "size": 0.07, "color": [1, 0.84, 0.2], "center": [0.5, 0.22]},
        ).raise_for_status()
        # pop-in: animate Size over the first 10 frames of the title's comp
        c.post(
            f"/fusion/items/{item_id}/comps/1/tools/Template/keyframes",
            json={"input": "Size", "keyframes": [{"frame": 0, "value": 0.0}, {"frame": 10, "value": 0.07}]},
        ).raise_for_status()
        print("title:", text, "->", item_id)

    job = c.post(
        "/render/jobs",
        json={"preset": "H.264 Master", "settings": {"TargetDir": "D:/out", "CustomName": "titled", "SelectAllFrames": True}},
    ).json()
    done = c.post(f"/render/jobs/{job['job_id']}/wait", params={"timeout": 900}).json()
    print("render:", done["JobStatus"], done.get("TimeTakenToRenderInMs"), "ms")
