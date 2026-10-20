import json
import os
import sys
import time
from playwright.sync_api import sync_playwright

EVIDENCE_DIR = os.path.abspath(os.environ.get("RDHS_E2E_EVIDENCE", "runtime/business-line-dashboard-evidence"))
os.makedirs(EVIDENCE_DIR, exist_ok=True)

BASE_URL = os.environ.get("RDHS_E2E_URL", "http://localhost:8089/meegle-rdhs-report/")

logs = []

def log(msg):
    print(f"[E2E] {msg}")
    logs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def run_acceptance():
    log("Starting comprehensive browser acceptance tests...")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        # -------------------------------------------------------------
        # Desktop Suite (1280x800)
        # -------------------------------------------------------------
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: errors.append(f"HTTP {response.status}: {response.url}") if response.status >= 400 else None)

        # Scenario 1: BG View default
        log("Scenario 1: Opening initial BG View at " + BASE_URL)
        page.goto(BASE_URL)
        page.wait_for_selector(".bentoWarReportContainer")
        log(f"Page title: {page.title()}")
        assert "CBG RDHS运营报告" in page.title()

        page.screenshot(path=os.path.join(EVIDENCE_DIR, "01-desktop-bg-view.png"))
        log("Saved 01-desktop-bg-view.png")

        # Scenario 2: Drilldown from BG matrix to line workbench
        log("Scenario 2: Clicking line '开放平台业务群' to drilldown into workbench")
        # Target the row in bentoTable with 开放平台业务群
        line_row = page.locator("tr.bentoTableRow", has_text="开放平台业务群")
        line_row.first.click()
        page.wait_for_selector(".lineCtoDashboard")
        time.sleep(0.5)

        # Check KPI summary elements
        hero_score = page.locator(".lineCtoHeroScoreNum").inner_text()
        log(f"Line Hero Score: {hero_score} 分")
        assert len(hero_score) > 0
        assert "line=" in page.url and "view=workbench" in page.url

        # Check sublines section
        sublines_count = page.locator(".sublineCard").count()
        log(f"Second-level sublines displayed: {sublines_count} cards")
        assert sublines_count > 0

        # Check governance recommendations (Top 3)
        gov_rec_count = page.locator(".govRecCard").count()
        log(f"Governance recommendation cards: {gov_rec_count}")
        assert gov_rec_count <= 3 and gov_rec_count > 0

        page.screenshot(path=os.path.join(EVIDENCE_DIR, "02-desktop-line-workbench.png"))
        log("Saved 02-desktop-line-workbench.png")

        # Scenario 3: Subline filter isolation
        log("Scenario 3: Clicking first subline card to isolate product list")
        first_subline_name = page.locator(".sublineCard .sublineName").first.inner_text()
        log(f"Filtering by subline: '{first_subline_name}'")
        page.locator(".sublineCard").first.click()
        time.sleep(0.4)

        # Invariant check: top hero score must remain unchanged
        hero_score_after_subline = page.locator(".lineCtoHeroScoreNum").inner_text()
        assert hero_score == hero_score_after_subline, f"Top average changed: {hero_score} -> {hero_score_after_subline}"
        log(f"Verified filter isolation invariant: whole-line avg score remained {hero_score} 分")

        page.screenshot(path=os.path.join(EVIDENCE_DIR, "03-desktop-subline-filter.png"))
        log("Saved 03-desktop-subline-filter.png")

        # Scenario 4: Product detail expansion
        log("Scenario 4: Inspecting first product detail")
        page.locator(".productList button.productRow").first.click()
        page.wait_for_selector("aside.detail .detailContent", state="visible")
        detail_score_label = page.locator("aside.detail .detailScoreLabel").inner_text()
        log(f"Product detail score label: {detail_score_label}")

        page.screenshot(path=os.path.join(EVIDENCE_DIR, "04-desktop-product-detail.png"))
        log("Saved 04-desktop-product-detail.png")

        # Scenario 5: Governance recommendation locate
        log("Scenario 5: Testing '定位至产品明细' from governance recommendation card")
        page.locator(".govRecBtn").first.click()
        time.sleep(0.4)
        active_product_title = page.locator("aside.detail .detailTitle").inner_text()
        log(f"Located and opened product detail for: {active_product_title}")

        page.screenshot(path=os.path.join(EVIDENCE_DIR, "05-desktop-locate-product.png"))
        log("Saved 05-desktop-locate-product.png")

        # Scenario 6: Return to BG
        log("Scenario 6: Clicking '返回 BG 全局大盘'")
        page.locator("button.backBtnPill").click()
        page.wait_for_selector(".bentoWarReportContainer")
        time.sleep(0.3)
        assert page.locator(".viewPaneBg").is_visible()
        log("Returned to BG view successfully")

        page.screenshot(path=os.path.join(EVIDENCE_DIR, "06-desktop-return-to-bg.png"))
        log("Saved 06-desktop-return-to-bg.png")

        # Scenario 7: Direct query URL bootstrap and Share URL
        direct_url = BASE_URL + "?period=2026-08&view=workbench&line=" + "开放平台业务群"
        log(f"Scenario 7: Navigating directly to {direct_url}")
        page.goto(direct_url)
        page.wait_for_selector(".lineCtoDashboard")
        time.sleep(0.5)

        # Reload to test static SPA query bootstrap
        page.reload()
        page.wait_for_selector(".lineCtoDashboard")
        log("Static SPA query bootstrap survived reload")
        snapshot = json.load(open("data/snapshots/2026-08.json", encoding="utf-8"))
        scope = [p for p in snapshot["products"] if p["businessLine"] == "开放平台业务群"]
        expected = sum(p["rdhs"] or 0 for p in scope) / len(scope)
        actual = float(page.locator(".lineCtoHeroScoreNum").inner_text())
        assert abs(actual - expected) <= 0.051, f"Data mismatch: {actual} != {expected}"
        page.locator('input[type="search"]').fill(scope[0]["product"])
        assert float(page.locator(".lineCtoHeroScoreNum").inner_text()) == actual
        page.locator('input[type="search"]').fill("")
        page.locator('select[aria-label="按治理分档筛选"]').select_option("重点治理")
        assert float(page.locator(".lineCtoHeroScoreNum").inner_text()) == actual
        page.locator('select[aria-label="按治理分档筛选"]').select_option("全部分档")
        log(f"Independent product-score recomputation matches: {actual:.1f}; search/band filters leave KPI unchanged")

        # Test share URL button
        share_btn = page.locator("button.shareUrlBtn")
        assert share_btn.is_visible()
        share_btn.click()
        time.sleep(0.2)
        share_text = share_btn.inner_text()
        log(f"Share button state after click: '{share_text}'")
        assert "链接已复制" in share_text

        page.screenshot(path=os.path.join(EVIDENCE_DIR, "07-desktop-direct-url-reload.png"))
        log("Saved 07-desktop-direct-url-reload.png")

        # Scenario 8: Browser History Back and Forward
        log("Scenario 8: Testing browser history back and forward")
        # Select another line via dropdown
        page.locator(".lineFilterSelect").select_option("讯飞听见")
        time.sleep(0.4)
        log("Switched line to 讯飞听见")
        assert "讯飞听见" in page.locator(".currentLineTitle").inner_text()

        # Go back
        page.go_back()
        time.sleep(0.5)
        log("Called browser back; verifying restoration of 开放平台业务群")
        assert "开放平台业务群" in page.locator(".currentLineTitle").inner_text()

        # Go forward
        page.go_forward()
        time.sleep(0.5)
        log("Called browser forward; verifying advance to 讯飞听见")
        assert "讯飞听见" in page.locator(".currentLineTitle").inner_text()

        page.screenshot(path=os.path.join(EVIDENCE_DIR, "08-desktop-browser-history.png"))
        log("Saved 08-desktop-browser-history.png")

        # Scenario 9: Month Switching
        log("Scenario 9: Switching month to 2026-07")
        page.locator(".barControls select").select_option("2026-07")
        time.sleep(0.5)
        log(f"Current period text in nav: {page.locator('.barControls select').input_value()}")
        assert page.locator(".barControls select").input_value() == "2026-07"

        page.screenshot(path=os.path.join(EVIDENCE_DIR, "09-desktop-month-switch.png"))
        log("Saved 09-desktop-month-switch.png")

        # Scenario 10: Invalid line handling
        invalid_line_url = BASE_URL + "?period=2026-08&view=workbench&line=不存在的业务线"
        log(f"Scenario 10: Opening invalid line URL: {invalid_line_url}")
        page.goto(invalid_line_url)
        time.sleep(0.5)
        banner_text = page.locator(".bannerNotice.warning").inner_text()
        log(f"Invalid line banner rendered: '{banner_text}'")
        assert "未在 2026-08 快照中找到业务线" in banner_text

        page.screenshot(path=os.path.join(EVIDENCE_DIR, "10-desktop-invalid-line-notice.png"))
        log("Saved 10-desktop-invalid-line-notice.png")

        # Scenario 11: Missing period notice
        missing_period_url = BASE_URL + "?period=2025-01&view=workbench"
        log(f"Scenario 11: Opening missing period URL: {missing_period_url}")
        page.goto(missing_period_url)
        time.sleep(0.5)
        missing_banner = page.locator(".bannerNotice.warning").inner_text()
        log(f"Missing period banner rendered: '{missing_banner}'")
        assert "2025-01" in missing_banner and "暂无有效快照" in missing_banner

        page.screenshot(path=os.path.join(EVIDENCE_DIR, "11-desktop-missing-period-notice.png"))
        log("Saved 11-desktop-missing-period-notice.png")

        # Returning in browser history to an URL without line/view must reset both.
        page.goto(BASE_URL)
        page.wait_for_selector(".bentoWarReportContainer")
        page.locator("tr.bentoTableRow", has_text="开放平台业务群").first.click()
        page.wait_for_selector(".lineCtoDashboard")
        page.go_back()
        page.wait_for_selector(".bentoWarReportContainer")
        page.go_forward()
        page.wait_for_selector(".lineCtoDashboard")
        log("Verified history restoration when original URL contains no query parameters")
        assert not errors, f"Desktop browser errors: {errors}"
        context.close()

        # -------------------------------------------------------------
        # Mobile Suite (iPhone 14 viewport: 390x844)
        # -------------------------------------------------------------
        log("Starting Mobile Viewport Acceptance (390x844)...")
        mobile_context = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        )
        mobile_page = mobile_context.new_page()
        mobile_page.on("pageerror", lambda error: errors.append(str(error)))
        mobile_page.on("response", lambda response: errors.append(f"HTTP {response.status}: {response.url}") if response.status >= 400 else None)

        mobile_target_url = BASE_URL + "?period=2026-08&view=workbench&line=" + "开放平台业务群"
        log(f"Scenario 12: Opening mobile workbench view at {mobile_target_url}")
        mobile_page.goto(mobile_target_url)
        mobile_page.wait_for_selector(".lineCtoDashboard")
        time.sleep(0.5)

        mobile_page.screenshot(path=os.path.join(EVIDENCE_DIR, "12-mobile-line-workbench.png"), full_page=True)
        assert mobile_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile page overflows viewport"
        log("Saved 12-mobile-line-workbench.png")

        # Test mobile product expand
        log("Scenario 13: Opening inline mobile product detail")
        mobile_page.locator(".productList button.productRow").first.click()
        mobile_page.wait_for_selector(".detailContent.mobile")
        time.sleep(0.3)

        mobile_page.screenshot(path=os.path.join(EVIDENCE_DIR, "13-mobile-product-detail.png"), full_page=True)
        assert not errors, f"Browser errors: {errors}"
        log("Saved 13-mobile-product-detail.png")

        mobile_context.close()
        browser.close()

    log("All 13 acceptance scenarios completed successfully!")

if __name__ == "__main__":
    try:
        run_acceptance()
        with open(os.path.join(EVIDENCE_DIR, "acceptance.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(logs))
    except Exception as e:
        log(f"FAILED: {e}")
        with open(os.path.join(EVIDENCE_DIR, "acceptance.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(logs))
        sys.exit(1)
