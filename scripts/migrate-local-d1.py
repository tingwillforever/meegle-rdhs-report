#!/usr/bin/env python3
"""Apply the RDHS D1 schema to the local Miniflare SQLite database."""

from __future__ import annotations

from pathlib import Path
import sqlite3


SITE_ROOT = Path(__file__).resolve().parents[1]
D1_ROOT = SITE_ROOT / ".wrangler" / "state" / "v3" / "d1" / "miniflare-D1DatabaseObject"
MIGRATION = SITE_ROOT / "drizzle" / "0000_normal_zemo.sql"


def _find_local_database() -> Path:
    candidates = sorted(
        path for path in D1_ROOT.glob("*.sqlite") if path.name != "metadata.sqlite"
    )
    if not candidates:
        raise SystemExit(
            "Local D1 database not found. Start `npm run dev` once, then rerun this command."
        )
    if len(candidates) == 1:
        return candidates[0]
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main() -> int:
    database = _find_local_database()
    sql = MIGRATION.read_text(encoding="utf-8")
    with sqlite3.connect(database) as connection:
        existing = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rdhs_snapshots'"
        ).fetchone()
        if existing:
            print(f"Local D1 schema already exists: {database}")
            return 0
        connection.executescript(sql)
    print(f"Local D1 schema migrated: {database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
