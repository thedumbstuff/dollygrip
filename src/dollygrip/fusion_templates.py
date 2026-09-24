"""Discover the Fusion templates Resolve can insert by name (Effects Library:
Titles, Generators, Effects, Transitions) plus the Fusion-page presets
(Particles, Shaders, Lens Flares, Styled Text, ...).

Resolve exposes no API for this, but the templates are `.setting` files:
loose on disk under the system / user template roots, or zipped inside
`.drfx` bundles (the built-ins ship as `Program Files/.../Fusion/Templates/
Templates.drfx`; user-installed packs are `.drfx` in the user root). The file
stem is exactly the name `InsertFusionTitleIntoTimeline` /
`InsertFusionGeneratorIntoTimeline` expect. `DOLLYGRIP_FUSION_TEMPLATE_DIRS`
(os.pathsep-separated) replaces the roots.

`extract(template)` materialises a bundle entry as a real file so Fusion's
`bmd.readfile` can load it (Fusion reads files, not zip members)."""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

KINDS = ("titles", "generators", "effects", "transitions", "fusion")
_EDIT_DIR = {"titles": "Titles", "generators": "Generators", "effects": "Effects", "transitions": "Transitions"}
_DIR_KIND = {v: k for k, v in _EDIT_DIR.items()}


def template_roots(env: Optional[dict] = None) -> List[Path]:
    env = os.environ if env is None else env
    override = env.get("DOLLYGRIP_FUSION_TEMPLATE_DIRS")
    if override:
        return [Path(p) for p in override.split(os.pathsep) if p]
    if sys.platform.startswith("win"):
        program_data = env.get("PROGRAMDATA", r"C:\ProgramData")
        program_files = env.get("PROGRAMFILES", r"C:\Program Files")
        appdata = env.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return [
            Path(program_files) / "Blackmagic Design" / "DaVinci Resolve" / "Fusion" / "Templates",
            Path(program_data) / "Blackmagic Design" / "DaVinci Resolve" / "Fusion" / "Templates",
            Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Templates",
        ]
    if sys.platform == "darwin":
        return [
            Path("/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Resources/Fusion/Templates"),
            Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Templates"),
            Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve" / "Fusion" / "Templates",
        ]
    return [
        Path("/opt/resolve/Fusion/Templates"),
        Path("/home/resolve/Fusion/Templates"),
        Path.home() / ".local" / "share" / "DaVinciResolve" / "Fusion" / "Templates",
    ]


def _classify(parts: List[str]):
    """('Edit', 'Titles', 'Lower Thirds', 'X.setting') -> (kind, category)."""
    if len(parts) >= 3 and parts[0] == "Edit" and parts[1] in _DIR_KIND:
        return _DIR_KIND[parts[1]], "/".join(parts[2:-1])
    if len(parts) >= 2 and parts[0] == "Fusion":
        return "fusion", "/".join(parts[1:-1])
    return None, None


def _source(root: Path) -> str:
    text = str(root)
    return "user" if "AppData" in text or str(Path.home()) in text else "system"


def list_templates(kind: Optional[str] = None, env: Optional[dict] = None) -> List[Dict]:
    """Every template as {name, kind, category, path, bundle, source}. `name`
    is what the insert endpoints take; `bundle` is set when the template lives
    inside a .drfx (then `path` is the member path). First hit wins per kind+name."""
    out: List[Dict] = []
    seen = set()

    def add(name, k, category, path, bundle, source):
        if kind and k != kind:
            return
        key = (k, name)
        if key in seen:
            return
        seen.add(key)
        out.append({"name": name, "kind": k, "category": category, "path": path, "bundle": bundle, "source": source})

    for root in template_roots(env):
        if not root.is_dir():
            continue
        source = _source(root)
        for path in sorted(root.rglob("*.setting")):
            parts = list(path.relative_to(root).parts)
            k, category = _classify(parts)
            if k:
                add(path.stem, k, category, str(path), None, source)
        for bundle in sorted(root.rglob("*.drfx")):
            try:
                with zipfile.ZipFile(bundle) as z:
                    members = [m for m in z.namelist() if m.endswith(".setting") and not m.startswith("__MACOSX")]
            except (zipfile.BadZipFile, OSError):
                continue
            for member in sorted(members):
                parts = member.split("/")
                k, category = _classify(parts)
                if k:
                    add(parts[-1][: -len(".setting")], k, category, member, str(bundle), source)
    return out


def find_template(ref: str, kind: Optional[str] = None, env: Optional[dict] = None) -> Optional[Dict]:
    """`ref` is a name ("Fade On"), "kind/name" ("titles/Fade On") or a
    category path ("fusion/Particles/Snow"). Case-insensitive."""
    want_kind = kind
    name = ref
    if "/" in ref and ref.split("/", 1)[0].lower() in KINDS:
        want_kind, name = ref.split("/", 1)
        want_kind = want_kind.lower()
    name_l = name.lower()
    for t in list_templates(want_kind, env):
        if t["name"].lower() == name_l:
            return t
        if t["category"] and f"{t['category']}/{t['name']}".lower() == name_l:
            return t
    return None


def cache_root() -> Path:
    """Where bundle members are extracted: `DOLLYGRIP_TEMPLATE_CACHE` or
    <temp>/dollygrip/fusion_templates."""
    override = os.environ.get("DOLLYGRIP_TEMPLATE_CACHE")
    return Path(override) if override else Path(tempfile.gettempdir()) / "dollygrip" / "fusion_templates"


def extract(template: Dict, cache_dir: Optional[Path] = None) -> str:
    """A real filesystem path for the template's .setting (bundle members are
    copied out into a cache folder keyed by the bundle's path, size and
    mtime, so two bundles with the same member name never collide)."""
    if not template.get("bundle"):
        return template["path"]
    bundle = Path(template["bundle"])
    try:
        stat = bundle.stat()
        key = hashlib.sha1(f"{bundle}|{stat.st_size}|{int(stat.st_mtime)}".encode("utf-8")).hexdigest()[:12]
    except OSError:
        key = hashlib.sha1(str(bundle).encode("utf-8")).hexdigest()[:12]
    target = (cache_dir or cache_root()) / key / template["path"].replace("/", os.sep)
    if not target.exists() or target.stat().st_size == 0:
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(template["bundle"]) as z:
            target.write_bytes(z.read(template["path"]))
    return str(target)
