"""Unblind and tally rater-packet responses (the naturalness verdict).

Reads rater_packet/responses.csv (choice = X | Y | same per question)
plus the gitignored rater_packet/rater_key.json (X/Y -> A/B mapping from
scripts/make_rater_packet.py), maps every vote to native/baseline/same,
and checks the acceptance-test rule from RIME_EVIDENCE.md: native wins
iff chosen by a majority of ratings excluding "same".

    py scripts/tally_ratings.py
    py scripts/tally_ratings.py --packet path/to/rater_packet

Counting rule is backend/ratings.tally_choices (shared with the live
vote API) so both paths agree by construction.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.ratings import tally_choices, verdict  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def unblind(responses_path: Path, key_path: Path) -> tuple[list[str], list[str]]:
    """Return (ab_votes, errors): each vote mapped to native/baseline/same."""
    key = json.loads(key_path.read_text(encoding="utf-8"))
    votes, errors = [], []
    with responses_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            q, choice = (row.get("question") or "").strip(), (row.get("choice") or "").strip()
            mapping = key.get(q)
            if mapping is None:
                errors.append(f"{q}: unknown question (not in rater_key.json)")
                continue
            if choice == "same":
                votes.append("same")
            elif choice in ("X", "Y"):
                votes.append("native" if mapping.get(choice.lower()) == "a" else "baseline")
            else:
                errors.append(f"{q}: bad choice {choice!r} (want X | Y | same)")
    return votes, errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", default=str(ROOT / "rater_packet"))
    args = ap.parse_args()
    packet = Path(args.packet)
    responses, key = packet / "responses.csv", packet / "rater_key.json"
    if not responses.exists():
        sys.exit(f"No {responses} — run `py scripts/make_rater_packet.py` and collect ratings first.")
    if not key.exists():
        sys.exit(f"No {key} — it is created alongside the packet (gitignored, keep it).")

    votes, errors = unblind(responses, key)
    # Count through the shared blind-label counter, then rename for display.
    blind = ["X" if v == "native" else "Y" if v == "baseline" else "same" for v in votes]
    blind_counts = tally_choices(blind)
    counts = {"native": blind_counts["X"], "baseline": blind_counts["Y"], "same": blind_counts["same"]}

    n = len(votes)
    decided = counts["native"] + counts["baseline"]
    print(f"votes: {n} ({decided} decisive, {counts['same']} same)")
    print(f"native (A):   {counts['native']}")
    print(f"baseline (B): {counts['baseline']}")
    print(f"same:         {counts['same']}")
    for e in errors:
        print(f"WARNING skipped: {e}")
    if decided == 0:
        print("\nNo decisive votes yet — acceptance test needs ratings first.")
        return
    w = verdict(counts["native"], counts["baseline"])
    print(f"\nNaturalness verdict: {w} "
          f"({max(counts['native'], counts['baseline'])}/{decided} decisive). "
          + ("Claim's naturalness half HOLDS." if w == "native" else
             "Claim's naturalness half FAILS — say so plainly (RIME_EVIDENCE.md)." if w == "baseline" else
             "Tie — not a majority either way."))


if __name__ == "__main__":
    main()
