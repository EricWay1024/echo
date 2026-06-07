"""Meaning layer: per-clause translation (Haiku) and mark explanation + card
suggestions (Sonnet). Both go through the user's key; results are cached by the
caller (db) and never re-asked."""

from __future__ import annotations

import json

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "lemma": {"type": "string"},
        "pos": {"type": "string"},
        "lang": {"type": "string", "enum": ["en", "zh"]},
        "explanation": {"type": "string"},
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string",
                             "enum": ["cloze", "vocab", "grammar", "usage"]},
                    "front": {"type": "string"},
                    "back": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["kind", "front", "back", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["lemma", "pos", "lang", "explanation", "cards"],
    "additionalProperties": False,
}

EXPLAIN_SYSTEM = """\
You help a French learner understand a span they marked in a transcript, then \
propose Anki cards. Calibrate to the learner's level (given): skip basics; focus \
on collocations, register, faux amis, spoken contractions, and idioms.

Return JSON:
- lemma: dictionary form of the key word (you lemmatize).
- pos: part of speech.
- lang: the language to explain IN — choose the shortest path: "en" for cognates, \
faux amis, and grammar metalanguage; "zh" (Mandarin) for direct glosses.
- explanation: 1-3 sentences IN THAT LANGUAGE — give the lemma, the role of the \
inflected form here, and the collocation/usage in this context.
- cards: 1-3 ATOMIC Anki suggestions (one idea each). Prefer a cloze built from \
the REAL clause using Anki syntax {{c1::target}} on the front and the answer + a \
short gloss on the back. Prefer collocations over bare words. kind ∈ \
cloze|vocab|grammar|usage. Each card: front, back, and a one-line rationale.

Output ONLY a JSON object with keys lemma, pos, lang, explanation, cards (an \
array of {kind, front, back, rationale}). No prose, no markdown, no code fences."""


def _client(cfg):
    import anthropic

    return anthropic.Anthropic(api_key=cfg.api_key)


def translate_clause(cfg, text: str, lang: str) -> str:
    target = "Mandarin Chinese" if lang == "zh" else "English"
    msg = _client(cfg).messages.create(
        model=cfg.llm_translate_model,
        max_tokens=1000,
        system=(f"Translate the French clause into {target}. Output ONLY the "
                "translation — natural and concise, the gist for a B2 learner. "
                "No quotes, no notes."),
        messages=[{"role": "user", "content": text}],
    )
    return next((b.text for b in msg.content if b.type == "text"), "").strip()


def _loads_loose(text: str) -> dict:
    """Parse the first {...} object — tolerates code fences / surrounding prose.
    (Strict output_config makes the model satisfice on generative fields, so we
    let it write freely and extract the JSON ourselves.)"""
    a, b = text.find("{"), text.rfind("}")
    if a == -1 or b <= a:
        raise ValueError("no JSON object in response")
    return json.loads(text[a:b + 1])


def explain_and_suggest(cfg, span_text: str, clause: str, profile: str,
                        note: str | None = None) -> dict:
    user = (f"Marked span: «{span_text}»\nIts clause: «{clause}»\n"
            + (f"Learner's note: {note}\n" if note else "")
            + f"Learner profile: {profile}")
    client = _client(cfg)
    extra = ""
    for _ in (1, 2):
        msg = client.messages.create(
            model=cfg.llm_model,
            max_tokens=4000,
            system=EXPLAIN_SYSTEM + extra,
            messages=[{"role": "user", "content": user}],
        )
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            data = _loads_loose(text)
            for k in ("lemma", "pos", "lang", "explanation"):
                if not data.get(k):
                    raise ValueError(f"missing {k}")
            data["cards"] = data.get("cards", [])[:3]
            return data
        except (ValueError, json.JSONDecodeError):
            extra = "\n\nReturn ONLY a valid JSON object — no code fences, no prose."
    raise RuntimeError("explain: could not parse a valid JSON response")


def profile_str(cfg) -> str:
    user = cfg.raw.get("user", {})
    known = ", ".join(f"{k.get('lang')} {k.get('level')}" for k in user.get("known", []))
    tgt = user.get("target", {})
    return f"known: {known}; learning: {tgt.get('lang')} {tgt.get('level')}"
