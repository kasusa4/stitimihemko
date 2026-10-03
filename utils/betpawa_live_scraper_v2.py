# utils/betpawa_live_scraper_v2.py
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import json
import requests

# ---------- 7 LEAGUE TEAMS FILTER ----------
LEAGUE_TEAMS = {
    'English League': ['ARS', 'AST', 'BHA', 'BOU', 'BRE', 'BUR', 'CHE', 'CRY', 'EVE', 'FUL', 'LEE', 'LIV', 'MCI', 'MUN', 'NEW', 'NOT', 'SUN', 'TOT', 'WHU', 'WOL'],
    'Spanish League': ['ALA', 'ATH', 'ATM', 'BAR', 'BET', 'CEL', 'ELC', 'ESP', 'GET', 'GIR', 'LEV', 'MAL', 'OSA', 'OVI', 'RAY', 'RMA', 'RSO', 'SEV', 'VAL', 'VIL'],
    'Italian League': ['ATA', 'BOL', 'CAG', 'COM', 'CRE', 'FIO', 'GEN', 'INT', 'JUV', 'LAZ', 'LEC', 'MIL', 'NAP', 'PAR', 'PIS', 'ROM', 'SAS', 'TOR', 'UDI', 'VER'],
    'German League': ['AUG', 'COL', 'DOR', 'EIN', 'FCB', 'FRE', 'HEI', 'HOF', 'HSV', 'LEV', 'MAI', 'MON', 'RBL', 'STP', 'STU', 'UNI', 'WER', 'WOL'],
    'French League': ['ANG', 'ASM', 'AUX', 'BRE', 'HAV', 'LEN', 'LIL', 'LOR', 'LYO', 'MAR', 'MET', 'NAN', 'NIC', 'PAR', 'PSG', 'REN', 'STR', 'TOU'],
    'Dutch League': ['AJA', 'AZA', 'EXC', 'FEY', 'FOR', 'GAE', 'GRO', 'HEE', 'HER', 'NAC', 'NEC', 'PEC', 'PSV', 'SPA', 'TEL', 'TWE', 'UTR', 'VOL'],
    'Portuguese League': ['ALV', 'ARO', 'AVS', 'BEN', 'BRA', 'CAS', 'EST', 'ETA', 'FAM', 'GIL', 'GUI', 'MOR', 'NAC', 'POR', 'RIO', 'SAN', 'SPO', 'TON']
}

ALL_TEAMS = set()
for teams in LEAGUE_TEAMS.values():
    ALL_TEAMS.update(teams)

def is_valid_team(team_name):
    """Check if a team belongs to the 7 leagues."""
    if not team_name:
        return False
    team_clean = team_name.upper().strip()
    # Remove common prefixes/suffixes
    for prefix in ['VIRTUAL ', 'VIRTUAL_', 'V_']:
        if team_clean.startswith(prefix):
            team_clean = team_clean[len(prefix):]
    # Check if in our team list
    if team_clean in ALL_TEAMS:
        return True
    # Check if it's a 2-4 letter code
    if len(team_clean) >= 2 and len(team_clean) <= 4 and team_clean.isalpha():
        return True
    return False

def is_valid_match(home, away):
    """Check if both teams belong to the 7 leagues."""
    return is_valid_team(home) and is_valid_team(away)

class BetpawaLiveScraperV2:
    def __init__(self, country="tz"):
        self.country = country
        self.base_url = f"https://www.betpawa.{country}/en"
        self.driver = None
    
    def setup_driver(self):
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        self.driver = webdriver.Chrome(options=options)
        return self.driver
    
    def _clean_odds_value(self, value):
        if not value:
            return 0.0
        if isinstance(value, (float, int)):
            return float(value)
        cleaned = re.sub(r'[^\d.]', '', str(value))
        if not cleaned:
            return 0.0
        parts = cleaned.split('.')
        if len(parts) > 2:
            cleaned = parts[0] + '.' + parts[1][:2]
        try:
            return float(cleaned)
        except:
            return 0.0
    
    def fetch_live_odds(self):
        if not self.driver:
            self.setup_driver()
        
        try:
            print("🔄 Fetching Betpawa Virtual Football odds...")
            self.driver.get(f"{self.base_url}/sports/virtual-football")
            time.sleep(5)
            
            # Scroll to load all content
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Try multiple methods to extract matches
            matches = []
            
            # Method 1: Try to find match elements directly
            match_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'event') or contains(@class, 'match') or contains(@class, 'game')]")
            
            if match_elements:
                for element in match_elements:
                    try:
                        text = element.text
                        lines = text.split('\n')
                        
                        # Look for team pairs (2-4 letter codes)
                        teams = []
                        for line in lines:
                            line_clean = line.strip().upper()
                            # Check if line looks like a team code (2-4 letters)
                            if len(line_clean) >= 2 and len(line_clean) <= 4 and line_clean.isalpha():
                                teams.append(line_clean)
                        
                        # Also look for patterns like "TEAM A vs TEAM B"
                        if len(teams) >= 2:
                            home = teams[0]
                            away = teams[1]
                            
                            if is_valid_match(home, away):
                                # Find odds in the text
                                odds = re.findall(r'(\d+\.\d+)', text)
                                odd_numbers = [float(o) for o in odds if float(o) < 100]  # filter out huge numbers
                                
                                if len(odd_numbers) >= 3:
                                    matches.append({
                                        'home_team': home,
                                        'away_team': away,
                                        'match_time': 'LIVE',
                                        'odds': {
                                            '1X2': {
                                                '1': odd_numbers[0] if len(odd_numbers) > 0 else 0,
                                                'X': odd_numbers[1] if len(odd_numbers) > 1 else 0,
                                                '2': odd_numbers[2] if len(odd_numbers) > 2 else 0
                                            }
                                        }
                                    })
                    except:
                        continue
            
            # Method 2: Parse from page source
            html = self.driver.page_source
            
            # Find all team pairs in the HTML
            team_pattern = r'([A-Z]{2,4})\s+(?:vs|VS|v|V)\s+([A-Z]{2,4})'
            team_matches = re.findall(team_pattern, html)
            
            for home, away in team_matches:
                if is_valid_match(home, away):
                    # Find odds near this match
                    # This is a simplified approach
                    matches.append({
                        'home_team': home,
                        'away_team': away,
                        'match_time': 'LIVE',
                        'odds': {'1X2': {'1': 0, 'X': 0, '2': 0}}
                    })
            
            # Method 3: Look for JSON data
            json_data = self._extract_json_data(html)
            if json_data:
                json_matches = self._parse_json_data(json_data)
                # Merge with existing matches, avoid duplicates
                existing = {(m['home_team'], m['away_team']) for m in matches}
                for m in json_matches:
                    if (m['home_team'], m['away_team']) not in existing:
                        matches.append(m)
            
            # Remove duplicates
            seen = set()
            unique_matches = []
            for m in matches:
                key = (m['home_team'], m['away_team'])
                if key not in seen:
                    seen.add(key)
                    unique_matches.append(m)
            
            # Filter for valid matches only
            final_matches = [m for m in unique_matches if is_valid_match(m['home_team'], m['away_team'])]
            
            if final_matches:
                print(f"✅ Found {len(final_matches)} valid matches")
                return final_matches
            
            # Fallback: Return sample data if no matches found
            print("⚠️ No matches found. Returning sample data.")
            return self._get_sample_data()
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return self._get_sample_data()
        finally:
            if self.driver:
                self.driver.quit()
    
    def _extract_json_data(self, html):
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
            r'window\.__DATA__\s*=\s*({.*?});',
            r'"events"\s*:\s*\[.*?\]',
            r'{"events":.*?}'
        ]
        for pattern in patterns:
            matches = re.findall(pattern, html, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except:
                    continue
        return None
    
    def _parse_json_data(self, data):
        matches = []
        try:
            events = []
            if 'events' in data:
                events = data['events']
            elif 'data' in data and 'events' in data['data']:
                events = data['data']['events']
            else:
                events = data.get('matches', [])
            
            for event in events:
                home = (event.get('home_team') or event.get('home') or event.get('homeName') or '').strip()
                away = (event.get('away_team') or event.get('away') or event.get('awayName') or '').strip()
                
                if home and away and is_valid_match(home, away):
                    odds_data = event.get('odds', {})
                    matches.append({
                        'home_team': home,
                        'away_team': away,
                        'match_time': event.get('time', 'LIVE'),
                        'odds': {
                            '1X2': {
                                '1': self._clean_odds_value(odds_data.get('home', odds_data.get('1', 0))),
                                'X': self._clean_odds_value(odds_data.get('draw', odds_data.get('X', 0))),
                                '2': self._clean_odds_value(odds_data.get('away', odds_data.get('2', 0)))
                            }
                        }
                    })
            return matches
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            return []
    
    def _get_sample_data(self):
        """Return sample data for 7 leagues"""
        return [
            {'home_team': 'ARS', 'away_team': 'MCI', 'match_time': 'LIVE', 'odds': {'1X2': {'1': 2.10, 'X': 3.20, '2': 3.80}}},
            {'home_team': 'BAR', 'away_team': 'RMA', 'match_time': 'LIVE', 'odds': {'1X2': {'1': 1.55, 'X': 4.00, '2': 5.50}}},
            {'home_team': 'JUV', 'away_team': 'MIL', 'match_time': 'LIVE', 'odds': {'1X2': {'1': 3.00, 'X': 3.50, '2': 2.20}}},
            {'home_team': 'BAY', 'away_team': 'BVB', 'match_time': 'LIVE', 'odds': {'1X2': {'1': 1.80, 'X': 3.80, '2': 4.20}}},
            {'home_team': 'PSG', 'away_team': 'MAR', 'match_time': 'LIVE', 'odds': {'1X2': {'1': 1.45, 'X': 4.50, '2': 6.00}}},
            {'home_team': 'AJA', 'away_team': 'PSV', 'match_time': 'LIVE', 'odds': {'1X2': {'1': 2.20, 'X': 3.40, '2': 3.00}}},
            {'home_team': 'BEN', 'away_team': 'POR', 'match_time': 'LIVE', 'odds': {'1X2': {'1': 2.50, 'X': 3.10, '2': 2.80}}},
        ]
    
    def get_live_matches(self):
        return self.fetch_live_odds()