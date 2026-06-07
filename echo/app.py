"""FastAPI app: serves the SPA, audio (with Range), and the data API.

Route convention: data endpoints under /api/*, audio under /audio/*, SPA at /.
(Refines the sketch in plan/initial.md: /api prefix avoids clashing with the
client-routed SPA.)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, phon, render

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
        }
    finally:
        conn.close()


@app.post("/api/videos/{video_id}/marks", status_code=201)
def add_mark(video_id: str, payload: dict) -> dict:
    span = (payload or {}).get("span")
    kind = (payload or {}).get("kind")
    if not (isinstance(span, list) and len(span) == 2) or kind not in ("pron", "meaning"):
        raise HTTPException(400, "need span [start,end] and kind in {pron,meaning}")
    conn = db.connect(cfg.db_path)
    try:
        db.add_mark(conn, video_id, int(span[0]), int(span[1]), kind,
                    (payload or {}).get("status", "unknown"))
    finally:
        conn.close()
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
