
import logging
import time
from typing import List, Dict

from .tools.browser import BrowserTool
from .tools.extractor import ExtractorTool
from .tools.kbb import KBBTool
from .database import MarketplaceDB
import os

# Configure logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("agent")

class MarketplaceAgent:
    def __init__(self, headless: bool = False, use_profile: bool = True, use_local_llm: bool = True):
        self.browser = BrowserTool(headless=headless, use_profile=use_profile)
        self.extractor = ExtractorTool(use_local=use_local_llm)
        self.kbb = KBBTool()
        self.db = MarketplaceDB()

    def run_search(self, search_term: str, scrolls: int = 2):
        """
        Main workflow:
        1. Login
        2. Search
        3. Scroll & Scrape
        4. Extract & Structure
        5. KBB Estimate
        6. Save to DB
        """
        try:
            log.info(f"Starting search agent for: '{search_term}'")
            self.browser.start()
            
            # 1. Login
            if not self.browser.login_facebook():
                log.error("Failed to login. Aborting.")
                return

            # 2. Search
            self.browser.navigate_to_marketplace_search(search_term)
            
            # 3. Scroll
            self.browser.scroll_down(times=scrolls)
            
            # 4. Extract HTML
            html = self.browser.get_page_source()
            
            # 5. Parse Listings
            log.info("Extracting listings via LLM...")
            listings = self.extractor.extract_listings_from_html(html)
            log.info(f"Parametric extraction found {len(listings)} items.")

            # 6. Process & Save
            for item in listings:
                self._process_item(item)
                
            log.info("Search run complete.")
            
        except Exception as e:
            log.error(f"Search run failed: {e}", exc_info=True)
        finally:
            self.browser.quit()

    def _process_item(self, item: Dict):
        """Enrich item with KBB price and save to DB."""
        item_id = item.get("item_id")
        title = item.get("title")
        
        # Check against DB to see if we already have a KBB price (to save calls)
        existing = self.db.con.execute("SELECT kbb_price FROM listings WHERE item_id = ?", [item_id]).fetchone()
        
        kbb_price = None
        if existing and existing[0]:
            kbb_price = existing[0]
        else:
            # Need to fetch KBB?
            # Only if we have enough info
            if item.get("brand") and item.get("model") and item.get("year"):
                 # Note: The extractor assumes Year is in title or passed. 
                 # If extractor didn't split year explicitly, we might need to regex title
                 pass
            
            # Simple fallback: try to parse year from title if not present
            year = item.get("year")
            if not year and title:
                import re
                m = re.search(r'\b(19|20)\d{2}\b', title)
                if m:
                    year = m.group(0)
            
            if year and item.get("brand") and item.get("model") and item.get("mileage"):
                log.info(f"Fetching KBB for {year} {item['brand']} {item['model']}...")
                try:
                    kbb_price = self.kbb.get_fair_price(
                        year, item['brand'], item['model'], item['mileage']
                    )
                except Exception as e:
                    log.error(f"KBB lookup failed: {e}")
                    kbb_price = None
                time.sleep(1) # politely pace search queries

        item["kbb_price"] = kbb_price
        
        # Calculate Quality Score (Simple heuristic)
        # Ratio of KBB / Listing Price. > 1.0 means good deal.
        price = item.get("price")
        if price and kbb_price and price > 0:
            item["quality_score"] = round(kbb_price / price, 2)
        else:
            item["quality_score"] = None

        log.info(f"Saving [{item_id}] {title} - ${price}")
        self.db.upsert_listing(item)

    def close(self):
        self.browser.quit()
        self.db.close()
