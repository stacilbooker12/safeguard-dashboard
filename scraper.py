"""
Safeguard Properties - Daily Report Automation
Version 3 - Built for slow site with extended timeouts throughout
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

OUTPUT_DIR       = "data"
COMPLETED_FILE   = f"{OUTPUT_DIR}/completed_orders.csv"
OPEN_ORDERS_FILE = f"{OUTPUT_DIR}/open_orders.xlsx"
LAST_UPDATED     = f"{OUTPUT_DIR}/last_updated.txt"

# How long to wait for slow pages (ms)
PAGE_TIMEOUT = 120000   # 2 minutes per page load
CLICK_WAIT   = 5000     # 5 seconds after every click
NAV_WAIT     = 8000     # 8 seconds after navigation


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
        print("  -> Loading login page (slow site - please wait)...")
        await page.goto(LOGIN_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)
        print(f"  -> Page loaded: {await page.title()}")

        print("  -> Entering credentials...")
        await page.locator("input[type='text']").first.fill(VENDOR_CODE)
        await page.wait_for_timeout(1000)
        await page.locator("input[type='password']").first.fill(PASSWORD)
        await page.wait_for_timeout(1000)

        print("  -> Clicking Login...")
        await page.locator("input[type='submit']").first.click()

        # Wait generously for slow redirect
        print("  -> Waiting for site to redirect after login...")
        await page.wait_for_timeout(10000)
        print(f"  -> URL after login: {page.url}")

        # If still on login page, wait more
        if "login" in page.url:
            print("  -> Still on login page, waiting longer...")
            await page.wait_for_timeout(10000)
            print(f"  -> URL now: {page.url}")

        # ── STEP 2: Close popup ────────────────────────────────────
        print("  -> Checking for appointment popup...")
        await page.wait_for_timeout(5000)
        try:
            close_btn = page.locator("input[value='Close']")
            if await close_btn.count() > 0:
                await close_btn.first.click()
                await page.wait_for_timeout(CLICK_WAIT)
                print("  OK Popup closed")
            else:
                print("  No popup found")
        except Exception as e:
            print(f"  Popup: {e}")

        # ── STEP 3: Request Completed Orders Report ─────────────────
        print("  -> Navigating to Reports page...")
        await page.goto(REPORTS_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)
        print(f"  -> Reports page: {await page.title()}")

        print("  -> Clicking New Invoice Summary 30 Days...")
        await page.get_by_text("New Invoice Summary 30 Days", exact=True).first.click()
        await page.wait_for_timeout(CLICK_WAIT)
        print("  OK Report requested!")
        print("  -> Waiting 90 seconds for report to generate on slow server...")
        await asyncio.sleep(90)
        print("  -> Done waiting, heading to Report List...")

        # ── STEP 4: Download Completed Orders ──────────────────────
        await page.goto(LISTING_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)
        print(f"  -> Report List loaded: {await page.title()}")

        print("  -> Clicking first report in list...")
        await page.locator("table tr").nth(1).click()
        await page.wait_for_timeout(CLICK_WAIT)
        print(f"  -> Download page: {page.url}")

        print("  -> Clicking Download CSV...")
        async with page.expect_download(timeout=60000) as dl:
            await page.locator("input[value='Download CSV']").click()
        download = await dl.value
        await download.save_as(COMPLETED_FILE)
        print(f"  OK Completed orders saved -> {COMPLETED_FILE}")

        # ── STEP 5: Open Orders with Due Dates ─────────────────────
        print("  -> Navigating to Inspections page...")
        await page.goto(INSP_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)
        print(f"  -> Inspections page: {await page.title()}")

        # Find and change Inspector dropdown to All
        print("  -> Finding Inspector dropdown...")
        selects = page.locator("select")
        sel_count = await selects.count()
        print(f"  Found {sel_count} dropdowns on page")

        changed = False
        for i in range(sel_count):
            inner = await selects.nth(i).inner_text()
            print(f"  Dropdown {i}: {inner[:100]}")
            if "ASOFFICE" in inner:
                await selects.nth(i).select_option(index=0)
                print(f"  OK Set dropdown {i} to All")
                changed = True
                await page.wait_for_timeout(8000)  # Wait for filter to apply
                break

        if not changed:
            print("  WARNING: Inspector dropdown not found, proceeding anyway")

        print("  -> Clicking Filtered List to Excel...")
        async with page.expect_download(timeout=60000) as dl:
            await page.locator("input[value='Filtered List to Excel']").click()
        download = await dl.value
        await download.save_as(OPEN_ORDERS_FILE)
        print(f"  OK Open orders saved -> {OPEN_ORDERS_FILE}")

        # ── Done ────────────────────────────────────────────────────
        with open(LAST_UPDATED, "w") as f:
            f.write(today)

        await browser.close()
        print(f"\nSUCCESS! Both reports downloaded at {today}")


if __name__ == "__main__":
    asyncio.run(run())
