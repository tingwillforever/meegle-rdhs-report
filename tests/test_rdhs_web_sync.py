from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.error import HTTPError

import scripts.rdhs_snapshot_sync as sync_module
from scripts.rdhs_snapshot_sync import build_snapshot
from scripts.rdhs_snapshot_sync import generate_report
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
        self.assertEqual(snapshot["audit"]["excludedProductAttributeCount"], 0)

    def test_build_snapshot_extracts_product_dependency_metrics(self) -> None:
        snapshot = build_snapshot(
            _load_json(REPORT_DIR / "report_data.json"),
            _load_json(REPORT_DIR / "audit_manifest.json"),
            cadence="monthly",
        )

        product = next(
            row for row in snapshot["products"]
            if row["businessLine"] == "AI文娱业务群" and row["product"] == "讯飞输入法"
        )
        metrics = {row["label"]: row for row in product["dependencyMetrics"]}

        self.assertEqual(product["subLine"], None)
        self.assertEqual(metrics["月人均需求吞吐量"]["value"], 0.0)
        self.assertEqual(metrics["月人均需求吞吐量"]["tone"], "critical")
        self.assertAlmostEqual(metrics["需求开发周期"]["value"], 88.41)
        self.assertEqual(metrics["需求开发周期"]["tone"], "critical")
        self.assertAlmostEqual(metrics["需求交付周期"]["value"], 90.85)
        self.assertEqual(metrics["需求交付周期"]["tone"], "critical")
        self.assertAlmostEqual(metrics["需求发布闭环率"]["value"], 1 / 6)
        self.assertEqual(metrics["需求发布闭环率"]["unit"], "%")
        self.assertEqual(metrics["需求发布闭环率"]["tone"], "critical")
        self.assertAlmostEqual(metrics["需求积压占比"]["value"], 0.5166)
        self.assertEqual(metrics["需求积压占比"]["tone"], "critical")

    def test_build_snapshot_rejects_weekly_periods(self) -> None:
        manifest = _load_json(REPORT_DIR / "audit_manifest.json")
        manifest["as_of"] = "2026-08-16"

        with self.assertRaisesRegex(ValueError, "cadence must be monthly"):
            build_snapshot(
                _load_json(REPORT_DIR / "report_data.json"),
                manifest,
                cadence="weekly",
            )

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

    def test_current_month_cache_uses_current_month_report_mode(self) -> None:
        captured: dict[str, object] = {}

        class Completed:
            returncode = 0
            stdout = '{"run_dir": "/tmp/current-month-run"}\n'
            stderr = ""

        def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
            captured["command"] = command
            captured["cwd"] = kwargs["cwd"]
            return Completed()

        original = sync_module.subprocess.run
        sync_module.subprocess.run = fake_run
        try:
            run_dir = generate_report(
                "monthly",
                Path("/tmp/rdhs-output"),
                "2026-08-19",
                current_month_cache=True,
            )
        finally:
            sync_module.subprocess.run = original

        command = captured["command"]
        self.assertEqual(run_dir, Path("/tmp/current-month-run"))
        self.assertIn("--mode", command)
        self.assertIn("monthly", command)
        self.assertNotIn("last-month", command)
        self.assertIn("--as-of", command)
        self.assertIn("2026-08-19", command)


if __name__ == "__main__":
    unittest.main()
