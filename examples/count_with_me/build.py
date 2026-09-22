"""'Count With Me!' - a full kids' music video for a real song, built entirely
through DollyGrip. The whole show is ONE Fusion composition on a black carrier
clip the length of the song, so every element is timed to Whisper's word
timestamps (no 5-second title limit). See README.md in this folder."""

import json
import math
import os
import time

import httpx

BASE = "http://127.0.0.1:4747/api/v1"
SONG_DIR = os.environ.get("CWM_SONG_DIR", "D:/count-with-me")  # song.mp3, carrier.mp4, words.json (see README.md)
OUT = os.environ.get("CWM_OUT_DIR", "D:/count-with-me/out")
FPS = 30
SONG_END = 162.82
PROJECT = "Count With Me (DollyGrip)"
TEXT_FONT, SYM_FONT = "Comic Sans MS", "Segoe UI Symbol"
INK = (0.13, 0.13, 0.25)
WHITE = (1.0, 1.0, 1.0)
GOLD = (1.0, 0.80, 0.12)
PASTELS = [
    (0.99, 0.80, 0.45), (0.55, 0.80, 0.98), (0.70, 0.90, 0.60), (0.98, 0.70, 0.75), (0.80, 0.70, 0.98),
    (0.99, 0.87, 0.50), (0.60, 0.90, 0.85), (0.98, 0.78, 0.60), (0.75, 0.85, 0.98), (0.88, 0.78, 0.95),
]
RAINBOW = ((0.98, 0.72, 0.78), (0.99, 0.87, 0.50), (0.60, 0.90, 0.85), (0.75, 0.80, 0.98))  # TL, TR, BL, BR
NUM_WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
ACTIONS = {
    1: ("touch the sun", "Wave your hands!", "☀"), 2: ("tap your shoe", "Tap, tap, tap!", "♫"), 3: ("bend your knee", "Bounce up high!", "⬆"),
    4: ("touch the floor", "Down and up!", "⬇"), 5: ("hands up high", "Give me five!", "✋"), 6: ("little kicks", "Kick, kick, kick!", "⚽"),
    7: ("reach to heaven", "Stretch up tall!", "☁"), 8: ("feeling great", "Turn around!", "☺"), 9: ("make a line", "Stand up straight!", "▌"),
    10: ("shout again", "ONE TO TEN!", "★"),
}

c = httpx.Client(base_url=BASE, timeout=600)
calls = 0


def call(method, path, **kw):
    global calls
    calls += 1
    r = c.request(method, path, **kw)
    if r.status_code != 200:
        raise SystemExit(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r.json()


def F(sec):
    return int(round(sec * FPS))


# ---------------------------------------------------------------- lyric timing
segs = json.load(open(f"{SONG_DIR}/words.json", encoding="utf-8"))
WORDS = [w for s in segs for w in s["words"]]
cursor = 0


def find(prefix, after=None):
    """Next word (from the cursor) starting with prefix (case-insensitive); advances the cursor."""
    global cursor
    start = cursor if after is None else after
    for i in range(start, len(WORDS)):
        if WORDS[i]["w"].lower().strip(".,!?").startswith(prefix.lower()):
            cursor = i + 1
            return WORDS[i]
    raise SystemExit(f"word {prefix!r} not found after index {start}")


def sentences():
    out, cur = [], []
    for w in WORDS:
        cur.append(w)
        if w["w"].endswith((".", "!", "?")):
            out.append({"text": " ".join(x["w"] for x in cur), "s": cur[0]["s"], "e": cur[-1]["e"]})
            cur = []
    if cur:
        out.append({"text": " ".join(x["w"] for x in cur), "s": cur[0]["s"], "e": cur[-1]["e"]})
    return out


# ---------------------------------------------------------------- comp builder
class Show:
    def __init__(self, comp_path, media_out):
        self.comp, self.media_out = comp_path, media_out
        self.n = 0
        self.chain = None  # name of the tool currently feeding the output

    def _name(self, kind):
        self.n += 1
        return f"{kind}{self.n}"

    def add(self, tool_id, inputs, name=None):
        name = name or self._name(tool_id)
        call("POST", f"{self.comp}/tools", json={"tool_id": tool_id, "name": name, "inputs": {"UseFrameFormatSettings": 1, **inputs}})
        return name

    def keys(self, tool, inp, kf):
        r = call("POST", f"{self.comp}/tools/{tool}/keyframes", json={"input": inp, "keyframes": [{"frame": f, "value": v} for f, v in kf]})
        assert r["all_ok"], (tool, inp, r)

    def expr(self, tool, inp, expression):
        call("PUT", f"{self.comp}/tools/{tool}/expression", json={"input": inp, "expression": expression})

    def layer(self, fg, blend_keys=None, expression=None):
        """Merge fg over the current chain; visibility via Blend keyframes or an expression."""
        if self.chain is None:  # a Merge with no Background outputs nothing - the first layer IS the chain root
            self.chain = fg
            return fg
        m = self._name("M")
        call("POST", f"{self.comp}/tools", json={"tool_id": "Merge", "name": m})
        call("POST", f"{self.comp}/tools/{m}/connect", json={"input": "Background", "source_tool": self.chain})
        call("POST", f"{self.comp}/tools/{m}/connect", json={"input": "Foreground", "source_tool": fg})
        if blend_keys:
            self.keys(m, "Blend", blend_keys)
        if expression:
            self.expr(m, "Blend", expression)
        self.chain = m
        return m

    def finish(self):
        call("POST", f"{self.comp}/tools/{self.media_out}/connect", json={"input": "Input", "source_tool": self.chain})

    # -- helpers ------------------------------------------------------------
    def bg_solid(self, rgb, name=None):
        r, g, b = rgb
        return self.add("Background", {"TopLeftRed": r, "TopLeftGreen": g, "TopLeftBlue": b, "TopLeftAlpha": 1.0}, name)

    def bg_corners(self, tl, tr, bl, br, name=None):
        inputs = {"Type": "Corner", "TopLeftAlpha": 1.0, "TopRightAlpha": 1.0, "BottomLeftAlpha": 1.0, "BottomRightAlpha": 1.0}
        for corner, rgb in (("TopLeft", tl), ("TopRight", tr), ("BottomLeft", bl), ("BottomRight", br)):
            inputs[f"{corner}Red"], inputs[f"{corner}Green"], inputs[f"{corner}Blue"] = rgb
        return self.add("Background", inputs, name)

    def text(self, s, size, center, color=WHITE, font=TEXT_FONT, style="Bold", shadow=False, name=None, extra=None):
        r, g, b = color
        inputs = {"StyledText": s, "Font": font, "Style": style, "Size": size, "Red1": r, "Green1": g, "Blue1": b, "Center": list(center)}
        if shadow:
            inputs.update({"Enabled3": 1})
        if extra:
            inputs.update(extra)
        return self.add("TextPlus", inputs, name)

    def bob(self, tool, x, y, amp=0.012, period=5.0, phase=0.0):
        self.expr(tool, "Center", f"Point({x}, {y} + {amp}*sin(time/{period} + {phase}))")

    def pop(self, tool, t, size, over=8):
        f = F(t)
        self.keys(tool, "Size", [(f, 0.02), (f + over, size * 1.12), (f + over + 5, size)])

    def pop_bumps(self, tool, t, size, bumps=(), over=8):
        f = F(t)
        kf = [(f, 0.02), (f + over, size * 1.12), (f + over + 5, size)]
        for tb in bumps:
            fb = F(tb)
            if fb > kf[-1][0] + 1:
                kf += [(fb, size), (fb + 3, size * 1.18), (fb + 8, size)]
        self.keys(tool, "Size", kf)

    def wobble(self, tool, t, degrees=8, over=10):
        f = F(t)
        self.keys(tool, "AngleZ", [(f, -degrees), (f + over, degrees * 0.4), (f + over + 8, 0)])


def on(t_in, t_out, fade_in=6, fade_out=6):
    """Blend keyframes: visible between t_in and t_out (seconds)."""
    a, b = F(t_in), F(t_out)
    fade_in, fade_out = min(fade_in, max(1, (b - a) // 2)), min(fade_out, max(1, (b - a) // 2))
    return [(a, 0.0), (a + fade_in, 1.0), (b - fade_out, 1.0), (b, 0.0)]


# ---------------------------------------------------------------- project + carrier
existing = call("GET", "/projects")["projects"]
if PROJECT in existing:  # a previous (partial) build - replace it
    r = c.get("/projects/current")
    if r.status_code == 200 and r.json()["name"] == PROJECT:
        call("POST", "/projects/current/close")
    if c.delete(f"/projects/{PROJECT}").status_code != 200:
        PROJECT = PROJECT + " " + time.strftime("%H%M%S")
project = PROJECT
call("POST", "/projects", json={"name": project})
call("POST", "/timelines", json={"name": "count-with-me", "width": 1920, "height": 1080, "fps": FPS, "start_timecode": "00:00:00:00"})
call("POST", "/system/background-tasks/disable")
call("POST", "/system/page", json={"page": "edit"})
call("POST", "/mediapool/folders", json={"path": "song", "create": True})
call("POST", "/mediapool/import", json={"paths": [f"{SONG_DIR}/carrier.mp4", f"{SONG_DIR}/song.mp3"]})
res = call("POST", "/timelines/current/append", json={"items": [
    {"clip_name": "carrier.mp4", "track_index": 1, "record_frame": 0, "media_type": "video"},
    {"clip_name": "song.mp3", "track_index": 1, "record_frame": 0, "media_type": "audio"},
]})
assert res["all_ok"], res
carrier_id = res["results"][0]["item_id"]
call("POST", f"/fusion/items/{carrier_id}/comps", json={})
comp = f"/fusion/items/{carrier_id}/comps/1"
tools = {t["id"]: t["name"] for t in call("GET", f"{comp}/tools")["tools"]}
show = Show(comp, tools["MediaOut"])
print("project", project, "| carrier", carrier_id, "| comp tools", tools, flush=True)

# ---------------------------------------------------------------- 1. backgrounds
base = show.bg_solid((0.05, 0.05, 0.08), "Base")
show.layer(base)
rainbow = show.bg_corners(*RAINBOW, name="Rainbow")
show.layer(rainbow, on(0, 8.7, 20, 12))  # intro

# verse windows: card n = [first "n" word, next card start)
cursor = 0
verse = {}
verse2_idx = [i for i, w in enumerate(WORDS) if w["s"] >= segs[4]["s"]][0]  # verse 2 starts after the chorus segment
for n in range(1, 11):
    if n == 6:
        cursor = verse2_idx  # skip the chorus's "six ... ten"
    w1 = find(NUM_WORDS[n - 1])
    w2 = find(NUM_WORDS[n - 1])
    act = find(ACTIONS[n][0].split()[0])
    line2 = find(ACTIONS[n][1].split()[0].strip("!,"))
    num = find("number")
    last = find(NUM_WORDS[n - 1])
    verse[n] = {"t0": w1["s"], "t1": w2["s"], "act": act["s"], "line2": line2["s"], "num": num["s"], "last": last["s"], "end": last["e"]}
    if n == 5:  # chorus follows
        chorus_start = find("one")["s"]
        cursor -= 1
    if n == 10:
        cursor_after_10 = cursor
starts = {n: verse[n]["t0"] - 0.15 for n in verse}
ends = {n: (starts[n + 1] - 0.25 if n not in (5, 10) else (chorus_start - 0.3 if n == 5 else 109.84 - 0.3)) for n in verse}
for n in range(1, 11):
    bg = show.bg_solid(PASTELS[n - 1], f"Card{n}")
    show.layer(bg, on(starts[n], ends[n], 10, 10))

chorus_bg_on = on(chorus_start - 0.3, verse[6]["t0"] - 0.4, 12, 10)
show.layer(rainbow, chorus_bg_on)  # same rainbow tool can be merged again? no - Fusion tools can feed several merges
big_start = 109.84 - 0.3
outro_start = 135.18 - 0.3
show.layer(rainbow, on(outro_start, SONG_END, 12, 1))

# ---------------------------------------------------------------- 2. intro
title = show.text("Count With Me!", 0.17, (0.5, 0.60), GOLD, shadow=True, name="IntroTitle")
show.bob(title, 0.5, 0.60, 0.015, 6)
show.pop(title, 0.4, 0.17, 12)
show.layer(title, on(0.3, 8.6, 1, 10))
ribbon = show.text("1  2  3  4  5  6  7  8  9  10", 0.075, (0.5, 0.30), INK, name="IntroRibbon")
show.bob(ribbon, 0.5, 0.30, 0.02, 4, 1.5)
show.layer(ribbon, on(1.2, 8.6, 12, 10))

# ---------------------------------------------------------------- 3. verse cards
for n in range(1, 11):
    v = verse[n]
    s, e = starts[n], ends[n]
    a_text, b_text, sym = ACTIONS[n]
    digit = show.text(str(n), 0.5, (0.36, 0.58), WHITE, shadow=True, name=f"Digit{n}")
    show.bob(digit, 0.36, 0.58, 0.012, 5)
    show.pop_bumps(digit, v["t0"], 0.5, bumps=(v["t1"], v["num"], v["last"]))
    show.layer(digit, on(v["t0"], e, 1, 8))
    symbol = show.text(sym, 0.22, (0.70, 0.60), GOLD, font=SYM_FONT, style="Regular", name=f"Sym{n}")
    show.bob(symbol, 0.70, 0.60, 0.02, 4, 2.0)
    show.pop_bumps(symbol, v["act"], 0.22, bumps=(v["line2"],))
    show.layer(symbol, on(v["act"], e, 1, 8))
    a = show.text(a_text, 0.075, (0.5, 0.30), INK, name=f"ActA{n}")
    show.pop(a, v["act"], 0.075, 6)
    show.layer(a, on(v["act"], v["line2"] - 0.05, 1, 4))
    b = show.text(b_text, 0.08, (0.5, 0.30), INK, name=f"ActB{n}")
    show.pop(b, v["line2"], 0.08, 6)
    show.layer(b, on(v["line2"], e, 1, 8))
    stars = show.text(" ".join(["★"] * n) if n <= 5 else " ".join(["★"] * 5) + "\n" + " ".join(["★"] * (n - 5)), 0.06 if n <= 5 else 0.05, (0.5, 0.17), GOLD, font=SYM_FONT, style="Regular", name=f"Stars{n}")
    show.pop_bumps(stars, v["num"], 0.06 if n <= 5 else 0.05, bumps=(v["last"],))
    show.layer(stars, on(v["num"], e, 1, 8))
print("verse cards built", flush=True)

# ---------------------------------------------------------------- 4. chorus (grid of ten)
def counting_grid(tag, t_end, row1_y=0.62, row2_y=0.40, size=0.19):
    """Digits 1..5 pop on their words into a top row, 6..10 into a second row; all stay until t_end."""
    xs = [0.2, 0.35, 0.5, 0.65, 0.8]
    times = []
    for n in range(1, 11):
        w = find(NUM_WORDS[n - 1])
        times.append(w["s"])
        x, y = xs[(n - 1) % 5], row1_y if n <= 5 else row2_y
        d = show.text(str(n), size, (x, y), WHITE if n % 2 else INK, shadow=True, name=f"{tag}D{n}")
        show.bob(d, x, y, 0.014, 3 + (n % 3), n * 0.7)
        show.pop(d, w["s"], size, 6)
        show.wobble(d, w["s"], 10, 8)
        show.layer(d, on(w["s"], t_end, 1, 8))
    return times


chorus_idx = [i for i, w in enumerate(WORDS) if w["s"] >= chorus_start][0]
cursor = chorus_idx
counting_grid("Ch", verse[6]["t0"] - 0.4)
smile = find("smile", after=chorus_idx)
face = show.text("☺", 0.30, (0.5, 0.20), GOLD, font=SYM_FONT, style="Regular", name="ChSmile")
show.pop(face, smile["s"], 0.30, 8)
show.wobble(face, smile["s"], 15, 10)
show.layer(face, on(smile["s"], smile["e"] + 1.8, 1, 8))
clap = find("clap")
hands = show.text("✋   ✋", 0.16, (0.5, 0.20), GOLD, font=SYM_FONT, style="Regular", name="ChHands")
show.pop_bumps(hands, clap["s"], 0.16, bumps=(clap["s"] + 0.35, clap["s"] + 0.7))
show.layer(hands, on(clap["s"], verse[6]["t0"] - 0.4, 1, 8))
print("chorus built", flush=True)

# ---------------------------------------------------------------- 5. big counting chorus: full-screen flashes
cursor = [i for i, w in enumerate(WORDS) if w["s"] >= 109.0][0]
big_times, big_idx = [], {}
for n in range(1, 11):
    w = find(NUM_WORDS[n - 1])
    big_times.append(w["s"])
    big_idx[n] = cursor - 1
extra_five = find("five", after=big_idx[5] + 1)  # the sung repeat, between five and six
cursor = big_idx[10] + 1
counted = find("counted")
ten_end = find("ten")
now = find("now")
one_again = find("one")
again = find("again")
for n in range(1, 11):
    t = big_times[n - 1]
    t_next = big_times[n] if n < 10 else counted["s"] - 0.2
    bg = show.bg_solid(PASTELS[n - 1], f"Flash{n}")
    show.layer(bg, [(F(t) - 1, 0.0), (F(t) + 1, 1.0), (F(t_next) - 1, 1.0), (F(t_next) + 1, 0.0)] if n < 10 else on(t, counted["s"] - 0.2, 2, 10))
    d = show.text(str(n), 0.72, (0.5, 0.56), WHITE, shadow=True, name=f"Big{n}")
    bumps = (extra_five["s"],) if n == 5 else ()
    show.pop_bumps(d, t, 0.72, bumps=bumps, over=6)
    show.wobble(d, t, 12, 8)
    show.layer(d, on(t, t_next, 1, 3))
row = show.text("1  2  3  4  5  6  7  8  9  10", 0.09, (0.5, 0.56), INK, name="BigRow")
show.bob(row, 0.5, 0.56, 0.02, 3)
show.pop(row, counted["s"], 0.09, 8)
show.layer(rainbow, on(counted["s"] - 0.2, 135.18 - 0.3, 6, 8))
show.layer(row, on(counted["s"], now["s"] - 0.1, 1, 6))
restart = show.text("↻  1", 0.22, (0.5, 0.56), GOLD, font=SYM_FONT, style="Regular", name="Restart")
show.pop_bumps(restart, now["s"], 0.22, bumps=(one_again["s"],))
show.layer(restart, on(now["s"], again["e"] + 0.8, 1, 8))
print("big chorus built", flush=True)

# ---------------------------------------------------------------- 6. outro
cursor = [i for i, w in enumerate(WORDS) if w["s"] >= 135.0][0]
counting_grid("Out", 147.4)
slow = find("slow")
fast = find("fast")
for n in range(1, 11):  # slow bob then fast bob on the outro grid
    x, y = [0.2, 0.35, 0.5, 0.65, 0.8][(n - 1) % 5], 0.62 if n <= 5 else 0.40
    show.expr(f"OutD{n}", "Center", f"Point({x}, {y} + iif(time < {F(slow['s'])}, 0.014*sin(time/4 + {n * 0.7}), iif(time < {F(fast['s'])}, 0.03*sin(time/9 + {n * 0.7}), 0.035*sin(time/1.5 + {n * 0.7}))))")
learning = find("learning")
blast = find("blast")
final = show.text("Learning numbers\nis a blast!", 0.12, (0.5, 0.56), GOLD, shadow=True, name="FinalLine")
show.bob(final, 0.5, 0.56, 0.012, 5)
show.pop(final, learning["s"], 0.12, 10)
show.layer(final, on(learning["s"], 152.5, 1, 10))
for i in range(10):  # star burst on "blast"
    ang = 2 * math.pi * i / 10
    x, y = 0.5 + 0.30 * math.cos(ang), 0.56 + 0.34 * math.sin(ang)
    st = show.text("★", 0.09, (x, y), GOLD, font=SYM_FONT, style="Regular", name=f"Burst{i + 1}")
    show.expr(st, "Center", f"Point({0.5 + 0.30 * math.cos(ang)} + {0.08 * math.cos(ang)}*(time-{F(blast['s'])})/40, {0.56 + 0.34 * math.sin(ang)} + {0.08 * math.sin(ang)}*(time-{F(blast['s'])})/40)")
    show.pop(st, blast["s"] + 0.04 * i, 0.09, 6)
    show.layer(st, on(blast["s"] + 0.04 * i, 152.5, 1, 12))
end_title = show.text("Count With Me!", 0.17, (0.5, 0.58), GOLD, shadow=True, name="EndTitle")
show.bob(end_title, 0.5, 0.58, 0.012, 6)
show.pop(end_title, 152.6, 0.17, 12)
show.layer(end_title, on(152.6, SONG_END, 1, 45))
end_sub = show.text("1  2  3  4  5  6  7  8  9  10", 0.07, (0.5, 0.32), INK, name="EndRibbon")
show.bob(end_sub, 0.5, 0.32, 0.02, 4, 1.5)
show.layer(end_sub, on(153.4, SONG_END, 12, 45))
print("outro built", flush=True)

# ---------------------------------------------------------------- 7. captions
sents = sentences()
for i, sn in enumerate(sents):
    nxt = sents[i + 1]["s"] if i + 1 < len(sents) else SONG_END
    t_in, t_out = sn["s"] - 0.1, min(sn["e"] + 0.45, nxt - 0.05)
    in_big = 109.5 <= sn["s"] <= 124.0
    cap = show.text(sn["text"], 0.042, (0.5, 0.06), WHITE if in_big else INK, shadow=in_big, name=f"Cap{i + 1}")
    show.layer(cap, on(t_in, t_out, 4, 4))
print("captions built:", len(sents), flush=True)

# ---------------------------------------------------------------- 8. global fade in / out over black
black = show.bg_solid((0, 0, 0), "FinalBlack")
fader = show._name("M")
call("POST", f"{comp}/tools", json={"tool_id": "Merge", "name": fader})
call("POST", f"{comp}/tools/{fader}/connect", json={"input": "Background", "source_tool": black})
call("POST", f"{comp}/tools/{fader}/connect", json={"input": "Foreground", "source_tool": show.chain})
show.keys(fader, "Blend", [(0, 0.0), (15, 1.0), (F(SONG_END) - 40, 1.0), (F(SONG_END), 0.0)])
show.chain = fader
show.finish()
call("POST", "/projects/current/save")
print("built:", show.n, "tools,", calls, "API calls", flush=True)
json.dump({"project": project, "carrier": carrier_id, "verse": verse, "starts": starts, "ends": ends, "chorus_start": chorus_start, "big": big_times}, open(f"{SONG_DIR}/build_info.json", "w"), indent=1)

# ---------------------------------------------------------------- 9. render
job = call("POST", "/render/jobs", json={"format": "mp4", "codec": "H264", "mode": "single", "settings": {"TargetDir": OUT, "CustomName": "count-with-me", "SelectAllFrames": True, "FormatWidth": 1920, "FormatHeight": 1080, "FrameRate": 30}, "start": True})
done = call("POST", f"/render/jobs/{job['job_id']}/wait", params={"timeout": 1800, "poll": 5})
print("render:", done["JobStatus"], "->", OUT)
