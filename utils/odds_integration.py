# utils/odds_integration.py
import time
import pandas as pd
from datetime import datetime

class OddsIntegration:
    def __init__(self, use_scraper=True):
        self.use_scraper = use_scraper
        self.last_fetch = None
        self.cached_matches = []
        
        if use_scraper:
            from utils.betpawa_scraper import BetpawaScraper
            self.scraper = BetpawaScraper(country="tz")  # Change to your country
    
    def fetch_live_data(self, refresh=False):
        """
        Fetch live data from Betpawa.
        If cache is recent (<30 seconds), use cached data unless refresh=True.
        """
        current_time = datetime.now()
        
        if not refresh and self.last_fetch and (current_time - self.last_fetch).seconds < 30:
            return self.cached_matches
        
        if self.use_scraper:
            try:
                matches = self.scraper.get_live_matches()
                self.cached_matches = matches
                self.last_fetch = current_time
                return matches
            except Exception as e:
                print(f"Error fetching from scraper: {e}")
                return self.cached_matches
        else:
            # Mock data for testing
            return self._get_mock_data()
    
    def _get_mock_data(self):
        """Mock data for testing without real scraping."""
        return [
            {
                'home_team': 'Yanga SC',
                'away_team': 'Simba SC',
                'score': '1-0',
                'time': '35\'',
                'over25_odds': 1.85,
                'btts_odds': 2.10,
                'home_odds': 2.15,
                'draw_odds': 3.20,
                'away_odds': 3.50
            },
            {
                'home_team': 'Young Africans',
                'away_team': 'Azam FC',
                'score': '0-0',
                'time': '15\'',
                'over25_odds': 2.05,
                'btts_odds': 2.30,
                'home_odds': 1.80,
                'draw_odds': 3.40,
                'away_odds': 4.20
            },
            {
                'home_team': 'Maniema Union',
                'away_team': 'TP Mazembe',
                'score': '2-1',
                'time': '62\'',
                'over25_odds': 1.45,
                'btts_odds': 1.90,
                'home_odds': 2.80,
                'draw_odds': 3.10,
                'away_odds': 2.40
            },
            {
                'home_team': 'Al Hilal',
                'away_team': 'Al Ahly',
                'score': '0-2',
                'time': '78\'',
                'over25_odds': 1.55,
                'btts_odds': 2.05,
                'home_odds': 3.50,
                'draw_odds': 3.30,
                'away_odds': 2.00
            },
            {
                'home_team': 'Esperance',
                'away_team': 'USM Alger',
                'score': '1-1',
                'time': '55\'',
                'over25_odds': 1.75,
                'btts_odds': 1.85,
                'home_odds': 2.20,
                'draw_odds': 3.00,
                'away_odds': 3.40
            }
        ]
    
    def combine_with_predictions(self, predictions, live_matches=None):
        """
        Combine APEX predictions with live odds.
        Returns a combined ranking.
        """
        if live_matches is None:
            live_matches = self.fetch_live_data()
        
        combined = []
        
        for live in live_matches:
            home = live['home_team']
            away = live['away_team']
            
            # Find matching prediction (fuzzy match by team names)
            best_match = None
            best_score = 0
            
            for pred in predictions:
                pred_text = pred.get('Match', '')
                # Check if either team appears in the prediction text
                if home.lower() in pred_text.lower() or away.lower() in pred_text.lower():
                    score = 0
                    if home.lower() in pred_text.lower():
                        score += 1
                    if away.lower() in pred_text.lower():
                        score += 1
                    if score > best_score:
                        best_score = score
                        best_match = pred
            
            if best_match and best_score >= 1:
                # Combine APEX over25 with live over25 odds
                apex_over25 = best_match.get('O/U 2.5', '0%')
                try:
                    apex_over25_val = float(apex_over25.replace('%', '')) / 100
                except:
                    apex_over25_val = 0.5
                
                # Convert odds to implied probability
                odds_value = live.get('over25_odds', 0)
                odds_prob = 1 / odds_value if odds_value and odds_value > 0 else 0.5
                
                # Combined confidence: APEX (60%) + Odds (40%)
                combined_conf = (apex_over25_val * 0.6) + (odds_prob * 0.4)
                
                # Determine tier
                if combined_conf >= 0.72:
                    tier = "S : Elite"
                elif combined_conf >= 0.62:
                    tier = "A : High"
                elif combined_conf >= 0.55:
                    tier = "B : Medium"
                else:
                    tier = "RISKY"
                
                # Value check: if odds probability > APEX probability, it's a value bet
                value_bet = odds_prob > apex_over25_val
                
                combined.append({
                    'league': best_match.get('League', 'Unknown'),
                    'match': f"{home} vs {away}",
                    'score': live.get('score', '0-0'),
                    'time': live.get('time', 'LIVE'),
                    'apex_over25': f"{apex_over25_val*100:.1f}%",
                    'odds_over25': odds_value,
                    'odds_prob': f"{odds_prob*100:.1f}%",
                    'combined_confidence': f"{combined_conf*100:.1f}%",
                    'tier': tier,
                    'value_bet': value_bet,
                    'max_confidence': max(apex_over25_val, odds_prob),
                    'min_confidence': min(apex_over25_val, odds_prob)
                })
        
        # Sort by combined confidence
        combined.sort(
            key=lambda x: float(x['combined_confidence'].replace('%', '')),
            reverse=True
        )
        
        return combined