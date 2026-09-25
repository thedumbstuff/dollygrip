"""'ABC Song' v2 - maximum-motion cut, built through DollyGrip.

Same footage and timing as v1 (26 stock clips on V1 placed by /stock/assemble,
one transparent Fusion comp on a black carrier on V2), but every element moves:

- footage: Ken Burns on all 26 clips (a Transform inside each clip's own comp)
- letter cards: panel slides in with overshoot and out again; big letter enters
  with squash-pop / spin-in / drop-and-bounce (cycling), bumps on its sung word,
  wiggles continuously; outlined lowercase spins in; the word slides in with a
  bounce and a tilt; a six-star burst fires on every sung letter; coloured swipe
  wipes at every letter change; an alphabet progress row lights up at the top
- choruses / bridge / finale: rainbow card, drifting candy stripes, confetti
  rain, rising music notes, hopping letters, clap hands, spinning arrow
- captions pop in over the band with a bobbing note
- audio stems are added by finalize_v2.py (mastered song, SFX, voice)."""

import json
import math
import os
import time

import httpx

BASE = "http://127.0.0.1:4747/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
ABC = os.environ.get("ABC_DIR", "D:/abc-song")  # carrier.mp4, clips.json (+ words.json for timing.py) - see ../README.md
T = json.load(open(os.path.join(HERE, "timing.json"), encoding="utf-8"))
FPS = 30
SONG_END = T["song_end"]
PROJECT = os.environ.get("ABC_PROJECT", "ABC Song v2 (DollyGrip)")
TEXT_FONT, SYM_FONT = "Comic Sans MS", "Segoe UI Symbol"
INK = (0.13, 0.13, 0.25)
WHITE = (1.0, 1.0, 1.0)
GOLD = (1.0, 0.80, 0.12)
PASTELS = [(0.99, 0.80, 0.45), (0.55, 0.80, 0.98), (0.70, 0.90, 0.60), (0.98, 0.70, 0.75), (0.80, 0.70, 0.98), (0.99, 0.87, 0.50), (0.60, 0.90, 0.85), (0.98, 0.78, 0.60), (0.75, 0.85, 0.98), (0.88, 0.78, 0.95)]
BRIGHTS = [(1.0, 0.45, 0.45), (1.0, 0.75, 0.2), (0.45, 0.85, 0.45), (0.35, 0.65, 1.0), (0.85, 0.5, 1.0), (1.0, 0.55, 0.8)]
RAINBOW = ((0.98, 0.72, 0.78), (0.99, 0.87, 0.50), (0.60, 0.90, 0.85), (0.75, 0.80, 0.98))
LETTERS = T["letters"]
WORDS = T["words"]
anchor = T["anchor"]
win = {L: tuple(v) for L, v in T["window"].items()}
CH = [(e["start"], e["end"]) for e in T["chorus"]]
BRIDGE = tuple(T["bridge"])
FINALE = tuple(T["finale"])
THANKS = T["thanks"]
BEAT = T["beat_estimate"]
OUTLINE = float(os.environ.get("ABC_OUTLINE", "0.05"))

c = httpx.Client(base_url=BASE, timeout=900)
calls = 0
t_start = time.time()


def call(method, path, **kw):
    global calls
    calls += 1
    r = c.request(method, path, **kw)
    if r.status_code != 200:
        raise SystemExit(f"{method} {path} -> {r.status_code} {r.text[:300]}")
    return r.json()


def F(sec):
    return int(round(sec * FPS))


def on(t_in, t_out, fade_in=6, fade_out=6):
    a, b = F(t_in), F(t_out)
    fade_in, fade_out = min(fade_in, max(1, (b - a) // 2)), min(fade_out, max(1, (b - a) // 2))
    return [(a, 0.0), (a + fade_in, 1.0), (b - fade_out, 1.0), (b, 0.0)]


def on_multi(windows, fade_in=6, fade_out=6):
    """Blend keys for several non-overlapping on-windows (sorted)."""
    keys = []
    for t_in, t_out in sorted(windows):
        seg = on(t_in, t_out, fade_in, fade_out)
        if keys and seg[0][0] <= keys[-1][0]:
            seg = seg[1:]
        keys += seg
    return keys


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

    # -- primitives
    def bg_solid(self, rgb, alpha=1.0, name=None):
        r, g, b = (v * alpha for v in rgb)  # premultiplied: a translucent Background otherwise renders too bright
        return self.add("Background", {"TopLeftRed": r, "TopLeftGreen": g, "TopLeftBlue": b, "TopLeftAlpha": alpha}, name)

    def bg_corners(self, tl, tr, bl, br, name=None):
        inputs = {"Type": "Corner", "TopLeftAlpha": 1.0, "TopRightAlpha": 1.0, "BottomLeftAlpha": 1.0, "BottomRightAlpha": 1.0}
        for corner, rgb in (("TopLeft", tl), ("TopRight", tr), ("BottomLeft", bl), ("BottomRight", br)):
            inputs[f"{corner}Red"], inputs[f"{corner}Green"], inputs[f"{corner}Blue"] = rgb
        return self.add("Background", inputs, name)

    def rect(self, rgb, alpha, center, w, h, radius=0.05, angle=0.0, name=None):
        """Rounded rectangle = Background + RectangleMask; returns (bg, mask)."""
        bg = self.bg_solid(rgb, alpha, name)
        mask = self.add("RectangleMask", {"Center": list(center), "Width": w, "Height": h, "CornerRadius": radius, "Angle": angle, "SoftEdge": 0.002}, (name or bg) + "Mask")
        self.connect(bg, "EffectMask", mask)
        return bg, mask

    def text(self, s, size, center, color=WHITE, font=TEXT_FONT, style="Bold", shadow=False, outline=None, alpha=1.0, name=None, extra=None):
        r, g, b = color
        inputs = {"StyledText": s, "Font": font, "Style": style, "Size": size, "Red1": r, "Green1": g, "Blue1": b, "Alpha1": alpha, "Center": list(center)}
        if shadow:
            inputs["Enabled3"] = 1
        if outline:
            orr, og, ob = outline
            inputs.update({"Enabled2": 1, "Red2": orr, "Green2": og, "Blue2": ob, "Thickness2": OUTLINE})
        if extra:
            inputs.update(extra)
        return self.add("TextPlus", inputs, name)

    # -- motion vocabulary
    def bob(self, tool, x, y, amp=0.012, period=2.5, phase=0.0):
        """Gentle vertical float; period in seconds."""
        self.expr(tool, "Center", f"Point({x}, {y} + {amp}*sin(6.2832*(time/30)/{period} + {phase}))")

    def wiggle(self, tool, degrees=4, period=1.2, phase=0.0):
        """Continuous rotation wobble; period in seconds."""
        self.expr(tool, "AngleZ", f"{degrees}*sin(6.2832*(time/30)/{period} + {phase})")

    def pop(self, tool, t, size, over=8):
        f = F(t)
        self.keys(tool, "Size", [(f, 0.02), (f + over, size * 1.12), (f + over + 5, size)])

    def squash_pop(self, tool, t, size, bumps=()):
        """Overshoot, undershoot, settle - then a bump on each extra time."""
        f = F(t)
        kf = [(f, 0.02), (f + 6, size * 1.28), (f + 10, size * 0.88), (f + 14, size * 1.06), (f + 18, size)]
        for tb in bumps:
            fb = F(tb)
            if fb > kf[-1][0] + 1:
                kf += [(fb, size), (fb + 3, size * 1.2), (fb + 7, size * 0.96), (fb + 10, size)]
        self.keys(tool, "Size", kf)

    def spin_in(self, tool, t, over=12):
        f = F(t)
        self.keys(tool, "AngleZ", [(f, -300), (f + over, 18), (f + over + 5, -4), (f + over + 9, 0)])

    def drop_in(self, tool, t, x, y, over=10):
        f = F(t)
        self.keys(tool, "Center", [(f, [x, y + 0.7]), (f + over, [x, y - 0.03]), (f + over + 4, [x, y + 0.035]), (f + over + 8, [x, y - 0.01]), (f + over + 11, [x, y])])

    def wobble(self, tool, t, degrees=8, over=10):
        f = F(t)
        self.keys(tool, "AngleZ", [(f, -degrees), (f + over, degrees * 0.4), (f + over + 8, 0)])

    def slide_in(self, tool, t, x_from, x_to, y, over=10):
        f = F(t)
        self.keys(tool, "Center", [(f, [x_from, y]), (f + over, [x_to + 0.02, y]), (f + over + 4, [x_to - 0.006, y]), (f + over + 7, [x_to, y])])


# ---------------------------------------------------------------- project, tracks, footage
existing = call("GET", "/projects")["projects"]
if PROJECT in existing:
    r = c.get("/projects/current")
    if r.status_code == 200 and r.json()["name"] == PROJECT:
        call("POST", "/projects/current/close")
    if c.delete(f"/projects/{PROJECT}").status_code != 200:
        PROJECT = PROJECT + " " + time.strftime("%H%M%S")
call("POST", "/projects", json={"name": PROJECT})
call("POST", "/timelines", json={"name": "abc-song-v2", "width": 1920, "height": 1080, "fps": FPS, "start_timecode": "00:00:00:00", "extra_video_tracks": 1})
call("POST", "/system/background-tasks/disable")
call("POST", "/system/page", json={"page": "edit"})
call("POST", "/mediapool/folders", json={"path": "song", "create": True})
call("POST", "/mediapool/import", json={"paths": [f"{ABC}/carrier.mp4"]})
res = call("POST", "/timelines/current/append", json={"items": [{"clip_name": "carrier.mp4", "track_index": 2, "record_frame": 0, "media_type": "video"}]})
assert res["all_ok"], res
carrier_id = res["results"][0]["item_id"]

clips = json.load(open(f"{ABC}/clips.json", encoding="utf-8"))
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

# ---------------------------------------------------------------- Ken Burns on every clip (a Transform inside each clip's comp)
items = [it for it in call("GET", "/timelines/current/items")["items"] if it.get("track_type") == "video" and it.get("track_index") == 1]
items.sort(key=lambda it: it.get("start", it.get("record_frame", 0)))
kb = 0
for k, it in enumerate(items):
    try:
        call("POST", f"/fusion/items/{it['id']}/comps", json={})
        cp = f"/fusion/items/{it['id']}/comps/1"
        tl_tools = {t["id"]: t["name"] for t in call("GET", f"{cp}/tools")["tools"]}
        attrs = call("GET", f"{cp}/attrs")
        a, b = int(attrs.get("render_start") or 0), int(attrs.get("render_end") or 60)
        call("POST", f"{cp}/tools", json={"tool_id": "Transform", "name": "KenBurns", "inputs": {"Edges": 1}})
        if k % 2 == 0:
            zoom = [(a, 1.0), (b, 1.11)]
            pan = [(a, [0.5, 0.5]), (b, [0.515, 0.49])]
        else:
            zoom = [(a, 1.11), (b, 1.0)]
            pan = [(a, [0.49, 0.51]), (b, [0.5, 0.5])]
        call("POST", f"{cp}/tools/KenBurns/keyframes", json={"input": "Size", "keyframes": [{"frame": f, "value": v} for f, v in zoom]})
        call("POST", f"{cp}/tools/KenBurns/keyframes", json={"input": "Center", "keyframes": [{"frame": f, "value": v} for f, v in pan]})
        call("POST", f"{cp}/tools/KenBurns/connect", json={"input": "Input", "source_tool": tl_tools["MediaIn"]})
        call("POST", f"{cp}/tools/{tl_tools['MediaOut']}/connect", json={"input": "Input", "source_tool": "KenBurns"})
        kb += 1
    except SystemExit as e:
        print("ken burns skipped for item", k, e, flush=True)
print("ken burns on", kb, "clips", f"({calls} calls, {time.time() - t_start:.0f}s)", flush=True)

# ---------------------------------------------------------------- the overlay comp
call("POST", f"/fusion/items/{carrier_id}/comps", json={})
comp = f"/fusion/items/{carrier_id}/comps/1"
tools = {t["id"]: t["name"] for t in call("GET", f"{comp}/tools")["tools"]}
show = Show(comp, tools["MediaOut"])
root = show.bg_solid((0, 0, 0), alpha=0.0, name="Clear")
show.layer(root)
rainbow = show.bg_corners(*RAINBOW, name="Rainbow")
PARTY = [(0.0, 9.0)] + [(a - 0.2, b + 0.2) for a, b in CH] + [BRIDGE, (FINALE[0], SONG_END)]
PARTY.sort()

# full-frame pastel cards for letters with no footage
for L in missing:
    t_in, t_out = win[L]
    show.layer(show.bg_solid(PASTELS[LETTERS.index(L) % 10], name=f"Card{L}"), on(t_in, t_out, 6, 6))

# rainbow card under intro / choruses / bridge / finale (one layer, multi-window)
show.layer(rainbow, on_multi(PARTY, 8, 8))

# drifting candy stripes over the rainbow
for k in range(6):
    col = BRIGHTS[k % len(BRIGHTS)]
    bg, mask = show.rect(col, 0.22, (0.5, 0.5), 0.07, 1.6, radius=0.0, angle=18, name=f"Stripe{k}")
    show.expr(mask, "Center", f"Point((((time/30)/7 + {k / 6:.3f}) % 1.3) - 0.15, 0.5)")
    show.layer(bg, on_multi(PARTY, 10, 10))
print("stage built", flush=True)

# caption band: dark vertical gradient at the bottom, always on during singing
# (a full-frame Vertical gradient Background darkened the whole picture; a soft-edged masked band does what was meant)
shade, shade_mask = show.rect((0.05, 0.05, 0.1), 0.8, (0.5, 0.02), 1.4, 0.2, radius=0.0, name="Shade")
call("PATCH", f"{comp}/tools/{shade_mask}/inputs", json={"inputs": {"SoftEdge": 0.06}})
show.layer(shade, on_multi([(8.2, 126.0), (CH[2][0] - 0.3, THANKS - 0.3)], 12, 12))

# alphabet progress row at the top: grey base, gold letters light up when learned
row_x = {L: 0.09 + 0.82 * i / 25 for i, L in enumerate(LETTERS)}
for i, L in enumerate(LETTERS):
    dim = show.text(L, 0.03, (row_x[L], 0.955), WHITE, alpha=0.35, name=f"RowDim{L}")
    show.layer(dim, on(win["A"][0] - 0.5, 126.0, 10, 10))
for i, L in enumerate(LETTERS):
    lit = show.text(L, 0.036, (row_x[L], 0.955), GOLD, shadow=True, name=f"Row{L}")
    show.pop(lit, win[L][0] + 0.1, 0.036, 6)
    show.layer(lit, on(win[L][0] + 0.1, 126.0, 1, 10))
print("progress row built", flush=True)

# swipe wipes at every letter-to-letter change (two colours alternating); the rectangle waits off-screen between wipes
cuts = []
for i in range(25):
    L, N = LETTERS[i], LETTERS[i + 1]
    if abs(win[L][1] - win[N][0]) < 0.05:
        cuts.append(win[N][0])
swipes = [show.rect(BRIGHTS[1], 0.95, (-0.6, 0.5), 0.5, 1.3, radius=0.0, angle=12, name="SwipeA"), show.rect(BRIGHTS[3], 0.95, (-0.6, 0.5), 0.5, 1.3, radius=0.0, angle=-12, name="SwipeB")]
for si, (bg, mask) in enumerate(swipes):
    kf, blend = [], []
    for j, t in enumerate(cuts):
        if j % 2 != si:
            continue
        f = F(t) - 6
        if kf:  # two equal keys on each side of the hold keep the spline flat (a single hold key overshoots back on screen)
            kf += [(f - 2, [1.6, 0.5]), (f - 1, [1.6, 0.5])]
        kf += [(f, [-0.6, 0.5]), (f + 12, [1.6, 0.5]), (f + 13, [1.6, 0.5])]
        blend += [(f - 2, 0.0), (f - 1, 1.0), (f + 12, 1.0), (f + 13, 0.0)]
    show.keys(mask, "Center", kf)
    show.layer(bg, blend)
print("swipes:", len(cuts), flush=True)

# letter cards
BURSTS = []  # (time, x, y) for the shared star burst
for i, L in enumerate(LETTERS):
    t_in, t_out = win[L]
    col = PASTELS[i % 10]
    fi, fo = F(t_in), F(t_out)
    # white frame + pastel panel slide in from the left with overshoot, slide out at the end
    for tag, rgb, alpha, w, h in (("Frame", WHITE, 0.9, 0.37, 0.90), ("Panel", col, 0.96, 0.34, 0.86)):
        bg, mask = show.rect(rgb, alpha, (-0.4, 0.5), w, h, radius=0.05, name=f"{tag}{L}")
        show.keys(mask, "Center", [(fi, [-0.4, 0.5]), (fi + 9, [0.205, 0.5]), (fi + 13, [0.185, 0.5]), (fi + 16, [0.19, 0.5]), (fo - 8, [0.19, 0.5]), (fo, [-0.45, 0.5])])
        show.layer(bg, on(t_in, t_out, 1, 1))
    # big letter: three entrance styles cycling, bump on the sung word, continuous wiggle
    style = i % 3
    big = show.text(L, 0.30, (0.19, 0.63), WHITE, shadow=True, outline=INK, name=f"Big{L}")
    show.squash_pop(big, t_in + 0.08, 0.30, bumps=(anchor[L],))
    if style == 0:
        show.bob(big, 0.19, 0.63, 0.012, 4, i * 0.4)
        show.wiggle(big, 5, 1.4, i)
    elif style == 1:
        show.spin_in(big, t_in + 0.08, 12)
        show.bob(big, 0.19, 0.63, 0.012, 4, i * 0.4)
    else:
        show.drop_in(big, t_in + 0.08, 0.19, 0.63, 10)
        show.wiggle(big, 5, 1.4, i)
    show.layer(big, on(t_in + 0.05, t_out, 1, 6))
    # lowercase spins in
    low = show.text(L.lower(), 0.16, (0.30, 0.60), GOLD, shadow=True, outline=INK, name=f"Low{L}")
    show.pop(low, t_in + 0.4, 0.16, 8)
    show.spin_in(low, t_in + 0.4, 10)
    show.layer(low, on(t_in + 0.35, t_out, 1, 6))
    # the word slides in with a bounce and a little tilt
    word = show.text(WORDS[L], 0.075, (0.19, 0.36), INK, name=f"Word{L}")
    show.slide_in(word, anchor[L], -0.1, 0.19, 0.36, 10)
    show.wobble(word, anchor[L], 6, 10)
    show.layer(word, on(anchor[L], t_out, 1, 6))
    BURSTS.append((anchor[L], 0.19, 0.63))
print("letter cards built", f"({calls} calls, {time.time() - t_start:.0f}s)", flush=True)

# choruses: hopping letters with pops, clap hands, spinning arrow, hooray stars; rising notes; confetti (below)
for ci, e in enumerate(T["chorus"]):
    a, b = e["start"], e["end"]
    letters = list(e["letters"].keys())
    xs = [0.2 + 0.6 * k / (len(letters) - 1) for k in range(len(letters))]
    for k, ch in enumerate(letters):
        t = e["letters"][ch]
        d = show.text(ch, 0.22, (xs[k], 0.60), WHITE if k % 2 == 0 else INK, shadow=True, outline=INK if k % 2 == 0 else None, name=f"Ch{ci}{ch}")
        show.expr(d, "Center", f"Point({xs[k]}, 0.60 + 0.035*abs(sin((time/30)*{math.pi / max(BEAT * 2, 0.25):.3f} + {k * 0.7:.2f})))")  # hop every two beats
        show.squash_pop(d, t, 0.22)
        show.wiggle(d, 7, 0.8, k)
        show.layer(d, on(t, b, 1, 8))
        BURSTS.append((t, xs[k], 0.60))
    if "clap" in e:
        hands = show.text("✋   ✋", 0.14, (0.5, 0.27), GOLD, font=SYM_FONT, style="Regular", shadow=True, name=f"Hands{ci}")
        claps = [e["clap"] + n * BEAT * 2 for n in range(4)]
        show.squash_pop(hands, e["clap"] - 0.15, 0.14, bumps=claps[1:])
        show.layer(hands, on(e["clap"] - 0.15, e["round"], 1, 4))
        arrow = show.text("↻", 0.20, (0.5, 0.27), GOLD, font=SYM_FONT, style="Regular", shadow=True, name=f"Round{ci}")
        show.expr(arrow, "AngleZ", "-((time/30)*150)")
        show.pop(arrow, e["round"], 0.20, 8)
        show.layer(arrow, on(e["round"], b, 1, 8))
    else:
        stars = show.text("★  ★  ★  ★  ★", 0.12, (0.5, 0.27), GOLD, font=SYM_FONT, style="Regular", shadow=True, name="Hooray")
        show.squash_pop(stars, e["hooray"], 0.12)
        show.wiggle(stars, 6, 1.2)
        show.layer(stars, on(e["hooray"], b + 0.2, 1, 8))
print("choruses built", flush=True)

# rising music notes during party windows
for k in range(5):
    note = show.text("♪" if k % 2 == 0 else "♫", 0.09, (0.1 + 0.2 * k, 0.5), BRIGHTS[k % len(BRIGHTS)], font=SYM_FONT, style="Regular", shadow=True, name=f"Note{k}")
    show.expr(note, "Center", f"Point({0.1 + 0.2 * k:.2f} + 0.05*sin(6.2832*(time/30)/2.2 + {k}), (((time/30)/{5.5 + k * 0.7:.1f} + {k * 0.2:.2f}) % 1.3) - 0.15)")
    show.wiggle(note, 18, 1.5, k)
    show.layer(note, on_multi([w for w in PARTY if w[0] > 0.5], 12, 12))

# confetti rain (glyph pieces on Segoe UI Symbol) during intro / choruses / finale
CONF_WINDOWS = [(0.0, 9.0)] + [(a - 0.2, b + 0.2) for a, b in CH] + [(FINALE[0], SONG_END)]
GLYPHS = ["●", "■", "▲", "★", "◆", "●", "■", "★"]
for k in range(14):
    x0 = 0.04 + 0.92 * ((k * 0.618) % 1.0)
    period = 4.5 + (k % 5) * 0.8
    piece = show.text(GLYPHS[k % len(GLYPHS)], 0.05 if k % 3 else 0.065, (x0, 1.1), BRIGHTS[k % len(BRIGHTS)], font=SYM_FONT, style="Regular", name=f"Conf{k}")
    show.expr(piece, "Center", f"Point({x0:.3f} + 0.04*sin(6.2832*(time/30)/1.7 + {k}), 1.08 - (((time/30)/{period:.1f} + {(k * 0.37) % 1.0:.2f}) % 1.25))")
    show.expr(piece, "AngleZ", f"(time/30)*{(60 + 15 * (k % 4)) * (1 if k % 2 == 0 else -1)}")
    show.layer(piece, on_multi(CONF_WINDOWS, 10, 10))
print("party layers built", f"({calls} calls, {time.time() - t_start:.0f}s)", flush=True)

# shared star bursts: six stars fly out from every sung letter (all bursts in one keyframe list per star)
BURSTS.sort()
for s in range(6):
    ang = 2 * math.pi * s / 6 + 0.3
    star = show.text("★", 0.06, (0.5, 0.5), GOLD if s % 2 == 0 else WHITE, font=SYM_FONT, style="Regular", name=f"Burst{s}")
    ckeys, skeys, last = [], [], -99
    for t, x, y in BURSTS:
        f = F(t)
        if f - last < 16:
            f = last + 16
        last = f + 13
        fx, fy = x + 0.15 * math.cos(ang), y + 0.19 * math.sin(ang)
        if ckeys:
            ckeys.append((f - 1, [x, y]))
        ckeys += [(f, [x, y]), (f + 12, [fx, fy]), (f + 13, [fx, fy])]
        skeys += [(f - 1, 0.0), (f, 0.0), (f + 3, 0.07), (f + 12, 0.0), (f + 13, 0.0)]
    show.keys(star, "Center", ckeys)
    show.keys(star, "Size", skeys)
    show.expr(star, "AngleZ", f"(time/30)*{120 if s % 2 else -120}")
    show.layer(star)
print("bursts:", len(BURSTS), flush=True)


# bridge (instrumental): letters learned so far dance in a grid; finale: whole alphabet
def grid(tag, letters, t_in, t_out, rows=2, size=0.11, y0=0.66, dy=0.24):
    per = math.ceil(len(letters) / rows)
    for k, ch in enumerate(letters):
        r, cidx = divmod(k, per)
        x = 0.1 + 0.8 * (cidx / max(per - 1, 1))
        y = y0 - r * dy
        d = show.text(ch, size, (x, y), WHITE if (k % 2 == 0) else INK, shadow=True, outline=INK if k % 2 == 0 else None, name=f"{tag}{ch}")
        show.expr(d, "Center", f"Point({x}, {y} + 0.025*sin(6.2832*(time/30)/1.2 + {k * 0.45}))")
        show.wiggle(d, 8, 1.0, k * 0.6)
        show.squash_pop(d, t_in + 0.06 * k, size)
        show.layer(d, on(t_in + 0.06 * k, t_out, 1, 8))


grid("Br", LETTERS[:16], BRIDGE[0] + 0.2, BRIDGE[1], rows=2, size=0.12)
btitle = show.text("Halfway there!", 0.08, (0.5, 0.25), INK, name="BridgeTitle")
show.squash_pop(btitle, BRIDGE[0] + 1.2, 0.08)
show.bob(btitle, 0.5, 0.25, 0.012, 4)
show.layer(btitle, on(BRIDGE[0] + 1.2, BRIDGE[1], 1, 8))

grid("Fin", LETTERS, FINALE[0] + 0.2, THANKS - 0.3, rows=2, size=0.095, y0=0.68, dy=0.22)
ftitle = show.text("We learned our alphabet today!", 0.065, (0.5, 0.22), INK, name="FinaleTitle")
show.squash_pop(ftitle, FINALE[0] + 1.5, 0.065)
show.bob(ftitle, 0.5, 0.22, 0.012, 4)
show.layer(ftitle, on(FINALE[0] + 1.5, THANKS - 0.3, 1, 8))

# thanks card: big text pops, stars orbit it
thanks = show.text("Thanks for watching!", 0.14, (0.5, 0.56), GOLD, shadow=True, outline=INK, name="Thanks")
show.squash_pop(thanks, THANKS, 0.14)
show.wiggle(thanks, 3, 1.8)
show.layer(thanks, on(THANKS, SONG_END, 1, 30))
for i in range(12):
    ang = 2 * math.pi * i / 12
    st = show.text("★", 0.08, (0.5, 0.56), GOLD if i % 2 else WHITE, font=SYM_FONT, style="Regular", name=f"TStar{i}")
    show.expr(st, "Center", f"Point(0.5 + 0.36*cos(6.2832*(time/30)/6 + {ang:.3f}), 0.56 + 0.38*sin(6.2832*(time/30)/6 + {ang:.3f}))")
    show.pop(st, THANKS + 0.05 * i, 0.08, 6)
    show.layer(st, on(THANKS + 0.05 * i, SONG_END, 1, 30))

# intro: three title words drop in with a bounce, sub line, alphabet ribbons sway
for k, (wtxt, x) in enumerate((("The", 0.24), ("ABC", 0.5), ("Song", 0.76))):
    t = show.text(wtxt, 0.19 if wtxt == "ABC" else 0.14, (x, 0.62), GOLD if wtxt == "ABC" else WHITE, shadow=True, outline=INK, name=f"Title{k}")
    show.drop_in(t, 0.4 + 0.25 * k, x, 0.62, 10)
    show.wiggle(t, 4, 1.9, k)
    show.layer(t, on(0.4 + 0.25 * k, 8.9, 1, 10))
sub = show.text("Learning letters happily!", 0.07, (0.5, 0.40), INK, name="IntroSub")
show.squash_pop(sub, 1.5, 0.07)
show.layer(sub, on(1.5, 8.9, 1, 10))
for k, (txt, y) in enumerate((("A B C D E F G H I J K L M", 0.24), ("N O P Q R S T U V W X Y Z", 0.15))):
    rb = show.text(txt, 0.055, (0.5, y), INK, name=f"IntroRibbon{k}")
    show.expr(rb, "Center", f"Point(0.5 + 0.03*sin(6.2832*(time/30)/3 + {k * 1.5}), {y} + 0.012*sin(6.2832*(time/30)/2 + {k}))")
    show.layer(rb, on(2.0 + 0.4 * k, 8.9, 10, 10))

# captions (official lyrics) pop in over the band; a note bobs at the left
for i, cap in enumerate(T["captions"]):
    if cap["text"].startswith("We learned our alphabet"):
        continue  # the finale title card says it
    tool = show.text(cap["text"], 0.042, (0.5, 0.065), WHITE, shadow=True, name=f"Cap{i + 1}")
    show.keys(tool, "Size", [(F(cap["t"]), 0.03), (F(cap["t"]) + 5, 0.045), (F(cap["t"]) + 8, 0.042)])
    show.layer(tool, on(cap["t"], cap["end"], 3, 4))
note = show.text("♪", 0.06, (0.05, 0.07), GOLD, font=SYM_FONT, style="Regular", name="CapNote")
show.expr(note, "Center", "Point(0.05, 0.07 + 0.012*sin(6.2832*(time/30)/0.7))")
show.wiggle(note, 14, 0.6)
show.layer(note, on(T["captions"][0]["t"], THANKS - 0.4, 8, 8))
print("captions:", len(T["captions"]), flush=True)

# global fade in/out (transparent base so the fade goes to black at both ends)
black = show.bg_solid((0, 0, 0), alpha=0.0, name="FadeBase")
fader = show._name("M")
call("POST", f"{comp}/tools", json={"tool_id": "Merge", "name": fader})
show.connect(fader, "Background", black)
show.connect(fader, "Foreground", show.chain)
show.keys(fader, "Blend", [(0, 0.0), (15, 1.0), (F(SONG_END) - 40, 1.0), (F(SONG_END), 0.0)])
show.chain = fader
show.finish()
call("POST", "/projects/current/save")
print("built:", show.n, "tools,", calls, "API calls,", f"{time.time() - t_start:.0f}s", flush=True)
json.dump({"project": PROJECT, "carrier": carrier_id, "missing": missing, "ken_burns": kb, "tools": show.n, "calls": calls}, open(os.path.join(HERE, "build_info.json"), "w"), indent=1)
