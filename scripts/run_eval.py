"""Run the 10-sentence A/B eval: native Rime code-switching vs segment-and-route.

Path A: one rime.speak(text, DEFAULT_LANG) — native code-switching.
Path B: segment_timed(text) -> per-segment rime.speak (sequential by
default, --parallel fans out) -> concat_wav.

Clips   -> data/clips/s{id}_a.wav, s{id}_b.wav
Timings -> data/timings.jsonl (one row per path, appended)

    py scripts/run_eval.py
    py scripts/run_eval.py --ids 1,5,10
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import audio, config, parallel, rime  # noqa: E402
from backend.segmenter import segment_timed  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TIMINGS = config.DATA_DIR / "timings.jsonl"


def run_sentence(s: dict, use_parallel: bool = False) -> list[dict]:
    sid, text = s["id"], s["text"]
    rows = []

    # Path A: one native call
    out_a = rime.speak(text, config.DEFAULT_LANG)
    (config.CLIPS_DIR / f"s{sid}_a.wav").write_bytes(out_a["audio"])
    rows.append({
        "sentence_id": sid, "path": "a",
        "ttfa_ms": out_a["ttfa_ms"], "total_ms": out_a["total_ms"],
        "segment_ms": 0, "api_calls": 1, "segments": 1,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    })

    # Path B: segment -> per-segment calls (sequential by default,
    # --parallel fans out) -> concat
    segs, seg_ms = segment_timed(text)
    t0 = time.perf_counter()
    rendered = parallel.render_segments(segs, parallel=use_parallel)
    wall_ms = int((time.perf_counter() - t0) * 1000)
    wavs, seg_total, first_ttfa = [], 0, 0
    for out in rendered:
        if not wavs:
            first_ttfa = out["ttfa_ms"]
        wavs.append(out["audio"])
        seg_total += out["total_ms"]
    # Parallel wall time is the honest total (segments overlap); the
    # summed figure is kept for comparability with sequential runs.
    total_b = seg_ms + (wall_ms if use_parallel else seg_total)
    (config.CLIPS_DIR / f"s{sid}_b.wav").write_bytes(audio.concat_wav(wavs))
    rows.append({
        "sentence_id": sid, "path": "b",
        # TTFA for the whole path = segmentation + first segment's first byte
        "ttfa_ms": seg_ms + first_ttfa,
        "total_ms": total_b,
        "mode": "parallel" if use_parallel else "sequential",
        "segment_ms": seg_ms, "api_calls": len(segs) + 1, "segments": len(segs),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="comma-separated sentence ids to re-run, e.g. 1,5,10")
    ap.add_argument("--parallel", action="store_true",
                    help="fan out Path B per-segment calls concurrently "
                         "(rows are tagged mode=parallel; default is sequential)")
    args = ap.parse_args()

    sentences = json.loads((ROOT / "sentences.json").read_text(encoding="utf-8"))["sentences"]
    if args.ids:
        wanted = {int(x) for x in args.ids.split(",")}
        sentences = [s for s in sentences if s["id"] in wanted]
        missing = wanted - {s["id"] for s in sentences}
        if missing:
            sys.exit(f"Unknown sentence ids: {sorted(missing)}")

    config.CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    TIMINGS.parent.mkdir(parents=True, exist_ok=True)

    new_rows = []
    with TIMINGS.open("a", encoding="utf-8") as f:
        for s in sentences:
            try:
                rows = run_sentence(s, use_parallel=args.parallel)
            except Exception as e:  # noqa: BLE001 — eval reports raw failures, keeps going
                print(f"[s{s['id']}] FAILED: {type(e).__name__}: {e}")
                continue
            # capture first segment's ttfa (rows are built inside run_sentence)
            for row in rows:
                f.write(json.dumps(row) + "\n")
            new_rows.extend(rows)
            a, b = rows
            print(f"[s{s['id']}] A: ttfa {a['ttfa_ms']}ms total {a['total_ms']}ms | "
                  f"B: ttfa {b['ttfa_ms']}ms total {b['total_ms']}ms "
                  f"({b['segments']} segs, {b['segment_ms']}ms segmentation)")

    if not new_rows:
        sys.exit("No sentences completed — nothing to summarize.")

    # Summary over ALL recorded rows: latest row per (sentence_id, path) wins.
    latest = {}
    if TIMINGS.exists():
        for line in TIMINGS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                latest[(row["sentence_id"], row["path"])] = row

    print(f"\n{'id':>3} | {'A ttfa':>7} {'A total':>7} | {'B ttfa':>7} {'B total':>7} {'B seg':>6} | {'ttfa A-B':>8} {'total A-B':>9}")
    print("-" * 78)
    sums = {"a": [0, 0], "b": [0, 0]}
    counts = {"a": 0, "b": 0}
    ids = sorted({sid for sid, _ in latest})
    for sid in ids:
        a = latest.get((sid, "a"))
        b = latest.get((sid, "b"))
        if not (a and b):
            continue
        for p, row in (("a", a), ("b", b)):
            sums[p][0] += row["ttfa_ms"]
            sums[p][1] += row["total_ms"]
            counts[p] += 1
        print(f"{sid:>3} | {a['ttfa_ms']:>7} {a['total_ms']:>7} | "
              f"{b['ttfa_ms']:>7} {b['total_ms']:>7} {b['segment_ms']:>6} | "
              f"{a['ttfa_ms'] - b['ttfa_ms']:>8} {a['total_ms'] - b['total_ms']:>9}")
    if counts["a"] and counts["b"]:
        n = min(counts["a"], counts["b"])
        print("-" * 78)
        print(f"avg | {sums['a'][0] // n:>7} {sums['a'][1] // n:>7} | "
              f"{sums['b'][0] // n:>7} {sums['b'][1] // n:>7}          | "
              f"{(sums['a'][0] - sums['b'][0]) // n:>8} {(sums['a'][1] - sums['b'][1]) // n:>9}")
    print(f"\nRows appended to {TIMINGS}. Clips in {config.CLIPS_DIR}.")


if __name__ == "__main__":
    main()
