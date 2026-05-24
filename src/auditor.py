
import logging
import time
from datetime import datetime, timedelta
from typing import List

from .tools.browser import BrowserTool
from .database import MarketplaceDB

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
log = logging.getLogger("auditor")

class AuditorAgent:
    def __init__(self, headless: bool = True):
        self.browser = BrowserTool(headless=headless, use_profile=True)
        self.db = MarketplaceDB()

    def audit_listings(self, max_check: int = 50):
        """
        Check active listings to see if they are still valid.
        """
        try:
            self.browser.start()
            
            # Get active listings that haven't been seen in > 24 hours
            # Or just check all active listings sorted by last_seen
            listings = self.db.get_active_listings()
            
            # Filter for ones not checked recently (simplification: check all for now)
            # In production: WHERE last_seen_at < NOW() - INTERVAL 1 DAY
            
            count = 0
            for item in listings:
                if count >= max_check:
                    break
                
                item_id = item.get("item_id")
                url = item.get("url")
                
                status = self._check_listing_status(url)
                
                if status != "active":
                    log.info(f"Listing {item_id} is now {status}. Updating DB.")
                    self.db.mark_sold_or_removed(item_id, status)
                else:
                    # Update last_seen_at
                    # We can use upsert or a minimal update query
                    self.db.upsert_listing(item) # re-upserts with now()
                    log.info(f"Listing {item_id} is still {status}.")
                
                count += 1
                time.sleep(2) # Polite delay
                
        except Exception as e:
            log.error(f"Audit failed: {e}")
        finally:
            self.browser.quit()
            self.db.close()

    def _check_listing_status(self, url: str) -> str:
        """
        Visit URL and infer status.
        Returns: 'active', 'sold', 'removed'
        """
        try:
            self.browser.driver.get(url)
            time.sleep(3)
            
            page_text = self.browser.get_page_source().lower()
            
            # Heuristics
            if "marketplacethis item isn't available anymore" in page_text:
                return "removed"
            if "this listing has been deleted" in page_text:
                return "removed"
            if "sold" in page_text:
                 # Be careful, "sold" might appear in description "not sold separately"
                 # Look for specific badges or buttons
                 # Facebook often puts "Sold" in a gray span or button
                 soup = self.browser.driver.find_elements(by="xpath", value="//*[text()='Sold']")
                 if soup: 
                     return "sold"
            
            # If we are redirected to the main marketplace feed, it's likely removed
            if "facebook.com/marketplace/?ref" in self.browser.driver.current_url:
                return "removed"
                
            return "active"
        except Exception as e:
            log.warning(f"Error checking {url}: {e}")
            return "active" # Assume active on error to be safe
