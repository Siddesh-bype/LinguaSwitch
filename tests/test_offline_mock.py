"""Offline-mode tests: mock TTS/segmenter, seam proxy, metrics API, summary.

No network, no keys. MOCK flags are set per-test via monkeypatch.
"""
import base64
import io
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402


def _wav(ms_tone=200, ms_silence=400, rate=8000):
    """Tone-silence-tone WAV: 1 interior gap of known length."""
    def tone(ms):
        n = rate * ms // 1000
        return struct.pack("<" + "h" * n, *([4000] * n))

    def silence(ms):
        n = rate * ms // 1000
        return struct.pack("<" + "h" * n, *([0] * n))

    pcm = tone(ms_tone) + silence(ms_silence) + tone(ms_tone)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def test_mock_wav_is_deterministic_and_valid():
    from backend.mock_tts import mock_wav

    a = mock_wav("hello ji")
    b = mock_wav("hello ji")
    c = mock_wav("something else")
    assert a == b
    assert a != c
    with wave.open(io.BytesIO(a)) as w:
        assert w.getnframes() > 0


def test_mock_segment_reconstructs_input():
    from backend.mock_tts import mock_segment

    for text in [
        "Mera order kahan hai, can you check the status please?",
        "Sir, ye product damaged hai — I want a return.",
        "Haan bhai, wo delivery date confirm kar do.",
    ]:
        segs = mock_segment(text)
        assert "".join(s["text"] for s in segs) == text
        assert all(s["lang"] in ("hin", "eng") for s in segs)


def test_rime_mock_mode_returns_synth_audio(monkeypatch):
    import backend.config as config
    import backend.rime as rime

    monkeypatch.setattr(config, "MOCK_TTS", True)
    monkeypatch.setattr(rime.config, "MOCK_TTS", True)
    out = rime.speak("hello ji")
    assert out["audio"][:4] == b"RIFF"
    assert out["total_ms"] > 0


def test_segmenter_mock_mode(monkeypatch):
    import backend.config as config
    import backend.segmenter as segmenter

    monkeypatch.setattr(config, "MOCK_SEGMENTER", True)
    monkeypatch.setattr(segmenter.config, "MOCK_SEGMENTER", True)
    text = "Mera order kahan hai, can you check?"
    segs = segmenter.segment(text)
    assert "".join(s["text"] for s in segs) == text


def test_seam_proxy_detects_long_gap():
    from backend import seam

    m = seam.score_wav(_wav(ms_silence=400))
    assert m["n_long_gaps"] >= 1
    assert m["max_gap_ms"] >= 300
    clean = seam.score_wav(_wav(ms_silence=0))
    assert clean["n_long_gaps"] == 0


def test_seam_proxy_rejects_non_wav():
    from backend import seam

    try:
        seam.score_wav(b"not audio")
    except ValueError as e:
        assert "WAV" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_metrics_api_scores_and_compares():
    from backend.main import app

    client = TestClient(app)
    gappy = base64.b64encode(_wav(ms_silence=500)).decode()
    clean = base64.b64encode(_wav(ms_silence=0)).decode()

    r = client.post("/api/metrics/seam", json={"audio_b64": clean})
    assert r.status_code == 200
    assert r.json()["n_long_gaps"] == 0

    r = client.post("/api/metrics/seam/compare", json={"audio_b64_a": clean, "audio_b64_b": gappy})
    assert r.status_code == 200
    body = r.json()
    assert body["delta_b_minus_a"] > 0

    r = client.post("/api/metrics/seam", json={"audio_b64": "!!!not-base64!!!"})
    assert r.status_code == 422


def test_export_summary_uses_latest_row_per_sentence():
    import json
    import tempfile

    from scripts.export_summary import load_latest, summarize

    rows = [
        {"sentence_id": 1, "path": "a", "ttfa_ms": 1000, "total_ms": 2000},
        {"sentence_id": 1, "path": "b", "ttfa_ms": 2500, "total_ms": 5000, "segment_ms": 1000, "segments": 2},
        {"sentence_id": 1, "path": "a", "ttfa_ms": 1100, "total_ms": 2100},  # rerun wins
    ]
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "timings.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        latest = load_latest(p)
    assert latest[(1, "a")]["total_ms"] == 2100
    s = summarize(latest)
    assert s["n_sentences"] == 1
    assert s["avg_a_total_ms"] == 2100
    assert s["native_wins"] == 1
