# Slice 1 — Fetch & Play (actionable)

Goal (from `initial.md`): **URL in → audio + json3 cached → words table → transcript page with karaoke highlight and click-to-seek. No LLM.** End state: a usable transcript player driven by a real cached video.

Locked decisions: backend Python+FastAPI w/ `uv`; frontend **Vite + React**; fixture obtained by **installing yt-dlp + deno + POT provider and capturing one real French video** (then committed and used for all dev/test — never hit live YouTube again in dev).

> **Status (2026-06-07):** Slice 1 COMPLETE — T0–T6 ✅. Fixture = `CE3foG8FRz4` (Les Echos, "Le yuan peut-il détrôner le dollar ?", 2064 words). Backend serves SPA + API + ranged audio; React player has rAF karaoke highlight + click-to-seek + spacebar. Secrets in gitignored `.env`.
>
> **Verified by me:** parser (6 tests), all API routes, audio Range 206, SPA build + served, route coexistence. **NOT yet verified (needs a browser / live net):** interactive karaoke/click-seek visuals; live `POST /api/videos` fetch on a fresh URL.

## Repo layout (target)

```
echo/
  config.toml                 # user/llm/paths/server config
  pyproject.toml              # uv project + deps
  .gitignore
  src/echo/
    __init__.py
    config.py                 # load config.toml (tomllib), expand paths
    db.py                     # sqlite connect + init from schema.sql
    schema.sql                # DDL (Slice 1: videos, words)
    fetcher.py                # ALL yt-dlp interaction lives here
    json3.py                  # parse json3 events -> flat word array
    app.py                    # FastAPI app + routes
    __main__.py               # uvicorn entrypoint (python -m echo)
  web/                        # Vite + React SPA -> built into static, served by FastAPI
  tests/
    fixtures/<id>.json3       # committed real sample
    fixtures/<id>.opus        # committed real audio (short or full)
    test_json3.py
  data/                       # dev data dir (gitignored): audio/, app.db
```

## Tasks

### T0 — Toolchain & fixture bootstrap  *(blocker for live fetch; not for parser)*
- [ ] Install `yt-dlp` (uv tool), `deno`, `bgutil-ytdlp-pot-provider` plugin + provider.
- [ ] User picks one French video URL (~10–20 min, auto-captions present).
- [ ] Pull bestaudio (opus) + `json3` auto-captions for source lang via fetcher.
- [ ] Commit the opus + json3 as the canonical fixture. **Acceptance:** fixture replays end-to-end offline.

### T1 — Project scaffold
- [ ] `uv init` project; deps: `fastapi`, `uvicorn[standard]`, `yt-dlp`, `pytest`, `httpx` (test client). `tomllib` is stdlib.
- [ ] `config.py` loads `config.toml`, expands `~` in `data_dir`, creates `data_dir/audio/`.
- [ ] `db.py`: `sqlite3` connection (WAL, foreign_keys on), `init_db()` runs `schema.sql`.
- [ ] Vite+React app in `web/`; dev proxy to backend; production build served as static by FastAPI.
- [ ] **Acceptance:** `python -m echo` boots FastAPI on :7777, serves the built SPA at `/`.

### T2 — `schema.sql` (Slice 1 subset)
- [ ] `videos(id, title, channel, lang, duration_ms, audio_path, fetched_at, status)`
- [ ] `words(video_id, idx, text, start_ms, dur_ms)` PK `(video_id, idx)` — IMMUTABLE.
- [ ] (Defer `edits/segments/marks/explanations/lexemes` to their slices, but design DDL so they slot in.)

### T3 — `fetcher.py`  *(isolation boundary — no yt-dlp anywhere else)*
- [ ] `fetch(url) -> {id, title, channel, lang, duration_ms, audio_path, words_json3}`.
- [ ] Pull bestaudio→opus into `data_dir/audio/{id}.opus`; pull `json3` captions (source lang).
- [ ] Permanent cache: if `{id}` exists, never refetch.
- [ ] Fallbacks: POT provider; then `--cookies-from-browser`.
- [ ] Keep raw json3 on disk too (so re-parse never needs network).
- [ ] **Acceptance:** running against the fixture path yields the same words as live did.

### T4 — `json3.py`  *(heart of the slice)*
- [ ] Parse json3 `events[].segs[]`: word `text`, `start_ms = event.tStartMs + seg.tOffsetMs`, `dur_ms = seg(or event).dDurationMs`.
- [ ] Drop whitespace/newline-only segs; normalize spacing; produce contiguous `idx` 0..N-1.
- [ ] Robust to missing `tOffsetMs`/`dDurationMs` (infer from next word start).
- [ ] **Acceptance:** unit test on fixture: word count sane, monotonic non-overlapping-ish starts, spot-check known phrases.

### T5 — API (Slice 1 subset)
- [ ] `POST /videos {url}` → fetch+parse+store → `{id}`.
- [ ] `GET /videos` → library list.
- [ ] `GET /videos/{id}` → `{video, words}` (edits/segments/marks empty for now).
- [ ] `GET /audio/{id}.opus` → **HTTP Range** support for seeking (verify Starlette FileResponse handles Range; else implement).
- [ ] **Acceptance:** `httpx` test hits each route against fixture-seeded DB.

### T6 — Frontend transcript page
- [ ] Library view → pick video.
- [ ] `<audio src="/audio/{id}.opus">`; transcript rendered from `words`.
- [ ] **Karaoke highlight:** `requestAnimationFrame` polling `currentTime` + binary search over word `start_ms` (NOT `timeupdate`).
- [ ] **Click word → seek** to its `start_ms`.
- [ ] **Acceptance:** load fixture video, play, the current word highlights in time, clicking a word seeks there.

## Risks / open
- **yt-dlp + POT provider** is the fragile part (YouTube hostile, 2026). Mitigated by fixture-first dev; may need cookies. Iterate live only at T0.
- **Range requests:** confirm Starlette `FileResponse` serves 206 correctly for opus; browsers need it to seek.
- **opus container/mime:** YouTube bestaudio is opus-in-webm; serve correct content-type so `<audio>` plays + seeks.
- **json3 shape drift:** real fixture (not synthetic) de-risks parser; keep raw json3 committed.

## Out of scope (later slices)
LLM rectify/segment, clause loops, marking, explanations, export, config UI. Build order continues per `initial.md` §"Build order".
