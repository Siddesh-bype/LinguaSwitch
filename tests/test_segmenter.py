"""Offline tests for the segmenter prompt contract (no Groq calls)."""
import json

import pytest

from backend import segmenter


def test_parse_valid_router_output():
    raw = json.dumps({"segments": [{"lang": "hin", "text": "mera order "}, {"lang": "eng", "text": "check please"}]})
    out = segmenter._parse(raw)
    assert out == [{"lang": "hin", "text": "mera order "}, {"lang": "eng", "text": "check please"}]


def test_parse_recovers_json_embedded_in_prose():
    raw = 'Sure! {"segments": [{"lang": "eng", "text": "Hi "}, {"lang": "hin", "text": "kaise ho?"}]} done'
    out = segmenter._parse(raw)
    assert [s["lang"] for s in out] == ["eng", "hin"]


def test_parse_rejects_bad_lang_tag():
    with pytest.raises(ValueError, match="bad segments"):
        segmenter._parse(json.dumps({"segments": [{"lang": "fra", "text": "bonjour"}]}))


def test_parse_rejects_empty_segments():
    with pytest.raises(ValueError, match="bad segments"):
        segmenter._parse(json.dumps({"segments": []}))


def test_parse_rejects_garbage():
    with pytest.raises(Exception):
        segmenter._parse("not json at all {{{")


def test_messages_reconstruct_original_sentence():
    # Few-shot examples must obey the concat-reconstruction rule they teach.
    for text, segs in segmenter.EXAMPLES:
        assert "".join(s["text"] for s in segs) == text
    msgs = segmenter._messages("Mera order kahan hai, can you check?")
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["content"] == "Mera order kahan hai, can you check?"
