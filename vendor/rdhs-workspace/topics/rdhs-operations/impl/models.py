from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field


@dataclass(frozen=True)
class BusinessLineRef:
    level_1: str
    level_2: str


@dataclass(frozen=True)
class NormalizedMetrics:
    period: str
    business_line: BusinessLineRef
    monthly_requirement_throughput: float
    monthly_bug_closed: float
    monthly_release_frequency: float
    avg_dev_cycle_days: float
    avg_delivery_cycle_days: float
    serious_bug_rate: float
    easy_detect_bug_rate: float
    precomputed_rdhs_score: int = 0
    precomputed_link_score: int = 0
    precomputed_release_score: int = 0
    precomputed_timeliness_score: int = 0
    precomputed_granularity_score: int = 0
    precomputed_quality_score: int = 0
    has_precomputed_scores: bool = False


@dataclass(frozen=True)
class RdhsScoreCard:
    metrics: NormalizedMetrics
    total_score: int
    level: str
    coverage_score: int
    process_norm_score: int
    link_score: int = 0
    release_score: int = 0
    timeliness_score: int = 0
    granularity_score: int = 0
    quality_score: int = 0
    risk_tags: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    timeliness_ratio_r: float = 0.0
    granularity_ratio_k: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "period": self.metrics.period,
            "business_line": asdict(self.metrics.business_line),
            "metrics": {
                "monthly_requirement_throughput": self.metrics.monthly_requirement_throughput,
                "monthly_bug_closed": self.metrics.monthly_bug_closed,
                "monthly_release_frequency": self.metrics.monthly_release_frequency,
                "avg_dev_cycle_days": self.metrics.avg_dev_cycle_days,
                "avg_delivery_cycle_days": self.metrics.avg_delivery_cycle_days,
                "serious_bug_rate": self.metrics.serious_bug_rate,
                "easy_detect_bug_rate": self.metrics.easy_detect_bug_rate,
            },
            "derived_metrics": {
                "timeliness_ratio_r": self.timeliness_ratio_r,
                "granularity_ratio_k": self.granularity_ratio_k,
            },
            "rdhs": {
                "score": self.total_score,
                "level": self.level,
                "coverage_score": self.coverage_score,
                "process_norm_score": self.process_norm_score,
                "link_score": self.link_score,
                "release_score": self.release_score,
                "timeliness_score": self.timeliness_score,
                "granularity_score": self.granularity_score,
                "quality_score": self.quality_score,
                "risk_tags": self.risk_tags,
                "reasons": self.reasons,
            },
        }
