from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def get_database_path() -> Path:
    value = Path(os.getenv("DATABASE_PATH", "data/olist.db")).expanduser()
    return value if value.is_absolute() else PROJECT_ROOT / value


def get_query_timeout_seconds() -> int:
    try:
        return max(1, min(30, int(os.getenv("MAX_QUERY_SECONDS", "4"))))
    except ValueError:
        return 4
