"""Switch-Boundary Discontinuity Score (SBDS): concat-seam proxy for Path A vs B clips.

Compares Rime native Hinglish TTS (Path A: ``data/clips/s{id}_a.wav``) against the
segment-and-route baseline (Path B: ``data/clips/s{id}_b.wav``) on purely
acoustic seam artefacts: long inter-word silences, pitch jumps, spectral-flux
bursts, and energy steps at silence boundaries.

Weights below are PRE-REGISTERED constants decided BEFORE seeing any data
(they are literature-scale priors, not fitted: silence gaps dominate perceived
concat seams, pitch jumps are the next most salient, flux bursts moderate,
energy steps smallest). They must not be tuned on the eval clips without
re-registering them.

Honest framing / limits:
  - Whole-utterance seam PROXY only. There is no forced alignment here, so
    boundaries are silence-inferred (librosa.effects.split), NOT
    switch-certified language-switch points.
  - A native Path A clip can also contain natural pauses; a high SBDS on A
    does not prove a code-switch glitch, only seam-like acoustics.
  - Pairs with Path B segmentation logs (segment boundaries + timings from
    scripts/run_eval.py) for true switch-point analysis as future work.

Usage:
    py scripts/sbds.py
    py scripts/sbds.py --ids 1,5,10      # same --ids convention as run_eval.py

Reads only local WAVs; makes no network/API calls.
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np

try:
    import librosa
except ImportError as _librosa_err:  # handled gracefully in main()
    librosa = None
    _LIBROSA_ERR = _librosa_err
else:
    _LIBROSA_ERR = None

# ---------------------------------------------------------------------------
# PRE-REGISTERED fixed weights (decided before seeing data — do not fit them).
# SBDS = W_SILENCE * n_long_gaps
#      + W_PITCH   * mean_pitch_jump_st
#      + W_FLUX    * seam_flux_ratio
#      + W_ENERGY  * max_energy_step_db
# ---------------------------------------------------------------------------
W_SILENCE = 1.0   # per long gap (>250 ms, concat-seam candidate)
W_PITCH = 1.0     # per semitone of mean pitch jump at boundaries
W_FLUX = 0.5      # per unit of seam-to-background flux ratio
W_ENERGY = 0.25   # per dB of max RMS energy step at boundaries

SR = 16000
TOP_DB = 30           # librosa.effects.split silence threshold
MIN_GAP_MS = 80.0     # gaps shorter than this are ignored (coarticulation)
LONG_GAP_MS = 250.0   # gaps above this count as concat-seam candidates
PITCH_WIN_MS = 150.0  # median-f0 window either side of a boundary
FLUX_WIN_MS = 100.0   # half-window around a gap centre for peak flux
FMIN_HZ = 50.0
FMAX_HZ = 500.0
_EPS = 1e-8

ROOT = Path(__file__).resolve().parent.parent
CLIPS_DIR = ROOT / "data" / "clips"
CLIP_RE = re.compile(r"^s(\d+)_(a|b)\.wav$")


def parse_ids(raw):
    """Mirror scripts/run_eval.py: comma-separated ids -> set of ints (or None)."""
    if not raw:
        return None
    return {int(x) for x in raw.split(",") if x.strip()}


def find_pairs(wanted):
    """Return {sid: {"a": Path, "b": Path}} for complete A/B pairs on disk."""
    pairs = {}
    if not CLIPS_DIR.is_dir():
        return pairs
    for p in sorted(CLIPS_DIR.glob("s*_[ab].wav")):
        m = CLIP_RE.match(p.name)
        if not m:
            continue
        sid, path = int(m.group(1)), m.group(2)
        if wanted is not None and sid not in wanted:
            continue
        pairs.setdefault(sid, {})[path] = p
    return {sid: v for sid, v in pairs.items() if "a" in v and "b" in v}


def analyze_clip(path):
    """Compute seam-proxy metrics + SBDS for one clip. Returns a dict."""
    y, _ = librosa.load(str(path), sr=SR, mono=True)
    n = len(y)
    if n == 0:
        raise ValueError(f"empty audio: {path}")
    dur_s = n / SR

    # --- Silence gaps from non-silent intervals ---------------------------
    intervals = librosa.effects.split(y, top_db=TOP_DB,
                                      frame_length=2048, hop_length=512)
    gaps = []  # (gap_start_samp, gap_end_samp, gap_ms)
    for (prev_end, next_start) in zip(intervals[:-1, 1], intervals[1:, 0]):
        gap_ms = (next_start - prev_end) / SR * 1000.0
        if gap_ms >= MIN_GAP_MS:
            gaps.append((int(prev_end), int(next_start), float(gap_ms)))
    n_long = sum(1 for _, _, ms in gaps if ms > LONG_GAP_MS)
    max_gap_ms = max((ms for _, _, ms in gaps), default=0.0)
    sil_ratio = 1.0 - float(np.sum(intervals[:, 1] - intervals[:, 0])) / n

    # --- Pitch continuity (pyin f0, median of 150 ms windows either side) --
    pitch_jumps = []
    try:
        f0, _, _ = librosa.pyin(y, fmin=FMIN_HZ, fmax=FMAX_HZ, sr=SR)
        f0_times = librosa.times_like(f0, sr=SR)  # default hop 512 = pyin default
        win_s = PITCH_WIN_MS / 1000.0
        for gs, ge, _ in gaps:
            gs_t, ge_t = gs / SR, ge / SR
            before = f0[(f0_times >= gs_t - win_s) & (f0_times < gs_t)]
            after = f0[(f0_times > ge_t) & (f0_times <= ge_t + win_s)]
            before = before[np.isfinite(before)]
            after = after[np.isfinite(after)]
            if len(before) == 0 or len(after) == 0:
                continue  # unvoiced side: no evidence, skip boundary
            fb, fa = float(np.median(before)), float(np.median(after))
            if fb > 0 and fa > 0:
                pitch_jumps.append(abs(12.0 * np.log2(fa / fb)))
    except Exception:  # pyin may fail on Degenerate input; treat as no evidence
        pitch_jumps = []
    pitch_mean = float(np.mean(pitch_jumps)) if pitch_jumps else 0.0
    pitch_max = float(np.max(pitch_jumps)) if pitch_jumps else 0.0

    # --- Spectral flux: peak near boundaries vs global median --------------
    env = librosa.onset.onset_strength(y=y, sr=SR)  # default hop_length=512
    flux_mean, flux_var = float(np.mean(env)), float(np.var(env))
    global_med = float(np.median(env))
    if gaps:
        env_times = librosa.frames_to_time(np.arange(len(env)), sr=SR)
        half = FLUX_WIN_MS / 1000.0
        peak = max(
            float(np.max(env[np.abs(env_times - ((gs + ge) / 2 / SR)) <= half]))
            for gs, ge, _ in gaps
        )
        flux_ratio = peak / (global_med + _EPS)
    else:
        flux_ratio = 1.0  # neutral: no boundaries, no seam evidence

    # --- Energy step: max dB RMS difference across a boundary --------------
    win_n = int(PITCH_WIN_MS / 1000.0 * SR)
    energy_steps = []
    for gs, ge, _ in gaps:
        xb = y[max(0, gs - win_n):gs]
        xa = y[ge:ge + win_n]
        if len(xb) == 0 or len(xa) == 0:
            continue
        rb = float(np.sqrt(np.mean(xb ** 2) + _EPS))
        ra = float(np.sqrt(np.mean(xa ** 2) + _EPS))
        energy_steps.append(abs(20.0 * np.log10(ra / rb)))
    energy_max = float(np.max(energy_steps)) if energy_steps else 0.0

    sbds = (W_SILENCE * n_long + W_PITCH * pitch_mean
            + W_FLUX * flux_ratio + W_ENERGY * energy_max)
    return {
        "gaps": len(gaps), "n_long": n_long, "max_gap_ms": max_gap_ms,
        "sil_ratio": sil_ratio, "pitch_mean_st": pitch_mean,
        "pitch_max_st": pitch_max, "flux_mean": flux_mean,
        "flux_var": flux_var, "flux_ratio": flux_ratio,
        "energy_max_db": energy_max, "sbds": sbds,
    }


def main():
    ap = argparse.ArgumentParser(
        description="Switch-Boundary Discontinuity Score for A/B TTS clips.")
    ap.add_argument("--ids",
                    help="comma-separated sentence ids to score, e.g. 1,5,10")
    args = ap.parse_args()

    wanted = parse_ids(args.ids)
    pairs = find_pairs(wanted)

    if not pairs:
        where = str(CLIPS_DIR)
        hint = ("Run `py scripts/run_eval.py%s` first to generate clips, "
                "then re-run `py scripts/sbds.py%s`.")
        scope = f" --ids {args.ids}" if args.ids else ""
        sys.exit(f"[sbds] No complete A/B clip pairs found in {where} "
                 f"(looked for s{{id}}_a.wav + s{{id}}_b.wav"
                 f"{f' with --ids {args.ids}' if args.ids else ''}). "
                 + hint % (scope, scope))

    if librosa is None:
        sys.exit(f"[sbds] ERROR: librosa is not installed ({_LIBROSA_ERR}). "
                 "Install it with `pip install librosa` (see requirements.txt) "
                 "and re-run `py scripts/sbds.py`. No clips were analysed.")

    print("SBDS weights (PRE-REGISTERED, fixed before seeing data):")
    print(f"  W_SILENCE={W_SILENCE} per long gap (>{LONG_GAP_MS:.0f}ms), "
          f"W_PITCH={W_PITCH} per semitone mean jump, "
          f"W_FLUX={W_FLUX} per seam-ratio unit, "
          f"W_ENERGY={W_ENERGY} per dB max step")
    print(f"  SBDS = {W_SILENCE}*n_long + {W_PITCH}*pitch_mean_st + "
          f"{W_FLUX}*flux_ratio + {W_ENERGY}*energy_max_db")
    print(f"  (silence: top_db={TOP_DB}, min gap {MIN_GAP_MS:.0f}ms; "
          f"windows: pitch/energy {PITCH_WIN_MS:.0f}ms, flux ±{FLUX_WIN_MS:.0f}ms)"
          f"  [higher SBDS = more seam-like discontinuity]")

    header = (f"\n{'sid':>4} {'path':>4} | {'gaps':>4} {'n_long':>6} "
              f"{'max_gap_ms':>10} {'sil_ratio':>9} | {'pitch_mean':>10} "
              f"{'pitch_max':>9} | {'flux_ratio':>10} | {'energy_db':>9} | "
              f"{'SBDS':>6}")
    print(header)
    print("-" * len(header))

    results = {}
    for sid in sorted(pairs):
        for tag in ("a", "b"):
            try:
                m = analyze_clip(pairs[sid][tag])
            except Exception as e:  # noqa: BLE001 — report per-clip, keep going
                print(f"{sid:>4} {tag:>4} | FAILED: {type(e).__name__}: {e}")
                m = None
            results[(sid, tag)] = m
            if m is not None:
                print(f"{sid:>4} {tag:>4} | {m['gaps']:>4} {m['n_long']:>6} "
                      f"{m['max_gap_ms']:>10.0f} {m['sil_ratio']:>9.3f} | "
                      f"{m['pitch_mean_st']:>10.2f} {m['pitch_max_st']:>9.2f} | "
                      f"{m['flux_ratio']:>10.2f} | {m['energy_max_db']:>9.2f} | "
                      f"{m['sbds']:>6.2f}")

    # Averages over sentences with BOTH sides scored + deltas (B - A).
    keys = ("n_long", "max_gap_ms", "pitch_mean_st", "flux_ratio",
            "energy_max_db", "sbds")
    agg = {"a": {k: [] for k in keys}, "b": {k: [] for k in keys}}
    for sid in sorted(pairs):
        ma, mb = results.get((sid, "a")), results.get((sid, "b"))
        if ma is None or mb is None:
            print(f"[s{sid}] skipped in averages (one side failed to score).")
            continue
        for k in keys:
            agg["a"][k].append(ma[k])
            agg["b"][k].append(mb[k])

    n = min(len(agg["a"]["sbds"]), len(agg["b"]["sbds"]))
    if n == 0:
        sys.exit("[sbds] No sentences had both sides scored — nothing to average.")
    print("-" * len(header))
    for tag, label in (("a", "avg A (native)"), ("b", "avg B (concat)")):
        vals = {k: float(np.mean(agg[tag][k])) for k in keys}
        print(f"{label:>18} | {vals['n_long']:>10.2f} "
              f"{vals['max_gap_ms']:>10.0f} {'':>9} | "
              f"{vals['pitch_mean_st']:>10.2f} {'':>9} | "
              f"{vals['flux_ratio']:>10.2f} | {vals['energy_max_db']:>9.2f} | "
              f"{vals['sbds']:>6.2f}   (n={n})")
    d = {k: float(np.mean(agg["b"][k]) - np.mean(agg["a"][k])) for k in keys}
    print(f"{'delta B-A':>18} | {d['n_long']:>+10.2f} "
          f"{d['max_gap_ms']:>+10.0f} {'':>9} | "
          f"{d['pitch_mean_st']:>+10.2f} {'':>9} | "
          f"{d['flux_ratio']:>+10.2f} | {d['energy_max_db']:>+9.2f} | "
          f"{d['sbds']:>+6.2f}")
    print("\nΔ = B − A; positive Δ means Path B (concat) shows more "
          "seam-like discontinuity than Path A (native).")


if __name__ == "__main__":
    main()
