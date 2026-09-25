"""Export the song's event timing (from the Whisper transcript, v1 logic) to
timing.json so the comp builder and the audio pass share one clock."""
import json
import os
import pathlib

ABC = pathlib.Path(os.environ.get("ABC_DIR", "D:/abc-song"))  # words.json from transcribe.py (see ../README.md)
OUT = pathlib.Path(__file__).with_name("timing.json")
SONG_END = 159.63
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ANCHORS = {"A": "apple", "B": "bear", "C": "cat", "D": "dog", "E": "elephant", "F": "fish", "G": "goat", "H": "hat", "I": "ice", "J": "jelly", "K": "kite", "L": "lion",
           "M": "moon", "N": "ne", "O": "orange", "P": "penguin", "Q": "queen", "R": "rabbit", "S": "sun", "T": "train", "U": "umbrella", "V": "violin", "W": "whale",
           "X": "xylophone", "Y": "yo", "Z": "zebra"}
CH = [(28.10, 37.58), (60.08, 70.00), (129.34, 139.14)]
BRIDGE = (70.6, 82.6)
FINALE = (139.6, 156.4)

segs = json.load(open(ABC / "words.json", encoding="utf-8"))
WORDS_T = [w for s in segs for w in s["words"]]
cursor = 0


def find(prefix, after=None, exact=False):
    global cursor
    start = cursor if after is None else after
    for i in range(start, len(WORDS_T)):
        tok = WORDS_T[i]["w"].lower().strip(".,!?-\"'")
        if (tok == prefix.lower()) if exact else tok.startswith(prefix.lower()):
            cursor = i + 1
            return WORDS_T[i]
    raise SystemExit(f"word {prefix!r} not found after {start}")


anchor = {L: find(ANCHORS[L])["s"] for L in LETTERS}
THANKS = find("thanks")["s"]
win = {}
for i, L in enumerate(LETTERS):
    t_in = anchor[L] - 1.05
    nxt = anchor[LETTERS[i + 1]] - 1.05 if i < 25 else 125.6
    for a, b in CH:
        if t_in < a < nxt:
            nxt = a - 0.3
    win[L] = (round(t_in, 2), round(nxt, 2))

chorus = []
for ci, (a, b) in enumerate(CH):
    letters = "ABCD" if ci < 2 else "ABCDEFG"
    idx = [i for i, w in enumerate(WORDS_T) if w["s"] >= a - 0.3][0]
    cursor = idx
    times = {ch: find(ch, exact=True)["s"] for ch in letters}
    cursor = idx
    entry = {"start": a, "end": b, "letters": times}
    if ci < 2:
        entry["clap"] = find("clap", after=idx)["s"]
        entry["round"] = find("round", after=idx)["s"]
    else:
        entry["hooray"] = find("hooray", after=idx)["s"]
    chorus.append(entry)

# caption script (official lyrics) timed by anchor words in song order
LINES = {
    "A": "A is for Apple, shiny and red,", "B": "B is for Bear who jumps out of bed.", "C": "C is for Cat with a soft little paw,", "D": "D is for Dog who says, \"Bow-wow-wow!\"",
    "E": "E is for Elephant, big and strong,", "F": "F is for Fish that swims along.", "G": "G is for Goat on top of a hill,", "H": "H is for Hat that fits you still.",
    "I": "I is for Ice cream, cold and sweet,", "J": "J is for Jelly, a wobbly treat.", "K": "K is for Kite flying up so high,", "L": "L is for Lion with a mighty cry.",
    "M": "M is for Moon shining at night,", "N": "N is for Nest where birds sit tight.", "O": "O is for Orange, juicy and round,", "P": "P is for Penguin waddling around.",
    "Q": "Q is for Queen with a sparkling crown,", "R": "R is for Rabbit hopping up and down.", "S": "S is for Sun shining warm and bright,", "T": "T is for Train going left and right.",
    "U": "U is for Umbrella when raindrops fall,", "V": "V is for Violin, music for all.", "W": "W is for Whale swimming in the sea,", "X": "X is for Xylophone, play with me!",
    "Y": "Y is for Yo-yo, down then high,", "Z": "Z is for Zebra passing by.",
}
CHORUS = [("a", True, "A-B-C-D, sing with me,"), ("learning", False, "Learning letters happily!"), ("clap", False, "Clap your hands and tap your toes,"), ("round", False, "Round and round the alphabet goes!")]
CHORUS_LAST = [("a", True, "A-B-C-D, sing with me,"), ("e", True, "E-F-G, so happily!"), ("h", True, "H to Z, now shout hooray,"), ("learned", False, "We learned our alphabet today!")]
EXTRA = [("26", False, "Twenty-six letters, now we know,"), ("fast", False, "Sing them fast or sing them slow!")]
script = []
for L in "ABCDEFGH":
    script.append((ANCHORS[L], False, LINES[L], 1.05))
script += [(a, e, t, 0.1) for a, e, t in CHORUS]
for L in "IJKLMNOP":
    script.append((ANCHORS[L], False, LINES[L], 1.05))
script += [(a, e, t, 0.1) for a, e, t in CHORUS]
for L in "QRSTUVWXYZ":
    script.append((ANCHORS[L], False, LINES[L], 1.05))
script += [(a, e, t, 0.1) for a, e, t in EXTRA]
script += [(a, e, t, 0.1) for a, e, t in CHORUS_LAST]
cursor = 0
caps = []
for anchor_word, exact, text, lead in script:
    w = find(anchor_word, exact=exact)
    caps.append({"t": round(max(0.0, w["s"] - lead), 3), "text": text})
for i, cap in enumerate(caps):
    t1 = caps[i + 1]["t"] - 0.05 if i + 1 < len(caps) else THANKS - 0.4
    cap["end"] = round(min(t1, cap["t"] + 6.0), 3)

# beat estimate from the chorus letter tokens (A-B-C-D spacing)
gaps = []
for e in chorus[:2]:
    ts = sorted(e["letters"].values())
    gaps += [b - a for a, b in zip(ts, ts[1:])]
beat = round(sum(gaps) / len(gaps), 4) if gaps else 0.5

out = {
    "song_end": SONG_END, "fps": 30, "letters": LETTERS, "anchor": anchor, "window": win, "chorus": chorus, "bridge": BRIDGE, "finale": FINALE,
    "thanks": THANKS, "captions": caps, "beat_estimate": beat, "words": {L: w for L, w in zip(LETTERS, ["Apple", "Bear", "Cat", "Dog", "Elephant", "Fish", "Goat", "Hat", "Ice cream", "Jelly", "Kite", "Lion", "Moon", "Nest", "Orange", "Penguin", "Queen", "Rabbit", "Sun", "Train", "Umbrella", "Violin", "Whale", "Xylophone", "Yo-yo", "Zebra"])},
}
OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
print("timing.json:", len(caps), "captions; beat", beat, "s; thanks", THANKS, "; A anchor", anchor["A"])
