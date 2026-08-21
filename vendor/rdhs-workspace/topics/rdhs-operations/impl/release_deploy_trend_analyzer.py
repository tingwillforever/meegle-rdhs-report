from __future__ import annotations

from typing import Any


def compute_mom_change(
    current: dict[str, Any],
    previous: dict[str, Any],
    field: str,
) -> float:
    current_value = current.get(field)
    previous_value = previous.get(field)
    if current_value is None or previous_value is None:
        return 0.0
    current_num = (
        float(current_value) if isinstance(current_value, str) else float(current_value)
    )
    previous_num = (
        float(previous_value)
        if isinstance(previous_value, str)
        else float(previous_value)
    )
    return round(current_num - previous_num, 1)


def compute_business_line_mom(
    summaries: list[dict[str, Any]],
    current_month: str,
    previous_month: str,
) -> list[dict[str, Any]]:
    current_rows = {
        row["business_line"]: row
        for row in summaries
        if row.get("month") == current_month
    }
    previous_rows = {
        row["business_line"]: row
        for row in summaries
        if row.get("month") == previous_month
    }
    results: list[dict[str, Any]] = []
    fields_to_compare = [
        "risk_score",
        "release_plan_total",
        "deploy_task_total",
        "digital_penetration_rate",
        "deploy_termination_rate",
    ]
    for business_line, current in current_rows.items():
        previous = previous_rows.get(business_line)
        if previous is None:
            continue
        row: dict[str, Any] = {
            "business_line": business_line,
            "current_month": current_month,
            "previous_month": previous_month,
            "current_risk_score": float(current.get("risk_score", 0)),
            "previous_risk_score": float(previous.get("risk_score", 0)),
        }
        for field in fields_to_compare:
            row[f"{field}_mom"] = compute_mom_change(current, previous, field)
        results.append(row)
    return sorted(results, key=lambda r: -r.get("risk_score_mom", 0))


def identify_consistent_top_risks(
    summaries: list[dict[str, Any]],
    min_months: int,
    rank_threshold: int = 3,
) -> list[dict[str, Any]]:
    business_line_months: dict[str, list[dict[str, Any]]] = {}
    for row in summaries:
        business_line = row.get("business_line")
        if business_line is None:
            continue
        rank_str = row.get("risk_rank")
        if rank_str is None:
            continue
        rank = int(rank_str) if isinstance(rank_str, str) else int(rank_str)
        if rank > rank_threshold:
            continue
        if business_line not in business_line_months:
            business_line_months[business_line] = []
        business_line_months[business_line].append(row)
    results: list[dict[str, Any]] = []
    for business_line, months_data in business_line_months.items():
        if len(months_data) < min_months:
            continue
        avg_risk = sum(float(m.get("risk_score", 0)) for m in months_data) / len(
            months_data
        )
        results.append(
            {
                "business_line": business_line,
                "months_in_top_risk": len(months_data),
                "avg_risk_score": round(avg_risk, 1),
                "max_risk_score": max(
                    float(m.get("risk_score", 0)) for m in months_data
                ),
                "months": sorted(m.get("month", "") for m in months_data),
            }
        )
    return sorted(
        results, key=lambda r: (-r["months_in_top_risk"], -r["avg_risk_score"])
    )
