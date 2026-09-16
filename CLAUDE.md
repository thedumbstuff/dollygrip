# CLAUDE.md — dollygrip

Guidance for Claude Code when working in this repo.

## Overview

**DollyGrip** is an open-source local REST gateway for the DaVinci Resolve scripting API:
a FastAPI app (`127.0.0.1:4747`) that lets any HTTP client - shell, Node, n8n, CI, MCP,
AI agents - drive a running Resolve Studio. Swagger at `/docs`, everything under `/api/v1`.

**The standing goal**: keep growing this repo until everything a human can do in Resolve is
reachable over HTTP - full post pipelines (edit, color, Fusion, delivery). `docs/ROADMAP.md`
is the climb; pick endpoints from there unless directed otherwise. Born from a real
production pipeline (multi-track vertical reels, assembled and rendered fully scripted).

## Commands

```bash
uv sync                 # deps incl. dev group (uv, NOT pip; Python pinned to 3.13 - see traps)
uv run pytest -q        # the whole suite runs against an in-memory fake Resolve - no install needed
uv run dollygrip doctor # diagnose the Resolve connection (safe with Resolve down)
uv run dollygrip serve [--allow-exec] [--token X] [--port 4747]
```

No linters are configured; pytest is the only gate. Commit in logical chunks; never push
unless asked.

## Architecture

```
src/dollygrip/
  discovery.py   per-OS path discovery + THE SUBPROCESS PROBE (see traps) + interpreter scan
  bridge.py      ResolveBridge: cached handle, liveness probe, reconnect, threading.Lock,
                 object-graph helpers (current_project, clip_by_name, ...) raising domain errors
  deps.py        resolve_session dependency = the lock + ensure(); EVERY router op depends on it
  server.py      create_app(Settings, bridge) - token middleware, domain-error -> HTTP mapping
                 (ResolveUnavailable 503, NothingOpen 409, NotFound 404), router mounting
  schemas.py     pydantic REQUEST models only - responses stay loose dicts (Resolve returns
                 variable shapes; do not pretend otherwise)
  routers/       system, projects, mediapool, timelines, render, exec_ (one file per domain)
  cli.py         argparse: serve, doctor
tests/conftest.py  FakeResolve - an in-memory model of the scripting object graph
docs/GOTCHAS.md    the hard-won Resolve API traps ledger
docs/ROADMAP.md    what to build next
```

- Bridge is injectable (`ResolveBridge(connector=...)`) - that is how tests run without Resolve.
- `/exec` is the escape hatch: raw Python against live scripting objects, 403 unless
  `--allow-exec`. Never weaken that default; never default-bind beyond localhost.

## Critical traps

1. **NEVER import `DaVinciResolveScript` (or `fusionscript`) in-process without the
   subprocess probe passing first.** fusionscript segfaults - no exception, the interpreter
   DIES (0xC0000005) - on Python builds it dislikes. Verified against Resolve Studio 21:
   uv-managed standalone 3.11 crashes at import; python.org 3.13 works. That is why
   `.python-version` pins 3.13 and why all connects go through
   `discovery.subprocess_probe()`. Any new code path that touches the module must go
   through `discovery.connect_to_resolve()` or run its own sacrificial subprocess.
2. **The fusionscript handle is not thread-safe and goes stale when Resolve restarts.**
   All access must stay behind `deps.resolve_session` (lock + ensure/reconnect). Do not
   add async endpoints that touch the bridge outside that dependency.
3. **Resolve API semantics** (source-fps frames, absolute recordFrame, useCustomSettings
   ordering, audio endFrame ignored, stills/image-sequence misbehavior, same-track push):
   read `docs/GOTCHAS.md` BEFORE designing any timeline/render endpoint, and append every
   newly discovered trap there - it is the project's institutional memory.

## Conventions for new endpoints

1. Add the request model to `schemas.py` (typed request, loose dict response).
2. Add the route to the matching domain router (or a new router file, mounted in
   `server.py`); depend on `resolve_session`; raise the domain errors, never bare
   HTTPException for Resolve-state problems.
3. Extend `FakeResolve` in `tests/conftest.py` with the same method SHAPES the real API
   has (keep the fake honest - it is the contract), and add at least one test per endpoint
   including a failure case.
4. Sand off known traps inside the endpoint (like append's start-frame offset) and note it
   in the docstring + README's "sharp edges" list if user-visible.
5. Breaking changes to existing endpoint contracts go to `/api/v2`, never mutate v1.
6. Verify against real Resolve when it matters: `uv run dollygrip doctor`, then serve and
   curl. Requires Resolve STUDIO running with Preferences > System > General >
   External scripting = Local.

## Docs to keep in sync

- `README.md` is the public face (quickstart, API table, security, sharp edges).
- `docs/GOTCHAS.md` - append new traps with what was observed and on which version.
- `docs/ROADMAP.md` - tick off / refine as endpoints land.
- License is **Apache-2.0** (LICENSE file is the source of truth).
- Not affiliated with Blackmagic Design; nothing from Resolve is bundled - the scripting
  module loads from the user's own install at runtime. Keep it that way.
