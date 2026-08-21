from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BusinessLineDimension:
    level1_business_line: str
    level2_business_line: str = ""
    business_id: str = ""
    parent_business_id: str = ""

    @property
    def business_line(self) -> str:
        return self.level2_business_line or self.level1_business_line


@dataclass
class ReleasePlanDetail:
    release_plan_id: int
    name: str
    business_line: str
    created_at: str
    level1_business_line: str = ""
    level2_business_line: str = ""
    release_plan_status: str = ""
    deploy_task_count: int = 0
    deploy_status_counts: dict[str, int] = field(default_factory=dict)
    deploy_tasks: list[dict[str, Any]] = field(default_factory=list)
    kubelink_task_count: int = 0


@dataclass
class BusinessSummary:
    business_line: str
    level1_business_line: str
    level2_business_line: str
    release_plan_total: int
    release_plan_with_deploy_task_total: int
    digital_penetration_rate: float
    deploy_task_total: int
    deploy_status_counts: dict[str, int]
    deploy_completion_rate: float | None
    release_plan_with_kubelink_task_total: int = 0
    kubelink_release_penetration_rate: float = 0.0
    kubelink_task_total: int = 0
    kubelink_task_rate: float | None = None
    deploy_termination_rate: float = 0.0
    risk_score: float = 0.0
    release_plan_status_counts: dict[str, int] = field(default_factory=dict)
    released_plan_count: int = 0


@dataclass
class Overview:
    release_plan_total: int
    release_plan_with_deploy_task_total: int
    digital_penetration_rate: float
    deploy_task_total: int
    deploy_status_counts: dict[str, int]
    release_plan_with_kubelink_task_total: int = 0
    kubelink_release_penetration_rate: float = 0.0
    kubelink_task_total: int = 0
    kubelink_task_rate: float | None = None
    deploy_termination_rate: float = 0.0
    release_plan_status_counts: dict[str, int] = field(default_factory=dict)
    released_plan_count: int = 0


@dataclass
class OutputPaths:
    base_dir: Path
    release_plan_details_json: Path
    deploy_task_details_json: Path
    summary_csv: Path
    analysis_md: Path
    top_risk_csv: Path
    insight_input_json: Path
    report_prompt_md: Path
    operational_report_md: Path

    @property
    def details_json(self) -> Path:
        return self.release_plan_details_json


@dataclass
class HistoryPaths:
    base_dir: Path
    release_plan_history_jsonl: Path
    deploy_task_history_jsonl: Path
    business_summary_csv: Path


@dataclass
class TrendOutputPaths:
    base_dir: Path
    trend_analysis_md: Path
    business_line_mom_csv: Path
    rolling_risk_summary_csv: Path


@dataclass(frozen=True)
class KubelinkConfig:
    mode: str = "k8s_helm_signals"
    rule_version: str = "devops-k8s-helm-v1"
    match_fields: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MetricsConfig:
    project_key: str = "cbg_product_develop"
    kubelink: KubelinkConfig = field(default_factory=KubelinkConfig)
