"""
Safeguard Properties - Daily Report Automation
Version 5 - Fixed Inspections page filter handling
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

PAGE_TIMEOUT = 120000
NAV_WAIT     = 8000
CLICK_WAIT   = 5000


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
                await page.wait_for_timeout(CLICK_WAIT)
                print("  OK Popup closed")
        except Exception:
            print("  No popup found")

        # ── STEP 3: Request Completed Orders Report ─────────────────
        print("  -> Going to Reports page...")
        await page.goto(REPORTS_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)

        print("  -> Clicking New Invoice Summary 30 Days...")
        await page.get_by_text("New Invoice Summary 30 Days", exact=True).first.click()
        await page.wait_for_timeout(CLICK_WAIT)
        print("  OK Report requested - waiting 90 seconds...")
        await asyncio.sleep(90)

        # ── STEP 4: Download Completed Orders ──────────────────────
        print("  -> Going to Report List...")
        await page.goto(LISTING_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)

        links = page.locator("table a")
        link_count = await links.count()
        print(f"  Found {link_count} links in report table")

        if link_count > 0:
            first_link_href = await links.first.get_attribute("href")
            print(f"  -> Clicking first report link: {first_link_href}")
            await links.first.click()
            await page.wait_for_timeout(NAV_WAIT)
            print(f"  -> Now on: {page.url}")

        print("  -> Looking for Download CSV button...")
        csv_btn = page.locator("input[value='Download CSV']")
        print(f"  Found {await csv_btn.count()} Download CSV buttons")

        async with page.expect_download(timeout=60000) as dl:
            await csv_btn.first.click()
        download = await dl.value
        await download.save_as(COMPLETED_FILE)
        print(f"  OK Completed orders saved -> {COMPLETED_FILE}")

        # ── STEP 5: Open Orders ─────────────────────────────────────
        print("  -> Going to Inspections page...")
        await page.goto(INSP_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)
        print(f"  -> Inspections loaded: {await page.title()}")

        # Print ALL inputs on the page to find the inspector filter
        inputs = page.locator("input[type='text'], input[type='search']")
        inp_count = await inputs.count()
        print(f"  Found {inp_count} text inputs on Inspections page")
        for i in range(inp_count):
            val = await inputs.nth(i).get_attribute("value") or ""
            name = await inputs.nth(i).get_attribute("name") or ""
            print(f"  Input {i}: name={name} value={val}")

        # The inspector filter is a TEXT input in the filter row
        # From the screenshot we saw "ASOFFICE" typed in an input field
        # Find it by looking for input containing ASOFFICE or named inspector
        inspector_input = None
        for i in range(inp_count):
            val = await inputs.nth(i).get_attribute("value") or ""
            name = await inputs.nth(i).get_attribute("name") or ""
            if "ASOFFICE" in val.upper() or "inspec" in name.lower() or "perf" in name.lower():
                inspector_input = inputs.nth(i)
                print(f"  -> Found inspector input at index {i}: name={name} value={val}")
                break

        if inspector_input:
            # Clear the inspector field so it shows ALL inspectors
            await inspector_input.triple_click()
            await inspector_input.fill("")
            await page.keyboard.press("Tab")
            await page.wait_for_timeout(8000)
            print("  OK Cleared inspector filter - showing all inspectors")
        else:
            print("  WARNING: Inspector input not found - downloading as-is")

        # Click Filtered List to Excel
        print("  -> Clicking Filtered List to Excel...")
        excel_btn = page.locator("input[value='Filtered List to Excel']")
        btn_count = await excel_btn.count()
        print(f"  Found {btn_count} Filtered List to Excel buttons")

        async with page.expect_download(timeout=60000) as dl:
            await excel_btn.first.click()
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
