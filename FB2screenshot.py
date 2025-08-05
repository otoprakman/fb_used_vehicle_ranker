from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

import os
import time
import csv
import random
import re
from datetime import datetime
from typing import Optional
import argparse
from pathlib import Path
from os import getenv
try:
    from dotenv import load_dotenv
    load_dotenv("creds.env")  # loads .env in the same folder
except Exception:
    pass  # script still works if python-dotenv isn't installed


def _parse_args():
    p = argparse.ArgumentParser(description="Facebook Marketplace screenshots")
    p.add_argument("--search", default=None, help="Marketplace search query")
    p.add_argument("--city", default=None, help="City/location filter (if supported on your UI)")
    p.add_argument("--price-min", type=int, dest="price_min", default=None)
    p.add_argument("--price-max", type=int, dest="price_max", default=None)
    p.add_argument("--scrolls", type=int, default=None, help="Number of times to scroll results list")
    p.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    return p.parse_args()

args = _parse_args()

# --- Config ---

EMAIL = getenv("FB_EMAIL")
PASSWORD = getenv("FB_PASSWORD")
if not EMAIL or not PASSWORD:
    raise SystemExit("EMAIL OR PASS are missing. Add it to .env or your environment.")

SEARCH_TERM = args.search if args.search else " "
NUM_SCROLLS = args.scrolls if args.scrolls else 2
OUT_DIR = "screenshots"
FINAL_OUT_DIR = "Output"
LINKS_CSV = os.path.join(OUT_DIR, "links.csv")
FORCE_RETAKE = False        # overwrite screenshots if True
OPEN_IN_NEW_TAB = False     # keep results page intact if True

# --- Setup ---
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(FINAL_OUT_DIR, exist_ok=True)

# Open CSV in APPEND mode, write header only if file absent
csv_exists = os.path.exists(LINKS_CSV)
links_file = open(LINKS_CSV, mode="a", newline='', encoding='utf-8')
csv_writer = csv.writer(links_file)
if not csv_exists:
    csv_writer.writerow(["run_ts", "index_hint", "item_id", "url", "screenshot_file"])


# Build a set of already processed item_ids from existing CSV (dedupe across runs)
processed_ids = set()
if csv_exists:
    try:
        with open(LINKS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                iid = (row.get("item_id") or "").strip()
                if iid:
                    processed_ids.add(iid)
    except Exception:
        pass


def extract_item_id(href: str) -> Optional[str]:
    """Extract Marketplace item ID from URL."""
    m = re.search(r"/marketplace/item/(\d+)", href)
    return m.group(1) if m else None


def clean_url(url: str) -> str:
    return url.split("?")[0].split("&")[0]


def is_vehicle_page(src_lower: str) -> bool:
    VEHICLE_CUES = [
        "about this vehicle", "driven", "miles",
        "automatic transmission", "manual transmission",
        "fuel type", "mpg",
        "clean title", "title"
    ]
    return any(k in src_lower for k in VEHICLE_CUES)

def matches_brand(src_lower: str, brand: str) -> bool:
    # Basic brand gate; you can enhance (e.g., also allow model names)
    return brand.lower() in src_lower


options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_argument("--disable-notifications")
# Note: typically pass the *profile root* (e.g., ...\User Data), not the "Default" folder.
# options.add_argument(r"--user-data-dir=C:\Users\otopr\AppData\Local\Google\Chrome\User Data")
# options.add_argument("--profile-directory=Default")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
wait = WebDriverWait(driver, 10)

# --- Helper ---
def human_typing(element, text, delay=0.1):
    for char in text:
        element.send_keys(char)
        time.sleep(delay + random.uniform(0, 0.05))

time.sleep(random.uniform(1, 2))
# --- Login ---
driver.get("https://www.facebook.com/login")
wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

try:
    email_field = driver.find_element(By.ID, "email")
    pass_field = driver.find_element(By.ID, "pass")
    human_typing(email_field, EMAIL, delay=random.uniform(0.06, 0.12))
    human_typing(pass_field, PASSWORD, delay=random.uniform(0.06, 0.12))
    time.sleep(random.uniform(0.8, 1.8))
    login_button = driver.find_element(By.NAME, "login")
    ActionChains(driver).move_to_element(login_button).pause(1).click().perform()
except Exception:
    # If already logged in via profile, this block may fail silently — that's fine.
    pass
time.sleep(random.uniform(5, 8))
# --- Go to Vehicles and Search ---
driver.get("https://www.facebook.com/marketplace/category/vehicles/")
time.sleep(random.randint(8, 12))

try:
    # Use a broader locator to handle placeholder variations
    search_input = driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Search Marketplace')]")
    search_input.click()
    time.sleep(random.randint(1, 3))
    query = args.search if args.search else " "  # if no search provided, keep your current default or blank
    human_typing(search_input, SEARCH_TERM, delay=random.uniform(0.05, 0.15))
    search_input.send_keys(Keys.RETURN)
    print(f"[OKAY] Searched for '{SEARCH_TERM}'")
    time.sleep(random.randint(5, 8))
except Exception as e:
    print("[ERROR] Search bar error:", e)


# ============================
# 1) SNAPSHOT ALL LINKS FIRST
# ============================
all_hrefs = []
seen_hrefs_snapshot = set()

for s in range(NUM_SCROLLS):
    print(f"\n Snapshot scroll {s+1}/{NUM_SCROLLS}")
    cards = driver.find_elements(By.XPATH, "//a[contains(@href, '/marketplace/item/')]")
    added = 0
    for c in cards:
        href_raw = c.get_attribute("href") or ""
        if not href_raw:
            continue
        href = clean_url(href_raw)
        if href and href not in seen_hrefs_snapshot:
            seen_hrefs_snapshot.add(href)
            all_hrefs.append(href)
            added += 1
    print(f" Added {added} new links this scroll (total unique so far: {len(all_hrefs)})")
    # Load more results
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(random.randint(5, 10))

print(f"\ Collected {len(all_hrefs)} unique item links across {NUM_SCROLLS} scrolls.")

# ============================
# 2) VISIT LINKS FROM SNAPSHOT
# ============================
run_ts = datetime.now().isoformat(timespec="seconds")

def open_in_new_tab_and_focus(href: str):
    # open detail in new tab and switch
    driver.execute_script("window.open(arguments[0], '_blank');", href)
    driver.switch_to.window(driver.window_handles[-1])


def close_tab_and_back_to_results():
    driver.close()
    driver.switch_to.window(driver.window_handles[0])


processed_this_run = 0
skipped_this_run = 0

for i, href in enumerate(all_hrefs, start=1):
    try:
        item_id = extract_item_id(href) or f"noid_{hash(href) & 0xffffffff}"
        # De-dupe across runs
        if item_id in processed_ids:
            skipped_this_run += 1
            continue
        print(f"\ [{i}/{len(all_hrefs)}] Opening [{item_id}] {href}")
        if OPEN_IN_NEW_TAB:
            open_in_new_tab_and_focus(href)
        else:
            driver.get(href)
        time.sleep(random.randint(6, 11))
        # Validate content (guard against boats/houses/sponsored)
        page_lower = driver.page_source.lower()
        if not is_vehicle_page(page_lower):
            print("  Non-vehicle page. Skipping.")
            if OPEN_IN_NEW_TAB: close_tab_and_back_to_results()
            continue
        if not matches_brand(page_lower, SEARCH_TERM):
            print(f"  Brand mismatch; expected '{SEARCH_TERM}'. Skipping.")
            if OPEN_IN_NEW_TAB: close_tab_and_back_to_results()
            continue
        # Expand description if present (optional)
        try:
            see_more_button = driver.find_element(By.XPATH, "//span[text()='See more' or text()='See More']")
            time.sleep(random.uniform(0.5, 1.5))
            driver.execute_script("arguments[0].click();", see_more_button)
            time.sleep(1.2)
        except Exception:
            pass
        # Save screenshot (idempotent)
        shot_name = f"listing_{item_id}.png"
        shot_path = os.path.join(OUT_DIR, shot_name)
        if os.path.exists(shot_path) and not FORCE_RETAKE:
            print(f" Exists, not overwriting: {shot_name}")
        else:
            driver.save_screenshot(shot_path)
            print(f" Screenshot saved: {shot_name}")
        # Append to CSV
        index_hint = f"snapshot_{i}"
        csv_writer.writerow([run_ts, index_hint, item_id, href, shot_name])
        links_file.flush()
        processed_ids.add(item_id)
        processed_this_run += 1
        if OPEN_IN_NEW_TAB:
            close_tab_and_back_to_results()
        # Small random delay between items
        time.sleep(random.uniform(0.8, 1.8))
    except Exception as e:
        print(f" Error on link {i}: {e}")
        try:
            if OPEN_IN_NEW_TAB and len(driver.window_handles) > 1:
                close_tab_and_back_to_results()
        except Exception:
            pass
        continue

# --- Cleanup ---
links_file.close()
driver.quit()
print(f"\ Done. Added {processed_this_run} items (skipped {skipped_this_run} previously processed).")

#########################
#########################
#########################

