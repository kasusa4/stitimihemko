# utils/virtual_odds_integration.py
import pandas as pd
from datetime import datetime

class VirtualOddsIntegration:
    def __init__(self, use_scraper=True):
        self.use_scraper = use_scraper
        self.last_fetch = None
        self.cached_matches = []
        
        if use_scraper:
            try:
                from utils.virtual_football_scraper import VirtualFootballScraper, get_mock_virtual_data
                self.scraper = VirtualFootballScraper()
                self.mock_data = get_mock_virtual_data
            except ImportError:
                print("VirtualFootballScraper not available, using mock data only")
                self.use_scraper = False
                self.mock_data = self._get_mock_data
    
    def fetch_virtual_odds(self, refresh=False):
        """Fetch virtual football odds."""
        current_time = datetime.now()
        
        if not refresh and self.last_fetch and (current_time - self.last_fetch).seconds < 30:
            return self.cached_matches
        
        if self.use_scraper:
            try:
                matches = self.scraper.get_all_markets()
                if matches:
                    self.cached_matches = matches
                    self.last_fetch = current_time
                    return matches
            except Exception as e:
                print(f"Scraper error: {e}")
        
        # Return mock data if no real data available
        self.cached_matches = self._get_mock_data()
        self.last_fetch = current_time
        return self.cached_matches
    
    def _get_mock_data(self):
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
            },
            {
                'home_team': 'Virtual Team E',
                'away_team': 'Virtual Team F',
                'match_time': '16:30',
                'odds': {
                    '1X2': {
                        '1': 3.00,
                        'X': 3.50,
                        '2': 2.20
                    },
                    'BTTS': {
                        'Yes': 1.65,
                        'No': 2.15
                    },
                    'DC': {
                        '1X': 1.50,
                        'X2': 1.35,
                        '12': 1.25
                    },
                    'HT/FT': {
                        'H/H': 4.00,
                        'D/D': 5.50,
                        'A/A': 3.50,
                        'H/D': 18.00,
                        'H/A': 40.00,
                        'D/H': 20.00,
                        'D/A': 22.00,
                        'A/H': 35.00,
                        'A/D': 18.00
                    }
                }
            }
        ]
    
    def convert_to_dataframe(self, matches):
        """Convert virtual matches to a nice dataframe."""
        rows = []
        for m in matches:
            odds = m.get('odds', {})
            
            # Base row
            row = {
                'Home': m['home_team'],
                'Away': m['away_team'],
                'Time': m.get('match_time', 'LIVE'),
            }
            
            # Add 1X2 odds
            for key, val in odds.get('1X2', {}).items():
                row[f'1X2_{key}'] = val
            
            # Add BTTS odds
            for key, val in odds.get('BTTS', {}).items():
                row[f'BTTS_{key}'] = val
            
            # Add DC odds
            for key, val in odds.get('DC', {}).items():
                row[f'DC_{key}'] = val
            
            # Add HT/FT odds
            for key, val in odds.get('HT/FT', {}).items():
                row[f'HTFT_{key}'] = val
            
            rows.append(row)
        
        return pd.DataFrame(rows)
    
    def get_best_odds(self, matches, market_type='1X2', selection=None):
        """Get the best odds for a specific market."""
        best = {}
        for m in matches:
            odds = m.get('odds', {}).get(market_type, {})
            for key, val in odds.items():
                if selection and key != selection:
                    continue
                if key not in best or val > best[key]['odds']:
                    best[key] = {'odds': val, 'match': f"{m['home_team']} vs {m['away_team']}"}
        return best
    
    def calculate_implied_probability(self, odds):
        """Convert odds to implied probability."""
        if odds and odds > 0:
            return 1 / odds
        return 0