"""将 direct Meegle 图表响应转换为经过严格校验的 RDHS 快照。"""

from __future__ import annotations

import hashlib
import json
from math import isfinite
from typing import Iterator

from impl.periodic_report_models import ChartSnapshot
from impl.periodic_report_models import COMPONENT_FIELDS
from impl.periodic_report_models import GOVERNANCE_TEXT_FIELDS
from impl.periodic_report_models import ProductMetricRecord
from impl.periodic_report_models import RDHS_FIELD
from impl.periodic_report_models import SnapshotAudit


_DIMENSION_FIELDS = ("一级业务线", "产品")
_EMPTY_VALUES = {"", "(空)"}


def _source_sha256(raw_payload: dict[str, object]) -> str:
    normalized = json.dumps(
        raw_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _as_number(value: object, *, field: str, business_line: str, product: str) -> float:
    if value is None or str(value).strip() == "":
        raise ValueError(f"missing numeric value for {field}: {business_line} / {product}")
    try:
        numeric_value = float(str(value).strip())
    except ValueError as exc:
        raise ValueError(
            f"invalid numeric value for {field}: {business_line} / {product}: {value!r}"
        ) from exc
    if not isfinite(numeric_value):
        raise ValueError(
            f"non-finite numeric value for {field}: {business_line} / {product}: {value!r}"
        )
    return numeric_value


def _is_empty(value: object) -> bool:
    return str(value or "").strip() in _EMPTY_VALUES


def _iter_chart_rows(value: object) -> Iterator[dict[str, object]]:
    if isinstance(value, dict):
        if "dim" in value and "value" in value:
            yield value
            return
        for nested in value.values():
            yield from _iter_chart_rows(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_chart_rows(nested)


def _map_values(
    values: object,
    titles: list[str],
    *,
    row_label: str,
) -> dict[str, object]:
    if not isinstance(values, dict):
        raise ValueError(f"{row_label} has no value map")

    mapped: dict[str, object] = {}
    for index, title in enumerate(titles):
        mapped[title] = values.get(str(index), values.get(title))
    return mapped


def _chart_payload(raw_payload: dict[str, object]) -> dict[str, object]:
    payload = raw_payload.get("data")
    if not isinstance(payload, dict):
        raise ValueError("chart response has no data payload")
    return payload


def parse_chart_snapshot(
    raw_payload: dict[str, object],
    *,
    chart_id: str,
    fetched_at: str,
) -> ChartSnapshot:
    """解析产品 RDHS 图表，并拒绝任何可能导致错报的残缺数据。"""
    payload = _chart_payload(raw_payload)
    dimensions = payload.get("dim_titles")
    quotas = payload.get("quota_titles")
    if not isinstance(dimensions, list) or not isinstance(quotas, list):
        raise ValueError("chart response has no dimensions or quotas")
    if list(dimensions) != list(_DIMENSION_FIELDS):
        raise ValueError(f"unexpected chart dimensions: {dimensions!r}")

    quota_titles = [str(item) for item in quotas]
    for required_field in (RDHS_FIELD, *COMPONENT_FIELDS, *GOVERNANCE_TEXT_FIELDS):
        if required_field not in quota_titles:
            raise ValueError(f"missing required quota: {required_field}")

    raw_rows = list(_iter_chart_rows(payload.get("chart_data_list", [])))
    records: list[ProductMetricRecord] = []
    seen_keys: set[tuple[str, str]] = set()
    zero_rdhs_row_count = 0
    empty_dimension_row_count = 0

    for raw_row in raw_rows:
        dimensions_by_name = _map_values(
            raw_row.get("dim"),
            list(dimensions),
            row_label="chart row",
        )
        business_line = str(dimensions_by_name["一级业务线"] or "").strip()
        product = str(dimensions_by_name["产品"] or "").strip()
        quota_by_name = _map_values(
            raw_row.get("value"),
            quota_titles,
            row_label=f"chart row {business_line} / {product}",
        )
        rdhs = _as_number(
            quota_by_name[RDHS_FIELD],
            field=RDHS_FIELD,
            business_line=business_line,
            product=product,
        )
        if rdhs <= 0:
            zero_rdhs_row_count += 1
            continue
        if _is_empty(business_line) or _is_empty(product):
            empty_dimension_row_count += 1
            continue

        key = (business_line, product)
        if key in seen_keys:
            raise ValueError(f"duplicate product key after filtering: {business_line} / {product}")
        seen_keys.add(key)

        metrics = {
            title: _as_number(
                value,
                field=title,
                business_line=business_line,
                product=product,
            )
            for title, value in quota_by_name.items()
        }
        records.append(
            ProductMetricRecord(
                business_line=business_line,
                product=product,
                metrics=metrics,
            )
        )

    audit = SnapshotAudit(
        chart_id=chart_id,
        chart_name=str(payload.get("name", "")),
        fetched_at=fetched_at,
        source_sha256=_source_sha256(raw_payload),
        raw_row_count=len(raw_rows),
        zero_rdhs_row_count=zero_rdhs_row_count,
        empty_dimension_row_count=empty_dimension_row_count,
        accepted_row_count=len(records),
    )
    return ChartSnapshot(
        chart_id=chart_id,
        chart_name=audit.chart_name,
        fetched_at=fetched_at,
        quota_titles=tuple(quota_titles),
        records=tuple(records),
        audit=audit,
    )
