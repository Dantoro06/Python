from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = PROJECT_ROOT / "reports"
DASHBOARD_DATA_DIR = PROJECT_ROOT / "Data Dashboard"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)
DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
