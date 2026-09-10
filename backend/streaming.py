"""Server-side Rime WebSocket streaming bridge (demo/streaming path).

True streaming per https://docs.rime.ai/docs/api-cheat-sheet is WebSocket
``wss://users-ws.rime.ai/ws3`` with query params ``speaker`` / ``modelId`` /
``audioFormat``, auth via the ``Authorization`` header (browsers CANNOT set
custom headers on a WebSocket handshake, so this server-side bridge is
required), client sends ``{"text": ...}`` then ``{"operation": "eos"}``, and
the server returns JSON events: ``chunk`` (base64 audio) / ``timestamps`` /
``done`` / ``error``. ``modelId`` is set explicitly from ``config.RIME_MODEL``.

Day-0 verification still needed before demo use:
  1. ``lang`` placement — implemented here as a ``lang`` *query param* when
     provided. The REST API takes ``lang`` inside the JSON body and the WS
     cheat-sheet does not clearly document a ``lang`` channel, so the WS
     endpoint may instead expect ``lang`` inside the ``{"text": ...}``
     message. Verify live and move it if the server ignores/rejects it.
  2. ``wav`` support on ``ws3`` — ``audioFormat=wav`` is assumed valid here;
     confirm the server accepts it (vs. e.g. ``pcm``/``mp3``) on Day 0.

Eval boundary: REST (``backend/rime.py``) remains the evaluation path
(single-shot request/response with ttfa/total timing). This module is the
demo/streaming path only (progressive audio + word timestamps over a
browser-facing app WebSocket).

This module only *defines* ``ws_router``; ``backend/main.py`` is intentionally
untouched — the orchestrator wires it up with ``include_router``.
"""

import base64
import binascii
import json
import time
from typing import Any, AsyncGenerator, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import websockets

from . import config

WS_URL = "wss://users-ws.rime.ai/ws3"
CONNECT_TIMEOUT_S = 15
# Generous per-message read timeout: synthesis of long texts can stall
# between chunks without the stream being dead.
READ_TIMEOUT_S = 120


def _build_ws_url(
    speaker: str, audio_format: str, lang: Optional[str] = None
) -> str:
    """Build the ws3 URL. ``modelId`` is always set explicitly."""
    params = {
        "speaker": speaker,
        "modelId": config.RIME_MODEL,
        "audioFormat": audio_format,
    }
    if lang:
        # ASSUMPTION (verify Day 0): `lang` goes on the query string. The WS
        # endpoint may instead want it inside the {"text": ...} message, in
        # which case move it there and drop it from `params`.
        params["lang"] = lang
    return f"{WS_URL}?{urlencode(params)}"


def _decode_chunk_b64(event: dict) -> Optional[bytes]:
    """Extract base64 audio bytes from a chunk event, or None."""
    for key in ("data", "audio", "chunk", "audioContent"):
        b64 = event.get(key)
        if isinstance(b64, str) and b64:
            try:
                return base64.b64decode(b64)
            except (binascii.Error, ValueError):
                continue
    return None


async def stream_tts(
    text: str,
    speaker: Optional[str] = None,
    lang: Optional[str] = None,
    audio_format: str = "wav",
) -> AsyncGenerator[tuple[str, Any], None]:
    """Stream TTS audio for ``text`` via Rime ``ws3``.

    Yields ``(event_type, payload)`` tuples:
      - ``("audio", bytes)`` — one per decoded audio chunk.
      - ``("timestamps", words)`` — one per word-timestamp event.
      - ``("done", stats)`` — terminal event; ``stats`` is
        ``{"ttfa_ms": int, "total_ms": int, "chunk_count": int}``.

    Raises ``RuntimeError`` on an ``"error"`` event from the server.
    """
    speaker = speaker or config.RIME_SPEAKER
    url = _build_ws_url(speaker, audio_format, lang)
    headers = {"Authorization": f"Bearer {config.RIME_API_KEY}"}

    t0 = time.perf_counter()
    first_chunk_t: Optional[float] = None
    chunk_count = 0

    connect_kwargs: dict = {
        "open_timeout": CONNECT_TIMEOUT_S,
    }
    # `websockets` renamed `extra_headers` -> `additional_headers` (>= v13).
    # Pass whichever the installed version accepts.
    try:
        async with websockets.connect(
            url, additional_headers=headers, **connect_kwargs
        ) as ws:
            async for event_type, payload in _run_session(
                ws, text, t0, READ_TIMEOUT_S
            ):
                if event_type == "audio":
                    chunk_count += 1
                    if first_chunk_t is None:
                        first_chunk_t = time.perf_counter()
                if event_type == "done":
                    payload = dict(payload)
                    payload.setdefault(
                        "ttfa_ms",
                        int(((first_chunk_t or time.perf_counter()) - t0) * 1000),
                    )
                    payload.setdefault(
                        "total_ms", int((time.perf_counter() - t0) * 1000)
                    )
                    payload.setdefault("chunk_count", chunk_count)
                yield event_type, payload
                if event_type == "audio":
                    pass  # chunk_count already tracked above
            return
    except TypeError:
        pass  # fall through to the legacy `extra_headers` spelling below

    async with websockets.connect(
        url, extra_headers=headers, **connect_kwargs
    ) as ws:
        async for event_type, payload in _run_session(ws, text, t0, READ_TIMEOUT_S):
            if event_type == "audio":
                chunk_count += 1
                if first_chunk_t is None:
                    first_chunk_t = time.perf_counter()
            if event_type == "done":
                payload = dict(payload)
                payload.setdefault(
                    "ttfa_ms",
                    int(((first_chunk_t or time.perf_counter()) - t0) * 1000),
                )
                payload.setdefault(
                    "total_ms", int((time.perf_counter() - t0) * 1000)
                )
                payload.setdefault("chunk_count", chunk_count)
            yield event_type, payload


async def _run_session(ws, text: str, t0: float, read_timeout: float):
    """Send text+eos on an open ``ws`` and yield parsed ``(type, payload)``."""
    import asyncio

    first_chunk_t: Optional[float] = None
    chunk_count = 0
    await ws.send(json.dumps({"text": text}))
    await ws.send(json.dumps({"operation": "eos"}))

    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=read_timeout)
        except asyncio.TimeoutError:
            raise RuntimeError("timed out waiting for Rime WS audio")
        if isinstance(raw, (bytes, bytearray)):
            # Some servers may emit raw binary audio frames.
            chunk_count += 1
            if first_chunk_t is None:
                first_chunk_t = time.perf_counter()
            yield "audio", bytes(raw)
            continue
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        kind = str(event.get("type") or event.get("event") or "").lower()
        if kind == "error":
            message = (
                event.get("message") or event.get("error") or json.dumps(event)
            )
            raise RuntimeError(f"Rime WS error: {message}")
        if kind in ("chunk", "audio", "audio_chunk", "data"):
            audio = _decode_chunk_b64(event)
            if audio is not None:
                chunk_count += 1
                if first_chunk_t is None:
                    first_chunk_t = time.perf_counter()
                yield "audio", audio
            continue
        if kind in ("timestamps", "timestamp", "word_timestamps"):
            words = event.get("words", event.get("timestamps", event.get("data")))
            yield "timestamps", words
            continue
        if kind in ("done", "eos", "complete", "completed"):
            total_ms = int((time.perf_counter() - t0) * 1000)
            ttfa_ms = (
                int((first_chunk_t - t0) * 1000)
                if first_chunk_t is not None
                else total_ms
            )
            stats = {
                "ttfa_ms": ttfa_ms,
                "total_ms": total_ms,
                "chunk_count": chunk_count,
            }
            yield "done", stats
            return


ws_router = APIRouter(prefix="/api")


@ws_router.websocket("/speak/stream")
async def speak_stream(ws: WebSocket) -> None:
    """Browser-facing stream: in JSON request, out JSON audio/timestamp frames.

    Request (single JSON message): ``{"text": ..., "speaker"?, "lang"?}``.
    Frames back: ``{"type": "audio", "b64": ...}`` /
    ``{"type": "timestamps", "words": [...]}`` /
    ``{"type": "done", "ttfa_ms": ..., "total_ms": ..., "chunks": N}`` /
    ``{"type": "error", "message": ...}``.
    """
    await ws.accept()
    try:
        req = await ws.receive_json()
    except Exception as e:
        await ws.send_json({"type": "error", "message": f"bad request: {e}"})
        await ws.close()
        return
    text = (req.get("text") or "") if isinstance(req, dict) else ""
    if not text:
        await ws.send_json({"type": "error", "message": "missing 'text'"})
        await ws.close()
        return
    speaker = req.get("speaker") if isinstance(req, dict) else None
    lang = req.get("lang") if isinstance(req, dict) else None
    try:
        async for event_type, payload in stream_tts(
            text, speaker=speaker, lang=lang
        ):
            if event_type == "audio":
                await ws.send_json(
                    {"type": "audio", "b64": base64.b64encode(payload).decode()}
                )
            elif event_type == "timestamps":
                await ws.send_json({"type": "timestamps", "words": payload})
            elif event_type == "done":
                await ws.send_json(
                    {
                        "type": "done",
                        "ttfa_ms": payload.get("ttfa_ms"),
                        "total_ms": payload.get("total_ms"),
                        "chunks": payload.get("chunk_count", 0),
                    }
                )
    except WebSocketDisconnect:
        return
    except RuntimeError as e:
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    except Exception as e:  # keep the socket protocol clean on surprises
        try:
            await ws.send_json({"type": "error", "message": f"stream failed: {e}"})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
