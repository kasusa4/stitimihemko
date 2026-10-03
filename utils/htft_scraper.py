# utils/htft_scraper.py
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# -------------------- CACHE --------------------
_cached_htft_data = None
_cached_matchday = None
_htft_timestamp = None

LEAGUES = {
    'English League': 7794,
    'Spanish League': 7795,
    'Italian League': 7796,
    'German League': 9184,
    'French League': 9183,
    'Dutch League': 13774,
    'Portuguese League': 13773
}

KNOWN_TEAMS = {
    'ARS','MCI','LIV','CHE','TOT','MUN','BHA','CRY','EVE','FUL',
    'LEE','NEW','NOT','SUN','WHU','WOL','BOU','BRE','BUR','AST',
    'BAR','RMA','ATM','SEV','VAL','VIL','RSO','BET','ATH','CEL',
    'GET','OSA','RAY','ELC','ESP','GIR','LEV','MAL','OVI','ALA',
    'JUV','MIL','INT','NAP','ROM','LAZ','FIO','ATA','BOL','TOR',
    'UDI','SAS','EMP','LEC','VER','CAG','GEN','CRE','SPE','SAL',
    'BAY','BVB','RBL','UNB','FRA','WOB','MAI','GLD','SCF','KOL',
    'HOF','STU','AUG','BOC','HER','SCH','DRE','HEI','MON','LEV',
    'PSG','MAR','MON','LIL','REN','OL','NIC','LMO','TRO','REI',
    'STR','CLM','AUX','TOU','LOR','ANG','BRT','HAV','MET','NAN',
    'AJA','PSV','FEB','TWE','ALK','GAE','UTR','HEE','SPA','FOR',
    'NEC','VIT','RKC','GRA','VOL','EXC','EMM','DOR','GRO','AZA',
    'BEN','POR','SPO','BRA','VGU','FAM','CHV','BOA','CAS','PAS',
    'VSC','ARU','EST','RIO','MOR','FAR','GIL','VIT','GUI','TRO'
}

def clear_htft_cache():
    global _cached_htft_data, _cached_matchday, _htft_timestamp
    _cached_htft_data = None
    _cached_matchday = None
    _htft_timestamp = None

def fetch_htft_odds(force_refresh=False):
    global _cached_htft_data, _cached_matchday, _htft_timestamp

    current_matchday = _get_current_matchday()
    if not force_refresh and _cached_htft_data and _cached_matchday == current_matchday:
        elapsed = (datetime.now() - _htft_timestamp).seconds
        print(f"📦 Using cached HT/FT data (matchday {current_matchday}, {elapsed}s old)")
        return _cached_htft_data

    print(f"🔄 Fetching fresh HT/FT odds for matchday {current_matchday}...")
    data = _fetch_htft_odds_all_leagues()
    if data:
        _cached_htft_data = data
        _cached_matchday = current_matchday
        _htft_timestamp = datetime.now()
    return data


def _get_current_matchday():
    driver = None
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        options.add_argument('--disable-logging')
        options.add_argument('--log-level=3')
        service = Service(ChromeDriverManager().install(), service_log_path='NUL')
        driver = webdriver.Chrome(service=service, options=options)
        driver.get('https://www.betpawa.co.tz/virtual-sports?virtualTab=live&leagueId=7794')
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        body = driver.find_element(By.TAG_NAME, "body").text
        m = re.search(r'Matchday\s*(\d+)', body)
        return int(m.group(1)) if m else 1
    except Exception as e:
        print(f"⚠️ Could not get matchday: {e}. Using 1.")
        return 1
    finally:
        if driver:
            driver.quit()


def _fetch_htft_odds_all_leagues():
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
    service = Service(ChromeDriverManager().install(), service_log_path='NUL')
    driver = webdriver.Chrome(service=service, options=options)

    all_matches = []
    try:
        for league_name, league_id in LEAGUES.items():
            print(f"📋 Processing {league_name}...")
            url = f'https://www.betpawa.co.tz/virtual-sports?virtualTab=upcoming&leagueId={league_id}'
            driver.get(url)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(1.5)

            # ----- CLICK HT/FT TAB (MULTIPLE SELECTORS) -----
            clicked = False
            selectors = [
                "//*[contains(text(), 'HT/FT')]",
                "//*[contains(text(), 'HTFT')]",
                "//*[contains(text(), 'HT-FT')]",
                "//button[contains(@data-market, 'HT/FT')]",
                "//div[contains(@class, 'htft')]",
                "//a[contains(@href, 'htft')]",
            ]

            for selector in selectors:
                try:
                    htft_tab = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    driver.execute_script("arguments[0].click();", htft_tab)
                    clicked = True
                    print(f"   ✅ Clicked HT/FT tab (selector: {selector[:30]})")
                    time.sleep(2)
                    break
                except:
                    continue

            if not clicked:
                try:
                    driver.execute_script("""
                        var elements = document.querySelectorAll('*');
                        for(var i=0; i<elements.length; i++) {
                            if(elements[i].textContent.includes('HT/FT')) {
                                elements[i].scrollIntoView();
                                elements[i].click();
                                break;
                            }
                        }
                    """)
                    clicked = True
                    print(f"   ✅ Clicked HT/FT tab (JS fallback)")
                    time.sleep(2)
                except:
                    pass

            if not clicked:
                print(f"   ❌ Could not click HT/FT tab for {league_name}")
                continue

            # ----- SCROLL TO LOAD ALL MATCHES -----
            for _ in range(8):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1.5)

            # Get body text
            body_text = driver.find_element(By.TAG_NAME, "body").text

            # Save debug file (optional)
            # with open(f"betpawa_{league_name.replace(' ', '_')}_HTFT.txt", "w", encoding="utf-8") as f:
            #     f.write(body_text)

            matches = parse_htft_middle_vertical(body_text, league_name)
            print(f"   Found {len(matches)} matches for {league_name}")
            all_matches.extend(matches)

        # Compute averages
        for m in all_matches:
            m['AVG'] = (m['ODD_1X'] + m['ODD_XX'] + m['ODD_2X']) / 3

        return all_matches
    finally:
        driver.quit()

def _fetch_single_league(driver, league_name, league_id):
    """Fetch one league – one attempt, no retry."""
    url = f'https://www.betpawa.co.tz/virtual-sports?virtualTab=upcoming&leagueId={league_id}'
    try:
        # Set a per‑league timeout using driver.set_page_load_timeout
        driver.set_page_load_timeout(15)
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1)

        # ---- Click HT/FT tab (multiple strategies) ----
        clicked = False
        try:
            htft_tab = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'HT/FT')]"))
            )
            driver.execute_script("arguments[0].click();", htft_tab)
            clicked = True
            print("   Clicked HT/FT tab (XPath)")
        except:
            try:
                htft_tab = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-market='HT/FT'], [data-tab='HT/FT']"))
                )
                driver.execute_script("arguments[0].click();", htft_tab)
                clicked = True
                print("   Clicked HT/FT tab (data attr)")
            except:
                try:
                    driver.execute_script("""
                        var elements = document.querySelectorAll('*');
                        for(var i=0; i<elements.length; i++) {
                            if(elements[i].textContent.trim() === 'HT/FT') {
                                elements[i].scrollIntoView();
                                elements[i].click();
                                break;
                            }
                        }
                    """)
                    clicked = True
                    print("   Clicked HT/FT tab (JS)")
                except:
                    pass

        if not clicked:
            print("   ❌ Could not click HT/FT tab")
            return False, []

        # Wait for odds to load
        try:
            WebDriverWait(driver, 8).until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), "1/X"))
            print("   ✅ Odds loaded")
        except:
            print("   ⚠️ Timeout waiting for 1/X – will try to parse anyway")
            time.sleep(1)

        # ---- Efficient scrolling: 3 scrolls down, 0.3s wait each ----
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.3)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)

        # Get body text after scrolling
        body_text = driver.find_element(By.TAG_NAME, "body").text

        # Optional debug save (commented out to save time)
        # with open(f"betpawa_{league_name.replace(' ', '_')}_HTFT.txt", "w", encoding="utf-8") as f:
        #     f.write(body_text)

        matches = parse_htft_middle_vertical(body_text, league_name)
        return True, matches

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False, []


def parse_htft_middle_vertical(text, league_name):
    """
    Parse matches and extract ONLY the middle vertical odds:
    1/X, X/X, 2/X using the exact line positions.
    """
    matches = []
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        team_match = re.match(r'^([A-Z]{2,4})\s*[-–—]\s*([A-Z]{2,4})$', line)
        if team_match:
            home = team_match.group(1)
            away = team_match.group(2)
            if home not in KNOWN_TEAMS or away not in KNOWN_TEAMS:
                i += 1
                continue

            odds_1x = odds_xx = odds_2x = None

            # 1/X: label at i+3, value at i+4
            if i + 4 < len(lines):
                label_1x = lines[i + 3].strip()
                value_1x = lines[i + 4].strip()
                if label_1x == '1/X':
                    try: odds_1x = float(value_1x)
                    except: pass

            # X/X: label at i+9, value at i+10
            if i + 10 < len(lines):
                label_xx = lines[i + 9].strip()
                value_xx = lines[i + 10].strip()
                if label_xx == 'X/X':
                    try: odds_xx = float(value_xx)
                    except: pass

            # 2/X: label at i+15, value at i+16
            if i + 16 < len(lines):
                label_2x = lines[i + 15].strip()
                value_2x = lines[i + 16].strip()
                if label_2x == '2/X':
                    try: odds_2x = float(value_2x)
                    except: pass

            if odds_1x is not None and odds_xx is not None and odds_2x is not None:
                if odds_1x > 1.0 and odds_xx > 1.0 and odds_2x > 1.0:
                    matches.append({
                        'LEAGUE': league_name,
                        'HOME_TEAM': home,
                        'AWAY_TEAM': away,
                        'ODD_1X': odds_1x,
                        'ODD_XX': odds_xx,
                        'ODD_2X': odds_2x
                    })

            i += 18  # skip entire match block
        else:
            i += 1

    return matches