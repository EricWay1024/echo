"""Export: .apkg builds (valid zip), TSV content (offline; no opus → audio skip)."""

from pathlib import Path
from types import SimpleNamespace

from echo import db, export


def _seed(tmp_path):
    dbp = tmp_path / "t.db"
    db.init_db(dbp)
    conn = db.connect(dbp)
    conn.execute("INSERT INTO videos (id, title, status) VALUES ('v', 'Titre', 'pipelined')")
    conn.executemany(
        "INSERT INTO words (video_id, idx, text, start_ms, dur_ms) VALUES (?,?,?,?,?)",
        [("v", 0, "le", 0, 100), ("v", 1, " dollar", 100, 200), ("v", 2, " vacille", 300, 200)],
    )
    conn.execute("INSERT INTO segments (video_id, seg_idx, span_start, span_end, kind) "
                 "VALUES ('v', 0, 0, 2, 'clause')")
    conn.commit()
    db.replace_suggested_cards(conn, "v", 1, 2, [
        {"kind": "cloze", "front": "le {{c1::dollar vacille}}", "back": "wavers", "rationale": "x"},
    ])
    db.replace_suggested_cards(conn, "v", 0, 0, [
        {"kind": "vocab", "front": "le", "back": "the", "rationale": "y"},
    ])
    # accept the cloze, leave the vocab suggested
    cloze = next(c for c in db.load_cards(conn, "v") if c["kind"] == "cloze")
    db.set_card_status(conn, cloze["id"], "accepted")
    db.add_mark(conn, "v", 2, 2, "pron")  # no opus on disk -> skipped at export
    return conn


def test_build_tsv_only_accepted(tmp_path):
    conn = _seed(tmp_path)
    tsv = export.build_tsv(conn, "v")
    assert tsv.strip().split("\n") == ["le {{c1::dollar vacille}}\twavers"]  # vocab not accepted


def test_build_apkg_is_valid_zip(tmp_path):
    conn = _seed(tmp_path)
    cfg = SimpleNamespace(audio_dir=tmp_path)  # no opus -> pron audio skipped
    out = export.build_apkg(cfg, conn, "v", tmp_path)
    assert out.exists() and out.stat().st_size > 0
    assert Path(out).read_bytes()[:2] == b"PK"  # zip magic (.apkg is a zip)
