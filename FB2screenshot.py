from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

import os
import time
import csv
import random
import re
from datetime import datetime
from typing import Optional
from pathlib import Path
from os import getenv
try:
    from dotenv import load_dotenv
    load_dotenv("creds.env", override=True)  # loads .env in the same folder
except Exception:
    pass  # script still works if python-dotenv isn't installed

# --- Config ---

EMAIL = getenv("FB_EMAIL")
PASSWORD = getenv("FB_PASSWORD")
if not EMAIL or not PASSWORD:
    raise SystemExit("EMAIL OR PASS are missing. Add it to .env or your environment.")

FB_SEARCH_TERM = getenv("FB_SEARCH_TERM")
NUM_SCROLLS = int(getenv("FB_SCROLLS", "2"))
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


def matches_search_term(src_lower: str, search_term: str) -> bool:
    # Basic search term filter; can be enhanced for more sophisticated matching
    return search_term.lower() in src_lower

# --- Helper ---
def human_typing(element, text, delay=0.1):
    for char in text:
        element.send_keys(char)
        time.sleep(delay + random.uniform(0, 0.05))
# -------------------- NEW: DETECT DEALER VS INDIVIDUAL --------------------- #


def seller_is_dealer(driver, wait, timeout=8, dealer_threshold=3) -> bool:
    """
    Opens the seller's Marketplace *profile* and counts active listings.
    Returns True  -> Dealer  (≥2 listings)
            False -> Individual
    """
    try:
        # Seller card container
        card = wait.until(
            EC.presence_of_element_located(
                (By.XPATH,
                 "//div[contains(translate(.,'SELLER INFORMATION','seller information'),"
                 "'seller information')]")
            )
        )
        # Profile <a>: starts with /marketplace/profile/  OR  full FB URL
        seller_link = card.find_element(
            By.XPATH,
            ".//a[starts-with(@href,'/marketplace/profile/') or "
            "starts-with(@href,'https://www.facebook.com/marketplace/profile/')]"
        )
    except TimeoutException:
        print("   [WARN] Seller profile link not found – assume Individual.")
        return False
    # --- Build absolute URL if needed -----------------------------------
    href = seller_link.get_attribute("href")
    if href.startswith("/"):
        href = "https://www.facebook.com" + href
    # --- Open in new tab -------------------------------------------------
    driver.execute_script("window.open(arguments[0], '_blank');", href)
    driver.switch_to.window(driver.window_handles[-1])
    # trigger lazy-load
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    try:
        # ① grab every product anchor in the whole page
        raw_links = WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located(
                (By.XPATH, "//a[contains(@href,'/marketplace/item/')]")
            )
        )
        # ② keep only those that have a seller-ref tag
        seller_hrefs = {
            a.get_attribute("href").split("?")[0]
            for a in raw_links
            if a.get_attribute("href") and
               ("?ref=marketplace_profile" in a.get_attribute("href") or
                "?ref=marketplace"         in a.get_attribute("href"))
        }
        print(f"   seller_hrefs = {len(seller_hrefs)}")   # <-- keeps printing
        print(seller_hrefs)
        is_dealer = len(seller_hrefs) >= dealer_threshold     # default 2
    except TimeoutException:
        is_dealer = False
    finally:
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
    return is_dealer


# --------------------------------------------------------------------------- #

def main(search=None, user_city=None, scrolls=None):
    """Main function to collect screenshots from Facebook Marketplace."""

    #TODO:user_city is not used for now for filtering as Facebook account has default location.

    global FB_SEARCH_TERM, NUM_SCROLLS
    
    # Update parameters if provided
    if search:
        FB_SEARCH_TERM = search
    if scrolls:
        NUM_SCROLLS = int(scrolls)

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    # Note: typically pass the *profile root* (e.g., ...\User Data), not the "Default" folder.
    # options.add_argument(r"--user-data-dir=C:\Users\YOURID\AppData\Local\Google\Chrome\User Data")
    # options.add_argument("--profile-directory=Default")

    headless = getenv("FB_HEADLESS", "").lower() in ("true", "1", "yes")
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 10)


    time.sleep(random.uniform(1, 2))
    # --- Login ---
    driver.get("https://www.facebook.com/login")
    time.sleep(random.uniform(3, 5))
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
    # --- Go to Marketplace and Search ---
    driver.get("https://www.facebook.com/marketplace/?ref=app_tab")
    time.sleep(random.randint(8, 12))

    try:
        # Use a broader locator to handle placeholder variations
        search_input = driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Search Marketplace')]")
        search_input.click()
        time.sleep(random.randint(1, 3))
        human_typing(search_input, FB_SEARCH_TERM, delay=random.uniform(0.05, 0.15))
        search_input.send_keys(Keys.RETURN)
        print(f"[OKAY] Searched for '{FB_SEARCH_TERM}'")
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

    print(f"[DONE] Collected {len(all_hrefs)} unique item links across {NUM_SCROLLS} scrolls.")

    # ============================
    # FAST MODE: SCREENSHOT GRID CARDS WITHOUT VISITING LINKS
    # ============================
    run_ts = datetime.now().isoformat(timespec="seconds")

    fast_mode = getenv("FB_FAST_MODE", "").lower() in ("true", "1", "yes")
    if fast_mode:
        print("[FAST-MODE] Taking screenshots of grid cards without visiting each listing…")
        processed_this_run = 0
        skipped_this_run = 0

        # Build mapping from cleaned href to element for current DOM
        card_anchors = driver.find_elements(By.XPATH, "//a[contains(@href, '/marketplace/item/')]")
        href_to_el = {}
        for el in card_anchors:
            try:
                href_raw = el.get_attribute("href") or ""
                if not href_raw:
                    continue
                href_clean = clean_url(href_raw)
                if href_clean not in href_to_el:
                    href_to_el[href_clean] = el
            except Exception:
                continue

        # Start from top to maximize chance that earlier items are present
        try:
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
        except Exception:
            pass

        def find_card_element_by_id(item_id: str, max_swipes: int = 35):
            """Try to locate the anchor for an item_id by progressively scrolling down.
            Returns the WebElement or None if not found after full scan.
            """
            # quick try in current viewport
            try:
                return driver.find_element(By.XPATH, f"//a[contains(@href, '{item_id}')]")
            except Exception:
                pass
            # progressive scroll down
            for _ in range(max_swipes):
                try:
                    driver.execute_script("window.scrollBy(0, Math.max(600, window.innerHeight - 200));")
                except Exception:
                    pass
                time.sleep(random.uniform(0.35, 0.7))
                try:
                    el2 = driver.find_element(By.XPATH, f"//a[contains(@href, '{item_id}')]")
                    return el2
                except Exception:
                    continue
            return None

        for i, href in enumerate(all_hrefs, start=1):
            try:
                item_id = extract_item_id(href) or f"noid_{hash(href) & 0xffffffff}"
                # De-dupe across runs
                if item_id in processed_ids:
                    skipped_this_run += 1
                    continue

                el = href_to_el.get(href)
                if el is None:
                    # Try within viewport, then progressively scroll down to find it
                    el = find_card_element_by_id(item_id)
                    if el is None:
                        print(f"  [WARN] Could not locate card element for {href}; skipping.")
                        continue

                # Re-find right before screenshot in case the previous reference went stale
                try:
                    el = driver.find_element(By.XPATH, f"//a[contains(@href, '{item_id}')]")
                except Exception:
                    el = None
                if el is None:
                    el = find_card_element_by_id(item_id)
                    if el is None:
                        print(f"  [WARN] Could not relocate card element for {href}; skipping.")
                        continue

                # Scroll into view and screenshot
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                    time.sleep(random.uniform(0.4, 0.9))
                except Exception:
                    pass

                shot_name = f"Grid_listing_{item_id}.png"
                shot_path = os.path.join(OUT_DIR, shot_name)
                if os.path.exists(shot_path) and not FORCE_RETAKE:
                    print(f" Exists, not overwriting: {shot_name}")
                else:
                    try:
                        el.screenshot(shot_path)
                        print(f" Screenshot saved: {shot_name}")
                    except Exception as se:
                        print(f"  [WARN] Failed to capture element screenshot for {item_id}: {se}")
                        # As a fallback, page-level screenshot with a different suffix
                        try:
                            driver.save_screenshot(shot_path)
                            print(f"  [FALLBACK] Page screenshot saved: {shot_name}")
                        except Exception:
                            pass

                index_hint = f"grid_snapshot_{i}"
                csv_writer.writerow([run_ts, index_hint, item_id, href, shot_name])
                links_file.flush()
                processed_ids.add(item_id)
                processed_this_run += 1
                time.sleep(random.uniform(0.2, 0.6))
            except Exception as e:
                print(f" Error on grid card {i}: {e}")
                continue

        # Cleanup and exit fast mode path
        links_file.close()
        driver.quit()
        print(f"\ Done. [FAST-MODE] Added {processed_this_run} items (skipped {skipped_this_run} previously processed).")
        return

    # ============================
    # 2) VISIT LINKS FROM SNAPSHOT
    # ============================

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
            # Validate content (guard against sponsored/irrelevant pages if needed)
            page_lower = driver.page_source.lower()
<<<<<<< HEAD

            ##### Comment out below if the app will be just for vehicles
            # if not is_vehicle_page(page_lower):
            #     print("  Non-vehicle page. Skipping.")
            #     if OPEN_IN_NEW_TAB: close_tab_and_back_to_results()
            #     continue

            if not matches_brand(page_lower, FB_SEARCH_TERM):
                print(f"  Brand mismatch; expected '{FB_SEARCH_TERM}'. Skipping.")
=======
            # Removed vehicle-specific filtering; now processes all product types
            if not matches_search_term(page_lower, FB_SEARCH_TERM):
                print(f"  Search term mismatch; expected '{FB_SEARCH_TERM}'. Skipping.")
>>>>>>> d8a4affc218420008cba726138d672eefd90dcbc
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
            # -------- NEW: decide Dealer vs Individual -------------------------------
            dealer_flag = seller_is_dealer(driver, wait)
            prefix = "Dealer" if dealer_flag else "Individual"
            shot_name = f"{prefix}_listing_{item_id}.png"
            shot_path = os.path.join(OUT_DIR, shot_name)
            # Save screenshot (idempotent)
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


if __name__ == "__main__":
    main()