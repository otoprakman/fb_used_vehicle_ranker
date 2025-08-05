# FB Used Vehicle Ranker 🚗🔍

Automates the whole “scroll Facebook Marketplace for hours” routine:

1. **Logs in** to Facebook (Selenium)  
2. **Takes screenshots** of matching listings  
3. Runs **OCR + GPT** to extract clean data  
4. Filters the Pareto front, **ranks with PROMETHEE**  
5. Exports a **clickable HTML report** with just the best options  
6. (Optional) **Task Scheduler** runs it for you every X hours

---

## 1  Prerequisites

| Tool | Tested Version | Notes |
|------|----------------|-------|
| **Windows 10/11** | — | Scripted for Windows paths & Task Scheduler |
| **Python 3.11**  | (any 3.9+) | Installed _outside_ this repo |
| **Google Chrome** | latest | Same major version as ChromeDriver |
| **ChromeDriver** | e.g. 124.x | Put in `env\Scripts\` or add to `PATH` |
| **Git** | any | To clone the repo |

> 💡 If you prefer WSL, macOS, or Linux: only Task Scheduler pieces differ; the rest runs the same.

---

## 2  Clone & install

```powershell
git clone https://github.com/<your-user>/fb_used_vehicle_ranker.git
cd fb_used_vehicle_ranker

# create & activate a venv  (choose the tool you like)
python -m venv env
.\env\Scripts\activate

pip install -r requirements.txt
```
## 3 Configure 📄creds.env

Copy the sample (if provided) or create a new file at repo root named creds.env.

Add your own keys — everything lives in one place:
```ini
# --- Facebook login ---
FB_EMAIL=you@example.com
FB_PASSWORD=super-secret-password

# --- Run-time settings ---
BRANDS="Toyota Prius" "Honda Civic" "Nissan Altima"
RETRIES=2          # webdriver retries per search
WAIT=20            # seconds to wait between retries
SCROLLS=5          # how many FB scroll events per search
```
## 4 Run once to test
```powershell
.\run_all_brands.bat
```
Expected:

A console window shows ==== Toyota Prius ==== etc.

New screenshots land in .\screenshots\.

A HTML report appears in .\Output\YYYY-MM-DD-hhmm.html.

Logs go to .\logs\.

## 5 Set-and-forget automation (Windows Task Scheduler)
### 5.1 Quick install script

```powershell
# from repo root
powershell -ExecutionPolicy Bypass -File .\setup_task.ps1
```
Creates a task named FB-Pipeline

Runs at 08:30 and repeats every 6 h (edit inside creds.env if you ship that knob)

Uses the same creds.env for creds & tuning

### 5.2 Manual import (fallback)

Open Task Scheduler → Action → Import Task…

Select task_template.xml.

In the dialog, replace each {{CLONED_PATH}} with your repo path, save.

## 6 Customising
Want…	Do this
More/fewer brands	Edit BRANDS= list in creds.env
Different scroll depth	Change SCROLLS=
Run every 3 hours	Edit <Interval>PT3H</Interval> in task_template.xml or expose it in creds.env and tweak setup_task.ps1
Debug Selenium	Set DEBUG=1 in creds.env (code checks for it) and the browser stays visible

## 7 Troubleshooting
Symptom	Fix
Task runs but window closes instantly	Change /c → /k in Task Scheduler “Arguments” to keep the console open.
Stale‐element or human-check pop-ups	Increase RETRIES/WAIT in creds.env; update ChromeDriver to match Chrome.
Push rejected on GitHub	git pull --rebase origin main then git push (see README “first push” section).

## 8 Legal & ethics

Scraping is subject to Facebook’s TOS; use responsibly.

This repo stores no passwords in code; they stay in your local creds.env.

Ranking logic (Pareto + PROMETHEE) is subjective—always verify listings manually.

## 9 Roadmap

✨ Add Telegram / e-mail notification with top 10 options

✨ Headless browser support

✨ Docker image for cross-platform scheduling

Enjoy fewer tabs and better deals—happy hunting! 🛻💨
