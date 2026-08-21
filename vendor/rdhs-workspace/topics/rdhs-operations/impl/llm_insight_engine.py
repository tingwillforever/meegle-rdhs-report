"""Constrained LLM insight orchestration for RDHS report sections."""

from __future__ import annotations

import json

from shared.llm.llm_client import LLMClient


SYSTEM_PROMPT = """
你是面向管理层的数据运营分析助手。

你的任务是基于给定的结构化数据，输出问题分析与改进建议。

严格遵守以下规则：
1. 只能依据输入中的结构化字段作答，禁止编造不存在的数据。
2. 必须区分“事实”与“推断”；推断只能建立在给定事实之上。
3. 当证据不足时，明确输出“证据不足”或“需要进一步核实”。
4. 输出必须是 JSON 对象。
5. 不要重复输入字段名列表，不要输出 markdown。
""".strip()


def build_ai_insight_payload(
    *,
    summary: dict[str, object],
    delivery_summary: dict[str, object] | None = None,
    cumulative_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "summary_overview": summary.get("overview", {}),
        "backlog_section": summary.get("backlog_section", {}),
        "honor_board": summary.get("honor_board", {}),
        "rankings_top": summary.get("rankings", [])[:10],
        "key_risks": summary.get("key_risks", []),
        "common_signals": summary.get("common_signals", []),
        "integrated_rows_top": summary.get("integrated_rows", [])[:10],
        "delivery_summary": delivery_summary or {},
        "cumulative_summary": cumulative_summary or {},
    }


def build_ai_insight_prompts(payload: dict[str, object]) -> tuple[str, str]:
    user_prompt = (
        "请基于以下结构化输入，为月报生成 AI 辅助洞察。\n"
        "输出必须是 JSON，并包含：\n"
        "- management_highlights: string[]\n"
        "- section_problem_analysis: object，至少包含 rdhs_collaboration, delivery_capability 两个数组字段\n"
        "- section_recommendations: object，必须按章节输出 rdhs_collaboration 和 delivery_capability；每个章节下再包含 management, business_line, platform_owner 三个数组字段\n"
        "每条结论都必须基于输入事实；如果证据不足，请明确写出“证据不足”或“需要进一步核实”。\n"
        "请区分事实与基于事实的推断，禁止把推断写成已确认事实。\n"
        "不要把产研协同建议复用到交付能力章节，也不要把交付能力建议复用到产研协同章节。\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    return SYSTEM_PROMPT, user_prompt


def generate_ai_insights(
    client: LLMClient,
    *,
    summary: dict[str, object],
    delivery_summary: dict[str, object] | None = None,
    cumulative_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = build_ai_insight_payload(
        summary=summary,
        delivery_summary=delivery_summary,
        cumulative_summary=cumulative_summary,
    )
    system_prompt, user_prompt = build_ai_insight_prompts(payload)
    raw = client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
    recommendations = raw.get("section_recommendations", {})
    return {
        "management_highlights": raw.get("management_highlights", []),
        "section_problem_analysis": raw.get(
            "section_problem_analysis",
            {"rdhs_collaboration": [], "delivery_capability": []},
        ),
        "section_recommendations": {
            "rdhs_collaboration": recommendations.get(
                "rdhs_collaboration",
                {"management": [], "business_line": [], "platform_owner": []},
            ),
            "delivery_capability": recommendations.get(
                "delivery_capability",
                {"management": [], "business_line": [], "platform_owner": []},
            ),
        },
    }
