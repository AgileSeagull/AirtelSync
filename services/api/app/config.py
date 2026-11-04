"""Central configuration. Values can be overridden with environment variables."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
API_DIR = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Real environment variables always win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


_load_dotenv(API_DIR / ".env")
DATA_DIR = Path(os.getenv("UDYAM_DATA_DIR", REPO_ROOT / "data"))
VAR_DIR = Path(os.getenv("UDYAM_VAR_DIR", REPO_ROOT / "var"))

# The case says to treat 2026-07-15 as "today" for every date-based check.
TODAY = date.fromisoformat(os.getenv("UDYAM_TODAY", "2026-07-15"))

GST_RATE = 0.18
