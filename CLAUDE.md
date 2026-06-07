# CLAUDE.md — engineering guide for agents working on écho

Orientation for AI agents (and humans) contributing to this repo. The **product
design** lives in `plan/workflow.md` (source of truth) and `plan/initial.md`
(original vision); the per-slice build history is `plan/slice-1..5.md`. This file
is the *engineering* map: invariants, layout, how to run/test, and gotchas.

## What this is
écho — a single-user, **local-first** web app for shadowing and learning a
language from YouTube audio (built for French, B2). Python + FastAPI backend on
localhost, Vite + React SPA served by the backend, SQLite + a local audio cache.
LLM features use the user's own Anthropic API key.

## Core design philosophy — do not violate

1. **Immutable ground truth + op-based edits.** `words` (per-word text + ms
   timing) is written once at fetch and **never mutated**. The LLM never returns
   transcript prose — only `replace`/`delete` **ops over word indices** plus
   `segments` that tile `[0, N-1]`. `render.py` derives display tokens; every
   token keeps a back-pointer to its source word span, so timing (karaoke,
   click-to-seek, clause loops) always works on edited text. This is what
   eliminates the re-alignment problem that breaks other tools.
2. **Cache everything; never re-ask the LLM.** Pipeline result, translations,
   explanations + cards, IPA — all cached (SQLite, or a process memo for IPA).
   One fetch per video, permanent.
3. **Develop against the committed fixture, never live YouTube.**
   `tests/fixtures/CE3foG8FRz4.*` is the canonical sample; `uv run python -m
   echo.seed` loads it into `~/echo-data`. All tests are offline (LLM mocked).
4. **Audio is ground truth; IPA is a diagnostic aid.** Word IPA from Lexique
   (offline); clause IPA (liaison) via espeak.
5. **Meaning is opt-in.** Translations are hidden until a clause is clicked;
   explanations only fire on a ❓ mark. **Marking is instant** (no LLM in the hot
   path) — explanations pre-generate in the background and are curated on the
   Review page.
6. **LLM tiering by value.** Rectify + explain use the strong model
   (`config.llm_model`); bulk clause translation uses a cheap one
   (`config.llm_translate_model`).

## Run / test / build
- Backend (serves built SPA + API on :7777): `uv run python -m echo`
- Tests (offline, fast): `uv run pytest -q`
- Frontend dev (HMR; proxies /api + /audio to :7777): `npm run dev --prefix web`
- Frontend build (→ `web/dist`, served by FastAPI): `npm run build --prefix web`
- Seed the fixture into `~/echo-data` + DB: `uv run python -m echo.seed`
- **After editing the SPA, rebuild** for the FastAPI-served app (:7777) to update.

## Repo map
Backend `echo/`:
| file | responsibility |
|---|---|
| `app.py` | FastAPI routes — the only web layer |
| `config.py` | load `config.toml` + `.env`; resolved settings |
| `db.py` | SQLite (stdlib, **no ORM**); schema init + all queries |
| `schema.sql` | DDL: videos, words, edits, segments, marks, translations, explanations, cards, lexemes |
| `fetcher.py` | the **only** yt-dlp boundary (bestaudio→opus, json3 captions) |
| `json3.py` | parse json3 → flat timed `words` |
| `pipeline.py` | LLM rectify+segment (structured output; validate; retry once) |
| `render.py` | `words ⊕ edits ⊕ segments → timed tokens` (the invariant) |
| `phon.py` | IPA: vendored Lexique + espeak fallback |
| `study.py` | translate (Haiku) + explain & suggest cards (Sonnet) |
| `export.py` | Anki `.apkg` (genanki) + TSV; audio cards from 🔊 marks |
| `seed.py` | offline fixture loader |
| `__main__.py` | uvicorn entrypoint |

Frontend `web/src/`:
| file | responsibility |
|---|---|
| `App.jsx` | view switch Library / Player / Review by state (no router) |
| `Library.jsx` | list + add video |
| `Player.jsx` | shadow: karaoke, click→IPA+mark, select→mark, clause loop, step, speed, hide, per-clause translate |
| `Review.jsx` | batch explanations + cards, curate, export |
| `api.js` | fetch wrappers |
| `styles.css` | all styles (no framework) |

`plan/` — design + build history. `tests/` — offline; `fixtures/` is canonical.

## Conventions
- Python 3.12 + `uv`. Stdlib `sqlite3`, **raw SQL in `db.py`, no ORM**. `tomllib`.
- React in **plain JS** (Vite, no TypeScript), no router, no state lib, no CSS framework.
- Karaoke/highlight: `requestAnimationFrame` + binary search over start_ms,
  applied via **direct DOM class toggling** (never React re-render per frame).
  `Transcript` is `memo`-ized; control/state changes must not re-render it.
- Keep modules single-purpose; match surrounding style.

## LLM specifics & gotchas
- Models from config: `llm_model` (rectify + explain; currently
  `claude-sonnet-4-6`), `llm_translate_model` (`claude-haiku-4-5`).
- **Structured output (`output_config` json_schema) only for extraction
  (rectify).** For *generation* (explain) it made the model **satisfice**
  (degenerate output, empty cards), so `study.explain_and_suggest` uses free-form
  generation + loose JSON parse (`_loads_loose`) + one retry. **Do not** switch it
  back to a strict schema.
- **Pipeline thinking is disabled** (`thinking:{type:"disabled"}`, `max_tokens=48000`):
  adaptive thinking blew the token cap on long transcripts.
- Explanations pre-generate via FastAPI `BackgroundTasks` on ❓ mark (`_bg_explain`);
  the Review page reads cached results, with on-demand explain as fallback.
- `'known'` lexeme dedup is **currently disabled** (commented in `_run_explain`);
  re-enable by loading known lemmas and passing `known=` to `explain_and_suggest`.

## External tooling (live fetch only — dev uses the fixture)
- **yt-dlp** + **deno** on PATH (`~/.deno/bin`) + `--remote-components ejs:github`
  for JS-challenge solving; bgutil POT plugin optional. All isolated in `fetcher.py`.
- **espeak-ng** (system pkg) for clause-level + OOV IPA; without it, word IPA still
  works via Lexique (degrades gracefully).
- **ffmpeg** for opus remux + clause clipping (audio cards).

## Secrets
`config.toml` and `.env` are gitignored. The key lives in `.env` as
`ANTHROPIC_API_KEY` (auto-loaded by `config.py`); `config.toml` only names the env
var via `api_key_env`. Commit `config.toml.example`, **never** a key.

## Operational gotchas
- `uv run uvicorn …` backgrounded, then killing the parent, **orphans the child**
  (port stays bound). For scripted boot/kill use `.venv/bin/uvicorn …` directly;
  free a stuck port with `fuser -k 7777/tcp`.
- Data dir `~/echo-data` (`audio/` + `app.db`). New *tables* appear via `init_db`
  (CREATE IF NOT EXISTS); a new *column* needs a migration (see the `marks.note`
  ALTER in `db.init_db`).

## Don'ts
Don't mutate `words` after fetch · don't have the LLM emit prose · don't refetch a
cached video · don't hit live YouTube in dev/tests · don't put a key in
`config.toml` · don't add an ORM or CSS framework · don't make the LLM call inline
in the shadowing hot path.
