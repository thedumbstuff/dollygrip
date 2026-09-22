import json, sys, time
from faster_whisper import WhisperModel
t0 = time.time()
model = WhisperModel("medium", device="cpu", compute_type="int8")
segments, info = model.transcribe(sys.argv[1], word_timestamps=True, language="en", beam_size=5, vad_filter=False,
                                  initial_prompt="Count with me! One, one, touch the sun. Two, two, tap your shoe. Three, four, five, six, seven, eight, nine, ten.")
out = []
for seg in segments:
    words = [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2), "p": round(w.probability, 2)} for w in (seg.words or [])]
    out.append({"s": round(seg.start, 2), "e": round(seg.end, 2), "text": seg.text.strip(), "words": words})
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), indent=1)
print("segments:", len(out), "words:", sum(len(s["words"]) for s in out), "secs:", round(time.time() - t0, 1))
for s in out:
    print(f"{s['s']:7.2f}-{s['e']:7.2f}  {s['text']}")
