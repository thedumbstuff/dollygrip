"""'ABC Song' - animated alphabet music video built through DollyGrip.

V1: one real stock clip per letter (Pexels/Pixabay via the gateway), placed by
/stock/assemble at the letter's sung window.  V2: a black carrier with ONE
Fusion comp whose root is transparent - flash-card panel on the left with the
big letter (pop + wobble), lowercase letter, the word sliding in; a dark
gradient band and the lyric caption at the bottom; rainbow chorus cards with
the letters bouncing; a dancing alphabet grid on the instrumental bridge and
the finale; intro and 'Thanks for watching' end card. Timed to Whisper words."""

import json
import math
import os
import time

import httpx

BASE = "http://127.0.0.1:4747/api/v1"
ABC = os.environ.get("ABC_DIR", "D:/abc-song")  # song.mp3, carrier.mp4, words.json, clips.json (see README.md)
FPS = 30
SONG_END = 159.63
PROJECT = "ABC Song (DollyGrip)"
TEXT_FONT, SYM_FONT = "Comic Sans MS", "Segoe UI Symbol"
INK = (0.13, 0.13, 0.25)
WHITE = (1.0, 1.0, 1.0)
GOLD = (1.0, 0.80, 0.12)
PASTELS = [(0.99, 0.80, 0.45), (0.55, 0.80, 0.98), (0.70, 0.90, 0.60), (0.98, 0.70, 0.75), (0.80, 0.70, 0.98), (0.99, 0.87, 0.50), (0.60, 0.90, 0.85), (0.98, 0.78, 0.60), (0.75, 0.85, 0.98), (0.88, 0.78, 0.95)]
RAINBOW = ((0.98, 0.72, 0.78), (0.99, 0.87, 0.50), (0.60, 0.90, 0.85), (0.75, 0.80, 0.98))
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# object-word prefixes as Whisper hears them (anchor of each letter line)
ANCHORS = {"A": "apple", "B": "bear", "C": "cat", "D": "dog", "E": "elephant", "F": "fish", "G": "goat", "H": "hat", "I": "ice", "J": "jelly", "K": "kite", "L": "lion",
           "M": "moon", "N": "ne", "O": "orange", "P": "penguin", "Q": "queen", "R": "rabbit", "S": "sun", "T": "train", "U": "umbrella", "V": "violin", "W": "whale",
           "X": "xylophone", "Y": "yo", "Z": "zebra"}
WORDS = {"A": "Apple", "B": "Bear", "C": "Cat", "D": "Dog", "E": "Elephant", "F": "Fish", "G": "Goat", "H": "Hat", "I": "Ice cream", "J": "Jelly", "K": "Kite", "L": "Lion", "M": "Moon",
         "N": "Nest", "O": "Orange", "P": "Penguin", "Q": "Queen", "R": "Rabbit", "S": "Sun", "T": "Train", "U": "Umbrella", "V": "Violin", "W": "Whale", "X": "Xylophone", "Y": "Yo-yo", "Z": "Zebra"}

c = httpx.Client(base_url=BASE, timeout=900)
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


# ---------------------------------------------------------------- timing from the transcript
segs = json.load(open(f"{ABC}/words.json", encoding="utf-8"))
WORDS_T = [w for s in segs for w in s["words"]]
clips = json.load(open(f"{ABC}/clips.json", encoding="utf-8"))
cursor = 0


def find(prefix, after=None, exact=False):
    global cursor
    start = cursor if after is None else after
    for i in range(start, len(WORDS_T)):
        tok = WORDS_T[i]["w"].lower().strip(".,!?-\"'")
        if (tok == prefix.lower()) if exact else tok.startswith(prefix.lower()):
            cursor = i + 1
            return WORDS_T[i]
    raise SystemExit(f"word {prefix!r} not found after {start}")


def sentences():
    out, cur = [], []
    for w in WORDS_T:
        cur.append(w)
        if w["w"].endswith((".", "!", "?")):
            out.append({"text": " ".join(x["w"] for x in cur), "s": cur[0]["s"], "e": cur[-1]["e"]})
            cur = []
    if cur:
        out.append({"text": " ".join(x["w"] for x in cur), "s": cur[0]["s"], "e": cur[-1]["e"]})
    return out


# letter lines: anchor = object word; the letter is sung ~1 s before it
anchor = {}
for L in LETTERS:
    anchor[L] = find(ANCHORS[L])["s"]
# chorus / bridge / finale markers
CH = [(28.10, 37.58), (60.08, 70.00), (129.34, 139.14)]
BRIDGE = (70.6, 82.6)
FINALE = (139.6, 156.4)
THANKS = find("thanks")["s"]

win = {}
for i, L in enumerate(LETTERS):
    t_in = anchor[L] - 1.05
    nxt = anchor[LETTERS[i + 1]] - 1.05 if i < 25 else 125.6
    # a chorus between two letters ends the window early
    for a, b in CH:
        if t_in < a < nxt:
            nxt = a - 0.3
    win[L] = (round(t_in, 2), round(nxt, 2))
print("windows:", {L: win[L] for L in "ABHIPQZ"}, flush=True)

# ---------------------------------------------------------------- comp builder (transparent root)
class Show:
    def __init__(self, comp_path, media_out):
        self.comp, self.media_out, self.n, self.chain = comp_path, media_out, 0, None

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

    def connect(self, tool, inp, src):
        call("POST", f"{self.comp}/tools/{tool}/connect", json={"input": inp, "source_tool": src})

    def layer(self, fg, blend_keys=None, expression=None):
        if self.chain is None:
            self.chain = fg
            return fg
        m = self._name("M")
        call("POST", f"{self.comp}/tools", json={"tool_id": "Merge", "name": m})
        self.connect(m, "Background", self.chain)
        self.connect(m, "Foreground", fg)
        if blend_keys:
            self.keys(m, "Blend", blend_keys)
        if expression:
            self.expr(m, "Blend", expression)
        self.chain = m
        return m

    def finish(self):
        self.connect(self.media_out, "Input", self.chain)

    def bg_solid(self, rgb, alpha=1.0, name=None):
        r, g, b = rgb
        return self.add("Background", {"TopLeftRed": r, "TopLeftGreen": g, "TopLeftBlue": b, "TopLeftAlpha": alpha}, name)

    def bg_corners(self, tl, tr, bl, br, name=None):
        inputs = {"Type": "Corner", "TopLeftAlpha": 1.0, "TopRightAlpha": 1.0, "BottomLeftAlpha": 1.0, "BottomRightAlpha": 1.0}
        for corner, rgb in (("TopLeft", tl), ("TopRight", tr), ("BottomLeft", bl), ("BottomRight", br)):
            inputs[f"{corner}Red"], inputs[f"{corner}Green"], inputs[f"{corner}Blue"] = rgb
        return self.add("Background", inputs, name)

    def text(self, s, size, center, color=WHITE, font=TEXT_FONT, style="Bold", shadow=False, name=None, extra=None):
        r, g, b = color
        inputs = {"StyledText": s, "Font": font, "Style": style, "Size": size, "Red1": r, "Green1": g, "Blue1": b, "Center": list(center)}
        if shadow:
            inputs["Enabled3"] = 1
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

    def slide_in(self, tool, t, x_from, x_to, y, over=10):
        f = F(t)
        self.keys(tool, "Center", [(f, [x_from, y]), (f + over, [x_to + 0.01, y]), (f + over + 4, [x_to, y])])


def on(t_in, t_out, fade_in=6, fade_out=6):
    a, b = F(t_in), F(t_out)
    fade_in, fade_out = min(fade_in, max(1, (b - a) // 2)), min(fade_out, max(1, (b - a) // 2))
    return [(a, 0.0), (a + fade_in, 1.0), (b - fade_out, 1.0), (b, 0.0)]


# ---------------------------------------------------------------- project, tracks, song, footage
existing = call("GET", "/projects")["projects"]
if PROJECT in existing:
    r = c.get("/projects/current")
    if r.status_code == 200 and r.json()["name"] == PROJECT:
        call("POST", "/projects/current/close")
    if c.delete(f"/projects/{PROJECT}").status_code != 200:
        PROJECT = PROJECT + " " + time.strftime("%H%M%S")
call("POST", "/projects", json={"name": PROJECT})
call("POST", "/timelines", json={"name": "abc-song", "width": 1920, "height": 1080, "fps": FPS, "start_timecode": "00:00:00:00", "extra_video_tracks": 1})
call("POST", "/system/background-tasks/disable")
call("POST", "/system/page", json={"page": "edit"})
call("POST", "/mediapool/folders", json={"path": "song", "create": True})
call("POST", "/mediapool/import", json={"paths": [f"{ABC}/carrier.mp4", f"{ABC}/song.mp3"]})
res = call("POST", "/timelines/current/append", json={"items": [
    {"clip_name": "carrier.mp4", "track_index": 2, "record_frame": 0, "media_type": "video"},
    {"clip_name": "song.mp3", "track_index": 1, "record_frame": 0, "media_type": "audio"},
]})
assert res["all_ok"], res
carrier_id = res["results"][0]["item_id"]

# stock clips on V1 at each letter window (fill framing); letters without a clip get a full pastel card in the comp
shots, missing = [], []
for L in LETTERS:
    info = clips.get(L) or {}
    t_in, t_out = win[L]
    if not info.get("file"):
        missing.append(L)
        continue
    length = min(t_out - t_in, float(info["duration"]) - 0.1)
    shots.append({"file": info["file"], "source_in": 0.0, "source_out": round(length, 3), "record_at": t_in, "term": info.get("term", ""), "provider": info["provider"], "material_id": info["id"]})
asm = call("POST", "/stock/assemble", json={"shots": shots, "track_index": 1, "bin": "stock", "fit": "fill"})
print("footage placed:", sum(1 for e in asm["items"] if e["ok"]), "/", len(shots), "missing:", missing, flush=True)

# ---------------------------------------------------------------- the overlay comp
call("POST", f"/fusion/items/{carrier_id}/comps", json={})
comp = f"/fusion/items/{carrier_id}/comps/1"
tools = {t["id"]: t["name"] for t in call("GET", f"{comp}/tools")["tools"]}
show = Show(comp, tools["MediaOut"])
root = show.bg_solid((0, 0, 0), alpha=0.0, name="Clear")  # transparent root: V1 footage shows through
show.layer(root)
rainbow = show.bg_corners(*RAINBOW, name="Rainbow")

# full-frame pastel cards for letters with no footage
for L in missing:
    t_in, t_out = win[L]
    card = show.bg_solid(PASTELS[LETTERS.index(L) % 10], name=f"Card{L}")
    show.layer(card, on(t_in, t_out, 6, 6))

# caption band: dark vertical gradient at the bottom, always on during singing
shade = show.add("Background", {"Type": "Vertical", "TopLeftRed": 0.05, "TopLeftGreen": 0.05, "TopLeftBlue": 0.1, "TopLeftAlpha": 0.0, "BottomLeftRed": 0.05, "BottomLeftGreen": 0.05, "BottomLeftBlue": 0.1, "BottomLeftAlpha": 0.85}, name="Shade")
show.layer(shade, on(8.2, 126.0, 12, 12))

# flash-card panel: pastel rectangle on the left third via a RectangleMask on a Background
for i, L in enumerate(LETTERS):
    t_in, t_out = win[L]
    col = PASTELS[i % 10]
    panel = show.bg_solid(col, alpha=0.94, name=f"Panel{L}")
    mask = show.add("RectangleMask", {"Center": [0.19, 0.5], "Width": 0.34, "Height": 0.86, "CornerRadius": 0.05, "SoftEdge": 0.002}, name=f"PanelMask{L}")
    show.connect(panel, "EffectMask", mask)
    show.layer(panel, on(t_in, t_out, 6, 6))
    big = show.text(L, 0.30, (0.19, 0.63), WHITE, shadow=True, name=f"Big{L}")
    show.bob(big, 0.19, 0.63, 0.01, 5, i * 0.4)
    show.pop_bumps(big, t_in + 0.05, 0.30, bumps=(anchor[L],))
    show.wobble(big, t_in + 0.05, 10, 10)
    show.layer(big, on(t_in, t_out, 1, 6))
    low = show.text(L.lower(), 0.16, (0.30, 0.60), GOLD, shadow=True, name=f"Low{L}")
    show.pop(low, t_in + 0.35, 0.16, 8)
    show.layer(low, on(t_in + 0.3, t_out, 1, 6))
    word = show.text(WORDS[L], 0.075, (0.19, 0.36), INK, name=f"Word{L}")
    show.slide_in(word, anchor[L], -0.1, 0.19, 0.36, 10)
    show.layer(word, on(anchor[L], t_out, 1, 6))
print("letter cards built", flush=True)

# choruses: rainbow card + bouncing A B C D + hands + spinning arrow
for ci, (a, b) in enumerate(CH):
    show.layer(rainbow, on(a - 0.2, b + 0.2, 8, 8))
    letters = "ABCD" if ci < 2 else "ABCDEFG"
    xs = [0.2 + 0.6 * k / (len(letters) - 1) for k in range(len(letters))]
    idx = [i for i, w in enumerate(WORDS_T) if w["s"] >= a - 0.3][0]
    cursor = idx
    times = [find(ch, exact=True)["s"] for ch in letters]  # Whisper tokens: A, -B, -C, -D, (E, -F, -G)
    for k, ch in enumerate(letters):
        t = times[k]
        d = show.text(ch, 0.22, (xs[k], 0.60), WHITE if k % 2 == 0 else INK, shadow=True, name=f"Ch{ci}{ch}")
        show.bob(d, xs[k], 0.60, 0.02, 3, k * 0.8)
        show.pop(d, t, 0.22, 6)
        show.wobble(d, t, 12, 8)
        show.layer(d, on(t, b, 1, 8))
    cursor = idx
    clap = find("clap", after=idx) if ci < 2 else None
    if clap:
        rnd = find("round", after=idx)
        hands = show.text("✋   ✋", 0.14, (0.5, 0.27), GOLD, font=SYM_FONT, style="Regular", name=f"Hands{ci}")
        show.pop_bumps(hands, clap["s"], 0.14, bumps=(clap["s"] + 0.4, clap["s"] + 0.8))
        show.layer(hands, on(clap["s"], rnd["s"], 1, 4))
        arrow = show.text("↻", 0.20, (0.5, 0.27), GOLD, font=SYM_FONT, style="Regular", name=f"Round{ci}")
        show.expr(arrow, "AngleZ", "-(time*8)")
        show.layer(arrow, on(rnd["s"], b, 4, 8))
    else:
        hooray = find("hooray", after=idx)
        stars = show.text("★  ★  ★  ★  ★", 0.12, (0.5, 0.27), GOLD, font=SYM_FONT, style="Regular", name="Hooray")
        show.pop(stars, hooray["s"], 0.12, 8)
        show.layer(stars, on(hooray["s"], b + 0.2, 1, 8))
print("choruses built", flush=True)

# bridge (instrumental): letters learned so far dance in a grid
def grid(tag, letters, t_in, t_out, rows=2, size=0.11, y0=0.66, dy=0.24):
    per = math.ceil(len(letters) / rows)
    for k, ch in enumerate(letters):
        r, cidx = divmod(k, per)
        x = 0.1 + 0.8 * (cidx / max(per - 1, 1))
        y = y0 - r * dy
        d = show.text(ch, size, (x, y), WHITE if (k % 2 == 0) else INK, shadow=True, name=f"{tag}{ch}")
        show.expr(d, "Center", f"Point({x}, {y} + 0.02*sin(time/4 + {k * 0.45}))")
        show.pop(d, t_in + 0.06 * k, size, 6)
        show.layer(d, on(t_in + 0.06 * k, t_out, 1, 8))


show.layer(rainbow, on(BRIDGE[0], BRIDGE[1], 10, 10))
grid("Br", LETTERS[:16], BRIDGE[0] + 0.2, BRIDGE[1], rows=2, size=0.12)
btitle = show.text("Halfway there!", 0.075, (0.5, 0.25), INK, name="BridgeTitle")
show.bob(btitle, 0.5, 0.25, 0.01, 5)
show.layer(btitle, on(BRIDGE[0] + 1.2, BRIDGE[1], 8, 8))

# finale: whole alphabet waves, title, thanks card
show.layer(rainbow, on(FINALE[0], SONG_END, 10, 1))
grid("Fin", LETTERS, FINALE[0] + 0.2, THANKS - 0.3, rows=2, size=0.095, y0=0.68, dy=0.22)
ftitle = show.text("We learned our alphabet today!", 0.065, (0.5, 0.22), INK, name="FinaleTitle")
show.bob(ftitle, 0.5, 0.22, 0.01, 5)
show.layer(ftitle, on(FINALE[0] + 1.5, THANKS - 0.3, 8, 8))
thanks = show.text("Thanks for watching!", 0.14, (0.5, 0.56), GOLD, shadow=True, name="Thanks")
show.bob(thanks, 0.5, 0.56, 0.012, 5)
show.pop(thanks, THANKS, 0.14, 10)
show.layer(thanks, on(THANKS, SONG_END, 1, 30))
for i in range(12):
    ang = 2 * math.pi * i / 12
    st = show.text("★", 0.08, (0.5 + 0.34 * math.cos(ang), 0.56 + 0.36 * math.sin(ang)), GOLD, font=SYM_FONT, style="Regular", name=f"TStar{i}")
    show.pop(st, THANKS + 0.05 * i, 0.08, 6)
    show.layer(st, on(THANKS + 0.05 * i, SONG_END, 1, 30))

# intro
show.layer(rainbow, on(0, 9.0, 1, 12))
title = show.text("The ABC Song", 0.17, (0.5, 0.62), GOLD, shadow=True, name="IntroTitle")
show.bob(title, 0.5, 0.62, 0.012, 6)
show.pop(title, 0.4, 0.17, 12)
show.layer(title, on(0.3, 8.9, 1, 10))
sub = show.text("Learning letters happily!", 0.07, (0.5, 0.40), INK, name="IntroSub")
show.layer(sub, on(1.4, 8.9, 10, 10))
ribbon = show.text("A B C D E F G H I J K L M", 0.055, (0.5, 0.24), INK, name="IntroRibbon1")
show.bob(ribbon, 0.5, 0.24, 0.015, 4, 1.0)
show.layer(ribbon, on(2.0, 8.9, 10, 10))
ribbon2 = show.text("N O P Q R S T U V W X Y Z", 0.055, (0.5, 0.15), INK, name="IntroRibbon2")
show.bob(ribbon2, 0.5, 0.15, 0.015, 4, 2.2)
show.layer(ribbon2, on(2.4, 8.9, 10, 10))

# captions = the OFFICIAL lyric lines (not the transcript), each timed by an anchor word walked in order
LINES = {
    "A": "A is for Apple, shiny and red,", "B": "B is for Bear who jumps out of bed.", "C": "C is for Cat with a soft little paw,", "D": "D is for Dog who says, \"Bow-wow-wow!\"",
    "E": "E is for Elephant, big and strong,", "F": "F is for Fish that swims along.", "G": "G is for Goat on top of a hill,", "H": "H is for Hat that fits you still.",
    "I": "I is for Ice cream, cold and sweet,", "J": "J is for Jelly, a wobbly treat.", "K": "K is for Kite flying up so high,", "L": "L is for Lion with a mighty cry.",
    "M": "M is for Moon shining at night,", "N": "N is for Nest where birds sit tight.", "O": "O is for Orange, juicy and round,", "P": "P is for Penguin waddling around.",
    "Q": "Q is for Queen with a sparkling crown,", "R": "R is for Rabbit hopping up and down.", "S": "S is for Sun shining warm and bright,", "T": "T is for Train going left and right.",
    "U": "U is for Umbrella when raindrops fall,", "V": "V is for Violin, music for all.", "W": "W is for Whale swimming in the sea,", "X": "X is for Xylophone, play with me!",
    "Y": "Y is for Yo-yo, down then high,", "Z": "Z is for Zebra passing by.",
}
CHORUS = [("a", True, "A-B-C-D, sing with me,"), ("learning", False, "Learning letters happily!"), ("clap", False, "Clap your hands and tap your toes,"), ("round", False, "Round and round the alphabet goes!")]
CHORUS_LAST = [("a", True, "A-B-C-D, sing with me,"), ("e", True, "E-F-G, so happily!"), ("h", True, "H to Z, now shout hooray,"), ("learned", False, "We learned our alphabet today!")]
EXTRA = [("26", False, "Twenty-six letters, now we know,"), ("fast", False, "Sing them fast or sing them slow!")]
script = []  # (anchor, exact, text, lead) in song order
for L in "ABCDEFGH":
    script.append((ANCHORS[L], False, LINES[L], 1.05))
script += [(a, e, t, 0.1) for a, e, t in CHORUS]
for L in "IJKLMNOP":
    script.append((ANCHORS[L], False, LINES[L], 1.05))
script += [(a, e, t, 0.1) for a, e, t in CHORUS]
for L in "QRSTUVWXYZ":
    script.append((ANCHORS[L], False, LINES[L], 1.05))
script += [(a, e, t, 0.1) for a, e, t in EXTRA]
script += [(a, e, t, 0.1) for a, e, t in CHORUS_LAST]
cursor = 0
caps = []
for anchor_word, exact, text, lead in script:
    w = find(anchor_word, exact=exact)
    caps.append((max(0.0, w["s"] - lead), text))
for i, (t0, text) in enumerate(caps):
    t1 = caps[i + 1][0] - 0.05 if i + 1 < len(caps) else THANKS - 0.4
    t1 = min(t1, t0 + 6.0)
    cap = show.text(text, 0.042, (0.5, 0.065), WHITE, shadow=True, name=f"Cap{i + 1}")
    show.layer(cap, on(t0, t1, 4, 4))
print("captions:", len(caps), flush=True)

# global fade in/out
black = show.bg_solid((0, 0, 0), alpha=0.0, name="FadeBase")  # transparent: the fade goes to whatever is under V2 (black at the ends)
fader = show._name("M")
call("POST", f"{comp}/tools", json={"tool_id": "Merge", "name": fader})
show.connect(fader, "Background", black)
show.connect(fader, "Foreground", show.chain)
show.keys(fader, "Blend", [(0, 0.0), (15, 1.0), (F(SONG_END) - 40, 1.0), (F(SONG_END), 0.0)])
show.chain = fader
show.finish()
call("POST", "/projects/current/save")
print("built:", show.n, "layers,", calls, "API calls", flush=True)
json.dump({"project": PROJECT, "carrier": carrier_id, "win": win, "anchor": anchor, "thanks": THANKS, "missing": missing}, open(f"{ABC}/build_info.json", "w"), indent=1)

# ---------------------------------------------------------------- render
OUT = os.environ.get("ABC_OUT_DIR", ABC + "/out")
job = call("POST", "/render/jobs", json={"format": "mp4", "codec": "H264", "mode": "single", "settings": {"TargetDir": OUT, "CustomName": "abc-song", "SelectAllFrames": True, "FormatWidth": 1920, "FormatHeight": 1080, "FrameRate": 30}, "start": True})
done = call("POST", f"/render/jobs/{job['job_id']}/wait", params={"timeout": 3400, "poll": 10})
print("render:", done["JobStatus"], "->", OUT)
