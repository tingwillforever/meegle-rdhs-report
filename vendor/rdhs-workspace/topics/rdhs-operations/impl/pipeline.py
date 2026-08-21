from __future__ import annotations

import csv
import json
from pathlib import Path

from impl.report_view_model import build_report_view
from impl.normalizer import normalize_business_line_metrics
from impl.operations_analyzer import build_operations_summary
from impl.rdhs_engine import score_rdhs
from impl.report_renderer import render_report

PRECOMPUTED_SCORE_FIELDS = (
    "precomputed_rdhs_score",
    "precomputed_link_score",
    "precomputed_release_score",
    "precomputed_timeliness_score",
    "precomputed_granularity_score",
    "precomputed_quality_score",
)


def build_raw_records_from_source(
    period: str, fetch_payload: dict[str, object]
) -> list[dict[str, object]]:
    rows = fetch_payload.get("rows", [])
    return [
        {
            "period": period,
            "level_1": str(row.get("level_1", "")),
            "level_2": str(row.get("level_2", "")),
            "monthly_requirement_throughput": row.get(
                "monthly_requirement_throughput", 0.0
            ),
            "monthly_bug_closed": row.get("monthly_bug_closed", 0.0),
            "monthly_release_frequency": row.get("monthly_release_frequency", 0.0),
            "avg_dev_cycle_days": row.get("avg_dev_cycle_days", 0.0),
            "avg_delivery_cycle_days": row.get("avg_delivery_cycle_days", 0.0),
            "serious_bug_rate": row.get("serious_bug_rate", 0.0),
            "easy_detect_bug_rate": row.get("easy_detect_bug_rate", 0.0),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def summarize_score_cards(score_cards: list) -> dict[str, object]:
    return build_operations_summary(score_cards)


def build_matrix_score_audit(
    raw_records: list[dict[str, object]], score_cards: list
) -> dict[str, object]:
    score_card_by_key = {
        (item.metrics.business_line.level_1, item.metrics.business_line.level_2): item
        for item in score_cards
    }
    rows: list[dict[str, object]] = []
    for record in raw_records:
        if not any(field in record for field in PRECOMPUTED_SCORE_FIELDS):
            continue

        level_1 = str(record.get("level_1", ""))
        level_2 = str(record.get("level_2", ""))
        score_card = score_card_by_key.get((level_1, level_2))
        expected_total = int(float(record.get("precomputed_rdhs_score", 0)))
        expected_link = int(float(record.get("precomputed_link_score", 0)))
        expected_release = int(float(record.get("precomputed_release_score", 0)))
        expected_timeliness = int(
            float(record.get("precomputed_timeliness_score", 0))
        )
        expected_granularity = int(
            float(record.get("precomputed_granularity_score", 0))
        )
        expected_quality = int(float(record.get("precomputed_quality_score", 0)))

        actual_total = score_card.total_score if score_card else None
        actual_link = score_card.link_score if score_card else None
        actual_release = score_card.release_score if score_card else None
        actual_timeliness = score_card.timeliness_score if score_card else None
        actual_granularity = score_card.granularity_score if score_card else None
        actual_quality = score_card.quality_score if score_card else None

        rows.append(
            {
                "level_1": level_1,
                "level_2": level_2,
                "expected": {
                    "rdhs_score": expected_total,
                    "link_score": expected_link,
                    "release_score": expected_release,
                    "timeliness_score": expected_timeliness,
                    "granularity_score": expected_granularity,
                    "quality_score": expected_quality,
                },
                "actual": {
                    "rdhs_score": actual_total,
                    "link_score": actual_link,
                    "release_score": actual_release,
                    "timeliness_score": actual_timeliness,
                    "granularity_score": actual_granularity,
                    "quality_score": actual_quality,
                },
                "delta": {
                    "rdhs_score": None if actual_total is None else actual_total - expected_total,
                    "link_score": None if actual_link is None else actual_link - expected_link,
                    "release_score": None
                    if actual_release is None
                    else actual_release - expected_release,
                    "timeliness_score": None
                    if actual_timeliness is None
                    else actual_timeliness - expected_timeliness,
                    "granularity_score": None
                    if actual_granularity is None
                    else actual_granularity - expected_granularity,
                    "quality_score": None
                    if actual_quality is None
                    else actual_quality - expected_quality,
                },
                "matches_snapshot": score_card is not None
                and actual_total == expected_total
                and actual_link == expected_link
                and actual_release == expected_release
                and actual_timeliness == expected_timeliness
                and actual_granularity == expected_granularity
                and actual_quality == expected_quality,
            }
        )

    return {
        "summary": {
            "rows_with_precomputed_scores": len(rows),
            "matched_rows": sum(1 for row in rows if row["matches_snapshot"]),
            "mismatched_rows": sum(1 for row in rows if not row["matches_snapshot"]),
        },
        "rows": rows,
    }


def _serialize_normalized_metrics(normalized: list) -> list[dict[str, object]]:
    return [
        {
            "period": item.period,
            "business_line": {
                "level_1": item.business_line.level_1,
                "level_2": item.business_line.level_2,
            },
            "metrics": {
                "monthly_requirement_throughput": item.monthly_requirement_throughput,
                "monthly_bug_closed": item.monthly_bug_closed,
                "monthly_release_frequency": item.monthly_release_frequency,
                "avg_dev_cycle_days": item.avg_dev_cycle_days,
                "avg_delivery_cycle_days": item.avg_delivery_cycle_days,
                "serious_bug_rate": item.serious_bug_rate,
                "easy_detect_bug_rate": item.easy_detect_bug_rate,
            },
        }
        for item in normalized
    ]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_core_metric_rows(normalized: list) -> list[dict[str, object]]:
    return [
        {
            "一级业务线": item.business_line.level_1,
            "二级业务线": item.business_line.level_2,
            "月均需求吞吐量": item.monthly_requirement_throughput,
            "需求交付周期 (天)": item.avg_delivery_cycle_days,
            "需求开发周期(天)": item.avg_dev_cycle_days,
            "月均缺陷关闭量": item.monthly_bug_closed,
            "严重缺陷占比": item.serious_bug_rate,
            "低级缺陷占比": item.easy_detect_bug_rate,
            "月均发布频率": item.monthly_release_frequency,
        }
        for item in normalized
    ]


def _build_rdhs_sorted_rows(summary: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "一级业务线": row["level_1"],
            "二级业务线": row["level_2"],
            "RDHS(100')": row["rdhs_score"],
            "链路闭环情况(25')": row["link_score"],
            "发布连续性 (15')": row["release_score"],
            "时效节奏合理性 (20')": row["timeliness_score"],
            "颗粒度对齐度 (20')": row["granularity_score"],
            "质量管理得分 (20')": row["quality_score"],
        }
        for row in summary.get("integrated_rows", [])
    ]


def _monthly_csv_suffix(period: str) -> str:
    return period


def _cumulative_csv_suffix(period: str) -> str:
    return period[:4]


def _to_float(value: object, default: float = 0.0) -> float:
    if value in ("", None):
        return default
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if value.endswith("%"):
            value = value[:-1]
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_rate(value: object) -> str:
    return f"{_to_float(value):.1f}%"


def _business_line_label(level_1: object, level_2: object) -> str:
    level_1_text = str(level_1 or "").strip()
    level_2_text = str(level_2 or "").strip() or "(空)"
    return f"{level_1_text} / {level_2_text}"


def _backlog_row_label(row: dict[str, object]) -> str:
    return _business_line_label(row.get("一级业务线", ""), row.get("二级业务线", ""))


def _delivery_line_label(item: dict[str, object]) -> str:
    level_1 = item.get("level1_business_line", "")
    level_2 = item.get("level2_business_line", "")
    if level_1 or level_2:
        return _business_line_label(level_1, level_2)
    return str(item.get("business_line", "")).strip()


def _is_real_business_line(label: str) -> bool:
    normalized = label.replace(" ", "")
    return bool(label.strip()) and "测试" not in normalized and "其他" not in normalized


def _build_management_summary(summary: dict[str, object]) -> dict[str, list[str]]:
    overview = summary.get("overview", {})
    backlog_section = summary.get("backlog_section", {})
    delivery_summary = summary.get("delivery_summary", {})
    delivery_overview = delivery_summary.get("overview", {})

    total = int(_to_float(overview.get("business_line_count", 0)))
    score_gte_60_count = int(_to_float(overview.get("score_gte_60_count", 0)))
    invalid_count = int(_to_float(overview.get("invalid_count", 0)))
    average_score = overview.get("average_score", 0.0)

    headline_judgements = [
        f"本月 RDHS 平均 {average_score}，{score_gte_60_count}/{total} 条业务线达到 60 分以上，改进重点仍在基础过程补齐。",
        f"失效业务线 {invalid_count} 条，建议聚焦少数重点样本持续改善，避免一次性铺开所有问题。",
    ]
    next_month_actions = [
        "低分业务线先补齐需求闭环、发布计划维护和颗粒度一致性。",
        "围绕高分样板沉淀可复制动作，优先做小步快跑的月度改善。",
    ]

    backlog_lines = backlog_section.get("summary_lines", [])
    if backlog_lines:
        headline_judgements.append(str(backlog_lines[0]))
        next_month_actions.insert(0, "优先处理积压占比最高的业务线，明确继续、拆分或关闭。")
    elif _to_float(overview.get("throughput_low_count", 0)) > 0:
        headline_judgements.append(
            f"需求吞吐量低于 5 的业务线 {overview.get('throughput_low_count')} 条，需要优先核实真实交付节奏。"
        )

    if delivery_overview:
        headline_judgements.append(
            "交付数字化率 {digital_rate}，云原生渗透率 {cloud_rate}，交付能力先聚焦发布计划与部署任务关联。".format(
                digital_rate=_format_rate(
                    delivery_overview.get("digital_penetration_rate", 0.0)
                ),
                cloud_rate=_format_rate(
                    delivery_overview.get(
                        "cloud_native_release_penetration_rate", 0.0
                    )
                ),
            )
        )
        next_month_actions.append("对发布计划多但部署任务少的业务线建立月度校验。")

    return {
        "headline_judgements": headline_judgements[:3],
        "next_month_actions": next_month_actions[:3],
    }


def _build_rdhs_spotlights(summary: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    backlog_rows = list(summary.get("backlog_section", {}).get("rows", []))
    honor_board = summary.get("honor_board", {})
    red_board = list(honor_board.get("red_board", []))
    benchmark = red_board[0] if red_board else None
    benchmark_label = (
        _business_line_label(benchmark.get("level_1", ""), benchmark.get("level_2", ""))
        if isinstance(benchmark, dict)
        else ""
    )

    priority_improvement: list[dict[str, object]] = []
    for row in backlog_rows[:2]:
        if not isinstance(row, dict):
            continue
        problems = []
        backlog_rate = row.get("积压占比")
        if backlog_rate not in ("", None):
            problems.append(f"积压占比 {backlog_rate}")
        over_delivery = row.get("交付周期>90天")
        if over_delivery not in ("", None):
            problems.append(f"交付周期>90天 {over_delivery} 个")
        over_dev = row.get("开发周期>60天")
        if over_dev not in ("", None):
            problems.append(f"开发周期>60天 {over_dev} 个")
        priority_improvement.append(
            {
                "business_line": _backlog_row_label(row),
                "headline": "积压占比高，优先做存量需求清理。",
                "problems": problems,
                "actions": ["清理长期未完结需求", "复核需求状态并补齐流转完结"],
                "benchmark_reference": f"参考 {benchmark_label} 的需求闭环维护节奏。"
                if benchmark_label
                else "",
            }
        )

    if not priority_improvement:
        for risk in list(summary.get("key_risks", []))[:2]:
            if not isinstance(risk, dict):
                continue
            business_actions = (
                risk.get("actions", {}).get("business_line", [])
                if isinstance(risk.get("actions"), dict)
                else []
            )
            priority_improvement.append(
                {
                    "business_line": risk.get("business_line", ""),
                    "headline": "RDHS 低分，先补齐基础过程记录与流转闭环。",
                    "problems": [f"RDHS {risk.get('score')}，等级 {risk.get('level')}"],
                    "actions": business_actions[:2] or ["复核需求与发布记录完整性"],
                    "benchmark_reference": f"参考 {benchmark_label} 的协同维护节奏。"
                    if benchmark_label
                    else "",
                }
            )

    benchmark_cases = []
    if benchmark:
        benchmark_cases.append(
            {
                "business_line": benchmark_label,
                "headline": f"RDHS {benchmark.get('score')} 分，可作为当前协同样板。",
                "problems": ["链路闭环与发布连续性表现相对稳定。"],
                "actions": ["沉淀需求到发布的标准节奏动作"],
                "benchmark_reference": "建议作为低分业务线的对标样板。",
            }
        )

    return {
        "priority_improvement": priority_improvement,
        "benchmark_cases": benchmark_cases,
    }


def _build_delivery_spotlights(
    delivery_summary: dict[str, object],
) -> dict[str, list[dict[str, object]]]:
    top_risks = list(delivery_summary.get("top_risk_business_lines", []))
    business_summaries = list(delivery_summary.get("business_summaries", []))
    benchmark = next(
        (
            item
            for item in sorted(
                business_summaries,
                key=lambda row: (
                    -_to_float(row.get("digital_penetration_rate", 0.0)),
                    -_to_float(
                        row.get("cloud_native_release_penetration_rate", 0.0)
                    ),
                    _to_float(row.get("deploy_termination_rate", 0.0)),
                    -_to_float(row.get("release_plan_total", 0)),
                ),
            )
            if _to_float(item.get("release_plan_total", 0)) > 0
            and _is_real_business_line(_delivery_line_label(item))
        ),
        None,
    )
    benchmark_label = _delivery_line_label(benchmark) if isinstance(benchmark, dict) else ""

    priority_improvement: list[dict[str, object]] = []
    for item in top_risks[:2]:
        if not isinstance(item, dict):
            continue
        deploy_tasks = _to_float(item.get("deploy_task_total", 0))
        termination_rate = _to_float(item.get("deploy_termination_rate", 0.0))
        actions = []
        if deploy_tasks == 0:
            actions.append("补齐发布计划与部署任务关联")
        if termination_rate > 0:
            actions.append("复盘终止任务原因并分类治理")
        actions.append("提升发布与云原生任务联动覆盖")
        priority_improvement.append(
            {
                "business_line": _delivery_line_label(item),
                "headline": "交付过程留痕或执行稳定性不足，需优先补齐。",
                "problems": [
                    "发布计划 {plans} 个，部署任务 {tasks} 个".format(
                        plans=int(_to_float(item.get("release_plan_total", 0))),
                        tasks=int(deploy_tasks),
                    ),
                    "云原生渗透率 {cloud_rate}，部署终止率 {termination_rate}".format(
                        cloud_rate=_format_rate(
                            item.get("cloud_native_release_penetration_rate", 0.0)
                        ),
                        termination_rate=_format_rate(termination_rate),
                    ),
                ],
                "actions": actions[:2],
                "benchmark_reference": f"参考 {benchmark_label} 的稳定交付节奏。"
                if benchmark_label
                else "",
            }
        )

    benchmark_cases = []
    if benchmark:
        benchmark_cases.append(
            {
                "business_line": benchmark_label,
                "headline": "数字化率 {digital_rate}，云原生渗透率 {cloud_rate}，可作为交付留痕样板。".format(
                    digital_rate=_format_rate(
                        benchmark.get("digital_penetration_rate", 0.0)
                    ),
                    cloud_rate=_format_rate(
                        benchmark.get("cloud_native_release_penetration_rate", 0.0)
                    ),
                ),
                "problems": [
                    "发布计划 {plans} 个，接入部署任务 {tasks} 个。".format(
                        plans=int(_to_float(benchmark.get("release_plan_total", 0))),
                        tasks=int(
                            _to_float(
                                benchmark.get(
                                    "release_plan_with_deploy_task_total", 0
                                )
                            )
                        ),
                    )
                ],
                "actions": ["沉淀计划与部署联动维护机制"],
                "benchmark_reference": "建议作为交付能力样板业务线。",
            }
        )

    return {
        "priority_improvement": priority_improvement,
        "benchmark_cases": benchmark_cases,
    }


def _ensure_report_expression_sections(summary: dict[str, object]) -> None:
    if not summary.get("management_summary"):
        summary["management_summary"] = _build_management_summary(summary)

    existing_spotlights = summary.get("business_line_spotlights") or {}
    if not existing_spotlights.get("rdhs_collaboration"):
        existing_spotlights["rdhs_collaboration"] = _build_rdhs_spotlights(summary)
    if not existing_spotlights.get("delivery_capability"):
        existing_spotlights["delivery_capability"] = _build_delivery_spotlights(
            summary.get("delivery_summary", {})
        )
    summary["business_line_spotlights"] = existing_spotlights


def _build_summary_bundle(
    raw_records: list[dict[str, object]],
) -> dict[str, object]:
    normalized = [normalize_business_line_metrics(record) for record in raw_records]
    score_cards = [score_rdhs(item) for item in normalized]
    summary = summarize_score_cards(score_cards)
    matrix_score_audit = build_matrix_score_audit(raw_records, score_cards)
    return {
        "normalized": normalized,
        "score_cards": score_cards,
        "summary": summary,
        "matrix_score_audit": matrix_score_audit,
    }


def _write_summary_bundle(
    *,
    output_dir: Path,
    file_prefix: str,
    csv_name_prefix: str,
    csv_suffix: str,
    raw_records: list[dict[str, object]],
    bundle: dict[str, object],
) -> None:
    normalized = bundle["normalized"]
    score_cards = bundle["score_cards"]
    summary = bundle["summary"]
    matrix_score_audit = bundle["matrix_score_audit"]

    (output_dir / f"{file_prefix}raw_metrics.json").write_text(
        json.dumps(raw_records, ensure_ascii=False, indent=2)
    )
    (output_dir / f"{file_prefix}normalized_metrics.json").write_text(
        json.dumps(
            _serialize_normalized_metrics(normalized),
            ensure_ascii=False,
            indent=2,
        )
    )
    (output_dir / f"{file_prefix}rdhs_scores.json").write_text(
        json.dumps(
            [item.to_dict() for item in score_cards], ensure_ascii=False, indent=2
        )
    )
    (output_dir / f"{file_prefix}summary_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )
    (output_dir / f"{file_prefix}matrix_score_audit.json").write_text(
        json.dumps(matrix_score_audit, ensure_ascii=False, indent=2)
    )
    _write_csv(
        output_dir / f"{csv_name_prefix}core_metrics_{csv_suffix}.csv",
        [
            "一级业务线",
            "二级业务线",
            "月均需求吞吐量",
            "需求交付周期 (天)",
            "需求开发周期(天)",
            "月均缺陷关闭量",
            "严重缺陷占比",
            "低级缺陷占比",
            "月均发布频率",
        ],
        _build_core_metric_rows(normalized),
    )
    _write_csv(
        output_dir / f"{csv_name_prefix}rdhs_sorted_{csv_suffix}.csv",
        [
            "一级业务线",
            "二级业务线",
            "RDHS(100')",
            "链路闭环情况(25')",
            "发布连续性 (15')",
            "时效节奏合理性 (20')",
            "颗粒度对齐度 (20')",
            "质量管理得分 (20')",
        ],
        _build_rdhs_sorted_rows(summary),
    )


def run_pipeline(
    period: str,
    raw_records: list[dict[str, object]],
    output_dir: Path,
    cumulative_raw_records: list[dict[str, object]] | None = None,
    ai_insight_runner=None,
    dashboard_url: str = "",
    delivery_summary: dict[str, object] | None = None,
    appendix_links: dict[str, object] | None = None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    monthly_bundle = _build_summary_bundle(raw_records)
    summary = monthly_bundle["summary"]
    summary["period"] = period
    _write_summary_bundle(
        output_dir=output_dir,
        file_prefix="",
        csv_name_prefix="",
        csv_suffix=_monthly_csv_suffix(period),
        raw_records=raw_records,
        bundle=monthly_bundle,
    )

    cumulative_summary = None
    if cumulative_raw_records:
        cumulative_bundle = _build_summary_bundle(cumulative_raw_records)
        cumulative_summary = cumulative_bundle["summary"]
        cumulative_summary["period"] = str(
            cumulative_raw_records[0].get("period", f"{period[:4]}-累计")
        )
        _write_summary_bundle(
            output_dir=output_dir,
            file_prefix="cumulative_",
            csv_name_prefix="cumulative_",
            csv_suffix=_cumulative_csv_suffix(cumulative_summary["period"]),
            raw_records=cumulative_raw_records,
            bundle=cumulative_bundle,
        )

    summary["delivery_summary"] = delivery_summary or {}
    summary["appendix_section"] = appendix_links or {
        "feedback_link": "",
        "reference_links": [],
    }
    summary.setdefault(
        "backlog_section",
        {
            "summary_lines": [],
            "rows": [],
            "headers": [],
            "data_available": False,
        },
    )
    _ensure_report_expression_sections(summary)
    ai_insights = (
        ai_insight_runner(
            summary=summary,
            cumulative_summary=cumulative_summary,
            delivery_summary=delivery_summary,
        )
        if ai_insight_runner is not None
        else {
            "management_highlights": [],
            "section_problem_analysis": {},
            "section_recommendations": {},
        }
    )
    summary["ai_insights"] = ai_insights
    (output_dir / "summary_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )
    report_view = build_report_view(
        period=period,
        summary=summary,
        cumulative_summary=cumulative_summary,
        dashboard_url=dashboard_url,
        ai_insights=ai_insights,
        delivery_summary=delivery_summary,
        appendix_links=appendix_links,
    )
    (output_dir / "report_view.json").write_text(
        json.dumps(report_view, ensure_ascii=False, indent=2)
    )
    report = render_report(summary, cumulative_summary=cumulative_summary)
    (output_dir / "report.md").write_text(report)
    return {
        "summary": summary,
        "cumulative_summary": cumulative_summary,
        "report_view": report_view,
        "ai_insights": ai_insights,
        "report": report,
    }
