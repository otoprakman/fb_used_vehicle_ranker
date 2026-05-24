
import random
import time
import os
import logging
from typing import Optional, List
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("browser")

load_dotenv("creds.env")

class BrowserTool:
    def __init__(self, headless: bool = False, use_profile: bool = True):
        self.headless = headless
        self.use_profile = use_profile
        self.driver = None
        self.wait = None
        self.email = os.getenv("FB_EMAIL")
        self.password = os.getenv("FB_PASSWORD")

    def _init_driver(self):
        if self.driver:
            return

        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # Anti-detection
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        if self.use_profile:
            # Use a persistent profile to save login state
            # Assumes running on Windows for now based on context
            user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
            os.makedirs(user_data_dir, exist_ok=True)
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument("--profile-directory=Default")

        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        self.wait = WebDriverWait(self.driver, 10)
        
        # Stealth JS
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    def start(self):
        self._init_driver()

    def quit(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def human_typing(self, element, text, delay=0.1):
        for char in text:
            element.send_keys(char)
            time.sleep(delay + random.uniform(0, 0.05))

    def login_facebook(self) -> bool:
        """
        Ensures we are logged into Facebook. 
        Returns True if logged in (or already logged in), False if failed.
        """
        self._init_driver()
        
        log.info("Navigating to Facebook...")
        self.driver.get("https://www.facebook.com")
        
        # Check if already logged in (look for profile or feed)
        if self._is_logged_in():
            log.info("Already logged in.")
            return True

        log.info("Not logged in. Attempting login...")
        self.driver.get("https://www.facebook.com/login")
        
        try:
            email_field = self.wait.until(EC.presence_of_element_located((By.ID, "email")))
            pass_field = self.driver.find_element(By.ID, "pass")
            
            if not self.email or not self.password:
                log.error("FB_EMAIL or FB_PASSWORD not set in creds.env")
                return False

            self.human_typing(email_field, self.email)
            self.human_typing(pass_field, self.password)
            
            login_btn = self.driver.find_element(By.NAME, "login")
            login_btn.click()
            
            # Wait for navigation
            time.sleep(5)
            
            if self._is_logged_in():
                log.info("Login successful.")
                return True
            else:
                log.error("Login failed (checkpoint or wrong creds).")
                return False

        except Exception as e:
            log.error(f"Error during login: {e}")
            return False

    def _is_logged_in(self) -> bool:
        """Check for common elements present only when logged in."""
        try:
            # Look for aria-label='Account' or standard feed containers
            if "facebook.com/login" in self.driver.current_url:
                return False
            # If we see the main navigation role or similar
            self.driver.find_element(By.CSS_SELECTOR, "[role='navigation']") # rough check
            return True
        except:
            return False

    def navigate_to_marketplace_search(self, query: str):
        """Navigate to Marketplace and search for a term."""
        encoded_query = query.replace(" ", "%20")
        url = f"https://www.facebook.com/marketplace/search/?query={encoded_query}"
        self.driver.get(url)
        time.sleep(random.uniform(3, 5))

    def get_page_source(self) -> str:
        return self.driver.page_source

    def scroll_down(self, times: int = 1):
        for _ in range(times):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(2, 4))
