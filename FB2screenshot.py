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
import base64
import logging, sys
import signal


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("fb-marketplace")

try:
    from dotenv import load_dotenv
    load_dotenv("creds.env", override=True)  # loads .env in the same folder
except Exception:
    pass  # script still works if python-dotenv isn't installed

# --- Storage backend: DuckDB ---
try:
    import duckdb  # type: ignore
except Exception:
    raise SystemExit("DuckDB not installed. Install with: pip install duckdb")

# --- Config ---

EMAIL = getenv("FB_EMAIL")
PASSWORD = getenv("FB_PASSWORD")
if not EMAIL or not PASSWORD:
    raise SystemExit("EMAIL OR PASS are missing. Add it to .env or your environment.")

FB_SEARCH_TERM = getenv("FB_SEARCH_TERM")
NUM_SCROLLS = int(getenv("FB_SCROLLS", "2"))
OUT_DIR = "screenshots"
FINAL_OUT_DIR = "Output"
DB_PATH = os.path.join(OUT_DIR, "links.duckdb")
FORCE_RETAKE = False        # overwrite screenshots if True
OPEN_IN_NEW_TAB = False     # keep results page intact if True
seller_cache: dict[str, bool] = {}

# --- Setup ---
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(FINAL_OUT_DIR, exist_ok=True)

# Initialize DuckDB and ensure table exists
con = duckdb.connect(DB_PATH)
con.execute(
    """
CREATE TABLE IF NOT EXISTS links (
  run_ts TIMESTAMP,
  index_hint VARCHAR,
  item_id VARCHAR,
  url VARCHAR,
  screenshot_file VARCHAR
);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_item ON links(item_id);
    """
)

# Build a set of already processed item_ids from DB (dedupe across runs)
processed_ids = set()
try:
    rows = con.execute("SELECT item_id FROM links").fetchall()
    processed_ids = {str(r[0]) for r in rows if r and r[0] is not None}
except Exception:
    processed_ids = set()


def extract_item_id(href: str) -> Optional[str]:
    """Extract Marketplace item ID from URL."""
    m = re.search(r"/marketplace/item/(\d+)", href)
    return m.group(1) if m else None


def clean_url(url: str) -> str:
    return url.split("?")[0].split("&")[0]


def matches_search_term(src_lower: str, search_term: str) -> bool:
    # Basic search term filter; can be enhanced for more sophisticated matching
    return search_term.lower() in src_lower


# --- Brand/Vehicle Helpers ---
def _normalize_simple(s: str) -> str:
    """Lowercase and collapse non-alphanumerics to simplify matching."""
    s = s.lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def is_vehicle_page(page_lower: str) -> bool:
    """Heuristic detection for vehicle listings based on common signals."""
    if not page_lower:
        return False
    vehicle_terms = {
        "vehicle details",
        "odometer",
        "mileage",
        "vin",
        "transmission",
        "engine",
        "drivetrain",
        "fuel type",
        "mpg",
        "horsepower",
        "sedan",
        "suv",
        "hatchback",
        "coupe",
        "convertible",
        "pickup",
        "truck",
        "van",
        "minivan",
        "motorcycle",
        "bike",
        "atv",
        "dealer information",
    }
    hits = sum(1 for t in vehicle_terms if t in page_lower)
    return hits >= 2



def matches_brand_html(driver, term: str) -> bool:
    """
    Match brand and model tokens from the search term against the listing title text.
    Handles reordered words, hyphens, casing, and fallbacks.
    """
    if not term:
        return True

    # --- Get candidate title text from multiple likely nodes ---
    title_candidates = []

    # 1) <h1> title
    try:
        title_candidates.append(driver.find_element(By.TAG_NAME, "h1").text)
    except:
        pass

    # 2) FB sometimes puts title in spans with dir="auto"
    try:
        spans = driver.find_elements(By.XPATH, "//span[@dir='auto']")
        for s in spans:
            t = s.text.strip()
            if 3 < len(t) < 80:  # avoid junk UI fragments
                title_candidates.append(t)
    except:
        pass

    # 3) Fallback: browser document title
    title_candidates.append(driver.title)

    # Combined normalized text
    combined = " ".join(title_candidates).lower()
    combined = re.sub(r"[^a-z0-9]+", " ", combined).strip()

    # --- Tokenize search term ("Toyota Corolla" → ["toyota", "corolla"]) ---
    tokens = re.findall(r"[a-z0-9]+", term.lower())
    if not tokens:
        return True

    # Require all tokens to appear in any order
    for token in tokens:
        if token not in combined:
            return False

    return True



# --- Helper ---
def human_typing(element, text, delay=0.1):
    for char in text:
        element.send_keys(char)
        time.sleep(delay + random.uniform(0, 0.05))
# -------------------- NEW: DETECT DEALER VS INDIVIDUAL --------------------- #


# def seller_is_dealer(driver, wait, timeout=8, dealer_threshold=3) -> bool:
#     """
#     Opens the seller's Marketplace *profile* and counts active listings.
#     Returns True  -> Dealer  (≥2 listings)
#             False -> Individual
#     """
#     try:
#         # Seller card container
#         card = wait.until(
#             EC.presence_of_element_located(
#                 (By.XPATH,
#                  "//div[contains(translate(.,'SELLER INFORMATION','seller information'),"
#                  "'seller information')]")
#             )
#         )
#         # Profile <a>: starts with /marketplace/profile/  OR  full FB URL
#         seller_link = card.find_element(
#             By.XPATH,
#             ".//a[starts-with(@href,'/marketplace/profile/') or "
#             "starts-with(@href,'https://www.facebook.com/marketplace/profile/')]"
#         )
#     except TimeoutException:
#         print("   [WARN] Seller profile link not found assume Individual.")
#         return False
#     # --- Build absolute URL if needed -----------------------------------
#     href = seller_link.get_attribute("href")
#     if href.startswith("/"):
#         href = "https://www.facebook.com" + href
#     # --- Open in new tab -------------------------------------------------
#     driver.execute_script("window.open(arguments[0], '_blank');", href)
#     driver.switch_to.window(driver.window_handles[-1])
#     # trigger lazy-load
#     driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
#     try:
#         # ① grab every product anchor in the whole page
#         raw_links = WebDriverWait(driver, timeout).until(
#             EC.presence_of_all_elements_located(
#                 (By.XPATH, "//a[contains(@href,'/marketplace/item/')]")
#             )
#         )
#         # ② keep only those that have a seller-ref tag
#         seller_hrefs = {
#             a.get_attribute("href").split("?")[0]
#             for a in raw_links
#             if a.get_attribute("href") and
#                ("?ref=marketplace_profile" in a.get_attribute("href") or
#                 "?ref=marketplace"         in a.get_attribute("href"))
#         }
#         print(f"   seller_hrefs = {len(seller_hrefs)}")   # <-- keeps printing
#         print(seller_hrefs)
#         is_dealer = len(seller_hrefs) >= dealer_threshold     # default 2
#     except TimeoutException:
#         is_dealer = False
#     finally:
#         driver.close()
#         driver.switch_to.window(driver.window_handles[0])
#     return is_dealer

def extract_seller_profile_url(driver, wait, timeout=8) -> Optional[str]:
    try:
        card = wait.until(
            EC.presence_of_element_located(
                (By.XPATH,
                 "//div[contains(translate(.,'SELLER INFORMATION','seller information'),'seller information')]")
            )
        )
        a = card.find_element(
            By.XPATH,
            ".//a[starts-with(@href,'/marketplace/profile/') or "
            "starts-with(@href,'https://www.facebook.com/marketplace/profile/')]"
        )
        href = a.get_attribute("href") or ""
        if href.startswith("/"):
            href = "https://www.facebook.com" + href
        return href
    except TimeoutException:
        return None

def seller_is_dealer_cached(driver, wait, cache: dict, timeout=8,
                            dealer_threshold: int = 3,
                            search_brand_hint: str = "") -> bool:
    url = extract_seller_profile_url(driver, wait, timeout=timeout)
    if not url:
        log.info("   [SELLER] Profile link not found → assume Individual.")
        return False
    if url in cache:
        return cache[url]

    driver.execute_script("window.open(arguments[0], '_blank');", url)
    driver.switch_to.window(driver.window_handles[-1])
    try:
        # small nudge to start loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(0.4, 0.9))

        veh_count, _ = count_vehicle_cards_on_seller_page(
            driver,
            max_scroll_rounds=10,
            pause=(0.5, 1.0),
            search_brand_hint=search_brand_hint
        )
        is_dealer = veh_count >= dealer_threshold
        cache[url] = is_dealer
        log.info(f"   [SELLER] {url} → vehicle_cards={veh_count} → Dealer={is_dealer}")
        return is_dealer
    finally:
        try:
            driver.close()
        finally:
            driver.switch_to.window(driver.window_handles[0])



# --- Vehicle heuristics (no per-item navigation needed) ---
VEHICLE_BRANDS = {
    # tune/trim as needed for your focus brands
    "acura","alfa","audi","bmw","buick","cadillac","chevrolet","chevy","chrysler",
    "dodge","fiat","ford","gmc","honda","hyundai","infiniti","jaguar","jeep","kia",
    "land rover","lexus","lincoln","mazda","mercedes","mercedes-benz","mini","mitsubishi",
    "nissan","porsche","ram","subaru","tesla","toyota","volkswagen","vw","volvo",
    "rivian","lucid"
}
VEHICLE_HINTS = {
    "awd","4wd","fwd","rwd","mpg","vin","odometer","mileage","mi.","miles","sedan","suv",
    "hatchback","coupe","convertible","pickup","truck","van","minivan","transmission",
    "drivetrain","engine","fuel","horsepower","hp","towing","trim","lx","le","se","xle","lt","ls","xlt","lariat"
}
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")  # rough vehicle model year signal
MILEAGE_RE = re.compile(r"\b\d{1,3}(?:,\d{3})?\s*(?:mi|miles)\b", re.I)

def _text_chunks_for_card(driver, el):
    """
    Extracts useful text from a seller-profile grid card anchor without opening it.
    Tries aria-label, innerText on the anchor and a couple of ancestors/children.
    """
    txts = []
    try:
        aria = el.get_attribute("aria-label") or ""
        if aria: txts.append(aria)
    except Exception:
        pass

    # Use JS to get innerText safely (avoids StaleElementReference a bit)
    for node_expr in [
        "arguments[0].innerText",
        "arguments[0].parentElement && arguments[0].parentElement.innerText",
        "arguments[0].closest('div') && arguments[0].closest('div').innerText",
    ]:
        try:
            v = driver.execute_script(f"return {node_expr};", el) or ""
            if v: txts.append(v)
        except Exception:
            pass

    # Dedup & normalize
    joined = " \n ".join(dict.fromkeys([t.strip() for t in txts if t]))
    return joined.lower()
    
def _looks_like_vehicle(text: str, search_brand_hint: str = "") -> bool:
    """
    Cheap classification: vehicle if (year + brand) OR (mileage hint) OR (>=2 vehicle hints).
    Optionally boost with the first token from your search term (brand).
    """
    if not text:
        return False

    has_year = bool(YEAR_RE.search(text))
    has_mileage = bool(MILEAGE_RE.search(text))

    # brand presence (either from known list or the user's search brand)
    tokens = set(re.findall(r"[a-z0-9]+", text))
    brand_in_text = any(b in tokens or (" " + b + " ") in " " + text + " " for b in VEHICLE_BRANDS)

    brand_hint = ""
    if search_brand_hint:
        hint_tokens = re.findall(r"[a-z0-9]+", search_brand_hint.lower())
        if hint_tokens:
            brand_hint = hint_tokens[0]
    brand_boost = bool(brand_hint and brand_hint in text)

    # vehicle keywords
    hint_hits = sum(1 for h in VEHICLE_HINTS if h in text)

    # rules (tune thresholds as you see results)
    if (has_year and (brand_in_text or brand_boost)):
        return True
    if has_mileage and (brand_in_text or hint_hits >= 1):
        return True
    if hint_hits >= 2 and (brand_in_text or has_year):
        return True

    return False


def count_vehicle_cards_on_seller_page(driver, max_scroll_rounds: int = 10, pause: tuple[float,float] = (0.6, 1.1),
                                       search_brand_hint: str = "") -> tuple[int, set[str]]:
    """
    On an open seller-profile tab, scroll to lazy-load, gather grid item anchors,
    classify each card as vehicle/non-vehicle by text heuristics, and return
    (vehicle_count, item_ids_set). No per-item navigation.
    """
    seen_ids: set[str] = set()
    vehicle_count = 0

    def _anchors():
        return driver.find_elements(By.XPATH, "//a[contains(@href,'/marketplace/item/')]")

    # Progressive scroll
    last_total = 0
    for _ in range(max_scroll_rounds):
        anchors = _anchors()
        # attempt to load more
        driver.execute_script("window.scrollBy(0, Math.max(800, window.innerHeight - 100));")
        time.sleep(random.uniform(*pause))

        # If nothing new shows up, try hitting bottom once
        if len(anchors) == last_total:
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(*pause))
            except Exception:
                pass
        else:
            last_total = len(anchors)

    # Final harvest after scrolling
    anchors = _anchors()

    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
            if not href:
                continue
            clean = clean_url(href)
            iid = extract_item_id(clean) or f"noid_{hash(clean)&0xffffffff}"
            if iid in seen_ids:
                continue

            text = _text_chunks_for_card(driver, a)
            if _looks_like_vehicle(text, search_brand_hint=search_brand_hint):
                vehicle_count += 1

            seen_ids.add(iid)
        except Exception:
            # be tolerant—skip bad cards
            continue

    return vehicle_count, seen_ids



def fullpage_png(driver, path: Path, device_scale_factor: int = 2) -> bool:
    """
    Capture a crisp, full-page PNG using Chrome DevTools. Returns True if success.
    Works best in headless mode; falls back to normal screenshot() otherwise.
    """
    try:
        # Get content size
        metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
        cs = metrics.get("contentSize") or metrics.get("cssContentSize") or {}
        width = int(cs.get("width", 1200))
        height = int(cs.get("height", 2000))

        # Set device metrics for crispness
        driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "mobile": False,
            "width": width,
            "height": height,
            "deviceScaleFactor": device_scale_factor
        })

        # Capture screenshot
        data = driver.execute_cdp_cmd("Page.captureScreenshot", {"fromSurface": True})
        png = base64.b64decode(data["data"])
        Path(path).write_bytes(png)
        return True
    except Exception as e:
        log.warning(f"[CDP] Full-page capture failed, fallback to element/page screenshot. {e}")
        return False

def on_login_challenge(driver) -> bool:
    body = driver.page_source.lower()
    # broad, language-agnostic-ish signals
    needles = [
        "enter login code", "two-factor", "approve your login",
        # "checkpoint", 
        "identity confirmation"
    ]
    return any(n in body for n in needles)

def on_login_failed(driver) -> bool:
    # still on login page with an error banner or same URL
    try:
        err = driver.find_elements(By.XPATH, "//*[contains(@id,'error') or contains(@class,'_9ay7') or contains(., 'incorrect')]")
        if err:
            return True
    except Exception:
        pass
    return "facebook.com/login" in (driver.current_url.lower())



# --- Robust Marketplace search box locator + search ---
def find_marketplace_search(driver, wait, timeout=12):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    # 1) Placeholder variant: "What do you want to buy?" (case-insensitive, language-agnostic-ish)
    # Use XPath translate() to lowercase and contains 'want to buy'
    try:
        return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((
            By.XPATH,
            "//input[@placeholder and contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'want to buy')]"
        )))
    except TimeoutException:
        pass

    # 2) role=search container
    try:
        return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((
            By.XPATH, "//div[@role='search']//input"
        )))
    except TimeoutException:
        pass

    # 3) Generic but strong: type=search with aria-label
    try:
        return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((
            By.CSS_SELECTOR, "div[role='search'] input[aria-label], input[aria-label][type='search']"
        )))
    except TimeoutException:
        pass

    # 4) Fallback: any visible text input within the sticky top bar
    try:
        return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((
            By.XPATH,
            "(//div[contains(@style,'position: sticky') or contains(@class,'sticky')]" 
            "//input[not(@type) or @type='text' or @type='search'])[1]"
        )))
    except TimeoutException:
        raise TimeoutException("Marketplace search input not found in current UI variant.")
    


def seller_is_dealer_via_modal(
    driver,
    wait,
    timeout: int = 8,
    dealer_threshold: int = 3,
    search_brand_hint: str = "",
) -> bool:
    """
    Open the 'Seller details' modal (like in your screenshot) and count ACTIVE vehicle
    listings inside the modal only. No navigation to profile tabs, no per-item visits.
    Returns True if vehicle_active >= dealer_threshold.
    """

    # ---------------- small helpers ----------------
    VEHICLE_BRANDS = {
        "acura","alfa","audi","bmw","buick","cadillac","chevrolet","chevy","chrysler",
        "dodge","fiat","ford","gmc","honda","hyundai","infiniti","jaguar","jeep","kia",
        "land rover","lexus","lincoln","mazda","mercedes","mercedes-benz","mini",
        "mitsubishi","nissan","porsche","ram","subaru","tesla","toyota","volkswagen","vw","volvo",
        "rivian","lucid",
    }
    VEHICLE_HINTS = {
        "awd","4wd","fwd","rwd","mpg","vin","odometer","mileage","mi.","miles","sedan","suv",
        "hatchback","coupe","convertible","pickup","truck","van","minivan","transmission",
        "drivetrain","engine","fuel","horsepower","hp","towing","trim","lx","le","se","xle","lt","ls","xlt","lariat"
    }
    YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
    MILEAGE_RE = re.compile(r"\b\d{1,3}(?:,\d{3})?\s*(?:mi|miles)\b", re.I)

    def _norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

    def _text_for_card(el) -> str:
        txts = []
        try:
            aria = el.get_attribute("aria-label") or ""
            if aria: txts.append(aria)
        except Exception:
            pass
        for expr in [
            "arguments[0].innerText",
            "arguments[0].parentElement && arguments[0].parentElement.innerText",
            "arguments[0].closest('div') && arguments[0].closest('div').innerText",
        ]:
            try:
                v = driver.execute_script(f"return {expr};", el) or ""
                if v: txts.append(v)
            except Exception:
                pass
        return _norm(" \n ".join(dict.fromkeys([t.strip() for t in txts if t])))

    def _looks_like_vehicle(text: str, brand_hint: str = "") -> bool:
        if not text:
            return False
        has_year = bool(YEAR_RE.search(text))
        has_mileage = bool(MILEAGE_RE.search(text))
        brand_in_text = any(b in text for b in VEHICLE_BRANDS)
        brand_boost = False
        if brand_hint:
            btoks = re.findall(r"[a-z0-9]+", brand_hint.lower())
            if btoks:
                brand_boost = btoks[0] in text
        hint_hits = sum(1 for h in VEHICLE_HINTS if h in text)
        if (has_year and (brand_in_text or brand_boost)):
            return True
        if has_mileage and (brand_in_text or hint_hits >= 1):
            return True
        if hint_hits >= 2 and (brand_in_text or has_year):
            return True
        return False

    def _extract_item_id(href: str):
        m = re.search(r"/marketplace/item/(\d+)", href or "")
        return m.group(1) if m else None

    # ---------------- open (or target) the modal ----------------
    # If modal is not open yet, click "Seller details" on the right rail.
    try:
        # many UIs render it as a link or button with 'Seller details'
        details_btn = driver.find_element(
            By.XPATH,
            "//a[.//span[normalize-space()='Seller details']] | "
            "//div[@role='button'][.//span[normalize-space()='Seller details']] | "
            "//span[normalize-space()='Seller details']/ancestor::a"
        )
        try:
            details_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", details_btn)
        time.sleep(random.uniform(0.3, 0.7))
    except Exception:
        # maybe the modal is already open; we’ll just look for it
        pass

    # Wait for the modal with the 'Search listings' box (as in your screenshot)
    dialog = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((
            By.XPATH,
            "//div[@role='dialog' and .//input[@placeholder and contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'search listings')]]"
        ))
    )

    # Find the scrollable container inside the dialog (we need to scroll THIS, not the window)
    try:
        scroller = dialog.find_element(
            By.XPATH,
            ".//div[contains(@style,'overflow') and (contains(@style,'auto') or contains(@style,'scroll'))]"
        )
    except Exception:
        # fallback to the first big div inside dialog
        scroller = dialog

    # ---------------- lazy-load and harvest anchors inside the modal ----------------
    def _anchors_in_modal():
        return dialog.find_elements(By.XPATH, ".//a[contains(@href,'/marketplace/item/')]")

    # progressive scroll inside the modal
    last_total = 0
    for _ in range(8):
        anchors = _anchors_in_modal()
        if len(anchors) <= last_total:
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroller)
            time.sleep(random.uniform(0.35, 0.7))
            anchors = _anchors_in_modal()
            if len(anchors) <= last_total:
                break
        last_total = len(anchors)
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + Math.max(800, window.innerHeight-120);", scroller)
        time.sleep(random.uniform(0.35, 0.7))

    anchors = _anchors_in_modal()

    # ---------------- count ACTIVE vehicle listings only ----------------
    seen_ids, vehicle_active = set(), 0
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
            if not href:
                continue
            iid = _extract_item_id(href) or f"noid_{hash(href)&0xffffffff}"
            if iid in seen_ids:
                continue
            seen_ids.add(iid)

            t = _text_for_card(a)

            # Exclude inactive states visible on card
            if any(w in t for w in (" sold ", " sold·", "sold ·", "unavailable", "pending", "sold out")):
                continue

            if _looks_like_vehicle(t, brand_hint=search_brand_hint):
                vehicle_active += 1

        except StaleElementReferenceException:
            continue
        except Exception:
            continue

    # ---------------- close modal & return ----------------
    try:
        # click ✕ or send Esc
        close_btn = dialog.find_element(By.XPATH, ".//div[@aria-label='Close' or @role='button'][.//*[(name()='svg') or @aria-label='Close']]")
        try:
            close_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", close_btn)
    except Exception:
        # fallback: ESC
        try:
            dialog.send_keys(Keys.ESCAPE)
        except Exception:
            pass

    return vehicle_active >= dealer_threshold


def print_full_listing_text(driver):
    """
    Prints *all visible text* from the current listing page with no parsing applied.
    """
    full_text = driver.execute_script("return document.body.innerText;")
    print("\n================= FULL LISTING TEXT =================\n")
    print(full_text)
    print("\n=====================================================\n")
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
    if on_login_challenge(driver):
        log.error("2FA / login challenge detected. Use a persistent profile (user-data-dir) or complete 2FA once and re-run.")
        driver.quit()
        try: con.close()
        except: pass
        return

    if on_login_failed(driver):
        log.error("Login appears to have failed. Check FB_EMAIL/FB_PASSWORD or use user-data-dir for a logged-in profile.")
        driver.quit()
        try: con.close()
        except: pass
        return

    # --- Go to Marketplace and Search ---
    driver.get("https://www.facebook.com/marketplace/?ref=app_tab")
    time.sleep(random.randint(8, 12))

    try:
        log.info("Locating Marketplace search bar...")
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        driver.execute_script("window.scrollBy(0, 120);")  # nudge to mount SPA widgets
        time.sleep(random.uniform(0.6, 1.2))

        search_input = find_marketplace_search(driver, wait, timeout=12)
        # Sometimes a placeholder overlay intercepts the first click—do a JS click as fallback
        try:
            search_input.click()
        except Exception:
            driver.execute_script("arguments[0].click();", search_input)

        time.sleep(random.uniform(0.3, 0.8))
        # Clear any stale text safely
        try:
            search_input.clear()
        except Exception:
            driver.execute_script("arguments[0].value='';", search_input)

        human_typing(search_input, FB_SEARCH_TERM, delay=random.uniform(0.05, 0.12))
        time.sleep(random.uniform(0.3, 0.9))
        search_input.send_keys(Keys.RETURN)

        log.info(f"[OK] Searched for: {FB_SEARCH_TERM}")
        time.sleep(random.uniform(3.5, 6.5))

    except Exception as e:
        log.error("Search bar interaction failed", exc_info=True)


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
                            # if not fullpage_png(driver, Path(shot_path)):
                            driver.save_screenshot(shot_path)
                            print(f"  [FALLBACK] Page screenshot saved: {shot_name}")
                        except Exception:
                            pass

                index_hint = f"grid_snapshot_{i}"
                try:
                    con.execute("""
                                    INSERT INTO links (run_ts, index_hint, item_id, url, screenshot_file)
                                    VALUES (?, ?, ?, ?, ?)
                                    ON CONFLICT (item_id) DO NOTHING
                                    """, [run_ts, index_hint, item_id, href, shot_name]
                                    )
                except Exception:
                    pass
                processed_ids.add(item_id)
                processed_this_run += 1
                time.sleep(random.uniform(0.2, 0.6))
            except Exception as e:
                print(f" Error on grid card {i}: {e}")
                continue

        # Cleanup and exit fast mode path
        try:
            con.close()
        except Exception:
            pass
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
            print_full_listing_text(driver)
            # Validate content (guard against sponsored/irrelevant pages if needed)
            page_lower = driver.page_source.lower()

            ##### Comment out below if the app will be just for vehicles
            # if not is_vehicle_page(page_lower):
            #     print("  Non-vehicle page. Skipping.")
            #     if OPEN_IN_NEW_TAB: close_tab_and_back_to_results()
            #     continue

            if not matches_brand_html(driver, FB_SEARCH_TERM):
                log.info(f"  Brand mismatch; expected '{FB_SEARCH_TERM}' in title. Skipping.")
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
            dealer_flag = seller_is_dealer_via_modal(driver, wait, dealer_threshold=3, search_brand_hint=FB_SEARCH_TERM)
            prefix = "Dealer" if dealer_flag else "Individual"
            shot_name = f"{prefix}_listing_{item_id}.png"
            shot_path = os.path.join(OUT_DIR, shot_name)
            # Save screenshot (idempotent)
            if os.path.exists(shot_path) and not FORCE_RETAKE:
                print(f" Exists, not overwriting: {shot_name}")
            else:
                # if not fullpage_png(driver, Path(shot_path)):
                driver.save_screenshot(shot_path)
                print(f" Screenshot saved: {shot_name}")
            # Persist to DuckDB
            index_hint = f"snapshot_{i}"
            try:
                con.execute(
                    "INSERT INTO links (run_ts, index_hint, item_id, url, screenshot_file) VALUES (?, ?, ?, ?, ?)",
                    [run_ts, index_hint, item_id, href, shot_name],
                )
            except Exception:
                pass
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
    try:
        con.close()
    except Exception:
        pass
    driver.quit()
    print(f"\ Done. Added {processed_this_run} items (skipped {skipped_this_run} previously processed).")


if __name__ == "__main__":
    main()
