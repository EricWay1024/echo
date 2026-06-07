"""Marks round-trip (offline, temp DB)."""

from echo import db


def test_marks_roundtrip(tmp_path):
    dbp = tmp_path / "t.db"
    db.init_db(dbp)
    conn = db.connect(dbp)
    conn.execute("INSERT INTO videos (id, status) VALUES ('v', 'fetched')")
    conn.commit()

    db.add_mark(conn, "v", 5, 7, "meaning")
    db.add_mark(conn, "v", 5, 5, "pron")
    marks = db.load_marks(conn, "v")
    assert len(marks) == 2
    assert any(m["kind"] == "meaning" and m["span_start"] == 5 for m in marks)
    assert all(m["status"] == "unknown" for m in marks)

    db.delete_mark(conn, "v", 5, 7, "meaning")
    remaining = db.load_marks(conn, "v")
    assert [m["kind"] for m in remaining] == ["pron"]
    conn.close()
