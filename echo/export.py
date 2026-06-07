"""Export accepted cards to Anki .apkg (cloze + basic + audio) or TSV.

Audio cards are generated from 🔊 pron marks at export time: clip the enclosing
clause from the cached opus and embed it. Stable model/deck/note IDs so a
re-import updates rather than duplicates.
"""

from __future__ import annotations

import subprocess
import zlib
from pathlib import Path

import genanki

from . import db, phon, render

BASIC_MODEL = genanki.Model(
    1742000001, "écho Basic",
    fields=[{"name": "Front"}, {"name": "Back"}],
    templates=[{"name": "Card 1", "qfmt": "{{Front}}",
                "afmt": '{{FrontSide}}<hr id="answer">{{Back}}'}],
)
CLOZE_MODEL = genanki.Model(
    1742000002, "écho Cloze",
    fields=[{"name": "Text"}, {"name": "Back Extra"}],
    templates=[{"name": "Cloze", "qfmt": "{{cloze:Text}}",
                "afmt": "{{cloze:Text}}<br>{{Back Extra}}"}],
    model_type=genanki.Model.CLOZE,
)


def _deck_id(video_id: str) -> int:
    return 1_700_000_000 + zlib.crc32(video_id.encode()) % 100_000_000


def _clip(opus: Path, start_ms: int, end_ms: int, out: Path) -> None:
    dur = max(0.1, (end_ms - start_ms) / 1000)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start_ms / 1000:.3f}",
         "-t", f"{dur:.3f}", "-i", str(opus), "-c", "copy", str(out)],
        check=True,
    )


def _clause_of(rendered, idx):
    return next((s for s in rendered
                 if s["span_start"] <= idx <= s["span_end"]), None)


def build_apkg(cfg, conn, video_id: str, out_dir: Path) -> Path:
    row = conn.execute("SELECT title FROM videos WHERE id = ?", (video_id,)).fetchone()
    title = (row["title"] if row else None) or video_id
    words = db.load_words(conn, video_id)
    rendered = render.render(words, db.load_edits(conn, video_id),
                             db.load_segments(conn, video_id))

    deck = genanki.Deck(_deck_id(video_id), f"écho::{title}")
    media: list[str] = []

    # Accepted LLM cards.
    for c in db.load_cards(conn, video_id):
        if c["status"] != "accepted":
            continue
        if c["kind"] == "cloze":
            deck.add_note(genanki.Note(
                model=CLOZE_MODEL, fields=[c["front"] or "", c["back"] or ""],
                guid=genanki.guid_for(video_id, "cloze", c["front"])))
        else:
            back = c["back"] or ""
            if c["rationale"]:
                back += f"<br><br><i>{c['rationale']}</i>"
            deck.add_note(genanki.Note(
                model=BASIC_MODEL, fields=[c["front"] or "", back],
                guid=genanki.guid_for(video_id, "basic", c["front"])))

    # 🔊 pron marks -> audio cards (clip the enclosing clause).
    opus = cfg.audio_dir / f"{video_id}.opus"
    for m in db.load_marks(conn, video_id):
        if m["kind"] != "pron":
            continue
        seg = _clause_of(rendered, m["span_start"])
        if not seg or not opus.exists():
            continue
        span_text = "".join(
            w["text"] for w in words[m["span_start"]:m["span_end"] + 1]).strip()
        clause_text = "".join(t["text"] for t in seg["tokens"]).strip()
        ipa = phon.word_ipa(span_text) or ""
        clip_name = f"echo_{video_id}_{m['span_start']}_{m['span_end']}.ogg"
        clip_path = out_dir / clip_name
        try:
            _clip(opus, seg["start_ms"], seg["end_ms"], clip_path)
        except Exception:
            continue
        media.append(str(clip_path))
        front = f"[sound:{clip_name}]<br>🔊 say it"
        back = f"{clause_text}<br><b>{span_text}</b>" + (f" /{ipa}/" if ipa else "")
        deck.add_note(genanki.Note(
            model=BASIC_MODEL, fields=[front, back],
            guid=genanki.guid_for(video_id, "audio", clip_name)))

    pkg = genanki.Package(deck)
    pkg.media_files = media
    out = out_dir / f"echo_{video_id}.apkg"
    pkg.write_to_file(str(out))
    return out


def build_tsv(conn, video_id: str) -> str:
    def clean(x):
        return (x or "").replace("\t", " ").replace("\n", " ")

    rows = [f"{clean(c['front'])}\t{clean(c['back'])}"
            for c in db.load_cards(conn, video_id) if c["status"] == "accepted"]
    return "\n".join(rows) + ("\n" if rows else "")
