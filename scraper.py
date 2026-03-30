"""
Safeguard Properties - Daily Report Automation
Version 7 - Fixed inspector dropdown handling with proper wait
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

        # ── STEP 3: Request Completed Orders Report ─────────────────
        print("  -> Going to Reports page...")
        await page.goto(REPORTS_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)

        print("  -> Clicking New Invoice Summary 30 Days...")
        await page.get_by_text("New Invoice Summary 30 Days", exact=True).first.click()
        await page.wait_for_timeout(5000)
        print("  OK Report requested - waiting 90 seconds...")
        await asyncio.sleep(90)

        # ── STEP 4: Download Completed Orders ──────────────────────
        print("  -> Going to Report List...")
        await page.goto(LISTING_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)

        links = page.locator("table a")
        link_count = await links.count()
        print(f"  Found {link_count} links in report table")
        first_link_href = await links.first.get_attribute("href")
        print(f"  -> Clicking: {first_link_href}")
        await links.first.click()
        await page.wait_for_timeout(NAV_WAIT)
        print(f"  -> Now on: {page.url}")

        async with page.expect_download(timeout=60000) as dl:
            await page.locator("input[value='Download CSV']").first.click()
        download = await dl.value
        await download.save_as(COMPLETED_FILE)
        print(f"  OK Completed orders saved -> {COMPLETED_FILE}")

        # ── STEP 5: Open Orders ─────────────────────────────────────
        print("  -> Going to Inspections page...")
        await page.goto(INSP_URL, wait_until="load", timeout=PAGE_TIMEOUT)

        # Wait for the Filtered List to Excel button to confirm page is ready
        print("  -> Waiting for page to fully load...")
        await page.wait_for_selector(
            "input[value='Filtered List to Excel']",
            timeout=60000
        )
        print("  OK Page fully loaded!")

        # Now find ALL select dropdowns and log every one
        selects = page.locator("select")
        sel_count = await selects.count()
        print(f"  Found {sel_count} dropdowns on Inspections page")

        for i in range(sel_count):
            # Get all options in this dropdown
            options = await selects.nth(i).locator("option").all_inner_texts()
            selected = await selects.nth(i).input_value()
            print(f"  Dropdown {i}: selected={selected} options={options[:5]}")

            # Look for the one containing ASOFFICE as selected value
            if "ASOFFICE" in selected.upper():
                print(f"  -> Found Inspector dropdown at index {i} - changing to All")
                # Select the first option (All / blank)
                await selects.nth(i).select_option(index=0)
                selected_after = await selects.nth(i).input_value()
                print(f"  -> Dropdown now set to: {selected_after}")
                await page.wait_for_timeout(8000)
                break

            # Also check if any option contains ASOFFICE
            all_opts = await selects.nth(i).locator("option").all_inner_texts()
            if any("ASOFFICE" in opt.upper() for opt in all_opts):
                print(f"  -> Inspector dropdown found at index {i} - changing to All")
                await selects.nth(i).select_option(index=0)
                selected_after = await selects.nth(i).input_value()
                print(f"  -> Dropdown now set to: {selected_after}")
                await page.wait_for_timeout(8000)
                break

        # Download open orders
        print("  -> Clicking Filtered List to Excel...")
        async with page.expect_download(timeout=60000) as dl:
            await page.locator("input[value='Filtered List to Excel']").first.click()
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
