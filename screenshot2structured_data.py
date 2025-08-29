
import os
import csv
import time
import json
import re
from openai import OpenAI
import easyocr
from pathlib import Path
from os import getenv
import ssl
try:
    from dotenv import load_dotenv
    load_dotenv("creds.env")  # loads .env in the same folder
except Exception:
    pass  # script still works if python-dotenv isn't installed

import argparse

def _parse_args():
    p = argparse.ArgumentParser(description="OCR to Structured Data")
    p.add_argument("--user-city", default=None, help="City of the User")
    return p.parse_known_args()[0]

args = _parse_args()

# -----------------------------
# Config
# -----------------------------
# For local Ollama usage, an OpenAI API key is not required.
# Keep reading the variable for potential future cloud usage, but do not enforce it.
OPENAI_API_KEY = getenv("OPENAI_API_KEY_FBAPP") or ""
USER_CITY = args.user_city if args.user_city else os.getenv("USER_CITY") or "Chicago, IL"
OUT_DIR = "screenshots"
LINKS_CSV = os.path.join(OUT_DIR, "links.csv")
STRUCTURED_CSV = os.path.join(OUT_DIR, "structured_results.csv")


# -----------------------------
# Helpers
# -----------------------------
def extract_json_from_response(text: str) -> str:
    """
    Extract JSON if the LLM wraps it in ```json ... ```; else return text as-is.
    """
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    return match.group(1) if match else text


def ask_openai_structured_data(client: OpenAI, text: str) -> dict:
    prompt = f"""
Extract the following from the vehicle listing text below:
- Model year
- Brand
- Model
- Price in USD (numeric)
- Location (city, state)
- Distance in mileage From listing location to User which is {USER_CITY}
- Mileage
- Mile per Gallon (fill in based on EPA data if it's null)
- Title Type (3 if clean title is stated, 2 if it's not, 1 if rebuilt title is stated)
- Exterior Color
- Condition rating (1 to 5 scale, based on condition keywords)
- Seller Name
- Listed How Many Days Ago
Text:
\"\"\"{text}\"\"\"

Return your response strictly in JSON with keys:
model_year, brand, model, price, location, distance_away, mileage, mpg, title_type, exterior_color,
condition_rating, seller_name, listed_days_ago.
"""
    # You can bump max_tokens if your OCR text is long
    resp = client.chat.completions.create(
        model="llama3.2:3b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=300
    )
    reply = resp.choices[0].message.content.strip()
    clean_json = extract_json_from_response(reply)
    try:
        return json.loads(clean_json)
    except Exception:
        # Fallback: try to salvage common trailing commas/newlines
        try:
            clean_json2 = re.sub(r",\s*}", "}", clean_json)
            return json.loads(clean_json2)
        except Exception as e:
            print("JSON parse error:", e)
            return {}


def load_existing_structured_keys(path: str):
    """
    Return sets of processed identifiers to dedupe:
    - processed_item_ids: set of item_id from prior runs
    - processed_images: set of Image (screenshot_file) from prior runs
    """
    processed_item_ids, processed_images = set(), set()
    if not os.path.exists(path):
        return processed_item_ids, processed_images
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Prefer to dedupe by item_id, fallback to Image
                iid = (row.get("item_id") or "").strip()
                img = (row.get("Image") or "").strip()
                if iid:
                    processed_item_ids.add(iid)
                if img:
                    processed_images.add(img)
    except Exception:
        pass
    return processed_item_ids, processed_images


def iter_links_rows(path: str):
    """
    Yield rows from links.csv with expected columns:
    run_ts,index_hint,item_id,url,screenshot_file
    """
    if not os.path.exists(path):
        print(f"  No links.csv found at {path}")
        return
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row
# -----------------------------
# Init
# -----------------------------
os.makedirs(OUT_DIR, exist_ok=True)
client = OpenAI(base_url = 'http://localhost:11434/v1', api_key='')

# Workaround for SSL certificate issues when EasyOCR downloads models (e.g., on macOS)
# Set EASYOCR_INSECURE_SSL=0 to disable this behavior and enforce certificate verification.
if (os.getenv("EASYOCR_INSECURE_SSL", "1").strip().lower() in ("1", "true", "yes")):
    try:
        ssl._create_default_https_context = ssl._create_unverified_context
    except Exception:
        pass

reader = easyocr.Reader(['en'])

# Prepare structured CSV in append mode; write header only if new
structured_exists = os.path.exists(STRUCTURED_CSV)
out_f = open(STRUCTURED_CSV, "a", newline="", encoding="utf-8")
fieldnames = [
    # linkage + identity
    "run_ts", "index_hint", "item_id", "url",
    # original files
    "Image", "ExtractedText",
    # extracted from LLM
    "model_year", "brand", "model", "price", "location","distance_away", "mileage", "mpg",
    "title_type", "exterior_color", "condition_rating", "seller_name", "listed_days_ago",
]
writer = csv.DictWriter(out_f, fieldnames=fieldnames)
if not structured_exists:
    writer.writeheader()

# Dedupe sets from prior structured_results.csv
processed_item_ids, processed_images = load_existing_structured_keys(STRUCTURED_CSV)

# -----------------------------
# Main loop: iterate links.csv rows -> OCR -> OpenAI -> append
# -----------------------------
rows_processed = 0
rows_skipped = 0

for row in iter_links_rows(LINKS_CSV):
    run_ts = row.get("run_ts", "")
    index_hint = row.get("index_hint", "")
    item_id = (row.get("item_id") or "").strip()
    url = row.get("url", "")
    image_file = row.get("screenshot_file", "")  # e.g., listing_<item_id>.png
    image_path = os.path.join(OUT_DIR, image_file) if image_file else ""
    # Deduping: prefer item_id, fallback to Image filename
    if item_id and item_id in processed_item_ids:
        rows_skipped += 1
        continue
    if (not item_id) and image_file and image_file in processed_images:
        rows_skipped += 1
        continue
    if not image_path or not os.path.exists(image_path):
        print(f"  Screenshot not found, skipping: {image_file}")
        rows_skipped += 1
        continue
    print(f"\ Processing item_id={item_id or 'N/A'} image={image_file}")
    # OCR
    try:
        ocr_text_lines = reader.readtext(image_path, detail=0)
        extracted_text = " ".join(ocr_text_lines)
        print(f" OCR (first 120 chars): {extracted_text[:120]}...")
    except Exception as e:
        print(f" OCR failed for {image_file}: {e}")
        extracted_text = ""
    # OpenAI extraction
    structured = {}
    if extracted_text:
        try:
            structured = ask_openai_structured_data(client, extracted_text)
            print(f" Structured: {structured}")
        except Exception as e:
            print(" OpenAI error:", e)
            structured = {}
    # Append row
    row_out = {
        "run_ts": run_ts,
        "index_hint": index_hint,
        "item_id": item_id,
        "url": url,
        "Image": image_file,
        "ExtractedText": extracted_text,
        "model_year": structured.get("model_year"),
        "brand": structured.get("brand"),
        "model": structured.get("model"),
        "price": structured.get("price"),
        "location": structured.get("location"),
        "distance_away": structured.get("distance_away"),
        "mileage": structured.get("mileage"),
        "mpg": structured.get("mpg"),
        "title_type": structured.get("title_type"),
        "exterior_color": structured.get("exterior_color"),
        "condition_rating": structured.get("condition_rating"),
        "seller_name": structured.get("seller_name"),
        "listed_days_ago": structured.get("listed_days_ago"),
    }
    print(row_out)
    writer.writerow(row_out)
    out_f.flush()
    # Update dedupe sets
    if item_id:
        processed_item_ids.add(item_id)
    elif image_file:
        processed_images.add(image_file)
    rows_processed += 1
    time.sleep(1)  # polite pacing for API limits

out_f.close()
print(f"\ Done. Appended {rows_processed} rows to {STRUCTURED_CSV} (skipped {rows_skipped} already-processed).")

