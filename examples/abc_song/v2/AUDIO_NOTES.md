# Audio pass notes (v2)

Produced by `make_sfx.py` + ffmpeg loudnorm; the song was then ducked 4-5 dB under the two voice lines and the voice lifted 7 dB (see README).

# ABC Song v2 - audio stems report

All stems are in `audio/`. Each is 48 kHz, stereo, and exactly 159.630 s (7,662,240 samples), so they line up at frame 0.

| File | Format | Duration | Mean vol | Max vol | Integrated | True peak |
|---|---|---|---|---|---|---|
| song_master.wav | PCM 24-bit | 159.630 s | -16.5 dB | -1.5 dB | -13.9 LUFS | -1.5 dBTP |
| sfx.wav | PCM 16-bit | 159.630 s | -39.5 dB | -16.0 dB | -32.1 LUFS | -16.0 dBTP |
| voice.wav | PCM 24-bit | 159.630 s | -42.9 dB | -14.0 dB | -26.9 LUFS | -14.0 dBTP |
| preview_mix.wav | PCM 24-bit | 159.630 s | -16.5 dB | -1.1 dB | -13.9 LUFS | -1.1 dBTP |

The preview mix has a loudness range of 2.7 LU.

## Deviations from the spec

1. **SFX and voice levels were trimmed.** At spec levels (SFX peak -10 dBFS, voice peak -6 dBFS) the preview mix hit +0.1 dBTP. The intro line lands on the loud instrumental intro at 4.34 s, and the chorus dings stack on the song near 132.4 s. The song master already sits at -1.5 dBTP, so any additive stem pushes the peak up. As the spec says, the song was left alone and the other stems were lowered. SFX got -6 dB, with a peak of -16 dBFS set by `STEM_TRIM_DB` in make_sfx.py. Voice got -8 dB, with a peak of -14 dBFS. The mix then measures -1.1 dBTP. The trims tested were SFX -4 / voice -7 at -1.0 dBTP, SFX -6 / voice -8 at -1.1, and SFX -8 / voice -9 at -1.2.
2. **The outro voice line was moved earlier.** Zira's outro is 6.30 s long, with 5.35 s of speech, at Rate -1. Starting at thanks + 0.4 = 157.26 s would run to about 163.6 s, past song_end. The "thanks" time of 156.86 s comes from a Whisper token with confidence 0.01 ("Thanks for watching!"), so it is almost certainly a hallucination over the instrumental tail. The song goes quiet at about 158 s. The outro is placed at 153.75 s, so the speech plays from 153.87 s to 159.22 s over the final instrumental bars. The intro stays at 1.0 s with Rate -1, and its speech plays from 1.12 s to 4.62 s.
3. **Loudnorm ran in dynamic mode.** Pass 2 used `linear=true`, but a linear gain of -2.1 dB would have left the true peak near -0.6 dBTP. Loudnorm therefore fell back to dynamic mode. Output LRA is 2.7 LU against 3.6 LU at input, which is a mild reduction and not over-compression.
4. **The Z window gets a swipe.** Only H (ending 27.80 s into a chorus at 28.10 s) and P (ending 59.78 s into a chorus at 60.08 s) meet the rule "out within 0.4 s before a chorus start." Z ends at 125.6 s, which is 3.7 s before the final chorus, so Z keeps its swipe. Z would be dropped by adding its letter to the skip test in make_sfx.py.
5. **The confetti level scales with the trim.** Confetti was placed at -30 dBFS absolute, then the stem trim of -6 dB applied to everything, so it now sits at -36 dBFS.
6. **The voice is quiet against the song.** A -14 dBFS voice peak over a song with a -16.5 dB mean is soft, especially over the busy intro. For clearer speech, duck the song by 4 to 6 dB under the two voice regions in the editor, then raise the voice by the same amount.

## Event counts (sfx.wav)

| Category | Count | Placement |
|---|---|---|
| pop | 26 | each window in, pitch x(1 + 0.1 sin(2.399 i)) |
| boing | 26 | window in + 0.35 s |
| whoosh | 26 | anchor - 0.15 s |
| sparkle | 26 | anchor |
| swipe | 24 | window out, H and P skipped |
| clap | 8 | 2 choruses x 4: clap + k*2*beat, beat = 0.2967 s |
| chorus_ding | 15 | chorus letters, 4 + 4 + 7 |
| tada_arpeggio | 3 | round 35.00 s, round 67.34 s, hooray 135.56 s |
| confetti | 107 | Poisson about 6 per second, 139.6 s to 156.86 s |
| big_tada | 1 | thanks 156.86 s, arpeggio one octave down |
| big_tada_cymbal | 1 | thanks 156.86 s, 5 kHz bandpassed noise swell |

The generator uses numpy with seed 20260925 plus the stdlib wave module. Panning is constant-power, drawn uniformly from -0.3 to 0.3 per event. The arpeggios and cymbal are centred. Every event has short raised-cosine edges, so nothing starts or ends with a step. Rerun it like this:

```
C:\Shwetank\Work\Workspace\Python\python\Sunlo\.venv\Scripts\python.exe make_sfx.py
```

## Loudnorm summaries

Pass 1 was the measurement. It is saved in audio/loudnorm_pass1.json:

```
input_i -11.87  input_tp 1.48  input_lra 3.60  input_thresh -21.94
output_i -13.51 output_tp -1.50 output_lra 2.70 output_thresh -23.54
normalization_type dynamic  target_offset -0.49
```

Pass 2 was the apply step. It is saved in audio/loudnorm_pass2.json:

```
input_i -11.87  input_tp 1.48  input_lra 3.60  input_thresh -21.94
output_i -13.95 output_tp -1.50 output_lra 2.70 output_thresh -23.98
normalization_type dynamic  target_offset -0.05
```

## Exact commands

`FF` is `C:/Shwetank/Work/Workspace/softwares/ffmpeg-2025-01-20-git-504df09c34-essentials_build/bin/ffmpeg.exe`. The working directory is `abc2`.

Song, pass 1:

```
"$FF" -hide_banner -nostats -i ../abc/song.mp3 -af "equalizer=f=3000:t=q:w=1:g=1.5,highshelf=f=10000:g=1,loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json" -f null -
```

Song, pass 2, with sample-exact pad and trim:

```
"$FF" -hide_banner -nostats -y -i ../abc/song.mp3 -af "equalizer=f=3000:t=q:w=1:g=1.5,highshelf=f=10000:g=1,loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=-11.87:measured_TP=1.48:measured_LRA=3.60:measured_thresh=-21.94:offset=-0.49:linear=true:print_format=json,aresample=48000,afade=t=in:st=0:d=0.4,afade=t=out:st=157.13:d=2.5,apad=whole_len=7662240,atrim=end_sample=7662240" -ar 48000 -ac 2 -c:a pcm_s24le audio/song_master.wav
```

TTS was generated in PowerShell with System.Speech, voice "Microsoft Zira Desktop". The output is 22.05 kHz mono.

```
$s.SelectVoice("Microsoft Zira Desktop"); $s.Rate = -1
$s.SetOutputToWaveFile("audio\tts\intro_r-1.wav"); $s.Speak("Let's sing the ABC song! Are you ready?")
$s.SetOutputToWaveFile("audio\tts\outro_r-1.wav"); $s.Speak("Great job! You know your ABCs! See you next time!")
```

Voice placement, resampling to 48 kHz stereo, and EQ. This was run in `audio/`:

```
"$FF" -y -i tts/intro_r-1.wav -i tts/outro_r-1.wav -filter_complex "[0:a]aresample=48000,aformat=channel_layouts=stereo,adelay=1000:all=1[a];[1:a]aresample=48000,aformat=channel_layouts=stereo,adelay=153750:all=1[b];[a][b]amix=inputs=2:normalize=0:duration=longest,equalizer=f=200:t=q:w=1:g=1,apad=whole_dur=159.63,atrim=end=159.63[v]" -map "[v]" -ar 48000 -ac 2 -c:a pcm_s24le voice_raw.wav
```

Voice peak normalisation to -6.000 dBFS, which astats measured at -5.970 before the gain:

```
"$FF" -y -i voice_raw.wav -af "volume=-0.029678dB" -c:a pcm_s24le voice_m6.wav
```

Voice mix trim of -8 dB, for a final peak of -14 dBFS:

```
"$FF" -y -i voice_m6.wav -af "volume=-8dB" -c:a pcm_s24le voice.wav
```

Preview mix:

```
"$FF" -y -i song_master.wav -i sfx.wav -i voice.wav -filter_complex "[0:a][1:a][2:a]amix=inputs=3:normalize=0:duration=first[m]" -map "[m]" -ar 48000 -ac 2 -c:a pcm_s24le preview_mix.wav
```

Verification was run for each file:

```
ffprobe -v error -show_entries stream=sample_rate,channels,sample_fmt,bits_per_sample:format=duration -of compact=p=0:nk=1 <file>.wav
"$FF" -i <file>.wav -af "volumedetect,ebur128=peak=true" -f null -
```
