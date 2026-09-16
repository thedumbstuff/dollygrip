# CLAUDE.md — dollygrip

Guidance for Claude Code when working in this repo.

## Overview

**DollyGrip** is an open-source local REST gateway (and MCP server) for the DaVinci Resolve
scripting API: a FastAPI app (`127.0.0.1:4747`) that lets any HTTP client - shell, Node, n8n,
CI, AI agents - drive a running Resolve Studio. Swagger at `/docs`, everything under `/api/v1`
(300+ operations as of v0.5). `dollygrip mcp` exposes the same operations as MCP tools.

**The standing goal**: everything a human can do in Resolve, reachable over HTTP. v0.4 covers
every method in Blackmagic's scripting README for Resolve 21, the (undocumented) Fusion
comp/tool API, composite edits the API lacks (relocate/split/ripple-insert), recipes, SSE render
progress, MCP profiles/resources and stock-footage b-roll (Pexels/Pixabay/Coverr -> planned shots ->
timeline). `docs/ROADMAP.md` lists what is left (retime, AI-analysis
progress, Fusion macro import, recipe library). Born from a real production pipeline.

## Commands

```bash
uv sync --extra mcp     # deps incl. dev group + the optional MCP server (uv, NOT pip; Python pinned 3.13 - see traps)
uv run pytest -q        # ~120 tests against an in-memory fake Resolve - no install needed
uv run dollygrip doctor # diagnose the Resolve connection (safe with Resolve down)
uv run dollygrip serve [--allow-exec] [--token X] [--port 4747]
uv run dollygrip mcp [--profile editor] [--tags timelines,render] [--allow-exec]   # stdio MCP server
uv run dollygrip run recipe.json [--dry-run]                       # run a pipeline without a server
```

No linters are configured; pytest is the only gate. Commit in logical chunks; never push
unless asked.

## Architecture

```
src/dollygrip/
  discovery.py   per-OS path discovery + THE SUBPROCESS PROBE (see traps) + interpreter scan
  bridge.py      ResolveBridge: cached handle, liveness probe, reconnect, RLock, domain errors,
                 and OBJECT ADDRESSING: item(id) / clip(ref) / timeline_by_name / folder_by_path /
                 fusion_comp / color_group / gallery_album (HTTP clients cannot hold Resolve handles)
  serialize.py   item_summary / clip_summary / marker_list / timeline_summary ... (null-safe)
  constants.py   the documented resolve.* enum names (the proxy does not enumerate them)
  deps.py        resolve_session dependency = the lock + ensure(); EVERY router op depends on it
  server.py      create_app(Settings, bridge) - token middleware, domain-error -> HTTP mapping
                 (ResolveUnavailable 503, NothingOpen 409, NotFound 404, Rejected 422),
                 operationId = function name (must be unique - test_contract enforces)
  schemas.py     pydantic REQUEST models only - responses stay loose dicts
  routers/       system (+storage), projects, mediapool, timelines (+ripple-insert), items
                 (+relocate/split composites), markers (factory, mounted 3x), color (graph factory
                 mounted 4x, groups, gallery), fusion (+input discovery/expressions), render (+SSE
                 events), recipes, stock (search/plan/assemble/b-roll), tools (offline timecode), exec_
  mcp_server.py  OpenAPI -> MCP tools (name = operationId) + resources, in-process ASGI dispatch,
                 mcp 1.x/2.x, PROFILES (curated tag sets)
  stock.py       StockClient: Pexels/Pixabay/Coverr search (filters, 24h cache, key rotation), downloads
                 + source records; fetch/download are injectable (tests use canned responses)
  broll.py       plan_shots: pure shot planning (segments, script_order/random, unique-first, loop)
  recipes.py     run_recipe: ordered steps of operations with {{ steps.name.path }} templating,
                 dispatched in-process through the app (routers/recipes.py exposes POST /recipes/run)
  cli.py         argparse: serve, doctor, mcp, run
tests/fake_resolve.py  FakeResolve - the in-memory model of the whole scripting object graph
tests/conftest.py      fixtures (client, fake_resolve, project, timeline, item_ids helper)
docs/GOTCHAS.md        the hard-won Resolve API traps ledger (append every new one)
docs/ROADMAP.md        what to build next
```

- Bridge is injectable (`ResolveBridge(connector=...)`) - that is how tests run without Resolve.
- Timeline items are addressed by `GetUniqueId()` (from `GET /timelines/current/items`);
  clips by name-in-current-bin, else unique id / media id / name anywhere; `current` works
  for the item under the playhead and the current timeline/album.
- `/exec` is the escape hatch: raw Python against live scripting objects, 403 unless
  `--allow-exec`. Never weaken that default; never default-bind beyond localhost.
- Resolve's bare `False` becomes `Rejected` (422) via `bridge.require(ok, reason)`.

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
   add async endpoints that touch the bridge outside that dependency. The one endpoint that
   sleeps (`/render/jobs/{id}/wait`) takes the lock per poll, never across the sleep.
3. **Resolve API semantics** (source-fps frames, absolute recordFrame, clip mark in/out
   trimming appends, useCustomSettings ordering, audio endFrame ignored, stills/image-sequence
   misbehavior, same-track push, OTIO re-import options, non-enumerable constants):
   read `docs/GOTCHAS.md` BEFORE designing any endpoint, and append every newly discovered
   trap there - it is the project's institutional memory.

## Conventions for new endpoints

1. Add the request model to `schemas.py` (typed request, loose dict response).
2. Add the route to the matching domain router (or a new router file, mounted in
   `server.py`); depend on `resolve_session`; raise the domain errors, never bare
   HTTPException for Resolve-state problems. Function names must be unique across ALL
   routers (they are the operationIds and the MCP tool names).
3. Extend `FakeResolve` in `tests/fake_resolve.py` with the same method SHAPES the real API
   has (keep the fake honest - it is the contract), and add at least one test per endpoint
   including a failure case.
4. Sand off known traps inside the endpoint (like append's start-frame offset) and note it
   in the docstring + README's "sharp edges" list if user-visible.
5. Breaking changes to existing endpoint contracts go to `/api/v2`, never mutate v1.
6. Verify against real Resolve when it matters: `uv run dollygrip doctor`, then serve and
   curl (a throwaway project, then delete it - closing first, Resolve refuses to delete the
   open project). Requires Resolve STUDIO running with Preferences > System > General >
   External scripting = Local.

## Docs to keep in sync

- `README.md` is the public face (quickstart, API table, Claude/MCP section, security, sharp edges).
- `docs/GOTCHAS.md` - append new traps with what was observed and on which version.
- `docs/ROADMAP.md` - tick off / refine as endpoints land.
- License is **Apache-2.0** (LICENSE file is the source of truth).
- Not affiliated with Blackmagic Design; nothing from Resolve is bundled - the scripting
  module loads from the user's own install at runtime. Keep it that way.
