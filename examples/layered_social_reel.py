"""The pipeline DollyGrip was born from: a layered vertical social reel.

V1 = spokesperson video (24fps source!) + animated end card
V2 = full-length alpha graphics overlay (qtrle mov)
V3 = one alpha clip PER SUBTITLE SENTENCE, so any sentence can be nudged
     by hand in Resolve afterwards
A2 = synthesized SFX bed

Run: python examples/layered_social_reel.py
"""

import time
import urllib.request
import json

DG = "http://127.0.0.1:4747/api/v1"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        DG + path, data=data, method=method,
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


ASSETS = "D:/reels/r8"
SUBTITLE_SENTENCES = [  # (file, 0-based timeline frame where it starts)
    ("sub-s0.mov", 2), ("sub-s1.mov", 95), ("sub-s2.mov", 136),
    ("sub-s3.mov", 259), ("sub-s4.mov", 404), ("sub-s5.mov", 440),
]

call("POST", "/mediapool/folders", {"path": "reel-assets", "create": True})
call("POST", "/mediapool/import", {
    "paths": [f"{ASSETS}/{name}" for name in
              ["spokesperson.mp4", "endcard.mov", "graphics.mov", "sfx.wav"]
              + [s[0] for s in SUBTITLE_SENTENCES]]})

call("POST", "/timelines", {
    "name": f"reel_{time.strftime('%H%M%S')}",
    "width": 1080, "height": 1920, "fps": 30,
    "extra_video_tracks": 2, "extra_audio_tracks": 1,
})

items = [
    # 433 frames at the SOURCE's 24fps = 18.04s = 541 timeline frames at 30fps
    {"clip_name": "spokesperson.mp4", "start_frame": 0, "end_frame": 432, "record_frame": 0},
    {"clip_name": "endcard.mov", "start_frame": 0, "end_frame": 89, "record_frame": 541},
    {"clip_name": "graphics.mov", "start_frame": 0, "end_frame": 540, "track_index": 2, "record_frame": 0},
]
items += [{"clip_name": name, "track_index": 3, "record_frame": frame}
          for name, frame in SUBTITLE_SENTENCES]
items.append({"clip_name": "sfx.wav", "track_index": 2, "record_frame": 0, "media_type": "audio"})
print(call("POST", "/timelines/current/append", {"items": items}))

job = call("POST", "/render/jobs", {
    "format": "mp4", "codec": "H264",
    "settings": {"TargetDir": ASSETS, "CustomName": "reel-final",
                 "SelectAllFrames": True, "FormatWidth": 1080, "FormatHeight": 1920},
})
print("render job:", job["job_id"])
while call("GET", "/render/active")["rendering"]:
    time.sleep(2)
print(call("GET", f"/render/jobs/{job['job_id']}"))
# Tip: if the SFX bed extended the timeline, trim the render:
#   ffmpeg -i reel-final.mp4 -t 21.0 -c copy reel-final-trimmed.mp4
