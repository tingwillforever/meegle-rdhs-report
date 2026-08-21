from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from impl.browser_auth import close_browser_session
from impl.browser_auth import ensure_rdhs_browser_session
from impl.browser_auth import open_browser_session
from impl.browser_auth import prepare_managed_rdhs_session
from impl.browser_auth import try_load_storage_state
from impl.chart_discovery import discover_chart_catalog
from impl.chart_discovery import extract_quick_filters_from_view_config
from impl.chart_discovery import extract_quick_filter_id
from impl.chart_discovery import extract_view_id
from impl.chart_discovery import fetch_view_config
from impl.llm_insight_engine import generate_ai_insights
from impl.chart_discovery import map_chart_name_to_metric_field
from impl.chart_export import export_chart_csvs_from_view
from impl.pipeline import run_pipeline
from impl.release_deploy_pipeline import export_month_to_dir
from impl.release_deploy_pipeline import export_trend
from impl.release_deploy_pipeline import rebuild_history_from_monthly_outputs
from shared.browser.browser_fetcher import discover_chart_request_payloads
from shared.browser.browser_fetcher import extract_measure_response_data
from shared.browser.browser_fetcher import fetch_chart_response_via_browser
from shared.browser.browser_fetcher import goto_view
from shared.browser.browser_fetcher import run_playwright_eval
from shared.browser.chart_discovery import parse_view_info
from shared.config.config_loader import load_llm_runtime_config
from shared.config.config_loader import load_browser_auth_runtime_config
from shared.config.config_loader import load_report_config
from shared.llm.llm_client import LLMClient

_CHART_CATALOG_CACHE: dict[tuple[str, str], tuple[int, object]] = {}
_REQUEST_PAYLOAD_BASE_KEYS = {
    "project_key",
    "chart_id",
    "is_latest",
    "is_complete_config",
    "latest",
    "client_info",
}


def _build_ai_insight_runner(config_path: Path):
    try:
        client = LLMClient(load_llm_runtime_config(config_path=config_path))
    except ValueError:
        return None

    return lambda **kwargs: generate_ai_insights(client, **kwargs)


def _build_appendix_links() -> dict[str, object]:
    return {
        "feedback_link": "https://project.xfchat.iflytek.com/cbg_product_develop/feedback/create?parentUrl=%2Fcbg_product_develop%2Ffeedback%2Fhomepage",
        "reference_links": [
            {"title": "RDHS规则说明", "url": ""},
            {"title": "自动化发布能力接入", "url": ""},
        ],
    }


def _resolve_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_topic_root(config_path: Path | None = None) -> Path:
    cli_root = _resolve_project_root()
    if config_path is None:
        return cli_root

    config_dir = config_path.resolve().parent
    default_config_dir = cli_root / "config"
    if config_dir == default_config_dir:
        return cli_root
    return cli_root


def _resolve_project_path(raw_path: str, default_relative: str) -> Path:
    path = Path(raw_path)
    if raw_path == default_relative:
        return _resolve_project_root() / default_relative
    return path if path.is_absolute() else (_resolve_project_root() / path)


def validate_month(value: str) -> str:
    if not re.match(r"^\d{4}-\d{2}$", value):
        raise argparse.ArgumentTypeError(
            f"月份格式错误: '{value}'，请使用 YYYY-MM 格式，例如: 2026-03"
        )
    _, month = value.split("-")
    if not 1 <= int(month) <= 12:
        raise argparse.ArgumentTypeError(f"月份值无效: '{value}'，月份应在 01-12 之间")
    return value


def build_cumulative_period(month: str) -> str:
    return f"{month[:4]}-累计"


def replace_quick_filter_id(view_url: str, quick_filter_id: str) -> str:
    parsed = urlparse(view_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["quickFilterId"] = quick_filter_id
    return urlunparse(parsed._replace(query=urlencode(query)))


def build_relative_month_labels(reference_month: str) -> dict[str, str]:
    previous_month = _previous_month(reference_month)
    return {
        reference_month: "上月",
        previous_month: "上上月",
    }


def resolve_month_from_quick_filter_name(
    *,
    quick_filter_name: str,
    reference_month: str,
) -> str:
    normalized_name = quick_filter_name.strip()
    if normalized_name == "上月":
        return reference_month
    if normalized_name == "上上月":
        return _previous_month(reference_month)
    raise ValueError(
        f"unable to resolve report month from quick filter name '{quick_filter_name}'"
    )


def resolve_quick_filter_id_by_name(
    *,
    view_payload: dict[str, object],
    quick_filter_name: str,
) -> str:
    for item in extract_quick_filters_from_view_config(view_payload):
        if item["name"] == quick_filter_name:
            return item["id"]
    raise ValueError(
        f"unable to resolve quick filter id for quick filter name '{quick_filter_name}'"
    )


def resolve_run_month_and_view_url(
    *,
    requested_month: str | None,
    configured_view_url: str,
    view_payload: dict[str, object],
    reference_month: str,
) -> tuple[str, str]:
    if requested_month:
        month_labels = build_relative_month_labels(reference_month)
        quick_filter_name = month_labels.get(requested_month, "").strip()
        if not quick_filter_name:
            raise ValueError(f"unsupported requested month '{requested_month}'")
        quick_filter_id = resolve_quick_filter_id_by_name(
            view_payload=view_payload,
            quick_filter_name=quick_filter_name,
        )
        return requested_month, replace_quick_filter_id(configured_view_url, quick_filter_id)

    current_quick_filter_id = extract_quick_filter_id(configured_view_url)
    for item in extract_quick_filters_from_view_config(view_payload):
        if item["id"] == current_quick_filter_id:
            return (
                resolve_month_from_quick_filter_name(
                    quick_filter_name=item["name"],
                    reference_month=reference_month,
                ),
                configured_view_url,
            )
    raise ValueError(
        f"unable to resolve report month from quickFilterId='{current_quick_filter_id}'"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CBG RDHS 月度运营报告自动化工具")
    parser.add_argument("--month", type=validate_month)
    parser.add_argument("--view-url")
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--config", default="config/template.yaml")
    parser.add_argument("--project-key", default="")
    parser.add_argument("--trend-months", type=int, default=3)
    parser.add_argument("--rebuild-history", action="store_true")
    parser.add_argument("--export-charts", action="store_true")
    parser.add_argument("--chart-name", action="append", dest="chart_names", default=[])
    parser.add_argument(
        "--business-line", action="append", dest="business_lines", default=[]
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    if not args.month and not args.rebuild_history and not args.export_charts:
        return args
    return args


def _previous_month(month: str) -> str:
    year, m = month.split("-")
    prev_month = int(m) - 1
    if prev_month == 0:
        return f"{int(year) - 1}-12"
    return f"{year}-{prev_month:02d}"


def _current_reference_month() -> str:
    from datetime import datetime

    return _previous_month(datetime.now().strftime("%Y-%m"))


def _resolve_release_deploy_output_root(output_dir: Path, month: str) -> Path:
    return output_dir.parent if output_dir.name == month else output_dir


def _prepare_managed_session_with_storage_only(*, dashboard_config, project_root: Path) -> str:
    storage_state_path = Path(dashboard_config.storage_state_path)
    if not storage_state_path.is_absolute():
        storage_state_path = project_root / storage_state_path

    session_name = dashboard_config.session_name or "rdhs-operations"
    start_url = dashboard_config.view_url or dashboard_config.login_url
    open_browser_session(
        session_name=session_name,
        start_url=start_url,
        headless=dashboard_config.headless,
    )
    try_load_storage_state(
        session_name=session_name,
        storage_state_path=storage_state_path,
    )
    return session_name


def _load_cached_delivery_summary(
    output_root: Path, month: str
) -> dict[str, object] | None:
    candidates = [
        output_root / month / "monthly_insight_input.json",
        output_root / "release-deploy-rerun" / month / "monthly_insight_input.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        return {
            "overview": payload.get("overview", {}),
            "top_risk_business_lines": payload.get("top_risk_business_lines", []),
            "focus_candidates": payload.get("focus_candidates", {}),
            "business_summaries": payload.get("business_summaries", []),
        }
    return None


def resolve_effective_view_url(session_name: str, fallback_view_url: str) -> str:
    try:
        page_state = run_playwright_eval(
            session_name,
            "() => ({ href: window.location.href })",
        )
    except Exception:
        return fallback_view_url

    current_url = str(page_state.get("href", "")).strip()
    if current_url:
        return current_url
    return fallback_view_url


def _build_chart_request_payload_overrides(
    captured_payload: dict[str, object] | None,
) -> dict[str, object] | None:
    if not captured_payload:
        return None

    overrides = {
        key: value
        for key, value in captured_payload.items()
        if key not in _REQUEST_PAYLOAD_BASE_KEYS
    }
    if "latest" in captured_payload:
        overrides["latest"] = captured_payload["latest"]
    return overrides or None


def fetch_raw_records_from_view(
    *,
    period: str,
    view_url: str,
    business_lines: list[str],
    session_name: str,
    project_key: str,
    quick_filter_id_override: str | None = None,
) -> list[dict[str, object]]:
    if not ensure_rdhs_browser_session(session_name):
        raise RuntimeError("浏览器会话未就绪，请先完成登录")

    goto_view(session_name=session_name, view_url=view_url)
    effective_view_url = resolve_effective_view_url(session_name, view_url)
    view_id = extract_view_id(view_url)
    view_payload = fetch_view_config(session_name=session_name, view_id=view_id)
    _view_name, resolved_project_key = parse_view_info(view_payload)
    effective_project_key = resolved_project_key or project_key
    cache_key = (session_name, view_url)
    cache_entry = _CHART_CATALOG_CACHE.get(cache_key)
    discover_version = id(discover_chart_catalog)
    if cache_entry and cache_entry[0] == discover_version:
        chart_catalog = cache_entry[1]
    else:
        chart_catalog = discover_chart_catalog(
            session_name=session_name, view_url=view_url
        )
        _CHART_CATALOG_CACHE[cache_key] = (discover_version, chart_catalog)
    captured_request_payloads = discover_chart_request_payloads(
        session_name=session_name,
        view_url=effective_view_url,
    )

    grouped_records: dict[tuple[str, str], dict[str, object]] = {}
    matrix_chart_id = chart_catalog.charts.get("产研过程核心指标 By 业务线")
    if matrix_chart_id:
        response = fetch_chart_response_via_browser(
            session_name=session_name,
            project_key=effective_project_key,
            chart_id=matrix_chart_id,
            request_payload=_build_chart_request_payload_overrides(
                captured_request_payloads.get(matrix_chart_id)
            ),
        )
        _merge_matrix_chart_records(
            grouped_records=grouped_records,
            period=period,
            business_lines=business_lines,
            raw_response=response,
        )
        rdhs_matrix_chart_id = chart_catalog.charts.get("产研健康度得分(RDHS) By 业务线")
        if rdhs_matrix_chart_id:
            rdhs_response = fetch_chart_response_via_browser(
                session_name=session_name,
                project_key=effective_project_key,
                chart_id=rdhs_matrix_chart_id,
                request_payload=_build_chart_request_payload_overrides(
                    captured_request_payloads.get(rdhs_matrix_chart_id)
                ),
            )
            _merge_matrix_chart_records(
                grouped_records=grouped_records,
                period=period,
                business_lines=business_lines,
                raw_response=rdhs_response,
            )
        if grouped_records:
            return list(grouped_records.values())

    for chart_name, chart_id in chart_catalog.charts.items():
        response = fetch_chart_response_via_browser(
            session_name=session_name,
            project_key=effective_project_key,
            chart_id=chart_id,
            request_payload=_build_chart_request_payload_overrides(
                captured_request_payloads.get(chart_id)
            ),
        )

        metric_field = map_chart_name_to_metric_field(chart_name)
        if not metric_field:
            continue
        normalized = extract_measure_response_data(response)
        chart_rows = normalized.get("data", {}).get("chart_data_list", [])
        for row_group in chart_rows:
            for row in row_group:
                dim = row.get("dim", {})
                value = row.get("value", {})
                level_1 = str(dim.get("一级业务线", dim.get("level_1", "")))
                level_2 = str(dim.get("二级业务线", dim.get("level_2", "")))
                if not level_1 and not level_2:
                    continue
                if (
                    business_lines
                    and level_1 not in business_lines
                    and level_2 not in business_lines
                ):
                    continue
                key = (level_1, level_2)
                record = grouped_records.setdefault(
                    key,
                    {
                        "period": period,
                        "level_1": level_1,
                        "level_2": level_2,
                        "monthly_requirement_throughput": 0.0,
                        "monthly_bug_closed": 0.0,
                        "monthly_release_frequency": 0.0,
                        "avg_dev_cycle_days": 0.0,
                        "avg_delivery_cycle_days": 0.0,
                        "serious_bug_rate": 0.0,
                        "easy_detect_bug_rate": 0.0,
                    },
                )
                metric_value = next(iter(value.values()), 0.0)
                record[metric_field] = metric_value

    return list(grouped_records.values())


def _merge_matrix_chart_records(
    *,
    grouped_records: dict[tuple[str, str], dict[str, object]],
    period: str,
    business_lines: list[str],
    raw_response: dict[str, object],
) -> None:
    nested = raw_response.get("data", {}).get("data", {})
    chart = nested.get("data_based_chart", {})
    magic_definition = chart.get("magicDefinition", {})
    dims = magic_definition.get("dims", [])
    quotas = magic_definition.get("quotas", [])

    dim_titles = [item.get("display", {}).get("showName", "") for item in dims]
    quota_title_by_key = {
        str(index): item.get("display", {}).get("showName", "")
        for index, item in enumerate(quotas)
    }
    quota_fields = {
        quota_key: map_chart_name_to_metric_field(quota_title)
        for quota_key, quota_title in quota_title_by_key.items()
    }
    precomputed_title_field_map = {
        "RDHS(100')": "precomputed_rdhs_score",
        "链路闭环得分(25')": "precomputed_link_score",
        "链路闭环情况(25')": "precomputed_link_score",
        "发布连续性(15')": "precomputed_release_score",
        "时效节奏合理性(20')": "precomputed_timeliness_score",
        "颗粒度对齐度(20')": "precomputed_granularity_score",
        "质量敏锐度(20')": "precomputed_quality_score",
        "质量管理得分(20')": "precomputed_quality_score",
    }
    precomputed_fields = {
        quota_key: precomputed_title_field_map[quota_title]
        for quota_key, quota_title in quota_title_by_key.items()
        if quota_title in precomputed_title_field_map
    }

    for chart_row in nested.get("chart_data_list", []):
        for data_set in chart_row.get("data_sets", []):
            dim_values = data_set.get("dimValues", {})
            quota_values = data_set.get("quotaValues", {})
            level_1 = str(dim_values.get("0", "")) if dim_titles[:1] else ""
            level_2 = str(dim_values.get("1", "")) if len(dim_titles) > 1 else ""

            if level_1 == "(空)":
                level_1 = ""
            if level_2 == "(空)":
                level_2 = ""
            if not level_1:
                continue
            if (
                business_lines
                and level_1 not in business_lines
                and level_2 not in business_lines
            ):
                continue

            metric_values = [
                quota_values.get(quota_key, "0")
                for quota_key, metric_field in quota_fields.items()
                if metric_field
            ]
            has_precomputed_scores = any(
                quota_key in quota_values for quota_key in precomputed_fields
            )
            precomputed_scores = {
                field_name: quota_values.get(quota_key, "0")
                for quota_key, field_name in precomputed_fields.items()
            }
            if all(float(value or 0) == 0.0 for value in metric_values) and all(
                float(value or 0) == 0.0 for value in precomputed_scores.values()
            ):
                continue

            key = (level_1, level_2)
            record = grouped_records.setdefault(
                key,
                {
                    "period": period,
                    "level_1": level_1,
                    "level_2": level_2,
                    "monthly_requirement_throughput": 0.0,
                    "monthly_bug_closed": 0.0,
                    "monthly_release_frequency": 0.0,
                    "avg_dev_cycle_days": 0.0,
                    "avg_delivery_cycle_days": 0.0,
                    "serious_bug_rate": 0.0,
                    "easy_detect_bug_rate": 0.0,
                },
            )
            if has_precomputed_scores:
                record.update(precomputed_scores)

            for quota_key, quota_value in quota_values.items():
                metric_field = quota_fields.get(str(quota_key), "")
                if metric_field:
                    record[metric_field] = quota_value


def run_with_args(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = _resolve_project_path(args.config, "config/template.yaml")
    config = load_report_config(config_path)
    resolved_output_dir = _resolve_project_path(args.output_dir, "reports")
    release_deploy_output_root = _resolve_release_deploy_output_root(
        resolved_output_dir, args.month or ""
    )
    release_deploy_project_key = args.project_key or config.dashboard.project_key

    if args.rebuild_history:
        rebuild_history_from_monthly_outputs(
            release_deploy_output_root, project_key=release_deploy_project_key
        )
        return 0

    configured_view_url = args.view_url or config.dashboard.view_url
    view_url = configured_view_url
    if not view_url:
        raise ValueError("missing required dashboard.view_url")
    if not config.dashboard.project_key:
        raise ValueError("missing required dashboard.project_key")
    project_root = _resolve_topic_root(config_path)

    session_name = config.dashboard.session_name
    should_close_session = False
    browser_mode = getattr(config.dashboard, "browser_mode", "session")
    if browser_mode == "managed":
        try:
            auth_config = load_browser_auth_runtime_config(config_path)
        except ValueError:
            auth_config = None
        if auth_config is not None:
            session_name = prepare_managed_rdhs_session(
                dashboard_config=config.dashboard,
                auth_config=auth_config,
                project_root=project_root,
            )
        else:
            session_name = _prepare_managed_session_with_storage_only(
                dashboard_config=config.dashboard,
                project_root=project_root,
            )
        should_close_session = True

    try:
        if args.export_charts:
            export_chart_csvs_from_view(
                view_url=view_url,
                session_name=session_name,
                project_key=config.dashboard.project_key,
                output_dir=resolved_output_dir,
                chart_names=args.chart_names,
            )
            return 0

        goto_view(session_name=session_name, view_url=configured_view_url)
        view_id = extract_view_id(configured_view_url)
        view_payload = fetch_view_config(session_name=session_name, view_id=view_id)
        effective_month, view_url = resolve_run_month_and_view_url(
            requested_month=args.month,
            configured_view_url=configured_view_url,
            view_payload=view_payload,
            reference_month=_current_reference_month(),
        )

        raw_records = fetch_raw_records_from_view(
            period=effective_month,
            view_url=view_url,
            business_lines=args.business_lines,
            session_name=session_name,
            project_key=config.dashboard.project_key,
        )
        cumulative_raw_records = None
        cumulative_quick_filter_id = getattr(
            config.dashboard, "cumulative_quick_filter_id", ""
        ).strip()
        cumulative_view_url = getattr(config.dashboard, "cumulative_view_url", "").strip()
        if cumulative_quick_filter_id:
            cumulative_raw_records = fetch_raw_records_from_view(
                period=build_cumulative_period(effective_month),
                view_url=view_url,
                business_lines=args.business_lines,
                session_name=session_name,
                project_key=config.dashboard.project_key,
                quick_filter_id_override=cumulative_quick_filter_id,
            )
        elif cumulative_view_url and cumulative_view_url != view_url:
            cumulative_raw_records = fetch_raw_records_from_view(
                period=build_cumulative_period(effective_month),
                view_url=cumulative_view_url,
                business_lines=args.business_lines,
                session_name=session_name,
                project_key=config.dashboard.project_key,
            )
        delivery_summary = None
        try:
            release_result = export_month_to_dir(
                month=effective_month,
                month_dir=resolved_output_dir,
                output_root=release_deploy_output_root,
                project_key=release_deploy_project_key,
            )
        except (FileNotFoundError, RuntimeError):
            release_result = None
        if isinstance(release_result, dict):
            delivery_summary = {
                "overview": release_result.get("overview", {}),
                "top_risk_business_lines": release_result.get(
                    "top_risk_business_lines", []
                ),
                "focus_candidates": release_result.get("focus_candidates", {}),
            }
        if delivery_summary is None:
            delivery_summary = _load_cached_delivery_summary(
                release_deploy_output_root, effective_month
            )

        run_pipeline(
            period=effective_month,
            raw_records=raw_records,
            output_dir=resolved_output_dir,
            cumulative_raw_records=cumulative_raw_records,
            ai_insight_runner=_build_ai_insight_runner(config_path),
            dashboard_url=view_url,
            delivery_summary=delivery_summary,
            appendix_links=_build_appendix_links(),
        )
        export_trend(
            current_month=effective_month,
            previous_month=_previous_month(effective_month),
            output_root=release_deploy_output_root,
            trend_months=args.trend_months,
        )
    finally:
        if should_close_session:
            close_browser_session(session_name=session_name)
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_with_args(argv)
