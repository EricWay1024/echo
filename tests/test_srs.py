"""SM-2-lite scheduler (pure, offline)."""

import datetime as dt

from echo import srs

T = dt.date(2026, 1, 1)


def test_new_card_good_then_progresses():
    s = srs.schedule({}, "good", T)
    assert s["interval"] == 1 and s["reps"] == 1
    assert s["due"] == "2026-01-02"
    s = srs.schedule(s, "good", T)          # reps 1 -> 3 days
    assert s["interval"] == 3 and s["reps"] == 2
    s = srs.schedule(s, "good", T)          # round(3 * 2.3) = 7
    assert s["interval"] == 7 and s["reps"] == 3


def test_again_resets_and_drops_ease():
    s = {"interval": 7, "ease": 2.3, "reps": 3, "lapses": 0}
    out = srs.schedule(s, "again", T)
    assert out["interval"] == 0 and out["due"] == "2026-01-01"  # due today
    assert out["reps"] == 0 and out["lapses"] == 1
    assert out["ease"] == 2.1


def test_easy_bumps_interval_and_ease():
    out = srs.schedule({}, "easy", T)       # new -> 2 days, ease up
    assert out["interval"] == 2 and out["ease"] == 2.45


def test_graduates_at_21_days():
    s = {"interval": 10, "ease": 2.3, "reps": 5, "lapses": 0}
    out = srs.schedule(s, "good", T)        # round(10 * 2.3) = 23 >= 21
    assert out["interval"] == 23 and out["graduated"] is True
    assert srs.schedule({}, "good", T)["graduated"] is False


def test_bad_grade():
    try:
        srs.schedule({}, "perfect", T)
        assert False
    except ValueError:
        pass
