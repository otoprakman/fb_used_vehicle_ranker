
import duckdb
import os
from datetime import datetime
from typing import Optional, Dict, List

class MarketplaceDB:
    def __init__(self, db_path: str = "marketplace.duckdb"):
        self.db_path = db_path
        self.con = duckdb.connect(self.db_path)
        self._init_schema()

    def _init_schema(self):
        """Initialize the database schema if it doesn't exist."""
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                item_id VARCHAR PRIMARY KEY,
                url VARCHAR,
                title VARCHAR,
                price DECIMAL,
                brand VARCHAR,
                model VARCHAR,
                mileage INTEGER, -- in miles
                location VARCHAR,
                distance_miles INTEGER,
                description VARCHAR,
                seller_name VARCHAR,
                status VARCHAR DEFAULT 'active', -- active, sold, removed
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                listed_days_ago INTEGER,
                kbb_price DECIMAL,
                quality_score DECIMAL,
                raw_json VARCHAR -- store full LLM extraction just in case
            );
            
            CREATE INDEX IF NOT EXISTS idx_status ON listings(status);
            CREATE INDEX IF NOT EXISTS idx_url ON listings(url);
        """)

    def upsert_listing(self, data: Dict):
        """
        Insert or Update a listing. 
        If it exists, update last_seen_at, price, status, etc.
        """
        # Prepare data with defaults
        item_id = data.get("item_id")
        if not item_id:
            return  # Can't insert without ID

        now = datetime.now()
        
        # Check existence
        exists = self.con.execute("SELECT 1 FROM listings WHERE item_id = ?", [item_id]).fetchone()
        
        if exists:
            # Update
            query = """
                UPDATE listings SET 
                    last_seen_at = ?,
                    price = ?,
                    status = 'active', -- Reactivate if it was marked missing
                    description = ?,
                    kbb_price = COALESCE(?, kbb_price), -- Only update if new value provided
                    quality_score = COALESCE(?, quality_score)
                WHERE item_id = ?
            """
            self.con.execute(query, [
                now, 
                data.get("price"), 
                data.get("description"), 
                data.get("kbb_price"),
                data.get("quality_score"),
                item_id
            ])
        else:
            # Insert
            query = """
                INSERT INTO listings (
                    item_id, url, title, price, brand, model, mileage, 
                    location, distance_miles, description, seller_name, 
                    status, first_seen_at, last_seen_at, listed_days_ago,
                    kbb_price, quality_score, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            """
            self.con.execute(query, [
                item_id,
                data.get("url"),
                data.get("title"),
                data.get("price"),
                data.get("brand"),
                data.get("model"),
                data.get("mileage"),
                data.get("location"),
                data.get("distance_miles"),
                data.get("description"),
                data.get("seller_name"),
                now, 
                now,
                data.get("listed_days_ago"),
                data.get("kbb_price"),
                data.get("quality_score"),
                str(data) # raw_json
            ])

    def mark_sold_or_removed(self, item_id: str, status: str = "removed"):
        """Mark a listing as sold or removed."""
        if status not in ("sold", "removed"):
            raise ValueError("Status must be 'sold' or 'removed'")
        
        self.con.execute("UPDATE listings SET status = ? WHERE item_id = ?", [status, item_id])

    def get_active_listings(self) -> List[Dict]:
        """Get all currently active listings."""
        columns = [c[0] for c in self.con.execute("DESCRIBE listings").fetchall()]
        rows = self.con.execute("SELECT * FROM listings WHERE status = 'active'").fetchall()
        
        results = []
        for row in rows:
            results.append(dict(zip(columns, row)))
        return results

    def get_listing_by_url(self, url: str) -> Optional[Dict]:
        columns = [c[0] for c in self.con.execute("DESCRIBE listings").fetchall()]
        row = self.con.execute("SELECT * FROM listings WHERE url = ?", [url]).fetchone()
        if row:
            return dict(zip(columns, row))
        return None

    def close(self):
        self.con.close()
