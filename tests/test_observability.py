"""Tests for request observability (no network, no keys)."""
import pytest
from fastapi.testclient import TestClient

from backend import observability
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_stats():
    observability.reset_stats()
    yield
    observability.reset_stats()


def test_responses_carry_unique_request_ids():
    r1 = client.get("/api/sentences")
    r2 = client.get("/api/sentences")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.headers["X-Request-ID"] and r2.headers["X-Request-ID"]
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


def test_caller_supplied_request_id_is_echoed():
    r = client.get("/api/sentences", headers={"X-Request-ID": "demo-123"})
    assert r.headers["X-Request-ID"] == "demo-123"


def test_error_responses_still_carry_request_id():
    r = client.post("/api/speak/native", json={"text": "   "})
    assert r.status_code == 422
    assert r.headers["X-Request-ID"]


def test_stats_count_requests_and_errors_per_route():
    client.get("/api/sentences")
    client.get("/api/sentences")
    client.post("/api/speak/native", json={"text": ""})  # 422
    snap = client.get("/api/metrics/requests").json()
    assert snap["uptime_s"] >= 0
    assert snap["routes"]["GET /api/sentences"]["requests"] == 2
    key = "POST /api/speak/native"
    assert snap["routes"][key]["requests"] == 1
    assert snap["routes"][key]["errors"] == 1
    # Snapshot is taken before the stats call itself is recorded.
    assert snap["totals"]["requests"] == 3
    assert snap["totals"]["errors"] == 1


def test_stats_call_counts_itself():
    snap = client.get("/api/metrics/requests").json()
    # The snapshot is taken before this very request is recorded, so the
    # totals reflect only prior requests — here, zero.
    assert snap["totals"] == {"requests": 0, "errors": 0, "avg_ms": 0.0}
    assert snap["routes"] == {}


def test_avg_ms_is_sane():
    client.get("/api/health")
    snap = client.get("/api/metrics/requests").json()
    avg = snap["routes"]["GET /api/health"]["avg_ms"]
    assert isinstance(avg, float) and avg >= 0.0
