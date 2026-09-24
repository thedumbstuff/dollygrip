"""Load a gitignored `.env` so provider keys can live in the project instead
of the shell. No dependency: KEY=VALUE lines, `#` comments, optional quotes,
optional `export ` prefix. Existing environment variables always win.

Search order (first hit is used unless `--env-file` names one explicitly):
  1. DOLLYGRIP_ENV_FILE
  2. ./.env (the current directory)
  3. <repo root>/.env (a checkout or editable install - so `dollygrip mcp`
     spawned from anywhere still finds the project's file)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key:
            out[key] = value
    return out


def candidates(explicit: Optional[str] = None) -> list:
    if explicit:
        return [Path(explicit)]
    paths = []
    if os.environ.get("DOLLYGRIP_ENV_FILE"):
        paths.append(Path(os.environ["DOLLYGRIP_ENV_FILE"]))
    paths.append(Path.cwd() / ".env")
    paths.append(REPO_ROOT / ".env")
    return paths


def load(explicit: Optional[str] = None, env: Optional[dict] = None) -> Optional[Path]:
    """Populate `env` (default os.environ) from the first existing candidate.
    Returns the file used, or None. Never overrides variables already set."""
    env = os.environ if env is None else env
    for path in candidates(explicit):
        if path.is_file():
            for key, value in parse(path.read_text(encoding="utf-8")).items():
                env.setdefault(key, value)
            return path
    if explicit:
        raise FileNotFoundError(f"env file not found: {explicit}")
    return None
