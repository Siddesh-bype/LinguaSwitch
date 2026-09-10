"""Eval dashboard API: serve the timings rollup for the /eval page.

GET /api/eval/summary -> latest-row-per-sentence rollup of
data/timings.jsonl (same numbers scripts/export_summary.py prints).
404 when no eval has been run yet — the dashboard shows "run the eval"
instead of fake zeros.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from . import eval_summary

router = APIRouter(prefix="/api/eval")


@router.get("/summary")
def summary():
    if not eval_summary.TIMINGS.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "no eval data yet — run `py scripts/run_eval.py` first"},
        )
    try:
        return eval_summary.summarize(eval_summary.load_latest(eval_summary.TIMINGS))
    except Exception as e:  # noqa: BLE001 — corrupt jsonl shouldn't 500 opaquely
        return JSONResponse(status_code=500, content={"error": f"could not read timings: {e}"})
