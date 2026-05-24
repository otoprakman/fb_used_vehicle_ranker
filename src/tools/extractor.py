
import json
import re
import os
import logging
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from openai import OpenAI  # Compatible with Ollama
from json_repair import repair_json
from dotenv import load_dotenv

load_dotenv("creds.env")
log = logging.getLogger("extractor")

class ExtractorTool:
    def __init__(self, model: str = "llama3.2:3b", use_local: bool = True):
        self.model = model
        self.use_local = use_local
        
        if use_local:
            # Ollama local endpoint
            self.client = OpenAI(
                base_url='http://localhost:11434/v1',
                api_key='ollama', # required but ignored
            )
        else:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY_FBAPP"))
            self.model = "gpt-4o-mini" # Fallback if not local

    def extract_listings_from_html(self, html_content: str) -> List[Dict]:
        """
        Parses HTML to find listing cards, then uses LLM to structure the data.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Heuristic: Find all anchor tags that look like marketplace items
        # Facebook structure changes, but links usually contain '/marketplace/item/'
        item_links = soup.find_all('a', href=re.compile(r'/marketplace/item/'))
        
        unique_cards = {}
        for link in item_links:
            # Get the card container (usually a few parents up, or the link itself content)
            # We'll extract all text from the link's parent container to capture price/title
            # Heuristic: The link is usually the card cover or title. 
            # We want the text of the surrounding 'div' that represents the card.
            
            # Simple approach: Get text from the link itself and its direct siblings/parent
            # Just grabbing the link text is often enough for Title + Price
            text = link.get_text(separator=" ", strip=True)
            
            # If text is too short, try parent
            if len(text) < 10:
                parent = link.parent
                if parent:
                    text = parent.get_text(separator=" ", strip=True)

            href = link.get('href')
            
            # Clean ID
            match = re.search(r'/marketplace/item/(\d+)', href)
            if not match:
                continue
            item_id = match.group(1)
            
            # Basic dedupe
            if item_id in unique_cards:
                if len(text) > len(unique_cards[item_id]['raw_text']): # Keep the one with more text
                    unique_cards[item_id] = {'id': item_id, 'url': href, 'raw_text': text}
            else:
                unique_cards[item_id] = {'id': item_id, 'url': href, 'raw_text': text}

        # Process in batches to save LLM calls? 
        # For now, let's process individually or in small groups. 
        # Text is short (e.g. "2015 Honda Civic $5000 120k miles Chicago, IL")
        
        results = []
        for item_id, data in unique_cards.items():
            print(data['raw_text'])
            if len(data['raw_text']) < 10: # limit noise
                continue
                
            structured = self._parse_with_llm(data['raw_text'])
            if structured:
                # Merge metadata
                structured['item_id'] = item_id
                structured['url'] = "https://www.facebook.com" + data['url'].split('?')[0]
                results.append(structured)

        return results

    def _parse_with_llm(self, text: str) -> Dict[str, Any]:
        prompt = f"""
        Extract vehicle data from this Marketplace listing snippet: "{text}"
        
        Return JSON with keys:
        - title (str)
        - price (number, remove currency symbols)
        - brand (str, inferred)
        - model (str)
        - mileage (int, inferred)
        - location (str)
        - description (str, brief)
        
        If not a vehicle or missing critical data (price/title), return empty JSON {{}}.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"} # Force JSON if supported, else rely on prompt
            )
            content = response.choices[0].message.content
            # Repair JSON
            repaired = repair_json(content)
            data = json.loads(repaired)
            return data
        except Exception as e:
            log.warning(f"LLM extraction failed for '{text[:30]}...': {e}")
            return {}
