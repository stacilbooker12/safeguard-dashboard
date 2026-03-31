"""
Safeguard Properties - Daily Report Automation
Version 16 - Direct POST to inspection-list-service.php with all IDs
"""

import asyncio
import os
from datetime import datetime
from playwright.async_api import async_playwright

VENDOR_CODE = os.environ["SAFEGUARD_VENDOR_CODE"]
PASSWORD    = os.environ["SAFEGUARD_PASSWORD"]

BASE_URL    = "https://inspi2.safeguardproperties.com/inspi2"
LOGIN_URL   = f"{BASE_URL}/login.php"
REPORTS_URL = f"{BASE_URL}/reports/main.php"
LISTING_URL = f"{BASE_URL}/reports/listing.php"
INSP_URL    = f"{BASE_URL}/inspsvc/main.php"
EXPORT_URL  = f"{BASE_URL}/inspsvc/inspection-list-service.php?oper=excelFilter"

OUTPUT_DIR       = "data"
COMPLETED_FILE   = f"{OUTPUT_DIR}/completed_orders.csv"
OPEN_ORDERS_FILE = f"{OUTPUT_DIR}/open_orders.xlsx"
LAST_UPDATED     = f"{OUTPUT_DIR}/last_updated.txt"

PAGE_TIMEOUT = 120000
NAV_WAIT     = 8000


async def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    print(f"[{today}] Starting Safeguard automation...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT)

        # ── STEP 1: Login ──────────────────────────────────────────
        print("  -> Loading login page...")
        await page.goto(LOGIN_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)
        await page.locator("input[type='text']").first.fill(VENDOR_CODE)
        await page.wait_for_timeout(1000)
        await page.locator("input[type='password']").first.fill(PASSWORD)
        await page.wait_for_timeout(1000)
        print("  -> Clicking Login...")
        await page.locator("input[type='submit']").first.click()
        await page.wait_for_timeout(10000)
        print(f"  -> URL after login: {page.url}")

        # ── STEP 2: Close popup ────────────────────────────────────
        await page.wait_for_timeout(5000)
        try:
            close_btn = page.locator("input[value='Close']")
            if await close_btn.count() > 0:
                await close_btn.first.click()
                await page.wait_for_timeout(5000)
                print("  OK Popup closed")
        except Exception:
            print("  No popup found")

        # ── STEP 3: Count existing reports BEFORE requesting ────────
        print("  -> Checking current report count...")
        await page.goto(LISTING_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)
        initial_count = await page.locator("table a").count()
        print(f"  -> Reports before request: {initial_count}")

        # ── STEP 4: Request new report ─────────────────────────────
        print("  -> Requesting New Invoice Summary 30 Days...")
        await page.goto(REPORTS_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)
        await page.get_by_text("New Invoice Summary 30 Days", exact=True).first.click()
        await page.wait_for_timeout(5000)
        print("  OK Report requested!")

        # ── STEP 5: Wait for new report to appear ──────────────────
        print("  -> Waiting for new report to appear...")
        new_count = initial_count
        for attempt in range(30):
            await page.goto(LISTING_URL, wait_until="load", timeout=PAGE_TIMEOUT)
            await page.wait_for_timeout(5000)
            new_count = await page.locator("table a").count()
            print(f"  -> Attempt {attempt+1}: {new_count} reports")
            if new_count > initial_count:
                print(f"  OK New report appeared!")
                break
            if attempt < 29:
                await asyncio.sleep(15)

        # ── STEP 6: Download completed orders ──────────────────────
        print("  -> Clicking newest report...")
        links = page.locator("table a")
        first_href = await links.first.get_attribute("href")
        print(f"  -> Clicking: {first_href}")
        await links.first.click()
        await page.wait_for_timeout(NAV_WAIT)
        async with page.expect_download(timeout=60000) as dl:
            await page.locator("input[value='Download CSV']").first.click()
        download = await dl.value
        await download.save_as(COMPLETED_FILE)
        print(f"  OK Completed orders saved -> {COMPLETED_FILE}")

        # ── STEP 7: Open Orders via direct API call ─────────────────
        print("  -> Going to Inspections page to get session/CSRF...")
        await page.goto(INSP_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_selector("#btnFilteredExcel", timeout=60000)
        print("  OK Inspections page fully loaded!")

        # Clear filter and get ALL work order IDs via Tabulator API
        print("  -> Clearing filter and collecting all work order IDs...")
        await page.evaluate("() => { window.InspectionTabulator.clearFilter(true); }")
        await page.wait_for_timeout(5000)

        # Use Full List to Excel — download all orders, dashboard will filter to Assigned only
        print("  -> Clicking Full List to Excel...")
        async with page.expect_download(timeout=60000) as dl:
            await page.locator("#btnFullExcel").click()
        download = await dl.value
        await download.save_as(OPEN_ORDERS_FILE)
        print(f"  OK Open orders saved -> {OPEN_ORDERS_FILE}")
        else:
            print("  ERROR: Could not get IDs or CSRF token")
            # Fallback: just click the button
            async with page.expect_download(timeout=60000) as dl:
                await page.locator("#btnFilteredExcel").click()
            download = await dl.value
            await download.save_as(OPEN_ORDERS_FILE)
            print(f"  OK Open orders saved (fallback) -> {OPEN_ORDERS_FILE}")

        # ── Done ────────────────────────────────────────────────────
        with open(LAST_UPDATED, "w") as f:
            f.write(today)
        await browser.close()
        print(f"\nSUCCESS! Both reports downloaded at {today}")


if __name__ == "__main__":
    asyncio.run(run())
