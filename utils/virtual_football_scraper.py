# utils/virtual_football_scraper.py
import requests
from bs4 import BeautifulSoup
import json
import re
import time
from datetime import datetime

class VirtualFootballScraper:
    """
    Scraper for Betpawa Virtual Football odds.
    Extracts: 1X2, BTTS, Double Chance, HT/FT
    """
    
    def __init__(self, country="tz"):
        self.country = country
        self.base_url = f"https://www.betpawa.{country}/en"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        self.virtual_odds = []
    
    def fetch_virtual_odds(self):
        """
        Fetch all virtual football matches with full odds.
        """
        matches = []
        
        try:
            # Virtual football URL
            url = f"{self.base_url}/sports/virtual-football"
            response = self.session.get(url)
            
            if response.status_code != 200:
                print(f"Error: {response.status_code}")
                return matches
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all virtual match containers
            match_containers = soup.find_all('div', class_=re.compile(r'(event|match|virtual|game)'))
            
            for container in match_containers:
                try:
                    # Extract team names
                    home = container.find('span', class_=re.compile(r'(home|team1|first)'))
                    away = container.find('span', class_=re.compile(r'(away|team2|second)'))
                    
                    if not home or not away:
                        continue
                    
                    home_team = home.text.strip()
                    away_team = away.text.strip()
                    
                    # Extract all markets
                    odds_data = self._extract_all_odds(container)
                    
                    if any(odds_data.values()):
                        match_data = {
                            'home_team': home_team,
                            'away_team': away_team,
                            'match_time': self._extract_match_time(container),
                            'odds': odds_data,
                            'timestamp': datetime.now().isoformat()
                        }
                        matches.append(match_data)
                        
                except Exception as e:
                    print(f"Error parsing match: {e}")
                    continue
            
            # If no matches found, try API approach
            if not matches:
                matches = self._fetch_via_api()
            
            self.virtual_odds = matches
            return matches
            
        except Exception as e:
            print(f"Error: {e}")
            return matches
    
    def _extract_all_odds(self, container):
        """
        Extract all odds markets from a match container.
        Returns dict with 1X2, BTTS, DC, HT/FT.
        """
        odds = {
            '1X2': {},
            'BTTS': {},
            'DC': {},
            'HT/FT': {}
        }
        
        # ------ 1X2 ODDS ------
        # Home Win (1)
        home_win = self._find_odds(container, ['1', 'home', 'h'])
        if home_win:
            odds['1X2']['1'] = home_win
        
        # Draw (X)
        draw = self._find_odds(container, ['X', 'draw'])
        if draw:
            odds['1X2']['X'] = draw
        
        # Away Win (2)
        away_win = self._find_odds(container, ['2', 'away', 'a'])
        if away_win:
            odds['1X2']['2'] = away_win
        
        # ------ BTTS ODDS ------
        # BTTS Yes
        btts_yes = self._find_odds(container, ['btts_yes', 'gg', 'both_yes'])
        if btts_yes:
            odds['BTTS']['Yes'] = btts_yes
        
        # BTTS No
        btts_no = self._find_odds(container, ['btts_no', 'ng', 'both_no'])
        if btts_no:
            odds['BTTS']['No'] = btts_no
        
        # ------ DOUBLE CHANCE ODDS ------
        # 1X (Home or Draw)
        dc_1x = self._find_odds(container, ['1X', 'home_draw', 'h_d'])
        if dc_1x:
            odds['DC']['1X'] = dc_1x
        
        # X2 (Draw or Away)
        dc_x2 = self._find_odds(container, ['X2', 'draw_away', 'd_a'])
        if dc_x2:
            odds['DC']['X2'] = dc_x2
        
        # 12 (Home or Away - No Draw)
        dc_12 = self._find_odds(container, ['12', 'home_away', 'h_a'])
        if dc_12:
            odds['DC']['12'] = dc_12
        
        # ------ HT/FT ODDS ------
        # HT/FT combinations
        htft_combinations = [
            ('H/H', 'home_home', '1/1'),
            ('D/D', 'draw_draw', 'X/X'),
            ('A/A', 'away_away', '2/2'),
            ('H/D', 'home_draw', '1/X'),
            ('H/A', 'home_away', '1/2'),
            ('D/H', 'draw_home', 'X/1'),
            ('D/A', 'draw_away', 'X/2'),
            ('A/H', 'away_home', '2/1'),
            ('A/D', 'away_draw', '2/X'),
        ]
        
        for htft_code, class1, class2 in htft_combinations:
            odd = self._find_odds(container, [class1, class2, htft_code])
            if odd:
                odds['HT/FT'][htft_code] = odd
        
        return odds
    
    def _find_odds(self, container, keywords):
        """
        Find odds for a specific selection.
        """
        for keyword in keywords:
            # Search by class
            elements = container.find_all(class_=re.compile(keyword, re.IGNORECASE))
            for el in elements:
                odd_text = el.text.strip()
                try:
                    return float(odd_text)
                except:
                    pass
            
            # Search by data attribute
            elements = container.find_all(attrs={re.compile(keyword, re.IGNORECASE): True})
            for el in elements:
                odd_text = el.text.strip()
                try:
                    return float(odd_text)
                except:
                    pass
            
            # Search by text content
            elements = container.find_all(string=re.compile(keyword, re.IGNORECASE))
            for el in elements:
                parent = el.parent
                if parent:
                    odd_span = parent.find('span', class_=re.compile(r'(odd|price)'))
                    if odd_span:
                        try:
                            return float(odd_span.text.strip())
                        except:
                            pass
        
        return None
    
    def _extract_match_time(self, container):
        """
        Extract match time or scheduled time.
        """
        time_patterns = [r'\d{2}:\d{2}', r'\d+ min', r'\d+']
        text = container.text
        
        for pattern in time_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group()
        
        return "LIVE"
    
    def _fetch_via_api(self):
        """
        Fallback: Try to fetch via API/JSON if available.
        """
        try:
            api_url = f"{self.base_url}/api/virtual-football"
            response = self.session.get(api_url, headers={'Accept': 'application/json'})
            if response.status_code == 200:
                data = response.json()
                return self._parse_api_response(data)
        except:
            pass
        
        return []
    
    def _parse_api_response(self, data):
        """
        Parse JSON API response.
        Structure depends on Betpawa's actual API format.
        """
        matches = []
        # This would need to be customized
        return matches
    
    def get_all_markets(self):
        """
        Get all matches with their full odds structure.
        """
        return self.fetch_virtual_odds()


# ---------- MOCK DATA FOR TESTING ----------
def get_mock_virtual_data():
    """Mock virtual football data for testing."""
    return [
        {
            'home_team': 'Virtual Team A',
            'away_team': 'Virtual Team B',
            'match_time': '15:30',
            'odds': {
                '1X2': {
                    '1': 2.10,
                    'X': 3.20,
                    '2': 3.80
                },
                'BTTS': {
                    'Yes': 1.85,
                    'No': 1.95
                },
                'DC': {
                    '1X': 1.25,
                    'X2': 1.70,
                    '12': 1.35
                },
                'HT/FT': {
                    'H/H': 2.80,
                    'D/D': 4.50,
                    'A/A': 6.00,
                    'H/D': 15.00,
                    'H/A': 34.00,
                    'D/H': 17.00,
                    'D/A': 19.00,
                    'A/H': 29.00,
                    'A/D': 15.00
                }
            }
        },
        {
            'home_team': 'Virtual Team C',
            'away_team': 'Virtual Team D',
            'match_time': '16:00',
            'odds': {
                '1X2': {
                    '1': 1.55,
                    'X': 4.00,
                    '2': 5.50
                },
                'BTTS': {
                    'Yes': 2.05,
                    'No': 1.75
                },
                'DC': {
                    '1X': 1.12,
                    'X2': 2.30,
                    '12': 1.20
                },
                'HT/FT': {
                    'H/H': 2.10,
                    'D/D': 5.00,
                    'A/A': 8.00,
                    'H/D': 17.00,
                    'H/A': 41.00,
                    'D/H': 18.00,
                    'D/A': 21.00,
                    'A/H': 34.00,
                    'A/D': 17.00
                }
            }
        }
    ]