"""Load the committed fixture into the data dir + DB, no network. Dev only:

    uv run python -m echo.seed
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import config, db, fetcher

FIXTURE_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
VIDEO_ID = "CE3foG8FRz4"
SUB_LANG = "fr-orig"


def main() -> None:
    cfg = config.get()
    db.init_db(cfg.db_path)

    info = json.loads((FIXTURE_DIR / f"{VIDEO_ID}.info.json").read_text("utf-8"))
    dst_opus = cfg.audio_dir / f"{VIDEO_ID}.opus"
    shutil.copyfile(FIXTURE_DIR / f"{VIDEO_ID}.opus", dst_opus)

    result = fetcher.build_result(
        dst_opus, FIXTURE_DIR / f"{VIDEO_ID}.{SUB_LANG}.json3", info
    )
    conn = db.connect(cfg.db_path)
    try:
        db.store_video(conn, result)
    finally:
        conn.close()
    print(f"seeded {VIDEO_ID} ({result.title!r}): "
          f"{len(result.words)} words, audio -> {dst_opus}")


if __name__ == "__main__":
    main()
