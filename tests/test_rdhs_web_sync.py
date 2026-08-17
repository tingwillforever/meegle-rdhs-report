from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.error import HTTPError

from scripts.rdhs_snapshot_sync import build_snapshot
from scripts.rdhs_snapshot_sync import upload_snapshot


WORKSPACE = Path(__file__).resolve().parents[2]
REPORT_DIR = (
    WORKSPACE
    / "reports"
    / "periodic-rerun-20260817"
    / "2026-08"
    / "monthly-report"
)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


class SnapshotSyncTests(unittest.TestCase):
    def test_build_snapshot_preserves_master_driven_product_coverage(self) -> None:
        snapshot = build_snapshot(
            _load_json(REPORT_DIR / "report_data.json"),
            _load_json(REPORT_DIR / "audit_manifest.json"),
            cadence="monthly",
        )

        self.assertEqual(snapshot["schemaVersion"], 1)
        self.assertEqual(snapshot["periodKey"], "2026-08")
        self.assertEqual(len(snapshot["products"]), 67)
        self.assertEqual(
            len([row for row in snapshot["products"] if row["rdhs"] is not None]),
            60,
        )
        self.assertEqual(
            len([row for row in snapshot["products"] if row["rdhs"] is None]),
            7,
        )
        self.assertEqual(
            sum(row["productTotal"] for row in snapshot["businessLines"]),
            67,
        )
        self.assertTrue(
            all(row["businessLine"] != "测试业务线" for row in snapshot["products"])
        )
        self.assertEqual(snapshot["audit"]["excludedTestBusinessLineCount"], 2)

    def test_build_snapshot_uses_as_of_date_for_weekly_period(self) -> None:
        manifest = _load_json(REPORT_DIR / "audit_manifest.json")
        manifest["as_of"] = "2026-08-16"

        snapshot = build_snapshot(
            _load_json(REPORT_DIR / "report_data.json"),
            manifest,
            cadence="weekly",
        )

        self.assertEqual(snapshot["periodKey"], "2026-08-16")
        self.assertEqual(snapshot["cadence"], "weekly")

    def test_upload_snapshot_reports_remote_validation_failure(self) -> None:
        class RejectingOpener:
            def open(self, request, timeout):  # noqa: ANN001
                raise HTTPError(
                    request.full_url,
                    422,
                    "Unprocessable Entity",
                    {},
                    None,
                )

        with self.assertRaisesRegex(RuntimeError, "422"):
            upload_snapshot(
                "https://rdhs.example.com",
                "secret-token",
                {"schemaVersion": 1},
                opener=RejectingOpener(),
            )

    def test_cli_wrapper_runs_from_the_site_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/sync-rdhs-snapshot.py",
                    "--cadence",
                    "monthly",
                    "--source-dir",
                    str(REPORT_DIR),
                    "--output-root",
                    directory,
                    "--dry-run",
                ],
                cwd=WORKSPACE / "rdhs-web",
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertFalse(result["uploaded"])


if __name__ == "__main__":
    unittest.main()
