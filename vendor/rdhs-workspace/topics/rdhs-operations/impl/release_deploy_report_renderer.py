from __future__ import annotations

from pathlib import Path
from typing import Any

from impl.release_deploy_models import BusinessSummary, Overview


def _format_rate(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}%"


def render_analysis_report(
    month: str,
    details_path: Path,
    summary_path: Path,
    overview: Overview,
    summaries: list[BusinessSummary],
) -> str:
    lines: list[str] = [
        f"# {month} 发布计划与部署任务分析",
        "",
        f"**统计范围**：`{month}-01 00:00:00` 至 `下月1日 00:00:00`  ",
        "**发布计划时间口径**：`创建时间(秒)`  ",
        "**数据来源**：",
        f"- `{details_path}`",
        f"- `{summary_path}`",
        "",
        "## 一、口径说明",
        "- 部署任务状态按正式部署状态枚举统计",
        "- `orchestration_status` 不作为部署状态统计口径",
        "- 发布计划状态统计：`已完成` 状态即为 `已发布`",
        "",
        "## 二、整体情况",
        f"- 发布计划总数：`{overview.release_plan_total}`",
        f"- 已发布发布计划数：`{overview.released_plan_count}`",
        f"- 含部署任务的发布计划数：`{overview.release_plan_with_kubelink_task_total}`",
        f"- 云原生渗透率：`{_format_rate(overview.kubelink_release_penetration_rate)}`",
        f"- 部署任务总数：`{overview.deploy_task_total}`",
    ]
    for status, count in overview.deploy_status_counts.items():
        lines.append(f"- {status}：`{count}`")
    lines.extend(
        [
            "",
            "## 三、各业务线分析",
            "",
            "| 业务线 | 发布计划总数 | 已发布 | 含部署任务的发布计划数 | 云原生渗透率 | 部署任务总数 | 部署完成 | 部署中 | 部署终止 | 部署完成率 | 部署终止率 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in summaries:
        lines.append(
            "| {business} | {plans} | {released} | {with_kubelink} | {kubelink_penetration} | {task_total} | {done} | {running} | {terminated} | {completion} | {termination} |".format(
                business=summary.business_line,
                plans=summary.release_plan_total,
                released=summary.released_plan_count,
                with_kubelink=summary.release_plan_with_kubelink_task_total,
                kubelink_penetration=_format_rate(
                    summary.kubelink_release_penetration_rate
                ),
                task_total=summary.deploy_task_total,
                done=summary.deploy_status_counts.get("部署完成", 0),
                running=summary.deploy_status_counts.get("部署中", 0),
                terminated=summary.deploy_status_counts.get("部署终止", 0),
                completion=_format_rate(summary.deploy_completion_rate),
                termination=_format_rate(summary.deploy_termination_rate),
            )
        )
    return "\n".join(lines) + "\n"


def render_monthly_report_prompt(payload: dict[str, Any]) -> str:
    top_risks = payload.get("top_risk_business_lines", [])
    risk_lines = (
        "\n".join(
            f"- {item['business_line']}（risk_rank={item.get('risk_rank')}, risk_score={item.get('risk_score')}）"
            for item in top_risks[:5]
        )
        or "- 暂无高风险业务线"
    )

    lines = [
        f"# {payload['month']} 月度运营报告生成提示词",
        "",
        "## 背景",
        f"- 项目：`{payload.get('project_key', '')}`",
        f"- 发布计划明细：`{payload['data_sources']['release_plan_details']}`",
        f"- 部署任务明细：`{payload['data_sources']['deploy_task_details']}`",
        f"- 业务线汇总：`{payload['data_sources']['business_summary']}`",
        "",
        "## 本月总览",
        f"- 发布计划总数：`{payload['overview']['release_plan_total']}`",
        f"- 发布数字化渗透率：`{payload['overview']['digital_penetration_rate']}`",
        f"- 云原生发布计划渗透率：`{payload['overview']['cloud_native_release_penetration_rate']}`",
        f"- 部署任务总数：`{payload['overview']['deploy_task_total']}`",
        f"- 部署终止率：`{payload['overview']['deploy_termination_rate']}`",
        "",
        "## 高风险业务线",
        risk_lines,
        "",
        "## 输出要求",
        "请基于输入数据生成一份月度运营报告，至少包含：",
        "1. 本月整体趋势概览",
        "2. Top 风险业务线及原因",
        "3. 数字化/云原生 机会点",
        "4. 下月建议动作，要求可执行、可跟踪",
    ]
    return "\n".join(lines) + "\n"


def render_trend_report(
    current_month: str,
    previous_month: str,
    mom_data: list[dict[str, Any]],
    rolling_risks: list[dict[str, Any]],
    monthly_summaries: list[dict[str, Any]] | None = None,
) -> str:
    lines: list[str] = [
        f"# {current_month} 趋势分析报告",
        "",
        f"**对比月份**：`{previous_month}` -> `{current_month}`",
    ]

    if monthly_summaries:
        lines.extend(
            [
                "",
                "## 一、整体累计趋势",
                "",
                "| 月份 | 发布计划总数 | 已发布 | 云原生渗透率 | 部署任务总数 | 部署终止率 |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for summary in sorted(monthly_summaries, key=lambda x: x.get("month", "")):
            lines.append(
                "| {month} | {plans} | {released} | {kubelink} | {tasks} | {termination} |".format(
                    month=summary.get("month", ""),
                    plans=summary.get("release_plan_total", 0),
                    released=summary.get("released_plan_count", 0),
                    kubelink=_format_rate(
                        summary.get("kubelink_release_penetration_rate")
                    ),
                    tasks=summary.get("deploy_task_total", 0),
                    termination=_format_rate(summary.get("deploy_termination_rate")),
                )
            )

    lines.extend(
        [
            "",
            "## 二、业务线环比变化",
            "",
            "| 业务线 | 风险分环比 | 发布计划环比 | 部署任务环比 | 云原生渗透率环比 | 终止率环比 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in mom_data:
        lines.append(
            "| {business} | {risk_mom} | {plan_mom} | {task_mom} | {kubelink_mom} | {term_mom} |".format(
                business=row.get("business_line", ""),
                risk_mom=row.get("risk_score_mom", 0),
                plan_mom=row.get("release_plan_total_mom", 0),
                task_mom=row.get("deploy_task_total_mom", 0),
                kubelink_mom=row.get("kubelink_release_penetration_rate_mom", 0),
                term_mom=row.get("deploy_termination_rate_mom", 0),
            )
        )
    lines.extend(
        [
            "",
            "## 三、持续高风险业务线",
            "",
            "| 业务线 | 高风险月数 | 平均风险分 | 最高风险分 | 月份列表 |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for row in rolling_risks:
        months_str = ", ".join(row.get("months", []))
        lines.append(
            "| {business} | {months_count} | {avg_risk} | {max_risk} | {months} |".format(
                business=row.get("business_line", ""),
                months_count=row.get("months_in_top_risk", 0),
                avg_risk=row.get("avg_risk_score", 0),
                max_risk=row.get("max_risk_score", 0),
                months=months_str,
            )
        )
    lines.extend(
        [
            "",
            "## 四、趋势洞察",
            "- 重点关注风险分环比上升的业务线",
            "- 持续高风险业务线需建立专项治理清单",
        ]
    )
    return "\n".join(lines) + "\n"


def render_monthly_operational_report(payload: dict[str, Any]) -> str:
    overview = payload["overview"]
    top_risks = payload.get("top_risk_business_lines", [])
    focus_candidates = payload.get("focus_candidates", {})

    lines = [
        f"# {payload['month']} 发布部署月度运营报告（初稿）",
        "",
        "## 一、本月总览",
        f"- 发布计划总数：`{overview['release_plan_total']}`",
        f"- 含云原生任务发布计划数：`{overview['release_plan_with_cloud_native_task_total']}`",
        f"- 云原生渗透率：`{overview['cloud_native_release_penetration_rate']}`",
        f"- 部署任务总数：`{overview['deploy_task_total']}`",
        f"- 部署终止率：`{overview['deploy_termination_rate']}`",
        "",
        "## 二、重点风险业务线",
    ]
    if top_risks:
        for item in top_risks[:5]:
            lines.append(
                "- {business}: risk_score={score}, 云原生率={kubelink}, 终止率={termination}".format(
                    business=item["business_line"],
                    score=item.get("risk_score"),
                    kubelink=item.get("cloud_native_release_penetration_rate"),
                    termination=item.get("deploy_termination_rate"),
                )
            )
    else:
        lines.append("- 暂无重点风险业务线")

    lines.extend(
        [
            "",
            "## 三、关注点",
            "### 云原生缺口",
        ]
    )
    for item in focus_candidates.get("cloud_native_gap", [])[:3]:
        lines.append(
            f"- {item['business_line']}: 云原生率={item.get('cloud_native_release_penetration_rate')}"
        )
    lines.append("")
    lines.append("### 终止风险")
    for item in focus_candidates.get("termination_risk", [])[:3]:
        lines.append(
            f"- {item['business_line']}: 终止率={item.get('deploy_termination_rate')}"
        )

    lines.extend(
        [
            "",
            "## 四、建议动作",
            "- 对 Top 风险业务线逐一确认未接入云原生部署的真实原因，区分口径缺失与流程未接入。",
            "- 对存在部署终止的业务线复盘终止原因，优先收敛高频失败场景。",
            "- 对云原生率为 0 的业务线建立专项迁移清单，按月跟踪关闭。",
        ]
    )
    return "\n".join(lines) + "\n"
