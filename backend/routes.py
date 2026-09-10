"""API routes: native (Path A) vs segment-and-route baseline (Path B)."""
import base64
import json
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from . import audio, config, parallel, rime, segmenter

router = APIRouter(prefix="/api")

SENTENCES_PATH = Path(__file__).resolve().parent.parent / "sentences.json"

# Shared input guard: Rime rejects empty text and bills per call, so fail
# fast with a 422 before any provider call. 1000 chars keeps demo + eval
# sentences well under provider limits while blocking pasted-article abuse.
MAX_TEXT_CHARS = 1000


class SpeakRequest(BaseModel):
    text: str
    router_model: str | None = None
    # Opt-in to concurrent per-segment synthesis (backend/parallel.py).
    # None -> server default (config.BASELINE_PARALLEL_DEFAULT, off unless
    # BASELINE_PARALLEL=1). Reported back as "mode" in the response.
    parallel: bool | None = None

    @field_validator("text")
    @classmethod
    def text_must_be_speakable(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text must not be empty")
        if len(v.strip()) > MAX_TEXT_CHARS:
            raise ValueError(f"text must be <= {MAX_TEXT_CHARS} characters")
        return v


@router.post("/speak/native")
def speak_native(req: SpeakRequest):
    try:
        r = rime.speak(req.text, config.DEFAULT_LANG)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e), "provider": "rime", "fallback": "none"})
    return {
        "audio_b64": base64.b64encode(r["audio"]).decode(),
        "ttfa_ms": r["ttfa_ms"],
        "total_ms": r["total_ms"],
        "api_calls": 1,
    }


@router.post("/speak/baseline")
def speak_baseline(req: SpeakRequest):
    try:
        segments, segment_ms = segmenter.segment_timed(req.text, req.router_model)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e), "provider": "groq", "fallback": "none"})

    if not segments:
        return JSONResponse(
            status_code=502,
            content={"error": "segmenter returned no segments", "provider": "groq", "fallback": "none"},
        )

    results = []
    use_parallel = req.parallel if req.parallel is not None else config.BASELINE_PARALLEL_DEFAULT
    try:
        t0 = time.perf_counter()
        results = parallel.render_segments(segments, parallel=use_parallel)
        wall_ms = int((time.perf_counter() - t0) * 1000)
        combined = audio.concat_wav([r["audio"] for r in results])
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e), "provider": "rime", "fallback": "none"})

    # Honest totals: sequential sums per-segment times (historical
    # behavior); parallel measures wall time (segments overlap).
    total_ms = segment_ms + (wall_ms if use_parallel else sum(r["total_ms"] for r in results))
    return {
        "audio_b64": base64.b64encode(combined).decode(),
        "segment_ms": segment_ms,
        "ttfa_ms": segment_ms + (results[0]["ttfa_ms"] if results else 0),
        "total_ms": total_ms,
        "mode": "parallel" if use_parallel else "sequential",
        "api_calls": len(segments) + 1,
        "segments": [
            {
                "lang": s["lang"],
                "text": s["text"],
                "speaker": config.SPEAKER_MAP.get(s["lang"], config.RIME_SPEAKER),
                "ttfa_ms": r["ttfa_ms"],
                "total_ms": r["total_ms"],
            }
            for s, r in zip(segments, results)
        ],
    }


@router.get("/sentences")
def get_sentences():
    return json.loads(SENTENCES_PATH.read_text(encoding="utf-8"))
