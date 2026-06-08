"""FastAPI app: serves the SPA, audio (with Range), and the data API.

Route convention: data endpoints under /api/*, audio under /audio/*, SPA at /.
(Refines the sketch in plan/initial.md: /api prefix avoids clashing with the
client-routed SPA.)
"""

from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, phon, render, srs, study

_ipa_cache: dict[str, dict] = {}  # video_id -> {tokens, segments} (process-level)

cfg = config.get()

# Container is opus-in-ogg (fetcher remuxes with -c copy), served as audio/ogg.
AUDIO_MEDIA_TYPE = "audio/ogg"

WEB_DIST = Path(__file__).parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db(cfg.db_path)
    yield


app = FastAPI(title="écho", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "data_dir": str(cfg.data_dir)}


@app.get("/api/videos")
def list_videos() -> list[dict]:
    conn = db.connect(cfg.db_path)
    try:
        rows = conn.execute(
            "SELECT id, title, channel, lang, duration_ms, status, fetched_at "
            "FROM videos ORDER BY fetched_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/videos/{video_id}")
def get_video(video_id: str) -> dict:
    conn = db.connect(cfg.db_path)
    try:
        video = conn.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        if video is None:
            raise HTTPException(404, "video not found")
        words = db.load_words(conn, video_id)
        edits = db.load_edits(conn, video_id)
        segments = db.load_segments(conn, video_id)
        rendered = render.render(words, edits, segments) if segments else []
        return {
            "video": dict(video),
            "words": words,
            "edits": edits,
            "segments": segments,
            "render": rendered,
            "marks": db.load_marks(conn, video_id),
            "explanations": db.load_explanations(conn, video_id),
            "cards": db.load_cards(conn, video_id),
        }
    finally:
        conn.close()


@app.post("/api/videos/{video_id}/marks", status_code=201)
def add_mark(video_id: str, payload: dict, background_tasks: BackgroundTasks) -> dict:
    span = (payload or {}).get("span")
    kind = (payload or {}).get("kind")
    if not (isinstance(span, list) and len(span) == 2) or kind not in ("pron", "meaning"):
        raise HTTPException(400, "need span [start,end] and kind in {pron,meaning}")
    s, e = int(span[0]), int(span[1])
    conn = db.connect(cfg.db_path)
    try:
        db.add_mark(conn, video_id, s, e, kind,
                    (payload or {}).get("status", "unknown"),
                    note=(payload or {}).get("note"))
    finally:
        conn.close()
    # Pre-generate the explanation in the background so the Review page is ready.
    if kind == "meaning":
        background_tasks.add_task(_bg_explain, video_id, s, e)
    return {"ok": True}


@app.delete("/api/videos/{video_id}/marks/{span_start}/{span_end}/{kind}")
def delete_mark(video_id: str, span_start: int, span_end: int, kind: str) -> dict:
    conn = db.connect(cfg.db_path)
    try:
        db.delete_mark(conn, video_id, span_start, span_end, kind)
    finally:
        conn.close()
    return {"ok": True}


@app.get("/api/videos/{video_id}/ipa")
def get_ipa(video_id: str) -> dict:
    """IPA aligned to the rendered token stream (tokens[gi]) + per segment.
    Word-level from Lexique (offline); segment-level needs espeak (else null)."""
    if video_id in _ipa_cache:
        return _ipa_cache[video_id]
    conn = db.connect(cfg.db_path)
    try:
        if conn.execute("SELECT 1 FROM videos WHERE id = ?", (video_id,)).fetchone() is None:
            raise HTTPException(404, "video not found")
        words = db.load_words(conn, video_id)
        segments = db.load_segments(conn, video_id)
        edits = db.load_edits(conn, video_id)
    finally:
        conn.close()

    token_texts: list[str] = []
    seg_ipa: list[str | None] = []
    if segments:
        for seg in render.render(words, edits, segments):
            for t in seg["tokens"]:
                token_texts.append(t["text"])
            seg_ipa.append(phon.clause_ipa("".join(t["text"] for t in seg["tokens"])))
    else:
        token_texts = [w["text"] for w in words]

    tok_ipa = [
        (phon.clause_ipa(t) if " " in t.strip() else phon.word_ipa(t))
        for t in token_texts
    ]
    result = {"tokens": tok_ipa, "segments": seg_ipa}
    _ipa_cache[video_id] = result
    return result


def _span_and_clause(words, rendered, s, e):
    """Reconstruct the marked span's rectified text and its enclosing clause."""
    if rendered:
        clause = ""
        span_toks = []
        for seg in rendered:
            if seg["span_start"] <= s <= seg["span_end"]:
                clause = "".join(t["text"] for t in seg["tokens"]).strip()
            for t in seg["tokens"]:
                if t["src_start"] <= e and s <= t["src_end"]:
                    span_toks.append(t["text"])
        span_text = "".join(span_toks).strip() or "".join(
            w["text"] for w in words[s:e + 1]).strip()
        return span_text, clause or span_text
    span_text = "".join(w["text"] for w in words[s:e + 1]).strip()
    return span_text, span_text


@app.get("/api/videos/{video_id}/translation/{seg_idx}")
def get_translation(video_id: str, seg_idx: int, lang: str = "zh") -> dict:
    conn = db.connect(cfg.db_path)
    try:
        cached = db.get_translation(conn, video_id, seg_idx, lang)
        if cached is not None:
            return {"text": cached, "cached": True}
        rendered = render.render(
            db.load_words(conn, video_id), db.load_edits(conn, video_id),
            db.load_segments(conn, video_id))
        if not (0 <= seg_idx < len(rendered)):
            raise HTTPException(404, "segment not found")
        clause = "".join(t["text"] for t in rendered[seg_idx]["tokens"]).strip()
    finally:
        conn.close()

    text = study.translate_clause(cfg, clause, lang)  # network; conn closed
    conn = db.connect(cfg.db_path)
    try:
        db.store_translation(conn, video_id, seg_idx, lang, text)
    finally:
        conn.close()
    return {"text": text, "cached": False}


def _run_explain(video_id: str, s: int, e: int) -> None:
    """Generate + store one explanation (+ lexeme + suggested cards). Blocking."""
    conn = db.connect(cfg.db_path)
    try:
        words = db.load_words(conn, video_id)
        rendered = render.render(words, db.load_edits(conn, video_id),
                                 db.load_segments(conn, video_id))
        note = next((m.get("note") for m in db.load_marks(conn, video_id)
                     if m["span_start"] == s and m["span_end"] == e
                     and m["kind"] == "meaning"), None)
        span_text, clause = _span_and_clause(words, rendered, s, e)
    finally:
        conn.close()

    # 'known' dedup disabled for now — re-enable by loading
    # db.load_known_lemmas(conn) above and passing known= here.
    data = study.explain_and_suggest(cfg, span_text, clause,
                                     study.profile_str(cfg), note)
    conn = db.connect(cfg.db_path)
    try:
        db.store_explanation(conn, video_id, s, e, data["lang"], data["lemma"],
                             data["pos"], data["explanation"])
        db.upsert_lexeme(conn, data["lemma"], "fr", "learning")
        db.replace_suggested_cards(conn, video_id, s, e, data["cards"])
    finally:
        conn.close()


def _bg_explain(video_id: str, s: int, e: int) -> None:
    """Background pre-generation: skip if already done or the mark was removed."""
    conn = db.connect(cfg.db_path)
    try:
        if db.get_explanation(conn, video_id, s, e):
            return
        still_marked = any(m["span_start"] == s and m["span_end"] == e
                           and m["kind"] == "meaning"
                           for m in db.load_marks(conn, video_id))
    finally:
        conn.close()
    if not still_marked:
        return
    try:
        _run_explain(video_id, s, e)
    except Exception:
        pass  # background best-effort; the Review page can retry on demand


@app.post("/api/videos/{video_id}/explain")
def explain(video_id: str, payload: dict) -> dict:
    span = (payload or {}).get("span")
    if not (isinstance(span, list) and len(span) == 2):
        raise HTTPException(400, "need span [start, end]")
    s, e = int(span[0]), int(span[1])

    conn = db.connect(cfg.db_path)
    try:
        cached = db.get_explanation(conn, video_id, s, e)
        if not cached or (payload or {}).get("force"):
            cached = None
        if cached:
            cards = [c for c in db.load_cards(conn, video_id)
                     if c["span_start"] == s and c["span_end"] == e]
            return {"explanation": cached, "cards": cards, "cached": True}
    finally:
        conn.close()

    _run_explain(video_id, s, e)
    conn = db.connect(cfg.db_path)
    try:
        explanation = db.get_explanation(conn, video_id, s, e)
        cards = [c for c in db.load_cards(conn, video_id)
                 if c["span_start"] == s and c["span_end"] == e]
    finally:
        conn.close()
    return {"explanation": explanation, "cards": cards, "cached": False}


@app.post("/api/videos", status_code=201)
def add_video(payload: dict) -> dict:
    url = (payload or {}).get("url")
    if not url:
        raise HTTPException(400, "missing 'url'")
    from . import fetcher  # local import keeps yt-dlp off the hot import path

    result = fetcher.fetch(url, cfg.audio_dir)
    conn = db.connect(cfg.db_path)
    try:
        db.store_video(conn, result)
    finally:
        conn.close()
    return {"id": result.id, "title": result.title, "words": len(result.words)}


@app.post("/api/videos/{video_id}/progress")
def set_progress(video_id: str, payload: dict) -> dict:
    pos = max(0, int((payload or {}).get("pos_ms") or 0))
    conn = db.connect(cfg.db_path)
    try:
        db.set_progress(conn, video_id, pos)
    finally:
        conn.close()
    return {"ok": True}


@app.post("/api/videos/{video_id}/pipeline")
def run_pipeline(video_id: str, force: bool = False) -> dict:
    from . import pipeline  # local import keeps the SDK off the hot import path

    conn = db.connect(cfg.db_path)
    try:
        result = pipeline.run(conn, cfg, video_id, force=force)
        _ipa_cache.pop(video_id, None)  # render changed -> IPA alignment changed
        return result
    finally:
        conn.close()


@app.post("/api/lexemes")
def set_lexeme(payload: dict) -> dict:
    lemma = (payload or {}).get("lemma")
    if not lemma:
        raise HTTPException(400, "need lemma")
    conn = db.connect(cfg.db_path)
    try:
        db.upsert_lexeme(conn, lemma, (payload or {}).get("lang", "fr"),
                         (payload or {}).get("status", "known"))
    finally:
        conn.close()
    return {"ok": True}


@app.get("/api/videos/{video_id}/export")
def export_video(video_id: str, format: str = "apkg"):
    from . import export as exporter

    conn = db.connect(cfg.db_path)
    try:
        if format == "tsv":
            tsv = exporter.build_tsv(conn, video_id)
            return PlainTextResponse(
                tsv, media_type="text/tab-separated-values",
                headers={"Content-Disposition": f'attachment; filename="echo_{video_id}.tsv"'})
        out_dir = Path(tempfile.mkdtemp(prefix="echo_apkg_"))
        path = exporter.build_apkg(cfg, conn, video_id, out_dir)
    finally:
        conn.close()
    return FileResponse(path, filename=f"echo_{video_id}.apkg",
                        media_type="application/octet-stream")


@app.post("/api/cards/{card_id}/status")
def set_card_status(card_id: int, payload: dict) -> dict:
    status = (payload or {}).get("status")
    if status not in ("suggested", "accepted", "rejected"):
        raise HTTPException(400, "status must be suggested|accepted|rejected")
    conn = db.connect(cfg.db_path)
    try:
        db.set_card_status(conn, card_id, status)
    finally:
        conn.close()
    return {"ok": True}


@app.get("/api/review")
def review_queue() -> dict:
    import datetime as _dt

    today = _dt.date.today().isoformat()
    conn = db.connect(cfg.db_path)
    try:
        cards = db.due_cards(conn, today)
        rcache: dict = {}
        out = []
        for c in cards:
            vid = c["video_id"]
            if vid not in rcache:
                vrow = conn.execute("SELECT title FROM videos WHERE id = ?",
                                    (vid,)).fetchone()
                rendered = render.render(db.load_words(conn, vid),
                                         db.load_edits(conn, vid),
                                         db.load_segments(conn, vid))
                exps = {(e["span_start"], e["span_end"]): e
                        for e in db.load_explanations(conn, vid)}
                rcache[vid] = (vrow["title"] if vrow else vid, rendered, exps)
            title, rendered, exps = rcache[vid]
            seg = next((s for s in rendered
                        if s["span_start"] <= c["span_start"] <= s["span_end"]), None)
            out.append({
                "id": c["id"], "video_id": vid, "video_title": title,
                "kind": c["kind"], "front": c["front"], "back": c["back"],
                "span": [c["span_start"], c["span_end"]],
                "clause_start_ms": seg["start_ms"] if seg else None,
                "clause_end_ms": seg["end_ms"] if seg else None,
                "explanation": exps.get((c["span_start"], c["span_end"])),
            })
        return {"due": out, "count": len(out)}
    finally:
        conn.close()


@app.post("/api/cards/{card_id}/review")
def review_card(card_id: int, payload: dict) -> dict:
    grade = (payload or {}).get("grade")
    if grade not in ("again", "good", "easy"):
        raise HTTPException(400, "grade must be again|good|easy")
    conn = db.connect(cfg.db_path)
    try:
        card = db.get_card(conn, card_id)
        if card is None:
            raise HTTPException(404, "card not found")
        sched = srs.schedule(card, grade)
        db.update_card_schedule(conn, card_id, sched)
        if sched["graduated"]:
            exp = db.get_explanation(conn, card["video_id"],
                                     card["span_start"], card["span_end"])
            if exp and exp.get("lemma"):
                db.upsert_lexeme(conn, exp["lemma"], "fr", "known")
        return {"ok": True, "due": sched["due"], "interval": sched["interval"]}
    finally:
        conn.close()


@app.get("/audio/{video_id}.opus")
def get_audio(video_id: str) -> FileResponse:
    path = cfg.audio_dir / f"{video_id}.opus"
    if not path.exists():
        raise HTTPException(404, "audio not found")
    # Starlette FileResponse honors the Range header (206) — verify in T5.
    return FileResponse(path, media_type=AUDIO_MEDIA_TYPE)


# Serve the built SPA last so it doesn't shadow the API. Only if built.
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="spa")
