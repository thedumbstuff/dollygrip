"""Discover the Fusion templates Resolve can insert by name (Effects Library:
Titles, Generators, Effects, Transitions). Resolve exposes no API for this,
but the templates are `.setting` files in known folders, and the file stem is
exactly the name `InsertFusionTitleIntoTimeline` / `InsertFusionGeneratorIntoTimeline`
expect. Scans the system and per-user folders; `DOLLYGRIP_FUSION_TEMPLATE_DIRS`
(os.pathsep-separated) adds or replaces roots."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

KINDS = ("titles", "generators", "effects", "transitions")
_KIND_DIR = {"titles": "Titles", "generators": "Generators", "effects": "Effects", "transitions": "Transitions"}


def template_roots(env: Optional[dict] = None) -> List[Path]:
    env = os.environ if env is None else env
    override = env.get("DOLLYGRIP_FUSION_TEMPLATE_DIRS")
    if override:
        return [Path(p) for p in override.split(os.pathsep) if p]
    if sys.platform.startswith("win"):
        program_data = env.get("PROGRAMDATA", r"C:\ProgramData")
        appdata = env.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return [
            Path(program_data) / "Blackmagic Design" / "DaVinci Resolve" / "Fusion" / "Templates",
            Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Templates",
        ]
    if sys.platform == "darwin":
        return [
            Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Templates"),
            Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve" / "Fusion" / "Templates",
        ]
    return [
        Path("/opt/resolve/Fusion/Templates"),
        Path("/home/resolve/Fusion/Templates"),
        Path.home() / ".local" / "share" / "DaVinciResolve" / "Fusion" / "Templates",
    ]


def list_templates(kind: Optional[str] = None, env: Optional[dict] = None) -> List[Dict]:
    """Every template as {name, kind, category, path, source}; `name` is what
    the insert endpoints take. Duplicates (same kind+name) keep the first hit."""
    out: List[Dict] = []
    seen = set()
    kinds = [kind] if kind else list(KINDS)
    for root in template_roots(env):
        for k in kinds:
            base = root / "Edit" / _KIND_DIR.get(k, k.title())
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*.setting")):
                name = path.stem
                key = (k, name)
                if key in seen:
                    continue
                seen.add(key)
                rel = path.relative_to(base)
                out.append(
                    {
                        "name": name,
                        "kind": k,
                        "category": str(rel.parent).replace("\\", "/") if str(rel.parent) != "." else "",
                        "path": str(path),
                        "source": "user" if "AppData" in str(root) or str(Path.home()) in str(root) else "system",
                    }
                )
    return out
