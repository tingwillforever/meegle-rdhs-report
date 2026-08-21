from __future__ import annotations


def _top_ranked_lines(rankings: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    return [
        {
            "rank": item["rank"],
            "level_1": item["level_1"],
            "level_2": item["level_2"],
            "score": item["score"],
            "level": item["level"],
        }
        for item in rankings[:limit]
    ]


def build_report_view(
    *,
    period: str,
    summary: dict[str, object],
    cumulative_summary: dict[str, object] | None = None,
    dashboard_url: str = "",
    ai_insights: dict[str, object] | None = None,
    delivery_summary: dict[str, object] | None = None,
    appendix_links: dict[str, object] | None = None,
) -> dict[str, object]:
    overview = summary.get("overview", {})
    honor_board = summary.get("honor_board", {})
    smart_insights = summary.get("smart_insights", {})
    ai_payload = ai_insights or {
        "management_highlights": [],
        "section_problem_analysis": {},
        "section_recommendations": {},
    }
    appendix_payload = appendix_links or {
        "feedback_link": "",
        "reference_links": [],
    }
    return {
        "header": {
            "title": f"产研过程效能运营报告-{period.replace('-', '')}",
            "period": period,
            "dashboard_url": dashboard_url,
        },
        "management_summary": summary.get("management_summary", {}),
        "honor_board": honor_board,
        "rdhs_section": {
            "overview": overview,
            "rankings": summary.get("rankings", []),
            "integrated_rows": summary.get("integrated_rows", []),
            "management_highlights": smart_insights.get("management_highlights", []),
            "structured_diagnosis": smart_insights.get("structured_diagnosis", {}),
            "business_line_spotlights": summary.get("business_line_spotlights", {}).get(
                "rdhs_collaboration", {}
            ),
        },
        "result_metrics_section": {
            "throughput_low_count": overview.get("throughput_low_count", 0),
            "throughput_low_ratio": overview.get("throughput_low_ratio", 0.0),
            "score_gte_60_count": overview.get("score_gte_60_count", 0),
            "score_gte_60_ratio": overview.get("score_gte_60_ratio", 0.0),
            "score_gte_80_count": overview.get("score_gte_80_count", 0),
            "score_gte_80_ratio": overview.get("score_gte_80_ratio", 0.0),
            "sample_business_lines": _top_ranked_lines(summary.get("rankings", []), 5),
        },
        "backlog_section": {
            "backlog_high_count": overview.get("backlog_high_count", 0),
            "backlog_high_ratio": overview.get("backlog_high_ratio", 0.0),
            "zero_throughput_with_bug_lines": overview.get(
                "zero_throughput_with_bug_lines", []
            ),
            "summary_lines": summary.get("backlog_section", {}).get("summary_lines", []),
            "rows": summary.get("backlog_section", {}).get("rows", []),
            "headers": summary.get("backlog_section", {}).get("headers", []),
            "data_available": summary.get("backlog_section", {}).get(
                "data_available", False
            ),
        },
        "delivery_section": {
            **(delivery_summary or {}),
            "business_line_spotlights": summary.get("business_line_spotlights", {}).get(
                "delivery_capability", {}
            ),
        },
        "appendix_section": appendix_payload,
        "ai_insights": ai_payload,
        "cumulative_section": cumulative_summary or {},
    }
