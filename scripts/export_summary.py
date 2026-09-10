"""Export a summary of data/timings.jsonl for README / RIME_EVIDENCE.md.

Latest row per (sentence_id, path) wins (same rule as run_eval.py).
Writes summary.json next to timings.jsonl and prints a markdown table.

    py scripts/export_summary.py
    py scripts/export_summary.py --json out.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config  # noqa: E402

TIMINGS = config.DATA_DIR / "timings.jsonl"
DEFAULT_OUT = config.DATA_DIR / "summary.json"


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    if not TIMINGS.exists():
        sys.exit(f"No {TIMINGS} — run `py scripts/run_eval.py` first.")
    summary = summarize(load_latest(TIMINGS))
    Path(args.json).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    n = summary["n_sentences"]
    print("| sentence | A ttfa (ms) | A total (ms) | B ttfa (ms) | B total (ms) |")
    print("|---|---|---|---|---|")
    for row in summary["per_sentence"]:
        print(f"| {row['sentence_id']} | {row['a_ttfa_ms']} | {row['a_total_ms']} | "
              f"{row['b_ttfa_ms']} | {row['b_total_ms']} |")
    print(f"| **avg** | **{summary['avg_a_ttfa_ms']}** | **{summary['avg_a_total_ms']}** | "
          f"**{summary['avg_b_ttfa_ms']}** | **{summary['avg_b_total_ms']}** |")
    print(f"\nNative wins (total A<=B): {summary['native_wins']}/{n}. Wrote {args.json}.")


if __name__ == "__main__":
    main()
