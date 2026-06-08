-- écho schema. Slice 1: videos, words. Slice 2: edits, segments.
-- Slice 3: marks. Slice 4: translations, explanations, cards, lexemes.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS videos (
    id          TEXT PRIMARY KEY,   -- YouTube video id
    title       TEXT,
    channel     TEXT,
    lang        TEXT,               -- source/caption language
    duration_ms INTEGER,
    audio_path  TEXT,               -- relative to data_dir/audio
    description TEXT,               -- kept for LLM context (Slice 2)
    fetched_at  TEXT,               -- ISO8601
    status      TEXT,               -- fetched | pipelined | ...
    last_pos_ms INTEGER             -- resume point (last playback position)
);

-- Ground truth. IMMUTABLE after fetch. Every later edit references these indices.
CREATE TABLE IF NOT EXISTS words (
    video_id TEXT    NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    idx      INTEGER NOT NULL,
    text     TEXT    NOT NULL,
    start_ms INTEGER NOT NULL,
    dur_ms   INTEGER NOT NULL,
    PRIMARY KEY (video_id, idx)
);

-- LLM rectification ops over word indices (replace | delete). Non-overlapping.
CREATE TABLE IF NOT EXISTS edits (
    video_id   TEXT    NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    span_start INTEGER NOT NULL,
    span_end   INTEGER NOT NULL,
    op         TEXT    NOT NULL,      -- replace | delete
    text       TEXT,                  -- replacement (replace only)
    PRIMARY KEY (video_id, span_start, span_end)
);

-- Clause segmentation; tiles [0, N-1] in order (no gaps/overlaps).
CREATE TABLE IF NOT EXISTS segments (
    video_id   TEXT    NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    seg_idx    INTEGER NOT NULL,
    span_start INTEGER NOT NULL,
    span_end   INTEGER NOT NULL,
    kind       TEXT,
    PRIMARY KEY (video_id, seg_idx)
);

-- User marks over word spans. kind: pron (🔊) | meaning (❓).
CREATE TABLE IF NOT EXISTS marks (
    video_id   TEXT    NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    span_start INTEGER NOT NULL,
    span_end   INTEGER NOT NULL,
    kind       TEXT    NOT NULL,   -- pron | meaning
    status     TEXT,               -- unknown | learning | known
    note       TEXT,               -- optional user comment
    created_at TEXT,
    PRIMARY KEY (video_id, span_start, span_end, kind)
);

-- On-demand clause translations, cached per (video, clause, language).
CREATE TABLE IF NOT EXISTS translations (
    video_id TEXT    NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    seg_idx  INTEGER NOT NULL,
    lang     TEXT    NOT NULL,      -- zh | en
    text     TEXT,
    PRIMARY KEY (video_id, seg_idx, lang)
);

-- LLM explanation of a marked span (one per span; language routed by the model).
CREATE TABLE IF NOT EXISTS explanations (
    video_id   TEXT    NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    span_start INTEGER NOT NULL,
    span_end   INTEGER NOT NULL,
    lang       TEXT,               -- en | zh
    lemma      TEXT,
    pos        TEXT,
    body       TEXT,
    created_at TEXT,
    PRIMARY KEY (video_id, span_start, span_end)
);

-- Suggested / curated Anki cards.
CREATE TABLE IF NOT EXISTS cards (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id   TEXT    NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    span_start INTEGER,
    span_end   INTEGER,
    kind       TEXT,               -- cloze | vocab | grammar | usage | audio
    front      TEXT,
    back       TEXT,
    rationale  TEXT,
    status     TEXT,               -- suggested | accepted | rejected
    created_at TEXT,
    -- SRS (Slice 6): scheduling for accepted cards
    due           TEXT,            -- ISO date (YYYY-MM-DD); null = new
    interval      INTEGER,         -- days
    ease          REAL,
    reps          INTEGER,
    lapses        INTEGER,
    last_reviewed TEXT
);

-- Cross-video vocabulary state.
CREATE TABLE IF NOT EXISTS lexemes (
    lemma      TEXT NOT NULL,
    lang       TEXT NOT NULL,
    status     TEXT,               -- unknown | learning | known
    updated_at TEXT,
    PRIMARY KEY (lemma, lang)
);
