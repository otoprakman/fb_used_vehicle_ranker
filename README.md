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
| **Windows 10/11** or **macOS/Linux** | — | Cross-platform support with .bat and .sh scripts |
| **Python 3.11**  | (any 3.9+) | Installed _outside_ this repo |
| **Google Chrome** | latest | Same major version as ChromeDriver |
| **ChromeDriver** | e.g. 124.x | Put in `env\Scripts\` (Windows) or `env/bin/` (Unix) or add to `PATH` |
| **Git** | any | To clone the repo |

> 💡 Task Scheduler automation is Windows-specific, but the core pipeline runs on any platform.

---

## 2  Clone & install

```bash
git clone https://github.com/otoprakman/fb_used_vehicle_ranker.git
cd fb_used_vehicle_ranker

# create & activate a venv
python -m venv env

# Windows:
.\env\Scripts\activate

# macOS/Linux:
source env/bin/activate

pip install -r requirements.txt
```
## 3 Configure 📄creds.env

Create a new file at repo root named creds.env.

Add your own keys — everything lives in one place:
```ini
# --- Facebook login ---
FB_EMAIL=you@example.com
FB_PASSWORD=super-secret-password

# --- OPENAI KEY ---
OPENAI_API_KEY_FBAPP=ultra-secret-key

# --- Run-time settings ---
FB_SEARCH_TERM="Toyota Prius" "Honda Civic" "Nissan Altima"
RETRIES=2          # webdriver retries per search
WAIT=20            # seconds to wait between retries
SCROLLS=5          # how many FB scroll events per search
USER_CITY=Chicago, IL # user location for getting distance between seller and user
```
## 4 Install Ollama and pull the Llama model (required for local GPT)

This project uses a local LLM via Ollama. The code is configured to call an OpenAI-compatible endpoint at http://localhost:11434 with the model name `llama3.2:3b`.

- Why: `screenshot2structured_data.py` sends prompts to a local Llama model through Ollama, so no cloud API calls are needed for the extraction step.
- Port: Ollama serves the OpenAI-compatible API at 11434 by default.

Steps:
1) Install Ollama
- macOS or Linux (official script):
```bash
curl -fsSL https://ollama.com/install.sh | sh
```
- macOS (Homebrew alternative):
```bash
brew install ollama
```
- Windows (any of the following):
```powershell
winget install Ollama.Ollama
```
Or download/install from: https://ollama.com/download/windows

2) Start the Ollama service (if not started automatically)
```bash
ollama serve
```
Note: On many systems, running `ollama run ...` will automatically start the service in the background. Ensure port 11434 is available.

3) Pull the required Llama model
```bash
ollama pull llama3.2:3b
```
You can test it quickly with:
```bash
ollama run llama3.2:3b "Hello from Llama"
```
If you prefer a bigger model and have more resources, you may try `llama3.1:8b` (and adjust the code accordingly), but the repo is set to `llama3.2:3b` by default.

Troubleshooting tips:
- If the scripts can’t connect: verify the server is running: `curl http://localhost:11434/api/tags`
- Firewall: allow local connections to 11434.
- Resources: models can take several GB of RAM and disk; ensure you have enough space.

## 5 Run once to test

**Windows:**
```cmd
.\run_all_brands.bat
```

**macOS/Linux:**
```bash
./run_all_brands.sh
```
Expected:

A console window shows ==== Toyota Prius ==== etc.

New screenshots land in .\screenshots\.

A HTML report appears in .\Output\YYYY-MM-DD-hhmm.html.

Logs go to .\logs\.

## 6 Set-and-forget automation (Windows Task Scheduler)
### 6.1 Quick install script

```powershell
# from repo root
powershell -ExecutionPolicy Bypass -File .\setup_task.ps1
```
Creates a task named FB-Pipeline

Runs at 08:30 and repeats every 6 h (edit inside fb_pipeline_daily if you ship that knob)

Uses the same creds.env for creds & tuning

### 6.2 Manual import (fallback)

Open Task Scheduler → Action → Import Task…

Select fb_pipeline_daily.xml.

In the dialog, replace each {{CLONED_PATH}} with your repo path, save.

## 7 Customising

Want…	Do this

Ranking logic (Pareto + PROMETHEE) requires weights for different criteria, adjust the weights in promethee_ranker.py

More/fewer brands	Edit FB_SEARCH_TERM= list in creds.env

Different scroll depth	Change SCROLLS=

Run every 3 hours	Edit <Interval>PT3H</Interval> in fb_pipeline_daily.xml or expose it in creds.env and tweak setup_task.ps1

Debug Selenium	Set DEBUG=1 in creds.env (code checks for it) and the browser stays visible

## 8 Troubleshooting

Symptom	Fix

Task runs but window closes instantly	Change /c → /k in Task Scheduler “Arguments” to keep the console open.

Stale‐element or human-check pop-ups	Increase RETRIES/WAIT in creds.env; update ChromeDriver to match Chrome.

Push rejected on GitHub	git pull --rebase origin main then git push (see README “first push” section).

## 9 Legal & ethics

Scraping is subject to Facebook’s TOS; use responsibly.

This repo stores no passwords in code; they stay in your local creds.env.

Ranking logic (Pareto + PROMETHEE) is subjective—always verify listings manually.

## 10 Roadmap

✨ Add Telegram / e-mail notification with top 10 options

✨ Headless browser support

✨ Docker image for cross-platform scheduling

Enjoy fewer tabs and better deals—happy hunting! 🛻💨
