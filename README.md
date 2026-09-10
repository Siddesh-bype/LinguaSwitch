# LinguaSwitch — does native code-switching beat segment-and-route for Hinglish voice?

![Python 3.13](https://img.shields.io/badge/python-3.13-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi)
![Next.js](https://img.shields.io/badge/Next.js-000000?logo=nextdotjs)
![Rime Coda](https://img.shields.io/badge/Rime-Coda-7c3aed)
![Groq](https://img.shields.io/badge/Groq-gpt--oss--20b-ff4d00)

> **30-second pitch:** Indians talk to voice assistants in Hinglish — Hindi and English *inside one sentence*. Most TTS pipelines either force one language or swap voices mid-sentence and stitch the audio. LinguaSwitch tests the alternative: one native code-switched call (Rime Coda) against the stitch-together baseline, on the same 10 sentences, with blind human ratings and measured latency. **Result so far: native is ≈2.3× faster end-to-end; the naturalness verdict awaits blind raters.**

![Architecture](assets/architecture.svg)

## A vs B on the same 10 sentences

| | Path A — native | Path B — segment-and-route |
|---|---|---|
| What happens | 1 Rime Coda call, model code-switches itself | Groq LLM tags `hin`/`eng` runs → 1 Rime call per run (own voice each) → WAV concat |
| API calls / sentence | 1 | segments + 1 router call (avg 3.3) |
| Avg TTFA | **1234 ms** | 2521 ms |
| Avg total | **2449 ms** | 5523 ms |
| Wins (of 10, latency) | **10** | 0 |

![Measured eval output](assets/terminal.svg)

*Both SVGs are rendered from real measured output (`data/timings.jsonl`, 2026-09-10) — no mock numbers anywhere in this repo.*

## The demo UI (real captures)

Pick a sentence (or type your own Hinglish), generate each path, play both, compare latency side by side.

| Before — idle | After — both paths generated |
|---|---|
| ![UI idle](assets/ui-idle.png) | ![UI with results](assets/ui-results.png) |
| "Press a button to generate." | Live run: A = 1 call / 2209 ms total · B = 3 calls / 5316 ms total, per-language speakers shown as tags |

*Captured with headless Chromium against the live backend + frontend. Numbers vary run to run with network; the direction (A faster, fewer calls) held on all 10 eval sentences.*

## How it works (request flow)

1. **Input** — preset sentence from `sentences.json` or free text. No STT: the research question lives on the output side.
2. **Path A (native)** — `rime.speak(text, "hin")`: one `POST /v1/rime-tts` (`modelId: coda`, voice `nadi`). Rime code-switches internally.
3. **Path B (baseline)** — `segmenter` (Groq `gpt-oss-20b`, few-shot JSON) splits the text into `hin`/`eng` runs → one Rime call per run, swapping voice per language (`nadi`/`astra` — a Rime voice serves exactly one language, so the voice swap is structural) → stdlib-`wave` concat. Rime streams placeholder WAV headers (`nframes=INT32_MAX`); `audio.py` rebuilds clean headers from actual bytes.
4. **Compare** — TTFA/total/API-calls per path, audio players side by side, segment tags showing router decisions.

## Repo map

```
backend/        FastAPI: rime.py (sole Rime call site), segmenter.py (Groq router),
                audio.py (WAV concat), routes.py (native/baseline/sentences),
                agent_graph.py (LangGraph agent, both paths), agent_routes.py,
                streaming.py (WS /ws3 bridge), config.py (env, single source of truth)
frontend/       Next.js A/B UI (this page's screenshots)
scripts/        smoke_test.py (Day 0 gate) · run_eval.py (A/B + timings.jsonl)
                make_rater_packet.py (blind X/Y packets) · bonus_segmentation.py
                sbds.py (objective seam metric, librosa)
sentences.json  10-sentence test set (customer-support/everyday, 1–3 switches each)
assets/         architecture.svg · terminal.svg · ui-idle.png · ui-results.png
RIME_EVIDENCE.md  falsifiable claim + acceptance test + measured tables
```

## Verification log (this machine)

| Check | Result |
|---|---|
| `smoke_test.py` (Rime eng/hin/mixed) | 3/3 valid WAV, TTFA ~1.1–1.4 s |
| Groq router probe (`gpt-oss-20b`) | correct `hin`/`eng` split, ~1.5 s |
| `run_eval.py` full 10-sentence A/B | 10/10 both paths (after fixing placeholder-header concat bug) |
| `audio.py` self-check | pass (incl. placeholder-header regression case) |
| `tsc --noEmit` (frontend) | pass |
| Live app import, 4 routes | pass |
| `sbds.py` without librosa | clean "not installed" message, exit 1 |

## Test sentence set

Mix of customer-support and everyday phrasing, each with ≥1 mid-sentence switch; #10 is the 3-switch stress case. Full texts in `sentences.json`; `ground_truth` hand-labels (segmentation answer key) are filled by the team before running `bonus_segmentation.py`.

## Roadmap to submission

- [x] Provider access + corrected API shapes (Coda, `/v1/rime-tts`, current Groq IDs)
- [x] Both paths + eval harness + measured latency (A wins 10/10)
- [ ] Hand-label `ground_truth` (native-speaker task)
- [ ] Blind ratings from 3–5 Hindi/English speakers (`make_rater_packet.py` builds the packet)
- [ ] `pip install librosa` → SBDS seam numbers → `RIME_EVIDENCE.md`
- [ ] Record 4–5 min demo (script outline in the original plan: problem → native → baseline → stress → numbers → provider disclosure)

## Quickstart (3 steps)

```bash
pip install -r requirements.txt
copy .env.example .env   # fill in RIME_API_KEY + GROQ_API_KEY
py scripts/smoke_test.py # Day 0 gate: confirms model/voices/endpoint live
```

```bash
py scripts/run_eval.py            # A/B latency + clips -> data/
py scripts/make_rater_packet.py   # blind packet -> rater_packet/
```

```bash
uvicorn backend.main:app --port 8000   # terminal 1
cd frontend && npm install && npm run dev   # terminal 2 -> http://localhost:3000
```

## Claim under test

> Rime's native code-switching (single unified-model call) renders mid-sentence Hinglish more naturally, **and** no slower, than segment-and-route.

"Better" = blind-rater majority **plus** mean total time ≤ baseline. If either fails, the claim is false — see [`RIME_EVIDENCE.md`](RIME_EVIDENCE.md) for the acceptance test, method, measured latency table, and limitations. Naturalness ratings are still open (packets built by `make_rater_packet.py`).

<details>
<summary><strong>Pinned providers & values (verified live 2026-09-10)</strong></summary>

| What | Value |
|---|---|
| TTS model | Rime `coda` (Arcana is gone from the public catalog) |
| Path A voice | `nadi` (Coda Hindi voice) |
| Path B voices | Hindi runs → `nadi`, English runs → `astra` (one voice per language — structural) |
| Lang codes | `hin` / `eng` |
| Endpoint | `POST https://users.rime.ai/v1/rime-tts`, fields `text`/`speaker`/`modelId`/`lang`, `Accept: audio/wav` |
| Transport | REST streamed (eval); WebSocket `/ws3` bridge at `/api/speak/stream` (demo) |
| Router | Groq `openai/gpt-oss-20b` (MoE — replaces long-dead `mixtral-8x7b-32768`) |
| Bonus comparison | Groq `openai/gpt-oss-120b` + optional OpenRouter `deepseek/deepseek-r1:free` |

</details>

<details>
<summary><strong>API contracts</strong></summary>

- `POST /api/speak/native {text}` → `{audio_b64, ttfa_ms, total_ms, api_calls: 1}`
- `POST /api/speak/baseline {text, router_model?}` → `{audio_b64, segment_ms, ttfa_ms, total_ms, api_calls, segments: [{lang, text, speaker, ttfa_ms, total_ms}]}`
- `POST /api/speak/agentic {text}` → both paths via the LangGraph agent (`backend/agent_graph.py`)
- `WS /api/speak/stream` → server-side bridge to Rime `/ws3` (browsers can't set the auth header)
- `GET /api/sentences` → the 10-sentence test set
- Errors: HTTP 502 `{error, provider, fallback: "none"}` — failures surface honestly, never faked.

</details>

<details>
<summary><strong>Evidence bundle & reproduce</strong></summary>

- `sentences.json` — 10 Hinglish sentences (customer-support/everyday, 1–3 switches each)
- `data/timings.jsonl` — one row per path per run (gitignored, regenerate; latest row per sentence/path wins)
- `data/clips/s{id}_{a,b}.wav` — rendered audio (gitignored)
- `rater_packet/` — blind X/Y randomized pairs + `responses.csv` (gitignored key)
- `scripts/sbds.py` — objective seam metric (silence gaps, pitch jumps, spectral flux, energy steps; weights pre-registered in-file)
- Reproduce: `py scripts/smoke_test.py` → `py scripts/run_eval.py` → `py scripts/make_rater_packet.py` → collect ratings → `py scripts/bonus_segmentation.py`

</details>

## Known limitations

- **No speech-to-text input** — text in, audio out. Deliberate scope cut; STT is another provider and another failure mode.
- **No fallback TTS** — if Rime fails, the error surfaces. Silent substitution would invalidate the A/B.
- **Small sample** — 10 sentences, a handful of raters. Directional signal, not proof; reported as raw counts.
- **Sequential baseline calls** — worst case for Path B latency; acknowledged in `RIME_EVIDENCE.md`.
- Single provider account, single region, one session — network variance uncontrolled.

## AI-assistance disclosure

Claude Code (Anthropic) scaffolded project structure, provider clients, eval scripts, and docs drafts. Sub-agents built the LangGraph wrapper, the SBDS metric, and the WS bridge (all compile-checked, provider calls verified live after). The hypothesis, sentence set, ground-truth labels, and all measured results come from the team's own runs; raters are humans.
