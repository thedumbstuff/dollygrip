# DollyGrip Watchtower

The one page that says where the project stands: what works, what is verified
against a real Resolve, what is pending, what was decided and why, and what
development is required next. Update it in the same commit as the change it
describes. Agents get it as the MCP resource `dollygrip://watchtower`.

_Last updated: 2026-09-24 · version 0.5.0 · 43 commits (8 ahead of GitHub) · 164 tests green ·
333 operations · verified on DaVinci Resolve Studio 21.0.4.5 (Windows 11)_

---

## 1. Status at a glance

| Signal | State |
|---|---|
| API coverage of Blackmagic's Resolve 21 scripting README | Complete - every object and method has a typed endpoint |
| Undocumented Fusion comp/tool API | 50 operations, all live-verified: comps CRUD + attrs/undo/save/markers/history, tools CRUD + lock/colour/position/selection/active, input discovery (driver-aware), connections + disconnect + outputs, node graph, keyframes (set/read/clear) + key-time navigation, expressions, modifiers (Shake/Path/XYPath/Calculation/Offset/Expression/Probe/KeyStretcher), paste Effects Library / Fusion templates and macros with overrides, duplicate/presets, template + font + registry discovery |
| Live verification | 116-step smoke, composite edits, stock providers (Pexels, Pixabay, Coverr), three full productions, and the full 50-op Fusion pass (2026-09-24) on Studio 21.0.4 |
| Test suite | 164 pytest cases against `tests/fake_resolve.py` (the contract); no Resolve needed |
| Agent integration | `dollygrip mcp` (stdio, mcp 1.x and 2.x), profiles, resources; README CLAUDE.md snippet for plain HTTP |
| Production guide | `docs/VIDEO_CRAFT.md` - agents must read it before building a video |
| Real deliverables produced | "Counting 1 to 10" (16:9 + 9:16 + SRT), "Count With Me!" music video (2:43), "The ABC Song" (2:40, 26 stock clips + flash-card overlay) |
| Published | github.com/thedumbstuff/dollygrip (Apache-2.0); 8 commits ahead of `origin/main`, push is the user's call |

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
| **Fusion** | 50 | comps (list/add/import/rename/load/export/delete, **attrs** incl. comp time / render range / HiQ, **undo groups**, save), tools (list with type filter, add/get/rename/bypass/**lock/tile colour/flow position**/delete, **duplicate**, **preset save/load**), **input discovery** with control type, range, default, page, set inputs, **expressions**, connect, **node graph** (edges + positions), **keyframes** (set / read back / clear), **modifiers** (Shake, Path, XYPath, Calculation, Offset, Expression, Probe, KeyStretcher), **paste macros / `.setting` templates with per-tool overrides**, `text-plus` helper (+ shadow/outline/tracking), current comp on the Fusion page, **template discovery** (Titles/Generators/Effects/Transitions + Fusion-page presets, folders and `.drfx`), **font list**, comp **markers**, **active tool**, **undo/redo history**, **key-time navigation**, **selection**, **disconnect**, **outputs**, **tool registry**, **reset input**, multi-line Text+ | yes - all 50 live-verified on 2026-09-24 (template paste on fresh comps, particle preset, duplicate, markers, history, key times, selection, outputs, registry); four Resolve freezes bisected to `GetInput` on modifier-driven inputs, now guarded |
| **Stock** | 6 | Pexels / Pixabay / Coverr search with aspect, duration and rendition filters, 24 h cache, key rotation; shot planner (script order or random, unique sources first, loop to cover the voiceover); Resolve-native assemble with source-fps conversion and fill/fit; one-call `b-roll` | yes - all three providers searched live 2026-09-24; plan + download and a 26-clip assemble verified (ABC Song) |
| **Recipes** | 2 | `POST /recipes/run` and `dollygrip run`: ordered steps of any operation with `{{ steps.name.path }}` templating, dry-run, stop-on-error; `GET /recipes/operations` | yes |
| **Tools** | 1 | timecode <-> frames, drop-frame aware | yes |
| **Exec** | 1 | raw Python against the live scripting objects (`--allow-exec` only) | yes |

Cross-cutting: object addressing (items by unique id, clips by id or name, `current` for playhead/timeline/album), reconnect on Resolve restart, crash-proof subprocess import probe, `--token` auth, localhost-only default, `--media-dir`, MCP profiles `editor | colorist | motion | delivery | core | all`, MCP resources `openapi.json | operations | craft | gotchas | readme | watchtower`. Provider keys and paths can live in a gitignored `.env` (loaded by serve/mcp/run; `.env.example` committed). Human pages served by the gateway: `/` (live status, links), `/watchtower`, `/pages/craft|gotchas|roadmap|readme` (Markdown rendered, open even with `--token`).

## 3. Pending items

Ordered by value to the standing goal ("Claude can do everything a human can in Resolve").

| # | Item | Why it matters | Size |
|---|---|---|---|
| P2 | **Push** the 8 unpushed commits to github.com/thedumbstuff/dollygrip | GitHub is missing the Fusion depth, stock verification and the ABC example | XS - user action ("never push unless asked") |
| P3 | **Retime** - Resolve exposes `RetimeProcess` but no speed setter | slow-mo / speed ramps are basic editing | M - composite via Fusion clip + TimeSpeed tool |
| P4 | **Cross-dissolves between clips** - no transition API | stock b-roll cuts only | M - Fusion clip composite or a dissolve recipe over paired items |
| P6 | **Recipe library** - vertical reel, podcast clip, dailies with burn-ins, music video | agents start from proven pipelines | S each |
| P7 | **Progress for long AI analyses** (transcription, IntelliSearch) | today: fire and hope | M - heuristic watcher; Resolve gives no callbacks |
| P8 | **LLM keyword extraction** step for stock b-roll (script -> search terms) | completes the MoneyPrinterTurbo loop end to end | S - recipe step calling a model |
| P9 | **AI-generated shots as a stock provider** | when stock has nothing | M |
| P10 | **v2 contract pass** - uniform `{ok, data}` envelopes | cleanliness; v1 stays frozen | M |
| P11 | Web dashboard on `/` - landing + rendered docs shipped 2026-09-24; still to do: live render-queue and job progress panel | nice-to-have | S |
| P12 | Multi-machine / render node fleet | someday | L |
| P13 | **Perturb / Follower modifiers** - no scripting constructor on Resolve 21 | organic wobble and per-character text animation without hand-built splines | S - paste a modifier `.setting` via the Lua paste path, then connect |
| P14 | **Fusion live sequence in the release gate** - the paste / read / markers / history run (`live_fusion5.py`, scratchpad) | four freezes today were only caught live | S - fold into `scripts/live_smoke.py` |

Closed today: P1 (stock providers live, 2026-09-24), P5 (Fusion macro import with overrides, 2026-09-24). Dropped by decision: cloud projects (see §4).

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
| 2026-09-24 | Fusion **pastes run in Fusion's Lua** (`comp.Execute` + pcall + `SetData` hand-back), never `comp.Paste(table)` from Python | Python-side Paste returns True and pastes nothing: nested settings tables do not survive the bridge |
| 2026-09-24 | A comp is **opened on the Fusion page automatically** before paste / node layout (`_loaded`: playhead onto the item, load, open page, settle - page and playhead are LEFT there and reported in the response) | `comp.CurrentFrame` is None until the comp has been shown once; the Fusion page shows the clip under the playhead |
| 2026-09-24 | **Never `GetInput` a modifier-driven input** (Calculation / AnimCurves / Expression): every input read path checks the driver first and reports `driven_by` | bisected after four hard freezes (UI dead, CPU flat, Resolve killed each time): `GetInput("CharacterSpacing")` on the pasted Fade On template never returned. Splines and static inputs are safe |
| 2026-09-24 | `_loaded` **disables background tasks** first and **leaves the page / playhead on the item** after a paste (reported in the response) | the bisect that never froze did no page restore; fewer moving parts while Fusion evaluates a fresh comp |
| 2026-09-24 | Effects Library templates are read from **folders and `.drfx` bundles**, extracted to `%TEMP%/dollygrip` for `bmd.readfile` | built-ins ship zipped in `Templates.drfx`; Fusion cannot read zip members |
| 2026-09-24 | Modifier list is the **verified constructor set** (BezierSpline, Path, XYPath, Shake, Calculation, Offset, Expression, Probe, KeyStretcher) | `comp.Perturb()` / `comp.Follower()` do not exist on Resolve 21 |
| 2026-09-24 | **Work runs in parallel agents** for everything that does not touch Resolve (docs sync, fake-first endpoints); live probing stays one serial lane | user asked "why only one worker?"; Resolve is one instance behind one lock, but docs and fake-backed code are not |
| 2026-09-24 | **Tests never touch machine-wide caches** (`DOLLYGRIP_TEMPLATE_CACHE` per test) | a pytest run put fake JSON where the live gateway extracts templates; `bmd.readfile` returned nil and pastes went silent for an hour |
| 2026-09-24 | **Freezes are bisected with per-step `/exec` calls and 20 s client timeouts**, never one long request | each hard freeze costs a Resolve restart (about 90 s to scripting); naming the step on the first try is the only affordable way |

## 5. Development required

Concrete work, with the file it lands in.

**Gateway**
- Retime composite: `routers/items.py` `retime` op (Fusion clip + `TimeSpeed`), fake support, gotcha entry (P3).
- Dissolve composite for two adjacent items: `routers/items.py` or a recipe (P4).
- Stock: `keywords_from_script` step (LLM call behind an env-selected provider) and an `ai` provider adapter in `stock.py` (P8, P9).
- Optional: analysis watcher for `transcribe_*` / `intellisearch_*` (P7).

**Fusion follow-ups**
- Perturb / Follower via pasted modifier settings + connect (P13); Text+ follower presets from `Fusion/Styled Text` could cover most needs.
- `list_tool_inputs` for a template's GroupOperator: surface the published inputs (`Input1..n` with `Name`) as the override surface, so agents do not need to know inner tool names.
- A `delete_project` retry that closes the project first: `dg-fusion-probe5` could not be deleted through the API after switching projects (Resolve still reported it open) - reproduce and sand off.

**Quality and safety**
- Live smoke script promoted into the repo (`scripts/live_smoke.py`) as the release gate, now including the Fusion paste / read / markers / history sequence (P14); both currently live in the session scratchpad only.
- Provider live test behind an env flag (`PEXELS_API_KEY`) in the same smoke.
- `uv sync` / `dollygrip serve` clash after a version bump: document in CLAUDE.md (stop the server first) - done in memory, not yet in the repo docs.

**Docs**
- `examples/` index in README (nine entries now, only three linked).
- Recipe library folder `recipes/` with the four templates (P6).

**Release**
- Bump to 0.6.0 when P3 (retime) lands - P1 is closed; push (P2) is the user's call.

## 6. Known traps (pointer)

`docs/GOTCHAS.md` is the ledger - 45+ live-verified traps. The ones that bite
first: source-fps frames and exclusive `endFrame`; clip Mark In/Out trims
appends; fusionscript segfaults on the wrong Python build; a Merge without a
Background outputs nothing; spline attach leaves a stray key; a stem at
-69 dB renders silent; `ReplaceExistingFilesInPlace` is rejected; A/V appends
drop audio when the audio track does not exist; `comp.Paste` from Python is a
silent no-op (Lua only, on a comp opened once on the Fusion page); `GetInput`
on a Calculation / AnimCurves-driven input deadlocks Resolve (check the driver
first); comp markers are keyed by the table's own `time`.

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
