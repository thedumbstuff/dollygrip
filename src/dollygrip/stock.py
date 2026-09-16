"""Stock footage sourcing: search Pexels / Pixabay / Coverr for clips that
match a keyword, an aspect ratio and a minimum duration, and download them
onto the Resolve machine (with a search cache and a source record per file).

Modelled on MoneyPrinterTurbo's `material.py`, minus the moviepy stitching -
DollyGrip stitches inside Resolve instead (see broll.py + routers/stock.py).

API keys come from the environment (comma-separated lists rotate):
  PEXELS_API_KEY / DOLLYGRIP_PEXELS_KEYS
  PIXABAY_API_KEY / DOLLYGRIP_PIXABAY_KEYS
  COVERR_API_KEY  / DOLLYGRIP_COVERR_KEYS
Downloads go to DOLLYGRIP_MEDIA_DIR (default ~/DollyGrip/stock).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

ASPECTS = {"portrait": (1080, 1920), "landscape": (1920, 1080), "square": (1080, 1080)}
PROVIDERS = ("pexels", "pixabay", "coverr")
CACHE_TTL = 24 * 3600


class StockError(RuntimeError):
    """Provider/config problem (missing key, HTTP failure) - surfaces as 422."""


@dataclass
class Material:
    provider: str
    id: str
    term: str
    url: str  # direct video file URL of the chosen rendition
    width: int
    height: int
    duration: float
    page_url: str = ""
    author: str = ""
    fps: Optional[float] = None
    file: Optional[str] = None  # local path once downloaded

    @property
    def aspect(self) -> str:
        if self.height > self.width:
            return "portrait"
        if self.width > self.height:
            return "landscape"
        return "square"

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["aspect"] = self.aspect
        return d


def keys_from_env(provider: str, env: Optional[Dict[str, str]] = None) -> List[str]:
    env = os.environ if env is None else env
    raw = env.get(f"DOLLYGRIP_{provider.upper()}_KEYS") or env.get(f"{provider.upper()}_API_KEY") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def default_media_dir(env: Optional[Dict[str, str]] = None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("DOLLYGRIP_MEDIA_DIR") or (Path.home() / "DollyGrip" / "stock"))


def _http_get_json(url: str, params: Dict, headers: Dict) -> Dict:
    import httpx

    r = httpx.get(url, params=params, headers=headers, timeout=30, follow_redirects=True)
    if r.status_code >= 400:
        raise StockError(f"{url} -> HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def _http_download(url: str, dest: Path) -> None:
    import httpx

    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
        if r.status_code >= 400:
            raise StockError(f"download {url} -> HTTP {r.status_code}")
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    tmp.replace(dest)


class StockClient:
    """Search + download with pluggable HTTP (tests inject canned responses)."""

    def __init__(
        self,
        media_dir: Optional[Path] = None,
        keys: Optional[Dict[str, List[str]]] = None,
        fetch: Callable[[str, Dict, Dict], Dict] = _http_get_json,
        download: Callable[[str, Path], None] = _http_download,
        env: Optional[Dict[str, str]] = None,
        cache_ttl: float = CACHE_TTL,
    ):
        self.media_dir = Path(media_dir) if media_dir else default_media_dir(env)
        self.keys = keys if keys is not None else {p: keys_from_env(p, env) for p in PROVIDERS}
        self._fetch, self._download = fetch, download
        self._key_cycle = {p: itertools.cycle(v) for p, v in self.keys.items() if v}
        self._lock = threading.Lock()
        self._cache_ttl = cache_ttl
        self._cache: Dict[str, Dict] = {}
        self._cache_file = self.media_dir / ".dollygrip-stock-cache.json"
        self._load_cache()

    # -- config -------------------------------------------------------------

    def providers(self) -> Dict[str, bool]:
        return {p: bool(self.keys.get(p)) for p in PROVIDERS}

    def _key(self, provider: str) -> str:
        cycle = self._key_cycle.get(provider)
        if cycle is None:
            raise StockError(
                f"No API key for {provider}. Set {provider.upper()}_API_KEY (or DOLLYGRIP_{provider.upper()}_KEYS) "
                "in the gateway's environment. Pexels and Pixabay keys are free."
            )
        return next(cycle)

    # -- cache --------------------------------------------------------------

    def _load_cache(self):
        try:
            if self._cache_file.is_file():
                self._cache = json.loads(self._cache_file.read_text(encoding="utf-8"))
        except Exception:
            self._cache = {}

    def _save_cache(self):
        try:
            self.media_dir.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(json.dumps(self._cache), encoding="utf-8")
        except Exception:
            pass

    # -- search -------------------------------------------------------------

    def search(self, term: str, provider: str = "pexels", aspect: str = "portrait", min_duration: float = 3.0, per_page: int = 20) -> List[Material]:
        if provider not in PROVIDERS:
            raise StockError(f"Unknown provider {provider!r}; choose from {PROVIDERS}")
        if aspect not in ASPECTS:
            raise StockError(f"Unknown aspect {aspect!r}; choose from {tuple(ASPECTS)}")
        cache_key = f"{provider}|{aspect}|{min_duration}|{per_page}|{term.strip().lower()}"
        with self._lock:
            hit = self._cache.get(cache_key)
            if hit and time.time() - hit["at"] < self._cache_ttl:
                return [Material(**m) for m in hit["materials"]]
        fn = {"pexels": self._search_pexels, "pixabay": self._search_pixabay, "coverr": self._search_coverr}[provider]
        materials = [m for m in fn(term, aspect, per_page) if m.duration >= min_duration and m.aspect == aspect]
        if materials:
            with self._lock:
                self._cache[cache_key] = {"at": time.time(), "materials": [asdict(m) for m in materials]}
                self._save_cache()
        return materials

    def search_many(self, terms: List[str], provider: str, aspect: str, min_duration: float, per_page: int = 20) -> Dict[str, List[Material]]:
        out: Dict[str, List[Material]] = {}
        seen: set = set()
        for term in terms:
            found = []
            for m in self.search(term, provider, aspect, min_duration, per_page):
                if (m.provider, m.id) in seen:
                    continue
                seen.add((m.provider, m.id))
                found.append(m)
            out[term] = found
        return out

    def _search_pexels(self, term: str, aspect: str, per_page: int) -> List[Material]:
        data = self._fetch(
            "https://api.pexels.com/videos/search",
            {"query": term, "per_page": per_page, "orientation": aspect},
            {"Authorization": self._key("pexels")},
        )
        target_w, target_h = ASPECTS[aspect]
        out = []
        for v in data.get("videos", []) or []:
            files = [f for f in v.get("video_files", []) or [] if str(f.get("file_type", "")).endswith("mp4") and f.get("link")]
            if not files:
                continue
            best = _pick_rendition(files, "width", "height", min(target_w, target_h))
            if not best:
                continue
            out.append(
                Material(
                    provider="pexels",
                    id=str(v.get("id")),
                    term=term,
                    url=best["link"],
                    width=int(best.get("width") or v.get("width") or 0),
                    height=int(best.get("height") or v.get("height") or 0),
                    duration=float(v.get("duration") or 0),
                    page_url=v.get("url", ""),
                    author=(v.get("user") or {}).get("name", ""),
                    fps=float(best["fps"]) if best.get("fps") else None,
                )
            )
        return out

    def _search_pixabay(self, term: str, aspect: str, per_page: int) -> List[Material]:
        data = self._fetch(
            "https://pixabay.com/api/videos/",
            {"key": self._key("pixabay"), "q": term, "video_type": "all", "per_page": max(3, min(per_page, 200))},
            {},
        )
        target_w, target_h = ASPECTS[aspect]
        out = []
        for hit in data.get("hits", []) or []:
            renditions = [dict(r, name=name) for name, r in (hit.get("videos") or {}).items() if r.get("url")]
            best = _pick_rendition(renditions, "width", "height", min(target_w, target_h))
            if not best:
                continue
            out.append(
                Material(
                    provider="pixabay",
                    id=str(hit.get("id")),
                    term=term,
                    url=best["url"],
                    width=int(best.get("width") or 0),
                    height=int(best.get("height") or 0),
                    duration=float(hit.get("duration") or 0),
                    page_url=hit.get("pageURL", ""),
                    author=hit.get("user", ""),
                )
            )
        return out

    def _search_coverr(self, term: str, aspect: str, per_page: int) -> List[Material]:
        params = {"query": term, "page_size": per_page, "urls": "true"}
        if aspect == "portrait":
            params["filter"] = "is_vertical:true"
        elif aspect == "landscape":
            params["filter"] = "is_vertical:false"
        data = self._fetch("https://api.coverr.co/videos", params, {"Authorization": f"Bearer {self._key('coverr')}"})
        out = []
        for hit in data.get("hits", []) or []:
            url = (hit.get("urls") or {}).get("mp4")
            if not url:
                continue
            out.append(
                Material(
                    provider="coverr",
                    id=str(hit.get("id")),
                    term=term,
                    url=url,
                    width=int(hit.get("max_width") or 0),
                    height=int(hit.get("max_height") or 0),
                    duration=float(hit.get("duration") or 0),
                    page_url=hit.get("url", ""),
                    author=(hit.get("user") or {}).get("name", "") if isinstance(hit.get("user"), dict) else "",
                )
            )
        return out

    # -- download -----------------------------------------------------------

    def download(self, material: Material) -> Material:
        """Fetch the rendition once; write a sidecar .json source record."""
        self.media_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", material.id)
        dest = self.media_dir / f"{material.provider}-{safe_id}-{material.width}x{material.height}.mp4"
        if not dest.is_file():
            self._download(material.url, dest)
        record = dest.with_suffix(".json")
        if not record.is_file():
            info = material.to_dict()
            info.pop("file", None)
            info["url"] = _strip_query(material.url)
            record.write_text(json.dumps(info, indent=2), encoding="utf-8")
        material.file = str(dest)
        return material

    def download_all(self, materials: List[Material]) -> List[Material]:
        return [self.download(m) for m in materials]


def _pick_rendition(files: List[Dict], wkey: str, hkey: str, min_short_side: int) -> Optional[Dict]:
    """Smallest rendition whose short side reaches the target; else the largest."""
    sized = [f for f in files if f.get(wkey) and f.get(hkey)]
    if not sized:
        return files[0] if files else None
    good = [f for f in sized if min(int(f[wkey]), int(f[hkey])) >= min_short_side]
    if good:
        return min(good, key=lambda f: int(f[wkey]) * int(f[hkey]))
    return max(sized, key=lambda f: int(f[wkey]) * int(f[hkey]))


def _strip_query(url: str) -> str:
    return url.split("?", 1)[0]


def cache_key_for(term: str) -> str:  # exposed for tests/debugging
    return hashlib.sha1(term.strip().lower().encode()).hexdigest()[:10]


__all__ = ["ASPECTS", "PROVIDERS", "Material", "StockClient", "StockError", "default_media_dir", "keys_from_env", "field"]
