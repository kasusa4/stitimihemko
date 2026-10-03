# utils/virtual_odds_api.py
import requests
import re
import pandas as pd
from datetime import datetime

class VirtualOddsAPI:
    def __init__(self, country="co.tz"):
        self.country = country
        self.base_url = f"https://www.betpawa.{country}"
        self.headers = {
            'accept': 'application/json',  # Try JSON instead of protobuf
            'accept-language': 'en-US,en;q=0.9',
            'devicetype': 'web',
            'referer': f'https://www.betpawa.{country}/virtual-sports?virtualTab=upcoming&leagueId=7794',
            'sec-ch-ua': '"Microsoft Edge";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0',
            'x-pawa-brand': f'betpawa-{country}',
            'x-pawa-language': 'en'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_current_season(self):
        """Get the current season/round info"""
        try:
            url = f"{self.base_url}/api/sportsbook/virtual/v2/seasons/list/actual"
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                return data
            else:
                # Fallback: try to get from HTML
                return self._get_season_from_html()
        except Exception as e:
            print(f"Error getting season: {e}")
            return self._get_season_from_html()
    
    def _get_season_from_html(self):
        """Fallback: extract season from HTML"""
        try:
            url = f"{self.base_url}/virtual-sports?virtualTab=upcoming&leagueId=7794"
            response = self.session.get(url)
            if response.status_code == 200:
                # Look for matchday in HTML
                match = re.search(r'Matchday\s*(\d+)', response.text)
                if match:
                    return {'round_id': match.group(1), 'matchday': match.group(1)}
        except:
            pass
        return {'round_id': '1', 'matchday': '1'}
    
    def get_round_matches(self, round_id):
        """Get all matches for a specific round"""
        try:
            # Try JSON first
            url = f"{self.base_url}/api/sportsbook/virtual/v3/events/list/by-round/{round_id}"
            response = self.session.get(url)
            
            if response.status_code == 200:
                # Try to parse as JSON
                try:
                    data = response.json()
                    return self._parse_json_matches(data)
                except:
                    # If not JSON, try to parse text
                    return self._parse_text_matches(response.text)
            else:
                return []
        except Exception as e:
            print(f"Error getting matches: {e}")
            return []
    
    def _parse_json_matches(self, data):
        """Parse matches from JSON response"""
        matches = []
        try:
            events = data.get('events', [])
            for event in events:
                home = event.get('homeTeam', {}).get('name', 'Unknown')
                away = event.get('awayTeam', {}).get('name', 'Unknown')
                odds = event.get('odds', {})
                
                match = {
                    'home_team': home,
                    'away_team': away,
                    'league': event.get('leagueName', 'Unknown'),
                    'match_time': 'Upcoming',
                    'odds': {
                        '1X2': {
                            '1': odds.get('home', 0),
                            'X': odds.get('draw', 0),
                            '2': odds.get('away', 0)
                        }
                    }
                }
                matches.append(match)
        except:
            pass
        return matches
    
    def _parse_text_matches(self, text):
        """Fallback: parse matches from text if JSON fails"""
        matches = []
        
        # Find all team pairs and odds
        pattern = r'([A-Z]{2,4})\s*[-–—]\s*([A-Z]{2,4}).*?(?:1\s+([\d.]+)\s+X\s+([\d.]+)\s+2\s+([\d.]+))'
        raw_matches = re.findall(pattern, text, re.DOTALL)
        
        for home, away, home_odd, draw_odd, away_odd in raw_matches:
            try:
                home_odd = float(home_odd)
                draw_odd = float(draw_odd)
                away_odd = float(away_odd)
                if 1.0 <= home_odd <= 10.0 and 1.0 <= draw_odd <= 10.0 and 1.0 <= away_odd <= 10.0:
                    matches.append({
                        'home_team': home,
                        'away_team': away,
                        'league': 'Unknown',
                        'match_time': 'Upcoming',
                        'odds': {
                            '1X2': {
                                '1': home_odd,
                                'X': draw_odd,
                                '2': away_odd
                            }
                        }
                    })
            except:
                continue
        
        return matches
    
    def fetch_matchday_odds(self):
        """Main method: fetch all matchday odds"""
        print("🔄 Fetching current season...")
        
        # Get the current round
        season_data = self.get_current_season()
        round_id = season_data.get('round_id', '1')
        matchday = season_data.get('matchday', '1')
        
        print(f"📅 Matchday: {matchday}")
        
        # Get matches for this round
        matches = self.get_round_matches(round_id)
        
        if matches:
            for match in matches:
                match['matchday'] = int(matchday)
            print(f"✅ Found {len(matches)} matches")
            self._save_csv(matches)
            self._print_summary(matches)
            return matches
        else:
            print("⚠️ No matches found via API. Falling back to HTML parsing...")
            return self._fetch_via_selenium()
    
    def _fetch_via_selenium(self):
        """Fallback to Selenium if API fails"""
        try:
            from utils.matchday_odds_scraper import MatchdayOddsScraper
            scraper = MatchdayOddsScraper()
            return scraper.fetch_matchday_odds()
        except:
            return self._get_sample_data()
    
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


# If run directly
if __name__ == "__main__":
    api = VirtualOddsAPI()
    matches = api.get_matchday_predictions()
    print(f"Found {len(matches)} matches")