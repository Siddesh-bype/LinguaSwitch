"""Rime TTS client.

Verified request shape per https://docs.rime.ai/docs/api-cheat-sheet:
POST https://users.rime.ai/v1/rime-tts with JSON
{"text", "speaker", "modelId", "lang"?} and `Accept: audio/<fmt>`.
scripts/smoke_test.py is the Day 0 gate confirming the pinned
model/speaker/lang values in config.py still work.
"""
import time

import httpx

from . import config


def speak(text: str, lang: str | None = None, speaker: str | None = None) -> dict:
    """Synthesize `text` via Rime.

    Returns {"audio": bytes, "ttfa_ms": int, "total_ms": int}
    (ttfa = time to first byte of the audio response body).
    """
    if not config.RIME_API_KEY:
        raise RuntimeError(
            "RIME_API_KEY is not set — copy .env.example to .env and fill it in."
        )
    if not text or not text.strip():
        raise ValueError("text must not be empty")
    body = {
        "text": text,
        "speaker": speaker or config.RIME_SPEAKER,
        "modelId": config.RIME_MODEL,
    }
    if lang:
        body["lang"] = lang

    t0 = time.perf_counter()
    first_byte = None
    audio = b""
    with httpx.Client(timeout=120) as client:
        with client.stream(
            "POST",
            f"{config.RIME_API_BASE}/rime-tts",
            headers={
                "Authorization": f"Bearer {config.RIME_API_KEY}",
                "Accept": f"audio/{config.RIME_OUTPUT_FORMAT}",
            },
            json=body,
        ) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes():
                if chunk and first_byte is None:
                    first_byte = time.perf_counter()
                audio += chunk
    t_end = time.perf_counter()

    return {
        "audio": audio,
        "ttfa_ms": int(((first_byte or t_end) - t0) * 1000),
        "total_ms": int((t_end - t0) * 1000),
    }
