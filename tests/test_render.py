"""render.py: words ⊕ edits ⊕ segments → timed, segmented tokens (offline)."""

from echo import render

WORDS = [
    {"idx": 0, "text": "a", "start_ms": 0, "dur_ms": 100},
    {"idx": 1, "text": "b", "start_ms": 100, "dur_ms": 100},
    {"idx": 2, "text": "c", "start_ms": 200, "dur_ms": 100},
    {"idx": 3, "text": "d", "start_ms": 300, "dur_ms": 100},
    {"idx": 4, "text": "e", "start_ms": 400, "dur_ms": 100},
]


def test_replace_delete_and_grouping():
    edits = [
        {"span_start": 1, "span_end": 2, "op": "replace", "text": "B"},
        {"span_start": 3, "span_end": 3, "op": "delete", "text": ""},
    ]
    segments = [
        {"seg_idx": 0, "span_start": 0, "span_end": 2, "kind": "clause"},
        {"seg_idx": 1, "span_start": 3, "span_end": 4, "kind": "clause"},
    ]
    out = render.render(WORDS, edits, segments)

    assert [s["seg_idx"] for s in out] == [0, 1]
    # segment 0: tokens "a" (untouched) + "B" (replace of words 1-2)
    assert [t["text"] for t in out[0]["tokens"]] == ["a", "B"]
    assert out[0]["start_ms"] == 0 and out[0]["end_ms"] == 300
    b = out[0]["tokens"][1]
    assert b == {"text": "B", "src_start": 1, "src_end": 2,
                 "start_ms": 100, "dur_ms": 200}
    # segment 1: "d" (idx 3) was deleted, so only "e" remains
    assert [t["text"] for t in out[1]["tokens"]] == ["e"]
    assert out[1]["start_ms"] == 300 and out[1]["end_ms"] == 500
    assert out[1]["tokens"][0]["start_ms"] == 400


def test_replace_restores_leading_space():
    # json3-style tokens carry leading spaces; a replacement that drops it
    # must be re-spaced so it doesn't glue to the previous word.
    words = [
        {"idx": 0, "text": "le", "start_ms": 0, "dur_ms": 100},
        {"idx": 1, "text": " Yan.", "start_ms": 100, "dur_ms": 100},
    ]
    edits = [{"span_start": 1, "span_end": 1, "op": "replace", "text": "yuan"}]
    segments = [{"seg_idx": 0, "span_start": 0, "span_end": 1, "kind": "clause"}]
    out = render.render(words, edits, segments)
    assert [t["text"] for t in out[0]["tokens"]] == ["le", " yuan"]


def test_no_edits_passthrough():
    segments = [{"seg_idx": 0, "span_start": 0, "span_end": 4, "kind": "clause"}]
    out = render.render(WORDS, [], segments)
    assert len(out) == 1
    assert [t["text"] for t in out[0]["tokens"]] == ["a", "b", "c", "d", "e"]
    assert out[0]["start_ms"] == 0 and out[0]["end_ms"] == 500
