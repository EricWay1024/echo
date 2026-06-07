"""SQLite access. Thin wrapper over stdlib sqlite3 — no ORM."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = (Path(__file__).parent / "schema.sql").read_text()


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    """Create tables if absent. Idempotent."""
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def store_video(conn, result, *, status: str = "fetched") -> None:
    """Persist a fetcher.FetchResult (video row + immutable words).

    Re-storing the same id replaces the row and re-seeds words — safe for the
    dev fixture; production never refetches a cached id anyway.
    """
    import datetime as _dt

    conn.execute(
        """INSERT OR REPLACE INTO videos
           (id, title, channel, lang, duration_ms, audio_path, description,
            fetched_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            result.id, result.title, result.channel, result.lang,
            result.duration_ms, f"{result.id}.opus", result.description,
            _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            status,
        ),
    )
    conn.execute("DELETE FROM words WHERE video_id = ?", (result.id,))
    conn.executemany(
        "INSERT INTO words (video_id, idx, text, start_ms, dur_ms) "
        "VALUES (?, ?, ?, ?, ?)",
        [(result.id, w.idx, w.text, w.start_ms, w.dur_ms) for w in result.words],
    )
    conn.commit()
