"""SM-2-lite spaced repetition. Pure functions — no DB, no I/O.

A card's state is {interval (days), ease, reps, lapses}. `schedule` returns the
next state given a grade ("again" | "good" | "easy") and today's date.
"""

from __future__ import annotations

import datetime as dt

DEFAULT_EASE = 2.3
MIN_EASE = 1.3
MAX_EASE = 3.0
GRADUATE_INTERVAL = 21  # days; at/over this, the card's lemma becomes "known"


def schedule(state: dict, grade: str, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    ease = state.get("ease") or DEFAULT_EASE
    interval = state.get("interval") or 0
    reps = state.get("reps") or 0
    lapses = state.get("lapses") or 0

    if grade == "again":
        ease = max(MIN_EASE, ease - 0.2)
        interval = 0  # due again today
        lapses += 1
        reps = 0
    elif grade == "good":
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 3
        else:
            interval = round(interval * ease)
        reps += 1
    elif grade == "easy":
        interval = 2 if reps == 0 else round(max(interval, 1) * ease * 1.3)
        ease = min(MAX_EASE, ease + 0.15)
        reps += 1
    else:
        raise ValueError(f"bad grade: {grade!r}")

    interval = max(0, int(interval))
    return {
        "ease": round(ease, 2),
        "interval": interval,
        "reps": reps,
        "lapses": lapses,
        "due": (today + dt.timedelta(days=interval)).isoformat(),
        "last_reviewed": today.isoformat(),
        "graduated": interval >= GRADUATE_INTERVAL,
    }
