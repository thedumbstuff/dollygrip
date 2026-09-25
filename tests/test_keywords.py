import json

import httpx

from conftest import make_client, make_stock
from dollygrip.keywords import heuristic_keywords, keywords_from_script, split_segments

V1 = "/api/v1"
SCRIPT = (
    "An apple a day keeps the doctor away. "
    "The little girl hugs her teddy bear before bed. "
    "Then Grandpa Joe takes her to the Eiffel Tower in Paris! "
    "At night, the stars shine over the quiet ocean."
)


def test_split_segments():
    assert split_segments(SCRIPT)[1] == "The little girl hugs her teddy bear before bed."
    assert len(split_segments(SCRIPT)) == 4
    assert split_segments("line one\n\nline two") == ["line one", "line two"]
    assert split_segments("") == [] and split_segments(" ... ") == []


def test_heuristic_kids_script_yields_concrete_terms():
    out = keywords_from_script(SCRIPT, env={})
    assert out["provider_used"] == "heuristic" and "fallback_reason" not in out
    assert [s["text"] for s in out["segments"]] == split_segments(SCRIPT)
    seg_terms = [s["terms"] for s in out["segments"]]
    assert "apple" in seg_terms[0] and "teddy bear" in seg_terms[1] and "eiffel tower" in seg_terms[2] and "ocean" in " ".join(seg_terms[3])
    assert all(1 <= len(t) <= 3 for t in seg_terms)
    # no verbs or stop words leak in, no single word already inside a kept phrase
    flat = [t for ts in seg_terms for t in ts]
    assert not {"keeps", "hugs", "takes", "shine", "the", "her", "bear"} & set(flat)
    # global list: every segment represented, script order, capped
    assert len(out["terms"]) == 8 and len(set(out["terms"])) == 8
    firsts = [ts[0] for ts in seg_terms]
    assert all(f in out["terms"] for f in firsts)
    order = [next(i for i, ts in enumerate(seg_terms) if t in ts) for t in out["terms"]]
    assert order == sorted(order)
    assert len(keywords_from_script(SCRIPT, max_terms=2, env={})["terms"]) == 2


def test_heuristic_single_segment_mode():
    out = keywords_from_script("We walked through the busy city streets at night, watching the rain.", per_segment=False, env={})
    assert len(out["segments"]) == 1 and "rain" in out["terms"] and any("city" in t for t in out["terms"])
    assert heuristic_keywords([]) == []


def _transport(reply_text=None, status=200, seen=None, shape="openai"):
    def handler(request: httpx.Request):
        if seen is not None:
            seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": "nope"})
        if shape == "anthropic":
            return httpx.Response(200, json={"content": [{"type": "text", "text": reply_text}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": reply_text}}]})

    return httpx.MockTransport(handler)


LLM_REPLY = json.dumps([["red apple", "doctor"], ["teddy bear"], ["eiffel tower", "paris street"], ["night sky stars", "ocean waves"]])


def test_provider_path_openai_and_deepseek():
    seen = []
    out = keywords_from_script(SCRIPT, provider="openai", env={"OPENAI_API_KEY": "sk-x"}, transport=_transport("Sure:\n" + LLM_REPLY, seen=seen))
    assert out["provider_used"] == "openai" and out["segments"][0]["terms"] == ["red apple", "doctor"]
    assert out["terms"][:3] == ["red apple", "doctor", "teddy bear"]
    req = seen[0]
    assert str(req.url) == "https://api.openai.com/v1/chat/completions" and req.headers["authorization"] == "Bearer sk-x"
    body = json.loads(req.content)
    assert body["model"] == "gpt-4o-mini" and "4. At night" in body["messages"][0]["content"]
    # env selects the provider; model override
    seen.clear()
    env = {"DOLLYGRIP_KEYWORDS_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "d", "DOLLYGRIP_KEYWORDS_MODEL": "deepseek-reasoner"}
    out = keywords_from_script(SCRIPT, env=env, transport=_transport(LLM_REPLY, seen=seen))
    assert out["provider_used"] == "deepseek" and json.loads(seen[0].content)["model"] == "deepseek-reasoner"
    assert str(seen[0].url) == "https://api.deepseek.com/chat/completions"


def test_provider_path_anthropic():
    seen = []
    out = keywords_from_script(SCRIPT, provider="anthropic", env={"ANTHROPIC_API_KEY": "a"}, transport=_transport(LLM_REPLY, seen=seen, shape="anthropic"))
    assert out["provider_used"] == "anthropic" and out["segments"][1]["terms"] == ["teddy bear"]
    req = seen[0]
    assert str(req.url) == "https://api.anthropic.com/v1/messages" and req.headers["x-api-key"] == "a" and req.headers["anthropic-version"]
    assert json.loads(req.content)["model"] == "claude-sonnet-5"


def test_provider_failures_fall_back_to_heuristic():
    heuristic = keywords_from_script(SCRIPT, env={})
    cases = [
        dict(provider="openai", env={}, transport=_transport(LLM_REPLY)),  # no key
        dict(provider="openai", env={"OPENAI_API_KEY": "k"}, transport=_transport(status=500)),  # HTTP error
        dict(provider="openai", env={"OPENAI_API_KEY": "k"}, transport=_transport("no json here")),  # unparseable
        dict(provider="openai", env={"OPENAI_API_KEY": "k"}, transport=_transport(json.dumps([["only one"]]))),  # wrong count
        dict(provider="mistral", env={}, transport=None),  # unknown provider
    ]
    for kw in cases:
        out = keywords_from_script(SCRIPT, **kw)
        assert out["provider_used"] == "heuristic" and out["fallback_reason"], kw
        assert out["terms"] == heuristic["terms"]


def test_keywords_endpoint(fake_resolve, tmp_path, monkeypatch):
    client = make_client(fake_resolve, stock=make_stock(tmp_path))
    r = client.post(f"{V1}/stock/keywords", json={"text": SCRIPT, "max_terms": 5, "provider": "heuristic"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_used"] == "heuristic" and len(body["terms"]) == 5 and len(body["segments"]) == 4
    assert client.post(f"{V1}/stock/keywords", json={"text": "   "}).status_code == 422
    assert client.post(f"{V1}/stock/keywords", json={"text": "x", "provider": "gemini"}).status_code == 422
    # stubbed provider through app state
    client.app.state.keywords_transport = _transport(LLM_REPLY)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = client.post(f"{V1}/stock/keywords", json={"text": SCRIPT, "provider": "openai"})
    assert r.json()["provider_used"] == "openai" and r.json()["segments"][2]["terms"] == ["eiffel tower", "paris street"]


def test_b_roll_from_script(fake_resolve, tmp_path, project, timeline):
    calls = []
    client = make_client(fake_resolve, stock=make_stock(tmp_path, calls))
    r = client.post(f"{V1}/stock/b-roll", json={"script": SCRIPT, "max_terms": 4, "keywords_provider": "heuristic", "audio_duration": 9, "max_clip_duration": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["keywords"]["provider_used"] == "heuristic" and len(body["keywords"]["terms"]) == 4
    assert [c[1]["query"] for c in calls] == body["keywords"]["terms"]  # searched the derived terms in script order
    assert body["all_ok"] and body["plan"]["total_duration"] == 9.1 and body["shots"] >= 3
    # neither terms nor script -> 422 before anything touches the timeline
    assert client.post(f"{V1}/stock/b-roll", json={"audio_duration": 5}).status_code == 422
    assert client.post(f"{V1}/stock/b-roll", json={"script": "   ", "audio_duration": 5}).status_code == 422
    # explicit terms still win and no keywords block is returned
    r = client.post(f"{V1}/stock/b-roll", json={"terms": ["city"], "script": SCRIPT, "audio_duration": 4})
    assert r.status_code == 200 and "keywords" not in r.json()
