"""图表数据抓取与 CSV 导出。"""

from __future__ import annotations

import csv
from pathlib import Path
import re

from shared.browser.browser_fetcher import fetch_chart_response_via_browser
from shared.browser.browser_fetcher import goto_view
from shared.browser.browser_fetcher import run_playwright_eval
from shared.browser.chart_discovery import build_bql_filter_from_view_config
from shared.browser.chart_discovery import extract_quick_filter_id
from shared.browser.chart_discovery import extract_view_id
from shared.browser.chart_discovery import fetch_view_config
from shared.browser.chart_discovery import parse_chart_ids_from_view_config
from shared.browser.chart_discovery import parse_view_info

DEFAULT_EXPORT_CHART_NAMES = [
    "产研过程核心指标 By 业务线",
    "产研健康度得分(RDHS) By 业务线",
    "积压需求分布 By 业务线",
]

_REQUEST_PAYLOAD_BASE_KEYS = {
    "project_key",
    "chart_id",
    "is_latest",
    "is_complete_config",
    "latest",
    "client_info",
}
_CHART_TITLE_SELECTOR = "h1.metric-header-title"


def _get_nested_chart_payload(raw_response: dict) -> dict:
    return raw_response.get("data", {}).get("data", {})


def _extract_axis_titles(chart_payload: dict) -> tuple[list[str], list[str]]:
    magic_definition = chart_payload.get("data_based_chart", {}).get("magicDefinition", {})
    dim_titles = chart_payload.get("dim_titles") or [
        item.get("display", {}).get("showName", "")
        for item in magic_definition.get("dims", [])
        if item.get("display", {}).get("showName")
    ]
    quota_titles = chart_payload.get("quota_titles") or [
        item.get("display", {}).get("showName", "")
        for item in magic_definition.get("quotas", [])
        if item.get("display", {}).get("showName")
    ]
    return list(dim_titles), list(quota_titles)


def _normalize_cell(value: object) -> str:
    text = "" if value is None else str(value)
    if text == "(空)":
        return ""
    return text


def _read_series_value(series: dict[str, object], index: int, title: str) -> str:
    if str(index) in series:
        return _normalize_cell(series[str(index)])
    if title in series:
        return _normalize_cell(series[title])
    return ""


def flatten_chart_response_to_table(raw_response: dict) -> dict[str, object]:
    """将图表接口响应展开成可写入 CSV 的二维表。"""
    chart_payload = _get_nested_chart_payload(raw_response)
    chart_name = chart_payload.get("data_based_chart", {}).get("name", "")
    dim_titles, quota_titles = _extract_axis_titles(chart_payload)
    headers = dim_titles + quota_titles

    rows: list[dict[str, str]] = []
    for chart_row in chart_payload.get("chart_data_list", []):
        for data_set in chart_row.get("data_sets", []):
            dim_values = data_set.get("dimValues", {})
            quota_values = data_set.get("quotaValues", {})
            row: dict[str, str] = {}
            for index, title in enumerate(dim_titles):
                row[title] = _read_series_value(dim_values, index, title)
            for index, title in enumerate(quota_titles):
                row[title] = _read_series_value(quota_values, index, title)
            if row:
                rows.append(row)

    return {
        "chart_name": chart_name,
        "headers": headers,
        "rows": rows,
    }


def sanitize_chart_filename(chart_name: str) -> str:
    sanitized = re.sub(r"[^\w\u4e00-\u9fff]+", "_", chart_name).strip("_")
    return f"{sanitized or 'chart'}.csv"


def _build_request_payload_overrides(captured_payload: dict[str, object] | None) -> dict | None:
    if not captured_payload:
        return None
    overrides = {
        key: value
        for key, value in captured_payload.items()
        if key not in _REQUEST_PAYLOAD_BASE_KEYS
    }
    return overrides or None


def _collect_visible_chart_titles(session_name: str, expected_count: int) -> list[str]:
    return run_playwright_eval(
        session_name,
        f"""async () => {{
          const selector = {repr(_CHART_TITLE_SELECTOR)};
          const expectedCount = {expected_count};
          const maxSteps = Math.max(6, expectedCount);
          const seen = new Set();

          const readTitles = () => Array.from(document.querySelectorAll(selector))
            .map((el) => (el.textContent || '').trim())
            .filter(Boolean);

          for (let step = 0; step < maxSteps; step += 1) {{
            for (const title of readTitles()) {{
              seen.add(title);
            }}
            if (seen.size >= expectedCount) {{
              break;
            }}
            const scrollHeight = Math.max(
              document.body?.scrollHeight || 0,
              document.documentElement?.scrollHeight || 0,
            );
            const nextTop = scrollHeight * ((step + 1) / maxSteps);
            window.scrollTo(0, nextTop);
            await new Promise((resolve) => setTimeout(resolve, 400));
          }}

          window.scrollTo(0, 0);
          return Array.from(seen);
        }}""",
    )


def _resolve_chart_ids_by_name(
    *,
    session_name: str,
    view_payload: dict,
    project_key: str,
    target_chart_names: list[str],
    request_payload: dict | None,
) -> dict[str, str]:
    chart_ids = parse_chart_ids_from_view_config(view_payload)
    visible_titles = _collect_visible_chart_titles(
        session_name=session_name,
        expected_count=len(chart_ids),
    )
    chart_name_to_id = {
        title: chart_id for title, chart_id in zip(visible_titles, chart_ids)
    }
    missing_chart_names = [
        chart_name for chart_name in target_chart_names if chart_name not in chart_name_to_id
    ]
    if missing_chart_names:
        used_chart_ids = set(chart_name_to_id.values())
        for chart_id in chart_ids:
            if chart_id in used_chart_ids:
                continue
            raw_response = fetch_chart_response_via_browser(
                session_name=session_name,
                project_key=project_key,
                chart_id=chart_id,
                request_payload=request_payload,
            )
            chart_name = (
                _get_nested_chart_payload(raw_response)
                .get("data_based_chart", {})
                .get("name", "")
            )
            if chart_name and chart_name not in chart_name_to_id:
                chart_name_to_id[chart_name] = chart_id
                used_chart_ids.add(chart_id)

        missing_chart_names = [
            chart_name for chart_name in target_chart_names if chart_name not in chart_name_to_id
        ]
        if missing_chart_names:
            raise ValueError(
                f"chart titles not found on page: {', '.join(missing_chart_names)}"
            )
    return chart_name_to_id


def _write_table_to_csv(table: dict[str, object], output_path: Path) -> None:
    headers = list(table.get("headers", []))
    rows = list(table.get("rows", []))
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def export_chart_csvs_from_view(
    *,
    view_url: str,
    session_name: str,
    project_key: str,
    output_dir: Path,
    chart_names: list[str],
) -> list[Path]:
    """抓取视图中的目标图表，并分别导出成 CSV。"""
    goto_view(session_name=session_name, view_url=view_url)
    view_id = extract_view_id(view_url)
    view_payload = fetch_view_config(session_name=session_name, view_id=view_id)
    _view_name, resolved_project_key = parse_view_info(view_payload)
    effective_project_key = resolved_project_key or project_key
    target_chart_names = chart_names or DEFAULT_EXPORT_CHART_NAMES
    quick_filter_id = extract_quick_filter_id(view_url)
    bql_filter = build_bql_filter_from_view_config(
        payload=view_payload,
        quick_filter_id=quick_filter_id,
    )
    request_payload = {"bql_filter": bql_filter} if bql_filter else None
    chart_name_to_id = _resolve_chart_ids_by_name(
        session_name=session_name,
        view_payload=view_payload,
        project_key=effective_project_key,
        target_chart_names=target_chart_names,
        request_payload=request_payload,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    exported_paths: list[Path] = []
    for chart_name in target_chart_names:
        chart_id = chart_name_to_id[chart_name]
        raw_response = fetch_chart_response_via_browser(
            session_name=session_name,
            project_key=effective_project_key,
            chart_id=chart_id,
            request_payload=request_payload,
        )
        table = flatten_chart_response_to_table(raw_response)
        output_path = output_dir / sanitize_chart_filename(chart_name)
        _write_table_to_csv(table, output_path)
        exported_paths.append(output_path)

    return exported_paths
