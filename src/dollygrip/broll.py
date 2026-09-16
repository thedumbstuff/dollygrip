"""B-roll shot planning: turn stock materials (grouped by search term) into
an ordered shot list that covers a voiceover's duration.

Pure logic - no HTTP, no Resolve - so it is fully unit-tested. Mirrors
MoneyPrinterTurbo's `combine_videos` selection rules:

- each material is cut into segments of at most `max_clip_duration` seconds
  (the tail is kept, nothing is discarded);
- **random** mode shuffles all segments; **script_order** mode round-robins
  through the terms in the order given so the footage follows the script;
- unique sources come first (the longest segment of every source before any
  source repeats), then overflow segments;
- if the shots still fall short of the audio, they loop until covered.

Times are in SECONDS. The assembler converts to frames with the real clip
fps that Resolve reports after import (source-fps trap) and the timeline fps.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from .stock import Material


@dataclass
class Shot:
    order: int
    file: Optional[str]
    provider: str
    material_id: str
    term: str
    source_in: float  # seconds into the source file
    source_out: float  # exclusive
    record_at: float  # seconds from the timeline start
    duration: float
    width: int
    height: int
    looped: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


def _segments(m: Material, max_clip: float, min_tail: float) -> List[tuple]:
    """(start, end) pairs of at most max_clip seconds; a tail shorter than
    min_tail is merged into the previous segment (or kept if it is the only one)."""
    out = []
    t = 0.0
    while t < m.duration - 1e-6:
        end = min(t + max_clip, m.duration)
        if out and (end - t) < min_tail:
            out[-1] = (out[-1][0], end)  # extend the last segment rather than leave a stub
            break
        out.append((t, end))
        t = end
    return out


def plan_shots(
    materials_by_term: Dict[str, List[Material]],
    audio_duration: float,
    max_clip_duration: float = 5.0,
    mode: str = "script_order",
    seed: Optional[int] = None,
    min_tail: float = 1.0,
    padding: float = 0.1,
) -> List[Shot]:
    """Build the shot list. `materials_by_term` keeps script order (dict order)."""
    if audio_duration <= 0:
        raise ValueError("audio_duration must be > 0")
    if max_clip_duration <= 0:
        raise ValueError("max_clip_duration must be > 0")
    rng = random.Random(seed)

    # segments per material, tagged with term order
    per_term: List[List[dict]] = []
    for term, mats in materials_by_term.items():
        segs = []
        for m in mats:
            for i, (s, e) in enumerate(_segments(m, max_clip_duration, min_tail)):
                segs.append({"m": m, "s": s, "e": e, "term": term, "primary": i == 0})
        if segs:
            per_term.append(segs)
    if not per_term:
        return []

    # primaries (first/longest segment of each source) before overflow
    def split(segs):
        primaries = [x for x in segs if x["primary"]]
        overflow = [x for x in segs if not x["primary"]]
        return primaries, overflow

    ordered: List[dict] = []
    if mode == "random":
        prim, over = [], []
        for segs in per_term:
            p, o = split(segs)
            prim += p
            over += o
        rng.shuffle(prim)
        rng.shuffle(over)
        ordered = prim + over
    elif mode == "script_order":
        queues = []
        for segs in per_term:
            p, o = split(segs)
            queues.append(p + o)  # per term: its sources first, then their overflow
        # round-robin across terms so the footage walks through the script
        idx = [0] * len(queues)
        while True:
            progressed = False
            for qi, q in enumerate(queues):
                if idx[qi] < len(q):
                    ordered.append(q[idx[qi]])
                    idx[qi] += 1
                    progressed = True
            if not progressed:
                break
    else:
        raise ValueError(f"mode must be 'random' or 'script_order', got {mode!r}")

    required = audio_duration + padding
    shots: List[Shot] = []
    t = 0.0
    base: List[dict] = []
    for seg in ordered:
        if t >= required:
            break
        shots.append(_shot(len(shots), seg, t, required, looped=False))
        base.append(seg)
        t += shots[-1].duration
    # loop until the voiceover is covered
    i = 0
    while t < required - 1e-6 and base:
        seg = base[i % len(base)]
        shots.append(_shot(len(shots), seg, t, required, looped=True))
        t += shots[-1].duration
        i += 1
    return shots


def _shot(order: int, seg: dict, t: float, required: float, looped: bool) -> Shot:
    m: Material = seg["m"]
    length = seg["e"] - seg["s"]
    remaining = required - t
    if length > remaining:  # last shot: trim to the voiceover end
        length = remaining
    return Shot(
        order=order,
        file=m.file,
        provider=m.provider,
        material_id=m.id,
        term=seg["term"],
        source_in=round(seg["s"], 3),
        source_out=round(seg["s"] + length, 3),
        record_at=round(t, 3),
        duration=round(length, 3),
        width=m.width,
        height=m.height,
        looped=looped,
    )


def total_duration(shots: List[Shot]) -> float:
    return round(sum(s.duration for s in shots), 3)
