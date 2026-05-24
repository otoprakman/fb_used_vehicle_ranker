
import re
import logging
from typing import Optional
# We need to ensure duckduckgo_search is installed
try:
    from duckduckgo_search import DDGS
except ImportError:
    try:
        from ddgs import DDGS
    except ImportError:
        DDGS = None

log = logging.getLogger("kbb")

class KBBTool:
    def __init__(self):
        if not DDGS:
            log.warning("duckduckgo_search not installed. KBB lookups will yield None.")

    def get_fair_price(self, year: str, make: str, model: str, mileage: int) -> Optional[float]:
        """
        Estimates fair price by searching web snippets.
        """
        if not DDGS:
            return None
            
        full_model = f"{year} {make} {model}"
        query = f"{full_model} {mileage} miles fair purchase price kbb"
        
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
                
            for res in results:
                snippet = res.get('body', '') + " " + res.get('title', '')
                # Regex to find price ranges: $10,000 - $12,000 or similar
                # Simple extraction of dollar amounts
                prices = re.findall(r'\$[\d,]+', snippet)
                
                valid_prices = []
                for p in prices:
                    try:
                        val = float(p.replace('$', '').replace(',', ''))
                        if 1000 < val < 100000: # Sanity check
                            valid_prices.append(val)
                    except:
                        pass
                
                if valid_prices:
                    # Return average of found prices in the top snippet
                    avg_price = sum(valid_prices) / len(valid_prices)
                    log.info(f"Estimated KBB for {full_model}: ${avg_price:,.2f}")
                    return avg_price
                    
        except Exception as e:
            log.error(f"KBB search failed: {e}")
            
        return None
