"""Request observability: IDs, per-request logs, in-memory route stats.

- Every response carries an X-Request-ID (caller-supplied or generated),
  so a demo failure can be tied to one backend log line.
- One log line per request: method, route template, status, latency.
- GET /api/metrics/requests serves aggregate counts / error counts /
  average latency per route template (in-memory, per-process; resets on
  restart — this is ops visibility, not eval data).

Route templates (e.g. POST /api/speak/native) are recorded instead of
raw paths so cardinality stays bounded.
"""
import logging
import threading
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("linguaswitch")

_lock = threading.Lock()
_stats: dict[tuple[str, str], list[int]] = {}  # (method, template) -> [requests, errors, total_ms]
_started_at = time.monotonic()


def _template(request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else request.url.path


def record(method: str, template: str, status: int, latency_ms: int) -> None:
    with _lock:
        entry = _stats.setdefault((method, template), [0, 0, 0])
        entry[0] += 1
        if status >= 400:
            entry[1] += 1
        entry[2] += latency_ms


def snapshot() -> dict:
    with _lock:
        routes = {}
        total_req, total_err, total_ms = 0, 0, 0
        for (method, template), (count, errors, ms) in sorted(_stats.items()):
            routes[f"{method} {template}"] = {
                "requests": count,
                "errors": errors,
                "avg_ms": round(ms / count, 1) if count else 0.0,
            }
            total_req += count
            total_err += errors
            total_ms += ms
    return {
        "uptime_s": int(time.monotonic() - _started_at),
        "routes": routes,
        "totals": {
            "requests": total_req,
            "errors": total_err,
            "avg_ms": round(total_ms / total_req, 1) if total_req else 0.0,
        },
    }


def reset_stats() -> None:
    """Clear counters (tests; the live server never calls this)."""
    with _lock:
        _stats.clear()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        t0 = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            # If the handler raised past the exception middleware there is
            # no response: count it as a 500 (the error still counts).
            status = response.status_code if response is not None else 500
            record(request.method, _template(request), status, latency_ms)
            logger.info(
                "%s %s -> %s in %dms id=%s",
                request.method, _template(request), status, latency_ms, request_id,
            )
