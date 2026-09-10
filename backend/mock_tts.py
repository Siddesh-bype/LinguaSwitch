"""Offline mock TTS + mock segmenter for dev/CI without API keys.

Enabled via env (see backend/config.py):
  MOCK_TTS=1        backend.rime.speak returns deterministic sine WAVs
  MOCK_SEGMENTER=1  backend.segmenter returns rule-based segments

Mock audio is deliberately synthetic (a sine tone whose duration scales
with text length) — it exercises the full native/baseline/concat code
paths, the frontend player, and CI, without billing any provider or
needing secrets. Never confuse it with real eval clips: mock runs must
not be appended to data/timings.jsonl.
"""
import hashlib
import io
import math
import struct
import wave

RATE = 8000


def mock_wav(text: str, freq: float = 440.0) -> bytes:
    """Deterministic sine WAV: 300ms base + 25ms per char, capped at 3s."""
    ms = min(3000, 300 + 25 * len(text))
    n = RATE * ms // 1000
    # Deterministic phase from text hash so different texts sound different.
    phase = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) % 360
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(
            b"".join(
                struct.pack(
                    "<h",
                    int(8000 * math.sin(2 * math.pi * freq * i / RATE + math.radians(phase))),
                )
                for i in range(n)
            )
        )
    return buf.getvalue()


def mock_speak(text: str) -> dict:
    """Stand-in for rime.speak: fake near-zero latency + synthetic audio."""
    audio = mock_wav(text)
    duration_ms = min(3000, 300 + 25 * len(text))
    return {"audio": audio, "ttfa_ms": 5, "total_ms": duration_ms}


def mock_segment(text: str) -> list[dict]:
    """Rule-based offline segmentation (reconstruction-guaranteed).

    Splits on strong phrase boundaries (em-dash, comma+space, '? ', '! ')
    and alternates hin/eng starting with hin. Concatenating segment texts
    always reconstructs the input exactly.
    """
    import re

    parts = re.split(r"( — |, |\? |! )", text)
    # re.split with capture keeps delimiters: re-attach each delimiter to
    # the preceding chunk so concat == original.
    chunks: list[str] = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        if i + 1 < len(parts):
            chunk += parts[i + 1]
            i += 2
        else:
            i += 1
        if chunk:
            chunks.append(chunk)
    if not chunks:
        return [{"lang": "hin", "text": text}]
    langs = ["hin", "eng"]
    return [{"lang": langs[k % 2], "text": c} for k, c in enumerate(chunks)]
