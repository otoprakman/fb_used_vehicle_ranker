
#!/usr/bin/env python3


import argparse, subprocess, sys, os, time, datetime, pathlib, logging, textwrap

STEPS = [
    ("Collect screenshots from Facebook",               "FB2screenshot.py"),
    ("OCR + structure data with OpenAI",               "screenshot2structured_data.py"),
    ("Filter Pareto-optimal listings",                 "pareto_finder.py"),
    ("Rank within (brand, model) using PROMETHEE",    "promethee_ranker.py"),
    ("Build HTML report",                              "report_maker.py"),
]

def run_step(name, script_path, retries=1, wait_seconds=10, extra_args=None):
    logging.info(" %s", name)
    attempt = 0
    while True:
        attempt += 1
        try:
            cmd = [sys.executable, script_path] + (extra_args or [])
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logging.info(" %s completed.\n%s", name, result.stdout.strip())
            if result.stderr:
                logging.warning("stderr from %s:\n%s", script_path, result.stderr.strip())
            return True
        except subprocess.CalledProcessError as e:
            logging.error(" %s failed (attempt %d): %s", name, attempt, e)
            if e.stdout:
                logging.error("stdout:\n%s", e.stdout)
            if e.stderr:
                logging.error("stderr:\n%s", e.stderr)
            if attempt > retries:
                return False
            logging.info("Retrying %s in %d seconds...", name, wait_seconds)
            time.sleep(wait_seconds)

def ensure_dirs():
    os.makedirs("logs", exist_ok=True)
    os.makedirs("screenshots", exist_ok=True)

def main():
    parser = argparse.ArgumentParser(description="Run the Facebook → OCR → Pareto → PROMETHEE → Report pipeline.")
    parser.add_argument("--retries", type=int, default=1, help="Number of retries per step on failure.")
    parser.add_argument("--wait", type=int, default=10, help="Seconds to wait between retries.")
    parser.add_argument("--skip-screenshots", action="store_true", help="Skip the Facebook screenshot step (reuse links.csv).")
    parser.add_argument("--skip-ocr", action="store_true", help="Skip the OCR/structuring step (reuse structured_results.csv).")
    parser.add_argument("--skip-pareto", action="store_true", help="Skip Pareto filtering.")
    parser.add_argument("--skip-rank", action="store_true", help="Skip PROMETHEE ranking.")
    parser.add_argument("--skip-report", action="store_true", help="Skip report generation.")
    parser.add_argument("--user-city", action="store_true", help="User City for Drive Distance")
    parser.add_argument("--search", default=None, help="Marketplace search query")
    parser.add_argument("--scrolls", default=None, help="Marketplace scrolls count")
    parser.add_argument("--only", choices=["screenshots","ocr","pareto","rank","report"], help="Run only a single stage.")
    args = parser.parse_args()

    extra_ss_args = []
    if args.search:
        extra_ss_args += ["--search", args.search]
        extra_ss_args += ["--scrolls", args.scrolls]

    ensure_dirs()
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join("logs", f"pipeline_{ts}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)]
    )
    logging.info("Starting pipeline run at %s", ts)

    # Map flags to steps
    plan = []
    if args.only:
        if args.only == "screenshots":
            plan = [STEPS[0]]
        elif args.only == "ocr":
            plan = [STEPS[1]]
        elif args.only == "pareto":
            plan = [STEPS[2]]
        elif args.only == "rank":
            plan = [STEPS[3]]
        elif args.only == "report":
            plan = [STEPS[4]]
    else:
        plan = [
            STEPS[0] if not args.skip_screenshots else None,
            STEPS[1] if not args.skip_ocr else None,
            STEPS[2] if not args.skip_pareto else None,
            STEPS[3] if not args.skip_rank else None,
            STEPS[4] if not args.skip_report else None,
        ]
        plan = [p for p in plan if p is not None]

    # Existence checks to allow skipping earlier stages
    # If skipping screenshots, require links.csv
    if not any(p[1]=="FB2screenshot.py" for p in plan):
        links_csv = os.path.join("screenshots", "links.csv")
        if not os.path.exists(links_csv):
            logging.error("links.csv not found at %s but screenshot step was skipped.", links_csv)
            sys.exit(2)
    # If skipping OCR, require structured_results.csv
    if not any(p[1]=="screenshot2structured_data.py" for p in plan):
        struct_csv = os.path.join("screenshots", "structured_results.csv")
        if not os.path.exists(struct_csv):
            logging.error("structured_results.csv not found at %s but OCR step was skipped.", struct_csv)
            sys.exit(2)

    ok = True
    for name, script_name in plan:
        extra = extra_ss_args if script_name == "FB2screenshot.py" else None
        if not os.path.exists(script_name):
            logging.error("Required script %s not found in current directory.", script_name)
            ok = False
            break
        if not run_step(name, script_name, retries=args.retries, wait_seconds=args.wait, extra_args=extra):
            ok = False
            break

    if ok:
        logging.info(" Pipeline completed successfully.")
        sys.exit(0)
    else:
        logging.error("Pipeline failed. See log file for details: %s", log_file)
        sys.exit(1)

if __name__ == "__main__":
    main()
