# Slice 6 — Built-in spaced-repetition review (in-context)

Goal: review accepted cards inside the app, **in context** — replay the clause
audio as the prompt, reveal sentence + IPA + explanation, and jump back to the
source video at that moment. A simple SM-2-lite scheduler. Anki export stays.

## Decisions
- **SM-2-lite**, 3 grades (Again / Good / Easy). Not FSRS — "good enough".
- **Export stays** alongside (built-in = at-the-desk in-context; Anki = mobile/sync).
- Card graduates (interval ≥ 21d) → its lemma becomes `known` (re-links the
  `lexemes` lifecycle).

## Backend
- [ ] schema: add SRS columns to `cards` — `due` (date), `interval` (days),
  `ease`, `reps`, `lapses`, `last_reviewed`. Auto-migrate (ALTER) in `init_db`.
- [ ] `srs.py` (pure, tested): `schedule(state, grade, today) -> new state`.
  - again: ease−0.2 (floor 1.3), interval 0 (due today), lapses+1, reps 0.
  - good: reps0→1d, reps1→3d, else round(interval×ease); reps+1.
  - easy: reps0→2d else round(interval×ease×1.3); ease+0.15 (cap 3.0); reps+1.
- [ ] db: `due_cards(today)` (accepted, due null or ≤ today), `get_card`,
  `update_card_schedule`, `count_due`.
- [ ] API:
  - `GET /review` → due items across videos, each joined with its clause
    (start/end ms + text) and explanation (lemma/pos/body). Render computed once
    per video.
  - `POST /cards/{id}/review {grade}` → reschedule; graduate → lemma `known`.

## Frontend
- [ ] `Revise.jsx` — one card at a time: front (cloze blanked + 中文 hint), ▶ play
  the clause, *reveal* → answer + back + explanation + "open in player"; grade
  Again/Good/Easy → next.
- [ ] `App.jsx` — a "revise (N)" entry in the top bar (due count); a `revise`
  view; "open in player" hands off to `Player` at the clause timestamp.
- [ ] `Player.jsx` — accept a `startMs` (open-at-timestamp from review); while
  "peeking" from review, don't overwrite the saved resume point.

## Verification
- Offline: `srs.schedule` transitions (again/good/easy progressions, graduate).
- Live-ish: a due card appears in `GET /review` with clause + explanation; grading
  reschedules; open-in-player seeks to the clause.

## Out of scope
Stats dashboards, leeches, custom steps, FSRS, sync. Keep v1 minimal.
