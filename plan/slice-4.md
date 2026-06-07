# Slice 4 — Meaning: per-clause translation + mark→explain→suggest (actionable)

Goal (revised, single-flow per `workflow.md`): **click a clause to translate it;
mark a ❓ span to get an explanation AND suggested Anki cards immediately.** No
mode split. Curation + export are Slice 5.

> **Status (2026-06-07):** COMPLETE & live-verified. 24 tests. Haiku translation
> is excellent (clause→中文); explanation needed a fix — strict `output_config`
> made Sonnet satisfice (degenerate "vaciller 意为", no cards), so explain now uses
> free-form generation + loose JSON parse + retry → full B2 explanation (lemma,
> form role, collocation, faux-ami contrast) + 3 atomic cards (cloze on real
> clause, nuance, production). Frontend: single view, 🌐 per-clause translate,
> mark→explain panel with accept/reject. **Needs a browser pass.**

## Locked decisions
- Translation: **on demand per clause** (small button), hidden by default, cached
  per (video, seg, lang). **Haiku** (`config.llm_translate_model`). Default 中文.
- Marking a **❓ meaning** span → one **Sonnet** (`config.llm_model`) call returns
  `{lemma, pos, lang∈{en,zh}, explanation, cards[]}`; explanation routed by lang;
  cards atomic (cloze using the real clause, collocations, type by mark).
- **🔊 pron** marks stay flags (no LLM); audio cards come at export (Slice 5).
- Explanation + suggested cards are stored at mark time; curation/export = Slice 5.

## Backend
- [x] **B1 — config:** `[llm].translate_model` default `claude-haiku-4-5`;
  explanations use `config.llm_model`. (done)
- [ ] **B2 — schema + db:**
  - `translations(video_id, seg_idx, lang, text)` PK `(video_id, seg_idx, lang)`.
  - `explanations(video_id, span_start, span_end, lang, lemma, pos, body, created_at)`
    PK `(video_id, span_start, span_end)`.
  - `cards(id, video_id, span_start, span_end, kind, front, back, rationale,
    status, created_at)` — status `suggested|accepted|rejected`.
  - `lexemes(lemma, lang, status, updated_at)` PK `(lemma, lang)`.
  - store/load helpers.
- [ ] **B3 — `study.py`:**
  - `translate_clause(cfg, text, lang)` → Haiku, concise gist, returns text.
  - `explain_and_suggest(cfg, span_text, clause, profile)` → Sonnet, structured
    output `{lemma, pos, lang, explanation, cards:[{kind, front, back, rationale}]}`.
- [ ] **B4 — API:**
  - `GET /videos/{id}/translation/{seg_idx}?lang=zh` → translate-on-demand + cache.
  - `POST /videos/{id}/explain` `{span}` → run explain_and_suggest (cached by
    span); upsert `lexemes` (learning); store `cards` (suggested); return
    `{explanation, cards}`.
  - include `explanations` + `cards` in `GET /videos/{id}`.
- [ ] **B5 — tests (offline, mocked LLM):** translation cache; explain output
  validation + lemma upsert + card rows created.

## Frontend (single view, no mode toggle)
- [ ] **F1 — remove Shadow/Study toggle.** One view keeps: word-click IPA,
  marking, step/loop/speed/hide.
- [ ] **F2 — per-clause translate button** (🌐 at clause edge) → fetch + show
  translation under the clause; toggle hides it. Language switch 中文/EN.
- [ ] **F3 — mark→explain inline.** On confirming a ❓ mark, call explain; show a
  panel with the explanation (lemma · pos · routed body) and the suggested cards
  (accept/reject buttons; accept persists status — full curation/export in S5).
  Loading + error states. (🔊 marks: no call.)

## Verification
- Offline tests (mocked LLM).
- Live (small, authorized): translate 1–2 clauses (Haiku) + explain 1 ❓ mark
  (Sonnet) → confirm routing, lemma in `lexemes`, card rows.

## Risks
- Crutch — mitigated: translations hidden until clicked; explanations only on mark.
- Cost — Haiku for clauses, Sonnet only per ❓ mark; all cached, never re-asked.
- Combined explain+cards JSON could be large → cap cards (≤3); validate; retry once.

## Out of scope (Slice 5)
Card curation UI depth, `.apkg`/audio export, pron→audio cards, lexeme dedup of
suggestions, marks→known propagation.
