"""WAV concatenation using stdlib `wave` only — no pydub, no ffmpeg.

Rime streams WAV with an INT32_MAX placeholder frame count
(nframes=2147483647, size bytes ffffffff), so header counts are lies:
we re-derive everything from the actual PCM bytes and write a fresh,
correct header. Params (channels/width/rate) must match across segments
— a mismatch raises instead of producing garbage audio.
"""
import io
import math
import struct
import wave


def read_pcm(wav_bytes: bytes) -> tuple[tuple[int, int, int], bytes]:
    """Return ((nchannels, sampwidth, framerate), raw PCM frames).

    Raises ValueError (not wave.Error) with context if the input is not
    a readable WAV — run_eval.py reports these per sentence.
    """
    try:
        reader = wave.open(io.BytesIO(wav_bytes))
    except wave.Error as e:
        raise ValueError(
            f"not a WAV file ({len(wav_bytes)} bytes, head={wav_bytes[:12]!r}): {e}"
        )
    with reader:
        params = (reader.getnchannels(), reader.getsampwidth(), reader.getframerate())
        # Header frame count is a streaming placeholder: read to EOF.
        frames = reader.readframes(reader.getnframes())
    if not frames and wav_bytes:
        raise ValueError(f"WAV contained no readable frames ({len(wav_bytes)} bytes)")
    return params, frames


def write_pcm(params: tuple[int, int, int], frames_list: list[bytes]) -> bytes:
    """Write PCM frames under a fresh, correct WAV header."""
    nchannels, sampwidth, framerate = params
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(nchannels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        for frames in frames_list:
            out.writeframes(frames)
    return buf.getvalue()


def concat_wav(wav_bytes_list: list[bytes]) -> bytes:
    pcms = [read_pcm(b) for b in wav_bytes_list]
    base = pcms[0][0]
    for params, _ in pcms[1:]:
        if params != base:
            raise ValueError(
                f"WAV param mismatch across segments: {base} vs {params} — "
                "refusing to concatenate incompatible audio"
            )
    return write_pcm(base, [frames for _, frames in pcms])


if __name__ == "__main__":
    # Self-check: two in-memory sine WAVs, concat, assert frame counts add up.
    RATE, WIDTH, CH = 8000, 2, 1

    def sine_wav(freq: float, ms: int, lie_nframes: bool = False) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(CH)
            w.setsampwidth(WIDTH)
            w.setframerate(RATE)
            n = RATE * ms // 1000
            w.writeframes(
                b"".join(
                    struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / RATE)))
                    for i in range(n)
                )
            )
        raw = buf.getvalue()
        if lie_nframes:
            # Simulate Rime's streaming header: patch nframes + sizes to INT32_MAX.
            raw = raw[:40] + struct.pack("<L", 2147483647) + raw[44:]
        return raw

    # The regression case: placeholder headers must not break the concat.
    a, b = sine_wav(440, 100, lie_nframes=True), sine_wav(880, 150, lie_nframes=True)
    joined = concat_wav([a, b])
    with wave.open(io.BytesIO(joined)) as w:
        n, p = w.getnframes(), w.getparams()
    assert n == 800 + 1200 == 2000, f"frame count mismatch: {n}"
    assert p.nchannels == CH and p.sampwidth == WIDTH and p.framerate == RATE
    print(f"audio.py self-check OK: 2 placeholder-header WAVs -> 1 valid WAV, {n} frames == 800+1200")
