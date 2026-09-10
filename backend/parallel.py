"""Parallel fan-out for Path B per-segment synthesis.

README/RIME_EVIDENCE.md acknowledge that Path B's per-segment Rime calls
are sequential (worst case for baseline latency). This module adds an
opt-in concurrent fan-out: order-preserving, fail-fast, and off by
default so published eval numbers stay comparable unless --parallel
(or parallel:true) is explicitly requested.

Wall-clock honesty: in parallel mode the path total must be measured
wall time, NOT the sum of per-segment totals (segments overlap).
Callers measure the wall time around render_segments().
"""
from concurrent.futures import ThreadPoolExecutor

from . import config, rime


def _speak_one(seg: dict) -> dict:
    # A Rime voice serves one language: swap speaker per segment
    # (same mapping as the sequential loop in backend/routes.py).
    return rime.speak(
        seg["text"],
        config.LANG_MAP.get(seg["lang"], config.DEFAULT_LANG),
        config.SPEAKER_MAP.get(seg["lang"], config.RIME_SPEAKER),
    )


def render_segments(segments: list[dict], parallel: bool = False, max_workers: int | None = None) -> list[dict]:
    """Synthesize one Rime result per segment, preserving segment order.

    Sequential mode is the historical behavior (loop in call order).
    Parallel mode fans out over a thread pool (Rime calls are
    network-bound, so threads — not processes — are the right tool).
    The first segment failure propagates; partial results are discarded
    so callers never concatenate a half-rendered baseline.
    """
    if not parallel or len(segments) < 2:
        return [_speak_one(seg) for seg in segments]
    workers = max_workers or config.BASELINE_MAX_WORKERS
    with ThreadPoolExecutor(max_workers=min(workers, len(segments))) as pool:
        # executor.map preserves input order and raises on first error
        # when iterated — exactly the fail-fast semantics we want.
        return list(pool.map(_speak_one, segments))
