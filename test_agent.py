
from src.agent import MarketplaceAgent
import logging

# Setup basic logging to see output
logging.basicConfig(level=logging.INFO)

def test_pipeline():
    print("Initializing Agent...")
    # headless=False so we can see what's happening
    agent = MarketplaceAgent(headless=False, use_profile=True, use_local_llm=True)
    
    print("Running Search for 'Honda Civic'...")
    # 1 Scroll for speed
    agent.run_search("Honda Civic", scrolls=1)
    
    print("Verifying Database...")
    listings = agent.db.con.execute("SELECT * FROM listings").fetchall()
    print(f"Total Listings Saved: {len(listings)}")
    
    if len(listings) > 0:
        print("First listing:", listings[0])
    
    agent.close()

if __name__ == "__main__":
    test_pipeline()
