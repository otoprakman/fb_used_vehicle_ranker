import os, math, webbrowser
import pandas as pd
from pathlib import Path

OUT_DIR = "screenshots"
STRUCTURED_CSV = os.path.join('', r"Output\used_cars_promethee_ranked.csv")

# ---------- 1) Load data ----------
if not os.path.exists(STRUCTURED_CSV):
    raise FileNotFoundError(f"{STRUCTURED_CSV} not found. Run OCR+OpenAI first.")

df = pd.read_csv(STRUCTURED_CSV)


# Keep only rows with essentials
needed = ["url", "item_id", "price", "model_year", "brand", "model", "condition_rating", "listed_days_ago"]
for col in needed:
    if col not in df.columns:
        df[col] = None

# Coerce numerics
for col in ["price", "model_year", "condition_rating", "listed_days_ago"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Compute age if we have model_year
from datetime import datetime
current_year = datetime.now().year
df["age"] = current_year - df["model_year"]
df = df[(df['age']<=15)&(df['avg_yearly_mileage']>10000)&(df['listed_days_ago']<7)&(df['title_type']==3)&(df['price']<=6000)&(df['price']>=3500)]

# Drop rows missing key pieces we need to rank
rank_df = df.dropna(subset=["price", "age"]).copy()
rank_df = rank_df[rank_df["price"] > 0]
rank_df = rank_df[(rank_df["age"] >= 0) & (rank_df["age"] <= 50)]  # sanity band

if rank_df.empty:
    raise ValueError("No rows with enough data to rank. Check structured_results.csv contents.")

rank_df = rank_df.sort_values(by=['brand','model','promethee_rank'])

# ---------- 3) Build HTML report ----------

def safe_img_tag(image_filename: str) -> str:
    if not isinstance(image_filename, str) or not image_filename.strip():
        return '<div style="color:#a00">Screenshot: None</div>'
    img_path = Path(OUT_DIR, image_filename)
    if not img_path.exists():
        return f'<div style="color:#a00">Screenshot missing: {image_filename}</div>'
    # Build proper file:// URL
    img_uri = img_path.resolve().as_uri()
    return f'<img src="{img_uri}" alt="{image_filename}" style="max-width:340px;border:1px solid #ccc;border-radius:8px" />'


def row_html(r):
    img_html = safe_img_tag('listing_'+str(int(r.get("item_id", "")))+'.png')
    print(img_html)
    price = f"${int(r['price']):,}" if not math.isnan(r['price']) else "N/A"
    cond  = int(r["condition_rating"]) if not math.isnan(r["condition_rating"]) else "N/A"
    age   = int(r["age"]) if not math.isnan(r["age"]) else "N/A"
    listed = (f"{int(r['listed_days_ago'])} days ago"
              if pd.notna(r["listed_days_ago"]) else "N/A")
    title = " ".join([str(r.get("brand","") or ""), str(r.get("model","") or "")]).strip() or "(Unknown title)"
    url = r.get("url","") or "#"
    filename_note = str(int(r.get("item_id","None")))
    return f"""
    <tr>
      <td>{img_html}</td>
      <td style="padding-left:12px;">
        <div style="font-size:16px;font-weight:600;margin-bottom:4px;">
          <a href="{url}" target="_blank" style="text-decoration:none;color:#0b57d0">{title}</a>
        </div>
        <div>Price: <b>{price}</b></div>
        <div>Age: <b>{age}</b> years</div>
        <div>Condition rating: <b>{cond}/5</b></div>
        <div>Listed: <b>{listed}</b></div>
        <div>Model year: {r.get('model_year','')}</div>
        <div>Aprox. Distance: {r.get('distance_away','')}</div>
        <div>Screenshot: {filename_note}</div>
        <div style="margin-top:4px;color:#555">Rank: {r['promethee_rank']:.3f}</div>
      </td>
    </tr>
    """

html_rows = "\n".join(
    row_html(row)
    for _, group in rank_df.groupby(['brand', 'model'])
    for _, row in group.nsmallest(10, 'promethee_rank').iterrows()
)
html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Top 3 Picks</title>
</head>
<body style="font-family:Arial,Helvetica,sans-serif;">
  <h2>Top 3 Picks for Your Search</h2>
  <table cellpadding="8" cellspacing="0" style="border-collapse:collapse;">
    {html_rows}
  </table>
</body>
</html>
"""

report_path = os.path.join('', r"Output\top10_report.html")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Report written to: {report_path}")
try:
    webbrowser.open('file://' + str(Path(report_path).resolve()))
except Exception:
    pass
