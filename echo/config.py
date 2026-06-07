"""Load and expose config.toml. No app logic here — just resolved settings."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Repo-root config by default; override with ECHO_CONFIG for tests/alt setups.
CONFIG_PATH = Path(os.environ.get("ECHO_CONFIG", "config.toml"))


@dataclass(frozen=True)
class Config:
    raw: dict
    data_dir: Path
    audio_dir: Path
    db_path: Path
    port: int
    llm_provider: str
    llm_model: str           # explanations / rectify (strongest)
    llm_translate_model: str  # bulk clause translation (cheap)
    explain_lang: str        # fixed language for explanations + card glosses
    api_key_env: str
    llm_api_key: str | None  # inline key from config (local-only convenience)

    @property
    def api_key(self) -> str | None:
        # 1) explicit inline key wins.
        if self.llm_api_key:
            return self.llm_api_key
        # 2) if a literal key was pasted into api_key_env, accept it (friendly).
        if self.api_key_env.startswith("sk-"):
            return self.api_key_env
        # 3) otherwise treat api_key_env as the name of an env var.
        return os.environ.get(self.api_key_env)


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency). Sets vars that aren't already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def load(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    _load_dotenv(path.resolve().parent / ".env")
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    data_dir = Path(raw["paths"]["data_dir"]).expanduser()
    audio_dir = data_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    server = raw.get("server", {})
    llm = raw.get("llm", {})
    return Config(
        raw=raw,
        data_dir=data_dir,
        audio_dir=audio_dir,
        db_path=data_dir / "app.db",
        port=int(server.get("port", 7777)),
        llm_provider=llm.get("provider", "anthropic"),
        llm_model=llm.get("model", ""),
        llm_translate_model=llm.get("translate_model", "claude-haiku-4-5"),
        explain_lang=llm.get("explain_lang", "zh"),
        api_key_env=llm.get("api_key_env", "ANTHROPIC_API_KEY"),
        llm_api_key=llm.get("api_key"),
    )


@lru_cache(maxsize=1)
def get() -> Config:
    """Cached singleton for app use."""
    return load()
