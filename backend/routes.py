"""API routes: native (Path A) vs segment-and-route baseline (Path B)."""
import base64
import json
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from . import audio, cache, config, parallel, rime, segmenter

router = APIRouter(prefix="/api")

SENTENCES_PATH = Path(__file__).resolve().parent.parent / "sentences.json"

# Shared input guard: Rime rejects empty text and bills per call, so fail
# fast with a 422 before any provider call. 1000 chars keeps demo + eval
# sentences well under provider limits while blocking pasted-article abuse.
MAX_TEXT_CHARS = 1000

# Process-wide API cache (backend/cache.py). run_eval.py bypasses it.
CACHE = cache.shared()


def _cache_on() -> bool:
    return config.CACHE_TTL_S > 0


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
    lang, speaker = config.DEFAULT_LANG, config.RIME_SPEAKER
    key = cache.tts_key(req.text, lang, speaker)
    if _cache_on():
        hit = CACHE.get(key)
        if hit is not None:
            return {
                "audio_b64": base64.b64encode(hit["audio"]).decode(),
                "ttfa_ms": hit["ttfa_ms"],
                "total_ms": hit["total_ms"],
                "api_calls": 1,
                "cached": True,
            }
    try:
        r = rime.speak(req.text, lang)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e), "provider": "rime", "fallback": "none"})
    if _cache_on():
        CACHE.set(key, r)
    return {
        "audio_b64": base64.b64encode(r["audio"]).decode(),
        "ttfa_ms": r["ttfa_ms"],
        "total_ms": r["total_ms"],
        "api_calls": 1,
        "cached": False,
    }


@router.post("/speak/baseline")
def speak_baseline(req: SpeakRequest):
    model = req.router_model or config.GROQ_ROUTER_MODEL
    seg_from_cache = False
    if _cache_on():
        seg_hit = CACHE.get(cache.seg_key(req.text, model))
        if seg_hit is not None:
            segments, segment_ms = seg_hit["segments"], seg_hit["segment_ms"]
            seg_from_cache = True
    if not seg_from_cache:
        try:
            segments, segment_ms = segmenter.segment_timed(req.text, req.router_model)
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": str(e), "provider": "groq", "fallback": "none"})
        if _cache_on():
            CACHE.set(cache.seg_key(req.text, model), {"segments": segments, "segment_ms": segment_ms})

    # Per-segment TTS: serve hits from cache, render only the misses
    # (through the sequential/parallel path), then merge back in order.
    slots: list[dict | None] = [None] * len(segments)
    if _cache_on():
        for i, seg in enumerate(segments):
            lang = config.LANG_MAP.get(seg["lang"], config.DEFAULT_LANG)
            speaker = config.SPEAKER_MAP.get(seg["lang"], config.RIME_SPEAKER)
            hit = CACHE.get(cache.tts_key(seg["text"], lang, speaker))
            if hit is not None:
                slots[i] = hit
    missing = [seg for seg, slot in zip(segments, slots) if slot is None]

    if not segments:
        return JSONResponse(
            status_code=502,
            content={"error": "segmenter returned no segments", "provider": "groq", "fallback": "none"},
        )

    use_parallel = req.parallel if req.parallel is not None else config.BASELINE_PARALLEL_DEFAULT
    try:
        t0 = time.perf_counter()
        rendered = parallel.render_segments(missing, parallel=use_parallel) if missing else []
        wall_ms = int((time.perf_counter() - t0) * 1000)
        if _cache_on():
            for seg, r in zip(missing, rendered):
                lang = config.LANG_MAP.get(seg["lang"], config.DEFAULT_LANG)
                speaker = config.SPEAKER_MAP.get(seg["lang"], config.RIME_SPEAKER)
                CACHE.set(cache.tts_key(seg["text"], lang, speaker), r)
        it = iter(rendered)
        results = [slot if slot is not None else next(it) for slot in slots]
        combined = audio.concat_wav([r["audio"] for r in results])
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e), "provider": "rime", "fallback": "none"})

    # Honest totals: sequential sums per-segment times (historical
    # behavior). Parallel takes max(wall, peak segment) — cold runs report
    # measured wall time, while partially-cached runs stay comparable to
    # cold ones instead of understating.
    peak = max([r["total_ms"] for r in results] + [0])
    total_ms = segment_ms + (max(wall_ms, peak) if use_parallel else sum(r["total_ms"] for r in results))
    all_cached = seg_from_cache and not missing
    return {
        "audio_b64": base64.b64encode(combined).decode(),
        "segment_ms": segment_ms,
        "ttfa_ms": segment_ms + (results[0]["ttfa_ms"] if results else 0),
        "total_ms": total_ms,
        "mode": "parallel" if use_parallel else "sequential",
        "cached": all_cached,
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


@router.get("/cache/stats")
def cache_stats():
    stats = CACHE.stats()
    stats["enabled"] = _cache_on()
    return stats


@router.post("/cache/clear")
def cache_clear():
    return {"cleared": CACHE.clear()}
