# Video craft guide - read this before building any video

DollyGrip gives an agent the whole Resolve toolbox. This page is the taste that
goes with it: what a finished video needs, how to get each part with the
endpoints that exist, and what to check before calling it done. Follow it and
the result looks designed rather than generated.

## 0. Before touching Resolve

1. **Write the beat sheet first.** One line per shot/card: what is on screen,
   what is said, how long. Never size the voice to the picture - size the
   picture to the voice.
2. **Voice first, then picture.** Generate/import the voiceover, place it on
   A1, read its length back (`stock_b_roll` does this; or append it and read
   `duration` from `list_items`). Every visual duration derives from it.
3. **Pick the format up front**: 9:16 1080x1920 for Shorts/Reels/TikTok,
   16:9 1920x1080 for YouTube, 1:1 1080x1080 for feeds. Create the timeline
   with `start_timecode: "00:00:00:00"` so record frames are 0-based.
4. **Do the timing math in frames** (`convert_timecode`). Cards tile perfectly
   when their length equals Resolve's default title length: 150 frames at
   30 fps (5 s). Shots should be 3-5 s; a hook card 2-3 s; an outro 4-5 s.

## 1. The ingredients checklist

| Ingredient | Rule | How, with DollyGrip |
|---|---|---|
| **Hook** | First 2 s state the promise ("Let's count to 10!") | intro title card |
| **Structure** | intro -> 3-10 beats -> recap -> call to action | one card/shot per beat |
| **Typography** | ONE display font + ONE body font. Display for the big element, body for words/captions. Check glyph coverage: symbols (stars, arrows, emoji) go in their own Text+ using `Segoe UI Symbol` / `Segoe UI Emoji` - fonts without a glyph draw boxes, not fallbacks | `set_tool_inputs` Font/Style/Size |
| **Hierarchy** | Big thing 0.35-0.5 size, word 0.08-0.1, caption 0.05-0.06; never more than three text sizes on screen | `Size` input |
| **Safe margins** | Keep text inside 0.08..0.92 of the frame on both axes; on 9:16 keep the bottom 0.2 free (platform UI) and the top 0.12 free | `Center` in 0..1 |
| **Palette** | One background family + one ink + one accent. Kids: pastels (sat 0.4-0.6, light 0.8-0.9) with dark navy ink and a gold accent. Corporate: deep background, white ink, one brand accent | Background tool `TopLeftRed/Green/Blue` |
| **Contrast** | Ink vs background luminance ratio >= 4.5:1 for body text; white on pastel is fine only for very large display text | choose ink per background |
| **Motion** | Every element enters (pop 8-12 frames or slide) and holds; nothing jumps in on frame 0 of a cut. One motion idea per card. Give static elements a slow breathing bob so nothing looks like a slide | `set_tool_keyframes` on `Size`, `AngleZ`, `Blend`; `set_tool_expression` on `Center` |
| **Transitions** | Cards: fade in 8 frames, fade out 8 frames via the last Merge's `Blend` (0 -> 1 -> 0). Footage: a cut is fine at 3-5 s pace; avoid dissolves between unrelated stock shots | keyframes on `Merge.Blend` |
| **B-roll rhythm** | 3-5 s per shot, follow the script order, never repeat a source before every source has appeared, trim the last shot to the voice end | `stock_plan` does all of this |
| **Framing** | Stock into a vertical frame: `fit: fill` (cover) - letterboxing reads as a mistake | `stock_assemble` fit |
| **Music bed** | Always. -18 to -22 dB under voice, fade in 1 s, fade out 2-3 s, trimmed to the timeline length, loop if short | pre-mix with ffmpeg (below), append on A2 |
| **Sound design** | A soft pop/whoosh on each card entrance and a chime on the outro sells the motion | append SFX at the card record frames on A3 |
| **Voice** | Human-paced: TTS at -1..-2 rate, 0.3-0.5 s of silence before each line, sentence per card | offline SAPI / any TTS -> WAV |
| **Captions** | Yes for anything spoken: `auto_subtitles` (Studio) or one Text+ per line timed to the voice; 42 chars/line, bottom-safe position | `auto_subtitles` / `insert_generator` + `text_plus` |
| **Loudness** | Voice + music mixed to about -14 LUFS integrated, true peak <= -1 dBTP | ffmpeg `loudnorm` on the stems before import |
| **Outro** | Recap + call to action + 1-2 s hold; end on the accent colour | outro title card |
| **Attribution** | Keep the `attribution` list the stock plan returns; put it in the description | `stock_plan` response |

## 2. Recipes for the parts the API cannot do directly

**Fade a Fusion-title card in and out** (transitions are not exposed for
clips; inside a comp they are just keyframes). `Merge.Blend` fades only the
foreground, so end the chain with a black `Background` + a final `Merge`
(`M4`) and fade THAT. With the card 150 frames long:

```json
{"op": "set_tool_keyframes", "args": {"item_id": "...", "comp": "1", "tool": "M4", "input": "Blend",
  "keyframes": [{"frame": 0, "value": 0.0}, {"frame": 8, "value": 1.0}, {"frame": 141, "value": 1.0}, {"frame": 149, "value": 0.0}]}}
```

**A card that carries its own background** (no separate colour clip):
insert `fusion_title` "Text+", then `add_tool` Background `Card` (colour in
`TopLeftRed/Green/Blue`, `UseFrameFormatSettings: 1`), Merge `M1`
(Background <- Card, Foreground <- the Text+), further Text+ tools for word,
symbols, captions merged in turn, and `connect_tool_input` on `MediaOut1`
`Input` from the last Merge. `examples/counting_cards.py` is the worked
example.

**Start from an Effects Library template instead of raw tools**: you do not
have to build every title from Background/Text+/Merge. `fusion_templates`
(GET `/fusion/templates`, filter with `kind` and `contains`) lists every
title, generator, effect and transition Resolve ships plus installed packs.
Paste one into a comp and override its text in the same call:

```json
{"op": "paste_settings", "args": {"item_id": "...", "comp": "1",
  "template": "titles/Fade On", "inputs": {"Text1": {"StyledText": "Count with me"}}}}
```

The response lists the tools that appeared (a group operator plus its inner
tools such as `Text1`, `Merge1`); read them with `list_tool_inputs` to find
what else to override (font, colour, timing). Fusion-page presets
(`fusion/Particles/Snow`, lens flares, shaders, styled text) paste the same
way and make good overlays merged over a card. Call `fusion_fonts` (GET
`/fusion/fonts`) before choosing a typeface and check it carries your
glyphs. The first paste into a comp takes a few seconds: the gateway has to
open the comp on the Fusion page once (it leaves you on the Fusion page with the playhead on that item; switch back with `set_page` when you are done pasting, not between pastes).

**Music bed and loudness** (audio levels are not scriptable; prepare the
stems on disk, then import):

```bash
# bed: trim to the timeline length, -20 dB, 1 s fade in, 3 s fade out
ffmpeg -y -i music.mp3 -t 60.2 -af "volume=-20dB,afade=t=in:d=1,afade=t=out:st=57.2:d=3" bed.wav
# voice: broadcast loudness, gentle limiter
ffmpeg -y -i voice.wav -af "loudnorm=I=-16:TP=-1.5:LRA=7" voice_norm.wav
```
then MEASURE them (`ffmpeg -i bed.wav -af volumedetect -f null -`: bed mean around -30 dB, voice around -20 dB, pops peaking around -10 dB) and only then `import_media` + `append_items` (`media_type: audio`) on A1/A2. A stem that is too quiet renders silently and nothing warns you.

**Silence padding for TTS lines**: `ffmpeg -i line.wav -af "adelay=400|400" line_padded.wav`
(0.4 s lead-in so the visual lands first).

**Captions when the speech model is not installed** (`auto_subtitles` answers
422 "Studio + speech model required"): you already know every line and when
its voice starts, so burn them in - one `Caption` Text+ per card merged before
the final fade Merge, `Blend` keyed 0 until the voice frame then 1 over 8
frames - and write an `.srt` sidecar from the same timings for the upload.
Body font, 0.045 size (16:9) / 0.06 (9:16), white on saturated backgrounds,
dark ink on pastels.

**A 9:16 version from a 16:9 timeline**: `duplicate_timeline`, then
`patch_timeline_settings` with 1080x1920 - Fusion tools created with
`UseFrameFormatSettings: 1` follow the new frame, and `Center` is in 0..1 so
the layout mostly survives. Then re-flow: big element up (~0.60), word ~0.42,
symbols ~0.34, caption ~0.25, nothing below 0.20. Render 1080x1920.

**A music video timed to a song** (lyric videos, kids' songs, anything
where visuals must land on sung words): get word timestamps first
(faster-whisper with `word_timestamps=True` and the lyrics as
`initial_prompt`), then build the WHOLE show as ONE Fusion comp: append a
black carrier clip the length of the song on V1 and the song on A1, add a
comp to the carrier (`add_comp`), and inside it merge every element over a
chain - visibility = `Merge.Blend` keys `(t_in, 0) (t_in+f, 1) (t_out-f, 1)
(t_out, 0)`, pops = `Size` keys, wobble = `AngleZ` keys, breathing =
`Center` expression `Point(x, y + 0.012*sin(time/5))`. Walk the transcript in
lyric order with a cursor and reset it at section boundaries. Preview with
`export_current_frame` at cue times before rendering (about a second per
still). Worked example: `examples/count_with_me/`.

**Stock explainer, one call**: `stock_b_roll` with `terms` in script order,
`voiceover_path`, `aspect`, `max_clip_duration: 4`, `fit: fill`; then
`auto_subtitles`; then `add_job`. See `examples/recipe_stock_explainer.json`.

## 3. Platform presets

| Target | Timeline | Render |
|---|---|---|
| YouTube | 1920x1080 30 fps (or 24) | preset "YouTube - 1080p" or mp4/H264, `FormatWidth 1920, FormatHeight 1080` |
| Shorts / Reels / TikTok | 1080x1920 30 fps | mp4/H264 1080x1920; keep bottom 20% free of text |
| Square feed | 1080x1080 30 fps | mp4/H264 1080x1080 |
| Master | as shot | QuickTime ProRes 422 HQ preset |

## 4. QA before you say "done"

1. Before heavy Fusion edits: `disable_background_tasks`, and give your HTTP
   client a timeout - a frozen Resolve must not freeze you.
2. `list_items`: every card/shot starts where planned, no gaps, no item pushed
   or trimmed (`relocate`/`ripple_insert` responses say `placed_as_requested`).
   For animation, read a value back mid-way (`set_tool_keyframes` returns
   `values_at_keys`; `exec` can sample `GetInput(name, frame)`) - a keyframe
   that did not take renders as a static frame.
3. Render with `add_job` + `wait_for_job` (or stream `job_events`), then probe
   the file: duration matches the timeline, resolution and fps match the spec.
4. Extract frames at the start, middle and end (`ffmpeg -ss T -frames:v 1`)
   and LOOK at them: glyph boxes, text over the safe margin, wrong colours,
   an element missing its entrance.
5. Measure the mix (`volumedetect` on the render, and on a window between voice lines to hear the bed alone); then listen once: voice over bed, no clipping, music fades out.
6. **Deliver upload metadata with every video** - always, unprompted: an
   SEO title (keywords first, under 100 characters, the audience and the
   promise in it), a description (hook line, what the viewer gets, a
   chapters list with `m:ss` timestamps from your own cue times, a call to
   action, 5-8 hashtags), and 10-16 tags. Write it next to the render as
   `<name>.metadata.md` and paste it in the reply. For 9:16 variants give a
   short Shorts/Reels title with `#shorts`.
7. Save the project (`save_project`) and report the file path and the project
   name so a human can open it in Resolve and adjust.

## 5. Things Resolve's API does not expose (say so, do not fake them)

Edit-page transitions and clip opacity/volume keyframes, Fairlight mixing,
node-based colour grading, reading a grade back. Work around with Fusion
comps (fades, motion), ffmpeg-prepared audio stems, DRX/LUT application
(`apply_drx_clip`, `set_node_lut_clip`) and CDL. Tell the user when a request
lands in this list and offer the workaround.


## Motion vocabulary that reads as animation (learned on the ABC v2 build)

- Points move through `set_tool_keyframes` with `[x, y]` values: the gateway
  attaches an XYPath for you. Give every entrance a settle: overshoot,
  undershoot, rest (e.g. Size 0.02 -> 1.28x -> 0.88x -> 1.06x -> 1.0 over 18
  frames); a plain linear pop looks mechanical to a child.
- Continuous life comes from expressions, in SECONDS: `sin(6.2832*(time/30)/P)`
  for a bob or wiggle, `((time/30)/P + offset) % 1.3 - 0.15` for a looping
  drift (confetti, notes, candy stripes), `abs(sin(...))` for hops.
- Reuse tools across many events: six burst stars with all 40 bursts in one
  keyframe list each, two swipe rectangles for 23 cuts (hold off-screen with a
  key one frame before each cut).
- Translucent shapes: premultiply the colour; caption bands: a soft-edged
  masked rectangle, never a full-frame vertical gradient.
- QA with `export_current_frame` at a dozen moments before rendering; it now
  takes a `timecode` and renders from the Color page.


## Speed changes and dissolves (composites, 2026-09-25)

- `retime_item` (`POST /timelines/current/items/{id}/retime`): `speed` 0.5 / 2 / -1,
  `mode: fit` keeps the item's length (slow motion shows the first part of the trim,
  fast motion runs into the clip's tail and holds its last frame), `mode: ripple`
  changes the length to duration / |speed| and pushes or pulls everything after it.
  Linked audio is not retimed - mute it or replace it.
- `dissolve_item` (`POST /timelines/current/items/{id}/dissolve`): a cross dissolve
  into the next item, built as an overlap one track up. It needs handles: head
  handles on the incoming clip (before the cut) or tail handles on the outgoing one
  (after the cut); stock b-roll placed with `source_in: 0` has no head handle, so
  either trim the b-roll in by the dissolve length first or use `align: after_cut`.
  Nothing on the original track moves, so captions and markers stay put.
- Prove both on stills (`export_current_frame` at the cut and mid-transition):
  the retime endpoint solves the TimeSpeed delay exactly, but a wrong-speed
  result is invisible without checking a frame.

- Stock b-roll from a script: `stock_keywords` (or `b-roll` with `script`) turns the voiceover text into 1-3 search terms per sentence; check the terms it picked before assembling, and override any that are too generic.
