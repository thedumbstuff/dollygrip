# Count With Me! - a music video for a real song, one Fusion comp

`build.py` turns a kids' counting song into a finished 1080p music video through
DollyGrip: word-timed number cards, a chorus grid that builds on the beat,
full-screen flashes for the big count, an outro star burst, and lyric captions.

## How it works

1. **Word timings.** `transcribe.py` runs faster-whisper (medium, CPU, word
   timestamps) on a 16 kHz mono WAV of the song and writes `words.json`.
   Every number word gets a timestamp; the builder walks the transcript in
   lyric order to find each card's cue words.
2. **A comp the length of the song.** Resolve's generators/titles are always
   5 s and cannot be trimmed via the API, so the builder appends a black
   `carrier.mp4` of the song's length on V1, the song on A1, adds a Fusion
   comp to the carrier (`POST /fusion/items/{id}/comps`) and builds the whole
   show inside it - comp time == timeline frame.
3. **Layers.** Every element is a Background or Text+ merged over the chain;
   visibility is `Merge.Blend` keyframes (`on(t_in, t_out)`), motion is
   `Size`/`AngleZ` keyframes and `Center` expressions (`Point(x, y + a*sin(time/p))`).
   ~160 layers, ~1000 API calls, about two minutes to build.
4. **QA before rendering.** `POST /color/export-frame` at chosen timecodes
   gives a still in about a second - look at them, then render.

## Run

```bash
ffmpeg -i song.mp3 -ac 1 -ar 16000 song16k.wav
python transcribe.py song16k.wav words.json          # needs faster-whisper
ffmpeg -f lavfi -i color=c=black:size=1920x1080:rate=30:duration=<song seconds + 0.1> -c:v libx264 -pix_fmt yuv420p carrier.mp4
dollygrip serve
CWM_SONG_DIR=D:/count-with-me CWM_OUT_DIR=D:/count-with-me/out python build.py
```

Adapt `ACTIONS`, `PASTELS` and the section logic to your own song; the
alignment helpers (`find`, `sentences`) and the `Show` layer builder are
song-agnostic.

## Traps met on the way (all in docs/GOTCHAS.md)

- `Background.Type` is a named multi-button (`"Corner"`), not an int.
- A Merge with no Background outputs nothing - the first layer is the root.
- Attaching a spline leaves a stray key; `SetKeyFrames(replace=True)` does not
  remove it. The gateway's keyframe endpoint handles this now.
- Scan transcripts in lyric order and reset the cursor at section boundaries,
  or the chorus's "six" steals verse 2's card.
