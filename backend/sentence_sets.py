"""Custom sentence sets: user sentence lists without touching the eval set.

The pinned 10-sentence eval set (sentences.json, GET /api/sentences) is
the research baseline — nothing here writes to it. Custom sets live in
data/sets/<name>.json (gitignored user data) and power the /demo set
picker for rater exploration beyond the pinned sentences.

Names are slugs ([a-z0-9_-], <=32 chars) and always resolved inside
SETS_DIR, so traversal names ("../x") are rejected, not sanitized.
"""
import json
import re
from pathlib import Path

from . import config

SETS_DIR = config.DATA_DIR / "sets"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MAX_SENTENCES = 50
MAX_CHARS = 1000


def _path(name: str) -> Path:
    if not NAME_RE.match(name):
        raise ValueError(
            "set name must match [a-z0-9_-]{1,32} (lowercase slug, e.g. support-extra)"
        )
    # Belt-and-braces with the regex above: never escape SETS_DIR.
    p = (SETS_DIR / f"{name}.json").resolve()
    if p.parent != SETS_DIR.resolve():
        raise ValueError("invalid set name")
    return p


def _clean(texts: list[str]) -> list[str]:
    cleaned = [t.strip() for t in texts if t and t.strip()]
    if not cleaned:
        raise ValueError("set needs at least 1 non-empty sentence")
    if len(cleaned) > MAX_SENTENCES:
        raise ValueError(f"set holds at most {MAX_SENTENCES} sentences")
    for t in cleaned:
        if len(t) > MAX_CHARS:
            raise ValueError(f"sentence over {MAX_CHARS} chars: {t[:40]!r}...")
    return cleaned


def list_sets() -> list[dict]:
    if not SETS_DIR.is_dir():
        return []
    out = []
    for p in sorted(SETS_DIR.glob("*.json")):
        try:
            texts = json.loads(p.read_text(encoding="utf-8"))
            count = len(texts) if isinstance(texts, list) else 0
        except (json.JSONDecodeError, OSError):
            count = 0
        out.append({"name": p.stem, "count": count})
    return out


def get_set(name: str) -> list[dict]:
    p = _path(name)
    if not p.exists():
        raise FileNotFoundError(f"unknown set: {name}")
    texts = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(texts, list):
        raise ValueError(f"corrupt set file: {name}")
    return [{"id": i + 1, "text": t} for i, t in enumerate(texts)]


def create_set(name: str, texts: list[str]) -> dict:
    p = _path(name)
    if p.exists():
        raise FileExistsError(f"set already exists: {name} (delete it first)")
    cleaned = _clean(texts)
    SETS_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"name": name, "count": len(cleaned)}


def delete_set(name: str) -> None:
    p = _path(name)
    if not p.exists():
        raise FileNotFoundError(f"unknown set: {name}")
    p.unlink()
