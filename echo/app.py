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

from . import config, db

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
        words = conn.execute(
            "SELECT idx, text, start_ms, dur_ms FROM words "
            "WHERE video_id = ? ORDER BY idx",
            (video_id,),
        ).fetchall()
        # edits/segments/marks land in later slices.
        return {
            "video": dict(video),
            "words": [dict(w) for w in words],
            "edits": [],
            "segments": [],
            "marks": [],
        }
    finally:
        conn.close()


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
