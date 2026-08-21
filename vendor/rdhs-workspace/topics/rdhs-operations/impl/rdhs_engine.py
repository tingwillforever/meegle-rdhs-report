from __future__ import annotations

from impl.models import NormalizedMetrics
from impl.models import RdhsScoreCard


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def score_rdhs(metrics: NormalizedMetrics) -> RdhsScoreCard:
    reasons: dict[str, str] = {}
    risk_tags: list[str] = []

    if metrics.has_precomputed_scores:
        coverage_score = (
            metrics.precomputed_link_score + metrics.precomputed_release_score
        )
        process_norm_score = (
            metrics.precomputed_timeliness_score
            + metrics.precomputed_granularity_score
            + metrics.precomputed_quality_score
        )
        total_score = metrics.precomputed_rdhs_score
        level = (
            "qualified"
            if total_score >= 80
            else "warning"
            if total_score >= 60
            else "invalid"
        )
        reasons["score_source"] = "precomputed matrix scores"

        return RdhsScoreCard(
            metrics=metrics,
            total_score=total_score,
            level=level,
            coverage_score=coverage_score,
            process_norm_score=process_norm_score,
            link_score=metrics.precomputed_link_score,
            release_score=metrics.precomputed_release_score,
            timeliness_score=metrics.precomputed_timeliness_score,
            granularity_score=metrics.precomputed_granularity_score,
            quality_score=metrics.precomputed_quality_score,
            risk_tags=[],
            reasons=reasons,
            timeliness_ratio_r=_safe_ratio(
                metrics.avg_dev_cycle_days, metrics.avg_delivery_cycle_days
            ),
            granularity_ratio_k=_safe_ratio(
                metrics.monthly_bug_closed, metrics.monthly_requirement_throughput
            ),
        )

    if (
        metrics.monthly_requirement_throughput >= 20
        and metrics.monthly_bug_closed >= 50
    ):
        link_score = 25
        reasons["link_closure"] = "requirement throughput >= 20 and bug closure >= 50"
    elif (
        metrics.monthly_requirement_throughput >= 10
        and metrics.monthly_bug_closed >= 20
    ):
        link_score = 15
        reasons["link_closure"] = "requirement throughput >= 10 and bug closure >= 20"
    elif metrics.monthly_requirement_throughput > 0 or metrics.monthly_bug_closed > 0:
        link_score = 5
        reasons["link_closure"] = (
            "only one of requirement throughput or bug closure is > 0"
        )
        risk_tags.append("link_closure_incomplete")
    else:
        link_score = 0
        reasons["link_closure"] = "both requirement throughput and bug closure are 0"
        risk_tags.append("link_closure_missing")

    frequency = metrics.monthly_release_frequency
    if frequency >= 2.0:
        release_score = 15
        reasons["release_continuity"] = "frequency >= 2.0"
    elif frequency >= 1.0:
        release_score = 10
        reasons["release_continuity"] = "1.0 <= frequency < 2.0"
    elif frequency >= 0.5:
        release_score = 5
        reasons["release_continuity"] = "0.5 <= frequency < 1.0"
        risk_tags.append("release_continuity_low")
    else:
        release_score = 0
        reasons["release_continuity"] = "frequency < 0.5"
        risk_tags.append("release_continuity_missing")

    r_ratio = _safe_ratio(metrics.avg_dev_cycle_days, metrics.avg_delivery_cycle_days)
    if 0.4 <= r_ratio <= 0.7:
        rhythm_score = 20
        reasons["timeliness_rhythm"] = "R in [0.4, 0.7]"
    elif 0.3 <= r_ratio < 0.4 or 0.7 < r_ratio <= 0.8:
        rhythm_score = 15
        reasons["timeliness_rhythm"] = "R in [0.3, 0.4) or (0.7, 0.8]"
    elif 0.2 <= r_ratio < 0.3 or 0.8 < r_ratio <= 0.9:
        rhythm_score = 10
        reasons["timeliness_rhythm"] = "R in [0.2, 0.3) or (0.8, 0.9]"
        risk_tags.append("timeliness_rhythm_borderline")
    else:
        rhythm_score = 0
        reasons["timeliness_rhythm"] = "R < 0.2 or R > 0.9"
        risk_tags.append("suspected_backfill_or_backlog")

    k_ratio = _safe_ratio(
        metrics.monthly_bug_closed, metrics.monthly_requirement_throughput
    )
    if 5 <= k_ratio <= 30:
        granularity_score = 20
        reasons["granularity_alignment"] = "K in [5, 30]"
    elif 2 <= k_ratio < 5 or 30 < k_ratio <= 80:
        granularity_score = 10
        reasons["granularity_alignment"] = "K in [2, 5) or (30, 80]"
        risk_tags.append("granularity_misaligned")
    else:
        granularity_score = 0
        reasons["granularity_alignment"] = "K < 2 or K > 80"
        risk_tags.append("granularity_invalid")

    severe_ok = 0 < metrics.serious_bug_rate <= 0.10
    easy_ok = 0 < metrics.easy_detect_bug_rate <= 0.10
    no_activity = (
        metrics.monthly_requirement_throughput == 0
        and metrics.monthly_bug_closed == 0
        and metrics.monthly_release_frequency == 0
    )
    if severe_ok and easy_ok:
        quality_score = 20
        reasons["quality_management"] = "0 < S <= 10% and 0 < L <= 10%"
    elif metrics.serious_bug_rate == 0 and metrics.easy_detect_bug_rate == 0:
        if no_activity and rhythm_score == 0:
            quality_score = 0
            reasons["quality_management"] = "no operational activity"
        else:
            quality_score = 5
            reasons["quality_management"] = "both S and L are 0"
    elif metrics.serious_bug_rate == 0 or metrics.easy_detect_bug_rate == 0:
        if severe_ok or easy_ok:
            quality_score = 15
            reasons["quality_management"] = "only one of S or L is 0"
        else:
            quality_score = 10
            reasons["quality_management"] = "one of S or L is 0 and the other exceeds the target"
        risk_tags.append("quality_classification_suspect")
    elif severe_ok or easy_ok:
        quality_score = 15
        reasons["quality_management"] = "only one of S or L meets the target"
        risk_tags.append("quality_ratio_partially_valid")
    else:
        quality_score = 10
        reasons["quality_management"] = "S > 10% or L > 10%"
        risk_tags.append("quality_ratio_exceeds_threshold")

    coverage_score = link_score + release_score
    process_norm_score = rhythm_score + granularity_score + quality_score
    total_score = coverage_score + process_norm_score
    level = (
        "qualified"
        if total_score >= 80
        else "warning"
        if total_score >= 60
        else "invalid"
    )

    return RdhsScoreCard(
        metrics=metrics,
        total_score=total_score,
        level=level,
        coverage_score=coverage_score,
        process_norm_score=process_norm_score,
        link_score=link_score,
        release_score=release_score,
        timeliness_score=rhythm_score,
        granularity_score=granularity_score,
        quality_score=quality_score,
        risk_tags=sorted(set(risk_tags)),
        reasons=reasons,
        timeliness_ratio_r=r_ratio,
        granularity_ratio_k=k_ratio,
    )
