from __future__ import annotations


def _business_line_label(level_1: str, level_2: str) -> str:
    return f"{level_1} / {level_2 or '(空)'}"


def _format_period_label(period: str) -> str:
    year, month = period.split("-")
    return f"{year} 年 {int(month)} 月"


def _format_rate(value: object) -> str:
    if value in ("", None):
        return "-"
    return f"{float(value):.1f}%"


def _format_number(value: object) -> str:
    if value in ("", None):
        return "-"
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}"


def _format_percent_point(value: object) -> str:
    if value in ("", None):
        return "-"
    return f"{float(value):.1f}%"


def _render_generic_table(
    lines: list[str],
    *,
    title: str,
    headers: list[str],
    rows: list[dict[str, object]],
) -> None:
    if not headers or not rows:
        return
    lines.extend(
        [
            "",
            f"### {title}",
            "",
            f"| {' | '.join(headers)} |",
            f"| {' | '.join(['---'] * len(headers))} |",
        ]
    )
    for row in rows:
        values = [str(row.get(header, "")) for header in headers]
        lines.append(f"| {' | '.join(values)} |")


def _take_text_items(items: object, limit: int) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item) for item in items if str(item).strip()][:limit]


def _join_text_items(items: object, limit: int = 2) -> str:
    return "；".join(_take_text_items(items, limit))


def _render_rdhs_table(
    lines: list[str], rows: list[dict[str, object]], title: str
) -> None:
    lines.extend(
        [
            f"### {title}",
            "",
            "| 一级业务线 | 二级业务线 | RDHS(100') | 链路闭环情况(25') | 发布连续性 (15') | 时效节奏合理性 (20') | 颗粒度对齐度 (20') | 质量管理得分 (20') |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['level_1']} | {row['level_2']} | {row['rdhs_score']} | {row['link_score']} | {row['release_score']} | {row['timeliness_score']} | {row['granularity_score']} | {row['quality_score']} |"
        )


def _render_core_metrics_table(
    lines: list[str], rows: list[dict[str, object]], title: str = "核心结果指标"
) -> None:
    lines.extend(
        [
            "",
            f"### {title}",
            "",
            "| 一级业务线 | 二级业务线 | 月均需求吞吐量 | 需求交付周期 (天) | 需求开发周期(天) | 月均缺陷关闭量 | 严重缺陷占比 | 低级缺陷占比 | 月均发布频率 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['level_1']} | {row['level_2']} | {row['monthly_requirement_throughput']} | {row['avg_delivery_cycle_days']} | {row['avg_dev_cycle_days']} | {row['monthly_bug_closed']} | {row['serious_bug_rate']} | {row['easy_detect_bug_rate']} | {row['monthly_release_frequency']} |"
        )


def _render_delivery_detail_table(
    lines: list[str], rows: list[dict[str, object]]
) -> None:
    if not rows:
        return
    lines.extend(
        [
            "",
            "### 交付能力明细",
            "",
            "| 一级业务线 | 二级业务线 | 发布计划数 | 接入部署任务计划数 | 数字化率 | 云原生渗透率 | 部署任务数 | 部署终止率 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| {level_1} | {level_2} | {plans} | {deploy_plans} | {digital_rate} | {cloud_rate} | {deploy_tasks} | {termination_rate} |".format(
                level_1=row.get("level1_business_line", ""),
                level_2=row.get("level2_business_line", "") or "(空)",
                plans=_format_number(row.get("release_plan_total", 0)),
                deploy_plans=_format_number(
                    row.get("release_plan_with_deploy_task_total", 0)
                ),
                digital_rate=_format_rate(row.get("digital_penetration_rate", 0.0)),
                cloud_rate=_format_rate(
                    row.get("cloud_native_release_penetration_rate", 0.0)
                ),
                deploy_tasks=_format_number(row.get("deploy_task_total", 0)),
                termination_rate=_format_rate(row.get("deploy_termination_rate", 0.0)),
            )
        )


def _render_detail_appendix(
    lines: list[str],
    *,
    integrated_rows: list[dict[str, object]],
    backlog_section: dict[str, object],
    delivery_summary: dict[str, object],
) -> None:
    lines.extend(["", "## 三、明细数据附录", ""])
    lines.append("> 以下明细用于一线业务线定位自身问题与改进动作，结构化数据仍同步保留在 JSON/CSV 产物中。")

    if integrated_rows:
        _render_rdhs_table(lines, integrated_rows, "RDHS月度明细")
        _render_core_metrics_table(lines, integrated_rows, "核心结果指标明细")

    _render_generic_table(
        lines,
        title="积压需求明细",
        headers=list(backlog_section.get("headers", [])),
        rows=list(backlog_section.get("rows", [])),
    )

    _render_delivery_detail_table(
        lines, list(delivery_summary.get("business_summaries", []))
    )


def _render_honor_board(lines: list[str], honor_board: dict[str, object]) -> None:
    lines.extend(["## 产研过程效能红黑榜", ""])
    red_board = honor_board.get("red_board", [])
    if red_board:
        red_names = [
            _business_line_label(item["level_1"], item["level_2"])
            for item in red_board[:3]
        ]
        suffix = "，其余见结构化明细" if len(red_board) > 3 else ""
        lines.append(f"- 红榜：{'；'.join(red_names)}{suffix}。")
    else:
        lines.append("- 红榜：暂无。")

    black_board = honor_board.get("black_board", [])
    if black_board:
        black_names = [
            _business_line_label(item["level_1"], item["level_2"])
            for item in black_board[:3]
        ]
        suffix = "，其余见结构化明细" if len(black_board) > 3 else ""
        lines.append(f"- 黑榜：{'；'.join(black_names)}{suffix}。")
    else:
        lines.append("- 黑榜：暂无。")


def _render_management_summary(lines: list[str], management_summary: dict[str, object]) -> None:
    headline_judgements = management_summary.get("headline_judgements", [])
    next_month_actions = management_summary.get("next_month_actions", [])
    if not headline_judgements and not next_month_actions:
        return

    lines.extend(["## 首页摘要", ""])
    if headline_judgements:
        lines.extend(["### 本月关键判断"])
        for item in headline_judgements:
            lines.append(f"- {item}")
        lines.append("")

    if next_month_actions:
        lines.extend(["### 下月优先动作"])
        for item in next_month_actions:
            lines.append(f"- {item}")
        lines.append("")


def _render_focus_and_recommendations(
    lines: list[str],
    *,
    problem_items: object,
    recommendations_by_role: dict[str, object],
    problem_limit: int = 2,
    recommendation_limit: int = 2,
) -> None:
    focused_problems = _take_text_items(problem_items, problem_limit)
    if focused_problems:
        lines.extend(["", "### 问题聚焦"])
        for item in focused_problems:
            lines.append(f"- {item}")

    role_order = (
        ("business_line", "业务线"),
        ("platform_owner", "平台侧"),
        ("management", "管理层"),
    )
    recommendations: list[str] = []
    for role_key, role_label in role_order:
        for item in _take_text_items(recommendations_by_role.get(role_key, []), 2):
            recommendations.append(f"{role_label}：{item}")

    if recommendations:
        lines.extend(["", "### 改进建议"])
        for item in recommendations[:recommendation_limit]:
            lines.append(f"- {item}")


def _render_backlog_section(
    lines: list[str], backlog_section: dict[str, object]
) -> None:
    lines.extend(["", "### 积压需求分布"])
    summary_lines = backlog_section.get("summary_lines", [])
    for item in summary_lines:
        lines.append(f"- {item}")

    if backlog_section.get("data_available"):
        count = backlog_section.get("backlog_high_count")
        ratio = backlog_section.get("backlog_high_ratio")
        if count not in ("", None):
            lines.append(
                f"- 积压偏高业务线数：{_format_number(count)}，占比 {_format_percent_point(ratio)}"
            )
    else:
        lines.append("- 当前未加载积压需求图表明细，暂不输出积压占比结论。")

    zero_throughput_lines = backlog_section.get("zero_throughput_with_bug_lines", [])
    if zero_throughput_lines:
        samples = _take_text_items(zero_throughput_lines, 3)
        suffix = " 等" if len(zero_throughput_lines) > len(samples) else ""
        lines.append(f"- 指标背离样本：{'；'.join(samples)}{suffix}")

    rows = list(backlog_section.get("rows", []))
    _render_generic_table(
        lines,
        title="积压需求重点样本",
        headers=list(backlog_section.get("headers", [])),
        rows=rows[:3],
    )
    if len(rows) > 3:
        lines.append(f"- 已展示积压占比较高的 3 条，完整明细见结构化产物。")


def _render_business_line_spotlights(
    lines: list[str], spotlight_section: dict[str, object]
) -> None:
    priority_improvement = spotlight_section.get("priority_improvement", [])
    benchmark_cases = spotlight_section.get("benchmark_cases", [])
    if not priority_improvement and not benchmark_cases:
        return

    lines.extend(["", "### 重点业务线说明"])
    for title, items in (
        ("重点提升", priority_improvement[:1]),
        ("样板复制", benchmark_cases[:1]),
    ):
        if not items:
            continue
        lines.extend(["", f"#### {title}"])
        for item in items:
            parts = []
            problems = _join_text_items(item.get("problems", []), 2)
            if problems:
                parts.append(problems)
            actions = _join_text_items(item.get("actions", []), 2)
            if actions:
                parts.append(f"动作：{actions}")
            benchmark_reference = item.get("benchmark_reference", "")
            if benchmark_reference and title == "样板复制":
                parts.append(f"参考：{benchmark_reference}")
            content = "；".join(part for part in parts if part)
            headline = str(item.get("headline", "")).strip()
            if content:
                lines.append(f"- {item.get('business_line', '')}：{headline}（{content}）")
            else:
                lines.append(f"- {item.get('business_line', '')}：{headline}")


def _render_delivery_section(
    lines: list[str],
    delivery_summary: dict[str, object],
    ai_insights: dict[str, object],
    spotlights: dict[str, object] | None = None,
) -> None:
    overview = delivery_summary.get("overview", {})
    top_risks = delivery_summary.get("top_risk_business_lines", [])
    focus_candidates = delivery_summary.get("focus_candidates", {})
    business_summaries = delivery_summary.get("business_summaries", [])
    recommendations = ai_insights.get("section_recommendations", {})
    delivery_recommendations_by_role = recommendations.get("delivery_capability", {})
    if delivery_recommendations_by_role == recommendations.get("rdhs_collaboration"):
        delivery_recommendations_by_role = {}

    lines.extend(["", "## 二、交付能力", ""])
    if overview:
        lines.extend(
            [
                "> 发布能力章节聚焦发布计划数字化、云原生接入与部署终止风险，作为 RDHS 之外的交付补充视角。",
                "",
                "### 交付能力摘要",
                f"- 发布计划 {_format_number(overview.get('release_plan_total', 0))} 个，已接入部署任务 {_format_number(overview.get('release_plan_with_deploy_task_total', 0))} 个，数字化率 {_format_rate(overview.get('digital_penetration_rate', 0.0))}；云原生渗透率 {_format_rate(overview.get('cloud_native_release_penetration_rate', 0.0))}。",
                f"- 部署任务 {_format_number(overview.get('deploy_task_total', 0))} 个，部署终止率 {_format_rate(overview.get('deploy_termination_rate', 0.0))}。",
            ]
        )
    else:
        lines.append("- 当前交付能力摘要尚未生成。")

    if top_risks:
        lines.extend(["", "### 重点风险业务线"])
        for item in top_risks[:2]:
            risk_rank = item.get("risk_rank")
            lines.append(
                "- {prefix}{business}：发布计划 {plans} 个，部署任务 {tasks} 个，云原生渗透率 {cloud_native_rate}，部署终止率 {termination_rate}。".format(
                    prefix=f"TOP{risk_rank} " if risk_rank else "",
                    business=item.get("business_line", ""),
                    plans=_format_number(item.get("release_plan_total", 0)),
                    tasks=_format_number(item.get("deploy_task_total", 0)),
                    cloud_native_rate=_format_rate(
                        item.get("cloud_native_release_penetration_rate", 0.0)
                    ),
                    termination_rate=_format_rate(
                        item.get("deploy_termination_rate", 0.0)
                    ),
                )
            )

    if focus_candidates:
        for item in focus_candidates.get("cloud_native_gap", [])[:1]:
            lines.append(
                "- 云原生接入缺口：{business} | 发布计划 {plans} 个，云原生渗透率 {rate}".format(
                    business=item.get("business_line", ""),
                    plans=_format_number(item.get("release_plan_total", 0)),
                    rate=_format_rate(
                        item.get("cloud_native_release_penetration_rate", 0.0)
                    ),
                )
            )
        for item in focus_candidates.get("termination_risk", [])[:1]:
            lines.append(
                "- 部署终止风险：{business} | 部署任务 {tasks} 个，终止率 {rate}".format(
                    business=item.get("business_line", ""),
                    tasks=_format_number(item.get("deploy_task_total", 0)),
                    rate=_format_rate(item.get("deploy_termination_rate", 0.0)),
                )
            )

    delivery_problem_analysis = ai_insights.get("section_problem_analysis", {}).get(
        "delivery_capability", []
    )
    _render_focus_and_recommendations(
        lines,
        problem_items=delivery_problem_analysis,
        recommendations_by_role=delivery_recommendations_by_role,
    )

    _render_business_line_spotlights(lines, spotlights or {})


def _render_appendix_section(lines: list[str], appendix: dict[str, object]) -> None:
    lines.extend(["", "## 四、补充说明", ""])
    lines.append("- 完整结构化数据仍同步保留在同目录 `report_view.json`、`summary_report.json` 和 CSV 明细产物。")
    feedback_link = appendix.get("feedback_link", "")
    if feedback_link:
        lines.append(f"- 使用反馈：{feedback_link}")
    for item in appendix.get("reference_links", []):
        title = item.get("title", "")
        url = item.get("url", "")
        if title and url:
            lines.append(f"- {title}：{url}")
        elif title:
            lines.append(f"- {title}")


def _render_cumulative_section(
    lines: list[str], cumulative_summary: dict[str, object]
) -> None:
    overview = cumulative_summary["overview"]
    rankings = cumulative_summary["rankings"]
    integrated_rows = cumulative_summary.get("integrated_rows", [])

    lines.extend(
        [
            "",
            "## 年累计概览",
            f"- 纳入统计业务线数：{overview['business_line_count']}",
            f"- 平均 RDHS：{overview['average_score']}",
            f"- 合格/预警/失效：{overview['qualified_count']}/{overview['warning_count']}/{overview['invalid_count']}",
            "",
        ]
    )
    for item in rankings[:5]:
        lines.append(
            f"- TOP{item['rank']}: {_business_line_label(item['level_1'], item['level_2'])} | 分数 {item['score']} | 等级 {item['level']}"
        )
    lines.extend(["", "## 年累计排名与指标总表", ""])
    _render_rdhs_table(lines, integrated_rows, "RDHS累计数据")
    _render_core_metrics_table(lines, integrated_rows)


def render_report(
    summary: dict[str, object], cumulative_summary: dict[str, object] | None = None
) -> str:
    overview = summary["overview"]
    honor_board = summary.get("honor_board", {})
    rankings = summary["rankings"]
    integrated_rows = summary.get("integrated_rows", [])
    smart_insights = summary.get("smart_insights", {})
    ai_insights = summary.get("ai_insights", {})
    delivery_summary = summary.get("delivery_summary", {})
    appendix_section = summary.get("appendix_section", {})
    management_summary = summary.get("management_summary", {})
    business_line_spotlights = summary.get("business_line_spotlights", {})

    lines = [
        f"# 产研过程效能运营报告-{summary['period'].replace('-', '')}",
        "",
        f"统计周期：{_format_period_label(summary['period'])}",
        "",
    ]

    _render_management_summary(lines, management_summary)
    _render_honor_board(lines, honor_board)

    lines.extend(
        [
            "",
            "## 一、产研协同",
            "",
            "### 产研健康度得分(RDHS)",
            "> RDHS 从链路闭环、发布连续性、时效节奏、颗粒度对齐度、质量管理五个维度衡量业务线产研协同状态。",
            f"- 纳入统计业务线数：{overview['business_line_count']}",
            f"- 平均 RDHS：{overview['average_score']}",
            f"- 合格/预警/失效：{overview['qualified_count']}/{overview['warning_count']}/{overview['invalid_count']}",
            f"- 80 分以上业务线占比：{overview.get('score_gte_80_ratio', 0.0)}%",
            f"- 60 分以上业务线占比：{overview.get('score_gte_60_ratio', 0.0)}%",
            "",
        ]
    )
    for item in smart_insights.get("management_highlights", [])[:2]:
        lines.append(f"- {item}")
    for item in ai_insights.get("management_highlights", [])[:1]:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "### 结果指标概览",
            f"- 60 分以上业务线数：{overview.get('score_gte_60_count', 0)}，占比 {overview.get('score_gte_60_ratio', 0.0)}%",
            f"- 需求吞吐量低于 5 的业务线数：{overview.get('throughput_low_count', 0)}，占比 {overview.get('throughput_low_ratio', 0.0)}%",
            "",
        ]
    )
    _render_backlog_section(lines, summary.get("backlog_section", {}))
    _render_business_line_spotlights(
        lines, business_line_spotlights.get("rdhs_collaboration", {})
    )

    recommendations = ai_insights.get("section_recommendations", {})
    rdhs_recommendations = recommendations.get("rdhs_collaboration", {})
    _render_focus_and_recommendations(
        lines,
        problem_items=ai_insights.get("section_problem_analysis", {}).get(
            "rdhs_collaboration", []
        ),
        recommendations_by_role=rdhs_recommendations,
    )
    _render_delivery_section(
        lines,
        delivery_summary,
        ai_insights,
        business_line_spotlights.get("delivery_capability", {}),
    )
    _render_detail_appendix(
        lines,
        integrated_rows=integrated_rows,
        backlog_section=summary.get("backlog_section", {}),
        delivery_summary=delivery_summary,
    )
    _render_appendix_section(lines, appendix_section)

    if cumulative_summary:
        _render_cumulative_section(lines, cumulative_summary)

    return "\n".join(lines)
