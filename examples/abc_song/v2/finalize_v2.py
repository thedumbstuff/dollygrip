"""ABC v2 finish: put the three audio stems on A1-A3, render, QA frames + levels."""
import json, os, subprocess, sys, time
import httpx

BASE = "http://127.0.0.1:4747/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
FF = r"C:/Shwetank/Work/Workspace/softwares/ffmpeg-2025-01-20-git-504df09c34-essentials_build/bin"
info = json.load(open(os.path.join(HERE, "build_info.json")))
T = json.load(open(os.path.join(HERE, "timing.json")))
c = httpx.Client(base_url=BASE, timeout=3600)


def call(method, path, **kw):
    r = c.request(method, path, **kw)
    if r.status_code != 200:
        raise SystemExit(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r.json()


cur = call("GET", "/projects/current")
if cur["name"] != info["project"]:
    call("POST", "/projects/current", json={"name": info["project"]})
call("POST", "/system/background-tasks/disable")

AUD = os.path.join(HERE, "audio")
stems = [("song_master_ducked.wav", 1), ("sfx.wav", 2), ("voice_lift.wav", 3)]
for fn, _ in stems:
    assert os.path.exists(os.path.join(AUD, fn)), fn
if "--no-audio" not in sys.argv:
    tl = call("GET", "/timelines/current")
    have = int(tl.get("audio_tracks") or tl.get("tracks", {}).get("audio") or 1) if isinstance(tl, dict) else 1
    for _ in range(max(0, 3 - have)):
        c.post("/timelines/current/tracks", json={"track_type": "audio"})
    call("POST", "/mediapool/folders", json={"path": "song", "create": True})
    call("POST", "/mediapool/import", json={"paths": [os.path.join(AUD, fn).replace("\\", "/") for fn, _ in stems]})
    res = call("POST", "/timelines/current/append", json={"items": [{"clip_name": fn, "track_index": ti, "record_frame": 0, "media_type": "audio"} for fn, ti in stems]})
    print("audio:", [(r.get("ok"), r.get("error")) for r in res["results"]], flush=True)
    call("POST", "/projects/current/save")

OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
job = call("POST", "/render/jobs", json={"format": "mp4", "codec": "H264", "mode": "single", "settings": {"TargetDir": OUT.replace("\\", "/"), "CustomName": "abc-song-v2", "SelectAllFrames": True, "FormatWidth": 1920, "FormatHeight": 1080, "FrameRate": 30}, "start": True})
t0 = time.time()
done = call("POST", f"/render/jobs/{job['job_id']}/wait", params={"timeout": 3500, "poll": 15})
print("render:", done.get("JobStatus"), f"{time.time() - t0:.0f}s", flush=True)
mp4 = os.path.join(OUT, "abc-song-v2.mp4")
if os.path.exists(mp4):
    print("size MB:", round(os.path.getsize(mp4) / 1e6, 1))
    for t in ("00:00:03", "00:00:11", "00:00:31", "00:01:15", "00:02:37"):
        subprocess.run([f"{FF}/ffmpeg.exe", "-y", "-loglevel", "error", "-ss", t, "-i", mp4, "-frames:v", "1", os.path.join(OUT, f"qa_{t.replace(':', '')}.png")])
    vol = subprocess.run([f"{FF}/ffmpeg.exe", "-i", mp4, "-af", "volumedetect,ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    print("\n".join(l for l in vol.splitlines() if "mean_volume" in l or "max_volume" in l or "I:" in l or "Peak:" in l)[-600:])
