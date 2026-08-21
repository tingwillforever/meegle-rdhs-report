from __future__ import annotations

import csv
import json
from pathlib import Path
import re
from typing import Any

import yaml

from shared.meego.business_lines import (
    BusinessLineDimension,
    EXCLUDED_LEVEL1_BUSINESS_LINES,
    fetch_business_dimensions,
)
from shared.meego.client import MeegoMCPClient
from impl.release_deploy_analyzer import build_business_summaries, build_overview
from impl.release_deploy_fetcher import fetch_release_plans
from impl.release_deploy_history_loader import load_monthly_summaries
from impl.release_deploy_models import (
    HistoryPaths,
    KubelinkConfig,
    MetricsConfig,
    OutputPaths,
    ReleasePlanDetail,
    TrendOutputPaths,
)
from impl.release_deploy_normalizer import (
    annotate_tasks_with_kubelink,
    build_release_plan_detail,
)
from impl.release_deploy_report_renderer import (
    render_analysis_report,
    render_monthly_operational_report,
    render_monthly_report_prompt,
    render_trend_report,
)
from impl.release_deploy_trend_analyzer import (
    compute_business_line_mom,
    identify_consistent_top_risks,
)


DEFAULT_METRICS_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "release_deploy_metrics.yaml"
)


def load_metrics_config(path: Path = DEFAULT_METRICS_CONFIG_PATH) -> MetricsConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    kubelink_payload = payload.get("kubelink", {}) or {}
    return MetricsConfig(
        project_key=str(payload.get("project_key", "cbg_product_develop")),
        kubelink=KubelinkConfig(
            mode=str(kubelink_payload.get("mode", "k8s_helm_signals")),
            rule_version=str(
                kubelink_payload.get("rule_version", "devops-k8s-helm-v1")
            ),
            match_fields=[
                str(field) for field in kubelink_payload.get("match_fields", []) or []
            ],
            keywords=[
                str(keyword) for keyword in kubelink_payload.get("keywords", []) or []
            ],
        ),
    )


def build_output_paths(output_root: Path, month: str) -> OutputPaths:
    base_dir = output_root / month
    return OutputPaths(
        base_dir=base_dir,
        release_plan_details_json=base_dir / "release_deploy_details.json",
        deploy_task_details_json=base_dir / "deploy_task_details.json",
        summary_csv=base_dir / "business_release_deploy_summary.csv",
        analysis_md=base_dir / "release_deploy_analysis.md",
        top_risk_csv=base_dir / "top_risk_business_lines.csv",
        insight_input_json=base_dir / "monthly_insight_input.json",
        report_prompt_md=base_dir / "monthly_report_prompt.md",
        operational_report_md=base_dir / "monthly_operational_report.md",
    )


def build_output_paths_for_month_dir(month_dir: Path) -> OutputPaths:
    return OutputPaths(
        base_dir=month_dir,
        release_plan_details_json=month_dir / "release_deploy_details.json",
        deploy_task_details_json=month_dir / "deploy_task_details.json",
        summary_csv=month_dir / "business_release_deploy_summary.csv",
        analysis_md=month_dir / "release_deploy_analysis.md",
        top_risk_csv=month_dir / "top_risk_business_lines.csv",
        insight_input_json=month_dir / "monthly_insight_input.json",
        report_prompt_md=month_dir / "monthly_report_prompt.md",
        operational_report_md=month_dir / "monthly_operational_report.md",
    )


def build_history_paths(output_root: Path) -> HistoryPaths:
    base_dir = output_root / "history"
    return HistoryPaths(
        base_dir=base_dir,
        release_plan_history_jsonl=base_dir / "release_plan_history.jsonl",
        deploy_task_history_jsonl=base_dir / "deploy_task_history.jsonl",
        business_summary_csv=base_dir / "business_line_monthly_summary.csv",
    )


def _write_details_json(path: Path, details: list[ReleasePlanDetail]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "release_plan_id": detail.release_plan_id,
            "name": detail.name,
            "business_line": detail.business_line,
            "level1_business_line": detail.level1_business_line,
            "level2_business_line": detail.level2_business_line,
            "created_at": detail.created_at,
            "release_plan_status": detail.release_plan_status,
            "deploy_task_count": detail.deploy_task_count,
            "deploy_status_counts": detail.deploy_status_counts,
            "kubelink_task_count": detail.kubelink_task_count,
            "deploy_tasks": detail.deploy_tasks,
        }
        for detail in details
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def flatten_deploy_task_details(
    month: str, project_key: str, details: list[ReleasePlanDetail]
) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for detail in details:
        for task in detail.deploy_tasks:
            flattened.append(
                {
                    "month": month,
                    "project_key": project_key,
                    "release_plan_id": detail.release_plan_id,
                    "release_plan_name": detail.name,
                    "business_line": detail.business_line,
                    "level1_business_line": detail.level1_business_line,
                    "level2_business_line": detail.level2_business_line,
                    "release_plan_created_at": detail.created_at,
                    "task_id": str(task.get("task_id") or task.get("id") or ""),
                    "deploy_status": str(
                        task.get("deploy_status") or task.get("status") or "未知状态"
                    ),
                    "app_name": str(task.get("app_name") or ""),
                    "cluster": str(task.get("cluster") or ""),
                    "namespace": str(task.get("namespace") or ""),
                    "artifact_package": str(task.get("artifact_package") or ""),
                    "create_time": str(task.get("create_time") or ""),
                    "update_time": str(task.get("update_time") or ""),
                    "is_kubelink_task": bool(task.get("is_kubelink_task")),
                    "kubelink_rule_version": str(
                        task.get("kubelink_rule_version") or ""
                    ),
                }
            )
    return flattened


def _write_deploy_task_details_json(
    path: Path, deploy_task_details: list[dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(deploy_task_details, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_summary_csv(
    path: Path,
    details: list[ReleasePlanDetail],
    business_dimensions: list[BusinessLineDimension] | None = None,
) -> None:
    summaries = sorted(
        [
            summary
            for summary in build_business_summaries(details, business_dimensions)
            if summary.level1_business_line not in EXCLUDED_LEVEL1_BUSINESS_LINES
        ],
        key=lambda summary: (
            -summary.released_plan_count,
            -(
                0.0
                if summary.release_plan_total == 0
                else round(
                    summary.released_plan_count * 100 / summary.release_plan_total,
                    1,
                )
            ),
            -summary.kubelink_release_penetration_rate,
            -(
                0.0
                if summary.deploy_completion_rate is None
                else summary.deploy_completion_rate
            ),
            summary.level1_business_line,
            summary.level2_business_line,
        ),
    )
    fieldnames = [
        "一级业务线",
        "二级业务线",
        "发布计划总数",
        "已发布计划数",
        "含部署的发布计划数",
        "发布完成率",
        "云原生渗透率",
        "部署任务总数",
        "部署任务完成率",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            release_completion_rate = (
                0.0
                if summary.release_plan_total == 0
                else round(
                    summary.released_plan_count * 100 / summary.release_plan_total,
                    1,
                )
            )
            deploy_completion_rate = (
                0.0
                if summary.deploy_completion_rate is None
                else summary.deploy_completion_rate
            )
            writer.writerow(
                {
                    "一级业务线": summary.level1_business_line,
                    "二级业务线": summary.level2_business_line,
                    "发布计划总数": summary.release_plan_total,
                    "已发布计划数": summary.released_plan_count,
                    "含部署的发布计划数": summary.release_plan_with_deploy_task_total,
                    "发布完成率": f"{release_completion_rate:.1f}%",
                    "云原生渗透率": f"{summary.kubelink_release_penetration_rate:.1f}%",
                    "部署任务总数": summary.deploy_task_total,
                    "部署任务完成率": f"{deploy_completion_rate:.1f}%",
                }
            )


def _write_analysis_md(
    path: Path,
    month: str,
    details_path: Path,
    summary_path: Path,
    details: list[ReleasePlanDetail],
) -> None:
    overview = build_overview(details)
    summaries = build_business_summaries(details)
    content = render_analysis_report(
        month=month,
        details_path=details_path,
        summary_path=summary_path,
        overview=overview,
        summaries=summaries,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _rank_summaries(summaries: list[Any]) -> list[Any]:
    return sorted(
        summaries,
        key=lambda summary: (
            -summary.risk_score,
            -summary.deploy_task_total,
            -summary.release_plan_total,
            summary.business_line,
        ),
    )


def _summary_to_dict(
    summary: Any, risk_rank: int | None = None, is_top_risk: bool | None = None
) -> dict[str, Any]:
    payload = {
        "business_line": summary.business_line,
        "level1_business_line": summary.level1_business_line,
        "level2_business_line": summary.level2_business_line,
        "release_plan_total": summary.release_plan_total,
        "release_plan_with_deploy_task_total": summary.release_plan_with_deploy_task_total,
        "digital_penetration_rate": summary.digital_penetration_rate,
        "release_plan_with_cloud_native_task_total": summary.release_plan_with_kubelink_task_total,
        "cloud_native_release_penetration_rate": summary.kubelink_release_penetration_rate,
        "deploy_task_total": summary.deploy_task_total,
        "deploy_completion_rate": summary.deploy_completion_rate,
        "deploy_termination_rate": summary.deploy_termination_rate,
        "risk_score": summary.risk_score,
        "released_plan_count": summary.released_plan_count,
    }
    if risk_rank is not None:
        payload["risk_rank"] = risk_rank
    if is_top_risk is not None:
        payload["is_top_risk"] = is_top_risk
    return payload


def _focus_candidates(
    summaries: list[Any], limit: int = 3
) -> dict[str, list[dict[str, Any]]]:
    termination_risk = sorted(
        summaries,
        key=lambda summary: (
            -summary.deploy_termination_rate,
            -summary.deploy_task_total,
            summary.business_line,
        ),
    )[:limit]
    kubelink_gap = sorted(
        summaries,
        key=lambda summary: (
            summary.kubelink_release_penetration_rate,
            -summary.release_plan_total,
            summary.business_line,
        ),
    )[:limit]
    return {
        "termination_risk": [_summary_to_dict(summary) for summary in termination_risk],
        "cloud_native_gap": [_summary_to_dict(summary) for summary in kubelink_gap],
    }


def build_monthly_insight_payload(
    month: str,
    project_key: str,
    release_plan_details_path: Path,
    deploy_task_details_path: Path,
    summary_path: Path,
    details: list[ReleasePlanDetail],
    business_dimensions: list[BusinessLineDimension] | None = None,
) -> dict[str, Any]:
    overview = build_overview(details)
    summaries = build_business_summaries(details, business_dimensions)
    ranked = _rank_summaries(summaries)
    risk_rank_map = {
        summary.business_line: index for index, summary in enumerate(ranked, start=1)
    }
    top_risks = []
    for summary in ranked[:5]:
        risk_rank = risk_rank_map[summary.business_line]
        top_risks.append(
            _summary_to_dict(
                summary,
                risk_rank=risk_rank,
                is_top_risk=summary.risk_score > 0 and risk_rank <= 3,
            )
        )

    return {
        "month": month,
        "project_key": project_key,
        "data_sources": {
            "release_plan_details": str(release_plan_details_path),
            "deploy_task_details": str(deploy_task_details_path),
            "business_summary": str(summary_path),
        },
        "overview": {
            "release_plan_total": overview.release_plan_total,
            "release_plan_with_deploy_task_total": overview.release_plan_with_deploy_task_total,
            "digital_penetration_rate": overview.digital_penetration_rate,
            "release_plan_with_cloud_native_task_total": overview.release_plan_with_kubelink_task_total,
            "cloud_native_release_penetration_rate": overview.kubelink_release_penetration_rate,
            "deploy_task_total": overview.deploy_task_total,
            "deploy_termination_rate": overview.deploy_termination_rate,
            "deploy_status_counts": overview.deploy_status_counts,
        },
        "top_risk_business_lines": top_risks,
        "focus_candidates": _focus_candidates(summaries),
        "business_summaries": [
            _summary_to_dict(
                summary,
                risk_rank=risk_rank_map[summary.business_line],
                is_top_risk=summary.risk_score > 0
                and risk_rank_map[summary.business_line] <= 3,
            )
            for summary in summaries
        ],
    }


def _write_top_risk_csv(path: Path, summaries: list[Any]) -> None:
    ranked = _rank_summaries(summaries)
    fieldnames = [
        "business_line",
        "risk_rank",
        "is_top_risk",
        "risk_score",
        "release_plan_total",
        "digital_penetration_rate",
        "cloud_native_release_penetration_rate",
        "deploy_task_total",
        "deploy_termination_rate",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for index, summary in enumerate(ranked[:10], start=1):
            writer.writerow(
                {
                    "business_line": summary.business_line,
                    "risk_rank": index,
                    "is_top_risk": "true"
                    if summary.risk_score > 0 and index <= 3
                    else "false",
                    "risk_score": summary.risk_score,
                    "release_plan_total": summary.release_plan_total,
                    "digital_penetration_rate": summary.digital_penetration_rate,
                    "cloud_native_release_penetration_rate": summary.kubelink_release_penetration_rate,
                    "deploy_task_total": summary.deploy_task_total,
                    "deploy_termination_rate": summary.deploy_termination_rate,
                }
            )


def _write_monthly_insight_input_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _month_sort_key(path: Path) -> str:
    return path.name


def _is_month_directory(path: Path) -> bool:
    return path.is_dir() and re.match(r"^\d{4}-\d{2}$", path.name) is not None


def _release_plan_detail_from_payload(
    payload: dict[str, Any], kubelink_config: KubelinkConfig | None = None
) -> ReleasePlanDetail:
    deploy_tasks = list(payload.get("deploy_tasks", []) or [])
    if deploy_tasks and (
        any("is_kubelink_task" not in task for task in deploy_tasks)
        or any("kubelink_rule_version" not in task for task in deploy_tasks)
        or (
            kubelink_config is not None
            and any(
                str(task.get("kubelink_rule_version", ""))
                != kubelink_config.rule_version
                for task in deploy_tasks
            )
        )
    ):
        deploy_tasks = annotate_tasks_with_kubelink(deploy_tasks, kubelink_config)

    kubelink_task_count = payload.get("kubelink_task_count")
    if kubelink_task_count is None:
        kubelink_task_count = sum(
            1 for task in deploy_tasks if task.get("is_kubelink_task")
        )
    return ReleasePlanDetail(
        release_plan_id=int(payload.get("release_plan_id") or payload.get("id") or 0),
        name=str(payload.get("name", "")),
        business_line=str(payload.get("business_line", "未填写业务线")),
        created_at=str(payload.get("created_at", "")),
        level1_business_line=str(
            payload.get("level1_business_line")
            or payload.get("business_line", "未填写业务线")
        ),
        level2_business_line=str(payload.get("level2_business_line", "")),
        release_plan_status=str(payload.get("release_plan_status", "")),
        deploy_task_count=int(payload.get("deploy_task_count", 0)),
        deploy_status_counts={
            str(key): int(value)
            for key, value in (payload.get("deploy_status_counts", {}) or {}).items()
        },
        deploy_tasks=deploy_tasks,
        kubelink_task_count=int(kubelink_task_count),
    )


def _load_month_release_details(
    path: Path, kubelink_config: KubelinkConfig | None = None
) -> list[ReleasePlanDetail]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        _release_plan_detail_from_payload(item, kubelink_config) for item in payload
    ]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def _write_history_summary_csv(
    path: Path,
    monthly_details: list[tuple[str, list[ReleasePlanDetail]]],
    business_dimensions: list[BusinessLineDimension] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "month",
        "level1_business_line",
        "level2_business_line",
        "business_line",
        "release_plan_total",
        "released_plan_count",
        "release_plan_with_deploy_task_total",
        "digital_penetration_rate",
        "release_plan_with_cloud_native_task_total",
        "cloud_native_release_penetration_rate",
        "deploy_task_total",
        "deploy_termination_rate",
        "risk_score",
        "risk_rank",
        "is_top_risk",
        "deploy_completion_rate",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for month, details in monthly_details:
            summaries = build_business_summaries(details, business_dimensions)
            ranked = _rank_summaries(summaries)
            risk_rank_map = {
                summary.business_line: index
                for index, summary in enumerate(ranked, start=1)
            }
            for summary in summaries:
                risk_rank = risk_rank_map[summary.business_line]
                writer.writerow(
                    {
                        "month": month,
                        "level1_business_line": summary.level1_business_line,
                        "level2_business_line": summary.level2_business_line,
                        "business_line": summary.business_line,
                        "release_plan_total": summary.release_plan_total,
                        "released_plan_count": summary.released_plan_count,
                        "release_plan_with_deploy_task_total": summary.release_plan_with_deploy_task_total,
                        "digital_penetration_rate": summary.digital_penetration_rate,
                        "release_plan_with_cloud_native_task_total": summary.release_plan_with_kubelink_task_total,
                        "cloud_native_release_penetration_rate": summary.kubelink_release_penetration_rate,
                        "deploy_task_total": summary.deploy_task_total,
                        "deploy_termination_rate": summary.deploy_termination_rate,
                        "risk_score": summary.risk_score,
                        "risk_rank": risk_rank,
                        "is_top_risk": "true"
                        if summary.risk_score > 0 and risk_rank <= 3
                        else "false",
                        "deploy_completion_rate": ""
                        if summary.deploy_completion_rate is None
                        else summary.deploy_completion_rate,
                    }
                )


def rebuild_history_from_monthly_outputs(
    output_root: Path,
    project_key: str = "cbg_product_develop",
    client: MeegoMCPClient | None = None,
) -> HistoryPaths:
    metrics_config = load_metrics_config()
    history_paths = build_history_paths(output_root)
    mcp_client = client or MeegoMCPClient(project_key=project_key)
    business_dimensions = fetch_business_dimensions(mcp_client)
    release_history_rows: list[dict[str, Any]] = []
    deploy_history_rows: list[dict[str, Any]] = []
    monthly_details: list[tuple[str, list[ReleasePlanDetail]]] = []

    month_dirs = (
        sorted(
            (path for path in output_root.iterdir() if _is_month_directory(path)),
            key=_month_sort_key,
        )
        if output_root.exists()
        else []
    )
    for month_dir in month_dirs:
        month = month_dir.name
        release_details_path = month_dir / "release_deploy_details.json"
        if not release_details_path.exists():
            continue
        details = _load_month_release_details(
            release_details_path, metrics_config.kubelink
        )
        monthly_details.append((month, details))
        for detail in details:
            release_history_rows.append(
                {
                    "month": month,
                    "release_plan_id": detail.release_plan_id,
                    "name": detail.name,
                    "business_line": detail.business_line,
                    "level1_business_line": detail.level1_business_line,
                    "level2_business_line": detail.level2_business_line,
                    "created_at": detail.created_at,
                    "release_plan_status": detail.release_plan_status,
                    "deploy_task_count": detail.deploy_task_count,
                    "kubelink_task_count": detail.kubelink_task_count,
                    "deploy_status_counts": detail.deploy_status_counts,
                }
            )

        deploy_task_details_path = month_dir / "deploy_task_details.json"
        if deploy_task_details_path.exists():
            deploy_history_rows.extend(
                json.loads(deploy_task_details_path.read_text(encoding="utf-8"))
            )
        else:
            deploy_history_rows.extend(
                flatten_deploy_task_details(
                    month=month, project_key="", details=details
                )
            )

    _write_jsonl(history_paths.release_plan_history_jsonl, release_history_rows)
    _write_jsonl(history_paths.deploy_task_history_jsonl, deploy_history_rows)
    _write_history_summary_csv(
        history_paths.business_summary_csv, monthly_details, business_dimensions
    )
    return history_paths


def export_month_to_dir(
    month: str,
    month_dir: Path,
    output_root: Path,
    project_key: str = "cbg_product_develop",
    client: MeegoMCPClient | None = None,
) -> dict[str, Any]:
    metrics_config = load_metrics_config()
    mcp_client = client or MeegoMCPClient(project_key=project_key)
    business_dimensions = fetch_business_dimensions(mcp_client)
    business_dimension_map = {
        dimension.business_line: dimension for dimension in business_dimensions
    }
    release_plans = fetch_release_plans(mcp_client, month)
    details: list[ReleasePlanDetail] = []
    for work_item in release_plans:
        release_plan_id = int(work_item.get("work_item_id") or work_item.get("id"))
        task_payload = mcp_client.call_tool(
            "list_deploy_tasks", {"release_id": str(release_plan_id)}
        )
        details.append(
            build_release_plan_detail(
                work_item,
                task_payload,
                metrics_config.kubelink,
                business_dimension_map,
            )
        )

    paths = build_output_paths_for_month_dir(month_dir)
    summaries = build_business_summaries(details, business_dimensions)
    _write_details_json(paths.release_plan_details_json, details)
    _write_deploy_task_details_json(
        paths.deploy_task_details_json,
        flatten_deploy_task_details(month, project_key, details),
    )
    _write_summary_csv(paths.summary_csv, details, business_dimensions)
    _write_analysis_md(
        paths.analysis_md,
        month,
        paths.release_plan_details_json,
        paths.summary_csv,
        details,
    )
    _write_top_risk_csv(paths.top_risk_csv, summaries)
    _write_monthly_insight_input_json(
        paths.insight_input_json,
        build_monthly_insight_payload(
            month=month,
            project_key=project_key,
            release_plan_details_path=paths.release_plan_details_json,
            deploy_task_details_path=paths.deploy_task_details_json,
            summary_path=paths.summary_csv,
            details=details,
            business_dimensions=business_dimensions,
        ),
    )
    insight_payload = json.loads(paths.insight_input_json.read_text(encoding="utf-8"))
    _write_markdown(
        paths.report_prompt_md, render_monthly_report_prompt(insight_payload)
    )
    _write_markdown(
        paths.operational_report_md, render_monthly_operational_report(insight_payload)
    )
    rebuild_history_from_monthly_outputs(
        output_root, project_key=project_key, client=mcp_client
    )
    return {
        "paths": paths,
        "overview": insight_payload.get("overview", {}),
        "top_risk_business_lines": insight_payload.get("top_risk_business_lines", []),
        "focus_candidates": insight_payload.get("focus_candidates", {}),
    }


def build_trend_output_paths(output_root: Path, month: str) -> TrendOutputPaths:
    base_dir = output_root / month
    return TrendOutputPaths(
        base_dir=base_dir,
        trend_analysis_md=base_dir / "trend_analysis.md",
        business_line_mom_csv=base_dir / "business_line_mom.csv",
        rolling_risk_summary_csv=base_dir / "rolling_risk_summary.csv",
    )


def _write_mom_csv(path: Path, mom_data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "business_line",
        "current_month",
        "previous_month",
        "current_risk_score",
        "previous_risk_score",
        "risk_score_mom",
        "release_plan_total_mom",
        "deploy_task_total_mom",
        "digital_penetration_rate_mom",
        "deploy_termination_rate_mom",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in mom_data:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _write_rolling_risk_csv(path: Path, rolling_risks: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "business_line",
        "months_in_top_risk",
        "avg_risk_score",
        "max_risk_score",
        "months",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rolling_risks:
            row_data = {k: row.get(k, "") for k in fieldnames}
            if isinstance(row_data.get("months"), list):
                row_data["months"] = ", ".join(row_data["months"])
            writer.writerow(row_data)


def _aggregate_monthly_overview(
    summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    months_data: dict[str, dict[str, Any]] = {}
    for s in summaries:
        month = s.get("month", "")
        if not month:
            continue
        if month not in months_data:
            months_data[month] = {
                "month": month,
                "release_plan_total": 0,
                "released_plan_count": 0,
                "deploy_task_total": 0,
                "release_plan_with_kubelink_task_total": 0,
                "deploy_termination_count": 0,
                "deploy_task_count_with_data": 0,
            }
        months_data[month]["release_plan_total"] += int(
            s.get("release_plan_total", 0) or 0
        )
        months_data[month]["released_plan_count"] += int(
            s.get("released_plan_count", 0) or 0
        )
        months_data[month]["deploy_task_total"] += int(
            s.get("deploy_task_total", 0) or 0
        )
        months_data[month]["release_plan_with_kubelink_task_total"] += int(
            s.get("release_plan_with_cloud_native_task_total", 0) or 0
        )
        termination_rate = float(s.get("deploy_termination_rate", 0) or 0)
        deploy_total = int(s.get("deploy_task_total", 0) or 0)
        if deploy_total > 0:
            termination_count = int(deploy_total * termination_rate / 100)
            months_data[month]["deploy_termination_count"] += termination_count
            months_data[month]["deploy_task_count_with_data"] += deploy_total

    result = []
    for month, data in months_data.items():
        kubelink_rate = (
            data["release_plan_with_kubelink_task_total"]
            / data["release_plan_total"]
            * 100
            if data["release_plan_total"] > 0
            else 0
        )
        termination_rate = (
            data["deploy_termination_count"] / data["deploy_task_count_with_data"] * 100
            if data["deploy_task_count_with_data"] > 0
            else 0
        )
        result.append(
            {
                "month": month,
                "release_plan_total": data["release_plan_total"],
                "released_plan_count": data["released_plan_count"],
                "kubelink_release_penetration_rate": kubelink_rate,
                "deploy_task_total": data["deploy_task_total"],
                "deploy_termination_rate": termination_rate,
            }
        )
    return result


def export_trend(
    current_month: str,
    previous_month: str,
    output_root: Path,
    trend_months: int = 3,
) -> TrendOutputPaths | None:
    history_paths = build_history_paths(output_root)
    if not history_paths.business_summary_csv.exists():
        return None
    summaries = load_monthly_summaries(
        history_paths.business_summary_csv, [current_month, previous_month]
    )
    if not summaries:
        return None
    mom_data = compute_business_line_mom(summaries, current_month, previous_month)
    all_summaries = load_monthly_summaries(history_paths.business_summary_csv, [])
    rolling_risks = identify_consistent_top_risks(
        all_summaries, min_months=trend_months
    )
    monthly_overview = _aggregate_monthly_overview(all_summaries)
    paths = build_trend_output_paths(output_root, current_month)
    _write_mom_csv(paths.business_line_mom_csv, mom_data)
    _write_rolling_risk_csv(paths.rolling_risk_summary_csv, rolling_risks)
    _write_markdown(
        paths.trend_analysis_md,
        render_trend_report(
            current_month, previous_month, mom_data, rolling_risks, monthly_overview
        ),
    )
    return paths
