"""Deterministic SFX stem for the ABC Song v2 video.

Reads timing.json next to this script and writes audio/sfx.wav
(48 kHz, stereo, 16-bit, exactly song_end seconds). numpy + stdlib only.
Rerun: python make_sfx.py
"""
import json
import math
import os
import wave
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 48000
SEED = 20260925
rng = np.random.default_rng(SEED)

with open(os.path.join(HERE, "timing.json"), encoding="utf-8") as f:
    T = json.load(f)

SONG_END = float(T["song_end"])
N = int(round(SONG_END * SR))
buf = np.zeros((N, 2), dtype=np.float64)
counts = Counter()


def t_axis(dur):
    return np.arange(int(round(dur * SR))) / SR


def fade_edges(x, ms_in=2.0, ms_out=4.0):
    """Short raised-cosine edges so no event starts or ends with a step."""
    n_in = max(1, int(SR * ms_in / 1000))
    n_out = max(1, int(SR * ms_out / 1000))
    x = x.copy()
    n_in = min(n_in, len(x))
    n_out = min(n_out, len(x))
    x[:n_in] *= 0.5 - 0.5 * np.cos(np.linspace(0, math.pi, n_in))
    x[-n_out:] *= 0.5 + 0.5 * np.cos(np.linspace(0, math.pi, n_out))
    return x


def sweep_sine(f0, f1, dur, exp=True):
    t = t_axis(dur)
    if exp:
        freq = f0 * (f1 / f0) ** (t / dur)
    else:
        freq = f0 + (f1 - f0) * t / dur
    phase = 2 * math.pi * np.cumsum(freq) / SR
    return np.sin(phase)


def bandpass_sweep(x, fc0, fc1, q=1.2):
    """Time-varying RBJ biquad bandpass (constant 0 dB peak gain), per sample."""
    n = len(x)
    y = np.zeros(n)
    fcs = fc0 * (fc1 / fc0) ** (np.arange(n) / max(1, n - 1))
    x1 = x2 = y1 = y2 = 0.0
    for i in range(n):
        w0 = 2 * math.pi * fcs[i] / SR
        alpha = math.sin(w0) / (2 * q)
        a0 = 1 + alpha
        b0 = alpha / a0
        b2 = -alpha / a0
        a1 = -2 * math.cos(w0) / a0
        a2 = (1 - alpha) / a0
        xi = x[i]
        yi = b0 * xi + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, xi
        y2, y1 = y1, yi
        y[i] = yi
    return y


def bell(freq, dur, decay, harmonic=2, harm_gain=0.35):
    t = t_axis(dur)
    env = np.exp(-t / (decay / 5.0))  # ~-43 dB at `decay`
    s = np.sin(2 * math.pi * freq * t) + harm_gain * np.sin(2 * math.pi * freq * harmonic * t)
    return fade_edges(s * env, 1.5, 6)


def place(sig, at, gain=1.0, pan=None, cat=None):
    if pan is None:
        pan = rng.uniform(-0.3, 0.3)
    ang = (pan + 1) * math.pi / 4  # constant-power pan
    lg, rg = math.cos(ang) * math.sqrt(2), math.sin(ang) * math.sqrt(2)
    i0 = int(round(at * SR))
    if i0 >= N or i0 + len(sig) <= 0:
        return
    s = sig * gain
    if i0 < 0:
        s = s[-i0:]
        i0 = 0
    s = s[: N - i0]
    buf[i0 : i0 + len(s), 0] += s * lg
    buf[i0 : i0 + len(s), 1] += s * rg
    if cat:
        counts[cat] += 1


# ---- sound designs ----------------------------------------------------------

def pop(pitch_mul):
    dur = 0.12
    t = t_axis(dur)
    tone = sweep_sine(320 * pitch_mul, 880 * pitch_mul, 0.07)
    tone = np.concatenate([tone, np.sin(2 * math.pi * 880 * pitch_mul * t[: len(t) - len(tone)] + 0.0)])
    env = np.exp(-t / 0.022)
    s = tone[: len(t)] * env
    click = np.zeros(len(t))
    nclick = int(0.002 * SR)
    click[:nclick] = rng.standard_normal(nclick) * np.exp(-np.arange(nclick) / (nclick / 4)) * 0.12
    return fade_edges(s + click, 0.5, 5)


def boing():
    dur = 0.2
    t = t_axis(dur)
    base = 180 * (90 / 180) ** (t / dur)
    freq = base * (1 + 0.06 * np.sin(2 * math.pi * 14 * t))  # wobble
    s = np.sin(2 * math.pi * np.cumsum(freq) / SR)
    env = np.minimum(1, t / 0.008) * np.exp(-t / 0.08)
    return fade_edges(s * env, 1, 10)


def whoosh():
    dur = 0.22
    t = t_axis(dur)
    noise = rng.standard_normal(len(t))
    y = bandpass_sweep(noise, 600, 2400, q=1.4)
    env = np.sin(math.pi * t / dur) ** 2  # soft swell in and out
    y = y * env
    return fade_edges(y / (np.abs(y).max() + 1e-9), 3, 10)


def sparkle():
    a = bell(1319, 0.42, 0.35, 2, 0.3)
    b = bell(1760, 0.42, 0.35, 2, 0.3)
    off = int(0.06 * SR)
    out = np.zeros(off + len(b))
    out[: len(a)] += a
    out[off:] += b
    return out / np.abs(out).max()


def swipe():
    dur = 0.18
    t = t_axis(dur)
    noise = rng.standard_normal(len(t))
    y = bandpass_sweep(noise, 2000, 300, q=1.4)
    env = np.minimum(1, t / 0.03) * np.exp(-t / 0.07)
    y = y * env
    return fade_edges(y / (np.abs(y).max() + 1e-9), 2, 10)


def clap():
    dur = 0.2
    t = t_axis(dur)
    noise = rng.standard_normal(len(t))
    burst_env = np.where(t < 0.025, 1.0, np.exp(-(t - 0.025) / 0.03))
    y = bandpass_sweep(noise * burst_env, 1200, 1200, q=1.8)
    env = np.minimum(1, t / 0.002) * np.exp(-t / 0.09 * 3)  # ~-26 dB by 90 ms... tail follows
    y = y * env
    return fade_edges(y / (np.abs(y).max() + 1e-9), 0.5, 10)


def xylo(freq):
    t = t_axis(0.34)
    env = np.exp(-t / (0.3 / 5.0))
    s = np.sin(2 * math.pi * freq * t) + 0.25 * np.sin(2 * math.pi * 3 * freq * t)  # 3rd at -12 dB
    return fade_edges(s * env, 1, 6)


ARP = [523.25, 659.25, 783.99, 1046.5, 1318.5]  # C5 E5 G5 C6 E6


def arpeggio(mul=1.0):
    step = int(0.07 * SR)
    notes = [bell(f * mul, 0.45, 0.4, 2, 0.3) for f in ARP]
    out = np.zeros(step * (len(notes) - 1) + len(notes[0]))
    for k, n in enumerate(notes):
        out[k * step : k * step + len(n)] += n * (0.8 + 0.05 * k)
    return out / np.abs(out).max()


def cymbal_swell():
    rise, fall = 0.3, 0.9
    t = t_axis(rise + fall)
    noise = rng.standard_normal(len(t))
    y = bandpass_sweep(noise, 5000, 5000, q=0.9)
    env = np.where(t < rise, (t / rise) ** 2, np.exp(-(t - rise) / (fall / 5.0)))
    y = y * env
    return fade_edges(y / (np.abs(y).max() + 1e-9), 2, 20)


def confetti_blip(freq):
    t = t_axis(0.04)
    env = np.sin(math.pi * t / 0.04) ** 2
    return np.sin(2 * math.pi * freq * t) * env


# ---- event placement --------------------------------------------------------
letters = T["letters"]
anchors = T["anchor"]
windows = T["window"]
choruses = T["chorus"]
beat = float(T["beat_estimate"])
chorus_starts = [c["start"] for c in choruses]

# relative gains (pre-normalisation), tuned so pops/sparkles lead and noise stays under
G = dict(pop=0.55, boing=0.5, whoosh=0.22, sparkle=0.35, swipe=0.2,
         clap=0.35, ding=0.45, tada=0.5, big_tada=0.55, cymbal=0.18)

pop_s = pop  # generated per letter for pitch variation
boing_s = boing()
sparkle_s = sparkle()
skipped_swipes = []
for i, L in enumerate(letters):
    w_in, w_out = windows[L]
    pitch = 1.0 + 0.10 * math.sin(i * 2.399)  # deterministic spread in +-10%
    place(pop_s(pitch), w_in, G["pop"], cat="pop")
    place(boing_s, w_in + 0.35, G["boing"], cat="boing")
    place(whoosh(), anchors[L] - 0.15, G["whoosh"], cat="whoosh")
    place(sparkle_s, anchors[L], G["sparkle"], cat="sparkle")
    ends_into_chorus = any(0 <= cs - w_out <= 0.4 for cs in chorus_starts)
    if ends_into_chorus:
        skipped_swipes.append(L)
    else:
        place(swipe(), w_out, G["swipe"], cat="swipe")

DING = dict(A=523, B=587, C=659, D=698, E=784, F=880, G=988)
tada_s = arpeggio(1.0)
for c in choruses:
    if "clap" in c:
        for k in range(4):
            place(clap(), c["clap"] + k * 2 * beat, G["clap"], cat="clap")
    for L, t in c["letters"].items():
        place(xylo(DING[L]), t, G["ding"], cat="chorus_ding")
    for key in ("round", "hooray"):
        if key in c:
            place(tada_s, c[key], G["tada"], pan=0.0, cat="tada_arpeggio")

thanks = float(T["thanks"])
place(arpeggio(0.5), thanks, G["big_tada"], pan=0.0, cat="big_tada")
place(cymbal_swell(), thanks, G["cymbal"], pan=0.0, cat="big_tada_cymbal")

# normalise everything so far to -10 dBFS peak
target = 10 ** (-10 / 20)
peak = np.abs(buf).max()
buf *= target / peak

# confetti shimmer: added after normalisation so it sits at -30 dBFS absolute
f_start, _ = T["finale"]
conf_amp = 10 ** (-30 / 20)
t = float(f_start)
while True:
    t += rng.exponential(1 / 6.0)
    if t + 0.04 >= thanks:
        break
    place(confetti_blip(rng.uniform(2000, 5000)), t, conf_amp, cat="confetti")

peak = np.abs(buf).max()
if peak > target:  # safety: keep the -10 dBFS peak contract
    buf *= target / peak
    peak = target
assert peak < 1.0

# Mix trim: the spec's -10 dBFS stem pushed the preview mix over -1 dBTP on top of
# the -1.5 dBTP song master, so the whole stem (confetti included) is trimmed here.
# Final stem peak = -10 + STEM_TRIM_DB dBFS. Set STEM_TRIM_DB = 0 for the raw spec level.
STEM_TRIM_DB = -6.0
buf *= 10 ** (STEM_TRIM_DB / 20)
peak = np.abs(buf).max()

pcm = np.clip(np.round(buf * 32767), -32768, 32767).astype("<i2")
out_dir = os.path.join(HERE, "audio")
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, "sfx.wav")
with wave.open(out, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())

print(f"wrote {out}  samples={N}  dur={N / SR:.3f}s  peak={20 * math.log10(peak):.2f} dBFS")
print("swipe skipped (window ends into a chorus):", ",".join(skipped_swipes))
for k in ["pop", "boing", "whoosh", "sparkle", "swipe", "clap", "chorus_ding",
          "tada_arpeggio", "confetti", "big_tada", "big_tada_cymbal"]:
    print(f"  {k:16s} {counts[k]}")
