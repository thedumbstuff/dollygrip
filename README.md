<p align="center">
  <a href="https://github.com/thedumbstuff"><img src="docs/assets/dumbstuff_banner.jpg" alt="thedumbstuff - a small collection of ridiculous ideas for a brighter tomorrow" width="720"></a>
</p>

# DollyGrip

**A local REST gateway and MCP server for the DaVinci Resolve scripting API.** An open-source project by [thedumbstuff](https://github.com/thedumbstuff).

On a film set, the dolly grip is the crew member who physically drives the camera so the director gets the shot. DollyGrip does that for DaVinci Resolve: it sits next to a running Resolve Studio and exposes its scripting API as clean, documented HTTP endpoints (and, with `dollygrip mcp`, as MCP tools) - so any language, tool, or AI agent can drive your edit, grade, Fusion titles and delivery.

```bash
uv tool install "dollygrip[mcp]"   # or: pipx install "dollygrip[mcp]" / pip install "dollygrip[mcp]"
dollygrip doctor                   # diagnose your Resolve scripting setup
dollygrip serve                    # http://127.0.0.1:4747/docs
```

```bash
curl http://127.0.0.1:4747/api/v1/health
# {"gateway":"ok","resolve":"connected","product":"DaVinci Resolve Studio","version":"21.0.4.5"}
```

## Why

Resolve's Python scripting API is powerful but awkward to reach: it needs the right environment variables, the right Python build, the same machine, and a long-lived process. That locks out everything that is not local Python - shell scripts, Node tools, n8n / Zapier-style automations, CI jobs, and AI coding agents.

DollyGrip turns all of that into `curl` (or an MCP tool call):

- **The whole scripting surface** - 287 typed operations covering every object in Blackmagic's API for Resolve 21 (project manager, media pool, timelines, timeline items, markers, color versions / node graphs / groups / gallery, Fusion compositions, render queue, presets, Media Storage, Studio AI features) - plus the undocumented Fusion comp/tool API for data-driven Text+ titles.
- **Auto-discovery** - finds the scripting module on Windows / macOS / Linux in the documented install paths; `RESOLVE_SCRIPT_API` / `RESOLVE_SCRIPT_LIB` still win if you set them.
- **One persistent connection** - lazily connected, probed per request, transparently reconnects when Resolve restarts, serialized behind a lock (the fusionscript handle is not thread-safe).
- **Crash-proof discovery** - fusionscript segfaults (no exception - the interpreter dies) on Python builds it dislikes; DollyGrip proves the import in a sacrificial subprocess first, so the gateway survives and answers 503 with a hint instead of dying, and `dollygrip doctor` scans your interpreters for one that works.
- **Stable addressing** - timeline items by unique id, clips by id or name anywhere in the pool, bins by path, `current` for whatever is under the playhead. No object handles leak across HTTP.
- **Sharp edges sanded off** - source-fps frames, absolute record frames, `useCustomSettings` ordering, marker dicts flattened to lists, Fusion point tables from plain `[x, y]` lists (see below).
- **A guarded escape hatch** - `POST /api/v1/exec` runs raw Python against the live scripting objects. Off by default.
- **Interactive docs for free** - OpenAPI/Swagger at `/docs`; the same document generates the MCP tools.

Born out of a real production pipeline: assembling multi-track vertical social reels (spokesperson video + alpha graphics overlays + per-sentence subtitle clips + SFX beds) in Resolve, fully scripted. Live-verified end to end on Resolve Studio 21.0.4.

## Requirements

- DaVinci Resolve **Studio** (the free edition does not allow external scripting), running, with **Preferences > System > General > External scripting using: Local**.
- Python 3.9+ on the same machine (3.10+ for the MCP server) - but note fusionscript is picky about Python **builds**: against Resolve Studio 21 a python.org 3.13 worked while a uv-managed standalone 3.11 segfaulted at import. If `dollygrip doctor` reports a crash, its interpreter scan will tell you which of your Pythons works; the repo pins 3.13 for development.

## Quickstart: assemble, title and render a timeline

```bash
# 1. point the media pool at a bin (create it if missing)
curl -X POST localhost:4747/api/v1/mediapool/folders -H 'content-type: application/json' \
  -d '{"path": "auto-edits", "create": true}'

# 2. import media into it
curl -X POST localhost:4747/api/v1/mediapool/import -H 'content-type: application/json' \
  -d '{"paths": ["D:/shoot/interview.mp4", "D:/shoot/broll.mov"]}'

# 3. create a vertical 30fps timeline with an extra overlay track
curl -X POST localhost:4747/api/v1/timelines -H 'content-type: application/json' \
  -d '{"name": "reel-v1", "width": 1080, "height": 1920, "fps": 30, "extra_video_tracks": 1}'

# 4. place clips at exact frames (record_frame is 0-based from the timeline start)
curl -X POST localhost:4747/api/v1/timelines/current/append -H 'content-type: application/json' \
  -d '{"items": [
        {"clip_name": "interview.mp4", "start_frame": 0, "end_frame": 432, "record_frame": 0},
        {"clip_name": "broll.mov", "track_index": 2, "record_frame": 90}
      ]}'

# 5. drop a data-driven Text+ title at the playhead
curl -X PUT  localhost:4747/api/v1/timelines/current/playhead -H 'content-type: application/json' -d '{"timecode": "00:00:01:00"}'
curl -X POST localhost:4747/api/v1/timelines/current/generators -H 'content-type: application/json' \
  -d '{"kind": "fusion_title", "name": "Text+", "text": "Homework, but with a tutor"}'

# 6. render and wait for it
JOB=$(curl -s -X POST localhost:4747/api/v1/render/jobs -H 'content-type: application/json' \
  -d '{"preset": "H.264 Master", "settings": {"TargetDir": "D:/out", "CustomName": "reel-v1", "SelectAllFrames": true}}' | jq -r .job_id)
curl -X POST "localhost:4747/api/v1/render/jobs/$JOB/wait?timeout=900"
```

More in [`examples/`](examples/) - including [`data_driven_titles.py`](examples/data_driven_titles.py), which styles and animates one Text+ per caption.

## Using DollyGrip with Claude

DollyGrip was built so an AI agent can operate Resolve like an editor, colorist and Fusion artist. Three ways to wire it up:

### 1. Claude Code as an MCP server (recommended)

`dollygrip mcp` runs the gateway as an MCP server over stdio - every endpoint becomes a tool (tool name = operation name, e.g. `append_items`, `text_plus`, `add_job`). Register it once:

```bash
# from a published install
claude mcp add dollygrip -- dollygrip mcp

# or straight from a checkout
claude mcp add dollygrip -- uv run --directory /path/to/dollygrip dollygrip mcp
```

Then just talk to it:

> "Open the TutorBee project, list the timelines, and tell me how long the R8 cut is."
>
> "Create a 1080x1920 30fps timeline called `promo-v2`, put `spokes.mp4` on V1 from frame 0, `art.mov` on V2 starting at frame 30, add a Text+ title reading 'Snap the question' at 00:00:01:00 in gold, then render it with the H.264 Master preset to D:/out and wait for it."
>
> "Grab a still of every clip, export the grades as .drx to D:/looks, and copy the grade from the first clip to the rest."

All ~290 tools at once is a lot of context. Pick a profile, or trim with tags (the OpenAPI tags you see in `/docs`):

```bash
claude mcp add dollygrip -- dollygrip mcp --profile editor     # editor | colorist | motion | delivery | core | all
claude mcp add dollygrip -- dollygrip mcp --tags "projects,mediapool,timelines,timeline items,render"
```

Add `--allow-exec` only if you want Claude to be able to run arbitrary Python inside Resolve via the `exec_code` tool.

### 2. Claude Desktop (or any MCP client)

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dollygrip": {
      "command": "dollygrip",
      "args": ["mcp", "--profile", "editor"]
    }
  }
}
```

Cursor, Windsurf, Zed and other MCP clients take the same `command` + `args`.

### 3. Plain HTTP from any agent

Run `dollygrip serve` and let the agent `curl`. Drop this into your project's `CLAUDE.md` (or system prompt) so Claude Code knows the gateway exists:

```markdown
## DaVinci Resolve
A DollyGrip gateway runs at http://127.0.0.1:4747 (Swagger: /docs, OpenAPI: /openapi.json).
Drive Resolve through it with curl - never import DaVinciResolveScript directly.
Start with GET /api/v1/health, GET /api/v1/projects/current, GET /api/v1/timelines/current/items.
Frames: source in/out are in SOURCE fps; record_frame is 0-based from the timeline start.
Timeline items are addressed by the `id` from /timelines/current/items; clips by name or id.
```

### What Claude can do through it

| You say | DollyGrip calls |
|---|---|
| "Rough-cut these 12 clips in order, 3 seconds each" | `import_media` → `timeline_from_clips` / `append_items` |
| "Push every V2 clip 10 frames later and drop opacity to 80%" | `list_items` → `patch_item` (Inspector properties) |
| "Add chapter markers at each scene change" | `detect_scene_cuts` → `add_marker_timeline` |
| "Caption it" | `auto_subtitles` (Studio) or per-line `insert_generator` (fusion_title) + `text_plus` |
| "Match the look of clip 3 across the interview" | `add_color_group` → `assign_to_color_group`, or `copy_grades` |
| "Apply this .cube on node 2 of every clip" | `refresh_luts` → `set_node_lut_clip` |
| "Deliver a TikTok and a YouTube version" | `add_job` with presets → `wait_for_job` |
| "Save a .drx of every graded clip" | `grab_stills` → `export_stills` |
| "Animate the title size in over 10 frames" | `set_tool_keyframes` on the Text+ tool |

Things the Resolve API itself does not expose (so neither can any agent): building color nodes or reading grades back, the Fairlight mixer, Edit-page keyframes. Moving/trimming/splitting an item in place is not native either - DollyGrip's `relocate` and `split` rebuild the item for you (grade preserved when the move does not overlap itself on the same track). `/exec` covers the rest.

## API surface (v1)

287 operations under `/api/v1`; every request/response shape is in the interactive docs at `/docs`. By area:

| Area | Highlights |
|---|---|
| System | `health` · `system/info` · `system/constants` · `system/page` · layout & preference presets · `system/quit` (confirm) · Media Storage: `storage/volumes`, `storage/files`, `storage/add-to-mediapool` |
| Projects | list/create/open/rename/save/close/delete · settings · presets · project folders · import/export/archive/restore · databases · Fairlight presets · AI speech generation |
| Media pool | bins (tree/create/move/delete/export/import .drb) · clips by id or name (properties, metadata, color, flags, markers, mark in/out) · import files / image sequences / subclips · proxies · relink/unlink · replace · mattes · audio sync · stereo · selection · metadata CSV · transcription / classification / deblur / IntelliSearch / slate |
| Timelines | list/create/from-clips/import (AAF/EDL/XML/FCPXML/DRT/OTIO) · settings · tracks (add/rename/lock/enable/delete) · `append` · delete/link items · compound & Fusion clips · generators / titles / **Fusion Text+ with text** · playhead · mark in/out · markers · export (17 formats) · duplicate/delete · stills · thumbnail (JSON or PNG) · auto subtitles · scene cuts · voice isolation · Dolby Vision |
| Timeline items | list (with 0-based frames) · get/patch (name, enabled, color, **all Inspector properties**) · delete (ripple) · **relocate** (move/trim - re-append preserving properties, markers, Fusion comps and, when possible, the grade) · **split** · flags · markers · linked · audio mapping · takes · stabilize · smart reframe · magic mask · caches · burn-in |
| Color | versions · CDL · copy grades · LUT export · node graphs (clip / timeline / group pre+post: LUT, cache, enable, DRX, reset) · color groups · gallery albums & stills (import/export/label/delete) · export frame · keyframe mode |
| Fusion | comps (list/add/import/rename/load/export/delete) · tools (list/add/get/delete) · inputs · connect · **keyframes** · `text-plus` helper · current comp on the Fusion page |
| Render | formats/codecs/resolutions · presets (list/load/save/delete/import/export) · queue (add with preset/format/mode/settings, list, delete) · start/stop · **wait** · quick export · burn-in presets |
| Tools | `tools/timecode` (frames ⇄ timecode, drop-frame aware) |
| Escape hatch | `POST /exec` (requires `--allow-exec`) - namespace: `resolve, fusion, project_manager, project, media_pool, media_storage, timeline, gallery` |

### The sharp edges we sand off

The scripting API has traps that cost real hours. DollyGrip's endpoints encode the workarounds and document the rest in [docs/GOTCHAS.md](docs/GOTCHAS.md):

- `startFrame`/`endFrame` are in **source-fps** frames, not timeline fps.
- `recordFrame` is absolute - Resolve timelines usually start at 01:00:00:00, so the gateway takes a 0-based frame and adds the offset for you (and reports `start_rel`/`end_rel` on items).
- A clip's **Mark In/Out silently trims appends** that do not pass explicit frames.
- Per-timeline custom settings only stick if `useCustomSettings` is set first - the create and settings endpoints do the dance in order.
- `resolve.*` constants are not enumerable through `dir()`; the export/subtitle/sync endpoints take plain names and look the values up.
- Fusion wants 1-based tables for points and colors; send `[x, y]` / `[r, g, b, a]` lists.
- Overlapping appends on one track get pushed, stills and numbered image sequences misbehave, OTIO re-import needs `import_source_clips: false` - see the gotchas doc.

## Security

This gateway is **remote control for an application with filesystem access** - treat it accordingly.

- Binds to `127.0.0.1` by default. Keep it there.
- `--token <secret>` requires `Authorization: Bearer <secret>` on every call (health and docs stay open).
- `POST /exec` is **disabled by default**; `--allow-exec` turns it on. It is arbitrary code execution on the host, by design - never combine it with a non-localhost bind.
- `dollygrip mcp` runs in-process over stdio: nothing listens on the network at all.

## Development

```bash
git clone https://github.com/thedumbstuff/dollygrip && cd dollygrip
uv sync --extra mcp   # installs with the dev group (pytest, httpx) and the MCP server
uv run pytest         # ~100 tests against an in-memory fake Resolve - no install needed
uv run dollygrip serve
```

Contributions welcome - especially the composite edit operations on the roadmap and more Fusion depth. Match the existing router style, keep the fake in `tests/fake_resolve.py` honest, and add a test per endpoint.

## Disclaimer

DollyGrip is an independent open-source project, not affiliated with or endorsed by Blackmagic Design. "DaVinci Resolve" is a trademark of Blackmagic Design Pty Ltd. Nothing from Resolve is bundled or redistributed here - the gateway imports the scripting module from your own installation at runtime.

## License

[Apache-2.0](LICENSE)
