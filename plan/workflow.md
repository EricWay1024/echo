# écho — the learning workflow (design philosophy)

How the app is used, agreed 2026-06-07 (revised to a **single unified flow** — the
earlier two-pass split is dropped; see history at the bottom).

## One pass, meaning opt-in
Everything happens in one view over the rectified+segmented transcript (Slice 2).
There are no Shadow/Study modes. The discipline that the two passes encoded —
**form first, meaning second** — is preserved not by enforcing modes but by
keeping everything meaning-related **off by default and opt-in**:

- Translations are hidden until you click a sentence.
- Explanations appear only when you deliberately mark something.

So "shadow the video, then go back for meaning" is a habit you choose, not a mode
the UI imposes. Nothing meaning-related is ambient.

## Pronunciation (Slice 3 — done, no LLM)
- IPA on word click (Lexique + espeak; clause-level liaison), on-demand.
- Step mode (auto-pause at clause end; Space resumes), clause loops, speed.
- Audio is ground truth; IPA is a diagnostic aid.

## Translation (on demand, per clause)
- Each clause has a small reveal/translate button → translate **that one clause**
  (never the whole passage), cached per (video, clause, lang). Hidden by default.
- **Haiku** (cheap) for gist; language configurable, default 中文 (faster to read),
  EN available.

## Marking is instant; explanations are batched on a Review page
Marking must not break shadowing flow, so it does **no LLM work** — select text →
🔊/❓ + optional note → confirm just records it (fast). After shadowing, open the
**Review page**, which **batch-generates explanations + cards for all ❓ marks**
(concurrency-limited, with progress), then lets you curate and export. (A single
inline ~13s Sonnet call per mark was too disruptive — revised 2026-06-07.)

Each ❓ mark, when explained on the Review page, yields one **Sonnet** result for
the span in its clause context (+ user profile + the note):
  - **explanation**: lemma + the inflected form's role + the collocation, routed
    by language (EN for cognates/faux-amis/grammar metalanguage, 中文 for direct
    glosses), calibrated to B2 (skip basics; collocations, register, idioms).
  - **suggested Anki cards** (shown inline to accept/reject), built right:
    - atomic (one idea each); cloze over front/back using the real clause;
      collocations over bare words; card type by what was marked (vocab → cloze,
      grammar → pattern, idiom/usage → usage card).
- A **🔊 pron** mark is a flag (no LLM); it becomes an **audio card** suggestion at
  export (clip the clause from the cached audio + IPA).

## Cards & lexemes
- Suggestions are stored at mark time; you curate (accept/reject); accepted cards
  export to **`.apkg`** (genanki) with audio + cloze (TSV fallback, text-only).
- **Dedup against `lexemes`:** don't suggest cards for words already `known` from
  an earlier video — cross-video memory makes video #20 faster than #1.
- **Rank/cap** suggestions (frequency × above-level × faux-ami) with a one-line
  rationale each; SRS only pays off if you actually review.
- Marks lifecycle: `unknown` (mark) → `learning` (card made) → `known`
  (matured / user-set), propagated to `lexemes`.

## Resolved decisions
1. Pronunciation: Lexique first, espeak-ng fallback. *(done)*
2. Two mark types: 🔊 pron / ❓ meaning, with an optional note. *(done)*
3. Translation **on demand per clause** (click), hidden by default — Haiku.
4. Export `.apkg` (audio + cloze).
5. Repeat: auto-pause at clause end + Space to resume. *(done)*
6. **Single unified flow** (no two-pass modes).
7. **Marking is instant (no LLM); explanations + cards are batch-generated on a
   dedicated Review page** after shadowing — inline per-mark LLM latency (~13s)
   broke flow. Translation latency is kept on purpose: the beat of friction nudges
   active comprehension before revealing.

## Roadmap
- **Slice 3 — Pronunciation** (IPA, marks, step). ✅
- **Slice 4 — Meaning** (revised): per-clause translation on click (Haiku);
  ❓ mark → explanation + suggested cards (Sonnet); lexeme tracking.
- **Slice 5 — Cards out**: curation (accept/reject), `.apkg` export with audio +
  cloze, pron→audio cards, lexeme dedup of suggestions.

## History
Originally specced as two passes (Shadow then Study) — see `git log` for the
earlier `workflow.md`. Collapsed into one opt-in flow on 2026-06-07: simpler, and
meaning stays opt-in so the anti-crutch property survives without enforced modes.
