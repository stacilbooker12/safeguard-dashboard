"""
Safeguard Properties - Daily Report Automation
Version 14 - Call getGridIDs(false) then submit form directly
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

        # ── STEP 7: Open Orders ─────────────────────────────────────
        print("  -> Going to Inspections page...")
        await page.goto(INSP_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_selector("#btnFilteredExcel", timeout=60000)
        print("  OK Inspections page fully loaded!")

        # Clear InspectionTabulator filter to show all inspectors
        print("  -> Clearing InspectionTabulator filter...")
        await page.evaluate("() => { window.InspectionTabulator.clearFilter(true); }")
        await page.wait_for_timeout(5000)

        row_count = await page.evaluate("() => window.InspectionTabulator.getDataCount()")
        print(f"  -> Row count after clear: {row_count}")

        # Call getGridIDs(false) to populate the IDs field, then submit form
        print("  -> Calling getGridIDs(false) to populate form IDs...")
        await page.evaluate("() => { getGridIDs(false); }")
        await page.wait_for_timeout(3000)

        # Check IDs are now populated
        ids_info = await page.evaluate("""
            () => {
                const form = document.getElementById('excelPost');
                if (!form) return 'no form';
                const ids = form.querySelector('input[name="IDs"]');
                if (!ids) return 'no IDs input';
                return 'IDs length: ' + ids.value.length + ' | first 100: ' + ids.value.substring(0,100);
            }
        """)
        print(f"  -> IDs after getGridIDs: {ids_info}")

        # Submit the form directly
        print("  -> Submitting excelPost form...")
        async with page.expect_download(timeout=60000) as dl:
            await page.evaluate("""
                () => {
                    const form = document.getElementById('excelPost');
                    form.submit();
                }
            """)
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
