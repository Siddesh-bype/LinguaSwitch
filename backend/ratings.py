"""Blind-rating vote store + shared tally helpers.

Two halves of the naturalness workflow:

1. Live demo votes: POST /api/ratings/vote stores one vote per
   (rater, question) — latest wins — in data/ratings.json (gitignored,
   survives restarts, atomic writes). GET /api/ratings/tally reports
   blind X/Y/same counts (unblinding needs rater_key.json, which must
   never reach raters, so the API stays blind by design).
2. Rater-packet verdict: scripts/tally_ratings.py maps responses.csv
   through rater_key.json to A/B and checks the acceptance test.

tally_choices() is shared by both so the counting rule is identical.
"""
import json
import threading
from pathlib import Path

CHOICES = ("X", "Y", "same")


def tally_choices(choices: list[str]) -> dict:
    counts = {c: 0 for c in CHOICES}
    for c in choices:
        if c in counts:
            counts[c] += 1
    return counts


def verdict(native: int, baseline: int) -> str:
    """Acceptance-test naturalness rule: majority of non-tie ratings."""
    if native > baseline:
        return "native"
    if baseline > native:
        return "baseline"
    return "tie"


class RatingsStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"votes": {}}

    def vote(self, rater: str, question: str, choice: str) -> dict:
        if choice not in CHOICES:
            raise ValueError(f"choice must be one of {CHOICES}")
        rater, question = rater.strip(), question.strip()
        if not rater or not question:
            raise ValueError("rater and question must not be empty")
        with self._lock:
            data = self._read()
            data.setdefault("votes", {})[f"{rater}\u0000{question}"] = {
                "rater": rater,
                "question": question,
                "choice": choice,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self.path)  # atomic: readers never see half a file
            return {"rater": rater, "question": question, "choice": choice}

    def tally(self) -> dict:
        with self._lock:
            votes = list(self._read().get("votes", {}).values())
        per_question: dict[str, dict] = {}
        for v in votes:
            per_question.setdefault(v["question"], []).append(v["choice"])
        return {
            "votes": len(votes),
            "raters": sorted({v["rater"] for v in votes}),
            "totals": tally_choices([v["choice"] for v in votes]),
            "per_question": {q: tally_choices(cs) for q, cs in sorted(per_question.items())},
        }

    def clear(self) -> int:
        with self._lock:
            data = self._read()
            n = len(data.get("votes", {}))
            self.path.write_text(json.dumps({"votes": {}}) + "\n", encoding="utf-8")
            return n
