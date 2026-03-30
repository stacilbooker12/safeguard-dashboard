"""
Safeguard Properties - Daily Report Automation
Runs every morning at 6:00 AM via GitHub Actions
Pulls: 1) Completed Orders (Invoice Summary 30 Days)
       2) Open Orders with Due Dates (Inspections filtered list)
"""

import asyncio
import os
import time
from datetime import datetime
from playwright.async_api import async_playwright

# ─── CREDENTIALS (stored as GitHub Secrets, never hardcoded) ───
VENDOR_CODE = os.environ["SAFEGUARD_VENDOR_CODE"]
PASSWORD    = os.environ["SAFEGUARD_PASSWORD"]

# ─── URLS ───
BASE_URL    = "https://inspi2.safeguardproperties.com/inspi2"
LOGIN_URL   = f"{BASE_URL}/login.php"
REPORTS_URL = f"{BASE_URL}/reports/main.php"
LISTING_URL = f"{BASE_URL}/reports/listing.php"
INSP_URL    = f"{BASE_URL}/inspsvc/main.php"

# ─── OUTPUT PATHS ───
OUTPUT_DIR         = "data"
COMPLETED_FILE     = f"{OUTPUT_DIR}/completed_orders.csv"
OPEN_ORDERS_FILE   = f"{OUTPUT_DIR}/open_orders.xlsx"
LAST_UPDATED_FILE  = f"{OUTPUT_DIR}/last_updated.txt"


async def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    print(f"[{today}] Starting Safeguard automation...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page    = await context.new_page()

        # ── STEP 1: Login ──────────────────────────────────────────
        print("  → Logging in...")
        await page.goto(LOGIN_URL)
        await page.fill('input[name="VendorCode"]', VENDOR_CODE)
        await page.fill('input[name="Password"]',   PASSWORD)
        await page.click('input[type="submit"]')
        await page.wait_for_load_state("networkidle")
        print("  ✓ Logged in")

        # ── STEP 2: Close popup if present ─────────────────────────
        try:
            close_btn = page.locator('input[value="Close"], button:has-text("Close")')
            if await close_btn.count() > 0:
                await close_btn.first.click()
                await page.wait_for_load_state("networkidle")
                print("  ✓ Closed popup")
        except Exception:
            pass  # No popup, continue

        # ── STEP 3: Request Completed Orders report ─────────────────
        print("  → Requesting completed orders report...")
        await page.goto(REPORTS_URL)
        await page.wait_for_load_state("networkidle")
        await page.click('text="New Invoice Summary 30 Days"')
        await page.wait_for_load_state("networkidle")
        print("  ✓ Report requested — waiting for it to generate...")

        # Wait up to 90 seconds for report to generate
        await asyncio.sleep(60)

        # ── STEP 4: Go to Report List and download ──────────────────
        print("  → Going to Report List...")
        await page.goto(LISTING_URL)
        await page.wait_for_load_state("networkidle")

        # Click the first (most recent) report in the list
        first_report = page.locator("table tr").nth(1).locator("a, td")
        await first_report.first.click()
        await page.wait_for_load_state("networkidle")

        # Click Download CSV
        print("  → Downloading completed orders CSV...")
        async with page.expect_download() as download_info:
            await page.click('input[value="Download CSV"], button:has-text("Download CSV")')
        download = await download_info.value
        await download.save_as(COMPLETED_FILE)
        print(f"  ✓ Completed orders saved → {COMPLETED_FILE}")

        # ── STEP 5: Open Orders with Due Dates ─────────────────────
        print("  → Pulling open orders with due dates...")
        await page.goto(INSP_URL)
        await page.wait_for_load_state("networkidle")

        # Change Inspector dropdown from ASOFFICE to All
        await page.select_option('select[name*="nspec"], select', label="All")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)  # Let the filter apply

        # Click Filtered List to Excel
        print("  → Downloading open orders Excel...")
        async with page.expect_download() as download_info:
            await page.click('input[value="Filtered List to Excel"], button:has-text("Filtered List to Excel")')
        download = await download_info.value
        await download.save_as(OPEN_ORDERS_FILE)
        print(f"  ✓ Open orders saved → {OPEN_ORDERS_FILE}")

        # ── STEP 6: Write last updated timestamp ───────────────────
        with open(LAST_UPDATED_FILE, "w") as f:
            f.write(today)

        await browser.close()
        print(f"\n✅ All done! Both reports downloaded at {today}")


if __name__ == "__main__":
    asyncio.run(run())
