# utils/live_odds_connector.py
import pandas as pd
import os

class LiveOddsConnector:
    def __init__(self, csv_path="betpawa_live_odds.csv"):
        self.csv_path = csv_path
    
    def fetch_live_odds(self):
        """Read live odds from CSV"""
        if os.path.exists(self.csv_path):
            try:
                df = pd.read_csv(self.csv_path)
                matches = []
                for _, row in df.iterrows():
                    matches.append({
                        'home_team': row.get('HOME TEAM', 'Unknown'),
                        'away_team': row.get('AWAY TEAM', 'Unknown'),
                        'match_time': row.get('TIME', 'LIVE'),
                        'odds': {
                            '1X2': {
                                '1': float(row.get('HOME ODD', 0)) if row.get('HOME ODD') else 0,
                                'X': float(row.get('DRAW ODD', 0)) if row.get('DRAW ODD') else 0,
                                '2': float(row.get('AWAY ODD', 0)) if row.get('AWAY ODD') else 0
                            }
                        }
                    })
                return matches
            except:
                pass
        return []