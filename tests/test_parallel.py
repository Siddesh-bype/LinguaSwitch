"""Tests for parallel Path B fan-out (no network, no keys)."""
import io
import struct
import time
import wave

import pytest
from fastapi.testclient import TestClient

from backend import parallel
from backend.main import app

client = TestClient(app)


def _wav(seed: int = 0):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        n = 800
        w.writeframes(struct.pack("<" + "h" * n, *([(1000 + seed)] * n)))
    return buf.getvalue()


SEGS = [
    {"lang": "hin", "text": "mera order "},
    {"lang": "eng", "text": "check please "},
    {"lang": "hin", "text": "kab tak aayega?"},
]


def test_sequential_preserves_order_and_mapping(monkeypatch):
    seen = []

    def fake_speak(text, lang=None, speaker=None):
        seen.append((text, lang, speaker))
        return {"audio": _wav(len(seen)), "ttfa_ms": 1, "total_ms": 2}

    monkeypatch.setattr("backend.parallel.rime.speak", fake_speak)
    out = parallel.render_segments(SEGS, parallel=False)
    assert [s for s, _, _ in seen] == [s["text"] for s in SEGS]
    # one voice per language: hin->nadi, eng->astra (pinned test speakers)
    assert seen[0][2] == "nadi" and seen[1][2] == "astra"
    assert len(out) == 3


def test_parallel_preserves_order_despite_skewed_latency(monkeypatch):
    def fake_speak(text, lang=None, speaker=None):
        # first segment slowest: naive append-as-completed would misorder
        time.sleep(0.05 if text.startswith("mera") else 0.0)
        return {"audio": _wav(len(text)), "ttfa_ms": 1, "total_ms": 2, "echo": text}

    monkeypatch.setattr("backend.parallel.rime.speak", fake_speak)
    out = parallel.render_segments(SEGS, parallel=True, max_workers=3)
    assert [r["echo"] for r in out] == [s["text"] for s in SEGS]


def test_parallel_single_segment_skips_pool(monkeypatch):
    calls = []

    def fake_speak(text, lang=None, speaker=None):
        calls.append(text)
        return {"audio": _wav(), "ttfa_ms": 1, "total_ms": 1}

    monkeypatch.setattr("backend.parallel.rime.speak", fake_speak)
    out = parallel.render_segments(SEGS[:1], parallel=True)
    assert len(out) == 1 and calls == [SEGS[0]["text"]]


def test_first_failure_propagates_no_partial_concat(monkeypatch):
    def fake_speak(text, lang=None, speaker=None):
        if "please" in text:
            raise RuntimeError("rime down")
        return {"audio": _wav(), "ttfa_ms": 1, "total_ms": 1}

    monkeypatch.setattr("backend.parallel.rime.speak", fake_speak)
    with pytest.raises(RuntimeError, match="rime down"):
        parallel.render_segments(SEGS, parallel=True)


def test_api_defaults_to_sequential_with_mode_flag(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.segmenter.segment_timed",
        lambda text, model=None: ([{"lang": "hin", "text": "a "}, {"lang": "eng", "text": "b"}], 10),
    )
    monkeypatch.setattr(
        "backend.routes.rime.speak",
        lambda text, lang=None, speaker=None: {"audio": _wav(), "ttfa_ms": 2, "total_ms": 5},
    )
    r = client.post("/api/speak/baseline", json={"text": "a b"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "sequential"
    assert body["total_ms"] == 10 + 5 + 5  # segment + summed (historical)


def test_api_parallel_flag_returns_wall_clock_mode(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.segmenter.segment_timed",
        lambda text, model=None: ([{"lang": "hin", "text": "a "}, {"lang": "eng", "text": "b"}], 10),
    )
    monkeypatch.setattr(
        "backend.routes.parallel.rime.speak",
        lambda text, lang=None, speaker=None: {"audio": _wav(), "ttfa_ms": 2, "total_ms": 500},
    )
    r = client.post("/api/speak/baseline", json={"text": "a b", "parallel": True})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "parallel"
    # wall-clock total must be far below the 10+500+500 sequential sum
    assert body["total_ms"] < 10 + 500 + 500
