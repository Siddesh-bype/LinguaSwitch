"""Day 0 smoke test — the verification gate for the whole project.

Makes 3 Rime calls (eng, hin, mixed Hinglish), prints status/timings/audio
info, and saves clips to data/. Run BEFORE trusting any other code:

    py scripts/smoke_test.py

If calls fail, read the error, fix .env / backend/rime.py, re-run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, rime  # noqa: E402

CASES = [
    ("eng", "Can you check the status of my order please?", config.RIME_LANG_ENG),
    ("hin", "Mera order kahan hai bhai?", config.RIME_LANG_HIN),
    ("mixed", "Mera order kahan hai, can you check the status please?", None),
]


def main() -> None:
    if not config.RIME_API_KEY:
        sys.exit("RIME_API_KEY not set — copy .env.example to .env and fill it in.")
    config.CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"endpoint : {config.RIME_API_BASE}/rime-tts")
    print(f"model    : {config.RIME_MODEL}  speaker: {config.RIME_SPEAKER}  "
          f"langs: {config.RIME_LANG_HIN}/{config.RIME_LANG_ENG}\n")

    for name, text, lang in CASES:
        try:
            out = rime.speak(text, lang)
        except Exception as e:  # noqa: BLE001 — smoke test reports raw failures
            print(f"[{name}] FAILED: {type(e).__name__}: {e}")
            continue
        audio = out["audio"]
        ext = "wav" if audio[:4] == b"RIFF" else "bin"
        path = config.CLIPS_DIR / f"smoke_{name}.{ext}"
        path.write_bytes(audio)
        print(f"[{name}] ok — {len(audio):,} bytes, ttfa {out['ttfa_ms']}ms, "
              f"total {out['total_ms']}ms, head={audio[:12]!r} -> {path}")

    print("\nIf all three played as audio files, Day 0 gate passed. "
          "Update README's endpoint/model/format section with what you saw.")


if __name__ == "__main__":
    main()
