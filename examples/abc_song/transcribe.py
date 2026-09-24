import json, sys, time
from faster_whisper import WhisperModel
t0 = time.time()
model = WhisperModel("medium", device="cpu", compute_type="int8")
segments, info = model.transcribe(sys.argv[1], word_timestamps=True, language="en", beam_size=5, vad_filter=False,
                                  initial_prompt="A is for Apple, shiny and red. B is for Bear who jumps out of bed. C is for Cat. D is for Dog. A-B-C-D, sing with me, learning letters happily. X is for Xylophone. Y is for Yo-yo. Z is for Zebra.")
out = []
for seg in segments:
    words = [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2), "p": round(w.probability, 2)} for w in (seg.words or [])]
    out.append({"s": round(seg.start, 2), "e": round(seg.end, 2), "text": seg.text.strip(), "words": words})
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), indent=1)
print("segments:", len(out), "words:", sum(len(s["words"]) for s in out), "secs:", round(time.time() - t0, 1))
for s in out:
    print(f"{s['s']:7.2f}-{s['e']:7.2f}  {s['text']}")
