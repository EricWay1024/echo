# Slice 3 — Shadow mode / pronunciation pass (actionable)

Goal (Pass 1 of `workflow.md`): **shadow with on-demand IPA, step through clauses
pausing for repetition, and flag spots by type — no LLM.** End state: a usable
pronunciation-practice mode over the rectified+segmented transcript.

> **Status (2026-06-07):** Backend COMPLETE & verified — 20 tests green; live IPA endpoint decodes correctly (`Depuis→dəpɥi`, `Guerre→ɡɛʁ`), 1815/2016 tokens with offline IPA; marks CRUD works. Lexique vendored (125k forms). **espeak-ng not installed** (no sudo) → clause-level IPA returns null until installed: `sudo apt-get install -y espeak-ng`. Frontend built; **interactive UX needs a browser pass**.

## Locked decisions (from workflow.md)
- IPA: **Lexique.org first** (inflected-form IPA + frequency), **espeak-ng /
  `phonemizer` fallback** (OOV words + clause-level transcription for liaison).
- **Clause-level IPA by default**, word-level on click; always on-demand.
- **Two mark types**: 🔊 pronunciation, ❓ meaning. Persisted; ❓ feeds Slice 4.
- **Step mode**: auto-pause at clause end; **Space** resumes into the next clause.

## Backend
- [ ] **B1 — pronunciation data (`phon.py`).** Vendor a slimmed Lexique383
  (`ortho`, `phon` (SAMPA), `freqfilms`) as a gzipped TSV under `echo/data/`
  (note license + attribution). Load into `{form_lower: (ipa, freq)}`. Implement
  SAMPA→IPA mapping (unit-tested on known words). `word_ipa(form)` → Lexique hit
  else espeak.
- [ ] **B2 — espeak G2P.** Add `phonemizer` (py) + `espeak-ng` (system dep;
  document install). `clause_ipa(text)` → IPA via phonemizer/espeak (captures
  approximate liaison); also covers OOV single words.
- [ ] **B3 — schema + marks API.** Add `marks(video_id, span_start, span_end,
  kind, status, created_at)`, `kind ∈ {pron, meaning}`. `POST /videos/{id}/marks`
  {span, kind, status?}; `DELETE /videos/{id}/marks/{span_start}/{span_end}/{kind}`;
  include `marks` in `GET /videos/{id}` (db loader).
- [ ] **B4 — IPA API.** `GET /videos/{id}/ipa` → `{words:[ipa…], segments:[ipa…]}`,
  computed from words/segments, cached (memo or a `pron_cache` table). Word IPA
  aligned to word idx; segment IPA = `clause_ipa` of the rendered clause.
- [ ] **B5 — tests.** SAMPA→IPA on sample inflected forms (`vacille`, `libellée`);
  marks round-trip; `clause_ipa` smoke test (skip if espeak absent).

## Frontend
- [ ] **F1 — mode scaffold.** Add a Shadow⇄Study toggle (Study lands in Slice 4;
  Shadow is the Slice-3 surface). Shadow mode default for un-studied videos.
- [ ] **F2 — IPA on click.** Click a word → small popover: word IPA + the clause's
  IPA (so liaison is visible). Fetch `/ipa` once per video, cache in component.
- [ ] **F3 — two-type marking.** Select a word/span; `P` = 🔊 pron toggle, `M` = ❓
  meaning toggle (also click affordance). Distinct underlines (dotted vs wavy);
  render existing marks; persist via API; survive reload.
- [ ] **F4 — step mode.** Toggle ("step"); rAF guard pauses at the current
  clause's end (once per boundary); **Space** resumes → plays next clause →
  pauses at its end. Composes with speed control + loop (loop overrides step).
- [ ] **F5 — keyboard.** Add `P`/`M` (mark current word/selection), `S` (toggle
  step). Keep space/←→/R/L/H/1–5 from Slice 2.

## Acceptance
Shadow the fixture: click a word → see its IPA and the clause IPA (liaison shows);
mark words 🔊/❓ and they persist across reload; step mode pauses at each clause and
Space advances; everything works with no API key configured.

## Risks
- `espeak-ng` is a system dependency — if absent, word IPA still works via Lexique;
  clause IPA degrades. Document install; degrade gracefully.
- Lexique is openly licensed — vendor with attribution; keep the slim file small.
- SAMPA→IPA mapping must be correct — lock with unit tests.
- Clause-level espeak liaison is approximate, not phonetician-grade — fine as a
  diagnostic aid (audio remains ground truth).

## Out of scope (later)
Translations, explanations, lexeme tracking (Slice 4); card inference + export
(Slice 5).
