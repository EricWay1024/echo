-- écho schema. Slice 1 covers `videos` and `words` only.
-- Later slices add: edits, segments, marks, explanations, lexemes.

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
    status      TEXT                -- fetched | pipelined | ...
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
