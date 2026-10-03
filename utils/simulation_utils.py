# utils/simulation_utils.py
import numpy as np
import pandas as pd
from collections import defaultdict

class LeagueStats:
    def __init__(self, name):
        self.name = name
        # Full-time stats
        self.home_goals_scored_ft = defaultdict(list)
        self.away_goals_scored_ft = defaultdict(list)
        self.home_goals_conceded_ft = defaultdict(list)
        self.away_goals_conceded_ft = defaultdict(list)
        
        # Half-time stats
        self.home_goals_scored_ht = defaultdict(list)
        self.away_goals_scored_ht = defaultdict(list)
        self.home_goals_conceded_ht = defaultdict(list)
        self.away_goals_conceded_ht = defaultdict(list)
        
        # Second-half performance
        self.home_goals_scored_2h = defaultdict(list)
        self.away_goals_scored_2h = defaultdict(list)
        self.home_goals_conceded_2h = defaultdict(list)
        self.away_goals_conceded_2h = defaultdict(list)

    def add_match(self, home, away, ft_h, ft_a, ht_h, ht_a):
        """
        Add a match to the stats database.
        Parameters: home, away, fulltime_home, fulltime_away, halftime_home, halftime_away
        """
        # Full-time stats
        self.home_goals_scored_ft[home].append(ft_h)
        self.away_goals_scored_ft[away].append(ft_a)
        self.home_goals_conceded_ft[home].append(ft_a)
        self.away_goals_conceded_ft[away].append(ft_h)
        
        # Half-time stats
        self.home_goals_scored_ht[home].append(ht_h)
        self.away_goals_scored_ht[away].append(ht_a)
        self.home_goals_conceded_ht[home].append(ht_a)
        self.away_goals_conceded_ht[away].append(ht_h)
        
        # Second-half stats (full-time minus half-time)
        self.home_goals_scored_2h[home].append(ft_h - ht_h)
        self.away_goals_scored_2h[away].append(ft_a - ht_a)
        self.home_goals_conceded_2h[home].append(ft_a - ht_a)
        self.away_goals_conceded_2h[away].append(ft_h - ht_h)

    def get_avg(self, data_dict, team, default=0.8):
        vals = data_dict.get(team, [])
        return np.mean(vals) if vals else default

    def predict_match(self, home, away, patterns=None, simulations=10000):
        """
        Predict a match using Monte Carlo simulation with pattern adjustments.
        """
        # -------- FULL-TIME EXPECTED GOALS --------
        home_attack_ft = self.get_avg(self.home_goals_scored_ft, home)
        away_attack_ft = self.get_avg(self.away_goals_scored_ft, away)
        home_defense_ft = self.get_avg(self.home_goals_conceded_ft, home)
        away_defense_ft = self.get_avg(self.away_goals_conceded_ft, away)
        
        # -------- HALF-TIME EXPECTED GOALS --------
        home_attack_ht = self.get_avg(self.home_goals_scored_ht, home, default=0.3)
        away_attack_ht = self.get_avg(self.away_goals_scored_ht, away, default=0.3)
        home_defense_ht = self.get_avg(self.home_goals_conceded_ht, home, default=0.3)
        away_defense_ht = self.get_avg(self.away_goals_conceded_ht, away, default=0.3)
        
        # -------- SECOND-HALF EXPECTED GOALS --------
        home_attack_2h = self.get_avg(self.home_goals_scored_2h, home, default=0.4)
        away_attack_2h = self.get_avg(self.away_goals_scored_2h, away, default=0.4)
        home_defense_2h = self.get_avg(self.home_goals_conceded_2h, home, default=0.4)
        away_defense_2h = self.get_avg(self.away_goals_conceded_2h, away, default=0.4)
        
        # -------- COMBINE INTO WEIGHTED EXPECTED GOALS --------
        # Weight: Full-time (60%), Half-time (20%), Second-half (20%)
        home_lambda = (
            (home_attack_ft * 0.6 + away_defense_ft * 0.6) / 2 +
            (home_attack_ht * 0.2 + away_defense_ht * 0.2) / 2 +
            (home_attack_2h * 0.2 + away_defense_2h * 0.2) / 2
        )
        
        away_lambda = (
            (away_attack_ft * 0.6 + home_defense_ft * 0.6) / 2 +
            (away_attack_ht * 0.2 + home_defense_ht * 0.2) / 2 +
            (away_attack_2h * 0.2 + home_defense_2h * 0.2) / 2
        )
        
        # -------- APPLY PATTERN ADJUSTMENTS --------
        if patterns:
            for p in patterns:
                if p['type'] == 'winning_streak' and p['team'] == home:
                    home_lambda *= 1.15
                elif p['type'] == 'winning_streak' and p['team'] == away:
                    away_lambda *= 1.15
                elif p['type'] == 'losing_streak' and p['team'] == home:
                    home_lambda *= 0.85
                elif p['type'] == 'losing_streak' and p['team'] == away:
                    away_lambda *= 0.85
                elif p['type'] == 'home_specialist' and p['team'] == home:
                    home_lambda *= 1.10
                elif p['type'] == 'away_specialist' and p['team'] == away:
                    away_lambda *= 1.10
                elif p['type'] == 'high_scoring' and p['team'] == home:
                    home_lambda *= 1.10
                elif p['type'] == 'high_scoring' and p['team'] == away:
                    away_lambda *= 1.10
                elif p['type'] == 'tight_defense' and p['team'] == home:
                    away_lambda *= 0.90
                elif p['type'] == 'tight_defense' and p['team'] == away:
                    home_lambda *= 0.90
        
        # Clamp to reasonable values
        home_lambda = max(home_lambda, 0.3)
        away_lambda = max(away_lambda, 0.3)
        
        # -------- RUN MONTE CARLO SIMULATION --------
        home_wins = 0
        draws = 0
        away_wins = 0
        goals_h = []
        goals_a = []

        for _ in range(simulations):
            h_goals = np.random.poisson(home_lambda)
            a_goals = np.random.poisson(away_lambda)
            goals_h.append(h_goals)
            goals_a.append(a_goals)
            if h_goals > a_goals:
                home_wins += 1
            elif h_goals == a_goals:
                draws += 1
            else:
                away_wins += 1

        # Most likely score
        score_df = pd.DataFrame({'H': goals_h, 'A': goals_a})
        most_likely = score_df.groupby(['H', 'A']).size().idxmax()

        # BTTS and Over 2.5
        btts = sum(1 for h, a in zip(goals_h, goals_a) if h > 0 and a > 0) / simulations
        over25 = sum(1 for h, a in zip(goals_h, goals_a) if h + a >= 3) / simulations

        return {
            "home_win": home_wins / simulations,
            "draw": draws / simulations,
            "away_win": away_wins / simulations,
            "most_likely": f"{most_likely[0]} - {most_likely[1]}",
            "btts": btts,
            "over25": over25,
            "home_lambda": home_lambda,
            "away_lambda": away_lambda
        }

    def get_team_stats(self, team):
        """
        Get detailed stats for a specific team (for debugging/insights)
        """
        return {
            "home_goals_scored_ft": self.home_goals_scored_ft.get(team, []),
            "away_goals_scored_ft": self.away_goals_scored_ft.get(team, []),
            "home_goals_conceded_ft": self.home_goals_conceded_ft.get(team, []),
            "away_goals_conceded_ft": self.away_goals_conceded_ft.get(team, []),
            "home_goals_scored_ht": self.home_goals_scored_ht.get(team, []),
            "away_goals_scored_ht": self.away_goals_scored_ht.get(team, []),
            "home_goals_scored_2h": self.home_goals_scored_2h.get(team, []),
            "away_goals_scored_2h": self.away_goals_scored_2h.get(team, [])
        }
    

    def predict_match_with_boost(self, home, away, leaky_analysis=None, patterns=None, simulations=10000):
        """
        Predict with leaky defense boost applied.
        """
        # Get base prediction
        pred = self.predict_match(home, away, patterns, simulations)
        
        # Apply leaky boost
        if leaky_analysis:
            over25_boost = leaky_analysis.get('over25_boost', 0)
            btts_boost = leaky_analysis.get('btts_boost', 0)
            
            # Boost Over 2.5 and BTTS
            pred['over25'] = min(pred['over25'] + over25_boost, 0.99)
            pred['btts'] = min(pred['btts'] + btts_boost, 0.99)
            
            # Add warnings and hints
            pred['leaky_warning'] = leaky_analysis.get('warning', None)
            pred['leaky_hint'] = leaky_analysis.get('prediction_hint', None)
            pred['over25_boost'] = over25_boost
            pred['btts_boost'] = btts_boost
        
        return pred