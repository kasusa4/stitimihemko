# utils/betpawa_scraper.py
import requests
from bs4 import BeautifulSoup
import json
import time
import re
from datetime import datetime

class BetpawaScraper:
    def __init__(self, country="tz"):
        """
        Initialize Betpawa scraper for a specific country.
        Countries: tz (Tanzania), ke (Kenya), ug (Uganda), gh (Ghana), ng (Nigeria), zm (Zambia)
        """
        self.country = country
        self.base_url = f"https://www.betpawa.{country}/en"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def get_live_matches(self):
        """
        Fetch all live matches with current scores and available odds.
        """
        matches = []
        
        try:
            # First, get the live events page
            url = f"{self.base_url}/sports/live"
            response = self.session.get(url)
            
            if response.status_code != 200:
                print(f"Error: Status code {response.status_code}")
                return matches
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all match containers (adjust selectors based on actual Betpawa structure)
            # Betpawa uses specific class names – we'll try multiple patterns
            match_containers = soup.find_all('div', class_=re.compile(r'(event|match|game|fixture)'))
            
            for container in match_containers:
                try:
                    # Extract team names
                    home = container.find('span', class_=re.compile(r'(home|team1|first)'))
                    away = container.find('span', class_=re.compile(r'(away|team2|second)'))
                    
                    if not home or not away:
                        continue
                    
                    home_team = home.text.strip()
                    away_team = away.text.strip()
                    
                    # Extract score
                    score_h = container.find('span', class_=re.compile(r'(score-home|home-score|score1)'))
                    score_a = container.find('span', class_=re.compile(r'(score-away|away-score|score2)'))
                    
                    score = "0-0"
                    if score_h and score_a:
                        score = f"{score_h.text.strip()}-{score_a.text.strip()}"
                    
                    # Extract Over 2.5 odds
                    over25_odds = self._extract_odds(container, 'over', '2.5')
                    
                    # Extract BTTS odds (Yes)
                    btts_odds = self._extract_odds(container, 'btts', 'yes')
                    
                    # Extract 1X2 odds
                    home_odds = self._extract_odds(container, '1', '')
                    draw_odds = self._extract_odds(container, 'X', '')
                    away_odds = self._extract_odds(container, '2', '')
                    
                    # Extract match time (if live, it shows elapsed minutes)
                    time_element = container.find('span', class_=re.compile(r'(time|minute|elapsed)'))
                    match_time = time_element.text.strip() if time_element else "LIVE"
                    
                    match_data = {
                        'home_team': home_team,
                        'away_team': away_team,
                        'score': score,
                        'time': match_time,
                        'over25_odds': over25_odds,
                        'btts_odds': btts_odds,
                        'home_odds': home_odds,
                        'draw_odds': draw_odds,
                        'away_odds': away_odds,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    # Only add matches that have at least one available odd
                    if any([over25_odds, btts_odds, home_odds, draw_odds, away_odds]):
                        matches.append(match_data)
                        
                except Exception as e:
                    print(f"Error parsing match: {e}")
                    continue
            
            # Alternative method: Check if data is loaded via JavaScript/API
            if not matches:
                # Try to find the initial state data (Betpawa often embeds JSON)
                script_tags = soup.find_all('script')
                for script in script_tags:
                    if script.string and '__INITIAL_STATE__' in script.string:
                        try:
                            # Extract the JSON data
                            json_text = script.string
                            start = json_text.find('{')
                            end = json_text.rfind('}') + 1
                            if start >= 0 and end > start:
                                data = json.loads(json_text[start:end])
                                # Parse from the JSON structure if available
                                matches = self._parse_json_data(data)
                        except:
                            pass
        
        except Exception as e:
            print(f"Error fetching matches: {e}")
        
        return matches
    
    def _extract_odds(self, container, market, selection):
        """
        Extract odds for a specific market and selection.
        """
        # Try various patterns for odds
        patterns = [
            f"data-{market}-{selection}",
            f"data-{market}",
            f"odds-{market}-{selection}",
            f"sel-{selection}",
        ]
        
        for pattern in patterns:
            element = container.find('span', attrs={pattern: True})
            if element:
                odds_text = element.text.strip()
                try:
                    return float(odds_text)
                except:
                    pass
        
        # Try finding by text content
        if market == 'over' and selection == '2.5':
            # Look for text containing "Over 2.5"
            elements = container.find_all('span')
            for el in elements:
                if 'Over 2.5' in el.text or 'O 2.5' in el.text:
                    # Find the odds next to it
                    parent = el.parent
                    if parent:
                        odds_span = parent.find('span', class_=re.compile(r'(odds|price)'))
                        if odds_span:
                            try:
                                return float(odds_span.text.strip())
                            except:
                                pass
        
        return None
    
    def _parse_json_data(self, data):
        """
        Parse Betpawa's embedded JSON data if available.
        """
        matches = []
        # This would need to be customized based on Betpawa's actual JSON structure
        # I'll keep it as a template for now
        return matches
    
    def get_all_matches(self):
        """
        Get all matches (live and upcoming) for display.
        """
        live = self.get_live_matches()
        upcoming = self.get_upcoming_matches()
        return live + upcoming
    
    def get_upcoming_matches(self):
        """
        Fetch upcoming matches with pre-match odds.
        """
        matches = []
        try:
            url = f"{self.base_url}/sports/football"
            response = self.session.get(url)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                # Similar parsing logic for upcoming matches
                # ...
        except:
            pass
        
        return matches