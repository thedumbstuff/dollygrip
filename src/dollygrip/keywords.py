"""Script -> stock-search keywords: the step before `/stock/b-roll`.

Two tiers:

1. **heuristic** (default, no network): split the script into segments
   (sentences / lines), drop stop words, common verbs and filler, keep runs
   of content words as noun phrases ("teddy bear", "little girl"), rank them
   (multi-word phrases and proper nouns first) and keep 1-3 per segment plus a
   global list in script order.
2. **LLM** (optional): `DOLLYGRIP_KEYWORDS_PROVIDER` = `anthropic` | `openai` |
   `deepseek` with the matching `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` /
   `DEEPSEEK_API_KEY`. Plain httpx POSTs, no SDK. `DOLLYGRIP_KEYWORDS_MODEL`
   overrides the model. ANY failure (no key, HTTP error, unparseable reply)
   falls back to the heuristic and reports `provider_used: "heuristic"` plus
   the reason in `fallback_reason`.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Mapping, Optional

PROVIDERS = ("anthropic", "openai", "deepseek")
DEFAULT_MODELS = {"anthropic": "claude-sonnet-5", "openai": "gpt-4o-mini", "deepseek": "deepseek-chat"}
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
ENDPOINTS = {
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai": "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/chat/completions",
}

_STOP = set(
    """
a an the and or but nor so yet for of to in on at by with from into onto over under about above below
between through during before after up down out off than then there here this that these those
i me my mine we us our ours you your yours he him his she her hers it its they them their theirs
who whom whose which what when where why how all any both each every few more most other some such
no not only own same too very just also again once ever never always often sometimes still even
is am are was were be been being have has had having do does did doing done can could will would
shall should may might must let lets let's it's that's there's here's what's i'm you're we're they're
don't doesn't didn't can't won't isn't aren't wasn't weren't hasn't haven't hadn't
one two three four five six seven eight nine ten first second last next new old
lot lots thing things something anything everything nothing someone everyone anyone way ways
really quite rather much many little bit kind sort like well yes okay ok oh hey hi hello
today tomorrow yesterday now soon later day days time times year years
away back around together along ahead inside outside maybe please
""".split()
)
# "little" is a stop word only on its own; keep it inside phrases like "little girl"
_KEEP_INSIDE_PHRASE = {"little", "old", "new", "first"}

_VERBS_BASE = """
be have do say go get make know think take see come want look use find give tell work call try ask need feel
become leave put mean keep let begin seem help talk turn start show hear play run move like live believe hold
bring happen write provide sit stand lose pay meet include continue set learn change lead understand watch follow
stop create speak read allow add spend grow open walk win offer remember love consider appear buy wait serve die
send expect build stay fall cut reach kill remain suggest raise pass sell require report decide pull eat drink
hug hugs jump climb swim fly sing dance laugh cry smile sleep wake draw paint count share clean wash cook bake
pick throw catch kick carry push ride drive visit explore discover imagine wonder hope wish dream fix hide seek
keeps shows makes gives takes goes comes looks helps says gets finds tells knows thinks wants needs lives loves
shine glow sparkle float roar bark swing splash chase fetch blow melt shake wave nod clap giggle whisper shout
""".split()


def _verb_forms(base: List[str]) -> set:
    out = set()
    for v in base:
        out |= {v, v + "s", v + "es", v + "ed", v + "d", v + "ing"}
        if v.endswith("e"):
            out.add(v[:-1] + "ing")
        if len(v) > 2 and v[-1] not in "aeiouwy" and v[-2] in "aeiou" and v[-3] not in "aeiou":
            out |= {v + v[-1] + "ed", v + v[-1] + "ing"}  # hug -> hugged, hugging
    return out


_VERBS = _verb_forms(_VERBS_BASE) | {
    "went", "gone", "said", "made", "knew", "known", "thought", "took", "taken", "saw", "seen", "came", "found",
    "gave", "given", "told", "felt", "became", "left", "meant", "kept", "began", "begun", "held", "brought",
    "wrote", "written", "stood", "lost", "paid", "met", "led", "understood", "spoke", "spoken", "grew", "grown",
    "won", "bought", "sent", "built", "fell", "fallen", "ate", "eaten", "drank", "flew", "sang", "slept", "woke",
    "drew", "drawn", "caught", "threw", "rode", "drove", "hid", "sat", "ran", "got", "did", "had",
}

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_SEGMENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


class KeywordError(Exception):
    """The LLM provider path failed (caller falls back to the heuristic)."""


# -- segmentation + heuristic ----------------------------------------------------


def split_segments(text: str) -> List[str]:
    """Sentences (and lines) of the script, trimmed, empties dropped."""
    parts = [p.strip() for p in _SEGMENT_SPLIT.split(text or "")]
    return [p for p in parts if p and _WORD.search(p)]


def _is_break(word: str) -> bool:
    w = word.lower()
    return w in _STOP or w in _VERBS or len(w) < 3


def _phrases(segment: str) -> List[Dict[str, Any]]:
    """Runs of content words between stop words / verbs / punctuation."""
    out: List[Dict[str, Any]] = []
    # punctuation other than hyphen/apostrophe breaks a phrase too
    for chunk in re.split(r"[,;:()\"“”]|\s-\s", segment):
        tokens = list(_WORD.finditer(chunk))
        run: List[str] = []
        caps = 0

        def flush():
            nonlocal run, caps
            words = list(run)
            # an adjective-ish keeper alone is not a term ("little")
            if words and not (len(words) == 1 and words[0].lower() in _KEEP_INSIDE_PHRASE):
                if len(words) > 3:
                    words = words[-3:]  # head noun is last in English noun phrases
                out.append({"term": " ".join(w.lower() for w in words), "words": len(words), "caps": caps})
            run, caps = [], 0

        for i, m in enumerate(tokens):
            w = m.group(0).strip("'-")
            lw = w.lower()
            if lw in _KEEP_INSIDE_PHRASE and i + 1 < len(tokens) and not _is_break(tokens[i + 1].group(0)):
                run.append(w)
                continue
            if _is_break(w):
                flush()
                continue
            run.append(w)
            if w[:1].isupper() and m.start() > 0 and not _is_sentence_start(segment, chunk, m.start()):
                caps += 1
        flush()
    return out


def _is_sentence_start(segment: str, chunk: str, pos: int) -> bool:
    return segment.find(chunk) == 0 and chunk[:pos].strip() == ""


def _rank(phrases: List[Dict[str, Any]]) -> List[str]:
    seen: Dict[str, Dict[str, Any]] = {}
    for idx, p in enumerate(phrases):
        if p["term"] not in seen:
            seen[p["term"]] = {**p, "idx": idx}
    ranked = sorted(seen.values(), key=lambda p: (-min(p["words"], 2), -p["caps"], -len(p["term"]), p["idx"]))
    return [p["term"] for p in ranked]


def heuristic_keywords(segments: List[str], per_segment_max: int = 3) -> List[List[str]]:
    out = []
    for seg in segments:
        ranked = _rank(_phrases(seg))
        # drop single words already covered by a kept phrase ("bear" when "teddy bear" is in)
        kept: List[str] = []
        for t in ranked:
            if any(t in k.split() for k in kept) or any(k in t.split() for k in kept):
                continue
            kept.append(t)
            if len(kept) >= per_segment_max:
                break
        out.append(kept)
    return out


def _global_terms(per_seg: List[List[str]], max_terms: int) -> List[str]:
    """Round-robin by rank across segments (every segment gets its best term
    first), then restore script order so `script_order` b-roll follows the script."""
    chosen: Dict[str, tuple] = {}
    depth = max((len(t) for t in per_seg), default=0)
    for rank in range(depth):
        for si, terms in enumerate(per_seg):
            if rank < len(terms) and terms[rank] not in chosen and len(chosen) < max_terms:
                chosen[terms[rank]] = (si, rank)
    return sorted(chosen, key=lambda t: chosen[t])


# -- LLM providers -----------------------------------------------------------------

_PROMPT = (
    "You pick stock-footage search terms for a video voiceover. For EACH numbered segment below, "
    "give 1 to {n} short, concrete, visual search terms (nouns or noun phrases a stock library like "
    "Pexels would match, e.g. 'teddy bear', 'city at night'; no abstract words, no verbs alone). "
    "Reply with ONLY a JSON array with one inner array of strings per segment, in order, nothing else.\n\n{segments}"
)


def _prompt(segments: List[str], n: int) -> str:
    return _PROMPT.format(n=n, segments="\n".join(f"{i + 1}. {s}" for i, s in enumerate(segments)))


def _parse_reply(text: str, count: int) -> List[List[str]]:
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        raise KeywordError("reply had no JSON array")
    try:
        data = json.loads(m.group(0))
    except ValueError as e:
        raise KeywordError(f"reply was not valid JSON: {e}") from e
    if isinstance(data, dict):
        data = data.get("segments") or data.get("terms")
    if not isinstance(data, list) or len(data) != count:
        raise KeywordError(f"expected {count} segment lists, got {len(data) if isinstance(data, list) else type(data).__name__}")
    out = []
    for item in data:
        if isinstance(item, dict):
            item = item.get("terms", [])
        if isinstance(item, str):
            item = [item]
        if not isinstance(item, list):
            raise KeywordError("segment entry is not a list")
        out.append([str(t).strip().lower() for t in item if str(t).strip()])
    return out


def llm_keywords(
    segments: List[str], provider: str, per_segment_max: int = 3, env: Optional[Mapping[str, str]] = None, transport: Any = None
) -> List[List[str]]:
    """Ask the provider for terms per segment. Raises KeywordError on any problem."""
    import httpx

    env = os.environ if env is None else env
    if provider not in PROVIDERS:
        raise KeywordError(f"unknown provider {provider!r} (use one of {', '.join(PROVIDERS)})")
    key = (env.get(KEY_ENV[provider]) or "").strip()
    if not key:
        raise KeywordError(f"{KEY_ENV[provider]} is not set")
    model = (env.get("DOLLYGRIP_KEYWORDS_MODEL") or "").strip() or DEFAULT_MODELS[provider]
    prompt = _prompt(segments, per_segment_max)
    if provider == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        payload: Dict[str, Any] = {"model": model, "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}]}
    else:
        headers = {"authorization": f"Bearer {key}", "content-type": "application/json"}
        payload = {"model": model, "temperature": 0.2, "messages": [{"role": "user", "content": prompt}]}
    try:
        with httpx.Client(transport=transport, timeout=60) as client:
            r = client.post(ENDPOINTS[provider], headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # network, HTTP status, bad JSON body
        raise KeywordError(f"{provider} request failed: {e}") from e
    try:
        if provider == "anthropic":
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        else:
            text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise KeywordError(f"{provider} reply had an unexpected shape: {e}") from e
    per_seg = _parse_reply(text, len(segments))
    return [list(dict.fromkeys(t))[:per_segment_max] for t in per_seg]


# -- entry point ---------------------------------------------------------------------


def keywords_from_script(
    text: str,
    max_terms: int = 8,
    per_segment: bool = True,
    provider: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    transport: Any = None,
) -> Dict[str, Any]:
    """Turn a script / voiceover text into stock-search terms.

    Returns {segments: [{text, terms}], terms, provider_used} (plus
    `fallback_reason` when an LLM provider was asked for and failed).
    `provider`: None = env `DOLLYGRIP_KEYWORDS_PROVIDER` (unset = heuristic),
    "heuristic" forces the offline tier. `per_segment=False` treats the whole
    script as one segment. `transport` is an httpx transport (tests stub it)."""
    env = os.environ if env is None else env
    max_terms = max(1, int(max_terms))
    segments = split_segments(text) if per_segment else ([" ".join((text or "").split())] if (text or "").strip() else [])
    per_seg_max = 3 if per_segment else max_terms
    chosen = (provider or env.get("DOLLYGRIP_KEYWORDS_PROVIDER") or "heuristic").strip().lower()
    result: Dict[str, Any] = {}
    per_seg: Optional[List[List[str]]] = None
    used = "heuristic"
    if segments and chosen != "heuristic":
        try:
            per_seg = llm_keywords(segments, chosen, per_seg_max, env=env, transport=transport)
            used = chosen
        except KeywordError as e:
            result["fallback_reason"] = str(e)
    if per_seg is None:
        per_seg = heuristic_keywords(segments, per_seg_max)
    result.update(
        segments=[{"text": s, "terms": t} for s, t in zip(segments, per_seg)],
        terms=_global_terms(per_seg, max_terms),
        provider_used=used,
    )
    return result
