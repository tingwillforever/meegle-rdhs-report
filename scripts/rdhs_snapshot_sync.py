"""Build and upload the stable snapshot contract consumed by the RDHS Site."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable
from typing import Mapping
from typing import Optional
from urllib.error import HTTPError
from urllib.request import Request
from urllib.request import build_opener


SITE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SITE_ROOT.parent
DEFAULT_OUTPUT_ROOT = SITE_ROOT / "runtime" / "sync-runs"

RDHS_FIELD = "RDHS(100')"
COMPONENT_FIELDS = {
    "linkClosure": "链路闭环得分(25')",
    "deliveryClosure": "交付闭环得分(15')",
    "timeliness": "时效节奏合理性(20')",
    "granularity": "颗粒度对齐度(20')",
    "quality": "质量敏锐度(20')",
}


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
    if cadence not in {"weekly", "monthly"}:
        raise ValueError("cadence must be weekly or monthly")
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
                "product": product_name,
                "productStatus": "研发中",
                "rdhs": rdhs,
                "governanceBand": _band_for_rdhs(rdhs),
                "priority": _priority_for_rdhs(rdhs),
                "components": {
                    key_name: _number_or_none(metric_row.get(source_name))
                    for key_name, source_name in COMPONENT_FIELDS.items()
                },
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
                "product": product_name,
                "productStatus": "研发中",
                "rdhs": None,
                "governanceBand": "重点治理",
                "priority": "P0",
                "components": {key_name: None for key_name in COMPONENT_FIELDS},
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

    governed_total = (
        int(total_row["key_governance_count"])
        + int(total_row["risk_improvement_count"])
        + int(total_row["continuous_optimization_count"])
    )
    governed_rate = governed_total / product_total if product_total else 0
    conclusion = (
        f"本期消费者BG共覆盖{product_total}个研发中产品，其中{governed_total}个产品"
        f"RDHS低于70分或未度量，占比约{governed_rate:.0%}，整体仍处于"
        f"{total_row['mode']}阶段。"
    )

    return {
        "schemaVersion": 1,
        "cadence": cadence,
        "periodKey": as_of[:7] if cadence == "monthly" else as_of,
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


def generate_report(cadence: str, output_root: Path, as_of: Optional[str]) -> Path:
    period_command = "last-week" if cadence == "weekly" else "last-month"
    command = [
        sys.executable,
        str(WORKSPACE_ROOT / "run_periodic_report.py"),
        period_command,
        "--no-publish",
        "--output-root",
        str(output_root),
    ]
    if as_of:
        command.extend(["--as-of", as_of])
    environment = dict(os.environ)
    environment["PATH"] = f"{Path.home() / '.local' / 'bin'}:{environment.get('PATH', '')}"
    completed = subprocess.run(
        command,
        cwd=WORKSPACE_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步 RDHS 周/月快照到运营报告站点")
    parser.add_argument("--cadence", choices=("weekly", "monthly"), required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--site-url", default=os.environ.get("RDHS_SITE_URL", ""))
    parser.add_argument("--token", default=os.environ.get("RDHS_INGEST_TOKEN", ""))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    source_dir = args.source_dir or generate_report(args.cadence, args.output_root, args.as_of)
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
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
