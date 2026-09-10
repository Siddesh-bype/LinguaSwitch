"""Bonus (exploratory): segmentation accuracy — which LLM segments best?

For every sentence WITH non-null ground_truth, runs segmentation via:
  (a) Groq router model  (config.GROQ_ROUTER_MODEL, openai/gpt-oss-20b)
  (b) Groq second model  (config.GROQ_SECOND_MODEL, openai/gpt-oss-120b) —
      small-vs-large comparison, NOT MoE-vs-dense
  (c) OpenRouter model   (only if OPENROUTER_API_KEY is set) — via the `openai`
      package pointed at OpenRouter; <think>...</think> blocks stripped.

Prints a markdown table (paste into RIME_EVIDENCE.md):
  model | correct (of N) | word-level accuracy

    py scripts/bonus_segmentation.py
    py scripts/bonus_segmentation.py --list
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import config  # noqa: E402
from backend.segmenter import _messages, _parse, segment  # noqa: E402


def norm(text: str) -> str:
    return " ".join(text.split())


def segment_openrouter(text: str) -> list[dict]:
    from openai import OpenAI  # in requirements.txt; imported lazily (flag-gated)

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=config.OPENROUTER_API_KEY)
    last_raw = ""
    for _ in range(2):  # one retry on unparseable output, mirrors backend.segmenter
        resp = client.chat.completions.create(
            model=config.OPENROUTER_MODEL,
            messages=_messages(text),
        )
        raw = resp.choices[0].message.content or ""
        # reasoning models (deepseek-r1) emit <think>...</think> before the answer
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        last_raw = raw
        try:
            return _parse(raw)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    raise RuntimeError(f"openrouter segmenter: unparseable output: {last_raw!r}")


def words_with_lang(segs: list[dict]) -> list[tuple[str, str]]:
    return [(s["lang"], w) for s in segs for w in s["text"].split()]


def score(pred: list[dict], truth: list[dict]) -> tuple[bool, float]:
    """(exact match, word-level lang accuracy)."""
    p = [(s["lang"], norm(s["text"])) for s in pred]
    t = [(s["lang"], norm(s["text"])) for s in truth]
    exact = p == t

    pw, tw = words_with_lang(pred), words_with_lang(truth)
    if not tw:
        return exact, 0.0
    # ponytail: mismatched word counts use zip length over truth denominator —
    # exploratory metric, fine for a 10-sentence sanity signal
    hits = sum(1 for (pl, _), (tl, _) in zip(pw, tw) if pl == tl)
    return exact, hits / len(tw)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="print per-sentence comparisons")
    args = ap.parse_args()

    sentences = json.loads((ROOT / "sentences.json").read_text(encoding="utf-8"))["sentences"]
    labeled = [s for s in sentences if s["ground_truth"]]
    if not labeled:
        sys.exit("Fill ground_truth in sentences.json first (user task).")

    methods = [
        (f"Groq {config.GROQ_ROUTER_MODEL}", lambda t: segment(t, config.GROQ_ROUTER_MODEL)),
        (f"Groq {config.GROQ_SECOND_MODEL}", lambda t: segment(t, config.GROQ_SECOND_MODEL)),
    ]
    if config.OPENROUTER_API_KEY:
        methods.append((f"OpenRouter {config.OPENROUTER_MODEL}", segment_openrouter))
    else:
        print("(OPENROUTER_API_KEY not set — skipping OpenRouter comparison)\n")

    results = {}  # model -> list of (sentence, pred, exact, word_acc, error)
    for name, fn in methods:
        results[name] = []
        for s in labeled:
            try:
                pred = fn(s["text"])
                exact, wacc = score(pred, s["ground_truth"])
                results[name].append((s, pred, exact, wacc, None))
            except Exception as e:  # noqa: BLE001 — one bad call shouldn't kill the table
                results[name].append((s, [], False, 0.0, f"{type(e).__name__}: {e}"))

    n = len(labeled)
    print("| model | correct (of " f"{n}" ") | word-level accuracy |")
    print("|---|---|---|")
    for name, rows in results.items():
        correct = sum(1 for r in rows if r[2])
        wacc = sum(r[3] for r in rows) / len(rows) if rows else 0.0
        print(f"| {name} | {correct}/{n} | {wacc:.1%} |")

    print("\nNOTE: exploratory / small-sample (n=%d). Not a benchmark — a sanity signal." % n)

    if args.list:
        for name, rows in results.items():
            print(f"\n=== {name} ===")
            for s, pred, exact, wacc, err in rows:
                print(f"\n[s{s['id']}] {'EXACT' if exact else 'miss'} (word-acc {wacc:.0%})")
                if err:
                    print(f"  ERROR: {err}")
                print(f"  truth: {[(g['lang'], g['text']) for g in s['ground_truth']]}")
                print(f"  pred : {[(p['lang'], p['text']) for p in pred]}")


if __name__ == "__main__":
    main()
