"""French pronunciation (IPA). No LLM.

Word-level: Lexique.org (inflected forms + film frequency), converted from its
SAMPA-like `phon` code to IPA. Fallback / clause-level (liaison): espeak-ng via
`phonemizer` when available — degrades to None if espeak isn't installed.

Audio remains ground truth; this is a diagnostic aid for shadowing.
"""

from __future__ import annotations

import gzip
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "lexique_fr.tsv.gz"

# Lexique `phon` code -> IPA. Verified against known forms (dollar dolaR, grand
# gR@, bonjour b§ZuR, oignon ON§, huit 8it, camping k@piG, …).
_PHON_IPA = {
    # vowels
    "a": "a", "A": "ɑ", "e": "e", "E": "ɛ", "i": "i", "o": "o", "O": "ɔ",
    "u": "u", "y": "y", "2": "ø", "9": "œ", "°": "ə",
    # nasal vowels
    "@": "ɑ̃", "5": "ɛ̃", "1": "œ̃", "§": "ɔ̃",
    # semi-vowels
    "j": "j", "w": "w", "8": "ɥ",
    # consonants
    "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "g": "ɡ", "f": "f",
    "v": "v", "s": "s", "z": "z", "S": "ʃ", "Z": "ʒ", "m": "m", "n": "n",
    "N": "ɲ", "G": "ŋ", "R": "ʁ", "l": "l", "x": "x",
}

_STRIP = " .,;:!?«»\"'()[]…—–- "


def sampa_to_ipa(phon: str) -> str:
    return "".join(_PHON_IPA.get(c, c) for c in phon)


@lru_cache(maxsize=1)
def _lex() -> dict[str, str]:
    """form (lowercased) -> IPA, keeping the highest-frequency reading."""
    best: dict[str, tuple[float, str]] = {}
    with gzip.open(DATA, "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3 or not parts[1]:
                continue
            ortho, phon, freq = parts[0], parts[1], parts[2]
            try:
                fr = float(freq)
            except ValueError:
                fr = 0.0
            cur = best.get(ortho)
            if cur is None or fr > cur[0]:
                best[ortho] = (fr, sampa_to_ipa(phon))
    return {k: v[1] for k, v in best.items()}


def _phonemize(text: str) -> str | None:
    """espeak-ng G2P via phonemizer; None if unavailable (graceful)."""
    text = text.strip()
    if not text:
        return None
    try:
        from phonemizer import phonemize

        out = phonemize(
            text, language="fr-fr", backend="espeak",
            strip=True, with_stress=False, njobs=1,
            # Foreign words make espeak switch language and emit "(en)…(fr)"
            # markers; drop the flags, keep the phonemes.
            language_switch="remove-flags",
        ).strip()
        return out or None
    except Exception:
        return None


def word_ipa(form: str) -> str | None:
    """IPA for a single token. Lexique first, espeak fallback for OOV."""
    key = form.strip().lower().strip(_STRIP)
    if not key:
        return None
    hit = _lex().get(key)
    if hit:
        return hit
    return _phonemize(key)


def clause_ipa(text: str) -> str | None:
    """Phrase-level IPA (captures approximate liaison). None without espeak."""
    return _phonemize(text)
