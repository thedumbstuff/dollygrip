"""A complete kids' video - "Counting 1 to 10" - built and rendered through
DollyGrip with no footage at all: every card is a Fusion title composed via
the API (Background colour + big animated digit + word + one star per
number), inserted back to back on V1, with an offline text-to-speech
voiceover on A1.

    # 1. voice (Windows, offline):  powershell -File examples/counting_voice.ps1  (or any TTS -> voice_XX.wav)
    # 2. gateway:                   dollygrip serve
    # 3. this:                      python examples/counting_cards.py

Adjust VOICE_DIR / OUT_DIR below. Requires Resolve Studio running.
"""

import os
import time

import httpx

BASE = "http://127.0.0.1:4747/api/v1"
VOICE_DIR = os.environ.get("COUNTING_VOICE_DIR", "D:/counting/voice")  # voice_00_intro.wav, voice_01.wav ... voice_11_outro.wav
OUT_DIR = os.environ.get("COUNTING_OUT_DIR", "D:/counting/out")
FPS = 30
CARD = 150  # Resolve's default Fusion title length (5 s at 30 fps) - cards tile perfectly

WORDS = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]
PASTELS = [
    (0.99, 0.80, 0.45), (0.55, 0.80, 0.98), (0.70, 0.90, 0.60), (0.98, 0.70, 0.75), (0.80, 0.70, 0.98),
    (0.99, 0.87, 0.50), (0.60, 0.90, 0.85), (0.98, 0.78, 0.60), (0.75, 0.85, 0.98), (0.88, 0.78, 0.95),
]
TEXT_FONT, STAR_FONT = "Comic Sans MS", "Segoe UI Symbol"  # Comic Sans has no star glyph - symbols get their own Text+

c = httpx.Client(base_url=BASE, timeout=900)


def call(method, path, **kw):
    r = c.request(method, path, **kw)
    r.raise_for_status()
    return r.json()


def stars(n):
    return " ".join(["★"] * min(n, 5)) + ("\n" + " ".join(["★"] * (n - 5)) if n > 5 else "")


cards = [{"key": "00_intro", "big": "Let's Count!", "word": "from 1 to 10", "stars": "★  ★  ★", "color": (0.36, 0.62, 0.95), "size": 0.18}]
cards += [{"key": f"{i:02d}", "big": str(i), "word": WORDS[i - 1], "stars": stars(i), "color": PASTELS[i - 1], "size": 0.46} for i in range(1, 11)]
cards.append({"key": "11_outro", "big": "Great job!", "word": "You counted to 10", "stars": "★  ★  ★", "color": (0.95, 0.55, 0.45), "size": 0.16})

name = "Counting 1 to 10"
if name in call("GET", "/projects")["projects"]:
    name += " " + time.strftime("%H%M%S")
call("POST", "/projects", json={"name": name})
call("POST", "/timelines", json={"name": "counting", "width": 1920, "height": 1080, "fps": FPS, "start_timecode": "00:00:00:00"})

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
    for merge, bg, fg in (("M1", "Card", digit), ("M2", "M1", "Words"), ("M3", "M2", "Stars")):
        call("POST", f"{comp}/tools", json={"tool_id": "Merge", "name": merge})
        call("POST", f"{comp}/tools/{merge}/connect", json={"input": "Background", "source_tool": bg})
        call("POST", f"{comp}/tools/{merge}/connect", json={"input": "Foreground", "source_tool": fg})
    call("POST", f"{comp}/tools/{media_out}/connect", json={"input": "Input", "source_tool": "M3"})
    call("POST", f"{comp}/tools/{digit}/keyframes", json={"input": "Size", "keyframes": [{"frame": 0, "value": 0.0}, {"frame": 10, "value": card["size"]}]})  # pop-in
    print("card", card["key"], "->", item_id)

call("POST", "/mediapool/folders", json={"path": "voice", "create": True})
call("POST", "/mediapool/import", json={"paths": [f"{VOICE_DIR}/voice_{card['key']}.wav" for card in cards]})
call("POST", "/timelines/current/append", json={"items": [
    {"clip_name": f"voice_{card['key']}.wav", "track_index": 1, "record_frame": idx * CARD + 12, "media_type": "audio"} for idx, card in enumerate(cards)
]})
call("POST", "/projects/current/save")

job = call("POST", "/render/jobs", json={"format": "mp4", "codec": "H264", "mode": "single", "settings": {"TargetDir": OUT_DIR, "CustomName": "counting-1-to-10", "SelectAllFrames": True, "FormatWidth": 1920, "FormatHeight": 1080, "FrameRate": 30}, "start": True})
done = call("POST", f"/render/jobs/{job['job_id']}/wait", params={"timeout": 900})
print("render:", done["JobStatus"], "->", OUT_DIR)
