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
    """Create tables if absent + apply lightweight column migrations. Idempotent."""
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(marks)")}
        if "note" not in cols:
            conn.execute("ALTER TABLE marks ADD COLUMN note TEXT")
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


def load_words(conn, video_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT idx, text, start_ms, dur_ms FROM words "
        "WHERE video_id = ? ORDER BY idx",
        (video_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def store_pipeline(conn, video_id: str, edits: list, segments: list) -> None:
    """Persist LLM rectify+segment output. Replaces any prior pipeline result.

    edits: list of {op, span:[s,e], text?}. segments: list of {span:[s,e], kind?}.
    """
    conn.execute("DELETE FROM edits WHERE video_id = ?", (video_id,))
    conn.execute("DELETE FROM segments WHERE video_id = ?", (video_id,))
    conn.executemany(
        "INSERT INTO edits (video_id, span_start, span_end, op, text) "
        "VALUES (?, ?, ?, ?, ?)",
        [(video_id, e["span"][0], e["span"][1], e["op"], e.get("text"))
         for e in edits],
    )
    conn.executemany(
        "INSERT INTO segments (video_id, seg_idx, span_start, span_end, kind) "
        "VALUES (?, ?, ?, ?, ?)",
        [(video_id, i, s["span"][0], s["span"][1], s.get("kind"))
         for i, s in enumerate(segments)],
    )
    conn.execute("UPDATE videos SET status = 'pipelined' WHERE id = ?", (video_id,))
    conn.commit()


def load_edits(conn, video_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT span_start, span_end, op, text FROM edits "
        "WHERE video_id = ? ORDER BY span_start",
        (video_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def load_segments(conn, video_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT seg_idx, span_start, span_end, kind FROM segments "
        "WHERE video_id = ? ORDER BY seg_idx",
        (video_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def load_marks(conn, video_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT span_start, span_end, kind, status, note, created_at FROM marks "
        "WHERE video_id = ? ORDER BY span_start, kind",
        (video_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_mark(conn, video_id: str, span_start: int, span_end: int, kind: str,
             status: str = "unknown", note: str | None = None) -> None:
    import datetime as _dt

    conn.execute(
        "INSERT OR REPLACE INTO marks "
        "(video_id, span_start, span_end, kind, status, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (video_id, span_start, span_end, kind, status, note,
         _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")),
    )
    conn.commit()


def delete_mark(conn, video_id: str, span_start: int, span_end: int,
                kind: str) -> None:
    conn.execute(
        "DELETE FROM marks WHERE video_id = ? AND span_start = ? "
        "AND span_end = ? AND kind = ?",
        (video_id, span_start, span_end, kind),
    )
    conn.commit()
