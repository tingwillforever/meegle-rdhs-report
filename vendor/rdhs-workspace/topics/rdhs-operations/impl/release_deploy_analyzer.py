from __future__ import annotations

from collections import Counter, defaultdict

from impl.release_deploy_models import (
    BusinessSummary,
    Overview,
    ReleasePlanDetail,
)
from shared.meego.business_lines import BusinessLineDimension


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator * 100 / denominator, 1)


def _risk_score(
    release_plan_total: int,
    deploy_task_total: int,
    digital_penetration_rate: float,
    kubelink_release_penetration_rate: float,
    deploy_termination_rate: float,
) -> float:
    if release_plan_total == 0 and deploy_task_total == 0:
        return 0.0

    base_risk = (
        (100.0 - digital_penetration_rate) * 0.35
        + (100.0 - kubelink_release_penetration_rate) * 0.15
        + deploy_termination_rate * 0.50
    )
    volume_factor = (
        1.0 if (release_plan_total >= 10 or deploy_task_total >= 50) else 0.7
    )
    return round(base_risk * volume_factor, 1)


def _has_completed_deploy(detail: ReleasePlanDetail) -> bool:
    return int(detail.deploy_status_counts.get("部署完成", 0)) > 0


def _completion_rate_excluding_terminated(
    deploy_completed: int,
    deploy_task_total: int,
    deploy_terminated: int,
) -> float:
    effective_total = max(deploy_task_total - deploy_terminated, 0)
    return _rate(deploy_completed, effective_total)


def build_business_summaries(
    details: list[ReleasePlanDetail],
    business_dimensions: list[BusinessLineDimension] | None = None,
) -> list[BusinessSummary]:
    rollup: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {
            "release_plan_total": 0,
            "release_plan_with_deploy_task_total": 0,
            "release_plan_with_kubelink_task_total": 0,
            "deploy_task_total": 0,
            "kubelink_task_total": 0,
            "deploy_status_counts": Counter(),
            "release_plan_status_counts": Counter(),
        }
    )

    for detail in details:
        level1_business_line = detail.level1_business_line or detail.business_line
        level2_business_line = detail.level2_business_line
        key = (level1_business_line, level2_business_line)
        row = rollup[key]
        row["release_plan_total"] += 1
        if _has_completed_deploy(detail):
            row["release_plan_with_deploy_task_total"] += 1
        if detail.kubelink_task_count > 0:
            row["release_plan_with_kubelink_task_total"] += 1
        row["deploy_task_total"] += detail.deploy_task_count
        row["kubelink_task_total"] += detail.kubelink_task_count
        row["deploy_status_counts"].update(detail.deploy_status_counts)
        if detail.release_plan_status:
            row["release_plan_status_counts"].update([detail.release_plan_status])

    if business_dimensions:
        for dimension in business_dimensions:
            rollup.setdefault(
                (dimension.level1_business_line, dimension.level2_business_line),
                {
                    "release_plan_total": 0,
                    "release_plan_with_deploy_task_total": 0,
                    "release_plan_with_kubelink_task_total": 0,
                    "deploy_task_total": 0,
                    "kubelink_task_total": 0,
                    "deploy_status_counts": Counter(),
                    "release_plan_status_counts": Counter(),
                },
            )

    summaries: list[BusinessSummary] = []
    for (level1_business_line, level2_business_line), row in sorted(
        rollup.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        deploy_status_counts = dict(sorted(row["deploy_status_counts"].items()))
        release_plan_status_counts = dict(
            sorted(row["release_plan_status_counts"].items())
        )
        deploy_task_total = int(row["deploy_task_total"])
        deploy_completed = int(deploy_status_counts.get("部署完成", 0))
        deploy_terminated = int(deploy_status_counts.get("部署终止", 0))
        kubelink_task_total = int(row["kubelink_task_total"])
        release_plan_total = int(row["release_plan_total"])
        release_plan_with_kubelink_task_total = int(
            row["release_plan_with_kubelink_task_total"]
        )
        digital_penetration_rate = _rate(
            int(row["release_plan_with_deploy_task_total"]),
            release_plan_total,
        )
        kubelink_release_penetration_rate = _rate(
            release_plan_with_kubelink_task_total, release_plan_total
        )
        kubelink_task_rate = (
            _rate(kubelink_task_total, deploy_task_total) if deploy_task_total else None
        )
        deploy_completion_rate = _completion_rate_excluding_terminated(
            deploy_completed, deploy_task_total, deploy_terminated
        )
        deploy_termination_rate = (
            _rate(deploy_terminated, deploy_task_total) if deploy_task_total else 0.0
        )
        released_plan_count = int(release_plan_status_counts.get("已完成", 0))
        business_line = level2_business_line or level1_business_line
        summaries.append(
            BusinessSummary(
                business_line=business_line,
                level1_business_line=level1_business_line,
                level2_business_line=level2_business_line,
                release_plan_total=release_plan_total,
                release_plan_with_deploy_task_total=int(
                    row["release_plan_with_deploy_task_total"]
                ),
                digital_penetration_rate=digital_penetration_rate,
                deploy_task_total=deploy_task_total,
                deploy_status_counts=deploy_status_counts,
                deploy_completion_rate=deploy_completion_rate,
                release_plan_with_kubelink_task_total=release_plan_with_kubelink_task_total,
                kubelink_release_penetration_rate=kubelink_release_penetration_rate,
                kubelink_task_total=kubelink_task_total,
                kubelink_task_rate=kubelink_task_rate,
                deploy_termination_rate=deploy_termination_rate,
                risk_score=_risk_score(
                    release_plan_total=release_plan_total,
                    deploy_task_total=deploy_task_total,
                    digital_penetration_rate=digital_penetration_rate,
                    kubelink_release_penetration_rate=kubelink_release_penetration_rate,
                    deploy_termination_rate=deploy_termination_rate,
                ),
                release_plan_status_counts=release_plan_status_counts,
                released_plan_count=released_plan_count,
            )
        )
    return summaries


def build_overview(details: list[ReleasePlanDetail]) -> Overview:
    release_plan_total = len(details)
    release_plan_with_deploy_task_total = sum(
        1 for detail in details if _has_completed_deploy(detail)
    )
    release_plan_with_kubelink_task_total = sum(
        1 for detail in details if detail.kubelink_task_count > 0
    )
    deploy_status_counts = Counter()
    release_plan_status_counts = Counter()
    deploy_task_total = 0
    kubelink_task_total = 0
    for detail in details:
        deploy_status_counts.update(detail.deploy_status_counts)
        deploy_task_total += detail.deploy_task_count
        kubelink_task_total += detail.kubelink_task_count
        if detail.release_plan_status:
            release_plan_status_counts.update([detail.release_plan_status])
    deploy_terminated = int(deploy_status_counts.get("部署终止", 0))
    released_plan_count = int(release_plan_status_counts.get("已完成", 0))
    return Overview(
        release_plan_total=release_plan_total,
        release_plan_with_deploy_task_total=release_plan_with_deploy_task_total,
        digital_penetration_rate=_rate(
            release_plan_with_deploy_task_total, release_plan_total
        ),
        deploy_task_total=deploy_task_total,
        deploy_status_counts=dict(sorted(deploy_status_counts.items())),
        release_plan_with_kubelink_task_total=release_plan_with_kubelink_task_total,
        kubelink_release_penetration_rate=_rate(
            release_plan_with_kubelink_task_total, release_plan_total
        ),
        kubelink_task_total=kubelink_task_total,
        kubelink_task_rate=_rate(kubelink_task_total, deploy_task_total)
        if deploy_task_total
        else None,
        deploy_termination_rate=_rate(deploy_terminated, deploy_task_total)
        if deploy_task_total
        else 0.0,
        release_plan_status_counts=dict(sorted(release_plan_status_counts.items())),
        released_plan_count=released_plan_count,
    )
