
# écho — local YouTube shadowing workbench

(working name; rename freely)

## What this is

A single-user, local-first app for learning a language from YouTube audio — initially French. Core thesis: YouTube's auto-captions carry word-level timestamps but contain ASR errors and arbitrary segmentation; existing tools either keep the noise or destroy the timing. This app uses an LLM to rectify and re-segment the transcript **without ever detaching it from word-level timing**, then builds shadowing, marking, explanation, and export on top.

Primary user: one person — languages: en (C1+), zh (native), yue (conversational); learning fr (B2). Assume the strongest available LLM via the user's own Anthropic API key. No hosted deployment, no auth, no video playback — audio + transcript only.

## Architecture

Local server + browser UI.

- Backend: Python, FastAPI, on localhost (default port 7777).
- Storage: one data directory containing `audio/` (opus files, ~7 MB per 20 min of audio) and `app.db` (SQLite). Cache is permanent: a video is fetched once and never refetched.
- Frontend: static SPA served by the backend (vanilla or Vite+React — whatever keeps the repo small).
- Reversibility: the server/UI split makes form factor a wrapper decision. `chrome --app=http://localhost:7777` gives an app-like window; Tauri, LAN access from a phone, or Raspberry Pi hosting are later options requiring no architectural change.

## Data pipeline

### Fetch (isolate entirely in `fetcher.py`)

yt-dlp pulls two things per video: bestaudio (opus) and the auto-generated captions in **json3** format for the video's source language. json3 events contain `segs` with per-word text and millisecond offsets; parse into a flat word array.

Operational notes — YouTube is hostile to downloaders as of 2026:

- Install current yt-dlp plus the `bgutil-ytdlp-pot-provider` plugin, with Deno available (yt-dlp needs an external JS runtime for signature solving).
- Fallback: `--cookies-from-browser`.
- All yt-dlp interaction lives behind this one module so breakage is contained there.
- Keep one cached json3 + opus fixture in the repo; develop and test against the fixture, never against live YouTube.

### Ground truth

```
words(video_id, idx, text, start_ms, dur_ms)   -- PK (video_id, idx); IMMUTABLE after fetch
```

### The core invariant

**The LLM never returns transcript text as free prose. It returns operations referencing word indices.** This eliminates the alignment problem (re-attaching timestamps to rewritten text) that breaks every other tool.

One LLM call per video (chunk only above ~1 h, with ~30 s overlap) returns strict JSON:

```json
{
  "edits": [
    {"op": "replace", "span": [41, 42], "text": "d'accord"},
    {"op": "delete",  "span": [97, 97]}
  ],
  "segments": [
    {"span": [0, 17],  "kind": "clause"},
    {"span": [18, 30], "kind": "clause"}
  ]
}
```

Rules:

- Ops are `replace` and `delete` only. A word the ASR missed is handled by replacing an adjacent span with the longer text.
- Edits must be non-overlapping and in range; segments must tile the transcript in order — cover `[0, N-1]`, no gaps, no overlaps.
- Validate on receipt; on failure, retry once with the validation errors appended to the prompt.
- A rendered token's timing = [start of first word in its source span, end of last word]. Every rendered token keeps a back-pointer to its span, so click-to-seek and marking work on edited text.
- Prompt context: include video title, channel, and description — that's what lets the model fix proper nouns in news content.

### SQLite schema (beyond `words`)

```
videos(id, title, channel, lang, duration_ms, audio_path, fetched_at, status)
edits(video_id, span_start, span_end, op, text)
segments(video_id, seg_idx, span_start, span_end, kind)
marks(video_id, span_start, span_end, status, created_at)    -- unknown | learning | known
explanations(video_id, span_start, span_end, lang, lemma, body, created_at)
lexemes(lemma, lang, status, updated_at)                     -- cross-video vocabulary state
```

## LLM usage

Three jobs, all through the user's API key; model name set in config and assumed to be the strongest available:

1. **Rectify + segment** — as above.
2. **Explain on demand** — user selects a span → call with the span, its surrounding segment, and the user profile → returns `{lemma, pos, explanation}`. The lemma populates `lexemes` (the model lemmatizes; no spaCy dependency).
3. **Language routing** — per item, pick the explanation language with the shortest path: English for cognates, faux amis, and grammar metalanguage; Mandarin for direct glosses. The other language is always available on request. Calibrate to B2: skip basics; focus on collocations, register, spoken contractions, idioms.

Cache every LLM result keyed by (video, span, job); never re-ask.

## Player & UI

- `<audio>` element; serve audio with HTTP Range support so seeking works.
- Word-karaoke highlight via `requestAnimationFrame` polling of `currentTime`, with binary search over word start times. Do **not** use `timeupdate` (~4 Hz, too coarse).
- Click a word → seek to its span start.
- Segment loop (A–B at clause level) — the shadowing core. It lands on correct clause boundaries because of the segmentation pass. French liaison blurs ASR word boundaries, so the clause, not the word, is the unit of practice.
- Speed control via `playbackRate` (pitch preserved by default).
- Keyboard: space play/pause, ←/→ previous/next segment, R replay segment, M mark selection, digits for speed presets.
- Hide/reveal mode: listen first, reveal text on demand.
- MediaSession API for hardware media keys.

## Import & export

- Import: `POST /videos {url}`, plus a bookmarklet for one-click capture from any YouTube page:
  `javascript:fetch('http://localhost:7777/add?url='+encodeURIComponent(location.href))`
- Export per video: Markdown (segments + marks + explanations) and Anki TSV (front: the span in its segment context; back: explanation + lemma).

## API sketch

```
POST /videos {url}            → fetch, parse, store; returns id
POST /videos/{id}/pipeline    → run rectify + segment
GET  /videos                  → library
GET  /videos/{id}             → words ⊕ edits ⊕ segments ⊕ marks
POST /videos/{id}/marks       {span, status}
POST /videos/{id}/explain     {span} → cached explanation
GET  /videos/{id}/export      ?format=md|anki
GET  /audio/{id}.opus         (Range requests)
```

## Config (config.toml)

```toml
[user]
known  = [ {lang="en", level="C1"}, {lang="zh", level="native"}, {lang="yue", level="conversational"} ]
target = {lang="fr", level="B2"}

[llm]
provider = "anthropic"
model = "<strongest available>"
api_key_env = "ANTHROPIC_API_KEY"

[paths]
data_dir = "~/echo-data"

[server]
port = 7777
```

## Build order — vertical slices, each ends usable

1. **Fetch & play.** URL in → audio + json3 cached → words table → transcript page with karaoke highlight and click-to-seek. No LLM yet.
2. **Rectify & shadow.** LLM pass, edited + segmented rendering, clause loops, speed control, keyboard shortcuts, hide/reveal. At this point the app already beats any extension.
3. **Mark & explain.** Span marking, routed explanations, lexeme tracking.
4. **Export.** Markdown + Anki TSV.

Deferred deliberately: vocabulary-size estimation, external dictionary integration, LAN/phone mode, Pi deployment, anything multi-user.

## Non-goals

No video playback. No hosted version. No accounts. No browser extension. No degradation handling for weak models — the LLM is assumed strong.

