"""Env config — single source of truth. Copy .env.example to .env and fill in."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

RIME_API_KEY = os.getenv("RIME_API_KEY", "")
RIME_API_BASE = os.getenv("RIME_API_BASE", "https://users.rime.ai/v1")
# Pinned by the Day 0 smoke test. "coda" is Rime's flagship model (Arcana is
# gone from the public voice catalog); "nadi" is a Coda Hindi voice,
# "astra" a Coda English starter voice (verified in all-v2.json).
RIME_MODEL = os.getenv("RIME_MODEL", "coda")
RIME_SPEAKER = os.getenv("RIME_SPEAKER", "nadi")
RIME_SPEAKER_HIN = os.getenv("RIME_SPEAKER_HIN", "nadi")
RIME_SPEAKER_ENG = os.getenv("RIME_SPEAKER_ENG", "astra")
RIME_LANG_HIN = os.getenv("RIME_LANG_HIN", "hin")
RIME_LANG_ENG = os.getenv("RIME_LANG_ENG", "eng")
RIME_OUTPUT_FORMAT = os.getenv("RIME_OUTPUT_FORMAT", "wav")

# mixtral-8x7b-32768 was deprecated by Groq (shutdown Mar 2025) and
# llama-3.1-8b-instant followed (shutdown Aug 2026). Router is now
# openai/gpt-oss-20b (current production; MoE architecture, so the
# "router runs on a real MoE model" claim still holds — cite its model card).
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_ROUTER_MODEL = os.getenv("GROQ_ROUTER_MODEL", "openai/gpt-oss-20b")
# Second comparison model for the bonus table (small-vs-large, NOT MoE-vs-dense).
GROQ_SECOND_MODEL = os.getenv("GROQ_SECOND_MODEL", "openai/gpt-oss-120b")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-r1:free")

# Path A's native call defaults to Hindi: Hinglish sentences skew Hindi-framed.
DEFAULT_LANG = RIME_LANG_HIN

# Segmenter tags ("hin"/"eng") -> Rime lang codes and per-language speakers.
# A Rime voice serves one language, so Path B must swap speaker per segment.
LANG_MAP = {"hin": RIME_LANG_HIN, "eng": RIME_LANG_ENG}
SPEAKER_MAP = {"hin": RIME_SPEAKER_HIN, "eng": RIME_SPEAKER_ENG}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CLIPS_DIR = DATA_DIR / "clips"

# Offline mode for dev/CI without provider keys (see backend/mock_tts.py).
# Mock audio is synthetic and must never be written to data/timings.jsonl.
MOCK_TTS = os.getenv("MOCK_TTS", "0") == "1"
MOCK_SEGMENTER = os.getenv("MOCK_SEGMENTER", "0") == "1"

# Path B fan-out (see backend/parallel.py). Default sequential preserves
# the published eval numbers; opt in per-request (parallel:true) or
# globally for a session via BASELINE_PARALLEL=1.
BASELINE_PARALLEL_DEFAULT = os.getenv("BASELINE_PARALLEL", "0") == "1"
BASELINE_MAX_WORKERS = int(os.getenv("BASELINE_MAX_WORKERS", "4") or 4)

# API response cache (see backend/cache.py). On by default to avoid
# rebilling providers on demo/rater replays; run_eval.py bypasses it so
# eval timings always reflect live calls. Set CACHE_TTL_S=0 to disable.
CACHE_TTL_S = int(os.getenv("CACHE_TTL_S", "300") or 300)
CACHE_MAX_ENTRIES = int(os.getenv("CACHE_MAX_ENTRIES", "200") or 200)
