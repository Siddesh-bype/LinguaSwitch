"""Build a blind rater packet from data/clips/.

For each sentence id, copies s{id}_a.wav and s{id}_b.wav to rater_packet/
as q{id}_x.wav and q{id}_y.wav, with X/Y assignment randomized per sentence.
The mapping is logged to rater_packet/rater_key.json (gitignored) so results
can be unblinded later.

    py scripts/make_rater_packet.py
"""
import json
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIPS = ROOT / "data" / "clips"
PACKET = ROOT / "rater_packet"

INSTRUCTIONS = """# Rater Instructions

You will rate pairs of audio clips. Each question `qN` has two clips: **X** and **Y**.

These are text-to-speech renders of the same Hinglish (Hindi-English mix)
sentence — e.g. *"Mera order kahan hai, can you check the status please?"*

For each question:

1. Listen to `qN_x.wav`, then `qN_y.wav` (order within the pair doesn't matter).
2. Ask yourself: **which one sounds more natural?** — smoother switches between
   Hindi and English mid-sentence, more even pacing, fewer awkward pauses or
   tonal jumps at language boundaries.
3. Write your answer in `responses.csv`: `X`, `Y`, or `same` if you genuinely
   can't tell them apart.

There are no trick questions and no expected answers. If a clip is broken or
silent, still pick the one that is better overall.

Rows look like:

    rater,question,choice
    yourname,q1,X
    yourname,q2,same
"""


def main() -> None:
    sentences = json.loads((ROOT / "sentences.json").read_text(encoding="utf-8"))["sentences"]
    ids = [s["id"] for s in sentences]

    missing = [
        f"s{i}_{p}.wav" for i in ids for p in ("a", "b")
        if not (CLIPS / f"s{i}_{p}.wav").exists()
    ]
    if missing:
        sys.exit(f"Missing clips (run `py scripts/run_eval.py` first): {', '.join(missing)}")

    PACKET.mkdir(parents=True, exist_ok=True)
    # stale packet files from a previous build would leak old assignments
    for old in PACKET.glob("q*_*.wav"):
        old.unlink()

    key = {}
    for i in ids:
        a_is_x = random.random() < 0.5
        shutil.copyfile(CLIPS / f"s{i}_a.wav", PACKET / f"q{i}_{'x' if a_is_x else 'y'}.wav")
        shutil.copyfile(CLIPS / f"s{i}_b.wav", PACKET / f"q{i}_{'y' if a_is_x else 'x'}.wav")
        key[f"q{i}"] = {"x": "a" if a_is_x else "b", "y": "b" if a_is_x else "a"}

    (PACKET / "rater_key.json").write_text(
        json.dumps(key, indent=2) + "\n", encoding="utf-8"
    )
    (PACKET / "INSTRUCTIONS.md").write_text(INSTRUCTIONS, encoding="utf-8")
    (PACKET / "responses.csv").write_text("rater,question,choice\n", encoding="utf-8")

    print(f"Packet written to {PACKET} ({len(ids)} questions).")
    print(f"Blinding key: {PACKET / 'rater_key.json'} (gitignored — do not show raters).")
    print(f"Collect answers in {PACKET / 'responses.csv'} (choice = X | Y | same).")


if __name__ == "__main__":
    main()
