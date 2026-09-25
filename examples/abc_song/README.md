# The ABC Song - real footage per letter, flash-card overlay, one Fusion comp

The alphabet song as an animated video: for every letter a real stock clip of
the object (Pexels/Pixabay through the gateway) plays full frame on V1, while a
Fusion comp on a transparent carrier on V2 draws the flash-card panel (big
letter that pops and wobbles, lowercase letter, the word sliding in), the lyric
caption over a dark band, rainbow chorus cards with the letters bouncing on
their sung tokens, a dancing grid on the instrumental bridge, the full alphabet
waving at the finale, and a "Thanks for watching!" card.

## Steps

1. `ffmpeg -i song.mp3 -ac 1 -ar 16000 song16k.wav` then
   `python transcribe.py song16k.wav words.json` (faster-whisper, word
   timestamps). The sung letters are often misheard, so the builder anchors on
   the OBJECT words and captions from the official lyrics.
2. `ffmpeg -f lavfi -i color=c=black:size=1920x1080:rate=30:duration=<song+0.1> -c:v libx264 -pix_fmt yuv420p carrier.mp4`
3. Provider keys in the repo `.env`; `dollygrip serve --media-dir <clips folder>`;
   `python fetch_clips.py clips.json` - one landscape clip per letter word, with
   `author` and `page_url` kept for the credits file.
4. `ABC_DIR=D:/abc-song python build.py` - places the 26 clips with
   `/stock/assemble`, builds the ~230-layer overlay comp (~1,500 API calls),
   renders 1080p.

## Design notes worth stealing

- **Transparent comp over footage**: the comp root is a Background with alpha 0
  and the final fade base is transparent too, so V1 shows through. One opaque
  black base at the end of the chain hid all 26 clips the first time.
- **Flash-card panel** = Background + `RectangleMask` connected to its
  `EffectMask` (Center, Width, Height, CornerRadius in 0..1 of the frame).
- **Chorus letters**: Whisper emits `A`, `-B`, `-C`, `-D,` as separate tokens;
  match them exactly, in order.
- **Captions from the lyrics, not the transcript**, timed by anchor words walked
  in song order with a per-line lead (about 1 s for letter lines: the letter is
  sung a second before its word).

## v2 - the maximum-motion cut (`v2/`)

Same footage and timing, but everything moves, and the audio is produced:

- `v2/timing.py` - exports `timing.json` (anchors, windows, chorus tokens, captions, beat)
  from `words.json` so the comp builder and the audio pass share one clock.
- `v2/build_v2.py` - Ken Burns on all 26 clips (a Transform in each clip's own comp),
  flash cards that slide in with overshoot (white frame + pastel panel), big letters with
  cycling squash-pop / spin-in / drop-and-bounce entrances, a bump on the sung word and a
  continuous wiggle, spinning lowercase, words that slide in with a tilt, six shared burst
  stars firing on every sung letter (all 41 bursts in one keyframe list per star), two swipe
  rectangles for 23 letter changes, an alphabet progress row, candy stripes, confetti rain,
  rising notes, hopping chorus letters, pulsing grids, orbiting stars on the thanks card.
  341 tools, ~2,600 API calls, about 7 minutes.
- `v2/make_sfx.py` - deterministic numpy sound effects at the timing.json events (pops,
  boings, whooshes, sparkles, swipes, claps, xylophone dings, tada arpeggios, confetti
  shimmer); the song is mastered with two-pass loudnorm (-14 LUFS, -1.5 dBTP), ducked
  under the two Windows-TTS voice lines; see `v2/AUDIO_NOTES.md`.
- `v2/finalize_v2.py` - stems onto A1-A3, render, frame grabs and level check.

Lessons that went into the gateway while building it (all in `docs/GOTCHAS.md`): point
inputs need an XYPath (the keyframe endpoint does it now), translucent Backgrounds must
be premultiplied, `time` in expressions is in frames, frame exports need the Color page
and a settle after moving the playhead, and never read a modifier-driven input.
