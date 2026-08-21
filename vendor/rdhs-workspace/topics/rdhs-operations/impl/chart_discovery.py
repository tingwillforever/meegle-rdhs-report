"""RDHS 专题图表发现与字段映射。"""

from __future__ import annotations

from shared.browser.chart_discovery import build_bql_filter_from_view_config
from shared.browser.chart_discovery import discover_chart_catalog
from shared.browser.chart_discovery import extract_quick_filters_from_view_config
from shared.browser.chart_discovery import extract_quick_filter_id
from shared.browser.chart_discovery import extract_view_id
from shared.browser.chart_discovery import fetch_view_config


CHART_FIELD_MAPPING = {
    "月均需求吞吐量": "monthly_requirement_throughput",
    "需求吞吐量": "monthly_requirement_throughput",
    "月均缺陷关闭量": "monthly_bug_closed",
    "月均发布频率": "monthly_release_frequency",
    "发布频率(次)": "monthly_release_frequency",
    "平均开发周期": "avg_dev_cycle_days",
    "需求开发周期(天)": "avg_dev_cycle_days",
    "平均交付周期": "avg_delivery_cycle_days",
    "需求交付周期(天)": "avg_delivery_cycle_days",
    "需求交付周期": "avg_delivery_cycle_days",
    "严重及以上缺陷占比": "serious_bug_rate",
    "严重缺陷占比": "serious_bug_rate",
    "容易发现缺陷占比": "easy_detect_bug_rate",
    "低级缺陷占比": "easy_detect_bug_rate",
    "需求开发周期": "avg_dev_cycle_days",
}


def map_chart_name_to_metric_field(chart_name: str) -> str:
    return CHART_FIELD_MAPPING.get(chart_name, "")


__all__ = [
    "build_bql_filter_from_view_config",
    "discover_chart_catalog",
    "extract_quick_filters_from_view_config",
    "extract_quick_filter_id",
    "extract_view_id",
    "fetch_view_config",
    "map_chart_name_to_metric_field",
]
