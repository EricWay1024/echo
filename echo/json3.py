"""Parse YouTube json3 auto-captions into a flat, immutable word array.

json3 shape: top-level `events[]`; each event has `tStartMs`, `dDurationMs`,
and `segs[]`. Each seg has `utf8` (the token, usually with a leading space),
an optional `tOffsetMs` (relative to the event start), and `acAsrConf`.

Quirks handled:
- A seg with utf8 == "\n" (or all-whitespace) is a line break, not a word.
- YouTube drops the inter-word space at line breaks (the newline seg carried
  it), so two line-adjacent tokens would collide ("Guerre"+"mondiale," ->
  "Guerremondiale"). We reinsert a single space at those boundaries.
- French elisions ("c'est", "l'huile") are single segs, so they're untouched.
- Word start = event.tStartMs + seg.tOffsetMs. Word duration is gapless:
  next word's start minus this word's start (the last word gets its event's
  remaining duration).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Fallback duration (ms) for the final word if its event has no usable span.
_LAST_WORD_FALLBACK_MS = 600


@dataclass(frozen=True)
class Word:
    idx: int
    text: str       # display text, including any leading space
    start_ms: int
    dur_ms: int


def parse(data: dict) -> list[Word]:
    """json3 dict -> ordered, contiguous list of Words."""
    # Pass 1: collect real tokens with absolute start + a per-token flag marking
    # whether a line break preceded it.
    texts: list[str] = []
    starts: list[int] = []
    ends: list[int] = []          # event end, for last-word duration
    boundary_before: list[bool] = []
    pending_boundary = False

    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        base = int(event.get("tStartMs", 0))
        event_end = base + int(event.get("dDurationMs", 0))
        for seg in segs:
            t = seg.get("utf8", "")
            if t == "\n" or t.strip() == "":
                pending_boundary = True
                continue
            texts.append(t)
            starts.append(base + int(seg.get("tOffsetMs", 0)))
            ends.append(event_end)
            boundary_before.append(pending_boundary)
            pending_boundary = False

    n = len(texts)
    if n == 0:
        return []

    # Pass 2: reinsert dropped spaces at line boundaries.
    texts[0] = texts[0].lstrip()
    for i in range(1, n):
        if (
            boundary_before[i]
            and not texts[i][:1].isspace()
            and not texts[i - 1][-1:].isspace()
        ):
            texts[i] = " " + texts[i]

    # Pass 3: gapless durations.
    words: list[Word] = []
    for i in range(n):
        start = starts[i]
        if i + 1 < n:
            end = starts[i + 1]
        else:
            end = ends[i] if ends[i] > start else start + _LAST_WORD_FALLBACK_MS
        words.append(Word(idx=i, text=texts[i], start_ms=start, dur_ms=max(1, end - start)))
    return words


def parse_file(path: str | Path) -> list[Word]:
    with open(path, encoding="utf-8") as f:
        return parse(json.load(f))


def render(words: list[Word]) -> str:
    """Reconstruct the transcript text by concatenating tokens."""
    return "".join(w.text for w in words)
