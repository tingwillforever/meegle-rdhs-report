from __future__ import annotations

from impl.models import BusinessLineRef
from impl.models import NormalizedMetrics


def normalize_business_line_metrics(raw_record: dict[str, object]) -> NormalizedMetrics:
    precomputed_fields = (
        "precomputed_rdhs_score",
        "precomputed_link_score",
        "precomputed_release_score",
        "precomputed_timeliness_score",
        "precomputed_granularity_score",
        "precomputed_quality_score",
    )
    return NormalizedMetrics(
        period=str(raw_record["period"]),
        business_line=BusinessLineRef(
            level_1=str(raw_record["level_1"]),
            level_2=str(raw_record["level_2"]),
        ),
        monthly_requirement_throughput=float(
            raw_record.get("monthly_requirement_throughput", 0.0)
        ),
        monthly_bug_closed=float(raw_record.get("monthly_bug_closed", 0.0)),
        monthly_release_frequency=float(
            raw_record.get("monthly_release_frequency", 0.0)
        ),
        avg_dev_cycle_days=float(raw_record.get("avg_dev_cycle_days", 0.0)),
        avg_delivery_cycle_days=float(raw_record.get("avg_delivery_cycle_days", 0.0)),
        serious_bug_rate=float(raw_record.get("serious_bug_rate", 0.0)),
        easy_detect_bug_rate=float(raw_record.get("easy_detect_bug_rate", 0.0)),
        precomputed_rdhs_score=int(float(raw_record.get("precomputed_rdhs_score", 0))),
        precomputed_link_score=int(float(raw_record.get("precomputed_link_score", 0))),
        precomputed_release_score=int(
            float(raw_record.get("precomputed_release_score", 0))
        ),
        precomputed_timeliness_score=int(
            float(raw_record.get("precomputed_timeliness_score", 0))
        ),
        precomputed_granularity_score=int(
            float(raw_record.get("precomputed_granularity_score", 0))
        ),
        precomputed_quality_score=int(
            float(raw_record.get("precomputed_quality_score", 0))
        ),
        has_precomputed_scores=any(field in raw_record for field in precomputed_fields),
    )
