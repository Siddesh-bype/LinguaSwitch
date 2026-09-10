"""Tests for custom sentence sets (no network, no keys)."""
import pytest
from fastapi.testclient import TestClient

from backend import routes as routes_mod
from backend import sentence_sets
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_sets(monkeypatch):
    import shutil
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp(prefix="sets-test-"))
    monkeypatch.setattr(sentence_sets, "SETS_DIR", d)
    yield
    shutil.rmtree(d, ignore_errors=True)


def test_crud_roundtrip():
    assert client.get("/api/sentences/sets").json() == {"sets": []}
    r = client.post("/api/sentences/sets", json={"name": "extra", "sentences": ["hello ji", "kaise ho?"]})
    assert r.status_code == 201
    assert r.json() == {"name": "extra", "count": 2}
    assert client.get("/api/sentences/sets").json() == {"sets": [{"name": "extra", "count": 2}]}
    g = client.get("/api/sentences/sets/extra").json()
    assert [s["text"] for s in g["sentences"]] == ["hello ji", "kaise ho?"]
    assert [s["id"] for s in g["sentences"]] == [1, 2]
    assert client.delete("/api/sentences/sets/extra").json() == {"deleted": "extra"}
    assert client.get("/api/sentences/sets").json() == {"sets": []}


def test_duplicate_is_409():
    client.post("/api/sentences/sets", json={"name": "dup", "sentences": ["a"]})
    r = client.post("/api/sentences/sets", json={"name": "dup", "sentences": ["b"]})
    assert r.status_code == 409


def test_unknown_set_is_404():
    assert client.get("/api/sentences/sets/nope").status_code == 404
    assert client.delete("/api/sentences/sets/nope").status_code == 404


def test_traversal_and_bad_names_are_422():
    # URL-stable bad names (clients normalize ".." away before sending,
    # so traversal is covered through the POST body below).
    for bad in ["UPPER", "has space", "a" * 33]:
        r = client.get(f"/api/sentences/sets/{bad}")
        assert r.status_code == 422, bad
    for bad in ["../evil", "..", "a/b"]:
        r = client.post("/api/sentences/sets", json={"name": bad, "sentences": ["x"]})
        assert r.status_code == 422, bad


def test_blank_and_oversize_content_rejected():
    assert client.post("/api/sentences/sets", json={"name": "blank", "sentences": ["   "]}).status_code == 422
    assert client.post("/api/sentences/sets", json={"name": "big", "sentences": ["x" * 1001]}).status_code == 422
    assert client.post("/api/sentences/sets", json={"name": "empty", "sentences": []}).status_code == 422


def test_eval_set_untouched_by_set_ops():
    before = client.get("/api/sentences").json()
    assert len(before["sentences"]) == 10
    client.post("/api/sentences/sets", json={"name": "other", "sentences": ["custom only"]})
    client.delete("/api/sentences/sets/other")
    after = client.get("/api/sentences").json()
    assert after == before
