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
