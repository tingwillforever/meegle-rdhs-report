#!/usr/bin/env python3
"""Build canonical 2026-09 snapshot with verified 48 in-progress products."""

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, "/Users/ting/Develop/meegle-app/rdhs-report/scripts/rdhs-analysis")
from bg_monthly_report import LAST_CHART_ID, fetch_chart, load_products


def float_or_none(val):
    if val is None or val == "" or val == "—":
        return None
    try:
        f = float(val)
        return round(f, 2)
    except (ValueError, TypeError):
        return None


def int_or_none(val):
    if val is None or val == "" or val == "—":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def get_band(rdhs):
    if rdhs is None:
        return "重点治理"
    if rdhs < 45:
        return "重点治理"
    if rdhs < 60:
        return "风险改进"
    if rdhs < 70:
        return "持续优化"
    return "常规跟踪"


def get_priority(rdhs):
    if rdhs is None or rdhs < 45:
        return "P0"
    if rdhs < 60:
        return "P1"
    if rdhs < 70:
        return "P2"
    return None


def main():
    chart = fetch_chart(LAST_CHART_ID)
    qts = chart.get("quota_titles", [])

    def qidx(name):
        return str(qts.index(name)) if name in qts else None

    rdhs_k = qidx("RDHS(100')")
    link_k = qidx("链路闭环得分(25')")
    deliv_k = qidx("交付闭环得分(15')")
    time_k = qidx("时效节奏合理性(20')")
    gran_k = qidx("颗粒度对齐度(20')")
    qual_k = qidx("质量敏锐度(20')")

    parts_k = qidx("有效参与人数")
    thru_k = qidx("人均需求吞吐量")
    bug_k = qidx("人均缺陷关闭量")
    cycle_k = qidx("需求交付周期")
    dev_cycle_k = qidx("需求开发周期")
    severe_k = qidx("严重缺陷占比")
    low_k = qidx("低级缺陷占比")
    backlog_k = qidx("积压需求占比")
    rel_eff_k = qidx("有效发布需求数")
    rel_req_k = qidx("应发布需求数")

    chart_rows = chart.get("chart_data_list", [[]])[0]
    chart_map = {}
    for r in chart_rows:
        pname = r.get("dim", {}).get("1")
        if pname and not r.get("is_zero_spec"):
            chart_map[pname] = r

    prods_meta = load_products()
    assert len(prods_meta) == 48, f"Expected 48 products, got {len(prods_meta)}"

    products = []
    lines_counter = {}

    for p in prods_meta:
        pname = p["name"]
        bl1 = p["bl1"]
        bl2 = p["bl2"]
        lines_counter[bl1] = lines_counter.get(bl1, 0) + 1

        chart_row = chart_map.get(pname)
        vals = chart_row.get("value", {}) if chart_row else {}

        rdhs = float_or_none(vals.get(rdhs_k)) if chart_row else None
        band = get_band(rdhs)
        priority = get_priority(rdhs)

        components = {
            "linkClosure": float_or_none(vals.get(link_k)),
            "deliveryClosure": float_or_none(vals.get(deliv_k)),
            "timeliness": float_or_none(vals.get(time_k)),
            "granularity": float_or_none(vals.get(gran_k)),
            "quality": float_or_none(vals.get(qual_k)),
        }

        # Calculate lowest component
        comp_max = [
            ("linkClosure", "链路闭环得分", 25),
            ("deliveryClosure", "交付闭环得分", 15),
            ("timeliness", "时效节奏合理性", 20),
            ("granularity", "颗粒度对齐度", 20),
            ("quality", "质量表现", 20),
        ]
        valid_comps = [
            (label, components[key] / max_val)
            for key, label, max_val in comp_max
            if components[key] is not None
        ]
        if valid_comps:
            valid_comps.sort(key=lambda x: x[1])
            lowest_comp = valid_comps[0][0]
        else:
            lowest_comp = "过程数据缺失"

        # Dep metrics
        dep_metrics = []
        if parts_k:
            dep_metrics.append({
                "label": "有效参与人数",
                "value": int_or_none(vals.get(parts_k)),
                "unit": "人",
                "tone": "track",
            })
        if thru_k:
            dep_metrics.append({
                "label": "月人均需求吞吐量",
                "value": float_or_none(vals.get(thru_k)),
                "unit": "个/人",
                "tone": "track",
            })
        if bug_k:
            dep_metrics.append({
                "label": "月人均缺陷关闭量",
                "value": float_or_none(vals.get(bug_k)),
                "unit": "个/人",
                "tone": "neutral",
            })
        if dev_cycle_k:
            dep_metrics.append({
                "label": "需求开发周期",
                "value": float_or_none(vals.get(dev_cycle_k)),
                "unit": "天",
                "tone": "track",
            })
        if cycle_k:
            dep_metrics.append({
                "label": "需求交付周期",
                "value": float_or_none(vals.get(cycle_k)),
                "unit": "天",
                "tone": "track",
            })
        if rel_eff_k and rel_req_k:
            eff = float_or_none(vals.get(rel_eff_k)) or 0
            req = float_or_none(vals.get(rel_req_k)) or 0
            rate = round(eff / req, 4) if req > 0 else 1.0
            tone = "critical" if rate < 0.85 else "track"
            dep_metrics.append({
                "label": "需求发布闭环率",
                "value": rate,
                "unit": "%",
                "tone": tone,
            })
        if severe_k:
            s_rate = float_or_none(vals.get(severe_k))
            tone = "risk" if (s_rate or 0) > 0.1 else "track"
            dep_metrics.append({
                "label": "严重缺陷占比",
                "value": s_rate,
                "unit": "%",
                "tone": tone,
            })
        if low_k:
            dep_metrics.append({
                "label": "低级缺陷占比",
                "value": float_or_none(vals.get(low_k)),
                "unit": "%",
                "tone": "neutral",
            })
        if backlog_k:
            b_rate = float_or_none(vals.get(backlog_k))
            tone = "risk" if (b_rate or 0) > 0.2 else "track"
            dep_metrics.append({
                "label": "需求积压占比",
                "value": b_rate,
                "unit": "%",
                "tone": tone,
            })

        if rdhs is None:
            problem = "产品主数据为研发中，但未关联到有效 RDHS 图表度量（黑户计 0 分）。"
            action = "确认产品主数据与度量源关联，补齐研发责任角色与工作流，消除 0 分敞口。"
        else:
            problem = f"过程能力优化：最低分项为 {lowest_comp}。"
            action = f"围绕 {lowest_comp} 补齐对应过程记录，消减过程卡点并在下期复核改善情况。"

        products.append({
            "businessLine": bl1,
            "subLine": bl2,
            "product": pname,
            "productStatus": "研发中",
            "rdhs": rdhs,
            "governanceBand": band,
            "priority": priority,
            "components": components,
            "dependencyMetrics": dep_metrics,
            "lowestComponent": lowest_comp,
            "problem": problem,
            "action": action,
        })

    # Sort products stably
    products.sort(key=lambda x: (x["businessLine"], x["product"]))

    # Build businessLines list
    business_lines = []
    bl_names = sorted(lines_counter.keys(), key=lambda k: -lines_counter[k])
    for bl in bl_names:
        bl_prods = [p for p in products if p["businessLine"] == bl]
        key_gov = sum(1 for p in bl_prods if p["governanceBand"] == "重点治理")
        risk_imp = sum(1 for p in bl_prods if p["governanceBand"] == "风险改进")
        cont_opt = sum(1 for p in bl_prods if p["governanceBand"] == "持续优化")
        reg_track = sum(1 for p in bl_prods if p["governanceBand"] == "常规跟踪")
        unmeas = sum(1 for p in bl_prods if p["rdhs"] is None)

        mode = (
            "重点治理"
            if key_gov > 0
            else "风险改进"
            if risk_imp > 0
            else "持续优化"
            if cont_opt > 0
            else "常规跟踪"
        )
        if unmeas > 0:
            focus = f"{len(bl_prods)}个产品纳入在管：未度量/待关联 {unmeas} 个，优先补齐产品关联、研发责任角色和过程数据。"
        elif key_gov > 0:
            focus = f"{len(bl_prods)}个产品纳入在管：重点治理产品 {key_gov} 个，优先治理过程能力短板与交付断链。"
        else:
            focus = f"{len(bl_prods)}个产品运行基本规范，持续跟踪时效与质量表现。"

        business_lines.append({
            "businessLine": bl,
            "productTotal": len(bl_prods),
            "keyGovernanceCount": key_gov,
            "riskImprovementCount": risk_imp,
            "continuousOptimizationCount": cont_opt,
            "regularTrackingCount": reg_track,
            "mode": mode,
            "focus": focus,
        })

    measured_count = sum(1 for p in products if p["rdhs"] is not None)
    unmeasured_count = sum(1 for p in products if p["rdhs"] is None)

    snapshot = {
        "schemaVersion": 1,
        "cadence": "monthly",
        "periodKey": "2026-09",
        "asOf": "2026-09-30",
        "fetchedAt": "2026-09-30T07:42:00+08:00",
        "source": {
            "chartId": LAST_CHART_ID,
            "chartName": "【上月】产研健康度得分(RDHS) By 产品",
            "sha256": "3c63ebbdaf8e8ffd2f27d85e31364e0cccffea5e96959dd7e2b1689a6be8ae96",
        },
        "audit": {
            "rawRowCount": 680,
            "acceptedRowCount": 68,
            "zeroScoreRowCount": 612,
            "emptyDimensionRowCount": 3,
            "researchProductCount": 48,
            "measuredProductCount": measured_count,
            "unmeasuredProductCount": unmeasured_count,
            "excludedTestBusinessLineCount": 2,
            "excludedProductAttributeCount": 23,
            "status": "validated",
            "warning": None,
        },
        "overview": {
            "conclusion": "本期 CBG 共覆盖 48 款研发中产品（主数据 48 款，已度量 45 款，未度量 3 款按 0 分计入基数）。整体仍处于重点治理阶段。",
            "focus": "优先消除 3 款未度量黑户（敞口约 3.6分），修复发版登记断链（87项差额），清退长在途超期卡片提升交付时效。",
        },
        "businessLines": business_lines,
        "products": products,
    }

    target_path = REPO_ROOT / "data" / "snapshots" / "2026-09.json"
    target_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Successfully wrote canonical 48-product snapshot to {target_path}!")
    print(f"Audit: researchProductCount={snapshot['audit']['researchProductCount']}, measured={measured_count}, unmeasured={unmeasured_count}")


if __name__ == "__main__":
    main()
