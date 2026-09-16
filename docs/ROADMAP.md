# Roadmap

The goal: everything a human can do in Resolve, reachable over HTTP (and as
MCP tools) - from "assemble and render a cut" to full post pipelines: motion
graphics, grading, VFX compositing, sound. Blockbuster-grade automation, one
endpoint at a time.

## Where we are (v0.3)

Every object and method in Blackmagic's scripting README for Resolve 21 has a
typed endpoint (287 operations), plus the undocumented Fusion comp/tool API
and an MCP server mode. Live-verified end to end on Resolve Studio 21.0.4
(112-step smoke: projects, bins, import, timeline assembly, items, markers,
tracks, Fusion Text+ incl. keyframes, color versions/CDL/groups/gallery,
render + wait, OTIO/EDL/FCPXML export, project export).

| Area | Status |
|---|---|
| Discovery, resilient bridge, token auth, `/exec`, doctor | done (v0.1) |
| Projects: CRUD, folders, import/export/archive/restore, databases, presets | done |
| Media pool: bins, clips by id/name, import (files, image sequences, subclips), metadata, proxies, relink, mattes, audio sync, selection | done |
| Timelines: create/from-clips/import, tracks, append, playhead, marks, duplicate/delete, interchange export (17 types), generators/titles, compound & Fusion clips, stills, thumbnails | done |
| Timeline items: list/get/patch (all Inspector properties), delete, flags, takes, caches, stabilize, reframe, magic mask | done |
| Markers on timelines, items and clips | done |
| Color: versions, CDL, node graphs (clip/timeline/group), LUTs, DRX, groups, gallery albums & stills, LUT/frame export | done |
| Fusion: comps CRUD, tools, inputs, connections, keyframes, Text+ helper, current comp | done |
| Render: formats/codecs/resolutions, presets, queue, start/stop/wait, quick export, burn-in presets | done |
| System: layouts, preference presets, keyframe mode, Media Storage, quit | done |
| Studio AI: transcription, audio classification, auto subtitles, voice isolation, speech generation, deblur, IntelliSearch, slate, scene cuts, Dolby Vision | done (endpoints; needs the Extras installed to succeed) |
| `dollygrip mcp` - every endpoint as an MCP tool (stdio) | done |
| Timecode helpers | done |

## Next

- **More composite edit operations**: `relocate` (move/trim) and `split` exist;
  next are retime, ripple insert at playhead, and moving linked A/V together.
- **Recipes**: one POST that runs a whole pipeline (import -> assemble ->
  title -> grade -> render) with a dry-run plan; a `dollygrip run recipe.yaml`
  CLI.
- **Progress streaming**: server-sent events for render progress and long AI
  analyses (today: `POST /render/jobs/{id}/wait`).
- **Fusion depth**: macro/template parameter discovery (`GetInputList` with
  control metadata), comp import from `.setting` files with parameter
  overrides, expression setting.
- **MCP ergonomics**: profiles exist (`--profile editor|colorist|motion|delivery|core`);
  next: MCP resources for the OpenAPI doc and gotchas so agents can self-serve.
- **Cloud projects** (`CreateCloudProject` & co.) - unverified, needs a
  Blackmagic Cloud account.
- **v2 contract pass**: consistent `{ok, data}` envelopes once v1 usage
  settles (v1 stays frozen).

## Someday

- Fairlight beyond presets (whatever future API versions expose).
- Multi-machine: point one gateway at a render node fleet.
- A tiny web dashboard on / for humans watching the run.

PRs against any of these welcome - match the router style, extend the fake in
`tests/fake_resolve.py`, one test per endpoint.
