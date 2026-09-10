# RIME_EVIDENCE.md — Evidence for the DataForge claim

## Claim (falsifiable)

> Rime's native code-switching (single unified-model call) renders
> mid-sentence Hinglish more naturally, and no slower, than a
> segment-and-route baseline (Groq LLM tags language segments ->
> per-segment Rime calls, one voice per language -> concatenate).

"Better" means: (1) blind human raters prefer the native render for naturalness,
and (2) the native render is not slower end-to-end.

The claim is about the *mechanism* (native single call vs route-and-concat),
not a model version: the exact Rime model/voices/lang codes/endpoint used are
pinned in README Providers and verified by `scripts/smoke_test.py`.

## Acceptance test

The claim is TRUE only if **both** hold:

- **Naturalness:** in blind pairwise ratings, native (Path A) is chosen over the
  baseline (Path B) by a majority of ratings (excluding "same").
- **Latency:** Path A's mean total time is less than or equal to Path B's mean
  total time across the 10 sentences.

If **either** fails, the claim is **false** — say so plainly; do not soften it.

## Method

Two rendering paths over the same 10 Hinglish sentences (`sentences.json`,
mix of customer-support and everyday phrasing, 1–3 language switches each):

- **Path A (native):** one Rime call per sentence — `rime.speak(text, DEFAULT_LANG)`
  with the default Hindi voice and no pre-segmentation. Rime decides
  code-switching itself.
- **Path B (segment-and-route baseline):** Groq router model
  (`openai/gpt-oss-20b`, MoE) segments the sentence into `hin`/`eng` runs
  (`backend/segmenter.py`), then one Rime call per segment (sequential, with
  the per-language voice from `config.SPEAKER_MAP`), then WAV concatenation
  (`backend/audio.py`). The voice swap at every language boundary is structural
  to this design — a Rime voice serves one language — which is exactly the seam
  under test.

Measurement procedure:

1. `py scripts/run_eval.py` — renders both paths for all 10 sentences, saves
   clips to `data/clips/s{id}_a.wav` / `s{id}_b.wav`, appends timings
   (ttfa, total, segmentation ms, api calls) to `data/timings.jsonl`.
2. `py scripts/make_rater_packet.py` — builds a blind packet
   (`rater_packet/`): A/B assignment to X/Y randomized per question, mapping
   kept in gitignored `rater_key.json`. Raters listen to both and pick X, Y,
   or same; answers go in `responses.csv`.
3. `py scripts/bonus_segmentation.py` — exploratory: segmentation accuracy
   (exact-match and word-level language assignment) of the router model, a
   dense model, and (optional) an OpenRouter reasoning model against
   hand-labeled ground truth.

## Results

### Latency (per sentence, A vs B)

| sentence | A ttfa (ms) | A total (ms) | B ttfa (ms) | B total (ms) | B segment (ms) | B segments |
|---|---|---|---|---|---|---|
| 1 | 1399 | 2303 | 3062 | 5754 | 1720 | 2 |
| 2 | 1130 | 2069 | 2352 | 6031 | 1100 | 3 |
| 3 | 1433 | 2443 | 2315 | 3356 | 1116 | 1 |
| 4 | 1295 | 2762 | 2191 | 5056 | 1011 | 2 |
| 5 | 1108 | 2259 | 2387 | 4704 | 1189 | 2 |
| 6 | 1142 | 2223 | 2813 | 6521 | 1625 | 3 |
| 7 | 1303 | 2472 | 2336 | 5037 | 1103 | 2 |
| 8 | 1122 | 2382 | 2653 | 6740 | 1394 | 3 |
| 9 | 1219 | 1964 | 2441 | 4800 | 1266 | 2 |
| 10 | 1197 | 3618 | 2666 | 7238 | 1482 | 3 |
| **avg** | **1234** | **2449** | **2521** | **5523** | **1271** | **2.3** |

Measured 2026-09-10 (`data/timings.jsonl`). Latency half of the acceptance
test holds: Path A mean total ≤ Path B mean total on all 10 sentences.

### Rater preferences (raw counts)

| rater | A (native) | B (baseline) | same |
|---|---|---|---|
|  |  |  |  |
| **total** |  |  |  |

### Bonus: segmentation accuracy (exploratory)

| model | correct (of N) | word-level accuracy |
|---|---|---|
| Groq openai/gpt-oss-20b (router) |  |  |
| Groq openai/gpt-oss-120b (second, small-vs-large) |  |  |
| OpenRouter (bonus) |  |  |

## Limitations

- **Small sample:** 10 sentences, a handful of raters. Directional signal, not
  statistical proof.
- **Raters not fully blinded:** the author team knows the hypothesis; only clip
  identity was blinded (X/Y randomization).
- **Sequential baseline calls:** Path B's per-segment Rime calls are sequential
  (worst case for latency); parallel calls would narrow the gap. This favors
  Path A on latency — acknowledged.
- **API-call counting:** A = 1 Rime call always; B = one Rime call per language
  segment + 1 Groq router call (`api_calls` in code counts both).
- **Bonus is exploratory:** segmentation accuracy runs on only the sentences
  with hand-labeled ground truth, with no prompt tuning per model.
- Single provider account, single region, one session — network variance is
  not controlled for.

## Reproduce

```bash
py scripts/smoke_test.py            # Day 0 gate: verify Rime endpoint/model
py scripts/run_eval.py              # A/B latency + clips -> data/
py scripts/make_rater_packet.py     # blind packet -> rater_packet/
# collect responses.csv from raters, then:
py scripts/bonus_segmentation.py    # exploratory segmentation table
py scripts/bonus_segmentation.py --list   # per-sentence debug output
```

Timings for every run are appended to `data/timings.jsonl` (re-runs add rows;
the summary table uses the latest row per sentence/path).
