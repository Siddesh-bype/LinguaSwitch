"""Offline tests for WAV concat (no network, no API keys).

Covers the regression backend/audio.py was written for: Rime streams WAV
with placeholder header counts, and Path B concatenates per-segment WAVs.
"""
import io
import struct
import wave

import pytest

from backend import audio


def _sine_wav(freq=440.0, ms=100, rate=8000, lie_nframes=False):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = rate * ms // 1000
        import math

        w.writeframes(
            b"".join(
                struct.pack("<h", int(12000 * math.sin(2 * 3.14159 * freq * i / rate)))
                for i in range(n)
            )
        )
    raw = buf.getvalue()
    if lie_nframes:
        raw = raw[:40] + struct.pack("<L", 2147483647) + raw[44:]
    return raw


def test_concat_two_placeholder_wavs_frame_counts_add_up():
    a = _sine_wav(440, 100, lie_nframes=True)
    b = _sine_wav(880, 150, lie_nframes=True)
    joined = audio.concat_wav([a, b])
    with wave.open(io.BytesIO(joined)) as w:
        assert w.getnframes() == 800 + 1200
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 8000)


def test_concat_single_wav_roundtrips():
    a = _sine_wav(440, 50)
    joined = audio.concat_wav([a])
    with wave.open(io.BytesIO(joined)) as w:
        assert w.getnframes() == 400


def test_concat_param_mismatch_raises_instead_of_garbage():
    a = _sine_wav(440, 50, rate=8000)
    b = _sine_wav(440, 50, rate=16000)
    with pytest.raises(ValueError, match="param mismatch"):
        audio.concat_wav([a, b])


def test_read_pcm_rejects_non_wav_with_context():
    with pytest.raises(ValueError, match="not a WAV"):
        audio.read_pcm(b"definitely not audio" * 10)


def test_read_pcm_rejects_empty_frames():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
    with pytest.raises(ValueError, match="no readable frames"):
        audio.read_pcm(buf.getvalue())
