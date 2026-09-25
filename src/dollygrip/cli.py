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
    parser.add_argument("--env-file", default=None, help="KEY=VALUE file with provider keys etc. (default: DOLLYGRIP_ENV_FILE, ./.env, then <repo>/.env; existing env vars win)")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Run the gateway (Resolve Studio must be running)")
    serve.add_argument("--host", default="127.0.0.1", help="Bind address (keep it on localhost)")
    serve.add_argument("--port", type=int, default=4747, help="Port (default 4747 - GRIP on a keypad)")
    serve.add_argument("--token", default=None, help="Require 'Authorization: Bearer <token>' on every call")
    serve.add_argument("--media-dir", default=None, help="Folder for stock footage downloads (default ~/DollyGrip/stock or DOLLYGRIP_MEDIA_DIR)")
    serve.add_argument(
        "--allow-exec",
        action="store_true",
        help="Enable POST /api/v1/exec (raw Python against the scripting objects)",
    )

    sub.add_parser("doctor", help="Diagnose the connection to DaVinci Resolve")

    mcp = sub.add_parser("mcp", help="Run as an MCP server over stdio (for Claude Code, Claude Desktop, Cursor...)")
    mcp.add_argument("--allow-exec", action="store_true", help="Expose the exec_code tool (raw Python in Resolve)")
    mcp.add_argument("--profile", default="all", help="Curated tool set: all, editor, colorist, motion, delivery, core (default: all)")
    mcp.add_argument("--tags", default=None, help="Comma-separated OpenAPI tags to expose (overrides --profile), e.g. 'timelines,timeline items,render'")
    mcp.add_argument("--exclude-tags", default=None, help="Comma-separated tags to hide")

    runp = sub.add_parser("run", help="Run a recipe file (JSON, or YAML if pyyaml is installed) against Resolve without starting a server")
    runp.add_argument("recipe", help="Path to the recipe file: {steps: [{name, op, args}], stop_on_error}")
    runp.add_argument("--dry-run", action="store_true", help="Validate ops, argument names and templates offline (no Resolve connection)")
    runp.add_argument("--input", action="append", default=[], metavar="KEY=VALUE", help="Override a recipe input (value parsed as JSON when it parses, else a string); repeatable")
    runp.add_argument("--allow-exec", action="store_true", help="Allow exec_code steps")

    args = parser.parse_args(argv)

    from . import envfile

    used = envfile.load(args.env_file)
    if used and args.command != "mcp":
        print(f"loaded environment from {used}")
    elif used:
        print(f"loaded environment from {used}", file=sys.stderr)

    if args.command == "serve":
        return _serve(args)
    if args.command == "doctor":
        return _doctor()
    if args.command == "mcp":
        return _mcp(args)
    if args.command == "run":
        return _run(args)
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
    app = create_app(Settings(allow_exec=args.allow_exec, token=args.token, media_dir=args.media_dir))
    print(f"DollyGrip {__version__} - http://{args.host}:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def _mcp(args) -> int:
    from .mcp_server import PROFILES, serve_stdio
    from .server import Settings, create_app

    split = lambda v: [t.strip() for t in v.split(",") if t.strip()] if v else None  # noqa: E731
    if args.profile not in PROFILES:
        print(f"unknown profile {args.profile!r}; choose from {', '.join(PROFILES)}", file=sys.stderr)
        return 2
    include = split(args.tags) or PROFILES[args.profile]
    if include is not None and args.allow_exec and "exec" not in include:
        include = include + ["exec"]
    app = create_app(Settings(allow_exec=args.allow_exec))
    serve_stdio(app, include_tags=include, exclude_tags=split(args.exclude_tags))
    return 0


def _run(args) -> int:
    import json

    from .recipes import run_recipe_sync
    from .server import Settings, create_app

    with open(args.recipe, encoding="utf-8") as f:
        text = f.read()
    try:
        recipe = json.loads(text)
    except ValueError:
        try:
            import yaml  # type: ignore

            recipe = yaml.safe_load(text)
        except ImportError:
            print("Recipe is not JSON and pyyaml is not installed (pip install pyyaml for YAML recipes)", file=sys.stderr)
            return 2
    steps = recipe["steps"] if isinstance(recipe, dict) else recipe
    stop = recipe.get("stop_on_error", True) if isinstance(recipe, dict) else True
    inputs = dict(recipe.get("inputs") or {}) if isinstance(recipe, dict) else {}
    for pair in args.input:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            print(f"--input expects KEY=VALUE, got {pair!r}", file=sys.stderr)
            return 2
        try:
            inputs[key] = json.loads(value)
        except ValueError:
            inputs[key] = value
    app = create_app(Settings(allow_exec=args.allow_exec))
    report = run_recipe_sync(app, steps, dry_run=args.dry_run, stop_on_error=stop, inputs=inputs)
    for step in report["steps"]:
        line = f"[{step['status']:>7}] {step['name']} ({step.get('op')})"
        if step.get("error"):
            line += f" - {step['error']}"
        print(line)
    print(json.dumps(report, indent=2, default=str)) if args.dry_run else None
    return 0 if report["ok"] else 1


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
