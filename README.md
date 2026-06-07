# écho

**A local-first workbench for shadowing and learning a language from YouTube audio** — built for French (B2+), single-user, bring-your-own-Anthropic-key.

> YouTube auto-captions carry word-level timestamps but are full of ASR errors and
> arbitrary line breaks. Existing tools either keep the noise or, when they clean
> it up, lose the timing that makes shadowing possible. écho uses an LLM to
> **rectify and re-segment** the transcript **without ever detaching it from
> word-level timing** — then builds shadowing, pronunciation, marking,
> explanation, and Anki export on top.

No accounts, no hosting, no video — just audio + an honest, timed transcript.

## The core idea

The LLM **never returns rewritten text**. It returns **operations over word
indices** (`replace` / `delete`) plus **clause segments**. The per-word timing is
immutable, so every corrected word still knows exactly when it's spoken.
Click-to-seek, karaoke highlight, and clause loops keep working on the cleaned-up
text — no fragile re-alignment.

```
YouTube ──yt-dlp──▶  words  (immutable: text + per-word ms timing)
                       │
                  LLM  ▼  ops over indices + clause segments
                  edits + segments ──render──▶  timed tokens
                       │                              │
                  SQLite cache              Player (shadow) · Review (cards)
```

## Features

- 🎧 **Fetch & cache** a video's audio + auto-captions once; fully offline after.
- ✍️ **Rectify + segment** (one LLM pass): fixes ASR errors and proper nouns using
  the video's title/channel/description, splits into natural clauses — timing kept.
- 🗣️ **Shadowing**: word-level karaoke highlight, click-to-seek, clause **A–B
  loop**, **step mode** (auto-pause each clause; Space to repeat), speed control
  (pitch preserved), hide/reveal.
- 🔤 **IPA on click**: French word-level from [Lexique](http://www.lexique.org)
  (offline), clause-level (with liaison) via espeak.
- 🖍️ **Marking**: flag spans as 🔊 *pronunciation* or ❓ *meaning*, with notes.
- 🌐 **On-demand translation** per clause (中文 / English) — revealed only when you
  ask, so you attempt comprehension first. Cached.
- 💡 **Explanations** of marked spans, routed EN/中文 and calibrated to B2
  (collocations, register, faux amis) — pre-generated in the background.
- 🃏 **Anki export**: suggested cloze / vocab / grammar cards, plus **audio cards**
  clipped from the real clause → `.apkg` (with media) or `.tsv`.

## How it works

- **Backend** — Python + FastAPI on `localhost:7777`; SQLite (`app.db`) + an audio
  cache directory. Frontend is built and served by the backend.
- **Frontend** — Vite + React SPA (plain JS).
- **LLM** — your Anthropic key. A strong model for rectify/explain, a cheap model
  for bulk translation; **every result is cached and never re-asked.**
- **Pronunciation** is **not** LLM-based — Lexique for word IPA, espeak for phrase
  IPA. Audio is always ground truth.

## Requirements

- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- Node 20+ (to build the SPA)
- ffmpeg
- An **Anthropic API key** (rectify / translate / explain — you pay per use)
- For fetching from YouTube: **yt-dlp** + **Deno** (JS-challenge solving)
- Optional: **espeak-ng** (clause-level IPA; word IPA works without it)

## Setup

```bash
# backend deps
uv sync

# config + key (both gitignored)
cp config.toml.example config.toml
printf 'ANTHROPIC_API_KEY=sk-ant-...\n' > .env

# build the SPA
npm install --prefix web
npm run build --prefix web

# run
uv run python -m echo            # → http://localhost:7777
```

System tools (Debian/Ubuntu):

```bash
sudo apt-get install -y ffmpeg espeak-ng
# live YouTube fetch:
uv tool install yt-dlp
curl -fsSL https://deno.land/install.sh | sh
```

For an app-like window: `chrome --app=http://localhost:7777`.

## Usage

1. **Add** a YouTube URL in the library → it fetches and caches audio + captions.
2. **Rectify & segment** the video (one LLM pass) to unlock clause-level features.
3. **Shadow**: play with karaoke, loop or step through clauses, adjust speed, click
   words for IPA. Mark 🔊/❓ spans as you go — instant; explanations bake in the
   background.
4. **Review & cards**: explanations + suggested Anki cards are already there; play
   each clause, read its translation, curate cards (accept/reject), then **export**
   `.apkg` (with audio) or `.tsv` and import into Anki.

## Configuration

`config.toml` (gitignored — see `config.toml.example`): learner profile (known and
target languages + levels), model IDs (`model`, `translate_model`), data directory,
and port. The API key is read from the environment variable named by `api_key_env`
(default `ANTHROPIC_API_KEY`) — keep it in `.env`, never in the committed config.

## Project layout

```
echo/        FastAPI backend (app, db, fetcher, json3, pipeline, render, phon, study, export)
echo/data/   vendored Lexique pronunciation data
web/         Vite + React SPA (built into web/dist, served by the backend)
tests/       offline tests + the canonical fixture
plan/        design philosophy (workflow.md) + build history
CLAUDE.md    engineering guide for contributors/agents
```

## Status & scope

Personal, single-user, local-first. Built for **French**; the pipeline is largely
language-agnostic but the prompts and IPA data assume French. Bring-your-own-key —
budget roughly a few cents per video (rectify) and per explanation; translations
are fractions of a cent. Cached, so you pay once.

## Acknowledgements

- [Lexique 3.83](http://www.lexique.org) — French pronunciation + frequency data
  (see `echo/data/LEXIQUE_NOTICE.md`)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) ·
  [espeak-ng](https://github.com/espeak-ng/espeak-ng) ·
  [phonemizer](https://github.com/bootphon/phonemizer) ·
  [genanki](https://github.com/kerrickstaley/genanki) ·
  [Anthropic](https://www.anthropic.com)

## License

MIT — add a `LICENSE` file before publishing.
