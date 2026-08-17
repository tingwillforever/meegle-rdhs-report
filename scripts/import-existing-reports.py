#!/usr/bin/env python3
"""Import verified report_data/audit pairs into the hosted RDHS history."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.rdhs_snapshot_sync import build_snapshot
from scripts.rdhs_snapshot_sync import upload_snapshot


def load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file is not an object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="导入已验证的 RDHS 历史报告")
    parser.add_argument("report_roots", nargs="+", type=Path)
    parser.add_argument("--site-url", default=os.environ.get("RDHS_SITE_URL", ""))
    parser.add_argument("--token", default=os.environ.get("RDHS_INGEST_TOKEN", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    imported: list[dict[str, object]] = []
    seen_hashes: set[str] = set()
    for root in args.report_roots:
        for report_path in sorted(root.rglob("report_data.json")):
            manifest_path = report_path.with_name("audit_manifest.json")
            if not manifest_path.exists():
                continue
            manifest = load_json(manifest_path)
            mode = str(manifest.get("mode") or "")
            if mode not in {"weekly", "monthly"}:
                continue
            snapshot = build_snapshot(load_json(report_path), manifest, cadence=mode)
            source_hash = str(snapshot["source"]["sha256"])
            if source_hash in seen_hashes:
                continue
            seen_hashes.add(source_hash)
            remote = None if args.dry_run else upload_snapshot(args.site_url, args.token, snapshot)
            imported.append(
                {
                    "periodKey": snapshot["periodKey"],
                    "cadence": mode,
                    "source": str(report_path),
                    "remote": remote,
                }
            )
    print(json.dumps({"imported": imported}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
