# Recipe library

Four production pipelines, each one JSON file you can run with `dollygrip run`
(no server needed) or POST to `/api/v1/recipes/run`. Every recipe has:

- `description` - what it builds and what you supply,
- `inputs` - the values you fill in (paths, names, ranges), referenced by the
  steps as `{{ inputs.<key> }}`,
- `input_notes` - hints for the trickier inputs,
- `steps` - operations by name (the operationIds in `/docs`, the same names as
  the MCP tools); later steps read earlier results as `{{ steps.<name>.<path> }}`.

Edit `inputs` in the file, or override single values on the command line with
`--input key=value` (the value is parsed as JSON when it parses, so numbers and
lists work: `--input source_in=54000`, `--input 'terms=["cat","dog"]'`).

Always dry-run first. It works offline, with Resolve closed: it checks every
operation name, every argument name and the required arguments against the
gateway's own OpenAPI catalogue, fills in your inputs, and shows each
step-to-step reference as a placeholder such as `<steps.render.job_id>`.

```bash
uv run dollygrip run recipes/vertical_reel.json --dry-run
uv run dollygrip run recipes/vertical_reel.json            # for real: Resolve Studio running, a project open
```

## The recipes

| Recipe | Builds | Inputs you fill |
|---|---|---|
| [`vertical_reel.json`](vertical_reel.json) | 1080x1920 30 fps phone reel: clips end to end, Text+ title card in the upper safe zone, H.264 render | `bin`, `clip_paths`, `clips` (clip names in cut order), `timeline_name`, `title`, `out_dir` |
| [`podcast_clip.json`](podcast_clip.json) | 1080p highlight cut from one long recording: one in/out range, Text+ lower third with the guest's name, auto captions burned in, H.264 render | `bin`, `recording_path`, `recording_name`, `source_in`, `source_out` (source-fps frames, exclusive end), `guest_name`, `guest_title`, `caption_language`, `timeline_name`, `out_dir` |
| [`dailies_burnin.json`](dailies_burnin.json) | Dailies: import card folders into a dated bin, clips end to end, project data burn-in preset, one review render | `bin`, `media_paths`, `clips`, `timeline_name`, `width`, `height`, `fps`, `burn_in_preset`, `render_format`, `render_codec`, `out_dir` |
| [`music_video_overlay.json`](music_video_overlay.json) | The ABC pattern: stock b-roll on V1 against the song on A1, a black carrier on V2, one Fusion comp on the carrier with a title and a caption over transparency, render | `timeline_name`, `song_path`, `terms`, `provider`, `carrier_path`, `carrier_name`, `song_frames`, `title`, `caption`, `out_dir` |

Run commands:

```bash
uv run dollygrip run recipes/vertical_reel.json --dry-run
uv run dollygrip run recipes/podcast_clip.json --dry-run
uv run dollygrip run recipes/dailies_burnin.json --dry-run
uv run dollygrip run recipes/music_video_overlay.json --dry-run
```

Over HTTP, send the file as the request body (add `"dry_run": true` to plan only):

```bash
curl -X POST localhost:4747/api/v1/recipes/run -H 'content-type: application/json' -d @recipes/podcast_clip.json
```

## Before a real run

- **Clip names.** `append_items` finds clips by name in the current bin, which
  is the file name after `import_media`. List them in `clips` in cut order.
- **Frames are source frames.** `start_frame` / `end_frame` count in the clip's
  own frame rate, and `end_frame` is exclusive (see `docs/GOTCHAS.md`).
- **Stock keys.** `music_video_overlay` calls `stock_b_roll`, which needs a
  Pexels, Pixabay or Coverr key in the gateway's `.env`.
- **Burn-in preset.** `dailies_burnin` loads a preset that must already exist
  (`GET /render/burn-in/presets`).
- **Codec keys.** Codec names are Resolve's keys. `GET /render/formats` and
  `GET /render/formats/{fmt}/codecs` list what your install renders.
- **Studio features.** `auto_subtitles` (podcast captions) needs Resolve Studio.

## Gaps found while building these

These recipes use only operations that exist today. Where the API falls short,
the recipe was simplified rather than calling something that does not exist:

- **No subtitle-file (SRT) import.** The timelines router has `auto_subtitles`
  (speech to captions) but nothing that imports an SRT onto a subtitle track,
  and `import_timeline` takes AAF/EDL/XML/FCPXML/DRT/ADL/OTIO only. So
  `podcast_clip` generates captions with `auto_subtitles` and puts the guest
  name on a Text+ lower third instead of burning in an existing SRT.
- **No "append every clip in a bin".** `append_items` needs explicit clip
  names, and a template cannot turn `import_media`'s result list into append
  items. `vertical_reel` and `dailies_burnin` therefore take a `clips` list.
- **Subtitle burn-in render keys are not live-verified here.** `podcast_clip`
  passes `ExportSubtitle: true` and `SubtitleFormat: "BurnIn"` to
  `SetRenderSettings` (the keys Resolve's scripting README documents). The
  dry run checks the operation, not Resolve's acceptance of those keys.
- **Carrier length is an input.** There is no operation that makes a black
  clip of a given length, so `music_video_overlay` takes a black video file
  and trims it to `song_frames`.
