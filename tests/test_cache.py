"""Tests for the API response cache (no network, no keys)."""
import io
import struct
import wave

import pytest
from fastapi.testclient import TestClient

from backend import cache as cache_mod
from backend import routes as routes_mod
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(routes_mod, "CACHE", cache_mod.TTLCache(ttl_s=300))


def _wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        n = 800
        w.writeframes(struct.pack("<" + "h" * n, *([1000] * n)))
    return buf.getvalue()


def test_native_second_identical_call_is_cache_hit(monkeypatch):
    calls = []

    def fake_speak(text, lang=None, speaker=None):
        calls.append(text)
        return {"audio": _wav(), "ttfa_ms": 7, "total_ms": 21}

    monkeypatch.setattr("backend.routes.rime.speak", fake_speak)
    r1 = client.post("/api/speak/native", json={"text": "hello ji"})
    r2 = client.post("/api/speak/native", json={"text": "hello ji"})
    assert r1.json()["cached"] is False
    assert r2.json()["cached"] is True
    assert r2.json()["audio_b64"] == r1.json()["audio_b64"]
    assert calls == ["hello ji"]  # provider billed once


def test_cache_key_includes_text(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.rime.speak",
        lambda text, lang=None, speaker=None: {"audio": _wav(), "ttfa_ms": 1, "total_ms": 2},
    )
    client.post("/api/speak/native", json={"text": "sentence one"})
    r = client.post("/api/speak/native", json={"text": "sentence two"})
    assert r.json()["cached"] is False


def test_baseline_caches_router_and_segments(monkeypatch):
    seg_calls, tts_calls = [], []

    def fake_segment(text, model=None):
        seg_calls.append(text)
        return [{"lang": "hin", "text": "a "}, {"lang": "eng", "text": "b"}], 12

    def fake_speak(text, lang=None, speaker=None):
        tts_calls.append(text)
        return {"audio": _wav(), "ttfa_ms": 2, "total_ms": 6}

    monkeypatch.setattr("backend.routes.segmenter.segment_timed", fake_segment)
    monkeypatch.setattr("backend.routes.parallel.rime.speak", fake_speak)
    r1 = client.post("/api/speak/baseline", json={"text": "a b"})
    r2 = client.post("/api/speak/baseline", json={"text": "a b"})
    assert r1.json()["cached"] is False
    assert r2.json()["cached"] is True
    assert r2.json()["audio_b64"] == r1.json()["audio_b64"]
    assert seg_calls == ["a b"]  # Groq billed once
    assert sorted(tts_calls) == ["a ", "b"]  # Rime billed once per segment


def test_ttl_expiry_forces_rebill():
    c = cache_mod.TTLCache(ttl_s=10)
    c.set(("k",), "v", now=100.0)
    assert c.get(("k",), now=105.0) == "v"
    assert c.get(("k",), now=111.0) is None
    assert c.stats()["hits"] == 1 and c.stats()["misses"] == 1


def test_max_entries_evicts_oldest():
    c = cache_mod.TTLCache(ttl_s=300, max_entries=2)
    c.set(("a",), 1, now=1.0)
    c.set(("b",), 2, now=2.0)
    c.set(("c",), 3, now=3.0)
    assert c.get(("a",), now=4.0) is None
    assert c.get(("b",), now=4.0) == 2


def test_stats_and_clear_endpoints(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.rime.speak",
        lambda text, lang=None, speaker=None: {"audio": _wav(), "ttfa_ms": 1, "total_ms": 2},
    )
    client.post("/api/speak/native", json={"text": "stats probe"})
    stats = client.get("/api/cache/stats").json()
    assert stats["enabled"] is True and stats["entries"] >= 1
    cleared = client.post("/api/cache/clear").json()
    assert cleared["cleared"] >= 1
    assert client.get("/api/cache/stats").json()["entries"] == 0
