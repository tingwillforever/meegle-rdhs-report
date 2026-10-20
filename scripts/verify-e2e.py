#!/usr/bin/env python3
"""End-to-End Real Browser Verification for RDHS Unified GitHub Pages Site."""

import functools
import http.server
import os
from pathlib import Path
import socketserver
import threading
import time
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
STATIC_DIR = Path(__file__).resolve().parents[1] / "dist" / "static"
SCREENSHOT_DIR = Path(__file__).resolve().parents[1] / "dist" / "e2e-screenshots"
PORT = 8089


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format, *args):
        pass  # Quiet logging


def start_server():
    try:
        server = socketserver.TCPServer(("127.0.0.1", PORT), QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server
    except OSError:
        # Server already running on port, reuse it
        return None


def main():
    if not STATIC_DIR.exists():
        raise RuntimeError(f"Static directory does not exist: {STATIC_DIR}")
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    print("==> 1. 启动本地静态服务器 (http://127.0.0.1:8089)...")
    server = start_server()
    time.sleep(0.5)

    print("==> 2. 启动原生无头 Chrome 浏览器运行端到端验收...")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        console_errors = []
        page.on("pageerror", lambda err: console_errors.append(f"PageError: {err}"))
        page.on(
            "console",
            lambda msg: console_errors.append(f"ConsoleError: {msg.text}")
            if msg.type == "error"
            else None,
        )

        base_url = f"http://127.0.0.1:{PORT}"

        # -------------------------------------------------------------------
        # Test 1: Initial Load & BG War Report View
        # -------------------------------------------------------------------
        print("\n--- [测试用例 1] 默认首页加载与 BG 顶层战报视图 ---")
        page.goto(f"{base_url}/")
        page.wait_for_selector(".dashboardShell")

        # 验证标题与顶部栏
        assert "CBG RDHS运营报告" in page.title(), f"Title mismatch: {page.title()}"
        bg_tab = page.locator(".viewTabBtn.active")
        assert "BG 全局大盘" in bg_tab.inner_text() or "BG 全局战报" in bg_tab.inner_text(), "Default view tab is not BG 全局大盘"
        print("  ✓ 默认进入【BG 全局战报】视图")

        # 验证 Bento Grid 结构 (Hero 卡片 + 4 个指标胶囊)
        bento_hero = page.locator(".bentoHero")
        assert bento_hero.is_visible(), "Bento hero card is not visible"
        metric_capsules = page.locator(".metricCapsule")
        assert metric_capsules.count() == 4, f"Expected 4 metric capsules, got {metric_capsules.count()}"
        print("  ✓ Bento 英雄大卡与 4 项指标胶囊渲染正常")

        # 验证最需关注治理业务线 (Top 3 攻坚重点)
        focus_section = page.locator(".focusSectionWrap")
        assert focus_section.is_visible(), "Top 3 攻坚重点板块未显示"
        focus_cards = page.locator(".focusBentoCard")
        assert focus_cards.count() == 3, f"Expected 3 focus cards, got {focus_cards.count()}"
        first_focus_title = focus_cards.nth(0).locator(".focusCardTitle").inner_text()
        second_focus_title = focus_cards.nth(1).locator(".focusCardTitle").inner_text()
        third_focus_title = focus_cards.nth(2).locator(".focusCardTitle").inner_text()
        print(f"  ✓ Top 3 攻坚业务线卡片存在: 1.{first_focus_title} 2.{second_focus_title} 3.{third_focus_title}")

        # 验证 9 大业务线综合考核矩阵
        table_rows = page.locator(".bentoTable tbody tr")
        assert table_rows.count() == 9, f"Expected 9 rows in ranking table, got {table_rows.count()}"
        print("  ✓ 9 大一级业务线综合考核矩阵完整渲染 (9 条记录)")

        page.screenshot(path=str(SCREENSHOT_DIR / "01_bento_dashboard.png"), full_page=True)
        print("  ✓ 已截图: 01_bento_dashboard.png")

        # -------------------------------------------------------------------
        # Test 2: Drill-down from Top 3 Focus Card into Workbench
        # -------------------------------------------------------------------
        print("\n--- [测试用例 2] 从 Top 3 攻坚卡片下钻穿透到业务明细工作台 ---")
        # 点击第 2 张卡片 (企业数字化业务群) 的下钻按钮
        target_card = focus_cards.nth(1)
        target_name = target_card.locator(".focusCardTitle").inner_text()
        print(f"  --> 点击攻坚卡片下钻: 【{target_name}】")
        target_card.locator(".focusActionBtn").click()

        # 等待视图切换完成
        page.wait_for_timeout(300)
        workbench_pane = page.locator(".viewPaneWorkbench")
        bg_pane = page.locator(".viewPaneBg")
        assert workbench_pane.is_visible(), "Workbench pane is not visible after drilldown"
        assert not bg_pane.is_visible(), "BG pane is still visible after drilldown"

        # 验证一体化顶栏与筛选联动
        header = page.locator(".workstationNavHeader")
        assert header.is_visible(), "Workstation nav header is not visible"
        line_title = page.locator(".currentLineTitle").inner_text()
        assert target_name in line_title, f"Header title does not contain {target_name}"
        print(f"  ✓ 工作台一体化顶栏已显示: 【{line_title}】")

        line_select = page.locator(".lineFilterSelect")
        selected_line_val = line_select.input_value()
        assert selected_line_val == target_name, f"Expected selected line {target_name}, got {selected_line_val}"
        print(f"  ✓ 工作台业务线筛选器已自动锁定为: 【{selected_line_val}】")

        # 验证工作台产品列表仅展示该业务线的产品
        product_rows = page.locator(".productList .productRow")
        product_count = product_rows.count()
        print(f"  ✓ 产品工作台已联动过滤，展示产品数: {product_count} 款")
        assert product_count > 0, "No products shown for drilled-down business line"

        page.screenshot(path=str(SCREENSHOT_DIR / "02_drilldown_focus_card.png"))
        print("  ✓ 已截图: 02_drilldown_focus_card.png")

        # -------------------------------------------------------------------
        # Test 3: Return to BG War Report
        # -------------------------------------------------------------------
        print("\n--- [测试用例 3] 从工作台平滑返回 BG 全局战报 ---")
        return_btn = page.locator(".backBtnPill")
        assert return_btn.is_visible(), "Return to BG button is not visible"
        return_btn.click()
        page.wait_for_timeout(300)

        assert bg_pane.is_visible(), "BG pane is not visible after returning"
        assert not workbench_pane.is_visible(), "Workbench pane is still visible after returning"
        print("  ✓ 成功返回 BG 全局战报视图，视线重置")

        # -------------------------------------------------------------------
        # Test 4: Drill-down from Ranking Table Row Action
        # -------------------------------------------------------------------
        print("\n--- [测试用例 4] 从综合排行表格中穿透下钻 (AI文娱业务群) ---")
        # 找到包含 AI文娱业务群 的行
        ai_row = page.locator(".bentoTable tbody tr", has_text="AI文娱业务群")
        assert ai_row.count() == 1, "AI文娱业务群 row not found"
        ai_row.locator(".drilldownActionBtn").click()
        page.wait_for_timeout(300)

        assert workbench_pane.is_visible(), "Workbench pane is not visible"
        selected_line_val = page.locator(".lineFilterSelect").input_value()
        assert selected_line_val == "AI文娱业务群", f"Expected AI文娱业务群, got {selected_line_val}"
        print(f"  ✓ 排行榜下钻成功，工作台筛选器锁定为: 【{selected_line_val}】")
        page.screenshot(path=str(SCREENSHOT_DIR / "03_drilldown_table_action.png"))
        print("  ✓ 已截图: 03_drilldown_table_action.png")

        # -------------------------------------------------------------------
        # Test 5: Month Switching & Cross-View Continuity
        # -------------------------------------------------------------------
        print("\n--- [测试用例 5] 顶栏月份切换与跨视图状态保持 ---")
        period_select = page.locator(".barControls select")
        period_select.select_option("2026-08")
        page.wait_for_timeout(300)

        # 验证顶栏月份是否已切换为 2026-08
        selected_period = period_select.input_value()
        assert selected_period == "2026-08", f"Expected 2026-08, got {selected_period}"
        print(f"  ✓ 顶栏月份成功切换为: {selected_period}")

        # 切换回 BG 全局战报，验证也是 2026-08
        page.locator(".viewTabBtn", has_text="BG 全局").click()
        page.wait_for_timeout(300)
        hero_period = page.locator(".periodChip").inner_text()
        assert "2026-08" in hero_period, f"Expected 2026-08 in hero chip, got {hero_period}"
        print(f"  ✓ 切换回 BG 全局大盘，期数保持同步为: {hero_period}")
        page.screenshot(path=str(SCREENSHOT_DIR / "04_month_switch_august.png"))
        print("  ✓ 已截图: 04_month_switch_august.png")

        # -------------------------------------------------------------------
        # Test 6: Deep Linking with URL Query Parameters
        # -------------------------------------------------------------------
        print("\n--- [测试用例 6] URL 参数直链直达 (Deep Linking) ---")
        page.goto(f"{base_url}/?period=2026-07&view=workbench&line=讯飞听见")
        page.wait_for_selector(".dashboardShell")
        page.wait_for_timeout(300)

        assert workbench_pane.is_visible(), "Workbench should be visible via direct URL"
        assert page.locator(".barControls select").input_value() == "2026-07", "Period not 2026-07"
        assert page.locator(".lineFilterSelect").input_value() == "讯飞听见", "Line not 讯飞听见"
        print("  ✓ 成功通过直链直达: 2026-07 期 / 业务明细工作台 / 讯飞听见")
        page.screenshot(path=str(SCREENSHOT_DIR / "05_deep_linking.png"))
        print("  ✓ 已截图: 05_deep_linking.png")

        # -------------------------------------------------------------------
        # Test 7: Console & Runtime Errors Check
        # -------------------------------------------------------------------
        print("\n--- [测试用例 7] 浏览器控制台运行报错排查 ---")
        if console_errors:
            print("  ✗ 出现浏览器控制台错误:")
            for err in console_errors:
                print(f"    - {err}")
            raise AssertionError(f"Console errors found: {len(console_errors)}")
        else:
            print("  ✓ 浏览器运行全程 0 报错、0 警告异常")

        browser.close()

    if server:
        server.shutdown()
    print("\n🎉 端到端真实验收测试全部通过 (7/7 用例 100% 成功)！")


if __name__ == "__main__":
    main()
