#!/usr/bin/env python3
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rdhs_query import (
    ARCHIVE_TTL,
    CURRENT_CHART_ID,
    LAST_CHART_ID,
    MAX_MASTER_PAGES,
    SECONDARY_LINE_TREND_CHART_ID,
    chart_period,
    current_period,
    fetch_master_items,
    format_governance_entries,
    format_full_leaderboard,
    format_product_candidates,
    format_trend_judgement,
    is_eligible_product,
    parse_trend_rows,
    period_banner,
    previous_period,
    summarize_scope,
    ttl_for_chart,
)


class RdhsQueryTest(unittest.TestCase):
    def test_scope_average_excludes_missing_measurements(self):
        matched = [
            ("产品A", {"rdhs": 40}, {"rdhs": 50}, {}),
            ("产品B", {"rdhs": 80}, {"rdhs": 70}, {}),
            ("产品C", None, None, {}),
        ]
        summary = summarize_scope(matched)

        self.assertEqual(summary["audit_average_rdhs"], 40.0)
        self.assertEqual(summary["measured_average_rdhs"], 60.0)
        self.assertEqual(summary["average_rdhs"], 60)
        self.assertEqual(summary["comparison_count"], 2)
        self.assertEqual(summary["comparison_current_average"], 60)
        self.assertEqual(summary["last_average_rdhs"], 60)
        self.assertEqual(summary["eligible_count"], 3)
        self.assertEqual(summary["measured_count"], 2)
        self.assertAlmostEqual(summary["coverage"], 2 / 3)
        self.assertEqual(summary["missing_products"], ["产品C"])
        self.assertEqual(summary["tiers"], {"P0": 1, "P1": 0, "P2": 0, "达标": 1})

    def test_eligibility_requires_governed_active_product(self):
        base = {"is_in_progress": True, "is_custom": False, "business_path": "一级/二级"}
        self.assertTrue(is_eligible_product(base))
        self.assertFalse(is_eligible_product({**base, "is_in_progress": False}))
        self.assertFalse(is_eligible_product({**base, "is_custom": True}))
        self.assertFalse(is_eligible_product({**base, "business_path": "测试业务线/二级"}))

    def test_trend_uses_latest_six_complete_months_and_requested_line(self):
        titles = ["人均需求吞吐量"]
        current_month = "2026-10"
        rows = [
            {"dim": {"0": f"2026-{month:02d}", "1": "业务线A"}, "value": {"0": str(month)}}
            for month in range(1, 9)
        ] + [
            {"dim": {"0": "2026-08", "1": "业务线B"}, "value": {"0": "99"}},
            {"dim": {"0": current_month, "1": "业务线A"}, "value": {"0": "100"}},
        ]

        parsed = parse_trend_rows(titles, rows, "业务线A", now=datetime(2026, 10, 9))

        self.assertEqual([item["month"] for item in parsed], ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"])
        self.assertEqual(parsed[-1]["metrics"]["人均需求吞吐量"], "8")

    def test_scope_report_keeps_complete_original_product_leaderboard(self):
        master_a = {
            "business_path": "一级/二级",
            "product_attr": "标准产品",
            "is_in_progress": True,
            "prod_rep": "产品甲",
            "pm_rep": "项目甲",
        }
        master_b = {**master_a, "prod_rep": "产品乙", "pm_rep": "项目乙"}
        matched = [
            ("产品A", {"rdhs": 40, "business_line_chart": "一级", "metrics": {}}, None, master_a),
            ("产品B", {"rdhs": 80, "business_line_chart": "一级", "metrics": {}}, None, master_b),
            ("产品C", None, None, master_a),
        ]

        report = format_full_leaderboard(matched)

        self.assertIn("完整产品诊断榜单（共 3 款）", report)
        self.assertIn("产品A", report)
        self.assertIn("产品B", report)
        self.assertIn("产品C", report)
        self.assertIn("产品甲", report)
        self.assertIn("未度量 / 数据治理", report)
        self.assertNotIn("P0 数据治理", report)
        self.assertNotIn("重点穿透产品", report)

    def test_secondary_trend_filters_both_line_dimensions(self):
        titles = ["人均需求吞吐量"]
        rows = [
            {"dim": {"0": "2026-08", "1": "一级A", "2": "二级A"}, "value": {"0": "1.2"}},
            {"dim": {"0": "2026-08", "1": "一级A", "2": "二级B"}, "value": {"0": "2.4"}},
        ]

        parsed = parse_trend_rows(titles, rows, "一级A", "二级A", now=datetime(2026, 10, 9))

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["metrics"]["人均需求吞吐量"], "1.2")

    def test_governance_entries_prioritize_actionable_product_facts(self):
        master = {"prod_rep": "产品甲", "pm_rep": "项目甲"}
        matched = [
            ("待核实", {"rdhs": 13, "metrics": {"有效参与人数": "1", "人均需求吞吐量": "0", "人均缺陷关闭量": "0", "需求在途时长": "100", "积压需求占比": "1"}}, None, master),
            ("交付断链", {"rdhs": 33, "metrics": {"有效参与人数": "14", "人均需求吞吐量": "0", "人均缺陷关闭量": "2", "需求在途时长": "20", "积压需求占比": "0"}}, None, {"prod_rep": "-", "pm_rep": "-"}),
            ("积压失控", {"rdhs": 71, "metrics": {"有效参与人数": "45", "人均需求吞吐量": "1", "人均缺陷关闭量": "2", "需求在途时长": "217", "积压需求占比": "0.49"}}, None, master),
        ]

        report = format_governance_entries(matched)

        for text in ["状态/数据待核实", "交付断链", "积压失控", "第一动作", "产品甲", "先补齐责任角色"]:
            self.assertIn(text, report)

    def test_trend_judgement_summarizes_latest_month_change(self):
        rows = [
            {"month": "2026-07", "metrics": {"人均需求吞吐量": "1", "需求总量": "10", "需求交付周期": "20", "严重缺陷占比": "0.1"}},
            {"month": "2026-08", "metrics": {"人均需求吞吐量": "2", "需求总量": "20", "需求交付周期": "30", "严重缺陷占比": "0.05"}},
        ]

        judgement = "\n".join(format_trend_judgement(rows))

        self.assertIn("需求完成量 10 → 20", judgement)
        self.assertIn("拉长", judgement)
        self.assertIn("比例变化", judgement)

    def test_trend_judgement_does_not_call_zero_cycles_stable(self):
        rows = [
            {"month": "2026-07", "metrics": {"人均需求吞吐量": "0", "需求总量": "0", "需求交付周期": "0", "严重缺陷占比": "0"}},
            {"month": "2026-08", "metrics": {"人均需求吞吐量": "0", "需求总量": "0", "需求交付周期": "0", "严重缺陷占比": "0.05"}},
        ]

        judgement = "\n".join(format_trend_judgement(rows))

        self.assertIn("周期有效样本", judgement)
        self.assertNotIn("0.00 → 0.00 天（持平）", judgement)

    def test_current_month_chart_stays_realtime_while_archives_are_cached(self):
        # 当月实时图表默认 ttl=0 直连；归档与历史过程趋势图保底 300 秒短缓冲
        self.assertEqual(ttl_for_chart(CURRENT_CHART_ID, 0), 0)
        self.assertEqual(ttl_for_chart(CURRENT_CHART_ID, 3600), 3600)
        self.assertEqual(ttl_for_chart(LAST_CHART_ID, 0), 300)
        self.assertEqual(ttl_for_chart(SECONDARY_LINE_TREND_CHART_ID, 0), 300)
        self.assertEqual(ttl_for_chart(LAST_CHART_ID, 7200), 7200)

    def test_chart_periods_are_derived_not_hardcoded(self):
        anchor = datetime(2026, 10, 9, 11, 0)
        self.assertEqual(previous_period(anchor), "2026-09")
        self.assertEqual(current_period(anchor), "2026-10")
        self.assertEqual(chart_period(LAST_CHART_ID, anchor), "2026-09")
        self.assertEqual(chart_period(CURRENT_CHART_ID, anchor), "2026-10")
        self.assertIsNone(chart_period(SECONDARY_LINE_TREND_CHART_ID, anchor))
        self.assertIn("2026-09", period_banner(anchor))
        self.assertIn("2026-10", period_banner(anchor))

    def test_previous_period_crosses_year_boundary(self):
        self.assertEqual(previous_period(datetime(2027, 1, 5)), "2026-12")
        self.assertEqual(previous_period(datetime(2026, 1, 31)), "2025-12")
        self.assertEqual(previous_period(datetime(2026, 12, 1)), "2026-11")

    def test_master_pagination_collects_every_page(self):
        import rdhs_query

        pages = {
            1: [{"id": i} for i in range(200)],
            2: [{"id": 200 + i} for i in range(200)],
            3: [{"id": 400 + i} for i in range(42)],
        }
        calls = []

        def fake_run(args):
            page = int(args[args.index("--page-num") + 1])
            calls.append(page)
            return pages.get(page, [])

        original = rdhs_query.run_meegle_cmd
        rdhs_query.run_meegle_cmd = fake_run
        try:
            items = fetch_master_items()
        finally:
            rdhs_query.run_meegle_cmd = original

        self.assertEqual(len(items), 442)
        self.assertEqual(calls, [1, 2, 3])

    def test_master_pagination_fails_loudly_instead_of_truncating(self):
        import rdhs_query

        original = rdhs_query.run_meegle_cmd
        rdhs_query.run_meegle_cmd = lambda args: [{"id": i} for i in range(200)]
        try:
            with self.assertRaises(RuntimeError) as caught:
                fetch_master_items()
        finally:
            rdhs_query.run_meegle_cmd = original

        self.assertIn(str(200 * MAX_MASTER_PAGES), str(caught.exception))

    def test_fuzzy_product_matches_are_candidates_not_an_average(self):
        matched = [
            ("星火A", {"rdhs": 40}, None, {"business_path": "一级/二级"}),
            ("星火B", {"rdhs": 80}, None, {"business_path": "一级/二级"}),
        ]

        report = format_product_candidates("星火", matched)

        self.assertIn("请选择具体产品", report)
        self.assertIn("星火A", report)
        self.assertIn("星火B", report)
        self.assertNotIn("算术平均", report)

    def test_parse_chart_rows_deduplicates_phantom_empty_business_lines(self):
        import rdhs_query
        titles = list(rdhs_query.REQUIRED_METRICS)

        def make_row(b, p, score):
            vals = {"0": str(score)}
            vals["1"] = str(score * 0.25)
            vals["2"] = str(score * 0.15)
            vals["3"] = str(score * 0.20)
            vals["4"] = str(score * 0.20)
            vals["5"] = str(score * 0.20)
            for i in range(6, len(titles)):
                vals[str(i)] = "0"
            return {"dim": {"0": b, "1": p}, "is_zero_spec": False, "value": vals}

        rows = [
            make_row("(空)", "产品A", 70),
            make_row("业务线1", "产品A", 70),
            make_row("业务线1", "测试工具", 50),
        ]
        master = {
            "产品A": {"business_path": "业务线1/二级", "product_attr": "标准产品", "is_in_progress": True},
            "测试工具": {"business_path": "测试业务线/测试", "product_attr": "标准产品", "is_in_progress": True},
        }
        prods = rdhs_query.parse_chart_rows(titles, rows, master)
        self.assertIn("产品A", prods)
        self.assertEqual(prods["产品A"]["business_line_chart"], "业务线1")
        self.assertNotIn("测试工具", prods)


if __name__ == "__main__":
    unittest.main()
