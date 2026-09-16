#!/usr/bin/env bash
# Assemble a two-clip vertical timeline and render it - pure curl.
# Prereqs: Resolve Studio running with a project open, `dollygrip serve` up.
set -euo pipefail
DG=${DG:-http://127.0.0.1:4747/api/v1}
post() { curl -sf -X POST "$DG$1" -H 'content-type: application/json' -d "$2"; echo; }

curl -sf "$DG/health"; echo

post /mediapool/folders '{"path": "auto-edits", "create": true}'
post /mediapool/import  '{"paths": ["D:/shoot/interview.mp4", "D:/shoot/broll.mov"]}'
post /timelines         '{"name": "reel-v1", "width": 1080, "height": 1920, "fps": 30, "extra_video_tracks": 1}'
post /timelines/current/append '{"items": [
  {"clip_name": "interview.mp4", "start_frame": 0, "end_frame": 432, "record_frame": 0},
  {"clip_name": "broll.mov", "track_index": 2, "record_frame": 90}
]}'

JOB=$(post /render/jobs '{"format": "mp4", "codec": "H264",
  "settings": {"TargetDir": "D:/out", "CustomName": "reel-v1", "SelectAllFrames": true,
               "FormatWidth": 1080, "FormatHeight": 1920}}' | python -c 'import sys,json;print(json.load(sys.stdin)["job_id"])')

echo "waiting on render job $JOB"
until [ "$(curl -sf "$DG/render/active" | python -c 'import sys,json;print(json.load(sys.stdin)["rendering"])')" = "False" ]; do
  sleep 2
done
curl -sf "$DG/render/jobs/$JOB"; echo
