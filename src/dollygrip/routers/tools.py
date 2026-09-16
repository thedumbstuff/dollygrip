"""Offline helpers that need no Resolve: timecode <-> frames maths.
Handy for agents computing record frames from a script's timings."""

from __future__ import annotations

from fastapi import APIRouter

from ..bridge import Rejected
from ..schemas import TimecodeConvert

router = APIRouter(prefix="/tools", tags=["tools"])


def frames_to_timecode(frames: int, fps: float, drop_frame: bool = False) -> str:
    nominal = int(round(fps))
    if drop_frame and nominal in (30, 60):
        drop = 2 if nominal == 30 else 4
        per_min = nominal * 60 - drop
        per_10min = per_min * 10 + drop
        d, m = divmod(frames, per_10min)
        if m < drop:
            m = drop
        frames = frames + drop * (9 * d + (m - drop) // per_min)
    ff = frames % nominal
    total_s = frames // nominal
    return f"{total_s // 3600:02d}:{(total_s // 60) % 60:02d}:{total_s % 60:02d}{';' if drop_frame else ':'}{ff:02d}"


def timecode_to_frames(tc: str, fps: float, drop_frame: bool = False) -> int:
    parts = tc.replace(";", ":").replace(".", ":").split(":")
    if len(parts) != 4:
        raise Rejected(f"Timecode {tc!r} must be HH:MM:SS:FF")
    h, m, s, f = (int(p) for p in parts)
    nominal = int(round(fps))
    total = ((h * 60 + m) * 60 + s) * nominal + f
    if drop_frame and nominal in (30, 60):
        drop = 2 if nominal == 30 else 4
        total_minutes = h * 60 + m
        total -= drop * (total_minutes - total_minutes // 10)
    return total


@router.post("/timecode")
def convert_timecode(body: TimecodeConvert):
    """Convert frames -> timecode or timecode -> frames at a given fps."""
    if body.frames is None and body.timecode is None:
        raise Rejected("Give `frames` or `timecode`")
    out = {"fps": body.fps, "drop_frame": body.drop_frame}
    if body.frames is not None:
        out["frames"] = body.frames
        out["timecode"] = frames_to_timecode(body.frames, body.fps, body.drop_frame)
    else:
        out["timecode"] = body.timecode
        out["frames"] = timecode_to_frames(body.timecode, body.fps, body.drop_frame)
    out["seconds"] = out["frames"] / body.fps
    return out
