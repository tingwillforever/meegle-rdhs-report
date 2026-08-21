from __future__ import annotations

from collections import Counter

from impl.models import RdhsScoreCard

SUBSCORE_FIELDS = (
    ("link_score", "链路闭环"),
    ("release_score", "发布连续性"),
    ("timeliness_score", "时效节奏"),
    ("granularity_score", "颗粒度对齐度"),
    ("quality_score", "质量管理"),
)


def _business_line_label(score_card: RdhsScoreCard) -> str:
    level_2 = score_card.metrics.business_line.level_2 or "(空)"
    return f"{score_card.metrics.business_line.level_1} / {level_2}"


def _top_dimensions(score_card: RdhsScoreCard, limit: int = 2) -> list[str]:
    ranked = sorted(
        ((label, getattr(score_card, field_name)) for field_name, label in SUBSCORE_FIELDS),
        key=lambda item: (-item[1], item[0]),
    )
    labels = [label for label, value in ranked if value > 0][:limit]
    return labels or [ranked[0][0]]


def _weakest_dimensions(score_card: RdhsScoreCard) -> list[str]:
    values = [getattr(score_card, field_name) for field_name, _label in SUBSCORE_FIELDS]
    weakest = min(values)
    return [
        label
        for field_name, label in SUBSCORE_FIELDS
        if getattr(score_card, field_name) == weakest
    ]


def _build_integrated_rows(ordered: list[RdhsScoreCard]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, item in enumerate(ordered, start=1):
        rows.append(
            {
                "rank": index,
                "level_1": item.metrics.business_line.level_1,
                "level_2": item.metrics.business_line.level_2,
                "rdhs_score": item.total_score,
                "level": item.level,
                "link_score": item.link_score,
                "release_score": item.release_score,
                "timeliness_score": item.timeliness_score,
                "granularity_score": item.granularity_score,
                "quality_score": item.quality_score,
                "monthly_requirement_throughput": item.metrics.monthly_requirement_throughput,
                "monthly_bug_closed": item.metrics.monthly_bug_closed,
                "monthly_release_frequency": item.metrics.monthly_release_frequency,
                "avg_dev_cycle_days": item.metrics.avg_dev_cycle_days,
                "avg_delivery_cycle_days": item.metrics.avg_delivery_cycle_days,
                "serious_bug_rate": item.metrics.serious_bug_rate,
                "easy_detect_bug_rate": item.metrics.easy_detect_bug_rate,
            }
        )
    return rows


def _build_management_highlights(ordered: list[RdhsScoreCard]) -> list[str]:
    if not ordered:
        return []

    qualified = [item for item in ordered if item.level == "qualified"]
    warning = [item for item in ordered if item.level == "warning"]
    invalid = [item for item in ordered if item.level == "invalid"]

    top = ordered[0]
    highlights = [
        f"最高分业务线为 {_business_line_label(top)}，RDHS {top.total_score}，主要由 {'、'.join(_top_dimensions(top))} 支撑。",
        f"本月共 {len(qualified)} 条合格、{len(warning)} 条预警、{len(invalid)} 条失效，低分业务线仍占多数。",
    ]

    if warning:
        watch = min(warning, key=lambda item: item.total_score)
        highlights.append(
            f"临界预警业务线 {_business_line_label(watch)} 当前 {watch.total_score} 分，最薄弱环节是 {'、'.join(_weakest_dimensions(watch))}。"
        )

    if invalid:
        zero_counter = Counter()
        for item in invalid:
            for field_name, label in SUBSCORE_FIELDS:
                if getattr(item, field_name) == 0:
                    zero_counter[label] += 1
        if zero_counter:
            dominant_label, count = zero_counter.most_common(1)[0]
            highlights.append(
                f"失效业务线共 {len(invalid)} 条，最集中的失分项是 {dominant_label}，共有 {count} 条业务线该项为 0 分。"
            )

    divergence = next(
        (
            item
            for item in sorted(
                ordered,
                key=lambda score_card: (
                    -score_card.total_score,
                    -score_card.metrics.monthly_bug_closed,
                ),
            )
            if item.metrics.monthly_requirement_throughput == 0
            and item.metrics.monthly_bug_closed > 0
        ),
        None,
    )
    if divergence:
        highlights.append(
            f"{_business_line_label(divergence)} 需求吞吐量为 0，但缺陷关闭量为 {int(divergence.metrics.monthly_bug_closed)}，呈现明显存量消化型特征。"
        )

    return highlights


def _build_structured_diagnosis(
    ordered: list[RdhsScoreCard],
) -> dict[str, list[str]]:
    qualified = [item for item in ordered if item.level == "qualified"]
    warning = [item for item in ordered if item.level == "warning"]
    invalid = [item for item in ordered if item.level == "invalid"]

    high_performers = [
        f"{_business_line_label(item)}：RDHS {item.total_score}，{'、'.join(_top_dimensions(item))}是主要支撑项。"
        for item in qualified[:3]
    ] or ["暂无合格样板业务线。"]

    warning_watchlist = [
        f"{_business_line_label(item)}：RDHS {item.total_score}，当前短板是 {'、'.join(_weakest_dimensions(item))}。"
        for item in warning
    ] or ["暂无预警带业务线。"]

    zero_groups = Counter()
    owners: dict[str, list[str]] = {}
    for item in invalid:
        for field_name, label in SUBSCORE_FIELDS:
            if getattr(item, field_name) == 0:
                zero_groups[label] += 1
                owners.setdefault(label, []).append(_business_line_label(item))
    invalid_clusters = [
        f"{label}为集中失分项，涉及 {count} 条业务线，典型样本包括 {', '.join(owners[label][:3])}。"
        for label, count in zero_groups.most_common(2)
    ] or ["暂无失效集中短板。"]

    divergences = [
        f"{_business_line_label(item)}：需求吞吐量为 0，但缺陷关闭量为 {int(item.metrics.monthly_bug_closed)}。"
        for item in ordered
        if item.metrics.monthly_requirement_throughput == 0
        and item.metrics.monthly_bug_closed > 0
    ][:3] or ["未识别到明显指标背离样本。"]

    return {
        "高分样板": high_performers,
        "临界预警": warning_watchlist,
        "失效集中区": invalid_clusters,
        "指标背离": divergences,
    }


def _action_templates(score_card: RdhsScoreCard) -> dict[str, list[str]]:
    actions = {
        "bg_management": [],
        "business_line": [],
        "platform_owner": [],
    }
    if (
        "release_continuity_missing" in score_card.risk_tags
        or "release_continuity_low" in score_card.risk_tags
    ):
        actions["bg_management"].append("建立 BG 级月度发布治理例会")
        actions["business_line"].append("建立月度发布台账校验机制")
        actions["platform_owner"].append("补齐发布节点校验规则")
    if "suspected_backfill_or_backlog" in score_card.risk_tags:
        actions["bg_management"].append("将疑似补录问题纳入月度治理通报")
        actions["business_line"].append("抽查需求创建时间与交付时间，识别补录行为")
        actions["platform_owner"].append("补充需求流转时间戳审计能力")
    if (
        "granularity_invalid" in score_card.risk_tags
        or "granularity_misaligned" in score_card.risk_tags
    ):
        actions["bg_management"].append("推动重点业务线执行统一需求拆分标准")
        actions["business_line"].append("按标准功能点拆分需求，校正需求与缺陷颗粒度")
        actions["platform_owner"].append("在提单模板中增加颗粒度校验提示")
    if (
        "quality_classification_suspect" in score_card.risk_tags
        or "quality_ratio_exceeds_threshold" in score_card.risk_tags
        or "quality_ratio_partially_valid" in score_card.risk_tags
    ):
        actions["bg_management"].append("对高风险质量业务线进行专项复盘")
        actions["business_line"].append("复核缺陷定级与容易发现问题归类规则")
        actions["platform_owner"].append("统一质量分类口径并固化到平台")

    if any(actions.values()):
        return {key: value for key, value in actions.items() if value}
    return {
        "bg_management": ["保持现有治理节奏，持续监控环比波动"],
        "business_line": ["保持现有治理节奏，持续监控环比波动"],
        "platform_owner": ["保持现有治理节奏，持续监控环比波动"],
    }


def build_operations_summary(score_cards: list[RdhsScoreCard]) -> dict[str, object]:
    if not score_cards:
        return {
            "overview": {
                "business_line_count": 0,
                "qualified_count": 0,
                "warning_count": 0,
                "invalid_count": 0,
                "average_score": 0.0,
                "score_gte_60_count": 0,
                "score_gte_80_count": 0,
                "qualified_ratio": 0.0,
                "score_gte_60_ratio": 0.0,
                "score_gte_80_ratio": 0.0,
                "throughput_low_count": 0,
                "throughput_low_ratio": 0.0,
                "backlog_high_count": 0,
                "backlog_high_ratio": 0.0,
                "zero_throughput_with_bug_lines": [],
            },
            "honor_board": {
                "red_board": [],
                "black_board": [],
            },
            "rankings": [],
            "key_risks": [],
            "common_signals": [],
            "integrated_rows": [],
            "smart_insights": {
                "management_highlights": [],
                "structured_diagnosis": {},
            },
        }

    ordered = sorted(score_cards, key=lambda item: item.total_score, reverse=True)
    total = len(score_cards)
    qualified_count = sum(1 for item in score_cards if item.level == "qualified")
    warning_count = sum(1 for item in score_cards if item.level == "warning")
    invalid_count = sum(1 for item in score_cards if item.level == "invalid")
    score_gte_60 = sum(1 for item in score_cards if item.total_score >= 60)
    score_gte_80 = sum(1 for item in score_cards if item.total_score >= 80)
    throughput_low_lines = [
        _business_line_label(item)
        for item in score_cards
        if item.metrics.monthly_requirement_throughput < 5
    ]
    zero_throughput_with_bug_lines = [
        _business_line_label(item)
        for item in score_cards
        if item.metrics.monthly_requirement_throughput == 0
        and item.metrics.monthly_bug_closed > 0
    ]
    rankings = [
        {
            "rank": index + 1,
            "level_1": item.metrics.business_line.level_1,
            "level_2": item.metrics.business_line.level_2,
            "score": item.total_score,
            "level": item.level,
        }
        for index, item in enumerate(ordered)
    ]
    key_risks = [
        {
            "business_line": f"{item.metrics.business_line.level_1} / {item.metrics.business_line.level_2}",
            "score": item.total_score,
            "level": item.level,
            "top_issues": item.risk_tags,
            "actions": _action_templates(item),
            "metrics_snapshot": {
                "monthly_requirement_throughput": item.metrics.monthly_requirement_throughput,
                "monthly_bug_closed": item.metrics.monthly_bug_closed,
                "monthly_release_frequency": item.metrics.monthly_release_frequency,
                "avg_dev_cycle_days": item.metrics.avg_dev_cycle_days,
                "avg_delivery_cycle_days": item.metrics.avg_delivery_cycle_days,
                "serious_bug_rate": item.metrics.serious_bug_rate,
                "easy_detect_bug_rate": item.metrics.easy_detect_bug_rate,
            },
        }
        for item in sorted(score_cards, key=lambda card: card.total_score)[:3]
    ]
    risk_counter = Counter(tag for item in score_cards for tag in item.risk_tags)
    common_signals = [
        {
            "tag": tag,
            "count": count,
            "business_lines": [
                f"{item.metrics.business_line.level_1} / {item.metrics.business_line.level_2}"
                for item in score_cards
                if tag in item.risk_tags
            ],
        }
        for tag, count in risk_counter.most_common()
    ]
    average_score = round(
        sum(item.total_score for item in score_cards) / len(score_cards), 1
    )
    return {
        "overview": {
            "business_line_count": total,
            "qualified_count": qualified_count,
            "warning_count": warning_count,
            "invalid_count": invalid_count,
            "average_score": average_score,
            "score_gte_60_count": score_gte_60,
            "score_gte_80_count": score_gte_80,
            "qualified_ratio": round(qualified_count * 100 / total, 1),
            "score_gte_60_ratio": round(score_gte_60 * 100 / total, 1),
            "score_gte_80_ratio": round(score_gte_80 * 100 / total, 1),
            "throughput_low_count": len(throughput_low_lines),
            "throughput_low_ratio": round(len(throughput_low_lines) * 100 / total, 1),
            "backlog_high_count": 0,
            "backlog_high_ratio": 0.0,
            "zero_throughput_with_bug_lines": zero_throughput_with_bug_lines,
        },
        "honor_board": {
            "red_board": [
                {
                    "level_1": item.metrics.business_line.level_1,
                    "level_2": item.metrics.business_line.level_2,
                    "score": item.total_score,
                }
                for item in ordered
                if item.total_score >= 80
            ][:5],
            "black_board": [
                {
                    "level_1": item.metrics.business_line.level_1,
                    "level_2": item.metrics.business_line.level_2,
                    "score": item.total_score,
                }
                for item in sorted(score_cards, key=lambda item: item.total_score)
                if item.total_score < 30
            ][:5],
        },
        "rankings": rankings,
        "key_risks": key_risks,
        "common_signals": common_signals,
        "integrated_rows": _build_integrated_rows(ordered),
        "smart_insights": {
            "management_highlights": _build_management_highlights(ordered),
            "structured_diagnosis": _build_structured_diagnosis(ordered),
        },
    }
