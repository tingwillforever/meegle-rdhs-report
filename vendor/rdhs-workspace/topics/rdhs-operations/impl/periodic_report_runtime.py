"""周期 RDHS 报告的取数、快照与本地运行编排。"""

from __future__ import annotations

import csv
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import replace
from datetime import date
from datetime import datetime
from io import StringIO
import json
from math import isclose
from pathlib import Path
import re
import subprocess
from typing import Callable
from zoneinfo import ZoneInfo

from impl.periodic_report_analysis import build_periodic_report_data
from impl.periodic_report_data import parse_chart_snapshot
from impl.periodic_report_models import ChartSnapshot
from impl.periodic_report_models import PeriodicReportData
from impl.periodic_report_renderer import render_periodic_report_xml
from impl.periodic_report_renderer import report_document_title
from impl.product_improvement_enrichment import build_full_improvement_rows
from impl.product_improvement_enrichment import load_team_mappings
from impl.product_improvement_enrichment import parse_business_line_names
from impl.product_improvement_enrichment import parse_product_master_records


CommandRunner = Callable[[list[str], str | None], str]
_OVERVIEW_HEADERS = [
    "业务线",
    "产品总数",
    "重点治理(<45')",
    "风险改进\n(45'~60')",
    "持续优化\n(60'~70')",
    "本期模式",
    "本期关注重点",
]
_IMPROVEMENT_HEADERS = [
    "业务线",
    "产品",
    "治理模式",
    "RDHS",
    "最低分分项",
    "主要问题",
    "建议本期动作",
]
_FULL_IMPROVEMENT_HEADERS = [
    "业务线",
    "产品",
    "产品状态",
    "超级团队数量",
    "治理模式",
    "RDHS",
    "最低分分项",
    "主要问题",
    "主问题标签",
    "建议本期动作",
]
_PRODUCT_MASTER_TYPE_KEY = "693f665435b354b7ca0085dc"
_PRODUCT_MASTER_PAGE_SIZE = 200
_DEFAULT_TEAM_MAPPING_PATH = Path(__file__).resolve().parent.parent / "config" / "initial_super_team_mappings.csv"


@dataclass(frozen=True)
class PeriodicReportRunResult:
    run_dir: Path
    report_data_path: Path
    audit_manifest_path: Path
    publication_url: str | None


@dataclass(frozen=True)
class PeriodicPublication:
    document_url: str
    spreadsheet_token: str
    summary_sheet_id: str
    improvement_sheet_id: str
    full_product_sheet_id: str
    full_product_spreadsheet_token: str


def _subprocess_runner(command: list[str], input_text: str | None = None) -> str:
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr.strip()}"
        )
    return completed.stdout


def fetch_chart_payload(
    *,
    project_key: str,
    chart_id: str,
    command_runner: CommandRunner = _subprocess_runner,
) -> dict[str, object]:
    """按 Meegle CLI 合同读取一次已知图表。"""
    output = command_runner(
        [
            "meegle",
            "chart",
            "get",
            "--project-key",
            project_key,
            "--chart-id",
            chart_id,
            "--format",
            "json",
        ],
        None,
    )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid Meegle chart response for chart {chart_id}") from exc
    if not isinstance(payload, dict) or payload.get("err_code", 0) not in (0, None):
        raise RuntimeError(f"Meegle chart read failed for chart {chart_id}: {payload!r}")
    return payload


def _fetch_meegle_payload(
    command: list[str],
    *,
    command_runner: CommandRunner,
) -> dict[str, object]:
    output = command_runner(command, None)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid Meegle response: {' '.join(command)}") from exc
    if not isinstance(payload, dict) or payload.get("err_code", 0) not in (0, None):
        raise RuntimeError(f"Meegle read failed: {' '.join(command)}: {payload!r}")
    return payload


def fetch_business_lines_payload(
    *,
    project_key: str,
    command_runner: CommandRunner = _subprocess_runner,
) -> dict[str, object]:
    return _fetch_meegle_payload(
        ["meegle", "space", "business-lines", "--project-key", project_key, "--format", "json"],
        command_runner=command_runner,
    )


def fetch_product_master_payload(
    *,
    project_key: str,
    command_runner: CommandRunner = _subprocess_runner,
) -> dict[str, object]:
    def fetch_page(page_num: int) -> dict[str, object]:
        return _fetch_meegle_payload(
            [
            "meegle",
            "workitem",
            "search-filter",
            "--project-key",
            project_key,
            "--work-item-type-keys",
            json.dumps([_PRODUCT_MASTER_TYPE_KEY]),
            "--page-num",
            str(page_num),
            "--page-size",
            str(_PRODUCT_MASTER_PAGE_SIZE),
            "--format",
            "json",
            ],
            command_runner=command_runner,
        )

    def page_data(payload: dict[str, object], page_num: int) -> list[object]:
        data = payload.get("data")
        if not isinstance(data, list):
            raise RuntimeError(f"product master page {page_num} has non-list data")
        return data

    def page_total(payload: dict[str, object], page_num: int) -> int:
        pagination = payload.get("pagination")
        total = pagination.get("total") if isinstance(pagination, dict) else None
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise RuntimeError(f"product master page {page_num} is missing a valid pagination total")
        return total

    first_page = fetch_page(1)
    total = page_total(first_page, 1)
    all_items = list(page_data(first_page, 1))
    if len(all_items) > total:
        raise RuntimeError("product master page 1 contains more rows than pagination total")
    page_count = (total + _PRODUCT_MASTER_PAGE_SIZE - 1) // _PRODUCT_MASTER_PAGE_SIZE
    for page_num in range(2, page_count + 1):
        page = fetch_page(page_num)
        if page_total(page, page_num) != total:
            raise RuntimeError("product master pagination total changed during fetch")
        all_items.extend(page_data(page, page_num))
    if len(all_items) != total:
        raise RuntimeError(
            f"product master pagination incomplete: expected {total} rows, got {len(all_items)}"
        )
    return {
        **first_page,
        "data": all_items,
        "pagination": {
            "page_num": 1,
            "page_size": _PRODUCT_MASTER_PAGE_SIZE,
            "total": total,
        },
    }


def _previous_month(period: str) -> str:
    year, month = (int(part) for part in period.split("-"))
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load stored baseline: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"stored baseline is not a JSON object: {path}")
    return payload


def _snapshot_time() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def _baseline_metadata_path(baseline_path: Path) -> Path:
    return baseline_path.with_suffix(".metadata.json")


def _stored_baseline_timestamp(baseline_path: Path) -> str:
    metadata_path = _baseline_metadata_path(baseline_path)
    if not metadata_path.exists():
        return "unknown"
    metadata = _load_json(metadata_path)
    fetched_at = metadata.get("fetched_at")
    return fetched_at if isinstance(fetched_at, str) and fetched_at else "unknown"


def _write_validation_failure_audit(
    *,
    run_dir: Path,
    mode: str,
    as_of: date,
    source: str,
    chart_id: str,
    fetched_at: str,
    raw_path: Path,
    error: ValueError,
) -> None:
    _write_json(
        run_dir / "audit_manifest.json",
        {
            "mode": mode,
            "as_of": as_of.isoformat(),
            "status": "validation_failed",
            "data_validation": {
                source: {
                    "status": "validation_failed",
                    "chart_id": chart_id,
                    "fetched_at": fetched_at,
                    "raw_path": str(raw_path),
                    "error": str(error),
                }
            },
            "publication": {"published": False},
        },
    )


def _persist_and_parse_chart_snapshot(
    *,
    raw_payload: dict[str, object],
    chart_id: str,
    fetched_at: str,
    raw_path: Path,
    run_dir: Path,
    mode: str,
    as_of: date,
    source: str,
) -> ChartSnapshot:
    _write_json(raw_path, raw_payload)
    try:
        return parse_chart_snapshot(
            raw_payload,
            chart_id=chart_id,
            fetched_at=fetched_at,
        )
    except ValueError as exc:
        _write_validation_failure_audit(
            run_dir=run_dir,
            mode=mode,
            as_of=as_of,
            source=source,
            chart_id=chart_id,
            fetched_at=fetched_at,
            raw_path=raw_path,
            error=exc,
        )
        raise


def _write_csvs(report: PeriodicReportData, run_dir: Path) -> None:
    with (run_dir / "rdhs_overview.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_OVERVIEW_HEADERS)
        for row in report.overview_rows:
            writer.writerow(
                [
                    row.business_line,
                    row.product_total,
                    row.key_governance_count,
                    row.risk_improvement_count,
                    row.continuous_optimization_count,
                    row.mode,
                    row.focus,
                ]
            )
    with (run_dir / "product_improvement_list.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(_IMPROVEMENT_HEADERS)
        for row in report.improvement_rows:
            writer.writerow(
                [
                    row.business_line,
                    row.product,
                    row.governance_mode,
                    row.rdhs,
                    row.lowest_component,
                    row.problem,
                    row.action,
                ]
            )
    with (run_dir / "full_product_snapshot.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(report.full_product_headers)
        writer.writerows(report.full_product_rows)
    with (run_dir / "full_product_improvement_list.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(report.full_improvement_headers)
        writer.writerows(report.full_improvement_rows)


def _report_as_dict(report: PeriodicReportData) -> dict[str, object]:
    return {
        "overview_rows": [asdict(row) for row in report.overview_rows],
        "improvement_rows": [asdict(row) for row in report.improvement_rows],
        "todo_items": list(report.todo_items),
        "audit": report.audit,
        "full_product_headers": list(report.full_product_headers),
        "full_product_rows": [list(row) for row in report.full_product_rows],
        "full_improvement_headers": list(report.full_improvement_headers),
        "full_improvement_rows": [list(row) for row in report.full_improvement_rows],
    }


def _column_name(index: int) -> str:
    """将 1-based 列号转换为 A1 列名。"""
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _command_json(
    command: list[str],
    *,
    command_runner: CommandRunner,
    input_text: str | None = None,
) -> dict[str, object]:
    output = command_runner(command, input_text)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON response: {' '.join(command)}") from exc
    if not isinstance(payload, dict) or payload.get("ok") is False:
        raise RuntimeError(f"command did not succeed: {' '.join(command)}: {payload!r}")
    return payload


def _data_mapping(payload: dict[str, object]) -> dict[str, object]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"command response has no data mapping: {payload!r}")
    return data


def _spreadsheet_token(payload: dict[str, object]) -> str:
    data = _data_mapping(payload)
    spreadsheet = data.get("spreadsheet")
    if isinstance(spreadsheet, dict):
        for key in ("spreadsheet_token", "token"):
            if isinstance(spreadsheet.get(key), str):
                return spreadsheet[key]
    for key in ("spreadsheet_token", "token"):
        if isinstance(data.get(key), str):
            return data[key]
    raise RuntimeError(f"workbook create response has no spreadsheet token: {payload!r}")


def _document_url(payload: dict[str, object]) -> str:
    document = _data_mapping(payload).get("document")
    if not isinstance(document, dict) or not isinstance(document.get("url"), str):
        raise RuntimeError(f"document create response has no document URL: {payload!r}")
    return document["url"]


def _workbook_payload(report: PeriodicReportData) -> dict[str, object]:
    return {
        "sheets": [
            {
                "name": "RDHS总览",
                "columns": _OVERVIEW_HEADERS,
                "dtypes": {
                    "产品总数": "int64",
                    "重点治理(<45')": "int64",
                    "风险改进\n(45'~60')": "int64",
                    "持续优化\n(60'~70')": "int64",
                },
                "data": [
                    [
                        row.business_line,
                        row.product_total,
                        row.key_governance_count,
                        row.risk_improvement_count,
                        row.continuous_optimization_count,
                        row.mode,
                        row.focus,
                    ]
                    for row in report.overview_rows
                ],
            },
            {
                "name": "产品改进清单",
                "columns": _IMPROVEMENT_HEADERS,
                "dtypes": {"RDHS": "float64"},
                "data": [
                    [
                        row.business_line,
                        row.product,
                        row.governance_mode,
                        row.rdhs,
                        row.lowest_component,
                        row.problem,
                        row.action,
                    ]
                    for row in report.improvement_rows
                ],
            },
            {
                "name": "全量产品改进清单",
                "columns": list(report.full_improvement_headers),
                "data": [list(row) for row in report.full_improvement_rows],
            },
        ]
    }


def _full_product_workbook_payload(report: PeriodicReportData) -> dict[str, object]:
    workbook = _workbook_payload(report)
    sheets = workbook["sheets"]
    assert isinstance(sheets, list)
    return {"sheets": [sheets[2]]}


def _expected_sheet_rows(report: PeriodicReportData) -> tuple[list[list[object]], ...]:
    workbook = _workbook_payload(report)
    sheets = workbook["sheets"]
    assert isinstance(sheets, list)
    expected: list[list[list[object]]] = []
    for sheet in sheets:
        assert isinstance(sheet, dict)
        columns = sheet["columns"]
        data = sheet["data"]
        assert isinstance(columns, list) and isinstance(data, list)
        expected.append([list(columns), *(list(row) for row in data)])
    return tuple(expected)


def _sheet_id_by_name(payload: dict[str, object], name: str) -> str:
    sheets = _data_mapping(payload).get("sheets")
    if not isinstance(sheets, list):
        raise RuntimeError(f"workbook info response has no sheets: {payload!r}")
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        if sheet.get("title", sheet.get("sheet_name")) == name and isinstance(sheet.get("sheet_id"), str):
            return sheet["sheet_id"]
    raise RuntimeError(f"workbook is missing sheet {name}: {payload!r}")


def _verify_sheet_readback(
    payload: dict[str, object],
    *,
    expected_end_row: int,
    expected_end_column: str,
    expected_rows: list[list[object]],
) -> None:
    data = _data_mapping(payload)
    actual_range = data.get("actual_range")
    if actual_range != f"A1:{expected_end_column}{expected_end_row}":
        raise RuntimeError(
            "sheet readback range mismatch: expected "
            f"A1:{expected_end_column}{expected_end_row}, got {actual_range!r}"
        )
    annotated_csv = data.get("annotated_csv")
    if not isinstance(annotated_csv, str):
        raise RuntimeError("sheet readback has no annotated CSV")
    cleaned_csv = re.sub(r"(?m)^\[row=\d+\]\s*", "", annotated_csv)
    actual_rows = list(csv.reader(StringIO(cleaned_csv)))
    if len(actual_rows) != len(expected_rows):
        raise RuntimeError(
            f"sheet readback row count mismatch: expected {len(expected_rows)}, got {len(actual_rows)}"
        )
    for row_index, (actual_row, expected_row) in enumerate(
        zip(actual_rows, expected_rows, strict=True),
        start=1,
    ):
        if len(actual_row) != len(expected_row):
            raise RuntimeError(
                f"sheet readback column count mismatch at row {row_index}: "
                f"expected {len(expected_row)}, got {len(actual_row)}"
            )
        for column_index, (actual, expected) in enumerate(
            zip(actual_row, expected_row, strict=True),
            start=1,
        ):
            if _sheet_cells_match(actual, expected):
                continue
            raise RuntimeError(
                f"sheet readback mismatch at row {row_index}, column {column_index}: "
                f"expected {expected!r}, got {actual!r}"
            )


def _sheet_cells_match(actual: str, expected: object) -> bool:
    expected_text = str(expected)
    if actual == expected_text:
        return True
    try:
        return isclose(float(actual), float(expected_text), rel_tol=0.0, abs_tol=1e-9)
    except ValueError:
        return False


def _rows_as_csv(rows: list[list[object]]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerows(rows)
    return stream.getvalue()


def _embedded_sheet_refs(content: str) -> tuple[tuple[str, str], tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for attributes in re.findall(r"<sheet\b([^>]*)></sheet>", content):
        sheet_id = re.search(r'\bsheet-id="([^"]+)"', attributes)
        token = re.search(r'\btoken="([^"]+)"', attributes)
        if sheet_id and token:
            refs.append((token.group(1), sheet_id.group(1)))
    if len(refs) != 2:
        raise RuntimeError(f"document readback has {len(refs)} embedded sheets, expected 2")
    return refs[0], refs[1]


def publish_periodic_report(
    *,
    report: PeriodicReportData,
    period: str,
    snapshot_label: str,
    command_runner: CommandRunner = _subprocess_runner,
    publication_state: dict[str, object] | None = None,
) -> PeriodicPublication:
    """创建本期独立工作簿和报告，并在成功返回前执行回读校验。"""
    summary_expected_rows, improvement_expected_rows, full_expected_rows = _expected_sheet_rows(report)
    publication_state = publication_state if publication_state is not None else {}
    publication_state["status"] = "in_progress"
    full_workbook = _command_json(
        [
            "lark-cli",
            "sheets",
            "+workbook-create",
            "--title",
            f"全量产品改进清单-{period.replace('-', '')}",
            "--sheets",
            "-",
            "--as",
            "user",
            "--format",
            "json",
        ],
        command_runner=command_runner,
        input_text=json.dumps(_full_product_workbook_payload(report), ensure_ascii=False),
    )
    full_product_spreadsheet_token = _spreadsheet_token(full_workbook)
    publication_state["full_product_spreadsheet_token"] = full_product_spreadsheet_token
    full_workbook_info = _command_json(
        [
            "lark-cli",
            "sheets",
            "+workbook-info",
            "--spreadsheet-token",
            full_product_spreadsheet_token,
            "--as",
            "user",
            "--format",
            "json",
        ],
        command_runner=command_runner,
    )
    full_product_sheet_id = _sheet_id_by_name(full_workbook_info, "全量产品改进清单")
    publication_state["full_product_sheet_id"] = full_product_sheet_id
    full_source_readback = _command_json(
        [
            "lark-cli",
            "sheets",
            "+csv-get",
            "--spreadsheet-token",
            full_product_spreadsheet_token,
            "--sheet-id",
            full_product_sheet_id,
            "--range",
            f"A1:{_column_name(len(report.full_improvement_headers))}{len(report.full_improvement_rows) + 1}",
            "--as",
            "user",
            "--format",
            "json",
        ],
        command_runner=command_runner,
    )
    _verify_sheet_readback(
        full_source_readback,
        expected_end_row=len(report.full_improvement_rows) + 1,
        expected_end_column=_column_name(len(report.full_improvement_headers)),
        expected_rows=full_expected_rows,
    )
    report_xml = render_periodic_report_xml(
        report=report,
        period=period,
        snapshot_label=snapshot_label,
        full_product_url=f"https://my.feishu.cn/sheets/{full_product_spreadsheet_token}",
    )
    created_document = _command_json(
        [
            "lark-cli",
            "docs",
            "+create",
            "--as",
            "user",
            "--parent-position",
            "my_library",
            "--content",
            "-",
            "--format",
            "json",
        ],
        command_runner=command_runner,
        input_text=report_xml,
    )
    document_url = _document_url(created_document)
    publication_state["document_url"] = document_url
    document_readback = _command_json(
        [
            "lark-cli",
            "docs",
            "+fetch",
            "--as",
            "user",
            "--doc",
            document_url,
            "--scope",
            "full",
            "--detail",
            "simple",
            "--format",
            "json",
        ],
        command_runner=command_runner,
    )
    document = _data_mapping(document_readback).get("document")
    content = document.get("content") if isinstance(document, dict) else None
    expected_title = report_document_title(period, snapshot_label)
    if not isinstance(content, str) or expected_title not in content:
        raise RuntimeError("document readback is missing the expected report title")
    for section in (
        "RDHS总览",
        "产品改进清单",
        "全量产品改进清单",
        full_product_spreadsheet_token,
    ):
        if section not in content:
            raise RuntimeError(f"document readback is missing required content: {section}")
    (embedded_summary_token, embedded_summary_id), (
        embedded_improvement_token,
        embedded_improvement_id,
    ) = _embedded_sheet_refs(content)
    publication_state.update(
        {
            "spreadsheet_token": embedded_summary_token,
            "summary_sheet_id": embedded_summary_id,
            "improvement_sheet_id": embedded_improvement_id,
        }
    )
    for sheet_token, sheet_id, rows in (
        (embedded_summary_token, embedded_summary_id, summary_expected_rows),
        (embedded_improvement_token, embedded_improvement_id, improvement_expected_rows),
    ):
        _command_json(
            [
                "lark-cli",
                "sheets",
                "+csv-put",
                "--spreadsheet-token",
                sheet_token,
                "--sheet-id",
                sheet_id,
                "--start-cell",
                "A1",
                "--csv",
                "-",
                "--as",
                "user",
                "--format",
                "json",
            ],
            command_runner=command_runner,
            input_text=_rows_as_csv(rows),
        )
    for sheet_token, sheet_id, expected_end_row, expected_end_column, expected_rows in (
        (embedded_summary_token, embedded_summary_id, len(report.overview_rows) + 1, "G", summary_expected_rows),
        (
            embedded_improvement_token,
            embedded_improvement_id,
            len(report.improvement_rows) + 1,
            "G",
            improvement_expected_rows,
        ),
    ):
        sheet_readback = _command_json(
            [
                "lark-cli",
                "sheets",
                "+csv-get",
                "--spreadsheet-token",
                sheet_token,
                "--sheet-id",
                sheet_id,
                "--range",
                f"A1:{expected_end_column}{expected_end_row}",
                "--as",
                "user",
                "--format",
                "json",
            ],
            command_runner=command_runner,
        )
        _verify_sheet_readback(
            sheet_readback,
            expected_end_row=expected_end_row,
            expected_end_column=expected_end_column,
            expected_rows=expected_rows,
        )
    publication_state["status"] = "verified"
    return PeriodicPublication(
        document_url=document_url,
        spreadsheet_token=embedded_summary_token,
        summary_sheet_id=embedded_summary_id,
        improvement_sheet_id=embedded_improvement_id,
        full_product_sheet_id=full_product_sheet_id,
        full_product_spreadsheet_token=full_product_spreadsheet_token,
    )


def _run_dir_for(mode: str, as_of: date, output_root: Path) -> Path:
    if mode == "trial":
        return output_root / f"{as_of.isoformat()}-trial"
    if mode == "weekly":
        return output_root / as_of.strftime("%Y-%m") / f"week-{as_of.strftime('%Y%m%d')}"
    return output_root / as_of.strftime("%Y-%m") / "monthly-baseline"


def run_periodic_report(
    *,
    mode: str,
    as_of: date,
    output_root: Path,
    project_key: str,
    current_chart_id: str,
    previous_chart_id: str,
    current_payload: dict[str, object] | None = None,
    previous_payload: dict[str, object] | None = None,
    product_master_payload: dict[str, object] | None = None,
    business_lines_payload: dict[str, object] | None = None,
    team_mapping_path: Path = _DEFAULT_TEAM_MAPPING_PATH,
    publish: bool,
    command_runner: CommandRunner = _subprocess_runner,
) -> PeriodicReportRunResult:
    """执行试运行或周报；输入快照时不会重复请求图表。"""
    if mode not in {"trial", "weekly", "monthly-baseline"}:
        raise ValueError(f"unsupported periodic report mode: {mode}")
    run_dir = _run_dir_for(mode, as_of, output_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    period = as_of.strftime("%Y-%m")
    baseline_path = output_root / period / "baselines" / f"{_previous_month(period)}.json"

    if mode == "monthly-baseline":
        if previous_payload is not None:
            raw_baseline = previous_payload
        else:
            raw_baseline = fetch_chart_payload(
                project_key=project_key,
                chart_id=previous_chart_id,
                command_runner=command_runner,
            )
        baseline_fetched_at = _snapshot_time()
        baseline_snapshot = _persist_and_parse_chart_snapshot(
            raw_payload=raw_baseline,
            chart_id=previous_chart_id,
            fetched_at=baseline_fetched_at,
            raw_path=run_dir / "baseline_chart_raw.json",
            run_dir=run_dir,
            mode=mode,
            as_of=as_of,
            source="baseline",
        )
        _write_json(baseline_path, raw_baseline)
        _write_json(
            _baseline_metadata_path(baseline_path),
            {"chart_id": previous_chart_id, "fetched_at": baseline_fetched_at},
        )
        manifest_path = run_dir / "audit_manifest.json"
        _write_json(
            manifest_path,
            {
                "mode": mode,
                "as_of": as_of.isoformat(),
                "baseline_path": str(baseline_path),
                "data_validation": {"previous": asdict(baseline_snapshot.audit)},
                "publication": {"published": False},
            },
        )
        return PeriodicReportRunResult(
            run_dir=run_dir,
            report_data_path=manifest_path,
            audit_manifest_path=manifest_path,
            publication_url=None,
        )

    if current_payload is not None:
        raw_current = current_payload
    else:
        raw_current = fetch_chart_payload(
            project_key=project_key,
            chart_id=current_chart_id,
            command_runner=command_runner,
        )
    current_fetched_at = _snapshot_time()
    current_snapshot = _persist_and_parse_chart_snapshot(
        raw_payload=raw_current,
        chart_id=current_chart_id,
        fetched_at=current_fetched_at,
        raw_path=run_dir / "current_chart_raw.json",
        run_dir=run_dir,
        mode=mode,
        as_of=as_of,
        source="current",
    )
    if previous_payload is not None:
        raw_previous = previous_payload
        baseline_source = "provided"
        previous_fetched_at = _snapshot_time()
    elif baseline_path.exists():
        raw_previous = _load_json(baseline_path)
        baseline_source = "stored_month_start_baseline"
        previous_fetched_at = _stored_baseline_timestamp(baseline_path)
    else:
        raw_previous = fetch_chart_payload(
            project_key=project_key,
            chart_id=previous_chart_id,
            command_runner=command_runner,
        )
        baseline_source = "late_backfill"
        previous_fetched_at = _snapshot_time()
    previous_snapshot = _persist_and_parse_chart_snapshot(
        raw_payload=raw_previous,
        chart_id=previous_chart_id,
        fetched_at=previous_fetched_at,
        raw_path=run_dir / "previous_chart_raw.json",
        run_dir=run_dir,
        mode=mode,
        as_of=as_of,
        source="previous",
    )
    if baseline_source == "late_backfill":
        _write_json(baseline_path, raw_previous)
        _write_json(
            _baseline_metadata_path(baseline_path),
            {"chart_id": previous_chart_id, "fetched_at": previous_fetched_at},
        )
    raw_business_lines = business_lines_payload or fetch_business_lines_payload(
        project_key=project_key, command_runner=command_runner
    )
    raw_product_masters = product_master_payload or fetch_product_master_payload(
        project_key=project_key, command_runner=command_runner
    )
    _write_json(run_dir / "business_lines_raw.json", raw_business_lines)
    _write_json(run_dir / "product_master_raw.json", raw_product_masters)
    product_masters = parse_product_master_records(
        raw_product_masters, parse_business_line_names(raw_business_lines)
    )
    enriched_rows = build_full_improvement_rows(
        current_snapshot, product_masters, load_team_mappings(team_mapping_path)
    )
    full_improvement_rows = tuple(
        (
            row.business_line,
            row.product,
            row.product_status,
            row.super_team_count,
            row.governance_mode,
            row.rdhs,
            row.lowest_component,
            row.problem,
            row.main_problem_tag,
            row.action,
        )
        for row in enriched_rows
    )
    match_audit = [
        {
            "business_line": row.business_line,
            "product": row.product,
            "product_status": row.product_status,
            "master_match_state": row.master_match_state,
            "master_id": row.master_id,
            "master_status_raw": row.master_status_raw,
            "association_state": row.association_state,
            "super_team_count": row.super_team_count,
            "team_names": list(row.team_names),
        }
        for row in enriched_rows
    ]
    _write_json(run_dir / "product_master_match_audit.json", {"rows": match_audit})
    report = build_periodic_report_data(current=current_snapshot, previous=previous_snapshot)
    report = replace(
        report,
        full_improvement_headers=tuple(_FULL_IMPROVEMENT_HEADERS),
        full_improvement_rows=full_improvement_rows,
        audit={
            **report.audit,
            "full_improvement_count": len(full_improvement_rows),
            "product_master_match_audit_path": str(run_dir / "product_master_match_audit.json"),
        },
    )

    _write_csvs(report, run_dir)
    report_data_path = run_dir / "report_data.json"
    _write_json(report_data_path, _report_as_dict(report))

    publication: PeriodicPublication | None = None
    manifest_path = run_dir / "audit_manifest.json"
    if publish:
        snapshot_label = (
            f"{as_of.isoformat()} 试运行快照"
            if mode == "trial"
            else f"{as_of.isoformat()} 周度快照"
        )
        publication_state: dict[str, object] = {}
        try:
            publication = publish_periodic_report(
                report=report,
                period=period,
                snapshot_label=snapshot_label,
                command_runner=command_runner,
                publication_state=publication_state,
            )
        except Exception as exc:
            _write_json(
                manifest_path,
                {
                    "mode": mode,
                    "as_of": as_of.isoformat(),
                    "baseline_source": baseline_source,
                    "data_validation": {
                        "current": asdict(current_snapshot.audit),
                        "previous": asdict(previous_snapshot.audit),
                    },
                    "report": report.audit,
                    "publication": {
                        "published": False,
                        "status": "failed",
                        "error": str(exc),
                        "resources": publication_state,
                    },
                },
            )
            raise
    _write_json(
        manifest_path,
        {
            "mode": mode,
            "as_of": as_of.isoformat(),
            "baseline_source": baseline_source,
            "data_validation": {
                "current": asdict(current_snapshot.audit),
                "previous": asdict(previous_snapshot.audit),
            },
            "report": report.audit,
            "publication": (
                {
                    "published": True,
                    "document_url": publication.document_url,
                    "spreadsheet_token": publication.spreadsheet_token,
                    "summary_sheet_id": publication.summary_sheet_id,
                    "improvement_sheet_id": publication.improvement_sheet_id,
                    "full_product_sheet_id": publication.full_product_sheet_id,
                    "full_product_spreadsheet_token": publication.full_product_spreadsheet_token,
                }
                if publication
                else {"published": False}
            ),
        },
    )
    return PeriodicReportRunResult(
        run_dir=run_dir,
        report_data_path=report_data_path,
        audit_manifest_path=manifest_path,
        publication_url=publication.document_url if publication else None,
    )
