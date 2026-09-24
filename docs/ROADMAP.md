# Roadmap

The goal: everything a human can do in Resolve, reachable over HTTP (and as
MCP tools) - from "assemble and render a cut" to full post pipelines: motion
graphics, grading, VFX compositing, sound. Blockbuster-grade automation, one
endpoint at a time.

## Where we are (v0.5)

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
| `dollygrip mcp` - every endpoint as an MCP tool (stdio), profiles, resources | done |
| Composite edits: relocate (move/trim, linked A/V), split, ripple insert | done |
| Recipes: `POST /recipes/run`, `dollygrip run` (templating, dry-run) | done |
| Render progress as server-sent events | done |
| Fusion parameter discovery, expressions, bypass | done |
| Stock footage: Pexels/Pixabay/Coverr search, shot planner, Resolve-native stitch, one-call b-roll | done |
| Timecode helpers | done |

## Next

- **Retime**: the API exposes RetimeProcess but no speed setter; a composite
  retime via a Fusion TimeSpeed tool in a Fusion clip is the candidate.
- **Progress for long AI analyses** (transcription, IntelliSearch) - Resolve
  gives no status callbacks; a heuristic watcher may be all that is possible.
- **Fusion macros**: import `.setting` templates with parameter overrides in
  one call (today: import comp, then `list_tool_inputs` + `set_tool_inputs`).
- **Recipe library**: shareable recipe files for common deliverables
  (vertical reel, podcast clip, dailies with burn-ins).
- **Stock depth**: more providers (Storyblocks/Artgrid need paid accounts),
  AI-generated shots as a provider, keyword extraction from a script via an
  LLM step, transitions between shots (Resolve exposes none via the API -
  Fusion cross-dissolve composite is the candidate), BGM bed with fade.
- **v2 contract pass**: consistent `{ok, data}` envelopes once v1 usage
  settles (v1 stays frozen).

## Someday

- Fairlight beyond presets (whatever future API versions expose).
- Multi-machine: point one gateway at a render node fleet.
- The web pages on / now show status and docs; a live render-queue / job-progress panel is the remaining dashboard piece.

PRs against any of these welcome - match the router style, extend the fake in
`tests/fake_resolve.py`, one test per endpoint.
