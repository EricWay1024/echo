"""Rectify + segment: the single LLM pass over a video's words.

Core invariant: the model returns ONLY ops over word indices (replace/delete)
and segments that tile [0, N-1] — never transcript prose. We validate on
receipt and retry once with the errors appended. One call per video; cached.
"""

from __future__ import annotations

import json

from . import db

# JSON-schema for structured output. (Span length is validated in code — the
# structured-output schema layer doesn't support array-length constraints.)
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": ["replace", "delete"]},
                    "span": {"type": "array", "items": {"type": "integer"}},
                    "text": {"type": "string"},
                },
                "required": ["op", "span", "text"],
                "additionalProperties": False,
            },
        },
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "span": {"type": "array", "items": {"type": "integer"}},
                    "kind": {"type": "string"},
                },
                "required": ["span", "kind"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["edits", "segments"],
    "additionalProperties": False,
}

SYSTEM = """\
You rectify and segment an automatic-speech-recognition transcript for a \
language learner. You receive the transcript as an ordered list of word tokens, \
each with an integer index.

You MUST NOT return transcript text as prose. Return only:

1. `edits` — operations over word-index spans that fix genuine ASR errors:
   - `op`: "replace" or "delete".
   - `span`: [start, end] inclusive ORIGINAL word indices.
   - `text`: for "replace", the corrected text for that whole span (it may be \
multiple words; a word the ASR dropped is handled by replacing an adjacent span \
with the longer correct text). For "delete", use "".
   - Fix only true mistranscriptions, wrong proper nouns, and domain terms. Do \
NOT paraphrase, re-punctuate for style, or "improve" already-correct text. \
Preserve the speaker's actual words.
   - Edits must be non-overlapping and within [0, N-1]. Most transcripts need \
few edits — when unsure, leave the text alone.

2. `segments` — a list that tiles the ENTIRE transcript [0, N-1] in order, with \
no gaps and no overlaps, splitting it into natural clauses for shadowing:
   - `span`: [start, end] inclusive ORIGINAL word indices.
   - `kind`: "clause" (or "sentence"/"phrase" if more apt).
   - Put boundaries at clause/sentence breaks so each segment is a natural unit \
to repeat aloud. Every index 0..N-1 must belong to exactly one segment.

Use the video title, channel, and description to fix proper nouns and jargon."""


def build_user_prompt(video: dict, words: list[dict], extra: str = "") -> str:
    listing = "\n".join(f"{w['idx']}\t{w['text']}" for w in words)
    desc = (video.get("description") or "")[:1500]
    return (
        f"Video title: {video.get('title','')}\n"
        f"Channel: {video.get('channel','')}\n"
        f"Description: {desc}\n\n"
        f"Transcript ({len(words)} words) as `index<TAB>text` "
        f"(text keeps original leading spaces):\n{listing}"
        + (f"\n\n{extra}" if extra else "")
    )


def validate(data: dict, n: int) -> list[str]:
    """Return a list of human-readable validation errors ([] == valid)."""
    errs: list[str] = []
    edits = data.get("edits", [])
    segments = data.get("segments", [])

    # --- edits: in range, well-formed, non-overlapping ---
    spans = []
    for k, e in enumerate(edits):
        span = e.get("span")
        if not (isinstance(span, list) and len(span) == 2
                and all(isinstance(x, int) for x in span)):
            errs.append(f"edit[{k}]: span must be [start, end] integers")
            continue
        s, end = span
        if not (0 <= s <= end <= n - 1):
            errs.append(f"edit[{k}]: span {span} out of range [0,{n-1}] or start>end")
            continue
        if e.get("op") == "replace" and not (e.get("text") or "").strip():
            errs.append(f"edit[{k}]: replace span {span} has empty text")
        spans.append((s, end, k))
    spans.sort()
    for a, b in zip(spans, spans[1:]):
        if b[0] <= a[1]:
            errs.append(f"edits overlap: span ending {a[1]} and span starting {b[0]}")

    # --- segments: tile [0, n-1] exactly, in order ---
    if not segments:
        errs.append("segments is empty; must tile [0, N-1]")
    else:
        expected = 0
        for k, seg in enumerate(segments):
            span = seg.get("span")
            if not (isinstance(span, list) and len(span) == 2
                    and all(isinstance(x, int) for x in span)):
                errs.append(f"segment[{k}]: span must be [start, end] integers")
                return errs  # can't continue tiling check meaningfully
            s, end = span
            if s != expected:
                errs.append(
                    f"segment[{k}]: starts at {s}, expected {expected} "
                    "(gap or overlap)")
            if end < s:
                errs.append(f"segment[{k}]: end {end} < start {s}")
            expected = end + 1
        if expected != n:
            errs.append(f"segments cover [0,{expected-1}] but transcript is [0,{n-1}]")
    return errs


def _call_llm(cfg, system: str, user: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=cfg.api_key)
    with client.messages.stream(
        model=cfg.llm_model,
        max_tokens=48000,
        # Thinking disabled: this is a bounded structured extraction over a long
        # input — adaptive thinking blew the token budget without need. Structured
        # output forces the response to be just the JSON. Re-enable if edit
        # quality proves insufficient.
        thinking={"type": "disabled"},
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("LLM hit max_tokens; transcript too long for one pass")
    text = next((b.text for b in msg.content if b.type == "text"), None)
    if text is None:
        raise RuntimeError("LLM returned no text block")
    return json.loads(text)


def run(conn, cfg, video_id: str, *, force: bool = False) -> dict:
    """Run (or return cached) rectify+segment for one video."""
    if not force and db.load_segments(conn, video_id):
        return {"cached": True,
                "edits": len(db.load_edits(conn, video_id)),
                "segments": len(db.load_segments(conn, video_id))}

    video = conn.execute(
        "SELECT id, title, channel, description FROM videos WHERE id = ?",
        (video_id,),
    ).fetchone()
    if video is None:
        raise ValueError(f"unknown video {video_id}")
    video = dict(video)
    words = db.load_words(conn, video_id)
    n = len(words)
    if n == 0:
        raise ValueError("video has no words")

    extra = ""
    last_errs: list[str] = []
    for attempt in (1, 2):
        data = _call_llm(cfg, SYSTEM, build_user_prompt(video, words, extra))
        last_errs = validate(data, n)
        if not last_errs:
            db.store_pipeline(conn, video_id, data["edits"], data["segments"])
            return {"cached": False, "attempt": attempt,
                    "edits": len(data["edits"]),
                    "segments": len(data["segments"])}
        extra = ("A previous attempt failed validation with these errors — "
                 "fix them and return corrected JSON:\n- " + "\n- ".join(last_errs))

    raise RuntimeError("rectify+segment failed validation twice: "
                       + "; ".join(last_errs))
