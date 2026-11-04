"""Central configuration. Values can be overridden with environment variables."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.getenv("UDYAM_DATA_DIR", REPO_ROOT / "data"))
VAR_DIR = Path(os.getenv("UDYAM_VAR_DIR", REPO_ROOT / "var"))

# The case says to treat 2026-07-15 as "today" for every date-based check.
TODAY = date.fromisoformat(os.getenv("UDYAM_TODAY", "2026-07-15"))

GST_RATE = 0.18
