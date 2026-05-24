
import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv("creds.env")
log = logging.getLogger("watchdog")

class WatchdogAgent:
    def __init__(self, log_path: str = "logs/app.log", use_local: bool = True):
        self.log_path = log_path
        if use_local:
             # Ollama local endpoint
            self.client = OpenAI(
                base_url='http://localhost:11434/v1',
                api_key='ollama', 
            )
            self.model = "llama3.2:3b"
        else:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY_FBAPP"))
            self.model = "gpt-4o-mini"

    def analyze_logs(self):
        """Read logs and generate a health report."""
        if not os.path.exists(self.log_path):
            log.info("No logs to analyze.")
            return

        with open(self.log_path, 'r', encoding='utf-8') as f:
            # Read last 200 lines to avoid token limits
            lines = f.readlines()
            recent_logs = "".join(lines[-200:])

        prompt = f"""
        Analyze the following application logs for a Facebook Marketplace scraper.
        Identify any recurring failures, specific exceptions, or patterns (e.g., login failure, selector not found).
        Suggest a potential fix if possible.
        
        Logs:
        {recent_logs}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            report = response.choices[0].message.content
            print("\n=== Watchdog Health Report ===\n")
            print(report)
            print("\n==============================\n")
            
            # Save report
            with open("logs/daily_report.txt", "w") as f:
                f.write(report)
                
        except Exception as e:
            log.error(f"Watchdog analysis failed: {e}")

if __name__ == "__main__":
    agent = WatchdogAgent()
    agent.analyze_logs()
