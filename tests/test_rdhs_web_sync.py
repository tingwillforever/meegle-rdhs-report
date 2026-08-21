from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError

import scripts.rdhs_snapshot_sync as sync_module
from scripts.rdhs_snapshot_sync import build_snapshot
from scripts.rdhs_snapshot_sync import generate_report
from scripts.rdhs_snapshot_sync import hydrate_remote_baseline
from scripts.rdhs_snapshot_sync import persist_remote_baseline
from scripts.rdhs_snapshot_sync import prune_report_output
from scripts.rdhs_snapshot_sync import remote_sync_lease
from scripts.rdhs_snapshot_sync import upload_snapshot


SITE_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = SITE_ROOT / "tests" / "fixtures" / "monthly-report"


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


class SnapshotSyncTests(unittest.TestCase):
    def test_remote_baseline_is_restored_to_the_report_runtime_path(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):  # noqa: ANN002
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "periodKey": "2026-07",
                        "payload": {"rows": [["product-a", 60]]},
                        "metadata": {
                            "chart_id": "chart-previous",
                            "fetched_at": "2026-08-01T09:00:00+08:00",
                        },
                    }
                ).encode("utf-8")

        class Opener:
            request = None

            def open(self, request, timeout):  # noqa: ANN001
                self.request = request
                self.timeout = timeout
                return Response()

        opener = Opener()
        with tempfile.TemporaryDirectory() as directory:
            restored = hydrate_remote_baseline(
                "https://rdhs-report-web/meegle-rdhs-report",
                "test-token",
                Path(directory),
                date(2026, 8, 31),
                opener=opener,
            )
            baseline_path = Path(directory) / "2026-08" / "baselines" / "2026-07.json"
            metadata_path = baseline_path.with_suffix(".metadata.json")
            self.assertTrue(restored)
            self.assertEqual(_load_json(baseline_path), {"rows": [["product-a", 60]]})
            self.assertEqual(_load_json(metadata_path)["chart_id"], "chart-previous")

        self.assertIn("period=2026-07", opener.request.full_url)
        self.assertEqual(opener.request.headers["Authorization"], "Bearer test-token")

    def test_generated_baseline_is_persisted_through_the_web_api(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):  # noqa: ANN002
                return False

            def read(self) -> bytes:
                return b'{"stored":true}'

        class Opener:
            request = None

            def open(self, request, timeout):  # noqa: ANN001
                self.request = request
                return Response()

        opener = Opener()
        with tempfile.TemporaryDirectory() as directory:
            baseline_path = Path(directory) / "2026-09" / "baselines" / "2026-08.json"
            baseline_path.parent.mkdir(parents=True)
            baseline_path.write_text('{"rows":[["product-a",61]]}', encoding="utf-8")
            baseline_path.with_suffix(".metadata.json").write_text(
                '{"chart_id":"chart-previous","fetched_at":"2026-09-01T09:00:00+08:00"}',
                encoding="utf-8",
            )

            persist_remote_baseline(
                "https://rdhs-report-web/meegle-rdhs-report",
                "test-token",
                Path(directory),
                date(2026, 9, 1),
                opener=opener,
            )

        body = json.loads(opener.request.data)
        self.assertEqual(opener.request.method, "PUT")
        self.assertEqual(body["periodKey"], "2026-08")
        self.assertEqual(body["payload"]["rows"], [["product-a", 61]])

    def test_remote_sync_lease_is_released_after_the_report_finishes(self) -> None:
        requests = []

        class Response:
            def __init__(self, payload):  # noqa: ANN001
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args):  # noqa: ANN002
                return False

            def read(self) -> bytes:
                return json.dumps(self.payload).encode("utf-8")

        class Opener:
            def open(self, request, timeout):  # noqa: ANN001
                requests.append(request)
                if request.full_url.endswith("/lock/acquire"):
                    return Response(
                        {
                            "acquired": True,
                            "name": "report-sync",
                            "owner": "owner-1",
                            "expiresAt": "2026-08-21T10:30:00.000Z",
                        }
                    )
                return Response({"released": True})

        with remote_sync_lease(
            "https://rdhs-report-web/meegle-rdhs-report",
            "test-token",
            owner="owner-1",
            ttl_seconds=1800,
            opener=Opener(),
        ):
            self.assertEqual(len(requests), 1)

        self.assertEqual(len(requests), 2)
        self.assertTrue(requests[0].full_url.endswith("/lock/acquire"))
        self.assertTrue(requests[1].full_url.endswith("/lock/release"))

    def test_build_snapshot_preserves_master_driven_product_coverage(self) -> None:
        snapshot = build_snapshot(
            _load_json(REPORT_DIR / "report_data.json"),
            _load_json(REPORT_DIR / "audit_manifest.json"),
            cadence="monthly",
        )

        self.assertEqual(snapshot["schemaVersion"], 1)
        self.assertEqual(snapshot["periodKey"], "2026-08")
        self.assertEqual(len(snapshot["products"]), 61)
        self.assertEqual(
            len([row for row in snapshot["products"] if row["rdhs"] is not None]),
            55,
        )
        self.assertEqual(
            len([row for row in snapshot["products"] if row["rdhs"] is None]),
            6,
        )
        self.assertEqual(
            sum(row["productTotal"] for row in snapshot["businessLines"]),
            61,
        )
        self.assertTrue(
            all(row["businessLine"] != "测试业务线" for row in snapshot["products"])
        )
        self.assertEqual(snapshot["audit"]["excludedTestBusinessLineCount"], 2)
        self.assertEqual(snapshot["audit"]["excludedProductAttributeCount"], 9)

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
        self.assertAlmostEqual(metrics["需求开发周期"]["value"], 88.21)
        self.assertEqual(metrics["需求开发周期"]["tone"], "critical")
        self.assertAlmostEqual(metrics["需求交付周期"]["value"], 91.11)
        self.assertEqual(metrics["需求交付周期"]["tone"], "critical")
        self.assertAlmostEqual(metrics["需求发布闭环率"]["value"], 1 / 7)
        self.assertEqual(metrics["需求发布闭环率"]["unit"], "%")
        self.assertEqual(metrics["需求发布闭环率"]["tone"], "critical")
        self.assertAlmostEqual(metrics["需求积压占比"]["value"], 0.5082)
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

    def test_upload_snapshot_allows_explicit_internal_http_site_url(self) -> None:
        class RejectingOpener:
            def open(self, request, timeout):  # noqa: ANN001
                raise HTTPError(
                    request.full_url,
                    422,
                    "Unprocessable Entity",
                    {},
                    None,
                )

        previous = os.environ.get("RDHS_ALLOW_INSECURE_SITE_URL")
        os.environ["RDHS_ALLOW_INSECURE_SITE_URL"] = "true"
        try:
            with self.assertRaisesRegex(RuntimeError, "422"):
                upload_snapshot(
                    "http://rdhs-report-web:3000/meegle-rdhs-report",
                    "secret-token",
                    {"schemaVersion": 1},
                    opener=RejectingOpener(),
                )
        finally:
            if previous is None:
                os.environ.pop("RDHS_ALLOW_INSECURE_SITE_URL", None)
            else:
                os.environ["RDHS_ALLOW_INSECURE_SITE_URL"] = previous

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
                cwd=SITE_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertFalse(result["uploaded"])

    def test_monthly_sync_uses_configured_weekly_command_and_previous_month_end(self) -> None:
        captured: dict[str, object] = {}

        class Completed:
            returncode = 0
            stdout = '{"run_dir": "/tmp/current-month-run"}\n'
            stderr = ""

        def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
            captured["command"] = command
            captured["cwd"] = kwargs["cwd"]
            return Completed()

        original_run = sync_module.subprocess.run
        original_monthly_command = os.environ.get("RDHS_MONTHLY_REPORT_COMMAND")
        original_baseline_command = os.environ.get("RDHS_MONTHLY_BASELINE_COMMAND")
        os.environ["RDHS_MONTHLY_REPORT_COMMAND"] = "python3 report.py --mode weekly"
        os.environ.pop("RDHS_MONTHLY_BASELINE_COMMAND", None)
        sync_module.subprocess.run = fake_run
        try:
            run_dir = generate_report(
                "monthly",
                Path("/tmp/rdhs-output"),
                None,
                current_month_cache=False,
            )
        finally:
            sync_module.subprocess.run = original_run
            if original_monthly_command is None:
                del os.environ["RDHS_MONTHLY_REPORT_COMMAND"]
            else:
                os.environ["RDHS_MONTHLY_REPORT_COMMAND"] = original_monthly_command
            if original_baseline_command is not None:
                os.environ["RDHS_MONTHLY_BASELINE_COMMAND"] = original_baseline_command

        command = captured["command"]
        self.assertEqual(run_dir, Path("/tmp/current-month-run"))
        self.assertEqual(
            command[:4],
            ["python3", "report.py", "--mode", "weekly"],
        )
        self.assertIn("--no-publish", command)
        self.assertIn("--output-root", command)
        self.assertIn("--as-of", command)
        self.assertIn("2026-07-31", command)

    def test_current_month_cache_uses_its_own_configured_command(self) -> None:
        captured: dict[str, object] = {}

        class Completed:
            returncode = 0
            stdout = '{"run_dir": "/tmp/current-month-run"}\n'
            stderr = ""

        def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
            captured["command"] = command
            return Completed()

        original_run = sync_module.subprocess.run
        original_current_command = os.environ.get("RDHS_CURRENT_REPORT_COMMAND")
        os.environ["RDHS_CURRENT_REPORT_COMMAND"] = "python3 report.py --mode weekly"
        sync_module.subprocess.run = fake_run
        try:
            generate_report(
                "monthly",
                Path("/tmp/rdhs-output"),
                "2026-08-19",
                current_month_cache=True,
            )
        finally:
            sync_module.subprocess.run = original_run
            if original_current_command is None:
                del os.environ["RDHS_CURRENT_REPORT_COMMAND"]
            else:
                os.environ["RDHS_CURRENT_REPORT_COMMAND"] = original_current_command

        command = captured["command"]
        self.assertEqual(command[:4], ["python3", "report.py", "--mode", "weekly"])
        self.assertIn("2026-08-19", command)

    def test_report_output_lock_serializes_separate_sync_processes(self) -> None:
        script = """
from pathlib import Path
import sys
import time
from scripts.rdhs_snapshot_sync import _report_output_lock

with _report_output_lock(Path(sys.argv[1])):
    print("locked", flush=True)
    time.sleep(0.25)
"""
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen(
                [sys.executable, "-c", script, directory],
                cwd=SITE_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                assert process.stdout is not None
                self.assertEqual(process.stdout.readline().strip(), "locked")
                started_at = time.monotonic()
                with sync_module._report_output_lock(Path(directory)):
                    pass
                self.assertGreaterEqual(time.monotonic() - started_at, 0.15)
            finally:
                stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, f"{stdout}\n{stderr}")

    def test_report_output_pruning_keeps_recent_months_and_ignores_unknown_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            for month in ("2026-02", "2026-03", "2026-08"):
                (output_root / month / "week-run").mkdir(parents=True)
            (output_root / "site-snapshots").mkdir()
            (output_root / "site-snapshots" / "monthly-2026-02.json").write_text(
                "{}", encoding="utf-8"
            )
            (output_root / "site-snapshots" / "monthly-2026-03.json").write_text(
                "{}", encoding="utf-8"
            )
            (output_root / "keep-me").mkdir()

            prune_report_output(output_root, current_date=date(2026, 8, 20), retention_months=6)

            self.assertFalse((output_root / "2026-02").exists())
            self.assertTrue((output_root / "2026-03").exists())
            self.assertTrue((output_root / "2026-08").exists())
            self.assertFalse((output_root / "site-snapshots" / "monthly-2026-02.json").exists())
            self.assertTrue((output_root / "site-snapshots" / "monthly-2026-03.json").exists())
            self.assertTrue((output_root / "keep-me").exists())

    def test_report_command_honors_configured_timeout(self) -> None:
        captured: dict[str, object] = {}

        class Completed:
            returncode = 0
            stdout = '{"run_dir": "/tmp/current-month-run"}\n'
            stderr = ""

        def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
            captured["timeout"] = kwargs["timeout"]
            return Completed()

        previous = os.environ.get("RDHS_REPORT_COMMAND_TIMEOUT_SECONDS")
        original_run = sync_module.subprocess.run
        os.environ["RDHS_REPORT_COMMAND_TIMEOUT_SECONDS"] = "90"
        sync_module.subprocess.run = fake_run
        try:
            generate_report("monthly", Path("/tmp/rdhs-output"), "2026-08-19")
        finally:
            sync_module.subprocess.run = original_run
            if previous is None:
                del os.environ["RDHS_REPORT_COMMAND_TIMEOUT_SECONDS"]
            else:
                os.environ["RDHS_REPORT_COMMAND_TIMEOUT_SECONDS"] = previous

        self.assertEqual(captured["timeout"], 90)

    def test_refresh_runner_refuses_an_empty_webhook_token(self) -> None:
        module = runpy.run_path(str(SITE_ROOT / "scripts" / "local-refresh-runner.py"))
        previous = os.environ.get("RDHS_REFRESH_WEBHOOK_TOKEN")
        os.environ.pop("RDHS_REFRESH_WEBHOOK_TOKEN", None)
        try:
            with self.assertRaisesRegex(RuntimeError, "RDHS_REFRESH_WEBHOOK_TOKEN"):
                module["required_refresh_webhook_token"]()
        finally:
            if previous is not None:
                os.environ["RDHS_REFRESH_WEBHOOK_TOKEN"] = previous

    def test_monthly_sync_uses_month_start_baseline_and_previous_month_end_report(self) -> None:
        captured: list[list[str]] = []

        class Completed:
            returncode = 0
            stdout = '{"run_dir": "/tmp/monthly-run"}\n'
            stderr = ""

        def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
            captured.append(command)
            return Completed()

        previous = {
            name: os.environ.get(name)
            for name in (
                "RDHS_MONTHLY_BASELINE_COMMAND",
                "RDHS_MONTHLY_REPORT_COMMAND",
            )
        }
        os.environ["RDHS_MONTHLY_BASELINE_COMMAND"] = (
            "python3 report.py --mode monthly-baseline"
        )
        os.environ["RDHS_MONTHLY_REPORT_COMMAND"] = "python3 report.py --mode weekly"
        original_run = sync_module.subprocess.run
        sync_module.subprocess.run = fake_run
        try:
            generate_report("monthly", Path("/tmp/rdhs-output"), "2026-08-31")
        finally:
            sync_module.subprocess.run = original_run
            for name, value in previous.items():
                if value is None:
                    del os.environ[name]
                else:
                    os.environ[name] = value

        self.assertEqual(captured[0][:4], ["python3", "report.py", "--mode", "monthly-baseline"])
        self.assertEqual(captured[1][:4], ["python3", "report.py", "--mode", "weekly"])
        self.assertIn("2026-09-01", captured[0])
        self.assertIn("2026-08-31", captured[1])

    def test_cron_wrapper_uses_injected_environment_without_an_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "python-success"
            helper.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
            helper.chmod(0o755)
            environment = {
                **os.environ,
                "RDHS_SYNC_ENV": str(Path(directory) / "does-not-exist"),
                "RDHS_SITE_URL": "http://rdhs-report-web:3000",
                "RDHS_INGEST_TOKEN": "test-ingest-token",
                "RDHS_PYTHON_BIN": str(helper),
            }
            completed = subprocess.run(
                ["bash", "scripts/run-sync-job.sh", "monthly"],
                cwd=SITE_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_refresh_runner_uses_the_container_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = {**os.environ, "RDHS_OUTPUT_ROOT": directory}
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import runpy; module = runpy.run_path('scripts/local-refresh-runner.py'); "
                        "print(module['build_parser']().parse_args([]).output_root)"
                    ),
                ],
                cwd=SITE_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), directory)

    def test_monthly_sync_uses_the_container_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = {**os.environ, "RDHS_OUTPUT_ROOT": directory}
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import runpy; module = runpy.run_path('scripts/rdhs_snapshot_sync.py'); "
                        "print(module['build_parser']().parse_args([]).output_root)"
                    ),
                ],
                cwd=SITE_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), directory)


if __name__ == "__main__":
    unittest.main()
