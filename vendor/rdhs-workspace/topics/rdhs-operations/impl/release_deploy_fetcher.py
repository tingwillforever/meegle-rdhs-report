from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from shared.meego.business_lines import fetch_business_dimensions
from shared.meego.client import MeegoMCPClient

RELEASE_PLAN_TYPE_KEY = "69662b23c736e8d336c81994"
CREATED_TIME_SECONDS_FIELD_KEY = "field_cc4d12"
TIMEZONE = ZoneInfo("Asia/Shanghai")


def month_range(month: str) -> tuple[str, str]:
    start = datetime.strptime(f"{month}-01", "%Y-%m-%d").replace(tzinfo=TIMEZONE)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    return start.strftime("%Y-%m-%d %H:%M:%S"), next_month.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def fetch_release_plans(
    client: MeegoMCPClient, month: str, page_size: int = 50
) -> list[dict[str, Any]]:
    start_at, end_at = month_range(month)
    page_num = 1
    items: list[dict[str, Any]] = []

    while True:
        response = client.call_tool(
            "get_work_items",
            {
                "work_item_type_key": RELEASE_PLAN_TYPE_KEY,
                "page_num": page_num,
                "page_size": page_size,
                "fields": [
                    "business",
                    CREATED_TIME_SECONDS_FIELD_KEY,
                    "work_item_status",
                ],
                "field_filters": [
                    {
                        "field_key": CREATED_TIME_SECONDS_FIELD_KEY,
                        "operator": ">=",
                        "value": start_at,
                    },
                    {
                        "field_key": CREATED_TIME_SECONDS_FIELD_KEY,
                        "operator": "<",
                        "value": end_at,
                    },
                ],
            },
        )
        work_items = response.get("work_items", [])
        items.extend(work_items)
        total = int(response.get("total", len(items)))
        if len(items) >= total or not work_items:
            return items
        page_num += 1


__all__ = [
    "CREATED_TIME_SECONDS_FIELD_KEY",
    "MeegoMCPClient",
    "fetch_business_dimensions",
    "fetch_release_plans",
]
