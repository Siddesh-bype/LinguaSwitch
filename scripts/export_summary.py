"""Export a summary of data/timings.jsonl for README / RIME_EVIDENCE.md.

Latest row per (sentence_id, path) wins (same rule as run_eval.py).
Writes summary.json next to timings.jsonl and prints a markdown table.
Rollup logic lives in backend/eval_summary.py (shared with the
GET /api/eval/summary dashboard endpoint); this file is the CLI.

    py scripts/export_summary.py
    py scripts/export_summary.py --json out.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config  # noqa: E402
from backend.eval_summary import TIMINGS, load_latest, summarize  # noqa: E402

DEFAULT_OUT = config.DATA_DIR / "summary.json"


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
