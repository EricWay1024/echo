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

_LANG_NAMES = {"zh": "Mandarin Chinese (中文)", "en": "English", "yue": "Cantonese"}


def _lang_name(code: str) -> str:
    return _LANG_NAMES.get(code, code)


# Base prompt (no f-string: keeps the literal {{c1::target}} Anki cloze syntax).
EXPLAIN_SYSTEM_BASE = """\
You help a French learner understand a span they marked in a transcript, then \
propose Anki cards. Calibrate to the learner's level (given): skip basics; focus \
on collocations, register, faux amis, spoken contractions, and idioms.

Return JSON with keys:
- lemma: dictionary form of the key word (you lemmatize).
- pos: part of speech.
- lang: the language code you wrote the explanation in.
- explanation: 1-3 sentences — give the lemma, the role of the inflected form \
here, and the collocation/usage in this context.
- cards: 1-3 ATOMIC Anki suggestions (one idea each). Prefer a cloze built from \
the REAL clause using Anki syntax {{c1::target}} on the front and the answer + a \
short gloss on the back. Prefer collocations over bare words. kind ∈ \
cloze|vocab|grammar|usage. Each card: front, back, and a one-line rationale.

Output ONLY a JSON object with these keys. No prose, no markdown, no code fences."""


def _explain_system(lang_name: str) -> str:
    return (
        f"Language rules (STRICT):\n"
        f"- Write the `explanation`, every card `back`, every `rationale`, and any "
        f"question/prompt text on a card `front` in {lang_name}.\n"
        f"- The ONLY French permitted is the actual French being studied: the cloze "
        f"`front` (the real French clause) and French words/phrases you quote.\n"
        f"- Never write explanations, glosses, prompts, or rationales in French or "
        f"any language other than {lang_name}.\n\n"
        + EXPLAIN_SYSTEM_BASE
    )


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
                        note: str | None = None,
                        known: list[str] | None = None) -> dict:
    user = (f"Marked span: «{span_text}»\nIts clause: «{clause}»\n"
            + (f"Learner's note: {note}\n" if note else "")
            + f"Learner profile: {profile}")
    if known:
        user += ("\nAlready known (do NOT make cards that merely re-teach these "
                 "words; only card genuinely new value): " + ", ".join(known[:200]))
    lang = getattr(cfg, "explain_lang", "zh")
    system = _explain_system(_lang_name(lang))
    client = _client(cfg)
    extra = ""
    for _ in (1, 2):
        msg = client.messages.create(
            model=cfg.llm_model,
            max_tokens=4000,
            system=system + extra,
            messages=[{"role": "user", "content": user}],
        )
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            data = _loads_loose(text)
            for k in ("lemma", "pos", "explanation"):
                if not data.get(k):
                    raise ValueError(f"missing {k}")
            data["cards"] = data.get("cards", [])[:3]
            data["lang"] = lang  # fixed by config, not model-chosen
            return data
        except (ValueError, json.JSONDecodeError):
            extra = "\n\nReturn ONLY a valid JSON object — no code fences, no prose."
    raise RuntimeError("explain: could not parse a valid JSON response")


def profile_str(cfg) -> str:
    user = cfg.raw.get("user", {})
    known = ", ".join(f"{k.get('lang')} {k.get('level')}" for k in user.get("known", []))
    tgt = user.get("target", {})
    return f"known: {known}; learning: {tgt.get('lang')} {tgt.get('level')}"
