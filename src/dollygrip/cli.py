from __future__ import annotations

import argparse
import sys

from . import __version__, discovery


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="dollygrip",
        description="A local REST gateway for the DaVinci Resolve scripting API.",
    )
    parser.add_argument("--version", action="version", version=f"dollygrip {__version__}")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Run the gateway (Resolve Studio must be running)")
    serve.add_argument("--host", default="127.0.0.1", help="Bind address (keep it on localhost)")
    serve.add_argument("--port", type=int, default=4747, help="Port (default 4747 - GRIP on a keypad)")
    serve.add_argument("--token", default=None, help="Require 'Authorization: Bearer <token>' on every call")
    serve.add_argument(
        "--allow-exec",
        action="store_true",
        help="Enable POST /api/v1/exec (raw Python against the scripting objects)",
    )

    sub.add_parser("doctor", help="Diagnose the connection to DaVinci Resolve")

    args = parser.parse_args(argv)

    if args.command == "serve":
        return _serve(args)
    if args.command == "doctor":
        return _doctor()
    parser.print_help()
    return 2


def _serve(args) -> int:
    import uvicorn

    from .server import Settings, create_app

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            f"WARNING: binding to {args.host} exposes full control of Resolve "
            "(and, with --allow-exec, this machine) to your network. "
            "Use --token at the very least.",
            file=sys.stderr,
        )
    app = create_app(Settings(allow_exec=args.allow_exec, token=args.token))
    print(f"DollyGrip {__version__} - http://{args.host}:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def _doctor() -> int:
    info = discovery.probe()
    checks = [
        ("Scripting modules dir exists", info["modules_dir_exists"], info["modules_dir"]),
        ("fusionscript library exists", info["lib_exists"], info["lib_path"]),
        ("DaVinciResolveScript imports", info["module_importable"], ""),
        ("Resolve reachable", info["resolve_reachable"], ""),
    ]
    ok = True
    for label, passed, detail in checks:
        mark = "OK  " if passed else "FAIL"
        ok = ok and passed
        print(f"[{mark}] {label}" + (f"  ({detail})" if detail else ""))
    if info["resolve_reachable"]:
        try:
            r = discovery.connect_to_resolve()
            print(f"       product: {r.GetProductName()}  version: {r.GetVersionString()}")
            pm = r.GetProjectManager()
            project = pm.GetCurrentProject() if pm else None
            print(f"       open project: {project.GetName() if project else '(none)'}")
        except Exception as e:  # noqa: BLE001
            print(f"       (detail probe failed: {e})")
    if not ok:
        print()
        if info["error"]:
            print(f"Last error: {info['error']}")
        if info.get("probe_status") == "crash":
            print("\nScanning your other Python interpreters (fusionscript is picky):")
            for row in discovery.scan_interpreters():
                verdict = {
                    "connected": "WORKS (Resolve reachable)",
                    "no-resolve": "imports fine (Resolve not reachable - is it running?)",
                    "crash": "hard-crashes fusionscript",
                }.get(row["status"], row["status"])
                print(f"  {row['python']}\n      -> {verdict}")
            print(
                "\nIf another interpreter works, run DollyGrip under it - e.g.\n"
                "  uv python pin 3.13 && uv sync     (in a checkout)\n"
                "  uv tool install dollygrip --python 3.13\n"
                "or set DOLLYGRIP_PYTHON for future probes."
            )
        print(
            "\nFixes: install/start DaVinci Resolve STUDIO, enable Preferences > System >\n"
            "General > 'External scripting using' = Local, or set RESOLVE_SCRIPT_API /\n"
            "RESOLVE_SCRIPT_LIB to your install paths. External scripting needs Studio;\n"
            "the free edition only scripts from Resolve's own console."
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
