# Resolve scripting API gotchas

Hard-won in production. The typed endpoints encode the workarounds where they
can; the rest you need to know when you reach for `/exec` or extend the API.

## Frames and timing

- **Source in/out are in SOURCE fps frames.** A 24fps clip trimmed onto a 30fps
  timeline takes `startFrame`/`endFrame` in 24fps frames. Passing timeline-fps
  numbers stretches the clip (a 433-frame 24fps clip is 18.04s = 541 timeline
  frames at 30fps - do the conversion yourself).
- **`recordFrame` is absolute.** Timelines usually start at 01:00:00:00
  (frame 108000 at 30fps). `GET /timelines/current` returns `start_frame`;
  the append endpoint takes a 0-based `record_frame` and adds the offset.
- **Audio appends ignore `endFrame`.** A long WAV extends the timeline past
  your video. Trim the rendered file afterwards (`ffmpeg -t <dur> -c copy`).

## Timeline assembly

- **Same-track overlapping appends get pushed, not layered.** Resolve shoves
  the later clip out of the way (or trims it). Put overlapping elements on
  separate tracks.
- **Stills are unreliable through `AppendToTimeline`** - durations and
  positions come out mangled. Convert overlays to exact-length movie files
  first (QuickTime Animation `qtrle` with `argb` carries alpha:
  `ffmpeg -framerate 30 -i f%04d.png -c:v qtrle -pix_fmt argb out.mov`).
- **Numbered image files fuse into an image sequence on import**
  (`sub1.png..sub5.png` becomes one `sub[1-5].png` clip). Use non-sequential
  names, or better, movs as above.
- **Per-timeline settings need `useCustomSettings` FIRST.** Set it to "1",
  then resolution/fps, or the values silently do not stick. (The create
  endpoint does this for you.)

## Environment

- **External scripting is Studio-only.** The free edition scripts only from
  Resolve's internal console.
- Preferences > System > General > "External scripting using" must be
  **Local**, and Resolve must be running.
- On Windows, use a 64-bit Python; the module loads `fusionscript.dll` from
  the Resolve install directory.
- The fusionscript handle **goes stale when Resolve restarts** and is not
  documented as thread-safe - DollyGrip reconnects transparently and
  serializes access behind a lock.
- **fusionscript is picky about the Python BUILD, and a mismatch is a
  SEGFAULT, not an ImportError.** Verified on Windows against Resolve
  Studio 21: a python.org 3.13 imports fine and behaves classically
  (scriptapp returns None when Resolve is down), while a uv-managed
  standalone Python 3.11 hard-crashed at `import DaVinciResolveScript` -
  exit 0xC0000005, no exception, the interpreter just dies - with Resolve
  running or not. DollyGrip therefore proves the import in a sacrificial
  subprocess before ever touching the module in-process, and
  `dollygrip doctor` scans your interpreters to find one that works.
- If Resolve QUITS while the gateway holds a live handle, the next call
  raised cleanly in our testing (3.13) and DollyGrip reconnects or answers
  503. The handle is still undocumented territory - for long unattended
  sessions a supervisor that restarts the gateway costs nothing.

## Rendering

- `SetCurrentRenderFormatAndCodec("mp4", "H264")` before `SetRenderSettings`.
- `AddRenderJob` returns the job id; `StartRendering(job_id)` then poll
  `IsRenderingInProgress()` / `GetRenderJobStatus(job_id)`.
- Renders include everything on the timeline - if an audio bed extended the
  timeline (see above), trim the output file.

## Learned while covering the full API (live on Resolve Studio 21.0.4, 2026-09-16)

- **A clip's Mark In/Out silently trims appends.** `AppendToTimeline` without
  `startFrame`/`endFrame` uses the media pool clip's mark in/out if one is
  set (a 180-frame clip marked 10..100 landed as 91 frames). Clear the marks
  (`DELETE /mediapool/clips/{ref}/mark-in-out`) or pass explicit frames.
- **`endFrame` is EXCLUSIVE.** `AppendToTimeline` with `startFrame: 0, endFrame: 44`
  lands 44 frames, and `TimelineItem.GetSourceEndFrame()` returns
  `source start + duration`. Think half-open ranges `[start, end)`.
- **`resolve.*` constants are not enumerable.** `dir(resolve)` lists none of
  the `EXPORT_*`, `MARKER_*`, ... enums, but `getattr` works (values are
  floats). `GET /system/constants` probes the documented names for you.
- **Re-importing a Resolve-exported OTIO fails with the default options** when
  the media is already in the pool. `import_source_clips: false` plus
  `source_clips_bins` pointing at the bin that holds the media imports fine.
- **FCPXML 1.10 export writes a bundle directory** (`name.fcpxml/Info.fcpxml`
  ...), not a single file. Plan file handling accordingly.
- **Media Storage listing only answers inside configured storage locations.**
  `GetSubFolderList` / `GetFileList` return `[]` for a drive root (`C:\`) or
  arbitrary paths; under a volume added in Preferences > Media Storage they
  work. `GET /storage/volumes` tells you where you may look.
- **Fusion comps ARE scriptable** even though the Resolve README does not list
  the comp/tool API: `comp.GetToolList()`, `AddTool(regid)`, `FindTool(name)`,
  `tool.SetInput(name, value[, time])`, `tool.<Input>[frame] = value` for
  keyframes, `tool.Delete()`, `comp.Save(path)`. A Fusion title inserted via
  `InsertFusionTitleIntoTimeline("Text+")` carries one `TextPlus` tool named
  `Template` - set `StyledText` on it for data-driven titles. Points/colors are
  1-based tables (`{1: x, 2: y}`); the gateway converts `[x, y]` lists.
- **`GetCurrentPage()` can be `None`** right after launch (project manager
  showing). `GetCurrentClipThumbnailImage` only returns data on the Color page.
- **Deleting the open project is refused**; close it (or load another) first.
  Closing an unsaved "Untitled Project" discards it - there is nothing to
  reopen.
- **`TimelineItem.GetProperty()` for enum keys returns the numeric constant**
  (CompositeMode 0 = Normal ...); pass numbers back when setting.

## Learned building the composite edits (live on Resolve Studio 21.0.4, 2026-09-16)

- **A/V appends need the audio track to exist.** `AppendToTimeline` with
  `trackIndex: 3` puts video on V3 and audio on A3; if A3 does not exist the
  audio part is dropped SILENTLY (no error, `GetLinkedItems()` is empty).
  Add the audio track first (`POST /timelines/current/tracks`).
- **Re-appending into an occupied range pushes and trims.** Relocating a clip
  onto a range another item occupies on the same track lands it AFTER that
  item and shortens it (requested 300 for 60 frames, got 310 for 50). The
  `relocate`/`ripple-insert` responses now flag this (`placed_as_requested`,
  `note`); check them.
- **Generators, titles and Fusion compositions cannot be re-appended** - they
  have no media pool item. `relocate` refuses them (422) and `ripple-insert`
  leaves them in place and lists them under `skipped`.
- **The Inspector page of a Fusion input is `INPS_ICS_ControlPage`** (values
  like `Text`, `Layout`, `Shading`, `Settings`), not `INPS_Page`. Text+ exposes
  ~309 inputs; `GET .../tools/{tool}/inputs?page=Text` narrows it.
- **`tool.<Input>.SetExpression(expr)` / `GetExpression()` work** on the live
  comp; the expression shows up in the input attrs immediately.

## Stock footage (providers, 2026-09-16)

- Provider keys live in the GATEWAY's environment (`PEXELS_API_KEY`, ...), not
  in requests; `GET /stock/providers` shows which are configured.
- Pexels renditions carry `fps`; Pixabay and Coverr do not. The assembler never
  trusts provider fps - it reads the clip's FPS from Resolve after import and
  converts the planned seconds to source frames with that.
- Pexels and Pixabay are free to use without credit, but both ask for it; the
  plan/b-roll responses return an `attribution` list - keep it with the export.
- Downloads are cached by `<provider>-<id>-<w>x<h>.mp4` in the media dir; a
  `.json` sidecar next to each file records provider, author, term and page URL.

## Learned making a real video end to end (Resolve Studio 21.0.4, 2026-09-16)

- **`ReplaceExistingFilesInPlace` makes `SetRenderSettings` return False** on
  this build even though the README lists it. Leave it out and use a new
  `CustomName` (Resolve refuses to overwrite anyway).
- **Fusion titles land where the playhead is, on the lowest track with room**
  - so on an EMPTY timeline, inserting titles at 0, 150, 300... puts them back
  to back on V1 exactly. Insert titles before other clips when you need exact
  placement; the default title length is 5 s (150 frames at 30 fps).
- **A Fusion title can carry its own background**: add a `Background` tool and
  `Merge`s inside the title's comp and rewire `MediaOut1.Input` - one item per
  card, no separate colour clips. `Background` colour = `TopLeftRed/Green/
  Blue/Alpha`; set `UseFrameFormatSettings: 1` so tools take the timeline size.
- **Fonts lacking a glyph render boxes, not fallbacks** - Comic Sans MS has no
  ★ (U+2605); put symbols in their own Text+ using `Segoe UI Symbol`.
- **Windows can voice a script offline**: `System.Speech.Synthesis` (SAPI
  voices Zira/David) writes WAVs that import straight into Resolve.

## Fusion animation (live on Resolve Studio 21.0.4, 2026-09-16)

- **`tool.Input[frame] = value` on a STATIC input does not animate** - it
  writes a static value; the last write wins. The digit "pop-in" rendered as
  a full-size digit and a Blend fade ended up as Blend = 0 (stars vanished).
- **Attaching a spline adds a stray key.** `tool.Input = comp.BezierSpline()`
  animates the input but Fusion drops a key at the comp's CURRENT time holding
  the old static value (a 0 at frame 5 in our case). Set all keys wholesale
  afterwards: `spline = tool.Input.GetConnectedOutput().GetTool();
  spline.SetKeyFrames({frame: {1: value}, ...}, True)` (True = replace).
  `POST .../tools/{tool}/keyframes` now does exactly this.
- **Expressions are the simplest fades**: `iif(time<8, time/8, iif(time>141,
  (149-time)/8, 1))` on `Merge.Blend` interpolates perfectly; no spline needed.
- **`Merge.Blend` fades only the foreground.** To fade a whole card, put a
  black `Background` + final `Merge` at the end of the chain and fade that.
- **Resolve froze hard (UI not responding, scripting call never returned)**
  once on a raw `SetInput("Blend", 1.0)` into a card comp while background
  Fusion rendering was active. Since then: call
  `POST /system/background-tasks/disable` before heavy comp edits, pace
  writes, and drive the gateway with client timeouts so a frozen Resolve
  cannot wedge your session. Restarting Resolve recovered; the saved project
  was intact.
- **Measure audio stems BEFORE importing** (`ffmpeg -af volumedetect`). A
  synthesized bed came out at -69 dB and was inaudible in the render - Resolve
  will not tell you.
- **A spline with a single key can evaluate to 0 after that key.** A constant
  set as one key at frame 0 rendered 1.0 at frame 0 and 0.0 after it on one
  card (its spline had history from an earlier stray key). For constants use
  two keys (first and last frame) - or set the static value with SetInput.
- **`CreateSubtitlesFromAudio` needs the Studio speech model downloaded**
  (Extras Download Manager); without it the call returns False. Burn captions
  in via Text+ and write an SRT yourself when you know the lines.
- **Duplicating a timeline copies the Fusion comps**; edits in the copy do not
  touch the original - the right way to make aspect-ratio variants.
- **`BezierSpline:SetKeyFrames(keys, True)` does NOT remove existing keys.**
  The stray key that attaching a spline leaves at the comp's current time
  survived "replace" and, on a 160-second comp with 150 Blend-gated layers,
  held every layer at 1.0 from frame 0 - everything rendered at once. The
  keyframes endpoint now sets the static value to the first key and parks
  `COMPN_CurrentTime` on the first key's frame before attaching, so the stray
  key coincides with a real one. Verify gating by reading `GetInput(name, t)`
  at a frame OUTSIDE your window.
- **A Merge with no Background outputs nothing** - and every tool downstream
  goes black. The first layer of a chain must be the background itself.
- **A comp meant to overlay lower tracks must stay transparent all the way
  down**: root Background with alpha 0 AND any fade/base Background at the end
  of the chain with alpha 0. One opaque black base hid 26 stock clips on V1.
- **Whisper splits sung letters into tokens** (`A`, `-B`, `-C`, `-D,`) and
  mishears the letters in "X is for ..." lines; anchor on the object words and
  caption from the official lyrics.
- **`RectangleMask` on a Background's `EffectMask`** makes a rounded panel;
  Center/Width/Height/CornerRadius are 0..1 of the frame.

## Fusion depth: paste, templates, modifiers (live on Resolve Studio 21.0.4, 2026-09-24)

- **`comp.Paste(table)` from Python returns True and pastes nothing.** Nested
  settings tables do not survive the Python bridge: `tool.SaveSettings()`
  arrives as `{'Tools': None}`. Paste must run in Fusion's own Lua:
  `comp.Execute('comp:Paste(bmd.readfile([[path]]))')`. The gateway's `lua()`
  helper wraps the body in `pcall` and hands the status (and any result) back
  through `comp:SetData` / `comp.GetData`, so a Lua error becomes a 422 with
  Fusion's own message.
- **`comp.Execute` returns before heavy scripts finish** (a particle preset
  paste took seconds). `lua()` polls the SetData status key until it appears
  (20 s default) instead of trusting the return.
- **Paste and FlowView only work once the comp has been opened on the Fusion
  page**: `comp.CurrentFrame` is None until then. The Fusion page shows the
  clip UNDER THE PLAYHEAD, so loading a comp for an item means: park the
  playhead on the item, `item.LoadFusionCompByName`, `resolve.OpenPage("fusion")`,
  wait for `CurrentFrame`, settle about 1 s - and then LEAVE the page and
  playhead there (see the freeze bullet below; the response reports what moved).
  The gateway does this automatically (`_loaded`) before pastes and duplicates,
  which is why the first paste into a comp takes a few seconds.
- **`COMPN_RenderEnd` is clamped to `COMPN_GlobalEnd`.** Setting both in one
  `SetAttrs` can leave the render end short. PATCH `.../attrs` applies the
  global range first, then the rest.
- **Modifier constructors that exist**: `comp.BezierSpline / Path / XYPath /
  Shake / Calculation / Offset / Expression / Probe / KeyStretcher`.
  `comp.Perturb` and `comp.Follower` are None in both Python and Lua. Calling
  a constructor without assigning it to an input leaves an orphan modifier
  tool in the comp, so the modifier endpoint only constructs while attaching.
- **Only `BezierSpline` holds keys.** Shake & co answer `GetKeyFrames` with
  their valid range `{1: -1e9, 2: 1e9}`, not keys. A spline's `GetKeyFrames`
  returns `{frame: {1: value, 'RH': {...}, 'LH': {...}}}`; GET `.../keyframes`
  drops the RH/LH handle tables and reads keys from splines only (a non-spline
  driver is reported as `modifier`).
- **`input.ConnectTo(None)` detaches a spline/modifier**, and the input then
  holds whatever value the animation had at the comp's current time. DELETE
  `.../keyframes` sets a static value explicitly afterwards (`?value=` or the
  current animated value).
- **Two coordinate systems for node positions**: FlowView positions are grid
  units (about 1.5, 1.0) while the `ViewInfo.Pos` stored in tool settings is
  something else (e.g. 385, 82). GET `.../graph` reports which one it used in
  `position_units` (`flow` when the comp is open on the Fusion page,
  `settings` otherwise); PATCH `position` sets FlowView units.
- **These work from Python as-is**: `tool.SaveSettings(path)` /
  `tool.LoadSettings(path)` with real file paths, `tool.TileColor = {"R", "G",
  "B"}`, `TOOLB_Locked` via `SetAttrs`, and
  `fusion.FontManager.GetFontList()` (a dict of 281 fonts on this machine).
- **Effects Library templates are `.setting` files.** The built-ins ship
  zipped in `C:\Program Files\Blackmagic Design\DaVinci Resolve\Fusion\Templates\Templates.drfx`
  (`Edit/Titles|Generators|Effects|Transitions/*.setting` plus
  `Fusion/Particles|Shaders|Lens Flares|Styled Text|.../*.setting`); user packs
  are `.drfx` bundles or loose files under
  `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Templates` and
  `%PROGRAMDATA%\...\Fusion\Templates`. The file stem is the name
  `InsertFusionTitleIntoTimeline` expects. GET `/fusion/templates` lists 2302
  here (titles 1760 incl. user packs, transitions 315, fusion 143, generators
  54, effects 30). Fusion cannot read zip members, so the gateway extracts to
  `%TEMP%\dollygrip\fusion_templates` before `bmd.readfile`.
- **A pasted template arrives as a `GroupOperator`** (e.g. `FadeOn`) plus its
  inner tools listed flat (`Text1`, `Merge1`, `Blur1`, `AnimCurves`...).
  Override the inner tools' inputs (`Text1.StyledText`) or the group's
  published inputs; the paste endpoint returns the new tool names so you know
  which to target.
- **Second hard freeze on a Fusion write (2026-09-24).** A template paste into
  a freshly loaded comp, while two other comps in the same timeline held a
  particle system, froze Resolve completely (UI dead, CPU flat, no recovery in
  three minutes; killed and relaunched, the unsaved throwaway project was
  lost). `_loaded` now calls `DisableBackgroundTasksForCurrentResolveSession`
  before opening a comp on the Fusion page, and a paste is bracketed by
  client timeouts. Keep heavy Fusion-page presets (particles, 3D) out of a
  timeline you are still scripting against, or paste them last.
- **`tool.GetInput(name)` on an input driven by a Calculation / AnimCurves
  (LUTLookup) / Expression modifier deadlocks Resolve.** Bisected after four
  hard freezes: after pasting the "Fade On" title template, `GetAttrs` on
  every input, `GetInput("StyledText")`, `GetInput("Size")` and the connected
  outputs all answered instantly; `GetInput("CharacterSpacing")` (fed by
  `Calculation1` <- `AnimCurves`) never returned and the UI died with it.
  Static inputs and BezierSpline-driven inputs evaluate fine. Every read path
  (`GET .../tools/{tool}`, `.../inputs`, `.../keyframes`, `DELETE keyframes`)
  now checks `GetConnectedOutput().GetTool().ID` first and reports
  `{"driven_by": "Calculation1", "driver": "Calculation"}` instead of a value.
  Never read a template's driven inputs through `/exec` either.
- **`_loaded` leaves Resolve on the Fusion page with the playhead on the
  item** and reports `loaded: {page_before, playhead_before, ...}` instead of
  switching back; the step-by-step bisect that never froze did no restore, and
  a page switch while Fusion is still evaluating a pasted comp is one more
  thing to go wrong. Switch back with `POST /system/page` when done.
- **Shared temp caches poison live runs.** The template extractor wrote bundle
  members to `%TEMP%/dollygrip/fusion_templates/<kind>/<member>`; a pytest run
  put its 117-byte fake JSON at the same path, `bmd.readfile` returned nil and
  `comp:Paste(nil)` answered `true` while pasting nothing - an afternoon of
  "paste lands nothing" that looked like a Fusion bug. The cache is now keyed
  by bundle path + size + mtime, tests point `DOLLYGRIP_TEMPLATE_CACHE` at a
  per-test folder, and the Lua raises when readfile returns nil.
- **Comp markers are lowercase and time-keyed.** `comp.GetMarkers()` ->
  `{time: {time, name, note, duration, customData}}`; `comp.SetMarker(frame,
  table)` adds or replaces, but the TABLE's `time` decides where the marker
  lands (a table with `time = 30` passed as `SetMarker(12, ...)` moves the
  marker to 30); `SetMarker(frame, None)` deletes; there is no colour. Both
  calls return None, so success is checked by reading the markers back.
- **`comp.GetNextKeyTime(t)` answers an out-of-range x.9999 value when there
  is no further key** (119.9999 on a 120-frame comp; 1000.9999 when asked from
  frame 100 on a 9-frame comp), never nil. Anything at or past
  `COMPN_RenderEnd` / `COMPN_GlobalEnd` is "no key" (`GET .../key-times`
  does this; a key sitting exactly on the last frame is therefore reported as
  not found).
- **Undoing after a paste undoes the paste** ("Paste: Multiple Tools" is one
  undo step); `SetInput` calls made through scripting do not appear on the
  undo stack. `comp.GetUndoStack()` / `GetRedoStack()` are lists of step names.
- **`fusion.GetRegSummary()`** is a dict of 1279 entries keyed by index with
  `REGS_ID`, `REGS_Name`, `REGI_ClassType` - no category. `GetRegList(CT_Modifier)`
  entries have no `GetID` method from scripting.
