"""Lightweight seam proxy (stdlib-only, no librosa) for the metrics API.

scripts/sbds.py remains the full offline analysis (pitch/flux/energy with
librosa). This module answers a narrower question fast and without heavy
deps: does this WAV contain long inter-word silences typical of
concat seams? It uses frame-RMS energy gating on 20ms frames.

Returns {"duration_s", "n_gaps", "n_long_gaps", "max_gap_ms",
"silence_ratio", "seam_score"} where seam_score = n_long_gaps
(gaps > 250ms, same LONG_GAP_MS prior as scripts/sbds.py).
"""
import io
import struct
import wave

FRAME_MS = 20
LONG_GAP_MS = 250.0
SILENCE_RMS = 500.0  # int16 RMS below this counts as silence (quiet room)


def score_wav(wav_bytes: bytes) -> dict:
    try:
        reader = wave.open(io.BytesIO(wav_bytes))
    except wave.Error as e:
        raise ValueError(f"not a WAV file ({len(wav_bytes)} bytes): {e}")
    with reader:
        nch, width, rate = reader.getnchannels(), reader.getsampwidth(), reader.getframerate()
        if width != 2:
            raise ValueError(f"only 16-bit PCM supported (got sampwidth={width})")
        nframes = reader.getnframes()
        raw = reader.readframes(nframes)
    if not raw:
        raise ValueError("WAV contained no readable frames")

    nsamp = len(raw) // 2
    fmt = "<" + "h" * nsamp
    samples = struct.unpack(fmt, raw)
    if nch > 1:
        # Mono-mix channels for energy gating.
        samples = [sum(samples[i * nch:(i + 1) * nch]) // nch for i in range(nsamp // nch)]
        nsamp = len(samples)

    frame_n = max(1, rate * FRAME_MS // 1000)
    silent = []
    for start in range(0, nsamp, frame_n):
        frame = samples[start:start + frame_n]
        rms = (sum(s * s for s in frame) / len(frame)) ** 0.5
        silent.append(rms < SILENCE_RMS)

    # Merge consecutive silent frames into gaps (ignore leading/trailing).
    gaps_ms: list[float] = []
    run = 0
    for idx, is_sil in enumerate(silent):
        is_edge = idx == 0 or idx == len(silent) - 1
        if is_sil and not is_edge:
            run += 1
        else:
            if run:
                gaps_ms.append(run * FRAME_MS)
                run = 0
    if run:
        gaps_ms.append(run * FRAME_MS)

    n_long = sum(1 for g in gaps_ms if g > LONG_GAP_MS)
    return {
        "duration_s": round(nsamp / rate, 3),
        "n_gaps": len(gaps_ms),
        "n_long_gaps": n_long,
        "max_gap_ms": round(max(gaps_ms, default=0.0), 1),
        "silence_ratio": round(sum(gaps_ms) / 1000.0 / (nsamp / rate), 4) if nsamp else 0.0,
        "seam_score": float(n_long),
    }
