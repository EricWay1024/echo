# Slice 5 — Cards out: curation, .apkg export, audio cards, lexeme dedup

Goal (from `workflow.md`): **curate the suggested cards, export to Anki, and stop
re-suggesting words you already know.** Closes the loop into SRS.

> **Status (2026-06-07):** COMPLETE & verified. 27 tests. Live `.apkg` export
> built a valid Anki zip (collection + embedded audio clip from a 🔊 pron mark +
> cloze card); TSV export works. Cards drawer curates (accept/reject) + exports;
> explain panel has "✓ known" → lexeme dedup in future explanations. **Needs a
> browser pass + a real Anki import to confirm cards render.** This closes the
> full loop: import → play → rectify → shadow → meaning → curated Anki deck.

## Backend
- [ ] **B1 — dep:** `genanki` (.apkg authoring).
- [ ] **B2 — `export.py`:**
  - `build_apkg(cfg, conn, video_id)` → temp `.apkg`:
    - accepted **cloze** cards → Cloze note (`{{c1::}}` front, gloss back).
    - accepted **vocab/grammar/usage** → Basic note (front/back, rationale tag).
    - **🔊 pron marks → audio cards**: `ffmpeg`-clip the enclosing clause from the
      cached opus, embed as media; Front `[sound:clip]`, Back = clause text + IPA.
  - `build_tsv(conn, video_id)` → text-only fallback (front\tback) for accepted
    cards (no audio).
- [ ] **B3 — lexeme dedup:** pass `known` lemmas (from `lexemes`) into the explain
  prompt so it won't re-suggest cards for words already known. Endpoint
  `POST /lexemes` `{lemma, lang, status}` to set a lemma `known`.
- [ ] **B4 — API:** `GET /videos/{id}/export?format=apkg|tsv` → FileResponse
  download; `POST /lexemes`.

## Frontend
- [ ] **F1 — cards panel:** a "cards" toggle opens a drawer listing all cards for
  the video (suggested/accepted/rejected) with accept/reject, plus a count of
  🔊 pron marks → audio cards on export.
- [ ] **F2 — export buttons:** download `.apkg` / `.tsv` for the video.
- [ ] **F3 — known:** in the explain panel, "I know «lemma»" → `POST /lexemes`
  known (future explanations skip re-teaching it).

## Verification
- Offline: build_apkg produces a valid (non-empty, sqlite-backed) `.apkg` zip with
  the expected notes; build_tsv content; lexeme known round-trip + dedup prompt.
- Live (small): explain a span with a `known` lemma in the list → confirm it's not
  re-suggested.

## Risks
- `.apkg` is a zip of an Anki sqlite + media; stable model/deck IDs matter (fixed
  constants) so re-imports update rather than duplicate.
- ffmpeg clip with `-c copy` at arbitrary offsets is approximate but fine for a
  clause; opus stream-copy keeps it instant.
- Audio cards are generated from pron marks at export (not curated as rows) — the
  mark is the deliberate choice.

## Done = the full loop
import → fetch/play → rectify/segment → shadow (IPA, marks, step) → meaning
(translate, explain) → **curated Anki deck with audio + cloze**, deduped across
videos.
