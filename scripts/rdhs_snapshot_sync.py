"""Build and upload the stable snapshot contract consumed by the RDHS Site."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date
from datetime import datetime
from datetime import timedelta
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Callable
from typing import Mapping
from typing import Optional
from urllib.error import HTTPError
from urllib.request import Request
from urllib.request import build_opener
from zoneinfo import ZoneInfo


SITE_ROOT = Path(__file__).resolve().parents[1]
SHANGHAI_TIME_ZONE = ZoneInfo("Asia/Shanghai")
MONTH_KEY_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
SITE_SNAPSHOT_PATTERN = re.compile(r"^monthly-(\d{4}-\d{2})\.json$")


def _resolve_workspace_root() -> Path:
    configured = os.environ.get("RDHS_WORKSPACE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    for candidate in (SITE_ROOT, SITE_ROOT.parent):
        if (candidate / "run_periodic_report.py").exists():
            return candidate
    return SITE_ROOT


WORKSPACE_ROOT = _resolve_workspace_root()
DEFAULT_OUTPUT_ROOT = Path(
    os.environ.get("RDHS_OUTPUT_ROOT", str(SITE_ROOT / "runtime" / "sync-runs"))
)

RDHS_FIELD = "RDHS(100')"
COMPONENT_FIELDS = {
    "linkClosure": "链路闭环得分(25')",
    "deliveryClosure": "交付闭环得分(15')",
    "timeliness": "时效节奏合理性(20')",
    "granularity": "颗粒度对齐度(20')",
    "quality": "质量敏锐度(20')",
}
SUB_LINE_FIELDS = ("二级业务线", "二级业务线名称", "业务线二级", "产品二级业务线")


def _as_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _as_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _number_or_none(value: object) -> Optional[float]:
    if value is None or str(value).strip() in {"", "—", "-"}:
        return None
    return float(value)


def _optional_text(row: Mapping[str, object], fields: tuple[str, ...]) -> Optional[str]:
    for field in fields:
        value = row.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in {"—", "-"}:
            return text
    return None


def _tone_by_lower_bound(value: Optional[float], critical: float, risk: float) -> str:
    if value is None or value < critical:
        return "critical"
    if value < risk:
        return "risk"
    return "track"


def _tone_by_upper_bound(
    value: Optional[float],
    *,
    risk_above: float,
    critical_above: Optional[float] = None,
    neutral_when_ok: bool = False,
) -> str:
    if value is None:
        return "critical"
    if critical_above is not None and value > critical_above:
        return "critical"
    if value > risk_above:
        return "risk"
    return "neutral" if neutral_when_ok else "track"


def _release_closure_rate(row: Mapping[str, object]) -> Optional[float]:
    expected = _number_or_none(row.get("应发布需求数"))
    actual = _number_or_none(row.get("有效发布需求数"))
    if expected is None or actual is None or expected <= 0:
        return None
    return actual / expected


def _dependency_metrics(row: Mapping[str, object]) -> list[dict[str, object]]:
    demand_throughput = _number_or_none(row.get("人均需求吞吐量"))
    defect_closure = _number_or_none(row.get("人均缺陷关闭量"))
    delivery_cycle = _number_or_none(row.get("需求交付周期"))
    development_cycle = _number_or_none(row.get("需求开发周期"))
    release_closure = _release_closure_rate(row)
    severe_defect_rate = _number_or_none(row.get("严重缺陷占比"))
    low_level_defect_rate = _number_or_none(row.get("低级缺陷占比"))
    backlog_rate = _number_or_none(row.get("积压需求占比"))

    defect_tone = "risk" if (demand_throughput is not None and demand_throughput < 0.2 and (defect_closure or 0) > 0) else "neutral"
    return [
        {
            "label": "月人均需求吞吐量",
            "value": demand_throughput,
            "unit": "个/人",
            "tone": _tone_by_lower_bound(demand_throughput, 0.2, 0.5),
        },
        {
            "label": "月人均缺陷关闭量",
            "value": defect_closure,
            "unit": "个/人",
            "tone": defect_tone,
        },
        {
            "label": "需求开发周期",
            "value": development_cycle,
            "unit": "天",
            "tone": _tone_by_upper_bound(development_cycle, risk_above=30, critical_above=60),
        },
        {
            "label": "需求交付周期",
            "value": delivery_cycle,
            "unit": "天",
            "tone": _tone_by_upper_bound(delivery_cycle, risk_above=45, critical_above=90),
        },
        {
            "label": "需求发布闭环率",
            "value": release_closure,
            "unit": "%",
            "tone": _tone_by_lower_bound(release_closure, 0.6, 0.8),
        },
        {
            "label": "严重缺陷占比",
            "value": severe_defect_rate,
            "unit": "%",
            "tone": _tone_by_upper_bound(severe_defect_rate, risk_above=0.08, critical_above=0.15),
        },
        {
            "label": "低级缺陷占比",
            "value": low_level_defect_rate,
            "unit": "%",
            "tone": _tone_by_upper_bound(low_level_defect_rate, risk_above=0.10, neutral_when_ok=True),
        },
        {
            "label": "需求积压占比",
            "value": backlog_rate,
            "unit": "%",
            "tone": _tone_by_upper_bound(backlog_rate, risk_above=0.15, critical_above=0.30),
        },
    ]


def _band_for_rdhs(rdhs: Optional[float]) -> str:
    if rdhs is None or rdhs < 45:
        return "重点治理"
    if rdhs < 60:
        return "风险改进"
    if rdhs < 70:
        return "持续优化"
    return "常规跟踪"


def _priority_for_rdhs(rdhs: Optional[float]) -> Optional[str]:
    if rdhs is None or rdhs < 45:
        return "P0"
    if rdhs < 60:
        return "P1"
    if rdhs < 70:
        return "P2"
    return None


def _rows_as_dicts(headers: object, rows: object, label: str) -> list[dict[str, object]]:
    header_list = [str(value) for value in _as_list(headers, f"{label}.headers")]
    result: list[dict[str, object]] = []
    for index, row in enumerate(_as_list(rows, f"{label}.rows")):
        row_values = _as_list(row, f"{label}.rows[{index}]")
        if len(row_values) != len(header_list):
            raise ValueError(
                f"{label}.rows[{index}] has {len(row_values)} cells, expected {len(header_list)}"
            )
        result.append(dict(zip(header_list, row_values)))
    return result


def _lowest_component(metric_row: Mapping[str, object]) -> str:
    scored = [
        (field, _number_or_none(metric_row.get(field)))
        for field in COMPONENT_FIELDS.values()
    ]
    valid = [(field, value) for field, value in scored if value is not None]
    if not valid:
        return "未形成有效 RDHS 度量"
    lowest = min(value for _, value in valid)
    return " / ".join(field.split("(", 1)[0] for field, value in valid if value == lowest)


def build_snapshot(
    report_data: dict[str, object],
    audit_manifest: dict[str, object],
    *,
    cadence: str,
) -> dict[str, object]:
    """Convert a verified periodic report into the Site's schema-v1 contract."""
    if cadence != "monthly":
        raise ValueError("cadence must be monthly")
    as_of = str(audit_manifest.get("as_of") or "")
    if len(as_of) != 10:
        raise ValueError("audit manifest is missing a valid as_of date")

    report_audit = _as_mapping(report_data.get("audit"), "report_data.audit")
    validation = _as_mapping(audit_manifest.get("data_validation"), "data_validation")
    current_validation = _as_mapping(validation.get("current"), "data_validation.current")

    overview_rows = _as_list(report_data.get("overview_rows"), "overview_rows")
    line_rows: list[dict[str, object]] = []
    total_row: Optional[dict[str, object]] = None
    for index, raw_row in enumerate(overview_rows):
        row = _as_mapping(raw_row, f"overview_rows[{index}]")
        if str(row.get("business_line")) == "消费者BG（合计）":
            total_row = row
            continue
        line_rows.append(row)
    if total_row is None:
        raise ValueError("overview_rows is missing 消费者BG（合计）")

    measured_rows = _rows_as_dicts(
        report_data.get("full_product_headers"),
        report_data.get("full_product_rows"),
        "full_product",
    )
    improvement_rows = _rows_as_dicts(
        report_data.get("full_improvement_headers"),
        report_data.get("full_improvement_rows"),
        "full_improvement",
    )
    improvement_by_key = {
        (str(row["业务线"]), str(row["产品"])): row for row in improvement_rows
    }

    products: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str]] = set()
    for metric_row in measured_rows:
        business_line = str(metric_row["业务线"]).strip()
        product_name = str(metric_row["产品"]).strip()
        if business_line == "测试业务线":
            continue
        key = (business_line, product_name)
        improvement = improvement_by_key.get(key)
        rdhs = _number_or_none(metric_row.get(RDHS_FIELD))
        products.append(
            {
                "businessLine": business_line,
                "subLine": _optional_text(metric_row, SUB_LINE_FIELDS),
                "product": product_name,
                "productStatus": "研发中",
                "rdhs": rdhs,
                "governanceBand": _band_for_rdhs(rdhs),
                "priority": _priority_for_rdhs(rdhs),
                "components": {
                    key_name: _number_or_none(metric_row.get(source_name))
                    for key_name, source_name in COMPONENT_FIELDS.items()
                },
                "dependencyMetrics": _dependency_metrics(metric_row),
                "lowestComponent": str(
                    improvement.get("最低分分项") if improvement else _lowest_component(metric_row)
                ),
                "problem": str(
                    improvement.get("主要问题")
                    if improvement
                    else "RDHS 已达到常规跟踪区间，继续观察过程指标稳定性。"
                ),
                "action": str(
                    improvement.get("建议本期动作")
                    if improvement
                    else "保持当前过程记录完整度，按月复核积压、节奏、质量与发布闭环。"
                ),
            }
        )
        seen_keys.add(key)

    for improvement in improvement_rows:
        business_line = str(improvement["业务线"]).strip()
        product_name = str(improvement["产品"]).strip()
        key = (business_line, product_name)
        if key in seen_keys or business_line == "测试业务线":
            continue
        rdhs = _number_or_none(improvement.get("RDHS"))
        if rdhs is not None:
            raise ValueError(
                f"measured product is missing from full_product_rows: {business_line} / {product_name}"
            )
        products.append(
            {
                "businessLine": business_line,
                "subLine": _optional_text(improvement, SUB_LINE_FIELDS),
                "product": product_name,
                "productStatus": "研发中",
                "rdhs": None,
                "governanceBand": "重点治理",
                "priority": "P0",
                "components": {key_name: None for key_name in COMPONENT_FIELDS},
                "dependencyMetrics": [],
                "lowestComponent": str(improvement["最低分分项"]),
                "problem": str(improvement["主要问题"]),
                "action": str(improvement["建议本期动作"]),
            }
        )
        seen_keys.add(key)

    products.sort(key=lambda row: (str(row["businessLine"]), str(row["product"])))
    product_total = int(report_audit["clean_research_product_total"])
    measured_total = int(report_audit["measured_research_product_total"])
    unmeasured_total = int(report_audit["unmeasured_or_pending_total"])
    if len(products) != product_total:
        raise ValueError(f"product contract has {len(products)} rows, expected {product_total}")
    if measured_total + unmeasured_total != product_total:
        raise ValueError("measured and unmeasured product totals do not reconcile")

    business_lines = [
        {
            "businessLine": str(row["business_line"]),
            "productTotal": int(row["product_total"]),
            "keyGovernanceCount": int(row["key_governance_count"]),
            "riskImprovementCount": int(row["risk_improvement_count"]),
            "continuousOptimizationCount": int(row["continuous_optimization_count"]),
            "regularTrackingCount": int(row["regular_tracking_count"]),
            "mode": str(row["mode"]),
            "focus": str(row["focus"]),
        }
        for row in line_rows
    ]
    if sum(row["productTotal"] for row in business_lines) != product_total:
        raise ValueError("business line product totals do not reconcile with product master")

    conclusion = (
        f"本期 CBG 共覆盖{product_total}个研发中产品，整体仍处于"
        f"{total_row['mode']}阶段。"
    )

    return {
        "schemaVersion": 1,
        "cadence": cadence,
        "periodKey": as_of[:7],
        "asOf": as_of,
        "fetchedAt": str(current_validation["fetched_at"]),
        "source": {
            "chartId": str(current_validation["chart_id"]),
            "chartName": str(current_validation["chart_name"]),
            "sha256": str(current_validation["source_sha256"]),
        },
        "audit": {
            "rawRowCount": int(current_validation["raw_row_count"]),
            "acceptedRowCount": int(current_validation["accepted_row_count"]),
            "zeroScoreRowCount": int(current_validation["zero_rdhs_row_count"]),
            "emptyDimensionRowCount": int(current_validation["empty_dimension_row_count"]),
            "researchProductCount": product_total,
            "measuredProductCount": measured_total,
            "unmeasuredProductCount": unmeasured_total,
            "excludedTestBusinessLineCount": int(
                report_audit["excluded_business_line_master_total"]
            ),
            "excludedProductAttributeCount": int(
                report_audit.get("excluded_product_attribute_master_total", 0)
            ),
            "status": "validated",
            "warning": None,
        },
        "overview": {
            "conclusion": conclusion,
            "focus": str(total_row["focus"]),
        },
        "businessLines": business_lines,
        "products": products,
    }


def upload_snapshot(
    site_url: str,
    token: str,
    snapshot: dict[str, object],
    *,
    opener: object = None,
) -> dict[str, object]:
    if not site_url.startswith("https://") and not site_url.startswith("http://localhost"):
        raise ValueError("site URL must use HTTPS or localhost")
    if not token:
        raise ValueError("RDHS ingest token is required")
    payload = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{site_url.rstrip('/')}/api/snapshots",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    active_opener = opener or build_opener()
    try:
        response = active_opener.open(request, timeout=30)
        with response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        try:
            detail = error.read().decode("utf-8")
        except (AttributeError, KeyError, OSError):
            detail = ""
        raise RuntimeError(f"snapshot upload failed with HTTP {error.code}: {detail}") from error
    result = json.loads(body)
    if not isinstance(result, dict):
        raise RuntimeError("snapshot upload returned a non-object response")
    return result


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file is not an object: {path}")
    return payload


def _report_command(command_variable: str) -> list[str]:
    if command_variable in os.environ:
        configured = os.environ[command_variable].strip()
        if not configured:
            raise ValueError(f"{command_variable} must not be empty")
        command = shlex.split(configured)
        if not command:
            raise ValueError(f"{command_variable} must not be empty")
        return command
    return [
        sys.executable,
        str(WORKSPACE_ROOT / "run_periodic_report.py"),
        "--mode",
        "weekly",
    ]


def _run_report_command(
    command: list[str],
    *,
    output_root: Path,
    snapshot_date: str,
) -> Path:
    timeout_seconds = _report_command_timeout_seconds()
    try:
        completed = subprocess.run(
            [
                *command,
                "--no-publish",
                "--output-root",
                str(output_root),
                "--as-of",
                snapshot_date,
            ],
            cwd=WORKSPACE_ROOT,
            env={
                **os.environ,
                "PATH": f"{Path.home() / '.local' / 'bin'}:{os.environ.get('PATH', '')}",
            },
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"RDHS report generation exceeded {timeout_seconds} seconds"
        ) from error
    if completed.returncode != 0:
        raise RuntimeError(f"RDHS report generation failed: {completed.stderr.strip()}")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("RDHS report generation returned no result")
    result = json.loads(lines[-1])
    run_dir = Path(str(result["run_dir"]))
    if not run_dir.is_absolute():
        run_dir = WORKSPACE_ROOT / run_dir
    return run_dir


def _report_command_timeout_seconds() -> int:
    raw_value = os.environ.get("RDHS_REPORT_COMMAND_TIMEOUT_SECONDS", "540")
    try:
        timeout_seconds = int(raw_value)
    except ValueError as error:
        raise ValueError("RDHS_REPORT_COMMAND_TIMEOUT_SECONDS must be a positive integer") from error
    if timeout_seconds < 1:
        raise ValueError("RDHS_REPORT_COMMAND_TIMEOUT_SECONDS must be a positive integer")
    return timeout_seconds


def _next_month_start(report_date: date) -> date:
    if report_date.month == 12:
        return date(report_date.year + 1, 1, 1)
    return date(report_date.year, report_date.month + 1, 1)


def _month_start_from_key(month_key: str) -> date | None:
    match = MONTH_KEY_PATTERN.fullmatch(month_key)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), 1)
    except ValueError:
        return None


def _earliest_retained_month(current_date: date, retention_months: int) -> date:
    if retention_months < 1:
        raise ValueError("retention_months must be at least 1")
    month_index = current_date.year * 12 + current_date.month - retention_months
    return date(month_index // 12, month_index % 12 + 1, 1)


def prune_report_output(
    output_root: Path,
    *,
    current_date: date,
    retention_months: int,
) -> None:
    """Remove only dated, expired report output while preserving unrelated files."""
    if not output_root.exists():
        return
    earliest_month = _earliest_retained_month(current_date, retention_months)
    for path in output_root.iterdir():
        month_start = _month_start_from_key(path.name)
        if (
            month_start is not None
            and month_start < earliest_month
            and path.is_dir()
            and not path.is_symlink()
        ):
            shutil.rmtree(path)

    snapshot_dir = output_root / "site-snapshots"
    if not snapshot_dir.is_dir() or snapshot_dir.is_symlink():
        return
    for path in snapshot_dir.iterdir():
        match = SITE_SNAPSHOT_PATTERN.fullmatch(path.name)
        month_start = _month_start_from_key(match.group(1)) if match else None
        if month_start is not None and month_start < earliest_month and path.is_file():
            path.unlink()


def _output_retention_months() -> int:
    raw_value = os.environ.get("RDHS_OUTPUT_RETENTION_MONTHS", "6")
    try:
        retention_months = int(raw_value)
    except ValueError as error:
        raise ValueError("RDHS_OUTPUT_RETENTION_MONTHS must be a positive integer") from error
    if retention_months < 1:
        raise ValueError("RDHS_OUTPUT_RETENTION_MONTHS must be a positive integer")
    return retention_months


@contextmanager
def _report_output_lock(output_root: Path):
    """Serialize CronJob and Runner access to the shared report output."""
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / ".rdhs-sync.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def generate_report(
    cadence: str,
    output_root: Path,
    as_of: Optional[str],
    *,
    current_month_cache: bool = False,
) -> Path:
    if cadence != "monthly":
        raise ValueError("cadence must be monthly")
    snapshot_date = as_of
    if not snapshot_date:
        today = datetime.now(SHANGHAI_TIME_ZONE).date()
        snapshot_date = (
            today.isoformat()
            if current_month_cache
            else (today.replace(day=1) - timedelta(days=1)).isoformat()
        )

    with _report_output_lock(output_root):
        if not current_month_cache and "RDHS_MONTHLY_BASELINE_COMMAND" in os.environ:
            report_date = date.fromisoformat(snapshot_date)
            _run_report_command(
                _report_command("RDHS_MONTHLY_BASELINE_COMMAND"),
                output_root=output_root,
                snapshot_date=_next_month_start(report_date).isoformat(),
            )

        command_variable = (
            "RDHS_CURRENT_REPORT_COMMAND" if current_month_cache else "RDHS_MONTHLY_REPORT_COMMAND"
        )
        return _run_report_command(
            _report_command(command_variable),
            output_root=output_root,
            snapshot_date=snapshot_date,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步 RDHS 月度快照到运营报告站点")
    parser.add_argument("--cadence", choices=("monthly",), default="monthly")
    parser.add_argument("--as-of")
    parser.add_argument(
        "--current-month-cache",
        action="store_true",
        help="刷新当月缓存；默认用于每月 1 日固化上一个完整月快照",
    )
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--site-url", default=os.environ.get("RDHS_SITE_URL", ""))
    parser.add_argument("--token", default=os.environ.get("RDHS_INGEST_TOKEN", ""))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    source_dir = args.source_dir or generate_report(
        args.cadence,
        args.output_root,
        args.as_of,
        current_month_cache=args.current_month_cache,
    )
    snapshot = build_snapshot(
        _load_json(source_dir / "report_data.json"),
        _load_json(source_dir / "audit_manifest.json"),
        cadence=args.cadence,
    )
    snapshot_dir = args.output_root / "site-snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"{snapshot['cadence']}-{snapshot['periodKey']}.json"
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.dry_run:
        result = {"snapshot_path": str(snapshot_path), "uploaded": False}
    else:
        result = {
            "snapshot_path": str(snapshot_path),
            "uploaded": True,
            "remote": upload_snapshot(args.site_url, args.token, snapshot),
        }
        with _report_output_lock(args.output_root):
            prune_report_output(
                args.output_root,
                current_date=datetime.now(SHANGHAI_TIME_ZONE).date(),
                retention_months=_output_retention_months(),
            )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
