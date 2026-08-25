"""为全量低 RDHS 产品补充主数据状态、超级团队关联和治理动作。"""

from __future__ import annotations

from collections import Counter
from collections import defaultdict
import csv
from dataclasses import dataclass
from pathlib import Path

from impl.periodic_report_models import ChartSnapshot
from impl.periodic_report_models import COMPONENT_FIELDS
from impl.periodic_report_models import ProductMetricRecord


_COMPONENT_LABELS = {
    "链路闭环得分(25')": "链路闭环得分",
    "交付闭环得分(15')": "交付闭环得分",
    "时效节奏合理性(20')": "时效节奏合理性",
    "颗粒度对齐度(20')": "颗粒度对齐度",
    "质量敏锐度(20')": "质量敏锐度",
}
_TAG_PRIORITY = {
    "过程数据缺失": 0,
    "价值链路不完整": 1,
    "过程能力优化": 2,
    "需求链路缺失": 1,
    "需求积压": 2,
    "质量管理风险": 3,
    "发布闭环不足": 4,
    "研发节奏偏慢": 5,
    "需求粒度问题": 6,
}
_ASSOCIATION_PRIORITY = {"已关联": 0, "关联待确认": 1, "已确认无关联": 2}
_EXCLUDED_BUSINESS_LINES = ("测试业务线",)
_EXCLUDED_PRODUCT_ATTRIBUTES = ("hmeckpgbh", "交付定制")


@dataclass(frozen=True)
class ProductMasterRecord:
    id: int
    business_line: str
    product: str
    raw_status: str
    product_attribute_label: str
    product_attribute_value: str


@dataclass(frozen=True)
class ResearchProductRecord:
    master: ProductMasterRecord
    metric: ProductMetricRecord | None
    team_names: tuple[str, ...]

    @property
    def business_line(self) -> str:
        return self.master.business_line

    @property
    def product(self) -> str:
        return self.master.product


@dataclass(frozen=True)
class ResearchProductPortfolio:
    records: tuple[ResearchProductRecord, ...]
    audit: dict[str, object]


@dataclass(frozen=True)
class TeamMapping:
    business_line: str
    product: str
    team: str


def load_team_mappings(path: Path) -> tuple[TeamMapping, ...]:
    """读取由初始化 Excel 转换而来的团队关联清单。"""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"业务线", "产品", "超级团队"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"team mapping is missing required columns: {path}")
        return tuple(
            TeamMapping(
                business_line=_business_line(row["业务线"]),
                product=_text(row["产品"]),
                team=_text(row["超级团队"]),
            )
            for row in reader
            if _business_line(row["业务线"]) and _text(row["产品"]) and _text(row["超级团队"])
        )


@dataclass(frozen=True)
class FullImprovementRow:
    business_line: str
    product: str
    product_status: str
    super_team_count: int | str
    association_state: str
    governance_mode: str
    rdhs: float | None
    lowest_component: str
    problem: str
    main_problem_tag: str
    action: str
    master_match_state: str
    master_id: int | None
    master_status_raw: str | None
    team_names: tuple[str, ...]
    priority: str


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _business_line(value: object) -> str:
    return _text(value).split("/")[0].strip()


def _key(business_line: object, product: object) -> tuple[str, str]:
    return (_business_line(business_line), _text(product))


def _items(payload: dict[str, object]) -> list[dict[str, object]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "businesses", "business_lines", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError("Meegle response does not contain an item list")


def parse_business_line_names(payload: dict[str, object]) -> dict[str, str]:
    """将业务线 ID 映射为一级业务线名称。"""
    names: dict[str, str] = {}

    def add_item(item: dict[str, object], first_level_name: str) -> None:
        identifier = _text(item.get("id"))
        if identifier and first_level_name:
            names[identifier] = first_level_name
        children = item.get("children")
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    add_item(child, first_level_name)

    for item in _items(payload):
        name = _business_line(item.get("name"))
        if name:
            add_item(item, name)
    return names


def _field_value(item: dict[str, object], alias: str) -> object | None:
    fields = item.get("fields")
    if not isinstance(fields, list):
        return None
    for field in fields:
        if not isinstance(field, dict):
            continue
        if field.get("field_alias") == alias or field.get("field_key") == alias:
            return field.get("field_value")
    return None


def parse_product_master_records(
    payload: dict[str, object],
    business_line_names: dict[str, str],
) -> tuple[ProductMasterRecord, ...]:
    """解析产品型号/子平台工作项，并保留原始状态值。"""
    records: list[ProductMasterRecord] = []
    for item in _items(payload):
        identifier = item.get("id")
        if not isinstance(identifier, int):
            continue
        business_identifier = _text(_field_value(item, "business"))
        business_line = business_line_names.get(business_identifier, "")
        product = _text(item.get("name"))
        status = item.get("work_item_status")
        raw_status = _text(status.get("state_key") if isinstance(status, dict) else "")
        product_attribute = _field_value(item, "field_22acd7")
        product_attribute_label = ""
        product_attribute_value = ""
        if isinstance(product_attribute, dict):
            product_attribute_label = _text(product_attribute.get("label"))
            product_attribute_value = _text(product_attribute.get("value"))
        if business_line and product:
            records.append(
                ProductMasterRecord(
                    id=identifier,
                    business_line=business_line,
                    product=product,
                    raw_status=raw_status,
                    product_attribute_label=product_attribute_label,
                    product_attribute_value=product_attribute_value,
                )
            )
    return tuple(records)


def _is_excluded_product_attribute(master: ProductMasterRecord) -> bool:
    return bool(
        {
            master.product_attribute_label,
            master.product_attribute_value,
        }
        & set(_EXCLUDED_PRODUCT_ATTRIBUTES)
    )


def build_research_product_portfolio(
    snapshot: ChartSnapshot,
    product_masters: tuple[ProductMasterRecord, ...],
    team_mappings: tuple[TeamMapping, ...],
) -> ResearchProductPortfolio:
    """以研发中产品主数据为底表，左关联有效 RDHS 图表记录。"""
    all_masters_by_key: dict[tuple[str, str], list[ProductMasterRecord]] = defaultdict(list)
    for master in product_masters:
        all_masters_by_key[_key(master.business_line, master.product)].append(master)

    excluded_business_line_master_total = 0
    excluded_product_attribute_master_total = 0
    clean_masters_by_key: dict[tuple[str, str], ProductMasterRecord] = {}
    for master in product_masters:
        if master.raw_status != "In Progress":
            continue
        if master.business_line in _EXCLUDED_BUSINESS_LINES:
            excluded_business_line_master_total += 1
            continue
        if _is_excluded_product_attribute(master):
            excluded_product_attribute_master_total += 1
            continue
        key = _key(master.business_line, master.product)
        if key in clean_masters_by_key:
            raise ValueError(
                "duplicate research product master: "
                f"{master.business_line} / {master.product}"
            )
        clean_masters_by_key[key] = master

    metrics_by_key: dict[tuple[str, str], ProductMetricRecord] = {}
    excluded_business_line_chart_record_total = 0
    excluded_product_attribute_chart_record_total = 0
    excluded_finished = 0
    chart_orphan_record_total = 0
    unknown_status_counts: Counter[str] = Counter()
    for metric in snapshot.records:
        key = _key(metric.business_line, metric.product)
        matches = all_masters_by_key.get(key, [])
        if metric.business_line in _EXCLUDED_BUSINESS_LINES:
            excluded_business_line_chart_record_total += 1
            continue
        if any(
            master.raw_status == "In Progress" and _is_excluded_product_attribute(master)
            for master in matches
        ):
            excluded_product_attribute_chart_record_total += 1
            continue
        if key in clean_masters_by_key:
            metrics_by_key[key] = metric
            continue
        if any(master.raw_status == "Finished" for master in matches):
            excluded_finished += 1
            continue
        if matches:
            unknown_status_counts.update(master.raw_status or "(空)" for master in matches)
            continue
        chart_orphan_record_total += 1

    teams_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for mapping in team_mappings:
        if mapping.team:
            teams_by_key[_key(mapping.business_line, mapping.product)].add(mapping.team)

    records = tuple(
        ResearchProductRecord(
            master=master,
            metric=metrics_by_key.get(key),
            team_names=tuple(sorted(teams_by_key[key])),
        )
        for key, master in sorted(clean_masters_by_key.items())
    )
    measured_total = sum(record.metric is not None for record in records)
    unmeasured_total = len(records) - measured_total
    measured_lt70_total = sum(
        record.metric is not None and record.metric.rdhs < 70 for record in records
    )
    return ResearchProductPortfolio(
        records=records,
        audit={
            "clean_research_product_total": len(records),
            "clean_research_lt70_total": measured_lt70_total,
            "measured_research_product_total": measured_total,
            "unmeasured_or_pending_total": unmeasured_total,
            "chart_orphan_record_total": chart_orphan_record_total,
            "excluded_business_lines": list(_EXCLUDED_BUSINESS_LINES),
            "excluded_business_line_master_total": excluded_business_line_master_total,
            "excluded_business_line_chart_record_total": excluded_business_line_chart_record_total,
            "excluded_product_attributes": list(_EXCLUDED_PRODUCT_ATTRIBUTES),
            "excluded_product_attribute_master_total": excluded_product_attribute_master_total,
            "excluded_product_attribute_chart_record_total": excluded_product_attribute_chart_record_total,
            "excluded_finished": excluded_finished,
            "status_raw_counts": dict(
                sorted(Counter(record.master.raw_status for record in records).items())
            ),
            "unknown_status_counts": dict(sorted(unknown_status_counts.items())),
        },
    )


def _mode_for_rdhs(rdhs: float) -> str:
    if rdhs < 45:
        return "重点治理"
    if rdhs < 60:
        return "风险改进"
    return "持续优化"


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def _lowest_component(record: ProductMetricRecord) -> str:
    lowest = min(record.metric(field) for field in COMPONENT_FIELDS)
    return " / ".join(
        _COMPONENT_LABELS[field]
        for field in COMPONENT_FIELDS
        if record.metric(field) == lowest
    )


def _main_problem_tag(record: ProductMetricRecord) -> str:
    participants = record.metric("有效参与人数")
    throughput = record.metric("人均需求吞吐量")
    backlog_rate = record.metric("积压需求占比")
    serious_bug_rate = record.metric("严重缺陷占比")
    if participants == 0:
        return "过程数据缺失"
    if throughput == 0 or record.metric("链路闭环得分(25')") < 15:
        return "需求链路缺失"
    if backlog_rate > 0.3:
        return "需求积压"
    if serious_bug_rate > 0.15:
        return "质量管理风险"
    if record.metric("交付闭环得分(15')") < 8:
        return "发布闭环不足"
    if record.metric("时效节奏合理性(20')") < 10:
        return "研发节奏偏慢"
    return "需求粒度问题"


def _problem(record: ProductMetricRecord, tag: str) -> str:
    participants = record.metric("有效参与人数")
    throughput = record.metric("人均需求吞吐量")
    bugs = record.metric("人均缺陷关闭量")
    demand_total = record.metric("需求总量")
    backlog_rate = record.metric("积压需求占比")
    facts: list[str] = []
    if tag == "过程数据缺失":
        facts.append("有效参与人数为 0，过程数据缺失")
    elif throughput == 0 and bugs > 0:
        facts.append(f"人均缺陷关闭 {_format_number(bugs)}，人均需求吞吐为 0")
    elif throughput == 0:
        facts.append("人均需求吞吐和人均缺陷关闭均为 0")
    else:
        facts.append(f"最低分项为 {_lowest_component(record)}")
    if backlog_rate > 0.3:
        facts.append(
            "叠加积压风险（需求总量 {total}，积压占比 {rate:.1f}%）".format(
                total=_format_number(demand_total), rate=backlog_rate * 100
            )
        )
    return f"{tag}：" + "；".join(facts) + "。"


def _action(record: ProductMetricRecord, tag: str) -> str:
    throughput = record.metric("人均需求吞吐量")
    bugs = record.metric("人均缺陷关闭量")
    backlog_rate = record.metric("积压需求占比")
    if tag == "过程数据缺失":
        action = "由业务接口人确认产品状态、研发责任人与参与角色；主数据正确则补齐角色和过程记录"
    elif tag == "需求链路缺失" and bugs > 0:
        action = "将已处理缺陷回挂到需求，并补齐本期在研需求、拆分和状态推进记录"
    elif tag == "需求链路缺失" or throughput == 0:
        action = "确认是否存在计划性研发；存在则补齐需求、拆分和状态推进，不存在则由业务接口人核查产品状态"
    elif tag == "需求积压":
        action = "逐条确认积压需求的处理结论、负责人和预计完成时间"
    elif tag == "质量管理风险":
        action = "对严重缺陷进行专项复盘，补齐需求、测试和缺陷闭环记录"
    elif tag == "发布闭环不足":
        action = "核查应发布需求的发布计划关联和有效发布证据"
    elif tag == "研发节奏偏慢":
        action = "为超长周期需求明确完成时间、验收节点和周复盘节奏"
    elif tag == "需求粒度问题":
        action = "抽样复核需求粒度，按功能边界重拆过粗或过细需求，并补齐缺陷归属"
    else:
        action = f"围绕{_lowest_component(record)}补齐对应过程记录，并在下期快照复核改善情况"
    if backlog_rate > 0.3 and tag != "需求积压":
        action += "；逐条确认积压需求的处理结论、负责人和预计完成时间"
    return action + "。"


def build_full_improvement_rows(
    portfolio: ResearchProductPortfolio,
) -> tuple[FullImprovementRow, ...]:
    """生成研发中产品的全量治理底库，保留未度量产品。"""
    rows: list[FullImprovementRow] = []
    for research_product in portfolio.records:
        record = research_product.metric
        if record is not None and record.rdhs >= 70:
            continue
        master = research_product.master
        teams = research_product.team_names
        association_state = "已关联" if teams else "关联待确认"
        if record is None:
            tag = "过程数据缺失"
            governance_mode = "重点治理"
            lowest_component = "未形成有效 RDHS 度量"
            problem = "产品主数据为研发中，但未关联到本期有效 RDHS 度量。"
            action = "确认产品主数据与度量源关联，补齐研发责任角色、需求、缺陷和验收记录；下期复核 RDHS。"
            priority = "P0"
        else:
            participants = record.metric("有效参与人数")
            throughput = record.metric("人均需求吞吐量")
            if participants == 0:
                tag = "过程数据缺失"
                priority = "P0"
            elif throughput == 0:
                tag = "价值链路不完整"
                priority = "P1"
            else:
                tag = "过程能力优化"
                priority = "P2"
            governance_mode = _mode_for_rdhs(record.rdhs)
            lowest_component = _lowest_component(record)
            problem = _problem(record, tag)
            action = _action(record, tag)
        rows.append(
            FullImprovementRow(
                business_line=master.business_line,
                product=master.product,
                product_status="研发中",
                super_team_count=len(teams) if teams else "—",
                association_state=association_state,
                governance_mode=governance_mode,
                rdhs=record.rdhs if record is not None else None,
                lowest_component=lowest_component,
                problem=problem,
                main_problem_tag=tag,
                action=action,
                master_match_state="唯一匹配",
                master_id=master.id,
                master_status_raw=master.raw_status,
                team_names=teams,
                priority=priority,
            )
        )
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    rows.sort(
        key=lambda row: (
            priority_order[row.priority],
            _ASSOCIATION_PRIORITY[row.association_state],
            row.business_line,
            row.rdhs if row.rdhs is not None else -1,
            _TAG_PRIORITY[row.main_problem_tag],
            row.product,
        )
    )
    return tuple(rows)
