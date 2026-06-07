"""Entrypoint: `uv run python -m echo` boots the server."""

from __future__ import annotations

import uvicorn

from . import config


def main() -> None:
    cfg = config.get()
    uvicorn.run("echo.app:app", host="127.0.0.1", port=cfg.port, reload=True)


if __name__ == "__main__":
    main()
