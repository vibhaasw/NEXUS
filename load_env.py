"""Load environment variables from a .env file (stdlib only)."""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def load_dotenv(path: Path | None = None) -> Path | None:
    """Load KEY=VALUE pairs from .env into os.environ (does not override existing vars)."""
    env_path = path or repo_root() / ".env"
    if not env_path.exists():
        return None

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value

    return env_path
