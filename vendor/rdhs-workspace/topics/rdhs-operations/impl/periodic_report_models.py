"""周期性 RDHS 报告的稳定领域对象。"""

from __future__ import annotations

from dataclasses import dataclass


RDHS_FIELD = "RDHS(100')"
COMPONENT_FIELDS = (
    "链路闭环得分(25')",
    "交付闭环得分(15')",
    "时效节奏合理性(20')",
    "颗粒度对齐度(20')",
    "质量敏锐度(20')",
)
GOVERNANCE_TEXT_FIELDS = (
    "有效参与人数",
    "人均需求吞吐量",
    "人均缺陷关闭量",
    "需求总量",
    "积压需求占比",
    "需求开发周期",
    "需求交付周期",
    "严重缺陷占比",
)


@dataclass(frozen=True)
class ProductMetricRecord:
    business_line: str
    product: str
    metrics: dict[str, float]

    @property
    def rdhs(self) -> float:
        return self.metrics[RDHS_FIELD]

    def metric(self, field: str) -> float:
        return self.metrics[field]


@dataclass(frozen=True)
class SnapshotAudit:
    chart_id: str
    chart_name: str
    fetched_at: str
    source_sha256: str
    raw_row_count: int
    zero_rdhs_row_count: int
    empty_dimension_row_count: int
    accepted_row_count: int


@dataclass(frozen=True)
class ChartSnapshot:
    chart_id: str
    chart_name: str
    fetched_at: str
    quota_titles: tuple[str, ...]
    records: tuple[ProductMetricRecord, ...]
    audit: SnapshotAudit


@dataclass(frozen=True)
class PeriodicOverviewRow:
    business_line: str
    product_total: int
    key_governance_count: int
    risk_improvement_count: int
    continuous_optimization_count: int
    regular_tracking_count: int
    mode: str
    focus: str


@dataclass(frozen=True)
class PeriodicImprovementRow:
    business_line: str
    product: str
    governance_mode: str
    rdhs: float | None
    lowest_component: str
    problem: str
    action: str
    source_key: tuple[str, str]
    priority: str
    super_team: str


@dataclass(frozen=True)
class PeriodicReportData:
    overview_rows: tuple[PeriodicOverviewRow, ...]
    improvement_rows: tuple[PeriodicImprovementRow, ...]
    todo_items: tuple[str, ...]
    audit: dict[str, object]
    full_product_headers: tuple[str, ...] = ()
    full_product_rows: tuple[tuple[object, ...], ...] = ()
    full_improvement_headers: tuple[str, ...] = ()
    full_improvement_rows: tuple[tuple[object, ...], ...] = ()
