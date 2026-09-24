import json, sys
import httpx
B = "http://127.0.0.1:4747/api/v1"
c = httpx.Client(base_url=B, timeout=600)
WORDS = {
 "A": ("Apple", ["red apple close up", "apple fruit"]), "B": ("Bear", ["teddy bear", "brown bear"]), "C": ("Cat", ["cat paw", "kitten"]),
 "D": ("Dog", ["dog barking", "puppy"]), "E": ("Elephant", ["elephant walking", "elephant"]), "F": ("Fish", ["fish swimming aquarium", "goldfish"]),
 "G": ("Goat", ["goat on hill", "goat"]), "H": ("Hat", ["hat", "wearing hat"]), "I": ("Ice cream", ["ice cream cone", "ice cream"]),
 "J": ("Jelly", ["jelly dessert wobble", "gelatin dessert"]), "K": ("Kite", ["kite flying sky", "kite"]), "L": ("Lion", ["lion roar", "lion"]),
 "M": ("Moon", ["full moon night sky", "moon"]), "N": ("Nest", ["bird nest", "birds nest eggs"]), "O": ("Orange", ["orange fruit slices", "oranges"]),
 "P": ("Penguin", ["penguin walking", "penguins"]), "Q": ("Queen", ["crown jewels", "queen crown"]), "R": ("Rabbit", ["rabbit hopping", "bunny"]),
 "S": ("Sun", ["sun shining sky", "sunrise"]), "T": ("Train", ["train passing", "train"]), "U": ("Umbrella", ["umbrella rain", "colorful umbrella"]),
 "V": ("Violin", ["violin playing", "violin"]), "W": ("Whale", ["whale swimming ocean", "humpback whale"]), "X": ("Xylophone", ["xylophone", "playing xylophone toy"]),
 "Y": ("Yo-yo", ["yo-yo toy", "yoyo"]), "Z": ("Zebra", ["zebra walking", "zebra"]),
}
out = {}
for letter, (word, terms) in WORDS.items():
    chosen = None
    for provider in ("pexels", "pixabay"):
        for term in terms:
            r = c.post("/stock/search", json={"terms": [term], "provider": provider, "aspect": "landscape", "min_duration": 3, "per_page": 6}).json()
            mats = r.get("results", {}).get(term, []) if "results" in r else []
            mats = [m for m in mats if m["width"] >= 1280]
            if mats:
                chosen = mats[0]; chosen["term"] = term
                break
        if chosen:
            break
    if not chosen:
        print(letter, word, "-> NO CLIP", flush=True); out[letter] = {"word": word, "file": None}
        continue
    d = c.post("/stock/download", json={"materials": [chosen]}).json()
    m = d["materials"][0]
    out[letter] = {"word": word, "file": m["file"], "provider": m["provider"], "id": m["id"], "duration": m["duration"], "width": m["width"], "height": m["height"], "fps": m.get("fps"), "author": m["author"], "page_url": m["page_url"], "term": chosen["term"]}
    print(letter, word, "->", m["provider"], m["id"], f"{m['width']}x{m['height']}", m["duration"], "s", "fps", m.get("fps"), flush=True)
json.dump(out, open(sys.argv[1], "w"), indent=1)
print("done", sum(1 for v in out.values() if v["file"]), "/ 26")
