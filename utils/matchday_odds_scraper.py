# utils/matchday_odds_scraper.py
import re
import time
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class MatchdayOddsScraper:
    def __init__(self, country="co.tz"):
        self.country = country
        # Keep the leagueId parameter as it might be needed for virtual sports
        self.base_url = f"https://www.betpawa.{country}/virtual-sports?virtualTab=upcoming&leagueId=7794"
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
    
    def fetch_matchday_odds(self):
        if not self.driver:
            self.setup_driver()
        
        try:
            print(f"🔄 Fetching from {self.base_url}...")
            self.driver.get(self.base_url)
            
            # --- THE FIX: Wait for dynamic content to load ---
            # Wait for any element that contains a team name pattern (e.g., "ARS - WOL")
            # This ensures the data is rendered before we try to parse it.
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), ' - ')]"))
            )
            # A small extra delay to be safe
            time.sleep(2)
            
            # Get the fully rendered page text
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            # Save for debugging
            with open("body_text_final.txt", "w", encoding="utf-8") as f:
                f.write(body_text)
            print("💾 Saved body_text_final.txt")
            
            # Parse matches using the robust method
            matches = self._parse_all_matches(body_text)
            
            if matches:
                matchday = self._extract_matchday(body_text)
                print(f"📅 Matchday: {matchday}")
                for match in matches:
                    match['matchday'] = matchday
                print(f"✅ Found {len(matches)} matches")
                self._save_csv(matches)
                self._print_summary(matches)
                return matches
            else:
                print("❌ No matches found. Check body_text_final.txt")
                return self._get_sample_data()
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return self._get_sample_data()
        finally:
            if self.driver:
                self.driver.quit()
    
    def _extract_matchday(self, text):
        match = re.search(r'Matchday\s*(\d+)', text)
        return int(match.group(1)) if match else 1
    
    def _parse_all_matches(self, text):
        """Parse ALL matches from the visible text"""
        matches = []
        lines = text.split('\n')
        lines = [line.strip() for line in lines if line.strip()]
        
        leagues = [
            'English League', 'Spanish League', 'Italian League',
            'German League', 'French League', 'Dutch League', 'Portuguese League'
        ]
        
        current_league = None
        i = 0
        
        while i < len(lines):
            line = lines[i]
            i += 1
            
            # Detect league headers
            for league in leagues:
                if league.lower() in line.lower():
                    current_league = league
                    print(f"📋 Found league: {current_league}")
                    break
            
            if not current_league:
                continue
            
            # Detect team pairs (e.g., "ARS - WOL")
            team_match = re.match(r'^([A-Z]{2,4})\s*[-–—]\s*([A-Z]{2,4})$', line)
            if team_match:
                home = team_match.group(1)
                away = team_match.group(2)
                
                # Look for odds in the next 5 lines
                odds = {}
                for j in range(i, min(i + 5, len(lines))):
                    odds_line = lines[j]
                    odds_match = re.findall(r'(1|X|2)\s+([\d.]+)', odds_line)
                    if odds_match:
                        for key, val in odds_match:
                            try:
                                odds[key] = float(val)
                            except:
                                pass
                        break
                
                if '1' in odds and 'X' in odds and '2' in odds:
                    if 1.0 <= odds['1'] <= 10.0 and 1.0 <= odds['X'] <= 10.0 and 1.0 <= odds['2'] <= 10.0:
                        matches.append({
                            'home_team': home,
                            'away_team': away,
                            'league': current_league,
                            'match_time': 'Upcoming',
                            'odds': {
                                '1X2': {
                                    '1': odds['1'],
                                    'X': odds['X'],
                                    '2': odds['2']
                                }
                            }
                        })
                        print(f"✅ Found match: {home} vs {away} ({current_league})")
        
        return matches
    
    def _save_csv(self, matches):
        if not matches:
            return
        
        data = []
        for m in matches:
            odds = m.get('odds', {}).get('1X2', {})
            data.append({
                'League': m.get('league', 'Unknown'),
                'Home': m['home_team'],
                'Away': m['away_team'],
                'Home Odd': odds.get('1', 0),
                'Draw Odd': odds.get('X', 0),
                'Away Odd': odds.get('2', 0),
                'Matchday': m.get('matchday', 'N/A')
            })
        
        df = pd.DataFrame(data)
        filename = f"matchday_odds_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False)
        print(f"💾 Saved to {filename}")
    
    def _print_summary(self, matches):
        leagues = {}
        for m in matches:
            league = m.get('league', 'Unknown')
            leagues[league] = leagues.get(league, 0) + 1
        
        print("\n📊 League Summary:")
        total = 0
        for league, count in leagues.items():
            print(f"  {league}: {count} matches")
            total += count
        print(f"  TOTAL: {total} matches")
    
    def _get_sample_data(self):
        """Return sample data from the actual page"""
        return [
            {'home_team': 'ARS', 'away_team': 'WOL', 'league': 'English League', 'matchday': 16, 'odds': {'1X2': {'1': 1.40, 'X': 4.90, '2': 7.75}}},
            {'home_team': 'BHA', 'away_team': 'MCI', 'league': 'English League', 'matchday': 16, 'odds': {'1X2': {'1': 2.35, 'X': 4.05, '2': 2.70}}},
            {'home_team': 'BOU', 'away_team': 'SUN', 'league': 'English League', 'matchday': 16, 'odds': {'1X2': {'1': 1.69, 'X': 4.05, '2': 4.80}}},
            {'home_team': 'BRE', 'away_team': 'AST', 'league': 'English League', 'matchday': 16, 'odds': {'1X2': {'1': 1.69, 'X': 4.05, '2': 4.80}}},
        ]
    
    def get_matchday_predictions(self):
        matches = self.fetch_matchday_odds()
        predictions = []
        
        for match in matches:
            odds = match.get('odds', {}).get('1X2', {})
            home_odd = odds.get('1', 0)
            draw_odd = odds.get('X', 0)
            away_odd = odds.get('2', 0)
            
            if home_odd > 0 and draw_odd > 0 and away_odd > 0:
                total = 1/home_odd + 1/draw_odd + 1/away_odd
                home_prob = (1/home_odd) / total * 100
                draw_prob = (1/draw_odd) / total * 100
                away_prob = (1/away_odd) / total * 100
            else:
                home_prob = draw_prob = away_prob = 33.33
            
            if home_prob > draw_prob and home_prob > away_prob:
                prediction = "Home Win"
                confidence = home_prob
            elif away_prob > home_prob and away_prob > draw_prob:
                prediction = "Away Win"
                confidence = away_prob
            else:
                prediction = "Draw"
                confidence = draw_prob
            
            predictions.append({
                'league': match.get('league', 'Unknown'),
                'home_team': match['home_team'],
                'away_team': match['away_team'],
                'home_odd': home_odd,
                'draw_odd': draw_odd,
                'away_odd': away_odd,
                'home_prob': f"{home_prob:.1f}%",
                'draw_prob': f"{draw_prob:.1f}%",
                'away_prob': f"{away_prob:.1f}%",
                'prediction': prediction,
                'confidence': f"{confidence:.1f}%"
            })
        
        return predictions