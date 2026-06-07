"""Derive the rectified, segmented view from immutable words + LLM ops.

The invariant: a rendered token's text may come from an edit, but its TIMING
always derives from the source word span — so click-to-seek, karaoke highlight,
and clause loops keep working on edited text.

    replace [s,e] -> one token: edit.text, time = [words[s].start, words[e].end]
    delete  [s,e] -> nothing
    untouched word i -> one token from words[i]

Tokens are grouped into segments (which tile [0, N-1] by word index); a token
joins the segment containing its source-span start. Each segment carries its own
[start_ms, end_ms] (from word timing) for A-B looping.
"""

from __future__ import annotations


def _word_end(w: dict) -> int:
    return w["start_ms"] + w["dur_ms"]


def render(words: list[dict], edits: list[dict], segments: list[dict]) -> list[dict]:
    """Return segments with nested, timed tokens. Assumes validated input
    (edits non-overlapping/in-range; segments tile [0, N-1])."""
    n = len(words)
    edit_at = {e["span_start"]: e for e in edits}

    # Pass 1: build the flat, ordered token list with source spans + timing.
    tokens: list[dict] = []
    i = 0
    while i < n:
        e = edit_at.get(i)
        if e is not None:
            s, end = e["span_start"], e["span_end"]
            if e["op"] == "replace":
                start_ms = words[s]["start_ms"]
                text = e["text"]
                # Tokens carry a leading space as the word boundary (json3 style);
                # the LLM usually drops it on replacements. Restore it when the
                # replaced span's first word had one, so tokens don't glue.
                if words[s]["text"][:1].isspace() and not text[:1].isspace():
                    text = " " + text
                tokens.append({
                    "text": text,
                    "src_start": s,
                    "src_end": end,
                    "start_ms": start_ms,
                    "dur_ms": max(1, _word_end(words[end]) - start_ms),
                })
            # delete -> emit nothing
            i = end + 1
        else:
            w = words[i]
            tokens.append({
                "text": w["text"],
                "src_start": i,
                "src_end": i,
                "start_ms": w["start_ms"],
                "dur_ms": w["dur_ms"],
            })
            i += 1

    # Pass 2: drop tokens into segments by source-span start (segments are sorted
    # and tile the word indices, so a single forward walk suffices).
    out: list[dict] = []
    for seg in segments:
        s, end = seg["span_start"], seg["span_end"]
        out.append({
            "seg_idx": seg["seg_idx"],
            "kind": seg.get("kind"),
            "span_start": s,
            "span_end": end,
            "start_ms": words[s]["start_ms"],
            "end_ms": _word_end(words[end]),
            "tokens": [],
        })

    si = 0
    for tok in tokens:
        # advance to the segment whose word range contains this token's src_start
        while si < len(out) and tok["src_start"] > out[si]["span_end"]:
            si += 1
        if si >= len(out):
            break
        out[si]["tokens"].append(tok)

    return out
