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
