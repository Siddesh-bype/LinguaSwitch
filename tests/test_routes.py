"""Offline API tests: health, validation, native/baseline/agentic (mocked providers).

No network or API keys: rime.speak and segmenter are monkeypatched.
"""
import base64
import io
import struct
import wave

from fastapi.testclient import TestClient

from backend import audio as audio_mod
from backend.main import app
from backend.routes import MAX_TEXT_CHARS

client = TestClient(app)


def _wav_bytes(ms=80):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        n = 8000 * ms // 1000
        w.writeframes(struct.pack("<" + "h" * n, *([1000] * n)))
    return buf.getvalue()


def test_health_reports_config_without_secrets():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["rime_model"]
    assert "hin" in body["speakers"]
    assert "RIME_API_KEY" not in str(body)
    assert "GROQ_API_KEY" not in str(body)


def test_sentences_returns_test_set():
    r = client.get("/api/sentences")
    assert r.status_code == 200
    assert len(r.json()["sentences"]) == 10


def test_native_rejects_empty_text_with_422():
    r = client.post("/api/speak/native", json={"text": "   "})
    assert r.status_code == 422


def test_native_rejects_oversize_text_with_422():
    r = client.post("/api/speak/native", json={"text": "x" * (MAX_TEXT_CHARS + 1)})
    assert r.status_code == 422


def test_baseline_rejects_empty_text_with_422():
    r = client.post("/api/speak/baseline", json={"text": ""})
    assert r.status_code == 422


def test_agentic_rejects_empty_text_with_422():
    r = client.post("/api/speak/agentic", json={"text": ""})
    assert r.status_code == 422


def test_native_ok_path(monkeypatch):
    wav = _wav_bytes()
    monkeypatch.setattr("backend.routes.rime.speak", lambda text, lang=None, speaker=None: {"audio": wav, "ttfa_ms": 10, "total_ms": 20})
    r = client.post("/api/speak/native", json={"text": "Mera order kahan hai, can you check?"})
    assert r.status_code == 200
    body = r.json()
    assert body["api_calls"] == 1
    assert base64.b64decode(body["audio_b64"]) == wav


def test_native_surfaces_provider_error_as_502(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Rime WS error: down")

    monkeypatch.setattr("backend.routes.rime.speak", boom)
    r = client.post("/api/speak/native", json={"text": "hello"})
    assert r.status_code == 502
    assert r.json()["provider"] == "rime"
    assert r.json()["fallback"] == "none"


def test_baseline_concats_segments_and_counts_calls(monkeypatch):
    wav = _wav_bytes()
    monkeypatch.setattr(
        "backend.routes.segmenter.segment_timed",
        lambda text, model=None: ([{"lang": "hin", "text": "mera order "}, {"lang": "eng", "text": "check please"}], 50),
    )
    monkeypatch.setattr(
        "backend.routes.rime.speak",
        lambda text, lang=None, speaker=None: {"audio": wav, "ttfa_ms": 5, "total_ms": 15},
    )
    r = client.post("/api/speak/baseline", json={"text": "mera order check please"})
    assert r.status_code == 200
    body = r.json()
    assert body["api_calls"] == 3  # 2 segments + 1 router call
    assert body["segment_ms"] == 50
    assert [s["lang"] for s in body["segments"]] == ["hin", "eng"]
    combined = base64.b64decode(body["audio_b64"])
    # two 640-frame segments concatenated
    import wave as _wave

    with _wave.open(io.BytesIO(combined)) as w:
        assert w.getnframes() == 640 * 2


def test_baseline_empty_segments_is_502_not_crash(monkeypatch):
    monkeypatch.setattr("backend.routes.segmenter.segment_timed", lambda text, model=None: ([], 10))
    r = client.post("/api/speak/baseline", json={"text": "hello ji"})
    assert r.status_code == 502


def test_agentic_ok_path(monkeypatch):
    wav = _wav_bytes()
    fake = {
        "audio_a": wav,
        "audio_b": audio_mod.concat_wav([wav, wav]),
        "metrics_a": {"ttfa_ms": 1, "total_ms": 2, "api_calls": 1},
        "metrics_b": {"ttfa_ms": 3, "total_ms": 4, "api_calls": 3},
        "segments": [{"lang": "hin", "text": "a", "speaker": "nadi", "ttfa_ms": 1, "total_ms": 1}],
    }
    monkeypatch.setattr("backend.agent_routes.run_agentic", lambda text, model=None: fake)
    r = client.post("/api/speak/agentic", json={"text": "hello ji"})
    assert r.status_code == 200
    assert r.json()["metrics_a"]["api_calls"] == 1
