"""基于经过校验的 RDHS 快照生成可执行的周期治理清单。"""

from __future__ import annotations

from collections import Counter
from collections import defaultdict

from impl.periodic_report_models import ChartSnapshot
from impl.periodic_report_models import COMPONENT_FIELDS
from impl.periodic_report_models import PeriodicImprovementRow
from impl.periodic_report_models import PeriodicOverviewRow
from impl.periodic_report_models import PeriodicReportData
from impl.periodic_report_models import ProductMetricRecord
from impl.product_improvement_enrichment import FullImprovementRow
from impl.product_improvement_enrichment import ResearchProductPortfolio


_MODE_PRIORITY = {"重点治理": 0, "风险改进": 1, "持续优化": 2, "常规跟踪": 3}
_COMPONENT_LABELS = {
    "链路闭环得分(25')": "链路闭环得分",
    "交付闭环得分(15')": "交付闭环得分",
    "时效节奏合理性(20')": "时效节奏合理性",
    "颗粒度对齐度(20')": "颗粒度对齐度",
    "质量敏锐度(20')": "质量敏锐度",
}


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def _mode_for_rdhs(rdhs: float) -> str:
    if rdhs < 45:
        return "重点治理"
    if rdhs < 60:
        return "风险改进"
    if rdhs < 70:
        return "持续优化"
    return "常规跟踪"


def _lowest_component_fields(record: ProductMetricRecord) -> list[str]:
    lowest_value = min(record.metric(field) for field in COMPONENT_FIELDS)
    return [field for field in COMPONENT_FIELDS if record.metric(field) == lowest_value]


def _lowest_component_label(record: ProductMetricRecord) -> str:
    return " / ".join(_COMPONENT_LABELS[field] for field in _lowest_component_fields(record))


def _previous_record_map(previous: ChartSnapshot | None) -> dict[tuple[str, str], ProductMetricRecord]:
    if previous is None:
        return {}
    return {(record.business_line, record.product): record for record in previous.records}


def _rdhs_change(record: ProductMetricRecord, previous_by_key: dict[tuple[str, str], ProductMetricRecord]) -> float | None:
    previous = previous_by_key.get((record.business_line, record.product))
    return None if previous is None else record.rdhs - previous.rdhs


def _problem_text(
    record: ProductMetricRecord,
    *,
    previous_by_key: dict[tuple[str, str], ProductMetricRecord],
) -> str:
    facts: list[str] = []
    participants = record.metric("有效参与人数")
    throughput = record.metric("人均需求吞吐量")
    bug_closed = record.metric("人均缺陷关闭量")
    demand_total = record.metric("需求总量")
    backlog_rate = record.metric("积压需求占比")
    delivery_days = record.metric("需求交付周期")
    development_days = record.metric("需求开发周期")
    serious_bug_rate = record.metric("严重缺陷占比")
    change = _rdhs_change(record, previous_by_key)

    if participants == 0:
        facts.append("有效参与人数为0，需先核查产品/研发责任人与角色配置")
    if throughput == 0 and bug_closed > 0:
        facts.append(
            "人均需求吞吐为0、人均缺陷关闭为{bugs}，研发活动未沉淀到需求主链路".format(
                bugs=_format_number(bug_closed)
            )
        )
    elif throughput == 0 and bug_closed == 0:
        facts.append("人均需求吞吐和人均缺陷关闭均为0，过程有效样本不足")
    if demand_total > 0 and backlog_rate >= 0.3:
        facts.append(
            "需求总量{total}，积压占比{rate:.1f}%".format(
                total=_format_number(demand_total), rate=backlog_rate * 100
            )
        )
    if development_days > 60 or delivery_days > 90:
        facts.append(
            "需求开发/交付周期为{development}/{delivery}天，存在超长周期风险".format(
                development=_format_number(development_days),
                delivery=_format_number(delivery_days),
            )
        )
    if serious_bug_rate >= 0.2:
        facts.append(f"严重缺陷占比{serious_bug_rate * 100:.1f}%，需要专项核查")
    if change is not None and change <= -10:
        facts.append(f"RDHS 较上月下降 {_format_number(abs(change))} 分")
    if not facts:
        facts.append(f"最低分项为{_lowest_component_label(record)}，需核查该过程记录是否完整")
    return "；".join(facts) + "。"


def _action_text(
    record: ProductMetricRecord,
    *,
    previous_by_key: dict[tuple[str, str], ProductMetricRecord],
) -> str:
    actions: list[str] = []
    participants = record.metric("有效参与人数")
    throughput = record.metric("人均需求吞吐量")
    backlog_rate = record.metric("积压需求占比")
    development_days = record.metric("需求开发周期")
    delivery_days = record.metric("需求交付周期")
    serious_bug_rate = record.metric("严重缺陷占比")
    change = _rdhs_change(record, previous_by_key)

    if participants == 0:
        actions.append("确认产品/研发责任人与参与角色，并补齐实名配置")
    if throughput == 0:
        actions.append("将本期在研事项回挂到需求，补齐拆分、状态推进和验收，并要求缺陷关联需求")
    if backlog_rate >= 0.3:
        actions.append(f"针对积压占比 {backlog_rate * 100:.1f}% 的存量需求逐条确认处理计划")
    if development_days > 60 or delivery_days > 90:
        actions.append("为超长周期需求明确完成时间、验收节点和周复盘节奏")
    if serious_bug_rate >= 0.2:
        actions.append("对严重缺陷做专项复盘，补齐需求、测试和缺陷闭环记录")
    if change is not None and change <= -10:
        actions.append(f"围绕环比下降 {_format_number(abs(change))} 分的分项逐项复盘并在本周确认改进责任")
    if not actions:
        actions.append(f"围绕{_lowest_component_label(record)}补齐过程记录并在周快照复核")
    return "；".join(actions) + "。"


def _select_line_records(records: list[ProductMetricRecord]) -> list[ProductMetricRecord]:
    candidates = [record for record in records if record.rdhs < 70]
    return sorted(
        candidates,
        key=lambda record: (
            _MODE_PRIORITY[_mode_for_rdhs(record.rdhs)],
            record.rdhs,
            min(record.metric(field) for field in COMPONENT_FIELDS),
            record.product,
        ),
    )[:3]


def _focus_text(
    selected: list[ProductMetricRecord],
    *,
    previous_by_key: dict[tuple[str, str], ProductMetricRecord],
) -> str:
    if not selected:
        return "暂无<70产品，保持常规跟踪。"
    component_counts: Counter[str] = Counter(
        field for record in selected for field in _lowest_component_fields(record)
    )
    focus_components = [
        _COMPONENT_LABELS[field]
        for field, _count in sorted(
            component_counts.items(),
            key=lambda item: (-item[1], COMPONENT_FIELDS.index(item[0])),
        )[:2]
    ]
    mode = _mode_for_rdhs(selected[0].rdhs)
    text = f"优先盯{len(selected)}个{mode}产品，主看{' / '.join(focus_components)}。"
    declines = [
        (record, _rdhs_change(record, previous_by_key))
        for record in selected
    ]
    declines = [(record, change) for record, change in declines if change is not None and change <= -10]
    if declines:
        record, change = min(declines, key=lambda item: item[1])
        text += f"其中{record.product}较上月下降 {_format_number(abs(change))} 分，优先复盘。"
    return text


def build_periodic_report_data(
    *,
    current: ChartSnapshot,
    previous: ChartSnapshot | None,
    portfolio: ResearchProductPortfolio,
    enriched_rows: tuple[FullImprovementRow, ...],
) -> PeriodicReportData:
    """以研发中产品主数据为统计底表，生成可对账的周期报告。"""
    products_by_line = defaultdict(list)
    for product in portfolio.records:
        products_by_line[product.business_line].append(product)

    def governance_mode(metric: ProductMetricRecord | None) -> str:
        return "重点治理" if metric is None else _mode_for_rdhs(metric.rdhs)

    def focus_text(line_products: list[object]) -> str:
        metrics = [product.metric for product in line_products]
        unmeasured_count = sum(metric is None for metric in metrics)
        governance_count = sum(
            metric is None or metric.rdhs < 70 for metric in metrics
        )
        if governance_count == 0:
            return "暂无<70产品，保持常规跟踪。"
        if unmeasured_count:
            return (
                f"{governance_count}个产品纳入治理：未度量/待关联 {unmeasured_count} 个，"
                "优先补齐产品关联、研发责任角色和过程数据。"
            )
        return (
            f"{governance_count}个产品纳入治理：优先修复价值链路闭环，"
            "过程能力短板同步跟踪。"
        )

    overview_rows: list[PeriodicOverviewRow] = []
    for business_line in sorted(products_by_line):
        line_products = products_by_line[business_line]
        counts = Counter(governance_mode(product.metric) for product in line_products)
        line_mode = min(counts, key=lambda mode: _MODE_PRIORITY[mode])
        overview_rows.append(
            PeriodicOverviewRow(
                business_line=business_line,
                product_total=len(line_products),
                key_governance_count=counts["重点治理"],
                risk_improvement_count=counts["风险改进"],
                continuous_optimization_count=counts["持续优化"],
                regular_tracking_count=counts["常规跟踪"],
                mode=line_mode,
                focus=focus_text(line_products),
            )
        )

    overview_rows.sort(
        key=lambda row: (
            -row.key_governance_count,
            -row.risk_improvement_count,
            -row.continuous_optimization_count,
            row.business_line,
        )
    )
    total_counts = Counter()
    for row in overview_rows:
        total_counts.update(
            {
                "重点治理": row.key_governance_count,
                "风险改进": row.risk_improvement_count,
                "持续优化": row.continuous_optimization_count,
                "常规跟踪": row.regular_tracking_count,
            }
        )
    total_mode = min(
        (mode for mode, count in total_counts.items() if count),
        key=lambda mode: _MODE_PRIORITY[mode],
    )
    total_products = list(portfolio.records)
    overview_rows.append(
        PeriodicOverviewRow(
            business_line="消费者BG（合计）",
            product_total=len(total_products),
            key_governance_count=total_counts["重点治理"],
            risk_improvement_count=total_counts["风险改进"],
            continuous_optimization_count=total_counts["持续优化"],
            regular_tracking_count=total_counts["常规跟踪"],
            mode=total_mode,
            focus=focus_text(total_products),
        )
    )

    improvement_rows = tuple(
        PeriodicImprovementRow(
            business_line=row.business_line,
            product=row.product,
            governance_mode=row.governance_mode,
            rdhs=row.rdhs,
            lowest_component=row.lowest_component,
            problem=row.problem,
            action=row.action,
            source_key=(row.business_line, row.product),
            priority=row.priority,
            super_team=" / ".join(row.team_names) if row.team_names else "—",
        )
        for row in enriched_rows
    )
    full_product_headers = ("业务线", "二级业务线", "产品", *current.quota_titles)
    full_product_rows = tuple(
        (
            product.business_line,
            product.master.sub_line or "—",
            product.product,
            *(product.metric.metric(field) for field in current.quota_titles),
        )
        for product in portfolio.records
        if product.metric is not None
    )
    priority_counts = Counter(row.priority for row in enriched_rows)
    todo_items = (
        f"各业务线质量改进负责人认领本期 {len(improvement_rows)} 个治理产品，并确认产品、研发责任人与本期动作。",
        "优先推动 P0 {p0} 项过程数据补齐，其次推动 P1 {p1} 项价值链路闭环，"
        "同步跟踪 P2 {p2} 项过程能力优化。".format(
            p0=priority_counts["P0"],
            p1=priority_counts["P1"],
            p2=priority_counts["P2"],
        ),
        "对长期未反馈、无责任人或无行动计划的事项，升级至业务线技术总监协调处理。",
    )
    return PeriodicReportData(
        overview_rows=tuple(overview_rows),
        improvement_rows=tuple(improvement_rows),
        todo_items=todo_items,
        audit={
            "current_chart_id": current.chart_id,
            "previous_chart_id": previous.chart_id if previous else None,
            "current_accepted_row_count": current.audit.accepted_row_count,
            "previous_accepted_row_count": previous.audit.accepted_row_count if previous else None,
            "selected_improvement_count": len(improvement_rows),
            "selection_limit_per_business_line": None,
            "priority_counts": {
                priority: priority_counts[priority] for priority in ("P0", "P1", "P2")
            },
            **portfolio.audit,
        },
        full_product_headers=full_product_headers,
        full_product_rows=full_product_rows,
    )
