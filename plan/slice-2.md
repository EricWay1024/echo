# Slice 2 — Rectify & Shadow (actionable)

Goal (from `initial.md`): **LLM rectify + segment (op-based, timing-preserving), edited+segmented rendering, clause loops, speed control, keyboard shortcuts, hide/reveal.** End state: the shadowing core — beats any extension.

The core invariant (from `initial.md`): **the LLM never returns transcript text as free prose — only `replace`/`delete` ops over word indices, plus `segments` that tile `[0, N-1]`.** This keeps every rendered token attached to word-level timing.

> **Status (2026-06-07):** Backend COMPLETE & verified live — B1–B5 ✅, 16 tests green. Live `claude-sonnet-4-6` pass on the fixture: 41 edits / 91 segments, validated first attempt in ~33s, exact tiling, real proper-noun fixes (`Couturier`, `Échos`, `yuan`). **Thinking disabled** (adaptive thinking blew the 32K cap on this long bounded extraction; `max_tokens=48000`). Frontend F1–F6 ✅ built; **interactive UX not yet visually verified in a browser** (headless env) — needs a human pass.

## Locked decisions (from claude-api reference)
- SDK: `anthropic` (Python). Client reads key from env (`.env` already auto-loaded by `config.py`).
- Model: `config.llm_model` (currently `claude-sonnet-4-6` — user's explicit choice). `claude-opus-4-8` is the "strongest" option if higher rectification quality is wanted.
- Structured output: `output_config={"format": {"type":"json_schema","schema": …}}` → guaranteed schema-valid JSON. `thinking={"type":"adaptive"}`. Stream + `get_final_message()` (output may be large), `max_tokens≈32000`.
- Pipeline is **manual** (explicit "Rectify" action) and **idempotent/cached** — one LLM call per video, never re-ask (store edits+segments; skip if present unless `?force`).

## Backend tasks
- [ ] **B1** Add `anthropic` dependency (`uv add anthropic`).
- [ ] **B2** `schema.sql`: add `edits(video_id, span_start, span_end, op, text)` and `segments(video_id, seg_idx, span_start, span_end, kind)`; `db.py` store/load + clear-on-restore.
- [ ] **B3** `pipeline.py` — rectify+segment:
  - Prompt: system = task + invariant + rules; user = title/channel/description + indexed word list (`idx\ttext`).
  - Call Anthropic (model from config, adaptive thinking, json_schema output, streamed).
  - **Validate**: edits `op∈{replace,delete}`, spans in range `[0,N-1]`, non-overlapping; `replace` non-empty text. Segments tile exactly `[0,N-1]` — sorted, `start=0`, contiguous (`next.start=prev.end+1`), `last.end=N-1`, no gaps/overlaps.
  - On failure: **retry once** with the validation errors appended; else raise.
  - Cache: store edits+segments, set `status='pipelined'`.
- [ ] **B4** `render.py` — `words ⊕ edits ⊕ segments → tokens`:
  - `replace [s,e]` → one token (text=edit.text, src=[s,e], time=[words[s].start, words[e].end]); `delete` → nothing; untouched word → token src=[i,i].
  - Group tokens into segments; each segment carries `[start_ms,end_ms]` (for A–B loop) + `kind`. Token keeps `start_ms` for karaoke binary search. **Offline unit-tested.**
- [ ] **B5** API: `POST /videos/{id}/pipeline` (run+store, idempotent, `?force`); `GET /videos/{id}` returns `edits`, `segments`, and computed `render` (segments→tokens) when pipelined; expose `status`.

## Frontend tasks
- [ ] **F1** Rectify action + states: not-pipelined → "Rectify" button; running → progress; done → segmented view. (Explicit, controls API spend.)
- [ ] **F2** Segmented rendering: clause blocks; tokens clickable → seek; **karaoke highlight across rendered tokens** (rAF + binary search over token `start_ms`); falls back to raw words when not pipelined.
- [ ] **F3** **Segment loop (A–B at clause level)** — the shadowing core: select a segment, toggle loop; rAF guard re-seeks to segment start when `currentTime` passes its end.
- [ ] **F4** Speed control: `playbackRate` (`preservesPitch=true`) + digit presets.
- [ ] **F5** Keyboard: space play/pause, ←/→ prev/next segment, R replay segment, digits speed presets. (M = mark deferred to Slice 3.)
- [ ] **F6** Hide/reveal mode (listen first, reveal on demand).

## Verification
- [ ] `render.py` unit tests (synthetic edits/segments — offline).
- [ ] `pipeline` validator unit tests (offline; feed good/bad payloads).
- [ ] **Live** (needs consent — spends ~cents on the user's API key): run `POST /videos/CE3foG8FRz4/pipeline` once against the fixture to confirm the real LLM call + end-to-end edited/segmented playback.

## Risks
- LLM spans may not perfectly tile → validate + retry once; surface a clear error if still invalid.
- Output token volume (segments for 2064 words) → stream, generous `max_tokens`.
- Karaoke must keep working on **edited** tokens → timing always derived from the source word span, never the new text.
- `playbackRate` pitch preservation is the browser default (`preservesPitch`); set explicitly.
