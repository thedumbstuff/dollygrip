# Roadmap

The goal: everything a human can do in Resolve, reachable over HTTP - from
"assemble and render a cut" (done) to full post pipelines: motion graphics,
grading, VFX compositing, sound. Blockbuster-grade automation, one endpoint
at a time.

## v0.1 (now)

- Discovery + resilient bridge, projects, media pool, timeline assembly,
  render queue, page switching, guarded `/exec`, token auth, doctor.

## v0.2 - the edit page, properly

- Timeline items: list per track, transform properties (zoom/position/crop),
  opacity, composite modes, retimes.
- Markers: timeline + clip markers CRUD.
- In/out ranges, duplicate timeline, delete timeline.
- Media pool: relink, proxies, subclips, metadata read/write.
- Import AAF/EDL/XML/OTIO; export XML/OTIO (interchange with other tools).

## v0.3 - color and stills

- Gallery stills: grab, apply, import/export (LUT-less look transfer).
- Per-clip node basics the API exposes (versions, LUT apply, CDL).
- Burn-in presets.

## v0.4 - Fusion and titles

- Fusion comps: list, insert templates, set Text+ contents (data-driven
  titles and lower thirds without pre-rendered overlays).
- Template parameter setting for macro-based motion graphics.

## v0.5 - agents and pipelines

- `dollygrip mcp` - the same operations as MCP tools for AI agents.
- Webhooks / server-sent events for render progress (no more polling).
- Batch scripts: one POST that runs a whole recipe (import -> assemble ->
  render) transactionally, with a dry-run mode.
- Optional job queue for long renders.

## Someday

- Fairlight surface (whatever the API exposes).
- Multi-machine: point one gateway at a render node fleet.
- A tiny web dashboard on / for humans watching the run.

PRs against any of these welcome - match the router style, extend the fake in
tests/conftest.py, one test per endpoint.
