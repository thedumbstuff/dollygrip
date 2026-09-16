"""Locate and import DaVinci Resolve's scripting module on any OS.

Blackmagic ships the scripting API with Resolve itself; nothing is bundled
here. We find the `DaVinciResolveScript` module (and the fusionscript
library it loads) in the documented per-OS install locations, honouring the
same environment variables Blackmagic's own README describes:

  RESOLVE_SCRIPT_API   root of .../Support/Developer/Scripting
  RESOLVE_SCRIPT_LIB   full path to fusionscript.dll / .so / .dylib
  PYTHONPATH           must contain <RESOLVE_SCRIPT_API>/Modules

If the variables are already set they win; otherwise the defaults below are
tried. Import happens lazily so the gateway can start (and report a helpful
error) even when Resolve is not installed.
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class ScriptingPaths:
    api_root: str
    modules_dir: str
    lib_path: str


def default_paths() -> ScriptingPaths:
    if sys.platform.startswith("win"):
        api = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
        lib = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
    elif sys.platform == "darwin":
        api = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
        lib = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
    else:
        api = "/opt/resolve/Developer/Scripting"
        lib = "/opt/resolve/libs/Fusion/fusionscript.so"
    return ScriptingPaths(api_root=api, modules_dir=os.path.join(api, "Modules"), lib_path=lib)


def resolved_paths() -> ScriptingPaths:
    """Effective paths: environment overrides first, then per-OS defaults."""
    d = default_paths()
    api = os.environ.get("RESOLVE_SCRIPT_API", d.api_root)
    lib = os.environ.get("RESOLVE_SCRIPT_LIB", d.lib_path)
    return ScriptingPaths(api_root=api, modules_dir=os.path.join(api, "Modules"), lib_path=lib)


class ScriptingModuleNotFound(RuntimeError):
    """DaVinciResolveScript could not be imported."""


# Importing DaVinciResolveScript loads fusionscript.dll/.so, which HARD-
# CRASHES (segfault, not ImportError) on Python builds it dislikes - verified
# with a uv-managed standalone 3.11 against Resolve Studio 21 on Windows,
# while a python.org 3.13 was fine. So nothing may import the module
# in-process until a sacrificial subprocess has proven this interpreter
# survives it. Exit codes: 0 = connected, 2 = module fine but Resolve not
# reachable, 3 = import raised; anything else = native crash.
_PROBE_SNIPPET = r"""
import os, sys
sys.path.append(os.environ["DOLLYGRIP_MODULES_DIR"])
try:
    import DaVinciResolveScript as dvr
except Exception as e:
    print("import-error:", e)
    sys.exit(3)
resolve = dvr.scriptapp("Resolve")
sys.exit(0 if resolve is not None else 2)
"""


def subprocess_probe(timeout: float = 20.0, python_exe: Optional[str] = None) -> "tuple[str, str]":
    """Try the import + connect in a throwaway process.

    Returns (status, detail) with status one of:
    'connected', 'no-resolve', 'import-error', 'crash', 'timeout'.
    """
    import subprocess

    paths = resolved_paths()
    env = dict(os.environ)
    env.setdefault("RESOLVE_SCRIPT_API", paths.api_root)
    env.setdefault("RESOLVE_SCRIPT_LIB", paths.lib_path)
    env["DOLLYGRIP_MODULES_DIR"] = paths.modules_dir
    try:
        proc = subprocess.run(
            [python_exe or sys.executable, "-c", _PROBE_SNIPPET],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "timeout", f"probe did not finish within {timeout}s"
    if proc.returncode == 0:
        return "connected", ""
    if proc.returncode == 2:
        return "no-resolve", "module loaded but scriptapp('Resolve') returned nothing"
    if proc.returncode == 3:
        return "import-error", (proc.stdout or proc.stderr).strip()
    return "crash", (
        f"probe process died with code {proc.returncode} - fusionscript hard-crashed "
        "this interpreter, which usually means this Python build is one fusionscript "
        "cannot live with (observed with a uv-managed standalone 3.11 against Resolve "
        "21, while a python.org 3.13 worked). Run `dollygrip doctor` - it scans your "
        "other interpreters for one that works."
    )


def candidate_pythons() -> "list[str]":
    """Interpreters worth probing, most-specific first, deduped."""
    import shutil

    seen: dict = {}
    for cand in (
        os.environ.get("DOLLYGRIP_PYTHON"),
        sys.executable,
        getattr(sys, "_base_executable", None),
        shutil.which("python"),
        shutil.which("python3"),
    ):
        if cand and os.path.isfile(cand):
            key = os.path.normcase(os.path.realpath(cand))
            seen.setdefault(key, cand)
    return list(seen.values())


def scan_interpreters(timeout: float = 20.0) -> "list[dict]":
    """Probe every candidate interpreter; used by `dollygrip doctor`."""
    out = []
    for exe in candidate_pythons():
        status, detail = subprocess_probe(timeout=timeout, python_exe=exe)
        out.append({"python": exe, "status": status, "detail": detail})
    return out


def import_scripting_module():
    """Import DaVinciResolveScript, wiring up env + sys.path if needed."""
    paths = resolved_paths()
    os.environ.setdefault("RESOLVE_SCRIPT_API", paths.api_root)
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", paths.lib_path)
    if paths.modules_dir not in sys.path:
        sys.path.append(paths.modules_dir)
    try:
        return importlib.import_module("DaVinciResolveScript")
    except ImportError as e:
        raise ScriptingModuleNotFound(
            "Could not import DaVinciResolveScript. Checked modules dir: "
            f"{paths.modules_dir!r} and library: {paths.lib_path!r}. "
            "Install DaVinci Resolve (Studio is required for external scripting), "
            "or point RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB at your install. "
            f"Underlying error: {e}"
        ) from e


def connect_to_resolve():
    """Return a live handle to the running Resolve instance, or raise.

    A subprocess probe runs first: on some setups merely loading the scripting
    library segfaults when Resolve is down, and that must never take the
    gateway with it.
    """
    status, detail = subprocess_probe()
    if status != "connected":
        raise ConnectionError(
            "DaVinci Resolve is not reachable "
            f"(probe: {status}{' - ' + detail if detail else ''}). "
            "Make sure Resolve is RUNNING, you are on the Studio edition, and "
            "Preferences > System > General > 'External scripting using' is Local."
        )
    dvr = import_scripting_module()
    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        raise ConnectionError(
            "Resolve was reachable a moment ago but scriptapp('Resolve') "
            "returned nothing - did it just quit?"
        )
    return resolve


def probe() -> dict:
    """Non-raising diagnostic snapshot (used by /system/info and `dollygrip doctor`).

    All risky work happens in a subprocess - diagnostics must never crash the
    process they are diagnosing from.
    """
    paths = resolved_paths()
    info: dict = {
        "api_root": paths.api_root,
        "modules_dir": paths.modules_dir,
        "lib_path": paths.lib_path,
        "modules_dir_exists": os.path.isdir(paths.modules_dir),
        "lib_exists": os.path.isfile(paths.lib_path),
        "module_importable": False,
        "resolve_reachable": False,
        "error": None,
    }
    status, detail = subprocess_probe()
    info["probe_status"] = status
    if status == "connected":
        info["module_importable"] = True
        info["resolve_reachable"] = True
    elif status == "no-resolve":
        info["module_importable"] = True
        info["error"] = detail
    else:
        info["error"] = detail or status
    return info
