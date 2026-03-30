"""
Safeguard Properties - Daily Report Automation
Runs every morning at 6:00 AM via GitHub Actions
Pulls: 1) Completed Orders (Invoice Summary 30 Days)
       2) Open Orders with Due Dates (Inspections filtered list)
"""

import asyncio
import os
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
OUTPUT_DIR       = "data"
COMPLETED_FILE   = f"{OUTPUT_DIR}/completed_orders.csv"
OPEN_ORDERS_FILE = f"{OUTPUT_DIR}/open_orders.xlsx"
LAST_UPDATED     = f"{OUTPUT_DIR}/last_updated.txt"


async def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    print(f"[{today}] Starting Safeguard automation...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page    = await context.new_page()

        # ── STEP 1: Login ──────────────────────────────────────────
        print("  -> Logging in...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Fill vendor code - first text input on the page
        await page.locator("input[type='text']").first.fill(VENDOR_CODE)
        await page.wait_for_timeout(500)

        # Fill password
        await page.locator("input[type='password']").first.fill(PASSWORD)
        await page.wait_for_timeout(500)

        # Click Login
        await page.locator("input[type='submit']").first.click()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(3000)
        print(f"  OK Logged in - URL: {page.url}")

        # ── STEP 2: Close popup if present ─────────────────────────
        try:
            close_btn = page.locator("input[value='Close']")
            if await close_btn.count() > 0:
                await close_btn.first.click()
                await page.wait_for_load_state("networkidle")
                print("  OK Closed popup")
        except Exception:
            print("  No popup, continuing...")

        # ── STEP 3: Request Completed Orders report ─────────────────
        print("  -> Requesting completed orders report...")
        await page.goto(REPORTS_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.get_by_text("New Invoice Summary 30 Days", exact=True).first.click()
        await page.wait_for_load_state("networkidle")
        print("  OK Report requested - waiting 75 seconds...")
        await asyncio.sleep(75)

        # ── STEP 4: Report List and download ───────────────────────
        print("  -> Going to Report List...")
        await page.goto(LISTING_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.locator("table tr").nth(1).click()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        print("  -> Downloading completed orders CSV...")
        async with page.expect_download(timeout=30000) as dl:
            await page.locator("input[value='Download CSV']").click()
        download = await dl.value
        await download.save_as(COMPLETED_FILE)
        print(f"  OK Completed orders saved -> {COMPLETED_FILE}")

        # ── STEP 5: Open Orders ─────────────────────────────────────
        print("  -> Pulling open orders with due dates...")
        await page.goto(INSP_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Find and change Inspector dropdown to All
        selects = page.locator("select")
        sel_count = await selects.count()
        for i in range(sel_count):
            inner = await selects.nth(i).inner_text()
            if "ASOFFICE" in inner:
                await selects.nth(i).select_option(index=0)
                print("  OK Changed inspector to All")
                break
        await page.wait_for_timeout(3000)

        print("  -> Downloading open orders Excel...")
        async with page.expect_download(timeout=30000) as dl:
            await page.locator("input[value='Filtered List to Excel']").click()
        download = await dl.value
        await download.save_as(OPEN_ORDERS_FILE)
        print(f"  OK Open orders saved -> {OPEN_ORDERS_FILE}")

        # ── STEP 6: Timestamp ───────────────────────────────────────
        with open(LAST_UPDATED, "w") as f:
            f.write(today)

        await browser.close()
        print(f"\nDONE! Both reports downloaded at {today}")


if __name__ == "__main__":
    asyncio.run(run())
