# utils/live_results_scraper.py
import time
import re
from datetime import datetime
import gc
import tempfile
from typing import Dict, List, Optional, Any

# Selenium imports made optional (unavailable on Streamlit Cloud)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False
    webdriver = None
    Options = None
    By = None
    WebDriverWait = None

#  = {
  #  'English League': 7794,
   # 'Spanish League': 7795,
    #'Italian League': 7796,
    #'German League': 9184,
    #'French League': 9183,
    #'Dutch League': 13774,
    #'Portuguese League': 13773
#}

from utils.leagues_config import LEAGUES

class LiveResultsScraper:
    def __init__(self):
        self.driver = None
        self.cached_matchday = None
        self.cached_results = None
        self.run_count = 0
        self.max_runs_before_restart = 16

    def restart_driver_if_needed(self):
        """Restart ChromeDriver after max_runs_before_restart to free memory."""
        self.run_count += 1
        if self.run_count >= self.max_runs_before_restart:
            print(f"🔄 Restarting ChromeDriver (run {self.run_count})...")
            if self.driver:
                self.driver.quit()
                self.driver = None
            self.run_count = 0
            gc.collect()
            print("✅ ChromeDriver restarted and memory cleared.")

    def _ensure_driver(self):
        """
        Ensure a valid WebDriver instance exists.
        Checks if the current session is alive and recreates it if necessary.
        """
        # 1. Check if existing driver session is valid
        if self.driver:
            try:
                # Simple command to check if session is alive
                self.driver.current_url
            except Exception:
                print("🔄 Driver session invalid – recreating...")
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None

        # 2. Restart driver if needed (run count based)
        self.restart_driver_if_needed()

        # 3. Create new driver if None
        if self.driver is None:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument('--disable-logging')
            options.add_argument('--log-level=3')
            options.add_argument('--js-flags=--max-old-space-size=512')
            options.add_argument('--disable-accelerated-2d-canvas')
            options.add_argument('--disable-software-rasterizer')
            temp_dir = tempfile.mkdtemp()
            options.add_argument(f'--user-data-dir={temp_dir}')
            service = Service(ChromeDriverManager().install(), service_log_path='NUL')
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.set_page_load_timeout(30)

        return self.driver


    def _safe_get(self, url, timeout=20):
        driver = self._ensure_driver()
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        return True

    def get_current_matchday(self):
        driver = self._ensure_driver()
        try:
            self._safe_get('https://www.betpawa.co.tz/virtual-sports?virtualTab=live&leagueId=7794', timeout=20)
            body = driver.find_element(By.TAG_NAME, "body").text
            m = re.search(r'Matchday\s*(\d+)', body)
            if m:
                md = int(m.group(1))
                print(f"✅ Matchday {md} from scraper")
                return md
        except Exception as e:
            print(f"⚠️ Scraper matchday failed: {e}")

        # Time-based fallback
        print("⚠️ Using time‑based matchday estimate.")
        now = datetime.now()
        base = now.replace(hour=0, minute=0, second=0, microsecond=0)
        mins = (now - base).seconds // 60
        return (mins // 5) + 1

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8),
           retry=retry_if_exception_type((Exception)))
    def _fetch_league_with_retry(self, league_name, league_id):
        driver = self._ensure_driver()
        url = f'https://www.betpawa.co.tz/virtual-sports?virtualTab=live&leagueId={league_id}'
        driver.get(url)
        WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        #increase scrolls
        for _ in range(7):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.6)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.8)
        body_text = driver.find_element(By.TAG_NAME, "body").text
        return self._parse_live_results(body_text, league_name)

    def fetch_live_results(self):
        current_md = self.get_current_matchday()
        if current_md == self.cached_matchday and self.cached_results:
            print(f"ℹ️ Cached results for MD{current_md}")
            return self.cached_results

        print(f"🔄 Fetching live results for MD{current_md}...")
        driver = self._ensure_driver()
        all_results = {}
        start_time = time.time()
        max_duration = 90

        for league_name, league_id in LEAGUES.items():
            if time.time() - start_time > max_duration:
                print(f"⏱️ Time limit reached. Stopping live fetch.")
                break
            try:
                matches = self._fetch_league_with_retry(league_name, league_id)
                if matches:
                    all_results[league_name] = matches
                    print(f"   ✅ {len(matches)} matches in {league_name}")
                else:
                    print(f"   ⚠️ No matches in {league_name} (after retry)")
            except Exception as e:
                print(f"   ❌ Error {league_name}: {e}")
                continue

        self.cached_matchday = current_md
        self.cached_results = {'matchday': current_md, 'results': all_results}
        elapsed = time.time() - start_time
        print(f"✅ Live fetch complete in {elapsed:.1f}s")
        return self.cached_results

    def _parse_live_results(self, text, league_name):
        matches = []
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            team = re.match(r'^([A-Z]{2,4})\s*[-–—]\s*([A-Z]{2,4})$', line)
            if team:
                home, away = team.group(1), team.group(2)
                ft_h = ft_a = None
                ht_h = ht_a = 0
                for off in range(1, 11):
                    if i+off-1 >= len(lines): break
                    sl = lines[i+off-1]
                    pairs = re.findall(r'\(?(\d+)\s*[-–—]\s*(\d+)\)?', sl)
                    if pairs:
                        ft_h, ft_a = map(int, pairs[-1])
                        if len(pairs) > 1:
                            ht_h, ht_a = map(int, pairs[-2])
                        if '(' in sl and ')' in sl and len(pairs)==1:
                            ht_h, ft_h = ft_h, None
                            continue
                        break
                if ft_h is not None and ft_a is not None:
                    matches.append({'home': home, 'away': away, 'ft_h': ft_h, 'ft_a': ft_a, 'ht_h': ht_h, 'ht_a': ht_a})
        return matches

    def fetch_fixtures(self, league_id):
        """Fetch upcoming fixtures with aggressive scrolling, retry, and session recovery."""
        url = f'https://www.betpawa.co.tz/virtual-sports?virtualTab=upcoming&leagueId={league_id}'

        for attempt in range(3):
            try:
                # Ensure driver is valid (recreates if session is dead)
                driver = self._ensure_driver()
                driver.get(url)
                WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(2)

                # Scroll to load all fixtures
                for _ in range(8):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(0.5)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1.5)

                # Click "Show More" if present
                try:
                    show_more = driver.find_element(By.XPATH, "//*[contains(text(), 'Show More') or contains(text(), 'Load More')]")
                    driver.execute_script("arguments[0].click();", show_more)
                    time.sleep(1)
                except:
                    pass

                # Parse fixtures
                body = driver.find_element(By.TAG_NAME, "body").text
                fixtures = self._parse_fixtures(body)
                if fixtures:
                    return fixtures

                # Fallback: parse from raw HTML
                html = driver.page_source
                fixtures = self._parse_fixtures_from_html(html)
                if fixtures:
                    return fixtures

                print(f"   🔄 Attempt {attempt+1}: No fixtures, retrying...")
                time.sleep(2)

            except Exception as e:
                error_msg = str(e)
                # If session is invalid, recreate driver and retry
                if "invalid session id" in error_msg or "No active session" in error_msg:
                    print(f"   🔄 Invalid session – recreating driver (attempt {attempt+1})")
                    if self.driver:
                        try:
                            self.driver.quit()
                        except:
                            pass
                        self.driver = None
                    # Driver will be recreated in next loop iteration via _ensure_driver()
                    time.sleep(1)
                    continue
                else:
                    print(f"   ❌ Attempt {attempt+1} failed: {e}")
                    time.sleep(2)

        return []


    def _parse_fixtures(self, text):
        fixtures = []
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(k in line for k in ['League', 'Matchday', 'Results', '1X2', 'O/U', 'BTTS', 'DC', 'HT/FT']):
                continue
            if re.search(r'\d+\.\d+', line) or re.search(r'\d\s+\d', line):
                continue
            match = re.search(r'([A-Z]{2,4})\s*[-–—]\s*([A-Z]{2,4})', line)
            if match:
                home, away = match.group(1), match.group(2)
                if home.isalpha() and away.isalpha() and (home, away) not in fixtures:
                    fixtures.append((home, away))
        return fixtures
    

    def _parse_fixtures_response(self, data: Dict) -> Dict:
        """
        Parse the /getCurrentWeek/scheduled response.
        Returns: {
            'season_id': int,
            'week_id': int,
            'matches': [{'home': 'ARS', 'away': 'MCI'}, ...]
        }
        """
        season_id = data.get('seasonId')
        week_id = data.get('week', {}).get('id')
        raw_matches = data.get('matches', {}).get('ids', [])

        parsed_matches = []
        for match_str in raw_matches:
            if '-' not in match_str:
                continue
            home, away = match_str.split('-', 1)
            parsed_matches.append({
                'home': home.strip().upper(),
                'away': away.strip().upper()
            })

        return {
            'season_id': season_id,
            'week_id': week_id,
            'matches': parsed_matches
        }
    

    def _parse_fixtures_from_html(self, html):
        pattern = r'([A-Z]{2,4})\s*[-–—]\s*([A-Z]{2,4})'
        matches = re.findall(pattern, html)
        fixtures = []
        for home, away in matches:
            if home.isalpha() and away.isalpha() and (home, away) not in fixtures:
                fixtures.append((home, away))
        return fixtures

    def __del__(self):
        if self.driver:
            self.driver.quit()