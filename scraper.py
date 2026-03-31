"""
Safeguard Properties - Daily Report Automation
Version 9 - Wait for new report to appear in list before downloading
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
        print("  -> Checking current report count before requesting...")
        await page.goto(LISTING_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)
        
        initial_links = page.locator("table a")
        initial_count = await initial_links.count()
        print(f"  -> Reports in list before request: {initial_count}")

        # ── STEP 4: Request new report ─────────────────────────────
        print("  -> Requesting New Invoice Summary 30 Days...")
        await page.goto(REPORTS_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(NAV_WAIT)
        await page.get_by_text("New Invoice Summary 30 Days", exact=True).first.click()
        await page.wait_for_timeout(5000)
        print("  OK Report requested!")

        # ── STEP 5: Wait for new report to appear ──────────────────
        print("  -> Waiting for new report to appear in Report List...")
        max_wait = 30  # max 30 attempts x 15 seconds = 7.5 minutes
        new_count = initial_count
        
        for attempt in range(max_wait):
            await page.goto(LISTING_URL, wait_until="load", timeout=PAGE_TIMEOUT)
            await page.wait_for_timeout(5000)
            new_count = await page.locator("table a").count()
            print(f"  -> Attempt {attempt+1}: {new_count} reports in list (waiting for {initial_count+1})")
            
            if new_count > initial_count:
                print(f"  OK New report appeared! ({new_count} reports now)")
                break
            
            if attempt < max_wait - 1:
                print(f"  -> Not ready yet, waiting 15 seconds...")
                await asyncio.sleep(15)
        
        if new_count <= initial_count:
            print("  WARNING: Report never appeared, trying to download most recent anyway...")

        # ── STEP 6: Download the newest report ─────────────────────
        print("  -> Clicking first (newest) report in list...")
        links = page.locator("table a")
        link_count = await links.count()
        print(f"  Found {link_count} links")
        
        first_href = await links.first.get_attribute("href")
        print(f"  -> Clicking: {first_href}")
        await links.first.click()
        await page.wait_for_timeout(NAV_WAIT)
        print(f"  -> Now on: {page.url}")

        csv_btn = page.locator("input[value='Download CSV']")
        print(f"  Found {await csv_btn.count()} Download CSV buttons")

        async with page.expect_download(timeout=60000) as dl:
            await csv_btn.first.click()
        download = await dl.value
        await download.save_as(COMPLETED_FILE)
        print(f"  OK Completed orders saved -> {COMPLETED_FILE}")

        # ── STEP 7: Open Orders ─────────────────────────────────────
        print("  -> Going to Inspections page...")
        await page.goto(INSP_URL, wait_until="load", timeout=PAGE_TIMEOUT)
        await page.wait_for_selector("#btnFilteredExcel", timeout=60000)
        print("  OK Inspections page fully loaded!")

        # Use JavaScript to directly set the inspector dropdown to All and trigger reload
        print("  -> Using JavaScript to find and change Inspector dropdown...")
        
        # Print all select elements and their options via JS for debugging
        select_info = await page.evaluate("""
            () => {
                const selects = document.querySelectorAll('select');
                return Array.from(selects).map((s, i) => ({
                    index: i,
                    id: s.id,
                    name: s.name,
                    value: s.value,
                    options: Array.from(s.options).map(o => o.text + '=' + o.value).slice(0, 5)
                }));
            }
        """)
        for s in select_info:
            print(f"  Select {s['index']}: id={s['id']} name={s['name']} value={s['value']} options={s['options'][:3]}")
        
        # Find inspector select by looking for one that has inspector-like options
        changed = await page.evaluate("""
            () => {
                const selects = document.querySelectorAll('select');
                for (let sel of selects) {
                    const opts = Array.from(sel.options).map(o => o.text.toUpperCase());
                    if (opts.some(o => o.includes('ASOFFICE') || o.includes('ALL') || o.includes('INSPECTOR'))) {
                        // Set to first option (All)
                        sel.selectedIndex = 0;
                        sel.dispatchEvent(new Event('change', { bubbles: true }));
                        return 'Changed: ' + sel.id + ' to ' + sel.options[0].text;
                    }
                }
                return 'Not found';
            }
        """)
        print(f"  -> JS result: {changed}")
        
        # Wait for page to reload after change
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await page.wait_for_timeout(8000)
        await page.wait_for_selector("#btnFilteredExcel", timeout=30000)
        print("  OK Page reloaded, ready to download")

        print("  -> Clicking Filtered List to Excel...")
        async with page.expect_download(timeout=60000) as dl:
            await page.locator("#btnFilteredExcel").click()
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
