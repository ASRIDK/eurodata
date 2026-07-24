"""Emit a shields.io *endpoint* badge describing dataset freshness.

Reads the built DuckDB read-only and writes a small JSON file that
shields.io renders as a live badge:

    https://img.shields.io/endpoint?url=<raw-url-of-this-json>

Green when the newest data year is within `warn_years`, yellow otherwise.
Run after an ingestion so the badge tracks the latest release.

    python scripts/emit_freshness_badge.py [output.json]
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from _bootstrap import ensure_paths

ensure_paths()

from eurodata.db import connect  # noqa: E402

DEFAULT_OUT = Path(".github/badges/data-freshness.json")
WARN_YEARS = 3


def build_badge(con) -> dict:
    rows = con.execute("SELECT COUNT(*) FROM statistic_record").fetchone()[0]
    last_year = con.execute("SELECT MAX(year) FROM statistic_record").fetchone()[0]
    vintage = con.execute(
        "SELECT CAST(MAX(vintage_date) AS VARCHAR) FROM statistic_record").fetchone()[0]
    age = dt.date.today().year - int(last_year) if last_year is not None else None
    color = "brightgreen" if (age is not None and age <= WARN_YEARS) else "yellow"
    message = f"{rows:,} rows · to {last_year}" if last_year else "empty"
    if vintage:
        message += f" · {vintage}"
    return {"schemaVersion": 1, "label": "data", "message": message, "color": color}


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    con = connect(read_only=True)
    try:
        badge = build_badge(con)
    finally:
        con.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(badge, indent=2) + "\n")
    print(f"wrote {out}: {badge['message']} ({badge['color']})")


if __name__ == "__main__":
    main()
