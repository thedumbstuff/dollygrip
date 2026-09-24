# DollyGrip Watchtower

The one page that says where the project stands: what works, what is verified
against a real Resolve, what is pending, what was decided and why, and what
development is required next. Update it in the same commit as the change it
describes. Agents get it as the MCP resource `dollygrip://watchtower`.

_Last updated: 2026-09-24 · version 0.5.0 · 38 commits · 139 tests green ·
302 operations · verified on DaVinci Resolve Studio 21.0.4.5 (Windows 11)_

---

## 1. Status at a glance

| Signal | State |
|---|---|
| API coverage of Blackmagic's Resolve 21 scripting README | Complete - every object and method has a typed endpoint |
| Undocumented Fusion comp/tool API | Covered for the parts a video needs: tools, inputs, discovery, connections, keyframes, expressions, bypass, comps CRUD |
| Live verification | 116-step smoke, composite edits, stock providers (Pexels, Pixabay, Coverr) and three full productions on Studio 21.0.4 |
| Test suite | 129 pytest cases against `tests/fake_resolve.py` (the contract); no Resolve needed |
| Agent integration | `dollygrip mcp` (stdio, mcp 1.x and 2.x), profiles, resources; README CLAUDE.md snippet for plain HTTP |
| Production guide | `docs/VIDEO_CRAFT.md` - agents must read it before building a video |
| Real deliverables produced | "Counting 1 to 10" (16:9 + 9:16 + SRT), "Count With Me!" music video (2:43), "The ABC Song" (2:40, 26 stock clips + flash-card overlay) |
| Published | github.com/thedumbstuff/dollygrip (Apache-2.0); local commits not pushed since publication |

## 2. Functionality available

Operation counts are from the live OpenAPI document (`GET /openapi.json`).

| Area | Ops | What you can do | Live-verified |
|---|---|---|---|
| **Media pool** | 58 | bins (tree/create/move/delete/export/import .drb), clips by id or name anywhere (properties, metadata, colour, flags, markers, mark in/out), import files / image sequences / subclips, proxies, relink/unlink, replace, mattes, audio sync, stereo, selection, metadata CSV, Studio AI on clips and bins (transcribe, classify, deblur, IntelliSearch, slate) | yes (AI calls return 422 without the Extras) |
| **Color** | 57 | versions, CDL, copy grades, LUT export, node graphs (clip / timeline / group pre+post: LUT, cache, enable, DRX, reset), colour groups, gallery albums and stills (import/export/label/delete), export frame, keyframe mode | yes |
| **Timelines** | 43 | create / from-clips / import (AAF, EDL, XML, FCPXML, DRT, OTIO), settings, tracks (add/rename/lock/enable/delete), append at exact frames, **ripple-insert**, delete/link items, compound and Fusion clips, generators / titles / Fusion titles with text, playhead, mark in/out, markers, export (17 formats), duplicate/delete, stills, thumbnail (JSON or PNG), auto subtitles, scene cuts, voice isolation, Dolby Vision | yes (auto subtitles needs the speech model) |
| **Timeline items** | 33 | list with 0-based frames, get/patch (name, enabled, colour, every Inspector property), delete (ripple), **relocate** (move/trim with linked A/V, keeps properties, markers, comps and grade when possible), **split**, flags, markers, linked, audio mapping, takes, stabilize, smart reframe, magic mask, caches, burn-in | yes |
| **Render** | 29 | formats/codecs/resolutions, presets (list/load/save/delete/import/export), queue (preset/format/mode/settings), start/stop, **wait**, **SSE progress**, quick export, burn-in presets | yes |
| **Projects** | 28 | list/create/open/rename/save/close/delete, settings, presets, project folders, import/export/archive/restore, databases, Fairlight presets, AI speech generation | yes (speech needs the Extras) |
| **System** | 25 | health, info, constants, page switching, layout and preference presets, background tasks, quit (confirmed), Media Storage browsing and add-to-pool | yes (Media Storage lists only inside configured locations) |
| **Fusion** | 19 | comps (list/add/import/rename/load/export/delete), tools (list/add/get/rename/bypass/delete), **input discovery** with control type, range, default, page, set inputs, **expressions**, connect, **keyframes** (real splines), `text-plus` helper, current comp on the Fusion page | yes - two full productions built this way |
| **Stock** | 6 | Pexels / Pixabay / Coverr search with aspect, duration and rendition filters, 24 h cache, key rotation; shot planner (script order or random, unique sources first, loop to cover the voiceover); Resolve-native assemble with source-fps conversion and fill/fit; one-call `b-roll` | yes - all three providers searched live 2026-09-24; plan + download and a 26-clip assemble verified (ABC Song) |
| **Recipes** | 2 | `POST /recipes/run` and `dollygrip run`: ordered steps of any operation with `{{ steps.name.path }}` templating, dry-run, stop-on-error; `GET /recipes/operations` | yes |
| **Tools** | 1 | timecode <-> frames, drop-frame aware | yes |
| **Exec** | 1 | raw Python against the live scripting objects (`--allow-exec` only) | yes |

Cross-cutting: object addressing (items by unique id, clips by id or name, `current` for playhead/timeline/album), reconnect on Resolve restart, crash-proof subprocess import probe, `--token` auth, localhost-only default, `--media-dir`, MCP profiles `editor | colorist | motion | delivery | core | all`, MCP resources `openapi.json | operations | craft | gotchas | readme | watchtower`. Provider keys and paths can live in a gitignored `.env` (loaded by serve/mcp/run; `.env.example` committed). Human pages served by the gateway: `/` (live status, links), `/watchtower`, `/pages/craft|gotchas|roadmap|readme` (Markdown rendered, open even with `--token`).

## 3. Pending items

Ordered by value to the standing goal ("Claude can do everything a human can in Resolve").

| # | Item | Why it matters | Size |
|---|---|---|---|
| P2 | **Push** the 32 local commits to github.com/thedumbstuff/dollygrip | v0.1 is what the world sees; v0.5 is local | XS - user action ("never push unless asked") |
| P3 | **Retime** - Resolve exposes `RetimeProcess` but no speed setter | slow-mo / speed ramps are basic editing | M - composite via Fusion clip + TimeSpeed tool |
| P4 | **Cross-dissolves between clips** - no transition API | stock b-roll cuts only | M - Fusion clip composite or a dissolve recipe over paired items |
| P5 | **Fusion macro import with overrides** - `.setting` templates in one call | data-driven motion graphics from the Effects Library | S |
| P6 | **Recipe library** - vertical reel, podcast clip, dailies with burn-ins, music video | agents start from proven pipelines | S each |
| P7 | **Progress for long AI analyses** (transcription, IntelliSearch) | today: fire and hope | M - heuristic watcher; Resolve gives no callbacks |
| P8 | **LLM keyword extraction** step for stock b-roll (script -> search terms) | completes the MoneyPrinterTurbo loop end to end | S - recipe step calling a model |
| P9 | **AI-generated shots as a stock provider** | when stock has nothing | M |
| P10 | **v2 contract pass** - uniform `{ok, data}` envelopes | cleanliness; v1 stays frozen | M |
| P11 | Web dashboard on `/` - landing + rendered docs shipped 2026-09-24; still to do: live render-queue and job progress panel | nice-to-have | S |
| P12 | Multi-machine / render node fleet | someday | L |

Dropped by decision: cloud projects (see §4).

## 4. Decisions made

| Date | Decision | Why |
|---|---|---|
| 2026-09-16 | Own repo, Apache-2.0, published as **thedumbstuff/dollygrip**; banner in README | open source from day one; licence aligned to LICENSE file |
| 2026-09-16 | Python **pinned to 3.13**; every import of `DaVinciResolveScript` goes through a **subprocess probe** | fusionscript segfaults (no exception) on some builds - uv 3.11 died, python.org 3.13 works |
| 2026-09-16 | All Resolve access behind **one lock**, `ensure()` reconnects on stale handles; `/exec` off by default; bind 127.0.0.1 | the handle is not thread-safe and the gateway is remote control of a machine |
| 2026-09-16 | **Responses stay loose dicts**, requests are typed | Resolve returns variable shapes; pretending otherwise breaks |
| 2026-09-16 | **Object addressing by unique id** (items), id-or-name (clips), path (bins) | HTTP clients cannot hold handles |
| 2026-09-16 | `FakeResolve` in `tests/fake_resolve.py` is **the contract**; keep it shaped like the real API | whole suite runs without Resolve; live traps are folded back into the fake |
| 2026-09-16 | **operationId = endpoint function name**, unique across routers | doubles as the MCP tool name and recipe op name |
| 2026-09-16 | MCP dispatches **in-process** through the FastAPI app (no second server); tool schemas generated from OpenAPI | one code path, zero drift |
| 2026-09-16 | Composite edits (`relocate`, `split`, `ripple-insert`) rebuild items and **report** what could not be preserved | the API cannot move items; honesty over magic |
| 2026-09-16 | **Cloud projects dropped** from the roadmap | user decision; needs a Blackmagic Cloud account to verify |
| 2026-09-16 | Stock footage is stitched **inside Resolve** (real timeline items), not with moviepy/ffmpeg | the output stays editable and gradable |
| 2026-09-16 | **`docs/VIDEO_CRAFT.md` is mandatory reading** for agents; MCP instructions and README snippet enforce it | tools are not taste; the first video exposed glyph, spacing and audio-level mistakes |
| 2026-09-16 | Disable background tasks before heavy Fusion edits; clients use timeouts | Resolve froze hard once on a comp write during background Fusion rendering |
| 2026-09-22 | Song-length compositions live in **one Fusion comp on a black carrier clip** | titles are fixed at 5 s and cannot be trimmed via the API |
| 2026-09-22 | Keyframe endpoint **parks comp time and static value on the first key** before attaching a spline | `SetKeyFrames(replace=True)` does not remove the stray key Fusion adds on attach |
| 2026-09-22 | Every video delivery includes **SEO title, description with chapters, and tags** (`<name>.metadata.md`) | user rule: videos are for publishing |
| 2026-09-16 | Commit in logical chunks, no attribution footers, **never push** unless asked | user's workflow |

## 5. Development required

Concrete work, with the file it lands in.

**Gateway**
- Retime composite: `routers/items.py` `retime` op (Fusion clip + `TimeSpeed`), fake support, gotcha entry (P3).
- Dissolve composite for two adjacent items: `routers/items.py` or a recipe (P4).
- `POST /fusion/items/{id}/comps/import-template` with `overrides` (P5).
- Stock: `keywords_from_script` step (LLM call behind an env-selected provider) and an `ai` provider adapter in `stock.py` (P8, P9).
- Optional: analysis watcher for `transcribe_*` / `intellisearch_*` (P7).

**Quality and safety**
- Live smoke script promoted into the repo (`scripts/live_smoke.py`) and documented as the release gate; currently in the session scratchpad only.
- Provider live test behind an env flag (`PEXELS_API_KEY`) in the same smoke (P1).
- `uv sync` / `dollygrip serve` clash after a version bump: document in CLAUDE.md (stop the server first) - done in memory, not yet in the repo docs.

**Docs**
- `examples/` index in README (eight examples now, only three linked).
- Recipe library folder `recipes/` with the four templates (P6).

**Release**
- Bump to 0.6.0 when P1 and P3 land; push (P2) is the user's call.

## 6. Known traps (pointer)

`docs/GOTCHAS.md` is the ledger - 30+ live-verified traps. The ones that bite
first: source-fps frames and exclusive `endFrame`; clip Mark In/Out trims
appends; fusionscript segfaults on the wrong Python build; a Merge without a
Background outputs nothing; spline attach leaves a stray key; a stem at
-69 dB renders silent; `ReplaceExistingFilesInPlace` is rejected; A/V appends
drop audio when the audio track does not exist.

## 7. Deliverables produced with DollyGrip

| Date | Deliverable | Where | Method |
|---|---|---|---|
| 2026-09-16 | Counting 1 to 10 - 16:9 and 9:16, SRT sidecars, metadata | `C:/Users/shwet/Videos/DollyGrip/` | 12 Fusion title cards built via the API (background, animated digit, word, stars, caption), SAPI voice, synthesized bed and pops; `examples/counting_cards.py` |
| 2026-09-22 | Count With Me! - 2:43 music video for a real song, metadata | same folder | one Fusion comp on a carrier clip, ~160 Blend-gated layers timed to Whisper word timestamps; `examples/count_with_me/` |
| 2026-09-24 | The ABC Song - 2:40, metadata + footage credits | same folder | 26 Pexels clips placed by `/stock/assemble` on V1, transparent flash-card overlay comp on V2 (~230 layers), official lyrics as captions; `examples/abc_song/` |

## 8. How to keep this page honest

1. Change code -> update §2 (counts come from `openapi.json`) and §5.
2. Decide something -> add a dated row to §4 with the why.
3. Finish a pending item -> move it out of §3 and into §2 or §7.
4. Learn a trap -> `docs/GOTCHAS.md` (and the fake), then a line in §6 if it bites first.
5. Refresh the header line (version, commits, tests, operations).
