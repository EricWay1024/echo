# écho — the two-pass learning workflow (design philosophy)

How the app is actually used, agreed 2026-06-07. Every imported video goes
through two passes. The app models them as two explicit **modes** over the same
rectified+segmented transcript (Slice 2), with opposite affordances.

## Pass 1 — Shadow mode (form / pronunciation). No LLM.
Goal: shadow the audio, fix articulation, flag what to revisit. Meaning is
deliberately backgrounded.

- **Audio is ground truth; IPA is a diagnostic aid, not the target.** Word-level
  IPA in isolation lies in French (liaison/enchaînement: `les échos` → [le.ze.ko]).
  So: **clause-level IPA** by default, word-level on click; always on-demand
  (try to mimic from audio first, reveal IPA to diagnose a specific failure).
- **Pronunciation source (no LLM):** Lexique.org for dictionary-quality IPA of
  inflected forms (+ frequency), espeak-ng/phonemizer as G2P fallback for OOV and
  for phrase-level transcription. Lexique first, espeak fallback.
- **Step/repeat:** "step mode" auto-pauses at each clause end; **Space** resumes
  into the next clause (and pauses at its end). No inserted-silence estimation.
  Reuses existing clause loops + speed control.
- **Two mark types** (attention in this pass is on sound, not meaning):
  - 🔊 pronunciation-trouble → pronunciation drilling / audio cards.
  - ❓ meaning-unknown → carried into Pass 2.
  - Soft nudge toward *selective* marking (tolerating ambiguity is a B2 skill;
    over-marking explodes the card load).

## Pass 2 — Study mode (meaning / vocabulary). LLM, tiered by value.
Goal: comprehend, then turn the Pass-1 ❓ marks into durable cards.

- **Translations reveal-on-demand, not always-on.** Always-visible translation
  becomes a crutch — eyes read the gloss, skip parsing the French. Show the
  clause, attempt comprehension, *then* reveal (reuse hide/reveal). Bonus: only
  pay to translate clauses you reveal.
- **Model tiering by value, not uniformly cheap:** Haiku for bulk clause
  translation (gist, on-demand, cached); Sonnet for marked-item explanations and
  card suggestions (low-volume, learning-critical — don't cheap out on nuance).
- **Explanations** routed per learner: English for cognates / faux amis / grammar
  metalanguage; 中文 for fast direct glosses (faux amis are the highest-error-value
  items for an en+zh speaker). For a marked conjugated word: lemma + the form's
  role + the collocation in context, not a dictionary dump.
- **Translation language configurable** (default 中文 for reading speed).

## Card layer (the SRS payoff) — Pass 2 output.
The LLM infers card-worthy items from the ❓ marks; you curate (accept/reject);
export. Best practices baked in:
- **Atomic** cards (one idea each — minimum-information principle).
- **Cloze over front/back**, using the actual sentence you shadowed.
- **Collocations over bare words** (`prendre une décision`, not `décision`).
- **Card type by mark:** vocab/collocation → cloze; grammar/structure → pattern
  card; idiom/usage/register → usage card. The LLM diagnoses *why* a sentence was
  marked and picks the type.
- **Audio cards** (the edge): `ffmpeg`-clip the exact clause from the cached
  audio, embed it (listen → recall). Requires `.apkg` export (genanki), not TSV.
- **Dedup against `lexemes`:** never suggest a card for a word already marked
  "known" in an earlier video. Cross-video memory is what makes video #20 faster
  than #1.
- **Rank and cap** suggestions (frequency × above-level × faux-ami), each with a
  one-line rationale. SRS only pays off if you actually review.

## Marks lifecycle (closes the loop)
`unknown` (Pass-1 mark) → `learning` (card made) → `known` (matured / user-set),
propagated to `lexemes` so future videos pre-grey what you already know.

## Resolved decisions (2026-06-07)
1. Pronunciation source: **Lexique.org first, espeak-ng/phonemizer fallback**.
2. **Two mark types** (pronunciation 🔊 vs meaning ❓).
3. Translations **reveal-on-demand**.
4. Export: **`.apkg`** (enables audio + cloze cards).
5. Repeat: **auto-pause at clause end + Space to resume** (no inserted silence).

## Reshaped roadmap (supersedes Slices 3–4 in initial.md)
- **Slice 3 — Shadow mode / pronunciation pass.** IPA (Lexique+espeak), clause &
  word IPA on click, step mode, two-type marking. *No LLM.* (Pass 1)
- **Slice 4 — Study mode / comprehension pass.** Reveal-on-demand clause
  translations (Haiku), routed explanations of ❓ marks (Sonnet), lexeme tracking.
  (Pass 2 a–c)
- **Slice 5 — Card layer.** Mark→card inference + rationale, curation
  (accept/reject), `.apkg` export with audio + cloze, lexeme dedup. (Pass 2 d)

Detailed task breakdowns are written just-in-time per slice (see `slice-3.md`).
