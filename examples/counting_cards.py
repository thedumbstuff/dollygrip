"""A complete kids' video - "Counting 1 to 10" - built and rendered through
DollyGrip with no footage at all: every card is a Fusion title composed via
the API (Background colour + big digit that pops in + word + one gold star
per number + a dip-to-black fade), inserted back to back on V1, with an
offline text-to-speech voiceover on A1, a soft music bed on A2 and a pop on
each card entrance on A3, burned-in captions that fade in with the voice, an
SRT sidecar, and a second 9:16 timeline re-flowed for vertical safe margins.

    # 1. voice (Windows, offline):  powershell -File examples/counting_voice.ps1 -OutDir D:/counting/voice
    # 2. stems:                     see make_stems() below (ffmpeg) - or drop your own bed.wav / pop.wav in STEMS_DIR
    # 3. gateway:                   dollygrip serve
    # 4. this:                      python examples/counting_cards.py

Follows docs/VIDEO_CRAFT.md: voice first, glyph-safe fonts, safe margins,
entrance motion, whole-card fades, measured audio stems, frame-grab QA.
"""

import os
import shutil
import subprocess
import time
import wave

import httpx

BASE = "http://127.0.0.1:4747/api/v1"
VOICE_DIR = os.environ.get("COUNTING_VOICE_DIR", "D:/counting/voice")  # voice_00_intro.wav, voice_01.wav ... voice_11_outro.wav
STEMS_DIR = os.environ.get("COUNTING_STEMS_DIR", VOICE_DIR)  # bed.wav, pop.wav
OUT_DIR = os.environ.get("COUNTING_OUT_DIR", "D:/counting/out")
FPS = 30
CARD = 150  # Resolve's default Fusion title length (5 s at 30 fps) - cards tile perfectly
FADE = 8  # frames in / out
VOICE_IN = 12  # frames after the card start where the voice (and caption) begin
LINES = ["Let's count together, from one to ten!", "One.", "Two.", "Three.", "Four.", "Five.", "Six.", "Seven.", "Eight.", "Nine.", "Ten!", "Great job! You counted all the way to ten."]

WORDS = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]
PASTELS = [
    (0.99, 0.80, 0.45), (0.55, 0.80, 0.98), (0.70, 0.90, 0.60), (0.98, 0.70, 0.75), (0.80, 0.70, 0.98),
    (0.99, 0.87, 0.50), (0.60, 0.90, 0.85), (0.98, 0.78, 0.60), (0.75, 0.85, 0.98), (0.88, 0.78, 0.95),
]
TEXT_FONT, STAR_FONT = "Comic Sans MS", "Segoe UI Symbol"  # Comic Sans has no star glyph - symbols get their own Text+

c = httpx.Client(base_url=BASE, timeout=600)  # a timeout: a frozen Resolve must not freeze you


def call(method, path, **kw):
    r = c.request(method, path, **kw)
    r.raise_for_status()
    return r.json()


def make_stems(total_seconds: float):
    """Synthesize a soft C-major pad bed (loudnorm to -30 LUFS, fades) and a pop. Needs ffmpeg on PATH."""
    if not shutil.which("ffmpeg"):
        return
    os.makedirs(STEMS_DIR, exist_ok=True)
    fade_out_at = max(0.0, total_seconds - 3.2)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        *sum([["-f", "lavfi", "-i", f"sine=frequency={f}:duration={total_seconds + 1}"] for f in (261.63, 329.63, 392.0, 523.25)], []),
        "-filter_complex", f"[0][1][2][3]amix=inputs=4:normalize=0,tremolo=f=0.25:d=0.35,lowpass=f=900,aecho=0.6:0.4:60|120:0.3|0.2,"
        f"loudnorm=I=-30:TP=-9:LRA=7,afade=t=in:d=1.5,afade=t=out:st={fade_out_at}:d=3.2,atrim=0:{total_seconds},aformat=sample_rates=48000:channel_layouts=stereo",
        f"{STEMS_DIR}/bed.wav",
    ], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=880:duration=0.18",
                    "-af", "afade=t=out:st=0.02:d=0.16,volume=8dB,aformat=sample_rates=48000:channel_layouts=stereo", f"{STEMS_DIR}/pop.wav"], check=True)


def wav_seconds(path):
    try:
        with wave.open(path) as w:
            return w.getnframes() / w.getframerate()
    except (OSError, wave.Error):
        return 1.5


def write_srt(path, cards):
    def tc(sec):
        ms = int(round(sec * 1000))
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(path, "w", encoding="utf-8") as f:
        for i, card in enumerate(cards):
            start = (i * CARD + VOICE_IN) / FPS
            dur = wav_seconds(f"{VOICE_DIR}/voice_{card['key']}.wav")
            f.write(f"{i + 1}\n{tc(start)} --> {tc(start + dur + 0.4)}\n{LINES[i]}\n\n")


def stars(n):
    return " ".join(["★"] * min(n, 5)) + ("\n" + " ".join(["★"] * (n - 5)) if n > 5 else "")


cards = [{"key": "00_intro", "big": "Let's Count!", "word": "from 1 to 10", "stars": "★  ★  ★", "color": (0.36, 0.62, 0.95), "size": 0.18}]
cards += [{"key": f"{i:02d}", "big": str(i), "word": WORDS[i - 1], "stars": stars(i), "color": PASTELS[i - 1], "size": 0.46} for i in range(1, 11)]
cards.append({"key": "11_outro", "big": "Great job!", "word": "You counted to 10", "stars": "★  ★  ★", "color": (0.95, 0.55, 0.45), "size": 0.16})
TOTAL = len(cards) * CARD / FPS

name = "Counting 1 to 10"
if name in call("GET", "/projects")["projects"]:
    name += " " + time.strftime("%H%M%S")
call("POST", "/projects", json={"name": name})
call("POST", "/timelines", json={"name": "counting", "width": 1920, "height": 1080, "fps": FPS, "start_timecode": "00:00:00:00", "extra_audio_tracks": 2})
call("POST", "/system/background-tasks/disable")  # heavy comp edits ahead - avoid fighting Resolve's background renders
call("POST", "/system/page", json={"page": "edit"})

for idx, card in enumerate(cards):
    start = idx * CARD
    tc = call("POST", "/tools/timecode", json={"fps": FPS, "frames": start})["timecode"]
    call("PUT", "/timelines/current/playhead", json={"timecode": tc})
    item_id = call("POST", "/timelines/current/generators", json={"kind": "fusion_title", "name": "Text+", "text": card["big"]})["item_id"]
    comp = f"/fusion/items/{item_id}/comps/1"
    tools = {t["id"]: t["name"] for t in call("GET", f"{comp}/tools")["tools"]}
    digit, media_out = tools["TextPlus"], tools["MediaOut"]
    big_card = card["size"] > 0.3
    call("PATCH", f"{comp}/tools/{digit}/inputs", json={"inputs": {"Font": TEXT_FONT, "Style": "Bold", "Size": card["size"], "Red1": 1, "Green1": 1, "Blue1": 1, "Center": [0.5, 0.64 if big_card else 0.6], "UseFrameFormatSettings": 1}})
    r, g, b = card["color"]
    call("POST", f"{comp}/tools", json={"tool_id": "Background", "name": "Card", "inputs": {"TopLeftRed": r, "TopLeftGreen": g, "TopLeftBlue": b, "TopLeftAlpha": 1.0, "UseFrameFormatSettings": 1}})
    call("POST", f"{comp}/tools", json={"tool_id": "TextPlus", "name": "Words", "inputs": {"StyledText": card["word"], "Font": TEXT_FONT, "Style": "Bold", "Size": 0.09, "Red1": 0.16, "Green1": 0.16, "Blue1": 0.25, "Center": [0.5, 0.30], "UseFrameFormatSettings": 1}})
    two_rows = "\n" in card["stars"]
    call("POST", f"{comp}/tools", json={"tool_id": "TextPlus", "name": "Stars", "inputs": {"StyledText": card["stars"], "Font": STAR_FONT, "Size": 0.075 if two_rows else 0.09, "Red1": 1.0, "Green1": 0.78, "Blue1": 0.10, "Center": [0.5, 0.16 if two_rows else 0.18], "UseFrameFormatSettings": 1}})
    call("POST", f"{comp}/tools", json={"tool_id": "Background", "name": "Black", "inputs": {"TopLeftRed": 0, "TopLeftGreen": 0, "TopLeftBlue": 0, "TopLeftAlpha": 1.0, "UseFrameFormatSettings": 1}})
    # caption = the spoken line, body font, white on the saturated intro/outro, navy on pastels
    white = idx in (0, len(cards) - 1)
    ink = (1.0, 1.0, 1.0) if white else (0.16, 0.16, 0.25)
    call("POST", f"{comp}/tools", json={"tool_id": "TextPlus", "name": "Caption", "inputs": {"StyledText": LINES[idx], "Font": TEXT_FONT, "Style": "Bold", "Size": 0.045, "Red1": ink[0], "Green1": ink[1], "Blue1": ink[2], "Center": [0.5, 0.075], "UseFrameFormatSettings": 1}})
    # chain: Card <- digit <- word <- stars <- caption, then the whole card over black so the fade dips to black
    for merge, bg, fg in (("M1", "Card", digit), ("M2", "M1", "Words"), ("M3", "M2", "Stars"), ("MC", "M3", "Caption"), ("M4", "Black", "MC")):
        call("POST", f"{comp}/tools", json={"tool_id": "Merge", "name": merge})
        call("POST", f"{comp}/tools/{merge}/connect", json={"input": "Background", "source_tool": bg})
        call("POST", f"{comp}/tools/{merge}/connect", json={"input": "Foreground", "source_tool": fg})
    call("POST", f"{comp}/tools/{media_out}/connect", json={"input": "Input", "source_tool": "M4"})
    # motion: digit pops in; caption fades in with the voice; whole card fades in/out (real splines - the endpoint attaches them)
    call("POST", f"{comp}/tools/{digit}/keyframes", json={"input": "Size", "keyframes": [{"frame": 0, "value": 0.02}, {"frame": 10, "value": card["size"]}]})
    call("POST", f"{comp}/tools/MC/keyframes", json={"input": "Blend", "keyframes": [{"frame": 0, "value": 0.0}, {"frame": VOICE_IN, "value": 0.0}, {"frame": VOICE_IN + 8, "value": 1.0}]})
    call("POST", f"{comp}/tools/M4/keyframes", json={"input": "Blend", "keyframes": [{"frame": 0, "value": 0.0}, {"frame": FADE, "value": 1.0}, {"frame": CARD - 1 - FADE, "value": 1.0}, {"frame": CARD - 1, "value": 0.0}]})
    print("card", card["key"], "->", item_id, flush=True)
    time.sleep(0.2)

# audio: voice on A1, bed on A2, pops on A3
make_stems(TOTAL)
call("POST", "/mediapool/folders", json={"path": "audio", "create": True})
paths = [f"{VOICE_DIR}/voice_{card['key']}.wav" for card in cards]
if os.path.isfile(f"{STEMS_DIR}/bed.wav"):
    paths += [f"{STEMS_DIR}/bed.wav", f"{STEMS_DIR}/pop.wav"]
call("POST", "/mediapool/import", json={"paths": paths})
items = [{"clip_name": f"voice_{card['key']}.wav", "track_index": 1, "record_frame": idx * CARD + 12, "media_type": "audio"} for idx, card in enumerate(cards)]
if os.path.isfile(f"{STEMS_DIR}/bed.wav"):
    items.append({"clip_name": "bed.wav", "track_index": 2, "record_frame": 0, "media_type": "audio"})
    items += [{"clip_name": "pop.wav", "track_index": 3, "record_frame": idx * CARD, "media_type": "audio"} for idx in range(len(cards))]
call("POST", "/timelines/current/append", json={"items": items})
for i, label in enumerate(("Voice", "Music", "SFX"), start=1):
    call("PATCH", f"/timelines/current/tracks/audio/{i}", json={"name": label})
call("POST", "/projects/current/save")

def render(custom_name, width, height):
    job = call("POST", "/render/jobs", json={"format": "mp4", "codec": "H264", "mode": "single", "settings": {"TargetDir": OUT_DIR, "CustomName": custom_name, "SelectAllFrames": True, "FormatWidth": width, "FormatHeight": height, "FrameRate": 30}, "start": True})
    done = call("POST", f"/render/jobs/{job['job_id']}/wait", params={"timeout": 900})
    print("render:", custom_name, done["JobStatus"], "->", OUT_DIR)


render("counting-1-to-10-16x9", 1920, 1080)
write_srt(f"{OUT_DIR}/counting-1-to-10-16x9.srt", cards)

# --- 9:16 version: duplicate, resize (comps follow the frame format), re-flow for vertical safe margins
call("POST", "/timelines/current/duplicate", json={"name": "counting-9x16"})
call("POST", "/timelines/current", json={"name": "counting-9x16"})
call("PATCH", "/timelines/current/settings", json={"settings": {"timelineResolutionWidth": "1080", "timelineResolutionHeight": "1920"}})
vcards = sorted((i for i in call("GET", "/timelines/current/items", params={"track_type": "video"})["items"] if i["track_index"] == 1), key=lambda i: i["start_rel"])
for idx, item in enumerate(vcards):
    comp = f"/fusion/items/{item['id']}/comps/1"
    big = 0 < idx < len(vcards) - 1
    two_rows = big and idx > 5
    call("PATCH", f"{comp}/tools/Template/inputs", json={"inputs": {"Center": [0.5, 0.60 if big else 0.58]}})
    call("PATCH", f"{comp}/tools/Words/inputs", json={"inputs": {"Center": [0.5, 0.42], "Size": 0.11}})
    call("PATCH", f"{comp}/tools/Stars/inputs", json={"inputs": {"Center": [0.5, 0.33 if two_rows else 0.35], "Size": 0.085 if two_rows else 0.1}})
    call("PATCH", f"{comp}/tools/Caption/inputs", json={"inputs": {"Center": [0.5, 0.25], "Size": 0.06}})  # bottom 20% stays free for platform UI
    time.sleep(0.1)
call("POST", "/projects/current/save")
render("counting-1-to-10-9x16", 1080, 1920)
write_srt(f"{OUT_DIR}/counting-1-to-10-9x16.srt", vcards)
print("QA: probe both files, grab frames at a cut (t=4.9s, 5.1s) and at the outro, measure levels - see docs/VIDEO_CRAFT.md section 4")
