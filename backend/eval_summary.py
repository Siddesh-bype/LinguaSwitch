"""Eval rollup logic shared by scripts/export_summary.py and GET /api/eval/summary.

Rule (same as run_eval.py): latest row per (sentence_id, path) wins.
Pure functions over parsed rows — no I/O except load_latest(path).
"""
import json
from pathlib import Path

from . import config

TIMINGS = config.DATA_DIR / "timings.jsonl"


def load_latest(path: Path) -> dict:
    latest = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        latest[(row["sentence_id"], row["path"])] = row
    return latest


def summarize(latest: dict) -> dict:
    ids = sorted({sid for sid, _ in latest})
    per_sentence = []
    sums = {"a": [0, 0], "b": [0, 0]}
    counts = {"a": 0, "b": 0}
    wins_a = 0
    for sid in ids:
        a, b = latest.get((sid, "a")), latest.get((sid, "b"))
        if not (a and b):
            continue
        per_sentence.append({
            "sentence_id": sid,
            "a_ttfa_ms": a["ttfa_ms"], "a_total_ms": a["total_ms"],
            "b_ttfa_ms": b["ttfa_ms"], "b_total_ms": b["total_ms"],
            "b_segment_ms": b.get("segment_ms", 0), "b_segments": b.get("segments", 0),
            "delta_total_ms": a["total_ms"] - b["total_ms"],
        })
        for p, row in (("a", a), ("b", b)):
            sums[p][0] += row["ttfa_ms"]
            sums[p][1] += row["total_ms"]
            counts[p] += 1
        if a["total_ms"] <= b["total_ms"]:
            wins_a += 1
    n = len(per_sentence)
    return {
        "n_sentences": n,
        "avg_a_ttfa_ms": sums["a"][0] // n if n else 0,
        "avg_a_total_ms": sums["a"][1] // n if n else 0,
        "avg_b_ttfa_ms": sums["b"][0] // n if n else 0,
        "avg_b_total_ms": sums["b"][1] // n if n else 0,
        "native_wins": wins_a,
        "per_sentence": per_sentence,
    }
