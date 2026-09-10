"""In-memory TTL cache for TTS + segmentation results.

Demo and rater sessions replay the same sentences repeatedly; without a
cache every replay rebills Rime/Groq. This caches *successful* results
only (never errors), keyed so a change of voice/lang/model is a miss:

- ("tts", text, lang, speaker) -> {"audio", "ttfa_ms", "total_ms"}
- ("segments", text, router_model) -> {"segments", "segment_ms"}

Eval integrity: scripts/run_eval.py calls providers directly and never
touches this cache, so data/timings.jsonl always reflects live calls.
API responses report "cached": true/false so no one mistakes a cache
hit for a fresh measurement. Bounded (CACHE_MAX_ENTRIES, oldest-first
eviction) and thread-safe for the parallel fan-out path.
"""
import hashlib
import threading
from collections import OrderedDict
from typing import Any


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def tts_key(text: str, lang: str | None, speaker: str | None) -> tuple:
    return ("tts", _h(text), lang or "", speaker or "")


def seg_key(text: str, model: str | None) -> tuple:
    return ("segments", _h(text), model or "")


class TTLCache:
    def __init__(self, ttl_s: int = 300, max_entries: int = 200):
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._items: OrderedDict = OrderedDict()
        self.hits = 0
        self.misses = 0

    def _expired(self, stored_at: float, now: float) -> bool:
        return self.ttl_s <= 0 or (now - stored_at) > self.ttl_s

    def get(self, key: tuple, now: float | None = None) -> Any | None:
        import time as _time

        now = now if now is not None else _time.monotonic()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                self.misses += 1
                return None
            value, stored_at = entry
            if self._expired(stored_at, now):
                del self._items[key]
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: tuple, value: Any, now: float | None = None) -> None:
        import time as _time

        now = now if now is not None else _time.monotonic()
        with self._lock:
            self._items[key] = (value, now)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def clear(self) -> int:
        with self._lock:
            n = len(self._items)
            self._items.clear()
            return n

    def stats(self) -> dict:
        with self._lock:
            return {
                "entries": len(self._items),
                "hits": self.hits,
                "misses": self.misses,
                "ttl_s": self.ttl_s,
                "max_entries": self.max_entries,
            }


# Shared by the API routes (per-process). Tests construct their own
# TTLCache instances or monkeypatch backend.routes.CACHE.
_default_cache = TTLCache()


def shared() -> TTLCache:
    return _default_cache
