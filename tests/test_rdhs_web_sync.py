from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import json
import os
from pathlib import Path
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
VENDORED_REPORT_ROOT = (
    SITE_ROOT / "vendor" / "rdhs-workspace" / "topics" / "rdhs-operations"
)
sys.path.insert(0, str(VENDORED_REPORT_ROOT))

from impl.periodic_report_runtime import run_periodic_report  # noqa: E402


REPORT_QUOTAS = (
    "RDHS(100')",
    "链路闭环得分(25')",
    "交付闭环得分(15')",
    "时效节奏合理性(20')",
    "颗粒度对齐度(20')",
    "质量敏锐度(20')",
    "有效参与人数",
    "人均需求吞吐量",
    "人均缺陷关闭量",
    "需求交付周期",
    "需求开发周期",
    "严重缺陷占比",
    "低级缺陷占比",
    "应发布需求数",
    "有效发布需求数",
    "需求总量",
    "积压需求占比",
)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _chart_payload(rows: list[tuple[str, str, float]]) -> dict[str, object]:
    chart_rows = []
    for business_line, product, rdhs in rows:
        values = [
            rdhs,
            min(rdhs, 25),
            min(rdhs, 15),
            min(rdhs, 20),
            min(rdhs, 20),
            min(rdhs, 20),
            1,
            1,
            1,
            10,
            10,
            0,
            0,
            1,
            1,
            1,
            0,
        ]
        chart_rows.append(
            {
                "dim": {"0": business_line, "1": product},
                "value": {str(index): value for index, value in enumerate(values)},
            }
        )
    return {
        "data": {
            "name": "RDHS test chart",
            "dim_titles": ["一级业务线", "产品"],
            "quota_titles": list(REPORT_QUOTAS),
            "chart_data_list": chart_rows,
        }
    }


def _product_master(
    identifier: int,
    business_id: str,
    product: str,
    *,
    status: str = "In Progress",
    attribute_label: str = "",
    attribute_value: str = "",
) -> dict[str, object]:
    fields: list[dict[str, object]] = [
        {
            "field_alias": "business",
            "field_key": "business",
            "field_value": business_id,
        }
    ]
    if attribute_label or attribute_value:
        fields.append(
            {
                "field_alias": "",
                "field_key": "field_22acd7",
                "field_value": {
                    "label": attribute_label,
                    "value": attribute_value,
                },
            }
        )
    return {
        "id": identifier,
        "name": product,
        "fields": fields,
        "work_item_status": {"state_key": status},
    }


def _run_vendored_contract_fixture(output_root: Path) -> tuple[dict[str, object], dict[str, object]]:
    current = _chart_payload(
        [
            ("主营业务线", "低分产品", 40),
            ("主营业务线", "积压产品", 65),
            ("主营业务线", "常规产品", 80),
            ("主营业务线", "交付定制产品", 30),
            ("主营业务线", "已结束产品", 30),
            ("主营业务线", "孤儿产品", 30),
            ("测试业务线", "测试产品", 30),
        ]
    )
    backlog_row = next(
        row for row in current["data"]["chart_data_list"]
        if row["dim"]["1"] == "积压产品"
    )
    backlog_row["value"]["16"] = 0.8
    masters = {
        "data": [
            _product_master(1, "main", "低分产品"),
            _product_master(7, "main", "积压产品"),
            _product_master(
                2,
                "main",
                "常规产品",
                attribute_label="标准产品",
                attribute_value="standard",
            ),
            _product_master(3, "main", "未度量产品"),
            _product_master(
                4,
                "main",
                "交付定制产品",
                attribute_label="交付定制",
                attribute_value="hmeckpgbh",
            ),
            _product_master(5, "main", "已结束产品", status="Finished"),
            _product_master(6, "test", "测试产品"),
        ]
    }
    business_lines = {
        "data": [
            {"id": "main", "name": "主营业务线"},
            {"id": "test", "name": "测试业务线"},
        ]
    }
    result = run_periodic_report(
        mode="weekly",
        as_of=date(2026, 8, 24),
        output_root=output_root,
        project_key="test-project",
        current_chart_id="current-chart",
        previous_chart_id="previous-chart",
        current_payload=current,
        previous_payload=current,
        product_master_payload=masters,
        business_lines_payload=business_lines,
        publish=False,
    )
    return _load_json(result.report_data_path), _load_json(result.audit_manifest_path)


class VendoredReportContractTests(unittest.TestCase):
    def test_research_product_master_is_the_report_coverage_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, _manifest = _run_vendored_contract_fixture(Path(directory))

        headers = report["full_product_headers"]
        measured = [dict(zip(headers, row, strict=True)) for row in report["full_product_rows"]]
        improvement_headers = report["full_improvement_headers"]
        improvements = [
            dict(zip(improvement_headers, row, strict=True))
            for row in report["full_improvement_rows"]
        ]

        self.assertEqual(
            {(row["业务线"], row["产品"]) for row in measured},
            {
                ("主营业务线", "低分产品"),
                ("主营业务线", "积压产品"),
                ("主营业务线", "常规产品"),
            },
        )
        unmeasured = next(row for row in improvements if row["产品"] == "未度量产品")
        self.assertEqual(unmeasured["RDHS"], "—")

    def test_non_research_products_are_excluded_with_reconciling_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, manifest = _run_vendored_contract_fixture(Path(directory))

        audit = report["audit"]
        self.assertEqual(audit["clean_research_product_total"], 4)
        self.assertEqual(audit["measured_research_product_total"], 3)
        self.assertEqual(audit["unmeasured_or_pending_total"], 1)
        self.assertEqual(audit["excluded_business_line_master_total"], 1)
        self.assertEqual(audit["excluded_business_line_chart_record_total"], 1)
        self.assertEqual(audit["excluded_product_attribute_master_total"], 1)
        self.assertEqual(audit["excluded_product_attribute_chart_record_total"], 1)
        self.assertEqual(audit["excluded_finished"], 1)
        self.assertEqual(audit["chart_orphan_record_total"], 1)
        self.assertEqual(audit["priority_counts"], {"P0": 1, "P1": 0, "P2": 2})
        self.assertEqual(manifest["report"], audit)

    def test_overview_includes_regular_tracking_and_reconciled_bg_total(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, _manifest = _run_vendored_contract_fixture(Path(directory))

        rows = {row["business_line"]: row for row in report["overview_rows"]}
        detail = rows["主营业务线"]
        total = rows["消费者BG（合计）"]

        self.assertEqual(detail["product_total"], 4)
        self.assertEqual(detail["key_governance_count"], 2)
        self.assertEqual(detail["continuous_optimization_count"], 1)
        self.assertEqual(detail["regular_tracking_count"], 1)
        self.assertEqual(total["product_total"], 4)
        self.assertEqual(total["regular_tracking_count"], 1)
        self.assertEqual(
            detail["key_governance_count"]
            + detail["risk_improvement_count"]
            + detail["continuous_optimization_count"]
            + detail["regular_tracking_count"],
            detail["product_total"],
        )


class SnapshotSyncTests(unittest.TestCase):
    def test_default_report_command_points_to_the_vendored_runtime(self) -> None:
        variable = "RDHS_CURRENT_REPORT_COMMAND"
        previous = os.environ.pop(variable, None)
        try:
            command = sync_module._report_command(variable)
        finally:
            if previous is not None:
                os.environ[variable] = previous

        self.assertTrue(
            Path(command[1]).is_file(),
            f"default report entrypoint does not exist: {command[1]}",
        )

    def test_local_d1_refresh_does_not_require_mysql_sync_state(self) -> None:
        @contextmanager
        def reject_remote_lease(*args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("local D1 refresh must not acquire a MySQL lease")
            yield

        def local_report(*args, **kwargs):  # noqa: ANN002, ANN003
            if kwargs.get("site_url") or kwargs.get("token"):
                raise AssertionError("local D1 refresh must keep baselines on local storage")
            return REPORT_DIR

        def accept_upload(*args, **kwargs):  # noqa: ANN002, ANN003
            return {"stored": True}

        original_lease = sync_module.remote_sync_lease
        original_generate = sync_module.generate_report
        original_upload = sync_module.upload_snapshot
        previous_storage = os.environ.pop("RDHS_STORAGE", None)
        sync_module.remote_sync_lease = reject_remote_lease
        sync_module.generate_report = local_report
        sync_module.upload_snapshot = accept_upload
        try:
            with tempfile.TemporaryDirectory() as directory:
                result = sync_module.main([
                    "--current-month-cache",
                    "--as-of",
                    "2026-08-24",
                    "--output-root",
                    directory,
                    "--site-url",
                    "http://localhost:3000",
                    "--token",
                    "test-token",
                ])
            self.assertEqual(result, 0)
        finally:
            sync_module.remote_sync_lease = original_lease
            sync_module.generate_report = original_generate
            sync_module.upload_snapshot = original_upload
            if previous_storage is not None:
                os.environ["RDHS_STORAGE"] = previous_storage

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
