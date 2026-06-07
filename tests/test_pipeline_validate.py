"""pipeline.validate: enforce the op + tiling invariants (offline)."""

from echo import pipeline

N = 10


def good():
    return {
        "edits": [{"op": "replace", "span": [2, 3], "text": "fixed"}],
        "segments": [
            {"span": [0, 4], "kind": "clause"},
            {"span": [5, 9], "kind": "clause"},
        ],
    }


def test_valid():
    assert pipeline.validate(good(), N) == []


def test_edit_out_of_range():
    d = good()
    d["edits"][0]["span"] = [8, 12]
    assert any("out of range" in e for e in pipeline.validate(d, N))


def test_edits_overlap():
    d = good()
    d["edits"] = [
        {"op": "replace", "span": [2, 4], "text": "x"},
        {"op": "replace", "span": [4, 5], "text": "y"},
    ]
    assert any("overlap" in e for e in pipeline.validate(d, N))


def test_replace_empty_text():
    d = good()
    d["edits"][0]["text"] = "  "
    assert any("empty text" in e for e in pipeline.validate(d, N))


def test_segments_gap():
    d = good()
    d["segments"] = [{"span": [0, 4], "kind": "c"}, {"span": [6, 9], "kind": "c"}]
    assert any("expected 5" in e for e in pipeline.validate(d, N))


def test_segments_dont_cover_end():
    d = good()
    d["segments"] = [{"span": [0, 4], "kind": "c"}, {"span": [5, 8], "kind": "c"}]
    assert any("transcript is [0,9]" in e for e in pipeline.validate(d, N))


def test_segments_must_start_at_zero():
    d = good()
    d["segments"] = [{"span": [1, 9], "kind": "c"}]
    assert any("expected 0" in e for e in pipeline.validate(d, N))
