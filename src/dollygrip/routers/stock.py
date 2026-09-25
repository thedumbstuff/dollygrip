"""Stock footage -> Resolve timeline. The MoneyPrinterTurbo idea (search a
provider per script keyword, pick clips that cover the voiceover, stitch)
done natively in Resolve: the clips land as real timeline items you can
still grade, retime and re-cut.

  POST /stock/keywords  script text -> search terms (heuristic or an LLM provider)
  POST /stock/search    keywords -> candidate materials (no download)
  POST /stock/download  materials -> files on the Resolve machine
  POST /stock/plan      keywords -> shot list (downloads by default)
  POST /stock/assemble  shot list -> timeline items (+ optional voiceover)
  POST /stock/b-roll    all of the above in one call (terms, or a script)
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..bridge import Rejected, ResolveBridge, require
from ..broll import Shot, plan_shots, total_duration
from ..deps import resolve_session
from ..keywords import keywords_from_script
from ..schemas import KeywordsRequest
from ..serialize import item_summary, safe
from ..stock import ASPECTS, PROVIDERS, Material, StockClient, StockError

router = APIRouter(prefix="/stock", tags=["stock"])

Aspect = Literal["portrait", "landscape", "square"]
Provider = Literal["pexels", "pixabay", "coverr"]
Mode = Literal["script_order", "random"]
Fit = Literal["fill", "fit", "none"]
_SCALING = {"fit": 2, "fill": 3}  # TimelineItem property "Scaling": SCALE_FIT / SCALE_FILL


def get_stock(request: Request) -> StockClient:
    client = getattr(request.app.state, "stock", None)
    if client is None:
        settings = request.app.state.settings
        client = StockClient(media_dir=getattr(settings, "media_dir", None))
        request.app.state.stock = client
    return client


# -- schemas -------------------------------------------------------------------


class SearchRequest(BaseModel):
    terms: List[str] = Field(description="Search keywords in script order, e.g. ['city at night', 'student studying']")
    provider: Provider = "pexels"
    aspect: Aspect = "portrait"
    min_duration: float = Field(default=3.0, ge=0)
    per_page: int = Field(default=20, ge=1, le=80)


class MaterialIn(BaseModel):
    provider: str
    id: str
    term: str = ""
    url: str
    width: int
    height: int
    duration: float
    page_url: str = ""
    author: str = ""
    fps: Optional[float] = None
    file: Optional[str] = None


class DownloadRequest(BaseModel):
    materials: List[MaterialIn]


class PlanRequest(SearchRequest):
    audio_duration: float = Field(description="Seconds of voiceover to cover")
    max_clip_duration: float = Field(default=5.0, gt=0, description="Longest shot in seconds")
    mode: Mode = "script_order"
    seed: Optional[int] = Field(default=None, description="Seed for random mode (reproducible plans)")
    download: bool = Field(default=True, description="Download the chosen clips so the plan is ready to assemble")


class ShotIn(BaseModel):
    file: str = Field(description="Local media file on the Resolve machine")
    source_in: float = Field(ge=0, description="Seconds into the source")
    source_out: float = Field(description="Seconds, exclusive")
    record_at: float = Field(ge=0, description="Seconds from the timeline start")
    term: str = ""
    provider: str = ""
    material_id: str = ""


class Voiceover(BaseModel):
    path: str = Field(description="Voiceover audio file on the Resolve machine")
    track_index: int = Field(default=1, ge=1)
    record_at: float = Field(default=0.0, ge=0)


class AssembleRequest(BaseModel):
    shots: List[ShotIn]
    track_index: int = Field(default=1, ge=1, description="Video track for the b-roll")
    bin: Optional[str] = Field(default=None, description="Bin path to import into (default: current bin)")
    fit: Fit = Field(default="fill", description="fill = scale + centre-crop to the frame (cover), fit = letterbox, none = leave Resolve's default")
    voiceover: Optional[Voiceover] = None


class BRollRequest(SearchRequest):
    terms: List[str] = Field(default_factory=list, description="Search keywords in script order (or give `script` instead)")
    script: Optional[str] = Field(default=None, description="Voiceover/script text; terms are derived per segment like POST /stock/keywords")
    max_terms: int = Field(default=8, ge=1, le=50, description="With `script`: how many derived terms to search")
    keywords_provider: Optional[Literal["heuristic", "anthropic", "openai", "deepseek"]] = Field(
        default=None, description="With `script`: keyword provider (None = env DOLLYGRIP_KEYWORDS_PROVIDER, else heuristic)"
    )
    audio_duration: Optional[float] = Field(default=None, description="Seconds to cover (or give voiceover_path and it is measured)")
    voiceover_path: Optional[str] = Field(default=None, description="Voiceover file; imported, placed on the audio track and used for the duration")
    voiceover_track: int = Field(default=1, ge=1)
    max_clip_duration: float = Field(default=5.0, gt=0)
    mode: Mode = "script_order"
    seed: Optional[int] = None
    track_index: int = Field(default=1, ge=1)
    bin: Optional[str] = None
    fit: Fit = "fill"


# -- helpers ---------------------------------------------------------------------


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except StockError as e:
        raise Rejected(str(e)) from e


def _tl_fps(tl) -> float:
    raw = str(tl.GetSetting("timelineFrameRate") or "30").upper().replace("DF", "").strip()
    return float(raw or 30)


def _clip_fps(clip, fallback: float) -> float:
    try:
        return float(clip.GetClipProperty("FPS") or 0) or fallback
    except Exception:
        return fallback


def _import_files(bridge: ResolveBridge, files: List[str], bin_path: Optional[str]) -> Dict[str, Any]:
    """Import each file once (skip ones already in the bin by name); return path -> clip."""
    import os

    mp = bridge.media_pool()
    if bin_path:
        mp.SetCurrentFolder(bridge.folder_by_path(bin_path, create=True))
    folder = mp.GetCurrentFolder()
    existing = {c.GetName(): c for c in folder.GetClipList() or []}
    clips: Dict[str, Any] = {}
    missing = []
    for path in dict.fromkeys(files):
        name = os.path.basename(path)
        if name in existing:
            clips[path] = existing[name]
        else:
            missing.append(path)
    if missing:
        imported = mp.ImportMedia(list(missing)) or []
        by_name = {c.GetName(): c for c in imported}
        for path in missing:
            clip = by_name.get(os.path.basename(path))
            if clip is None:
                raise Rejected(f"Resolve did not import {path!r} (file missing on the Resolve machine?)")
            clips[path] = clip
    return clips


def _assemble(bridge: ResolveBridge, shots: List[Dict], track_index: int, bin_path: Optional[str], fit: str, voiceover: Optional[Dict]) -> Dict:
    tl = bridge.current_timeline()
    mp = bridge.media_pool()
    tl_fps = _tl_fps(tl)
    start_abs = int(tl.GetStartFrame())
    while int(tl.GetTrackCount("video") or 0) < track_index:
        tl.AddTrack("video")

    result: Dict[str, Any] = {"items": [], "voiceover": None}
    if voiceover:
        while int(tl.GetTrackCount("audio") or 0) < voiceover["track_index"]:
            tl.AddTrack("audio", "stereo")
        vo_clip = _import_files(bridge, [voiceover["path"]], bin_path)[voiceover["path"]]
        appended = mp.AppendToTimeline([{"mediaPoolItem": vo_clip, "trackIndex": voiceover["track_index"], "recordFrame": start_abs + int(round(voiceover["record_at"] * tl_fps)), "mediaType": 2}])
        vo_item = appended[0] if appended else None
        if not vo_item:
            raise Rejected("Resolve refused to place the voiceover")
        vo_frames = int(vo_item.GetDuration())
        result["voiceover"] = {"item_id": safe(vo_item.GetUniqueId), "frames": vo_frames, "seconds": round(vo_frames / tl_fps, 3)}

    clips = _import_files(bridge, [s["file"] for s in shots], bin_path)
    for shot in shots:
        clip = clips[shot["file"]]
        fps = _clip_fps(clip, tl_fps)
        info = {
            "mediaPoolItem": clip,
            "trackIndex": track_index,
            "recordFrame": start_abs + int(round(shot["record_at"] * tl_fps)),
            "startFrame": int(round(shot["source_in"] * fps)),
            "endFrame": max(int(round(shot["source_in"] * fps)) + 1, int(round(shot["source_out"] * fps))),
            "mediaType": 1,
        }
        appended = mp.AppendToTimeline([info])
        item = appended[0] if appended else None
        entry = {"shot": shot, "ok": bool(item), "item_id": safe(item.GetUniqueId) if item else None}
        if item and fit in _SCALING:
            entry["scaling"] = bool(safe(item.SetProperty, "Scaling", _SCALING[fit]))
        if item:
            entry["item"] = item_summary("video", track_index, item, start_abs)
        result["items"].append(entry)
    result["all_ok"] = all(e["ok"] for e in result["items"])
    result["timeline"] = tl.GetName()
    return result


# -- endpoints ---------------------------------------------------------------------


@router.get("/providers")
def stock_providers(request: Request):
    """Which providers have API keys, and where downloads go."""
    client = get_stock(request)
    return {"providers": client.providers(), "media_dir": str(client.media_dir), "aspects": {k: list(v) for k, v in ASPECTS.items()}}


def _keywords(request: Request, text: str, max_terms: int = 8, per_segment: bool = True, provider: Optional[str] = None) -> Dict:
    # tests put an httpx transport on app.state to stub the LLM providers
    transport = getattr(request.app.state, "keywords_transport", None)
    return keywords_from_script(text, max_terms=max_terms, per_segment=per_segment, provider=provider, transport=transport)


@router.post("/keywords")
def stock_keywords(body: KeywordsRequest, request: Request):
    """Script / voiceover text -> stock-search terms, ready for /stock/search,
    /stock/plan or /stock/b-roll. Splits the script into sentences and keeps
    1-3 concrete, visual terms per segment plus a global list in script order.
    Offline heuristic by default; `provider` (or env DOLLYGRIP_KEYWORDS_PROVIDER)
    = anthropic | openai | deepseek asks an LLM with the matching *_API_KEY and
    falls back to the heuristic on any failure (`provider_used` says which ran,
    `fallback_reason` why). Returns {segments: [{text, terms}], terms, provider_used}."""
    if not body.text.strip():
        raise Rejected("text is empty")
    return _keywords(request, body.text, body.max_terms, body.per_segment, body.provider)


@router.post("/search")
def stock_search(body: SearchRequest, request: Request):
    """Candidates per keyword - nothing is downloaded."""
    client = get_stock(request)
    found = _wrap(client.search_many, body.terms, body.provider, body.aspect, body.min_duration, body.per_page)
    return {"results": {term: [m.to_dict() for m in mats] for term, mats in found.items()}, "count": sum(len(v) for v in found.values())}


@router.post("/download")
def stock_download(body: DownloadRequest, request: Request):
    client = get_stock(request)
    mats = [Material(**m.model_dump()) for m in body.materials]
    done = _wrap(client.download_all, mats)
    return {"materials": [m.to_dict() for m in done]}


def _plan(client: StockClient, body: PlanRequest) -> Dict:
    found = _wrap(client.search_many, body.terms, body.provider, body.aspect, body.min_duration, body.per_page)
    if not any(found.values()):
        raise Rejected(f"No {body.aspect} clips >= {body.min_duration}s found on {body.provider} for {body.terms}")
    shots = plan_shots(found, body.audio_duration, body.max_clip_duration, body.mode, body.seed)
    used = {(s.provider, s.material_id) for s in shots}
    materials = [m for mats in found.values() for m in mats if (m.provider, m.id) in used]
    if body.download:
        _wrap(client.download_all, materials)
        by_id = {(m.provider, m.id): m.file for m in materials}
        for s in shots:
            s.file = by_id[(s.provider, s.material_id)]
    return {
        "shots": [s.to_dict() for s in shots],
        "total_duration": total_duration(shots),
        "audio_duration": body.audio_duration,
        "materials": [m.to_dict() for m in materials],
        "attribution": sorted({f"{m.provider}: {m.author or m.id} - {m.page_url or m.url}" for m in materials}),
    }


@router.post("/plan")
def stock_plan(body: PlanRequest, request: Request):
    """Search, choose and (by default) download the clips that cover the audio;
    returns the shot list to hand to /stock/assemble."""
    return _plan(get_stock(request), body)


@router.post("/assemble")
def stock_assemble(body: AssembleRequest, bridge: ResolveBridge = Depends(resolve_session)):
    """Stitch a shot list onto the current timeline: import the files, append
    each shot at its record time with the source range converted using the
    clip's own fps, set fill/fit scaling, optionally place the voiceover."""
    shots = [s.model_dump() for s in body.shots]
    for s in shots:
        if s["source_out"] <= s["source_in"]:
            raise Rejected(f"shot at {s['record_at']}s: source_out must be > source_in")
    return _assemble(bridge, shots, body.track_index, body.bin, body.fit, body.voiceover.model_dump() if body.voiceover else None)


@router.post("/b-roll")
def stock_b_roll(body: BRollRequest, request: Request, bridge: ResolveBridge = Depends(resolve_session)):
    """The whole MoneyPrinterTurbo move in one call: keywords -> stock clips ->
    shot plan covering the voiceover -> real timeline items in Resolve. Give
    `terms`, or `script` (voiceover text; terms are derived per segment as in
    POST /stock/keywords and returned under `keywords`). Give `audio_duration`,
    or `voiceover_path` (placed on the audio track and measured)."""
    client = get_stock(request)
    keywords = None
    terms = list(body.terms)
    if not terms:
        if not (body.script or "").strip():
            raise Rejected("Give terms or script")
        keywords = _keywords(request, body.script, body.max_terms, True, body.keywords_provider)
        terms = keywords["terms"]
        if not terms:
            raise Rejected("No search terms could be derived from the script")
    tl = bridge.current_timeline()
    tl_fps = _tl_fps(tl)
    voiceover = None
    duration = body.audio_duration
    if body.voiceover_path:
        voiceover = {"path": body.voiceover_path, "track_index": body.voiceover_track, "record_at": 0.0}
    if duration is None and voiceover is None:
        raise Rejected("Give audio_duration or voiceover_path")
    pre = None
    if voiceover is not None and duration is None:
        # place the voiceover first to measure it with Resolve's own clock
        pre = _assemble(bridge, [], body.track_index, body.bin, body.fit, voiceover)
        duration = pre["voiceover"]["seconds"]
        voiceover = None
    plan_req = PlanRequest(
        terms=terms, provider=body.provider, aspect=body.aspect, min_duration=body.min_duration, per_page=body.per_page,
        audio_duration=duration, max_clip_duration=body.max_clip_duration, mode=body.mode, seed=body.seed, download=True,
    )
    plan = _plan(client, plan_req)
    built = _assemble(bridge, plan["shots"], body.track_index, body.bin, body.fit, voiceover)
    if pre:
        built["voiceover"] = pre["voiceover"]
    out = {"plan": {k: plan[k] for k in ("total_duration", "audio_duration", "attribution")}, "shots": len(plan["shots"]), **built, "timeline_fps": tl_fps}
    if keywords is not None:
        out["keywords"] = keywords
    return out
