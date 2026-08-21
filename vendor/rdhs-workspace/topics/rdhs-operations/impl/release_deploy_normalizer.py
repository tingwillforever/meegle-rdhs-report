from __future__ import annotations

from collections import Counter
from typing import Any

from impl.release_deploy_fetcher import CREATED_TIME_SECONDS_FIELD_KEY
from impl.release_deploy_models import KubelinkConfig, ReleasePlanDetail
from shared.meego.business_lines import BusinessLineDimension


def field_value_map(work_item: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in work_item.get("fields", []):
        field_key = field.get("field_key")
        field_alias = field.get("field_alias")
        value = field.get("field_value")
        if field_key:
            values[field_key] = value
        if field_alias:
            values[field_alias] = value
    return values


def extract_business_line(work_item: dict[str, Any]) -> str:
    values = field_value_map(work_item)
    business = values.get("business")
    if isinstance(business, dict) and business.get("label"):
        return str(business["label"])
    return "未填写业务线"


def extract_business_hierarchy(
    work_item: dict[str, Any],
    business_dimensions: dict[str, BusinessLineDimension] | None = None,
) -> BusinessLineDimension:
    business_line = extract_business_line(work_item)
    if business_dimensions:
        dimension = business_dimensions.get(business_line)
        if dimension is not None:
            return dimension
    return BusinessLineDimension(
        level1_business_line=business_line if business_line != "未填写业务线" else "",
        level2_business_line="",
    )


def extract_created_at(work_item: dict[str, Any]) -> str:
    for field in work_item.get("fields", []):
        if field.get("field_key") == CREATED_TIME_SECONDS_FIELD_KEY:
            formatted = field.get("field_value_formatted")
            if formatted:
                return str(formatted)
            raw = field.get("field_value")
            if isinstance(raw, dict) and raw.get("formatted"):
                return str(raw["formatted"])
    return ""


def extract_release_plan_status(work_item: dict[str, Any]) -> str:
    status = work_item.get("work_item_status")
    if isinstance(status, dict) and status.get("state_name"):
        return str(status["state_name"])
    values = field_value_map(work_item)
    status = values.get("work_item_status")
    if isinstance(status, dict) and status.get("label"):
        return str(status["label"])
    return ""


def normalize_tasks(
    payload: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("tasks", "deploy_tasks", "items", "list"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("tasks", "deploy_tasks", "items", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def normalize_status(task: dict[str, Any]) -> str:
    for key in (
        "deploy_status",
        "status",
        "deployStatus",
        "deployment_status",
        "deploy_status_desc",
    ):
        value = task.get(key)
        if value:
            return str(value)
    return "未知状态"


def _matches_kubelink(task: dict[str, Any], config: KubelinkConfig) -> bool:
    if config.mode == "all_deploy_tasks":
        return True
    if config.mode == "k8s_helm_signals":
        cluster = str(task.get("cluster", "")).casefold()
        artifact_repo = str(task.get("artifact_repo", "")).casefold()
        artifact_package = str(task.get("artifact_package", "")).casefold()
        return "k8s" in cluster and (
            "helm" in artifact_repo or "helm" in artifact_package
        )
    if config.mode != "keyword_match":
        return False

    keywords = [keyword.casefold() for keyword in config.keywords if keyword]
    if not keywords:
        return False

    fields = config.match_fields or [
        "app_name",
        "cluster",
        "namespace",
        "artifact_package",
    ]
    haystacks = [str(task.get(field, "")).casefold() for field in fields]
    return any(keyword in haystack for keyword in keywords for haystack in haystacks)


def annotate_tasks_with_kubelink(
    tasks: list[dict[str, Any]], config: KubelinkConfig | None = None
) -> list[dict[str, Any]]:
    kubelink_config = config or KubelinkConfig(mode="disabled", rule_version="disabled")
    annotated: list[dict[str, Any]] = []
    for task in tasks:
        payload = dict(task)
        payload["is_kubelink_task"] = _matches_kubelink(payload, kubelink_config)
        payload["kubelink_rule_version"] = kubelink_config.rule_version
        annotated.append(payload)
    return annotated


def build_release_plan_detail(
    work_item: dict[str, Any],
    tasks_payload: dict[str, Any] | list[dict[str, Any]],
    kubelink_config: KubelinkConfig | None = None,
    business_dimensions: dict[str, BusinessLineDimension] | None = None,
) -> ReleasePlanDetail:
    tasks = annotate_tasks_with_kubelink(
        normalize_tasks(tasks_payload), kubelink_config
    )
    status_counts = Counter(normalize_status(task) for task in tasks)
    hierarchy = extract_business_hierarchy(work_item, business_dimensions)
    return ReleasePlanDetail(
        release_plan_id=int(work_item.get("work_item_id") or work_item.get("id")),
        name=str(work_item.get("name", "")),
        business_line=hierarchy.business_line,
        created_at=extract_created_at(work_item),
        level1_business_line=hierarchy.level1_business_line,
        level2_business_line=hierarchy.level2_business_line,
        release_plan_status=extract_release_plan_status(work_item),
        deploy_task_count=len(tasks),
        deploy_status_counts=dict(sorted(status_counts.items())),
        deploy_tasks=tasks,
        kubelink_task_count=sum(1 for task in tasks if task.get("is_kubelink_task")),
    )
