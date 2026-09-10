"""Tests for blind-rating store, API, and packet tally script."""
import csv
import json

import pytest
from fastapi.testclient import TestClient

from backend import ratings as ratings_mod
from backend import ratings_routes as rr_mod
from backend.main import app
from scripts.tally_ratings import unblind

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch):
    # Point the API store at a temp file so tests never touch
    # data/ratings.json (tempfile: tmp_path is unreliable on this box).
    import shutil
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp(prefix="ratings-test-"))
    monkeypatch.setattr(rr_mod, "STORE", ratings_mod.RatingsStore(d / "ratings.json"))
    yield
    shutil.rmtree(d, ignore_errors=True)


def test_vote_and_tally_roundtrip():
    r = client.post("/api/ratings/vote", json={"rater": "ann", "question": "q1", "choice": "X"})
    assert r.status_code == 200
    client.post("/api/ratings/vote", json={"rater": "bob", "question": "q1", "choice": "Y"})
    client.post("/api/ratings/vote", json={"rater": "ann", "question": "q2", "choice": "same"})
    t = client.get("/api/ratings/tally").json()
    assert t["votes"] == 3
    assert t["totals"] == {"X": 1, "Y": 1, "same": 1}
    assert t["per_question"]["q1"] == {"X": 1, "Y": 1, "same": 0}
    assert sorted(t["raters"]) == ["ann", "bob"]


def test_revote_overwrites_latest_wins():
    client.post("/api/ratings/vote", json={"rater": "ann", "question": "q1", "choice": "X"})
    client.post("/api/ratings/vote", json={"rater": "ann", "question": "q1", "choice": "Y"})
    t = client.get("/api/ratings/tally").json()
    assert t["votes"] == 1
    assert t["totals"]["Y"] == 1


def test_bad_choice_is_422():
    r = client.post("/api/ratings/vote", json={"rater": "ann", "question": "q1", "choice": "A"})
    assert r.status_code == 422


def test_empty_rater_is_422():
    assert client.post("/api/ratings/vote", json={"rater": "", "question": "q1", "choice": "X"}).status_code == 422


def test_store_survives_reload_and_rejects_bad_choice():
    import shutil
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp(prefix="ratings-persist-"))
    try:
        s1 = ratings_mod.RatingsStore(d / "r.json")
        s1.vote("ann", "q1", "X")
        s2 = ratings_mod.RatingsStore(d / "r.json")  # new instance, same file
        assert s2.tally()["totals"]["X"] == 1
        with pytest.raises(ValueError):
            s2.vote("ann", "q1", "maybe")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _packet(key, rows):
    import shutil
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp(prefix="packet-"))
    (d / "rater_key.json").write_text(json.dumps(key))
    with (d / "responses.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rater", "question", "choice"])
        w.writeheader()
        w.writerows(rows)
    return d


def test_unblind_maps_xy_to_ab():
    import shutil

    d = _packet({"q1": {"x": "a", "y": "b"}, "q2": {"x": "b", "y": "a"}}, [
        {"rater": "ann", "question": "q1", "choice": "X"},  # -> native
        {"rater": "ann", "question": "q2", "choice": "X"},  # -> baseline
        {"rater": "bob", "question": "q1", "choice": "same"},
        {"rater": "bob", "question": "q9", "choice": "X"},  # unknown q
        {"rater": "bob", "question": "q1", "choice": "Z"},  # bad choice
    ])
    try:
        votes, errors = unblind(d / "responses.csv", d / "rater_key.json")
        assert votes == ["native", "baseline", "same"]
        assert len(errors) == 2
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_verdict_rule():
    assert ratings_mod.verdict(6, 4) == "native"
    assert ratings_mod.verdict(3, 5) == "baseline"
    assert ratings_mod.verdict(2, 2) == "tie"
