"""Tests for the eval summary endpoint (no network, no keys)."""
import json

import pytest
from fastapi.testclient import TestClient

from backend import eval_routes, eval_summary
from backend.main import app

client = TestClient(app)


@pytest.fixture()
def timings_file():
    import shutil
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp(prefix="eval-test-"))
    p = d / "timings.jsonl"
    yield p
    shutil.rmtree(d, ignore_errors=True)


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_summary_missing_file_is_404(monkeypatch, timings_file):
    monkeypatch.setattr(eval_summary, "TIMINGS", timings_file)
    monkeypatch.setattr(eval_routes.eval_summary, "TIMINGS", timings_file)
    r = client.get("/api/eval/summary")
    assert r.status_code == 404
    assert "run_eval" in r.json()["error"]


def test_summary_rolls_up_latest_rows(monkeypatch, timings_file):
    _write(timings_file, [
        {"sentence_id": 1, "path": "a", "ttfa_ms": 1000, "total_ms": 2000},
        {"sentence_id": 1, "path": "b", "ttfa_ms": 2500, "total_ms": 5000, "segment_ms": 900, "segments": 2},
        {"sentence_id": 1, "path": "a", "ttfa_ms": 1100, "total_ms": 2100},  # rerun wins
        {"sentence_id": 2, "path": "a", "ttfa_ms": 1000, "total_ms": 9000},  # no B row: skipped
    ])
    monkeypatch.setattr(eval_summary, "TIMINGS", timings_file)
    monkeypatch.setattr(eval_routes.eval_summary, "TIMINGS", timings_file)
    r = client.get("/api/eval/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["n_sentences"] == 1
    assert body["per_sentence"][0]["a_total_ms"] == 2100
    assert body["native_wins"] == 1
    assert body["avg_b_total_ms"] == 5000


def test_summarize_unit_latest_wins():
    latest = {
        (1, "a"): {"sentence_id": 1, "path": "a", "ttfa_ms": 1, "total_ms": 10},
        (1, "b"): {"sentence_id": 1, "path": "b", "ttfa_ms": 2, "total_ms": 5, "segment_ms": 1, "segments": 1},
    }
    s = eval_summary.summarize(latest)
    assert s["native_wins"] == 0  # 10 > 5: baseline faster here
    assert s["per_sentence"][0]["delta_total_ms"] == 5
