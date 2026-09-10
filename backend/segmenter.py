"""Language segmentation via Groq (Mixtral) — the "Path B" router.

Splits a Hinglish sentence into ordered language-tagged runs. Run-level, not
word-by-word: ambiguous loanwords ("product", "damaged") stay inside the Hindi
run — that's how Hinglish actually works.
"""
import json
import re
import time

from groq import Groq

from . import config

SYSTEM = (
    "You segment Hinglish sentences into an ordered list of language-tagged runs. "
    'Respond with JSON: {"segments": [{"lang": "hin"|"eng", "text": "..."}]}. '
    "Rules: tags are strictly \"hin\" or \"eng\". Split at run/phrase level, NOT "
    "word-by-word — keep English loanwords that Hindi speakers use naturally "
    '(product, order, refund) inside the Hindi run. Concatenating all segment '
    "texts must reconstruct the original sentence exactly, preserving spacing "
    "and punctuation. Never merge or drop characters."
)

EXAMPLES = [
    (
        "Sir, ye product damaged hai — I want a return.",
        [{"lang": "eng", "text": "Sir, "}, {"lang": "hin", "text": "ye product damaged hai — "}, {"lang": "eng", "text": "I want a return."}],
    ),
    (
        "Can you please batao ki refund kab tak aayega?",
        [{"lang": "eng", "text": "Can you please "}, {"lang": "hin", "text": "batao ki refund kab tak aayega?"}],
    ),
    (
        "I need this by Friday, warna cancel kar dena padega.",
        [{"lang": "eng", "text": "I need this by Friday, "}, {"lang": "hin", "text": "warna cancel kar dena padega."}],
    ),
]


def _messages(text: str) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM}]
    for user, segs in EXAMPLES:
        msgs.append({"role": "user", "content": user})
        msgs.append({"role": "assistant", "content": json.dumps({"segments": segs})})
    msgs.append({"role": "user", "content": text})
    return msgs


def _parse(raw: str) -> list[dict]:
    try:
        segs = json.loads(raw)["segments"]
    except (json.JSONDecodeError, KeyError, TypeError):
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            raise
        segs = json.loads(m.group())
    out = [{"lang": s["lang"], "text": s["text"]} for s in segs]
    if not out or any(s["lang"] not in ("hin", "eng") for s in out):
        raise ValueError(f"bad segments: {out}")
    return out


def segment(text: str, model: str | None = None) -> list[dict]:
    client = Groq()  # GROQ_API_KEY from env via config-loaded dotenv
    model = model or config.GROQ_ROUTER_MODEL
    last_raw = ""
    for _ in range(2):  # one retry on unparseable output
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=_messages(text),
                response_format={"type": "json_object"},
            )
        except Exception:
            resp = client.chat.completions.create(
                model=model,
                messages=_messages(text),
            )
        last_raw = resp.choices[0].message.content or ""
        try:
            return _parse(last_raw)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    raise RuntimeError(f"segmenter: unparseable model output: {last_raw!r}")


def segment_timed(text: str, model: str | None = None) -> tuple[list[dict], int]:
    t0 = time.perf_counter()
    segs = segment(text, model)
    return segs, int((time.perf_counter() - t0) * 1000)
