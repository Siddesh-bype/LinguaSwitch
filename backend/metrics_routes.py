"""Metrics routes: lightweight offline-safe scoring APIs.

POST /api/metrics/seam {audio_b64} -> seam proxy for one clip
POST /api/metrics/seam/compare {audio_b64_a, audio_b64_b} -> both + delta

Stdlib-only (backend/seam.py); works without librosa, keys, or network.
The full librosa SBDS analysis stays in scripts/sbds.py.
"""
import base64
import binascii

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import seam

router = APIRouter(prefix="/api/metrics")


class SeamRequest(BaseModel):
    audio_b64: str


class SeamCompareRequest(BaseModel):
    audio_b64_a: str
    audio_b64_b: str


def _decode_b64(label: str, payload: str) -> bytes:
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} is not valid base64")


@router.post("/seam")
def seam_score(req: SeamRequest):
    try:
        wav = _decode_b64("audio_b64", req.audio_b64)
        return seam.score_wav(wav)
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    except Exception as e:  # noqa: BLE001 — never leak tracebacks to raters
        return JSONResponse(status_code=500, content={"error": f"scoring failed: {e}"})


@router.post("/seam/compare")
def seam_compare(req: SeamCompareRequest):
    try:
        wav_a = _decode_b64("audio_b64_a", req.audio_b64_a)
        wav_b = _decode_b64("audio_b64_b", req.audio_b64_b)
        a = seam.score_wav(wav_a)
        b = seam.score_wav(wav_b)
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": f"scoring failed: {e}"})
    return {
        "a": a,
        "b": b,
        "delta_b_minus_a": round(b["seam_score"] - a["seam_score"], 3),
        "note": "positive delta = B shows more long-gap seam evidence than A (stdlib proxy; see scripts/sbds.py for the full metric)",
    }
