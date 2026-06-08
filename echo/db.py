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


def _ensure_columns(conn, table: str, cols: dict[str, str]) -> None:
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    for name, decl in cols.items():
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init_db(db_path: Path) -> None:
    """Create tables if absent + apply lightweight column migrations. Idempotent."""
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        _ensure_columns(conn, "marks", {"note": "TEXT"})
        _ensure_columns(conn, "videos", {"last_pos_ms": "INTEGER"})
        _ensure_columns(conn, "cards", {
            "due": "TEXT", "interval": "INTEGER", "ease": "REAL",
            "reps": "INTEGER", "lapses": "INTEGER", "last_reviewed": "TEXT",
        })
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


def set_progress(conn, video_id: str, pos_ms: int) -> None:
    conn.execute("UPDATE videos SET last_pos_ms = ? WHERE id = ?", (pos_ms, video_id))
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


def _now() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# --- translations -------------------------------------------------------------
def get_translation(conn, video_id: str, seg_idx: int, lang: str) -> str | None:
    row = conn.execute(
        "SELECT text FROM translations WHERE video_id = ? AND seg_idx = ? AND lang = ?",
        (video_id, seg_idx, lang),
    ).fetchone()
    return row["text"] if row else None


def store_translation(conn, video_id: str, seg_idx: int, lang: str, text: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO translations (video_id, seg_idx, lang, text) "
        "VALUES (?, ?, ?, ?)",
        (video_id, seg_idx, lang, text),
    )
    conn.commit()


# --- explanations / cards / lexemes ------------------------------------------
def load_explanations(conn, video_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT span_start, span_end, lang, lemma, pos, body, created_at "
        "FROM explanations WHERE video_id = ? ORDER BY span_start",
        (video_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_explanation(conn, video_id: str, span_start: int, span_end: int) -> dict | None:
    row = conn.execute(
        "SELECT span_start, span_end, lang, lemma, pos, body FROM explanations "
        "WHERE video_id = ? AND span_start = ? AND span_end = ?",
        (video_id, span_start, span_end),
    ).fetchone()
    return dict(row) if row else None


def store_explanation(conn, video_id: str, span_start: int, span_end: int,
                      lang: str, lemma: str, pos: str, body: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO explanations "
        "(video_id, span_start, span_end, lang, lemma, pos, body, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (video_id, span_start, span_end, lang, lemma, pos, body, _now()),
    )
    conn.commit()


def load_cards(conn, video_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, span_start, span_end, kind, front, back, rationale, status "
        "FROM cards WHERE video_id = ? ORDER BY id",
        (video_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def replace_suggested_cards(conn, video_id: str, span_start: int, span_end: int,
                            cards: list[dict]) -> None:
    """Replace prior *suggested* cards for this span (keep accepted/rejected)."""
    conn.execute(
        "DELETE FROM cards WHERE video_id = ? AND span_start = ? AND span_end = ? "
        "AND status = 'suggested'",
        (video_id, span_start, span_end),
    )
    conn.executemany(
        "INSERT INTO cards (video_id, span_start, span_end, kind, front, back, "
        "rationale, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'suggested', ?)",
        [(video_id, span_start, span_end, c.get("kind"), c.get("front"),
          c.get("back"), c.get("rationale"), _now()) for c in cards],
    )
    conn.commit()


def set_card_status(conn, card_id: int, status: str) -> None:
    conn.execute("UPDATE cards SET status = ? WHERE id = ?", (status, card_id))
    conn.commit()


def get_card(conn, card_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    return dict(row) if row else None


def due_cards(conn, today: str) -> list[dict]:
    """Accepted cards due for review (never-scheduled cards come first)."""
    rows = conn.execute(
        "SELECT * FROM cards WHERE status = 'accepted' AND (due IS NULL OR due <= ?) "
        "ORDER BY (due IS NULL) DESC, due ASC, id ASC",
        (today,),
    ).fetchall()
    return [dict(r) for r in rows]


def count_due(conn, today: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM cards WHERE status = 'accepted' "
        "AND (due IS NULL OR due <= ?)",
        (today,),
    ).fetchone()["n"]


def update_card_schedule(conn, card_id: int, sched: dict) -> None:
    conn.execute(
        "UPDATE cards SET due = ?, interval = ?, ease = ?, reps = ?, lapses = ?, "
        "last_reviewed = ? WHERE id = ?",
        (sched["due"], sched["interval"], sched["ease"], sched["reps"],
         sched["lapses"], sched["last_reviewed"], card_id),
    )
    conn.commit()


def load_known_lemmas(conn, lang: str = "fr", limit: int = 300) -> list[str]:
    rows = conn.execute(
        "SELECT lemma FROM lexemes WHERE lang = ? AND status = 'known' "
        "ORDER BY updated_at DESC LIMIT ?",
        (lang, limit),
    ).fetchall()
    return [r["lemma"] for r in rows]


def upsert_lexeme(conn, lemma: str, lang: str, status: str = "learning") -> None:
    conn.execute(
        "INSERT INTO lexemes (lemma, lang, status, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(lemma, lang) DO UPDATE SET status = excluded.status, "
        "updated_at = excluded.updated_at",
        (lemma, lang, status, _now()),
    )
    conn.commit()
