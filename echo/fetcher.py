"""The ONLY module that touches yt-dlp. All breakage is contained here.

Pulls bestaudio (opus) + json3 auto-captions for one video, remuxes audio to
ogg/.opus (stream copy, no re-encode), and parses captions into words.

Operational notes (YouTube is hostile, 2026):
- Needs deno on PATH for JS-challenge ('n' signature) solving; we add ~/.deno/bin.
- `--remote-components ejs:github` lets yt-dlp fetch the deno solver on demand.
- Fallback: cookies_from_browser -> yt-dlp --cookies-from-browser.
- POT provider (bgutil) is auto-used if its server is reachable; not required here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import json3


@dataclass
class FetchResult:
    id: str
    title: str
    channel: str
    lang: str
    duration_ms: int
    description: str
    audio_path: Path            # absolute path to the .opus file
    words: list[json3.Word]


def _yt_dlp() -> str:
    return shutil.which("yt-dlp") or os.path.expanduser("~/.local/bin/yt-dlp")


def _env() -> dict:
    env = os.environ.copy()
    deno = os.path.expanduser("~/.deno/bin")
    if os.path.isdir(deno):
        env["PATH"] = deno + os.pathsep + env.get("PATH", "")
    return env


def _meta_from_info(info: dict) -> dict:
    return {
        "id": info["id"],
        "title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "lang": info.get("language") or "",
        "duration_ms": int((info.get("duration") or 0) * 1000),
        "description": info.get("description") or "",
    }


def _remux_to_opus(src: Path, dst: Path) -> None:
    """Stream-copy the opus track into an ogg/.opus container (no re-encode)."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-map", "0:a",
         "-c", "copy", str(dst)],
        check=True,
    )


def build_result(audio_path: Path, json3_path: Path, info: dict) -> FetchResult:
    """Assemble a FetchResult from local files — shared by fetch() and seeding.
    No network. This is the parse+package step."""
    meta = _meta_from_info(info)
    return FetchResult(
        **meta,
        audio_path=audio_path,
        words=json3.parse_file(json3_path),
    )


def fetch(
    url: str,
    audio_dir: Path,
    *,
    sub_lang: str = "fr-orig",
    cookies_from_browser: str | None = None,
) -> FetchResult:
    """Fetch + cache one video. Permanent cache: if the .opus already exists,
    re-parse from cached json3 without touching the network."""
    audio_dir = Path(audio_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Probe id cheaply to check the cache before any heavy download.
    vid = subprocess.run(
        [_yt_dlp(), "--no-warnings", "--skip-download", "--print", "%(id)s", url],
        capture_output=True, text=True, env=_env(), check=True,
    ).stdout.strip().splitlines()[-1]

    opus = audio_dir / f"{vid}.opus"
    raw_json3 = audio_dir / f"{vid}.{sub_lang}.json3"
    info_json = audio_dir / f"{vid}.info.json"

    if opus.exists() and raw_json3.exists() and info_json.exists():
        info = json.loads(info_json.read_text(encoding="utf-8"))
        return build_result(opus, raw_json3, info)

    cmd = [
        _yt_dlp(), "--remote-components", "ejs:github", "--no-warnings",
        "-f", "bestaudio[acodec=opus]/bestaudio",
        "--write-auto-subs", "--sub-langs", sub_lang, "--sub-format", "json3",
        "--write-info-json",
        "-o", str(audio_dir / "%(id)s.%(ext)s"),
    ]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    cmd.append(url)
    subprocess.run(cmd, env=_env(), check=True)

    # yt-dlp wrote {id}.<ext> for audio (webm/opus). Remux to {id}.opus.
    downloaded = next(
        (p for p in audio_dir.glob(f"{vid}.*")
         if p.suffix in {".webm", ".opus", ".m4a", ".ogg"} and p != opus),
        None,
    )
    if downloaded is None:
        raise RuntimeError(f"audio not found for {vid} after download")
    if downloaded != opus:
        _remux_to_opus(downloaded, opus)
        if downloaded.suffix != ".opus":
            downloaded.unlink(missing_ok=True)

    info = json.loads(info_json.read_text(encoding="utf-8"))
    return build_result(opus, raw_json3, info)
