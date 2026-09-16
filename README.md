# DollyGrip

**A local REST gateway for the DaVinci Resolve scripting API.**

On a film set, the dolly grip is the crew member who physically drives the camera so the director gets the shot. DollyGrip does that for DaVinci Resolve: it sits next to a running Resolve Studio and exposes its scripting API as clean, documented HTTP endpoints - so any language, tool, or AI agent that can speak HTTP can drive your edit.

```bash
uv tool install dollygrip        # or: pipx install dollygrip / pip install dollygrip
dollygrip doctor                 # diagnose your Resolve scripting setup
dollygrip serve                  # http://127.0.0.1:4747/docs
```

```bash
curl http://127.0.0.1:4747/api/v1/health
# {"gateway":"ok","resolve":"connected","product":"DaVinci Resolve Studio","version":"..."}
```

## Why

Resolve's Python scripting API is powerful but awkward to reach: it needs the right environment variables, the right Python, the same machine, and a long-lived process. That locks out everything that is not local Python - shell scripts, Node tools, n8n / Zapier-style automations, CI jobs, MCP servers, and AI coding agents.

DollyGrip turns all of that into `curl`:

- **Auto-discovery** - finds the scripting module on Windows / macOS / Linux in the documented install paths; `RESOLVE_SCRIPT_API` / `RESOLVE_SCRIPT_LIB` still win if you set them.
- **One persistent connection** - lazily connected, probed per request, transparently reconnects when Resolve restarts, and serialized behind a lock (the fusionscript handle is not thread-safe).
- **Crash-proof discovery** - fusionscript segfaults (no exception - the interpreter dies) on Python builds it dislikes; DollyGrip proves the import in a sacrificial subprocess first, so the gateway survives and answers 503 with a hint instead of dying, and `dollygrip doctor` scans your interpreters for one that works.
- **Typed endpoints for the workhorse operations** - projects, media pool, timeline assembly, rendering - with the API's sharp edges sanded off (see below).
- **A guarded escape hatch** - `POST /api/v1/exec` runs raw Python against the live scripting objects, so you are never blocked waiting for a typed endpoint to exist. Off by default.
- **Interactive docs for free** - OpenAPI/Swagger at `/docs`.

Born out of a real production pipeline: assembling multi-track vertical social reels (spokesperson video + alpha graphics overlays + per-sentence subtitle clips + SFX beds) in Resolve, fully scripted.

## Requirements

- DaVinci Resolve **Studio** (the free edition does not allow external scripting), running, with **Preferences > System > General > External scripting using: Local**.
- Python 3.9+ on the same machine - but note fusionscript is picky about Python **builds**: against Resolve Studio 21 a python.org 3.13 worked while a uv-managed standalone 3.11 segfaulted at import. If `dollygrip doctor` reports a crash, its interpreter scan will tell you which of your Pythons works; the repo pins 3.13 for development.

## Quickstart: assemble and render a timeline

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

# 5. render
curl -X POST localhost:4747/api/v1/render/jobs -H 'content-type: application/json' \
  -d '{"format": "mp4", "codec": "H264",
       "settings": {"TargetDir": "D:/out", "CustomName": "reel-v1", "SelectAllFrames": true,
                    "FormatWidth": 1080, "FormatHeight": 1920}}'

# 6. poll it
curl localhost:4747/api/v1/render/jobs   # or /render/jobs/{job_id}
```

More in [`examples/`](examples/).

## API surface (v1)

| Area | Endpoints |
|---|---|
| System | `GET /health` · `GET /system/info` · `POST /system/page` |
| Projects | `GET /projects` · `GET/POST /projects/current` · `POST /projects/current/save` · `GET/PATCH /projects/current/settings` |
| Media pool | `GET/POST /mediapool/folders` · `GET /mediapool/clips` · `POST /mediapool/import` |
| Timelines | `GET/POST /timelines` · `GET/POST /timelines/current` · `POST /timelines/current/tracks` · `POST /timelines/current/append` |
| Render | `GET /render/formats` · `GET /render/formats/{fmt}/codecs` · `GET/POST /render/jobs` · `GET/DELETE /render/jobs/{id}` · `GET /render/active` |
| Escape hatch | `POST /exec` (requires `--allow-exec`) |

All under `/api/v1`. Full request/response shapes live in the interactive docs at `/docs`.

### The sharp edges we sand off

The scripting API has traps that cost real hours. DollyGrip's endpoints encode the workarounds and document the rest in [docs/GOTCHAS.md](docs/GOTCHAS.md):

- `startFrame`/`endFrame` are in **source-fps** frames, not timeline fps.
- `recordFrame` is absolute - Resolve timelines usually start at 01:00:00:00, so the gateway takes a 0-based frame and adds the offset for you.
- Per-timeline custom settings only stick if `useCustomSettings` is set first - the create endpoint does the dance in order.
- Overlapping appends on one track get pushed, stills and numbered image sequences misbehave - see the gotchas doc.

## Security

This gateway is **remote control for an application with filesystem access** - treat it accordingly.

- Binds to `127.0.0.1` by default. Keep it there.
- `--token <secret>` requires `Authorization: Bearer <secret>` on every call (health and docs stay open).
- `POST /exec` is **disabled by default**; `--allow-exec` turns it on. It is arbitrary code execution on the host, by design - never combine it with a non-localhost bind.

## Using it from an AI agent

Any agent that can run `curl` or make HTTP calls can drive Resolve through DollyGrip - no Python environment gymnastics, no per-call process spawn, and the OpenAPI schema at `/openapi.json` doubles as tool documentation. An MCP server mode is on the [roadmap](docs/ROADMAP.md).

## Development

```bash
git clone https://github.com/shwetank/dollygrip && cd dollygrip
uv sync            # installs with the dev group (pytest, httpx)
uv run pytest      # the suite runs against an in-memory fake Resolve - no install needed
uv run dollygrip serve
```

Contributions welcome - especially typed endpoints for more of the API surface (markers, timeline items, color, Fusion, Fairlight). Match the existing router style, keep the fake in `tests/conftest.py` honest, and add a test per endpoint.

## Disclaimer

DollyGrip is an independent open-source project, not affiliated with or endorsed by Blackmagic Design. "DaVinci Resolve" is a trademark of Blackmagic Design Pty Ltd. Nothing from Resolve is bundled or redistributed here - the gateway imports the scripting module from your own installation at runtime.

## License

[MIT](LICENSE)
