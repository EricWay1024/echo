"""Parser tests against the committed real fixture (Les Echos, fr-orig)."""

from pathlib import Path

from echo import json3

FIXTURE = Path(__file__).parent / "fixtures" / "CE3foG8FRz4.fr-orig.json3"


def words():
    return json3.parse_file(FIXTURE)


def test_word_count_and_contiguous_idx():
    ws = words()
    assert len(ws) == 2064
    assert [w.idx for w in ws] == list(range(len(ws)))


def test_starts_monotonic_and_positive_durations():
    ws = words()
    for a, b in zip(ws, ws[1:]):
        assert b.start_ms >= a.start_ms
    assert all(w.dur_ms >= 1 for w in ws)


def test_first_word_timing():
    ws = words()
    assert ws[0].text == "Depuis"
    assert ws[0].start_ms == 719


def test_line_boundary_space_reinserted():
    # "Guerre" ends one caption line, "mondiale," opens the next; needs a space.
    text = json3.render(words())
    assert "Guerre mondiale" in text
    assert "Guerremondiale" not in text


def test_french_elisions_intact():
    text = json3.render(words())
    assert "c'est l'huile" in text
    assert "le dollar est la monnaie" in text


def test_no_newline_or_empty_tokens():
    ws = words()
    assert all(w.text.strip() != "" for w in ws)
    assert all("\n" not in w.text for w in ws)
