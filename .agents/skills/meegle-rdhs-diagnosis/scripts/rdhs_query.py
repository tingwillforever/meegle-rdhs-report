#!/usr/bin/env python3
"""RDHS 产研健康度极速查询与诊断工具 (rdhs_query.py)

专为 AI Agent 和产研效能分析设计：
1. 自动调用 Meegle CLI 拉取实时度量底表，支持会话级短缓存（默认 0 秒实时直连）。
2. 内置 10429 频率限制自动重试与退避机制。
3. 动态结合主数据清洗规则（自动剔除交付定制与测试业务线，只考核 In Progress 在研标准产品）。
4. 真实角色解析：严格从 role_owners 读取【产品代表】与【项目管理代表】，绝不误读卡片 owner 建卡人。
5. 内置 7 阶归因判定引擎与 4 级治理分档计算。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CACHE_DIR = Path(os.path.expanduser("~/.cache/meegle-rdhs"))
CACHE_TTL = 0  # 当月实时数据默认 0 秒直连；已归档数据另有下限，见 ttl_for_chart
ARCHIVE_TTL = 1800  # 已归档数据（上月图表、月度趋势）不会随日变化，最短缓存 30 分钟
MASTER_TTL = 1800  # 产品主数据状态与责任角色低频变化，最短缓存 30 分钟
MAX_MASTER_PAGES = 50  # 分页保险丝：防止服务端忽略 page-num 时死循环
TREND_MONTHS = 6
BUSINESS_TZ = timezone(timedelta(hours=8))
REQUEST_TIMEOUT = 30
COMPONENT_LIMITS = {
    "链路闭环得分(25')": 25,
    "交付闭环得分(15')": 15,
    "时效节奏合理性(20')": 20,
    "颗粒度对齐度(20')": 20,
    "质量敏锐度(20')": 20,
}
REQUIRED_METRICS = ["RDHS(100')", *COMPONENT_LIMITS, "有效参与人数", "人均需求吞吐量", "人均缺陷关闭量", "积压需求占比", "严重缺陷占比"]

CURRENT_CHART_ID = "7659618575337915254"
LAST_CHART_ID = "7681204196376314742"
BG_TREND_CHART_ID = "7688169549312557942"
LINE_TREND_CHART_ID = "7688177041702650742"
SECONDARY_LINE_TREND_CHART_ID = "7688220298042147702"
PROJECT_KEY = "cbg_product_develop"
MASTER_TYPE_KEY = "693f665435b354b7ca0085dc"

# 角色映射表
ROLE_MAP = {
    "role_01773a": "产品代表",
    "role_57dcb8": "产品经理",
    "role_424751": "研发代表",
    "role_0ba52c": "系统架构师",
    "role_8d8f90": "项目管理代表",
    "role_4292f5": "PMO"
}

# 7-tier attribution labels
ATTR_DATA_MISSING = "过程数据缺失"
ATTR_VALUE_CHAIN_BROKEN = "价值链路不完整"
ATTR_BACKLOG_HEAVY = "需求积压"
ATTR_QUALITY_RISK = "质量管理风险"
ATTR_RELEASE_DEFICIT = "发布闭环不足"
ATTR_PACE_SLOW = "研发节奏偏慢"
ATTR_PROCESS_OPTIMIZE = "过程能力优化"

USER_CACHE_FILE = CACHE_DIR / "user_names.json"

def run_meegle_cmd(args: List[str], max_retries: int = 3) -> Any:
    cmd = ["meegle"] + args + ["--format", "json"]
    for attempt in range(max_retries):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=REQUEST_TIMEOUT)
            if res.returncode != 0:
                err_text = res.stdout + "\n" + res.stderr
                transient = any(marker in err_text for marker in ("10429", "Frequency Limit", "ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "502 Bad Gateway", "503 Service Unavailable"))
                if transient and attempt < max_retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Meegle CLI failed: {err_text}")
            data = json.loads(res.stdout)
            if isinstance(data, dict) and data.get("error"):
                err_msg = json.dumps(data["error"], ensure_ascii=False)
                if "10429" in err_msg and attempt < max_retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Meegle API error: {err_msg}")
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            return data
        except subprocess.TimeoutExpired as exc:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Meegle CLI request timed out after {max_retries} attempts") from exc
            time.sleep(1.5 * (attempt + 1))
        except json.JSONDecodeError as exc:
            raise RuntimeError("Meegle CLI returned invalid JSON") from exc
    raise RuntimeError("Meegle CLI failed after retries.")

def get_cached_or_fetch(key: str, fetch_fn, ttl: int = CACHE_TTL, refresh: bool = False) -> Any:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{key}.json"
    now = time.time()
    if not refresh and ttl > 0 and cache_file.exists():
        try:
            mtime = cache_file.stat().st_mtime
            if now - mtime < ttl:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

    data = fetch_fn()
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass
    return data

def ttl_for_chart(chart_id: str, requested: int) -> int:
    """当月图表由 requested 决定（默认 0 实时直连）；已归档/历史趋势图表不随日频繁变化，应用短缓存策略（保底 300 秒，支持 --refresh 穿透）。"""
    if chart_id == CURRENT_CHART_ID:
        return requested
    return max(requested, 300)

def previous_period(now: Optional[datetime] = None) -> str:
    """上一个已收口自然月（YYYY-MM）。月份一律现算，不写死。"""
    anchor = now or datetime.now(BUSINESS_TZ)
    year, month = anchor.year, anchor.month - 1
    if month == 0:
        year, month = year - 1, 12
    return f"{year}-{month:02d}"

def current_period(now: Optional[datetime] = None) -> str:
    """当前自然月（MTD，未收口）。"""
    return (now or datetime.now(BUSINESS_TZ)).strftime("%Y-%m")

def chart_period(chart_id: str, now: Optional[datetime] = None) -> Optional[str]:
    """按图表角色推出该图当前承载的数据月份；非相对时间图（趋势图）返回 None。

    月份语义来自图表相对名（【本月】/【上月】），不是 chart_id 本身——
    同一 id 在不同自然月装不同月份的数据，所以月份必须现算。
    """
    if chart_id == CURRENT_CHART_ID:
        return current_period(now)
    if chart_id == LAST_CHART_ID:
        return previous_period(now)
    return None

def period_banner(now: Optional[datetime] = None) -> str:
    closed, running = previous_period(now), current_period(now)
    return (
        f"> **数据期间自检**：【本月】图 = `{running}`（MTD，未收口）；"
        f"【上月】图 = `{closed}`（已收口，可作整月结论）；"
        f"趋势图以图表自身 `YYYY-MM` 维度为准。"
    )

def fetch_master_items(page_size: int = 200) -> List[Dict[str, Any]]:
    """分页拉取产品主数据，避免 200 条上限造成静默截断。"""
    items: List[Dict[str, Any]] = []
    for page in range(1, MAX_MASTER_PAGES + 1):
        raw = run_meegle_cmd([
            "workitem", "search-filter",
            "--project-key", PROJECT_KEY,
            "--work-item-type-keys", MASTER_TYPE_KEY,
            "--page-size", str(page_size),
            "--page-num", str(page)
        ])
        batch = raw if isinstance(raw, list) else (raw.get("data", []) if isinstance(raw, dict) else [])
        items.extend(batch)
        if len(batch) < page_size:
            return items
    raise RuntimeError(
        f"产品主数据超过 {page_size * MAX_MASTER_PAGES} 条仍未取完，疑似分页未生效，请检查 CLI page-num 支持"
    )

def get_chart_data(chart_id: str, ttl: int = CACHE_TTL, refresh: bool = False, now: Optional[datetime] = None) -> Tuple[List[str], List[Dict[str, Any]]]:
    period = chart_period(chart_id, now)
    cache_key = f"{PROJECT_KEY}_chart_{chart_id}" + (f"_{period}" if period else "")

    def fetch():
        before = chart_period(chart_id)
        if period and before != period:
            raise RuntimeError("相对图查询已跨月，请重新发起以避免月份错标")
        data = run_meegle_cmd(["chart", "get", "--project-key", PROJECT_KEY, "--chart-id", chart_id])
        if period and chart_period(chart_id) != before:
            raise RuntimeError("相对图取数跨月，结果未缓存，请重新查询")
        return data

    raw = get_cached_or_fetch(cache_key, fetch, ttl=ttl_for_chart(chart_id, ttl), refresh=refresh)
    if not isinstance(raw, dict) or not isinstance(raw.get("quota_titles"), list) or not isinstance(raw.get("chart_data_list"), list):
        raise ValueError("图表响应缺少 quota_titles / chart_data_list，不能解释为零值")
    chart_list = raw["chart_data_list"]
    if len(chart_list) > 1 or (chart_list and not isinstance(chart_list[0], list)):
        raise ValueError("不支持的多块或非列表图表结构；需核实接口契约，不静默截断")
    if len(set(raw["quota_titles"])) != len(raw["quota_titles"]):
        raise ValueError("图表存在重复指标名称")
    return raw["quota_titles"], chart_list[0] if chart_list else []

def get_business_lines(ttl: int = CACHE_TTL, refresh: bool = False) -> Dict[str, str]:
    raw = get_cached_or_fetch(
        "business_lines",
        lambda: run_meegle_cmd(["space", "business-lines", "--project-key", PROJECT_KEY]),
        ttl=3600 if ttl == 0 else ttl,  # 业务线树结构极为稳定，默认安全缓存1小时
        refresh=refresh
    )
    b_map: Dict[str, str] = {}
    def traverse(nodes: List[Dict[str, Any]], prefix: str = ""):
        for n in nodes:
            full_name = f"{prefix}/{n['name']}" if prefix else n["name"]
            b_map[n["id"]] = full_name
            if n.get("children"):
                traverse(n["children"], full_name)
    nodes = raw if isinstance(raw, list) else (raw.get("data", []) if isinstance(raw, dict) else [])
    traverse(nodes)
    return b_map

def resolve_user_names(user_keys: List[str]) -> Dict[str, str]:
    if not user_keys:
        return {}
    known: Dict[str, str] = {}
    if USER_CACHE_FILE.exists():
        try:
            with open(USER_CACHE_FILE, "r", encoding="utf-8") as f:
                known = json.load(f)
        except Exception:
            pass

    to_query = [k for k in set(user_keys) if k and k not in known]
    if to_query:
        # Batch query in chunks of 10
        for i in range(0, len(to_query), 10):
            chunk = to_query[i:i+10]
            try:
                res = run_meegle_cmd(["user", "query", "--user-keys", ",".join(chunk)])
                user_list = res if isinstance(res, list) else (res.get("data", []) if isinstance(res, dict) else [])
                for u in user_list:
                    uk = str(u.get("user_key", ""))
                    name_cn = u.get("name_cn", "") or u.get("name", {}).get("zh_cn", "")
                    simple_name = name_cn.split()[0] if name_cn else uk
                    known[uk] = simple_name
            except Exception as exc:
                sys.stderr.write(f"Warning: 责任人姓名未解析，保留用户标识：{exc}\n")
        try:
            with open(USER_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(known, f, ensure_ascii=False)
        except Exception:
            pass
    return known

def get_product_master(ttl: int = CACHE_TTL, refresh: bool = False, resolve_names: bool = True) -> Dict[str, Dict[str, Any]]:
    items = get_cached_or_fetch(
        "product_master",
        fetch_master_items,
        ttl=ttl,
        refresh=refresh
    )
    b_lines = get_business_lines(ttl=ttl, refresh=refresh)
    
    # Pre-collect all user keys inside role_owners
    all_role_users: List[str] = []
    if resolve_names:
        for it in items:
            for f in it.get("fields", []):
                if f.get("field_key") == "role_owners":
                    for r in f.get("field_value") or []:
                        for o in r.get("owners") or []:
                            all_role_users.append(str(o))
    user_map = resolve_user_names(all_role_users) if resolve_names else {}

    # Filter items first: only govern active or distinct records
    # If the same product name has an active (In Progress) item and historical archived/finished ones,
    # keep the In Progress one. If multiple In Progress items share the exact same name, raise ValueError.
    seen_in_progress: Dict[str, int] = {}
    for it in items:
        pname = it.get("name", "").strip()
        status = it.get("work_item_status", {}).get("state_key", "")
        if status == "In Progress":
            if pname in seen_in_progress:
                raise ValueError(f"存在多条在研状态的同名产品：{pname}（ID {seen_in_progress[pname]} 与 {it.get('id')}），需核实身份")
            seen_in_progress[pname] = it.get("id")

    # Sort items so In Progress comes last to take precedence over historical/archived same-name items
    sorted_items = sorted(items, key=lambda x: (x.get("work_item_status", {}).get("state_key") == "In Progress", x.get("id", 0)))

    master: Dict[str, Dict[str, Any]] = {}
    for it in sorted_items:
        f_map = {f["field_key"]: f for f in it.get("fields", [])}
        bid = f_map.get("business", {}).get("field_value")
        attr = f_map.get("field_22acd7", {}).get("field_value")
        attr_labels = {"ettrf_vl8": "标准产品", "hmeckpgbh": "交付定制"}
        if isinstance(attr, dict):
            val = attr.get("value")
            label = attr.get("label")
            enum_label = attr_labels.get(val)
            if enum_label and label and enum_label != label:
                raise ValueError(f"{it['name']}: 产品属性枚举与标签冲突")
            if val is not None and val not in attr_labels:
                # 显式未知枚举值，标记为未知，不默认通过标签被判定为标准产品
                p_attr = "未知"
            else:
                p_attr = enum_label or label or "标准产品"
        elif isinstance(attr, str):
            p_attr = attr_labels.get(attr, "交付定制" if attr == "hmeckpgbh" else "标准产品")
        else:
            # 飞书项目中未填写 field_22acd7 的工作项，默认为标准自研产品
            p_attr = "标准产品"
        status = it.get("work_item_status", {}).get("state_key", "")
        b_path = b_lines.get(bid, "其他业务线")
        
        # Parse real role owners
        ro_list = f_map.get("role_owners", {}).get("field_value") or []
        roles: Dict[str, List[str]] = {}
        for r in ro_list:
            rid = r.get("role")
            rname = ROLE_MAP.get(rid, rid)
            owners = [user_map.get(str(o), str(o)) for o in (r.get("owners") or [])]
            if owners:
                roles[rname] = owners

        # Determine primary responsible person (优先产品代表 -> 产品经理 -> 项目管理代表)
        prod_rep = roles.get("产品代表", [])
        prod_mgr = roles.get("产品经理", [])
        pm_rep = roles.get("项目管理代表", [])
        
        primary_owner = ""
        if prod_rep:
            primary_owner = f"{','.join(prod_rep)} (产品代表)"
        elif prod_mgr:
            primary_owner = f"{','.join(prod_mgr)} (产品经理)"
        elif pm_rep:
            primary_owner = f"{','.join(pm_rep)} (项目管理)"
        else:
            primary_owner = "未指定"

        pname = it["name"].strip()
        master[pname] = {
            "id": it["id"],
            "business_id": bid,
            "business_path": b_path,
            "status": status,
            "is_in_progress": (status == "In Progress"),
            "product_attr": p_attr,
            "is_custom": (p_attr == "交付定制"),
            "roles": roles,
            "owner": primary_owner,
            "prod_rep": ",".join(prod_rep) if prod_rep else "-",
            "pm_rep": ",".join(pm_rep) if pm_rep else "-"
        }
    return master

def evaluate_attribution(metrics: Dict[str, Any]) -> Tuple[str, str, str]:
    participants = float(metrics.get("有效参与人数") or 0)
    throughput = float(metrics.get("人均需求吞吐量") or 0)
    defect_close = float(metrics.get("人均缺陷关闭量") or 0)
    chain_score = float(metrics.get("链路闭环得分(25')") or 0)
    backlog_ratio = float(metrics.get("积压需求占比") or 0)
    severe_ratio = float(metrics.get("严重缺陷占比") or 0)
    delivery_score = float(metrics.get("交付闭环得分(15')") or 0)
    time_score = float(metrics.get("时效节奏合理性(20')") or 0)

    if participants == 0:
        main_tag = ATTR_DATA_MISSING
        detail = "有效参与人数为 0；需核实实际参与、工作项关联及责任角色，不能据此确认角色缺失"
        step = "过程数据待核实"
    elif throughput == 0 or chain_score < 15:
        main_tag = ATTR_VALUE_CHAIN_BROKEN
        if throughput > 0:
            detail = f"人均需求吞吐量 {throughput:.2f}，链路闭环得分 {chain_score:.0f} < 15；有需求完成记录，但链路能力偏低"
        elif defect_close > 0:
            detail = f"人均需求吞吐量为 0，人均缺陷关闭 {defect_close:.1f}；未记录需求完成，需核实实际交付与验收登记"
        else:
            detail = "人均需求吞吐与人均缺陷关闭均为 0；需核实当前阶段及完成记录，不等于团队未工作"
        step = "交付记录与链路待核实"
    elif backlog_ratio > 0.30:
        main_tag = ATTR_BACKLOG_HEAVY
        detail = f"积压需求占比 {backlog_ratio*100:.1f}% > 30%，大量需求停滞在途中未闭环"
        step = "在途失控（僵尸需求超期滞留）"
    elif severe_ratio > 0.15:
        main_tag = ATTR_QUALITY_RISK
        detail = f"严重缺陷占比 {severe_ratio*100:.1f}% > 15%，严重缺陷比例超标"
        step = "质量失守（严重致命缺陷超标）"
    elif delivery_score < 8:
        main_tag = ATTR_RELEASE_DEFICIT
        detail = f"交付闭环得分 {delivery_score:.0f} < 8 分，上线发布未按规范关联发布计划"
        step = "发版脱节（发版未挂发布计划）"
    elif time_score < 10:
        main_tag = ATTR_PACE_SLOW
        detail = f"时效节奏得分 {time_score:.0f} < 10 分；需拆查开发/交付周期比值和积压项，不能仅凭得分认定绝对周期过长"
        step = "时效构成待核实"
    else:
        main_tag = ATTR_PROCESS_OPTIMIZE
        detail = "未命中前述优先风险；按五维得分定位短板，不能直接认定需求拆解过粗"
        step = "分项能力待核实"

    if main_tag != ATTR_BACKLOG_HEAVY and backlog_ratio > 0.30:
        total_req = int(float(metrics.get("需求总量") or 0))
        detail += f"（叠加积压风险：需求总量 {total_req}，积压占比 {backlog_ratio*100:.1f}%）"

    return main_tag, detail, step

def get_tier(rdhs: float) -> Tuple[str, str]:
    if rdhs >= 70:
        return "常规跟踪", "达标"
    elif rdhs >= 60:
        return "持续优化", "P2"
    elif rdhs >= 45:
        return "风险改进", "P1"
    else:
        return "重点治理", "P0"

def parse_chart_rows(quota_titles: List[str], rows: List[Dict[str, Any]], master: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    prods: Dict[str, Dict[str, Any]] = {}
    valid_rows: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for r in rows:
        dim = r.get("dim", {})
        b_name = dim.get("0", "").strip()
        p_name = dim.get("1", "").strip()
        if not p_name or p_name == "(空)":
            continue
        zero_spec = r.get("is_zero_spec", False)
        if not isinstance(zero_spec, bool):
            raise ValueError(f"{p_name}: is_zero_spec 必须为布尔值")
        if zero_spec:
            continue
        missing = set(REQUIRED_METRICS) - set(quota_titles)
        if missing:
            raise ValueError(f"{p_name}: 缺少必需指标 {sorted(missing)}")
        vals = r.get("value", {})
        metric_dict: Dict[str, Any] = {}
        for idx, title in enumerate(quota_titles):
            value = vals.get(str(idx))
            try:
                number = float(value) if not isinstance(value, bool) else float("nan")
            except (TypeError, ValueError):
                raise ValueError(f"{p_name}: 指标 {title} 缺失或非数值") from None
            if not math.isfinite(number) or number < 0:
                raise ValueError(f"{p_name}: 指标 {title} 非有限非负数")
            metric_dict[title] = value
        for title, maximum in {"RDHS(100')": 100, **COMPONENT_LIMITS}.items():
            if float(metric_dict[title]) > maximum:
                raise ValueError(f"{p_name}: {title} 超过满分 {maximum}")
        for title in ("积压需求占比", "严重缺陷占比", "低级缺陷占比"):
            if title in metric_dict and float(metric_dict[title]) > 1:
                raise ValueError(f"{p_name}: {title} 应为 0~1")
        total = sum(float(metric_dict[title]) for title in COMPONENT_LIMITS)
        # Chart decimals are rounded; tolerate 0.05 point without rewriting source scores.
        if abs(float(metric_dict["RDHS(100')"]) - total) > 0.05:
            raise ValueError(f"{p_name}: RDHS 与五维得分之和不一致")
        row_obj = {
            "business_line_chart": b_name,
            "product_name": p_name,
            "is_zero_spec": r.get("is_zero_spec", False),
            "metrics": metric_dict,
            "rdhs": float(metric_dict.get("RDHS(100')", 0) or 0)
        }
        
        if (b_name, p_name) in valid_rows:
            raise ValueError(f"产品图重复行：{b_name}/{p_name}")
        valid_rows[(b_name, p_name)] = row_obj

    # 过滤维度空行幽灵数据：若某产品既有具名业务线行、又有业务线为 (空) 的行，过滤 (空) 行
    named_products = {p for (b, p) in valid_rows.keys() if b and b != "(空)"}
    cleaned_rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for (b, p), row_obj in valid_rows.items():
        if b == "(空)" and p in named_products:
            continue
        cleaned_rows[(b, p)] = row_obj

    for (b_name, pname), row_obj in cleaned_rows.items():
        if pname in prods:
            raise ValueError(f"产品图跨业务线重名：{pname}")
        if pname in master:
            minfo = master[pname]
            # 排除测试业务线产品
            if "测试业务线" in minfo.get("business_path", ""):
                continue
            b_top = minfo.get("business_path", "").split("/")[0]
            if b_top != b_name:
                raise ValueError(f"{pname}: 图表业务线 {b_name} 与主数据 {b_top} 不一致，需核实身份")
        prods[pname] = row_obj

    return prods

def is_eligible_product(master_info: Optional[Dict[str, Any]]) -> bool:
    """RDHS 聚合只纳入在研、非交付定制、非测试业务线产品。"""
    return bool(
        master_info
        and master_info.get("is_in_progress")
        and not master_info.get("is_custom")
        and master_info.get("product_attr", "标准产品") == "标准产品"
        and "测试业务线" not in master_info.get("business_path", "")
    )

def summarize_scope(
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]
) -> Dict[str, Any]:
    measured = [item for item in matched if item[1] is not None]
    missing = [item[0] for item in matched if item[1] is None]
    avg = sum(item[1]["rdhs"] for item in measured) / len(measured) if measured else None
    audit_avg = sum(item[1]["rdhs"] if item[1] is not None else 0 for item in matched) / len(matched) if matched else None
    paired = [item for item in matched if item[1] is not None and item[2] is not None]
    paired_current_avg = sum(item[1]["rdhs"] for item in paired) / len(paired) if paired else None
    paired_last_avg = sum(item[2]["rdhs"] for item in paired) / len(paired) if paired else None
    tiers = {"P0": 0, "P1": 0, "P2": 0, "达标": 0}
    for _, current, _, _ in measured:
        tiers[get_tier(current["rdhs"])[1]] += 1
    return {
        "average_rdhs": avg,
        "audit_average_rdhs": audit_avg,
        "measured_average_rdhs": avg,
        "comparison_count": len(paired),
        "comparison_current_average": paired_current_avg,
        "last_average_rdhs": paired_last_avg,
        "eligible_count": len(matched),
        "measured_count": len(measured),
        "coverage": len(measured) / len(matched) if matched else 0,
        "missing_products": missing,
        "tiers": tiers,
    }

def parse_trend_rows(
    quota_titles: List[str],
    rows: List[Dict[str, Any]],
    business_line: Optional[str] = None,
    secondary_line: Optional[str] = None,
    month: Optional[str] = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    current_month = current_period(now)
    parsed: List[Dict[str, Any]] = []
    for row in rows:
        dim = row.get("dim", {})
        row_month = dim.get("0", "")
        if len(row_month) != 7 or row_month >= current_month:
            continue
        try:
            datetime.strptime(row_month, "%Y-%m")
        except ValueError:
            raise ValueError(f"无效趋势月份：{row_month}") from None
        if month is not None and row_month != month:
            continue
        if business_line is not None and dim.get("1") != business_line:
            continue
        if secondary_line is not None and dim.get("2") != secondary_line:
            continue
        values = row.get("value", {})
        metrics = {title: values.get(str(index)) for index, title in enumerate(quota_titles)}
        for title, value in metrics.items():
            try:
                number = float(value) if not isinstance(value, bool) else float("nan")
            except (TypeError, ValueError):
                raise ValueError(f"{row_month}: 趋势指标 {title} 缺失或非数值") from None
            if not math.isfinite(number) or number < 0 or ((title.endswith("率") or title.endswith("占比")) and number > 1):
                raise ValueError(f"{row_month}: 趋势指标 {title} 数值无效")
        if "应发布需求数" in metrics and "有效发布需求数" in metrics and float(metrics["有效发布需求数"]) > float(metrics["应发布需求数"]):
            raise ValueError(f"{row_month}: 有效发布需求数超过应发布需求数")
        if any(item["month"] == row_month for item in parsed):
            raise ValueError(f"{row_month}: 趋势范围存在重复月份，需指定业务线")
        parsed.append({"month": row_month, "metrics": metrics})
    ordered = sorted(parsed, key=lambda item: item["month"])
    return ordered if month else ordered[-TREND_MONTHS:]

def trend_value(metrics: Dict[str, Any], *names: str) -> float:
    for name in names:
        if name in metrics:
            return float(metrics.get(name) or 0)
    return 0.0

def format_trend_judgement(rows: List[Dict[str, Any]]) -> List[str]:
    if len(rows) < 2:
        return []
    previous, current = rows[-2]["metrics"], rows[-1]["metrics"]
    previous_month, current_month = rows[-2]["month"], rows[-1]["month"]
    throughput_before = trend_value(previous, "人均需求吞吐量")
    throughput_now = trend_value(current, "人均需求吞吐量")
    demand_before = trend_value(previous, "需求吞吐量", "需求总量")
    demand_now = trend_value(current, "需求吞吐量", "需求总量")
    delivery_before = trend_value(previous, "需求交付周期")
    delivery_now = trend_value(current, "需求交付周期")
    severe_before = trend_value(previous, "严重缺陷占比") * 100
    severe_now = trend_value(current, "严重缺陷占比") * 100
    if demand_before <= 0 or demand_now <= 0 or delivery_before <= 0 or delivery_now <= 0:
        delivery_text = "- **时效**：至少一月无需求完成或周期有效样本，不作交付提速判断"
    else:
        delivery_text = (
            f"- **时效**：需求交付周期 {delivery_before:.2f} → {delivery_now:.2f} 天"
            f"（{'缩短' if delivery_now < delivery_before else '拉长' if delivery_now > delivery_before else '持平'}）"
        )
    throughput_text = (f"{throughput_before:.2f} → {throughput_now:.2f}" if all("人均需求吞吐量" in metrics for metrics in (previous, current)) else "未获取可比数据")
    demand_text = (f"{demand_before:.0f} → {demand_now:.0f}" if all("需求吞吐量" in metrics or "需求总量" in metrics for metrics in (previous, current)) else "未获取可比数据")
    return [
        f"- **产出**（{previous_month} → {current_month}）：人均需求吞吐 {throughput_text}，需求完成量 {demand_text}",
        delivery_text,
        (f"- **质量**：严重缺陷占比 {severe_before:.1f}% → {severe_now:.1f}%（比例变化，需核实缺陷样本口径，不代表治理效果）"
         if "严重缺陷占比" in previous and "严重缺陷占比" in current
         else "- **质量**：未获取严重缺陷占比，不作改善判断"),
    ]

def format_trend_report(title: str, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return f"### {title}月度趋势\n未找到可用的完整月趋势数据。"

    lines = [f"### {title}月度关键结果趋势（近 {len(rows)} 个完整月）", *format_trend_judgement(rows), ""]
    lines.extend([
        "| 月份 | 有效人数 | 需求完成量 | 人均需求吞吐 | 需求交付周期 | 需求开发周期 | 严重缺陷占比 | 缺陷逃逸率 | 发布完成量 | 发布登记闭环率 | 登记差额 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in rows:
        metrics = row["metrics"]

        def cell(*names: str, digits: int = 2, percentage: bool = False) -> str:
            if not any(name in metrics for name in names):
                return "—（未获取）"
            value = trend_value(metrics, *names)
            return f"{value * 100:.1f}%" if percentage else f"{value:.{digits}f}"

        counts_known = "需求吞吐量" in metrics or "需求总量" in metrics
        has_completions = trend_value(metrics, "需求吞吐量", "需求总量") > 0
        if not counts_known:
            delivery = development = "—（完成量未获取，样本待核实）"
        elif not has_completions:
            delivery = development = "—（无有效样本）"
        else:
            delivery = cell("需求交付周期") + " 天"
            development = cell("需求开发周期") + " 天"
        closure = gap = "—（未获取）"
        if "应发布需求数" in metrics and "有效发布需求数" in metrics:
            required = trend_value(metrics, "应发布需求数")
            valid = trend_value(metrics, "有效发布需求数")
            if valid > required:
                raise ValueError(f"{row['month']}: 有效发布需求数超过应发布需求数")
            closure = f"{valid / required * 100:.2f}%" if required else "—（无应发布样本）"
            gap = f"{required - valid:.0f}"
        lines.append(
            f"| {row['month']} | {cell('有效参与人数', digits=0)} | "
            f"{cell('需求吞吐量', '需求总量', digits=0)} | {cell('人均需求吞吐量')} | "
            f"{delivery} | {development} | {cell('严重缺陷占比', percentage=True)} | "
            f"{cell('缺陷逃逸率', percentage=True)} | {cell('发布完成量', digits=0)} | {closure} | {gap} |"
        )
    lines.extend([
        "",
        "> 口径说明：月度趋势覆盖整体历史业务数据；RDHS 依赖治理后的产品主数据。两者用于交叉印证，不强行对账。发布登记闭环率=有效发布/应发布需求数；登记差额不等于未实际上线。",
    ])
    return "\n".join(lines)

def product_facts(current: Dict[str, Any]) -> Tuple[float, float, float, float, float]:
    metrics = current["metrics"]
    return (
        trend_value(metrics, "有效参与人数"),
        trend_value(metrics, "人均需求吞吐量"),
        trend_value(metrics, "人均缺陷关闭量"),
        trend_value(metrics, "需求在途时长"),
        trend_value(metrics, "积压需求占比"),
    )

def select_governance_entries(
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]
) -> Dict[str, List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]]:
    status: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
    delivery: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
    backlog: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
    for pname, current, _, master_info in matched:
        if not current:
            status.append((pname, current, master_info))
            continue
        participants, throughput, defects, in_transit, backlog_ratio = product_facts(current)
        missing_roles = bool(master_info and master_info.get("prod_rep", "-") == "-" and master_info.get("pm_rep", "-") == "-")
        if participants <= 2 and throughput == 0 and defects == 0:
            status.append((pname, current, master_info))
        elif participants > 0 and throughput == 0:
            delivery.append((pname, current, master_info))
        elif missing_roles:
            status.append((pname, current, master_info))
        elif in_transit > 60 or backlog_ratio > 0.30:
            backlog.append((pname, current, master_info))
    status.sort(key=lambda item: (item[1] is not None, item[1]["rdhs"] if item[1] else 0))
    delivery.sort(key=lambda item: (-product_facts(item[1])[0], item[1]["rdhs"]))
    backlog.sort(key=lambda item: (-max(product_facts(item[1])[3] / 60, product_facts(item[1])[4] / 0.30), -product_facts(item[1])[0]))
    return {"状态/数据待核实": status[:2], "交付断链": delivery[:2], "积压失控": backlog[:2]}

def format_governance_entries(
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]
) -> str:
    lines = [
        "### 当前治理切口",
        "| 类型 | 产品 | 关键事实 | 责任角色 | 第一动作 |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    count = 0
    for category, entries in select_governance_entries(matched).items():
        for pname, current, master_info in entries:
            count += 1
            product_rep = master_info.get("prod_rep", "-") if master_info else "-"
            project_rep = master_info.get("pm_rep", "-") if master_info else "-"
            roles = f"产品：{product_rep}；项目：{project_rep}"
            if not current:
                facts = "本次查询无有效匹配，原因待核实"
                action = "核实图表范围、产品身份、占位行及度量关联"
            else:
                participants, throughput, defects, in_transit, backlog_ratio = product_facts(current)
                if category == "状态/数据待核实":
                    if product_rep == "-" and project_rep == "-":
                        facts = f"产品与项目责任角色均缺失；{participants:.0f} 人参与"
                        action = "先补齐责任角色，再确认真实在研状态和治理计划"
                    else:
                        facts = f"{participants:.0f} 人参与；需求/缺陷吞吐均为 0"
                        action = "先确认是否真实在研，再决定补闭环或调整状态"
                elif category == "交付断链":
                    facts = f"{participants:.0f} 人参与；需求吞吐 0；人均关闭缺陷 {defects:.2f}"
                    if product_rep == "-" and project_rep == "-":
                        action = "先补齐责任角色，再逐项核查并验收已交付需求"
                    else:
                        action = "逐项核查在途需求，优先完成已交付需求验收"
                else:
                    facts = f"在途 {in_transit:.1f} 天；积压率 {backlog_ratio * 100:.1f}%"
                    action = "对超期需求逐项决定继续、缩期或终止"
            lines.append(f"| **{category}** | **{pname}** | {facts} | {roles} | {action} |")
    if count == 0:
        lines.append("| — | — | 暂未发现明显断链、积压或数据缺口 | — | 保持当前节奏 |")
    return "\n".join(lines)

def format_scope_summary(
    title: str,
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]],
    compare: bool = False,
    scope_uncertain: bool = False,
) -> str:
    summary = summarize_scope(matched)
    audit_avg = summary["audit_average_rdhs"]
    audit_avg_text = f"{audit_avg:.1f} 分" if audit_avg is not None else "—"
    measured_avg = summary["measured_average_rdhs"]
    measured_avg_text = f"{measured_avg:.1f} 分" if measured_avg is not None else "—"
    if summary["missing_products"] or scope_uncertain:
        tier_text = "范围待核实，不作整体分档"
    else:
        tier_text = get_tier(audit_avg)[0] if audit_avg is not None else "无有效度量"
    compare_text = ""
    if compare and summary["comparison_current_average"] is not None and summary["last_average_rdhs"] is not None:
        delta = summary["comparison_current_average"] - summary["last_average_rdhs"]
        compare_text = (
            f"；同口径 {summary['comparison_count']} 款产品较上月 {delta:+.1f} 分"
            f"（{summary['last_average_rdhs']:.1f} → {summary['comparison_current_average']:.1f}）"
        )
    return "\n".join([
        f"## 📊 {title} RDHS 当下健康度",
        f"- **考核均分（未度量计0）**：**{audit_avg_text}**（{tier_text}）{compare_text}",
        f"- **实测样本均分**：{measured_avg_text}（度量覆盖：{summary['measured_count']} / {summary['eligible_count']} 款产品，{summary['coverage'] * 100:.1f}%）",
        f"- **产品分布**：P0 {summary['tiers']['P0']}｜P1 {summary['tiers']['P1']}｜P2 {summary['tiers']['P2']}｜达标 {summary['tiers']['达标']}",
    ])

def format_business_line_summary(
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]
) -> str:
    groups: Dict[str, List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]] = {}
    for item in matched:
        path = item[3].get("business_path", "其他业务线") if item[3] else "其他业务线"
        groups.setdefault(path.split("/")[0], []).append(item)
    lines = [
        "### 一级业务线概览",
        "| 一级业务线 | 考核均分(计0) | 实测均分 | P0 产品 | 度量覆盖 |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ]
    ranked = []
    for line_name, products in groups.items():
        summary = summarize_scope(products)
        ranked.append((summary["audit_average_rdhs"] if summary["audit_average_rdhs"] is not None else -1, line_name, summary))
    for audit_avg, line_name, summary in sorted(ranked):
        audit_text = f"{audit_avg:.1f}" if audit_avg >= 0 else "—"
        measured_avg = summary["measured_average_rdhs"]
        measured_text = f"{measured_avg:.1f}" if measured_avg is not None else "—"
        lines.append(
            f"| **{line_name}** | {audit_text} | {measured_text} | {summary['tiers']['P0']} | "
            f"{summary['measured_count']} / {summary['eligible_count']}（{summary['coverage'] * 100:.1f}%） |"
        )
    return "\n".join(lines)

def format_full_leaderboard(
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]
) -> str:
    summary = summarize_scope(matched)
    lines = [
        f"### 完整产品诊断榜单（共 {summary['eligible_count']} 款）",
        "| 产品型号/名称 | 业务线归属 | 属性/状态 | RDHS得分 | 治理分档 | 产品代表 | 项目管理代表 |",
        "| :--- | :--- | :--- | :---: | :---: | :--- | :--- |",
    ]
    for pname, current, _, master_info in sorted(matched, key=lambda item: item[1]["rdhs"] if item[1] else -1):
        if not current:
            lines.append(
                f"| **{pname}** | {master_info.get('business_path', '-') if master_info else '-'} | 无有效匹配（待核实） | **—** | "
                f"未度量 / 数据治理 | {master_info.get('prod_rep', '-') if master_info else '-'} | "
                f"{master_info.get('pm_rep', '-') if master_info else '-'} |"
            )
            continue
        tier_name, priority = get_tier(current["rdhs"])
        path = master_info.get("business_path", current["business_line_chart"]) if master_info else current["business_line_chart"]
        product_attr = master_info.get("product_attr", "标准产品") if master_info else "标准产品"
        status = "在研" if master_info and master_info.get("is_in_progress") else "存量"
        product_rep = master_info.get("prod_rep", "-") if master_info else "-"
        project_rep = master_info.get("pm_rep", "-") if master_info else "-"
        lines.append(
            f"| **{pname}** | {path} | {product_attr}({status}) | **{current['rdhs']:.0f} 分** | "
            f"`{tier_name}({priority})` | {product_rep} | {project_rep} |"
        )
    if summary["missing_products"]:
        lines.extend(["", f"- **无有效匹配产品**：{'、'.join(summary['missing_products'])}（不计入平均值或 P0；需核实图表范围、匹配与真实未度量原因）"])
    return "\n".join(lines)

def format_product_candidates(
    query: str,
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]],
) -> str:
    lines = [
        f"## “{query}”匹配到 {len(matched)} 款产品，请选择具体产品",
        "| 产品 | 业务归属 | RDHS |",
        "| :--- | :--- | ---: |",
    ]
    for pname, current, _, master_info in matched:
        path = master_info.get("business_path", "-") if master_info else "-"
        score = f"{current['rdhs']:.0f} 分" if current else "未度量"
        lines.append(f"| **{pname}** | {path} | {score} |")
    return "\n".join(lines)

def render_progress_bar(score: float, max_score: float, width: int = 10) -> str:
    ratio = max(0.0, min(1.0, score / max_score if max_score > 0 else 0))
    filled = int(round(ratio * width))
    empty = width - filled
    status_dot = "🟢" if ratio >= 0.8 else ("🟡" if ratio >= 0.5 else "🔴")
    return f"[{score:2.0f}/{max_score:2.0f}] {'█' * filled}{'░' * empty} {ratio * 100:3.0f}% {status_dot}"

def format_product_report(p_name: str, cur_item: Optional[Dict[str, Any]], last_item: Optional[Dict[str, Any]], master_info: Optional[Dict[str, Any]]) -> str:
    if not cur_item:
        return f"未在当前月度量图表中找到产品【{p_name}】的记录。"

    metrics = cur_item["metrics"]
    rdhs_cur = cur_item["rdhs"]
    tier_name, tier_p = get_tier(rdhs_cur)
    
    last_rdhs_str = "-"
    delta_str = "-"
    if last_item:
        rdhs_last = last_item["rdhs"]
        last_rdhs_str = f"{rdhs_last:.0f} 分"
        delta = rdhs_cur - rdhs_last
        if delta > 0:
            delta_str = f"+{delta:.0f} 分 🟢"
        elif delta < 0:
            delta_str = f"{delta:.0f} 分 🔴"
        else:
            delta_str = "持平"

    main_tag, detail, step = evaluate_attribution(metrics)
    
    b_path = master_info.get("business_path", cur_item["business_line_chart"]) if master_info else cur_item["business_line_chart"]
    p_attr = master_info.get("product_attr", "标准产品") if master_info else "标准产品"
    status_str = "在研 (In Progress)" if (master_info and master_info.get("is_in_progress")) else "存量维护/其他"
    
    roles_str = ""
    if master_info and master_info.get("roles"):
        roles_parts = [f"{r}: {','.join(names)}" for r, names in master_info["roles"].items() if r != "PMO"]
        roles_str = " | ".join(roles_parts)
    if not roles_str:
        roles_str = master_info.get("owner", "未指定") if master_info else "未指定"

    s_chain = float(metrics.get("链路闭环得分(25')", 0))
    s_deliv = float(metrics.get("交付闭环得分(15')", 0))
    s_time = float(metrics.get("时效节奏合理性(20')", 0))
    s_grain = float(metrics.get("颗粒度对齐度(20')", 0))
    s_qual = float(metrics.get("质量敏锐度(20')", 0))

    lines = [
        f"## 🏥【{p_name}】RDHS 产研体检单",
        f"- **综合健康度**：**{rdhs_cur:.0f} 分**（{tier_name}，治理优先级：`{tier_p}`） ｜ **上月基线**：{last_rdhs_str}（环比：{delta_str}）",
        f"- **业务归属**：`{b_path}` ｜ **核心责任人**：{roles_str}",
        f"- **核心归因诊断**：`【{main_tag}】` ── 节拍失衡点：`{step}`",
        f"- **病根事实**：{detail}",
        "",
        "### 五维健康度体检 (进度条自适应)",
        f"- 链路闭环得分(25')   {render_progress_bar(s_chain, 25)}  实绩: 人均吞吐 {metrics.get('人均需求吞吐量')}, 人均缺陷关闭 {metrics.get('人均缺陷关闭量')}",
        f"- 交付闭环得分(15')   {render_progress_bar(s_deliv, 15)}  实绩: 有效发布 {metrics.get('有效发布需求数')}/{metrics.get('应发布需求数')}",
        f"- 时效节奏合理性(20') {render_progress_bar(s_time, 20)}  实绩: 在途 {metrics.get('需求在途时长')}天, 积压率 {float(metrics.get('积压需求占比',0))*100:.1f}%",
        f"- 颗粒度对齐度(20')   {render_progress_bar(s_grain, 20)}  实绩: 交付周期 {metrics.get('需求交付周期')}天, 需求量 {metrics.get('需求总量')}",
        f"- 质量敏锐度(20')     {render_progress_bar(s_qual, 20)}  实绩: 严重缺陷比 {float(metrics.get('严重缺陷占比',0))*100:.1f}%, 线上Bug {metrics.get('线上缺陷数量')}",
        "",
        "### 🎯 当前优先治理动作" if rdhs_cur < 70 else "### 稳定性关注事项",
    ]

    actions = []
    if float(metrics.get("人均需求吞吐量") or 0) == 0:
        actions.append("**立即推进在途需求验收**：先核实实际阶段、上线与验收凭证；仅对真实完成且满足验收条件的需求补齐登记，不为提分虚假结项。")
    if float(metrics.get("积压需求占比") or 0) > 0.3 or float(metrics.get("需求在途时长") or 0) > 60:
        actions.append("**清理超期积压僵尸需求**：先核实超期原单及继续开发价值，由负责人决定继续、调整计划或终止；不因均值超期批量结项。")
    if s_deliv < 10 and float(metrics.get("应发布需求数") or 0) > 0:
        actions.append("**核实发布登记闭环**：逐项核对真实上线需求与发布计划关联，修正缺失记录；不承诺满分。")
    if main_tag == ATTR_DATA_MISSING:
        actions.insert(0, "**核实过程数据与角色**：先确认真实研发阶段、参与记录和责任人，再决定是否补登记。")
    if float(metrics.get("严重缺陷占比") or 0) > 0.15 or s_qual < 10:
        actions.append("**核查严重缺陷与质量门禁**：测试与研发负责人按严重缺陷原单核查版本、根因及漏测环节，依据样本制定改进。")
    if s_grain < 10:
        actions.append("**核查需求颗粒度与测试记录**：结合实际需求规模和缺陷样本确认拆分及登记是否合理。")
    if s_time < 10 and float(metrics.get("积压需求占比") or 0) <= 0.3:
        actions.append("**拆查时效构成**：分别核实已完成需求的开发/交付周期比值与在途积压，不只看总分。")
    if not actions:
        actions.append("**跟踪五维短板**：核实链路、发布与质量样本，保持迭代记录真实完整。")

    lines.extend(f"{index}. {action}" for index, action in enumerate(actions, 1))
    return "\n".join(lines)

def historical_report(args, parser, now: datetime) -> None:
    try:
        anchor = datetime.strptime(args.month, "%Y-%m")
    except ValueError:
        parser.error("--month 必须为 YYYY-MM")
    if anchor.strftime("%Y-%m") != args.month or args.month >= current_period(now):
        parser.error("--month 仅支持已收口自然月，不能将本月或未来月份当整月")
    if args.product or args.trend:
        parser.error("--month 仅支持 BG/业务线过程查询，不支持历史产品评分或同时 --trend")

    top_line = secondary = None
    chart_id = BG_TREND_CHART_ID
    if args.business_line:
        paths = sorted(set(get_business_lines(ttl=args.cache_ttl, refresh=args.refresh).values()))
        matches = [path for path in paths if args.business_line in (path, path.split("/")[-1])]
        if len(matches) != 1:
            parser.error(f"业务线名称不唯一或未找到：{args.business_line}；候选：{matches}，请使用完整路径")
        path = matches[0]
        top_line, _, secondary = path.partition("/")
        chart_id = SECONDARY_LINE_TREND_CHART_ID if secondary else LINE_TREND_CHART_ID
    titles, rows = get_chart_data(chart_id, ttl=args.cache_ttl, refresh=args.refresh, now=now)
    selected = parse_trend_rows(titles, rows, top_line, secondary or None, month=args.month, now=now)
    warnings = []
    report_rows = selected
    if args.compare and selected:
        baseline_month = previous_period(anchor)
        baseline = parse_trend_rows(titles, rows, top_line, secondary or None, month=baseline_month, now=now)
        if baseline:
            report_rows = baseline + selected
        else:
            warnings.append(f"未获取 {baseline_month}，不使用最近有数据月份替代环比基线")
    result = {
        "scope": args.business_line or "消费者BG",
        "period": args.month,
        "status": "no_data" if not selected else "partial" if warnings else "ok",
        "warnings": warnings,
        "source_chart_id": chart_id,
        "queried_at": now.isoformat(),
        "trends": [{"title": args.business_line or "消费者 BG", "rows": report_rows, "judgement": format_trend_judgement(report_rows)}],
        "limitations": ["过程趋势覆盖历史业务数据，不等同自研产品 RDHS 考核分母；不提供历史产品评分或已实施整改结论"],
    }
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"## {result['scope']} {args.month} 整月过程情况\n")
        print(format_trend_report("", report_rows) if selected else f"未获取 {args.month} 数据；可查深度受趋势源保留范围限制。")
        for message in warnings + result["limitations"]:
            print(f"\n> {message}")


def json_output_requested() -> bool:
    return "--format=json" in sys.argv or any(flag in sys.argv and sys.argv[sys.argv.index(flag) + 1:][:1] == ["json"] for flag in ("--format", "-f"))


class QueryParser(argparse.ArgumentParser):
    def error(self, message):
        if json_output_requested():
            print(json.dumps({"status": "error", "error": message}, ensure_ascii=False))
            self.exit(2)
        super().error(message)


def main():
    parser = QueryParser(description="RDHS 产研健康度极速查询与诊断")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--product", "-p", help="按产品名称精确或模糊查询")
    scope.add_argument("--business-line", "-b", help="按一级或二级业务线名称筛选")
    scope.add_argument("--all", "-a", action="store_true", help="输出消费者 BG 整体健康度")
    parser.add_argument("--compare", "-c", action="store_true", help="对比上一个自然月（本月 RDHS 或指定月过程指标）")
    parser.add_argument("--month", help="YYYY-MM：指定已收口月份的 BG/业务线过程指标，不提供历史产品评分")
    parser.add_argument("--trend", action="store_true", help="追加一级业务线或消费者 BG 月度趋势")
    parser.add_argument("--cache-ttl", type=int, default=CACHE_TTL, help="缓存过期时间(秒)，默认 0 (实时直连)")
    parser.add_argument("--refresh", "-r", action="store_true", help="强制穿透缓存直连拉取最新数据")
    parser.add_argument("--format", "-f", choices=["markdown", "json"], default="markdown", help="输出格式")
    args = parser.parse_args()
    now = datetime.now(BUSINESS_TZ)
    if args.month:
        historical_report(args, parser, now)
        return
    warnings: List[str] = []
    master = get_product_master(ttl=args.cache_ttl, refresh=args.refresh, resolve_names=False)
    unknown = [name for name, info in master.items() if info.get("product_attr") not in ("标准产品", "交付定制") and (args.all or args.product and args.product.lower() in name.lower() or args.business_line and args.business_line.lower() in info.get("business_path", "").lower())]
    if unknown:
        warnings.append(f"{len(unknown)} 款产品属性未确认，未默认纳入标准自研考核")
    cur_qt, cur_rows = get_chart_data(CURRENT_CHART_ID, ttl=args.cache_ttl, refresh=args.refresh, now=now)
    cur_prods = parse_chart_rows(cur_qt, cur_rows, master)

    last_prods: Dict[str, Dict[str, Any]] = {}
    if args.compare:
        try:
            last_qt, last_rows = get_chart_data(LAST_CHART_ID, ttl=args.cache_ttl, refresh=args.refresh, now=now)
            last_prods = parse_chart_rows(last_qt, last_rows, master)
        except Exception as e:
            warnings.append(f"上月基线未获取：{e}")
            sys.stderr.write(f"Warning: {warnings[-1]}\n")

    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
    all_pnames = sorted(set(master) | set(cur_prods))
    if args.product and args.product in all_pnames:
        all_pnames = [args.product]
    for pname in all_pnames:
        minfo = master.get(pname)
        current = cur_prods.get(pname)
        path = minfo.get("business_path", current["business_line_chart"] if current else "") if minfo else (current["business_line_chart"] if current else "")
        if args.product:
            if args.product.lower() in pname.lower():
                matched.append((pname, current, last_prods.get(pname), minfo))
        elif is_eligible_product(minfo) and (args.all or args.business_line.lower() in path.lower()):
            matched.append((pname, current, last_prods.get(pname), minfo))

    if not matched:
        message = f"未找到与 '{args.product or args.business_line or '消费者BG'}' 相关的度量数据。"
        print(json.dumps({"scope": args.product or args.business_line or "消费者BG", "status": "no_data", "products": [], "warnings": warnings, "message": message}, ensure_ascii=False) if args.format == "json" else message)
        return

    # Resolve only roles belonging to products that will be shown.
    role_users = [user for _, _, _, info in matched if info for owners in info.get("roles", {}).values() for user in owners]
    names = resolve_user_names(role_users)
    unresolved = set(role_users) - set(names)
    if unresolved:
        warnings.append(f"{len(unresolved)} 个责任人姓名未解析，保留用户标识，不视为身份已核实")
    for _, _, _, info in matched:
        if info and info.get("roles"):
            info["roles"] = {role: [names.get(user, user) for user in users] for role, users in info["roles"].items()}
            info["prod_rep"] = ",".join(info["roles"].get("产品代表", [])) or "-"
            info["pm_rep"] = ",".join(info["roles"].get("项目管理代表", [])) or "-"
            info["owner"] = info["prod_rep"] if info["prod_rep"] != "-" else info["pm_rep"]
    missing = [name for name, current, _, _ in matched if current is None]
    if missing:
        warnings.append(f"{len(missing)} 款产品无有效匹配；需核实图表范围、身份和占位，不能直接判业务未度量或代表全 BG")
    if args.compare and any(current is not None and last is None for _, current, last, _ in matched):
        warnings.append("部分产品未获取上月有效基线；环比仅限双期匹配产品，当前 MTD 不与上月整月等同")

    trend_sections: List[Tuple[str, List[Dict[str, Any]]]] = []
    if args.trend and args.all:
        trend_qt, trend_rows = get_chart_data(BG_TREND_CHART_ID, ttl=args.cache_ttl, refresh=args.refresh)
        trend_sections.append(("消费者 BG ", parse_trend_rows(trend_qt, trend_rows, now=now)))
    elif args.trend and args.business_line:
        paths = sorted({item[3]["business_path"] for item in matched if item[3]})
        top_lines = sorted({path.split("/")[0] for path in paths})
        secondary_names = {path.split("/", 1)[1] for path in paths if "/" in path}
        resolved_secondary = next(iter(secondary_names)) if len(secondary_names) == 1 else None
        if resolved_secondary and args.business_line.lower() in resolved_secondary.lower():
            trend_qt, trend_rows = get_chart_data(SECONDARY_LINE_TREND_CHART_ID, ttl=args.cache_ttl, refresh=args.refresh)
            trend_sections = [
                (
                    f"【{top_line}/{resolved_secondary}】",
                    parse_trend_rows(trend_qt, trend_rows, top_line, resolved_secondary, now=now),
                )
                for top_line in top_lines
            ]
        else:
            trend_qt, trend_rows = get_chart_data(LINE_TREND_CHART_ID, ttl=args.cache_ttl, refresh=args.refresh)
            trend_sections = [
                (f"【{top_line}】", parse_trend_rows(trend_qt, trend_rows, top_line, now=now))
                for top_line in top_lines
            ]

    if current_period() != current_period(now):
        raise RuntimeError("本次相对月份诊断已跨月，请重新查询，不输出跨期间拼接结果")
    if args.format == "json":
        result = {
            "scope": args.product or args.business_line or "消费者BG",
            "status": "partial" if warnings else "ok",
            "warnings": warnings,
            "queried_at": now.isoformat(),
            "periods": {
                "current_mtd": current_period(now),
                "latest_closed": previous_period(now),
                "current_chart_period": chart_period(CURRENT_CHART_ID, now),
                "last_chart_period": chart_period(LAST_CHART_ID, now),
            },
            "summary": None if args.product else summarize_scope(matched),
            "products": [
                {"product_name": pname, "current": current, "last": last, "master": minfo}
                for pname, current, last, minfo in matched
            ],
            "trends": [
                {"title": title, "judgement": format_trend_judgement(rows), "rows": rows}
                for title, rows in trend_sections
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(period_banner(now) + "\n")
    for message in warnings:
        print(f"> 范围/数据提示：{message}\n")
    if args.product and len(matched) == 1:
        pname, current, last, minfo = matched[0]
        print(format_product_report(pname, current, last, minfo))
    elif args.product:
        print(format_product_candidates(args.product, matched))
    else:
        title = f"【{args.business_line}】" if args.business_line else "消费者 BG"
        print(format_scope_summary(title, matched, args.compare, scope_uncertain=bool(unknown)))
        if args.all:
            print("\n\n" + format_business_line_summary(matched))
        print("\n\n" + format_governance_entries(matched))

    if not args.product:
        if trend_sections:
            print("\n\n" + "\n\n".join(format_trend_report(title, rows) for title, rows in trend_sections))
        print("\n\n" + format_full_leaderboard(matched))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as exc:
        if json_output_requested():
            print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        else:
            sys.stderr.write(f"Error: {exc}\n")
        sys.exit(1)
