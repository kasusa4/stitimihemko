# utils/prediction_boost.py
from collections import defaultdict
import numpy as np

class LeakyDefenseDetector:
    """
    Detects when BOTH teams conceded many goals in previous match.
    Also detects when a team conceded 3+ goals in last match.
    """
    def __init__(self, threshold=3, window=1):
        self.threshold = threshold
        self.window = window
        self.last_conceded = {}
        self.last_goals_scored = {}
        self.conceded_history = defaultdict(list)
        self.goals_scored_history = defaultdict(list)
    
    def add_match(self, home, away, ft_h, ft_a):
        """Store match data for analysis"""
        self.last_conceded[home] = ft_a
        self.last_conceded[away] = ft_h
        self.last_goals_scored[home] = ft_h
        self.last_goals_scored[away] = ft_a
        
        self.conceded_history[home].append(ft_a)
        self.conceded_history[away].append(ft_h)
        self.goals_scored_history[home].append(ft_h)
        self.goals_scored_history[away].append(ft_a)
        
        # Keep last 5 matches
        if len(self.conceded_history[home]) > 5:
            self.conceded_history[home] = self.conceded_history[home][-5:]
        if len(self.conceded_history[away]) > 5:
            self.conceded_history[away] = self.conceded_history[away][-5:]
        if len(self.goals_scored_history[home]) > 5:
            self.goals_scored_history[home] = self.goals_scored_history[home][-5:]
        if len(self.goals_scored_history[away]) > 5:
            self.goals_scored_history[away] = self.goals_scored_history[away][-5:]
    
    def get_avg_conceded(self, team):
        history = self.conceded_history.get(team, [])
        return np.mean(history) if history else 0
    
    def get_avg_scored(self, team):
        history = self.goals_scored_history.get(team, [])
        return np.mean(history) if history else 0
    
    def get_last_conceded(self, team):
        return self.last_conceded.get(team, 0)
    
    def get_last_scored(self, team):
        return self.last_goals_scored.get(team, 0)
    
    def analyze_match(self, home, away):
        """
        Analyzes if both teams have leaky defenses.
        Returns: dict with boosts and warnings
        """
        result = {
            "home_leaky": False,
            "away_leaky": False,
            "both_leaky": False,
            "home_high_scoring": False,
            "away_high_scoring": False,
            "over25_boost": 0,
            "btts_boost": 0,
            "warning": None,
            "prediction_hint": None,
            "massacre_detected": False
        }
        
        # Get last match data
        home_last_conceded = self.get_last_conceded(home)
        away_last_conceded = self.get_last_conceded(away)
        home_last_scored = self.get_last_scored(home)
        away_last_scored = self.get_last_scored(away)
        
        # Get averages
        home_avg_conceded = self.get_avg_conceded(home)
        away_avg_conceded = self.get_avg_conceded(away)
        home_avg_scored = self.get_avg_scored(home)
        away_avg_scored = self.get_avg_scored(away)
        
        # ----- LEAKY DEFENSE DETECTION -----
        if home_last_conceded >= self.threshold or home_avg_conceded >= 2.0:
            result["home_leaky"] = True
        if away_last_conceded >= self.threshold or away_avg_conceded >= 2.0:
            result["away_leaky"] = True
        
        # ----- HIGH SCORING DETECTION -----
        if home_avg_scored >= 1.5 or home_last_scored >= 2:
            result["home_high_scoring"] = True
        if away_avg_scored >= 1.5 or away_last_scored >= 2:
            result["away_high_scoring"] = True
        
        # ----- MASSACRE DETECTION (conceded 5+ goals) -----
        if home_last_conceded >= 5:
            result["massacre_detected"] = True
            result["warning"] = f"🔥 {home} was MASSACRED ({home_last_conceded} goals conceded) last match!"
        if away_last_conceded >= 5:
            result["massacre_detected"] = True
            if result["warning"]:
                result["warning"] += f" {away} also conceded {away_last_conceded} goals!"
            else:
                result["warning"] = f"🔥 {away} was MASSACRED ({away_last_conceded} goals conceded) last match!"
        
        # ----- BOTH LEAKY = OVER 2.5 BOOST -----
        if result["home_leaky"] and result["away_leaky"]:
            result["both_leaky"] = True
            result["over25_boost"] = 0.25  # 25% boost for Over 2.5
            result["btts_boost"] = 0.20
            warning = f"🔥 BOTH TEAMS HAVE LEAKY DEFENSES! "
            warning += f"{home} conceded {home_last_conceded} goals last match"
            warning += f" (avg {home_avg_conceded:.1f}), "
            warning += f"{away} conceded {away_last_conceded} goals last match"
            warning += f" (avg {away_avg_conceded:.1f})."
            result["warning"] = warning
            result["prediction_hint"] = f"⚽ EXPECT GOALS! Over 2.5 is HIGHLY PROBABLE."
        
        # ----- HIGH SCORING BOTH = OVER 2.5 BOOST -----
        elif result["home_high_scoring"] and result["away_high_scoring"]:
            result["over25_boost"] = 0.15
            result["btts_boost"] = 0.10
            result["warning"] = f"⚽ BOTH TEAMS ARE HIGH SCORING! {home} avg {home_avg_scored:.1f} goals, {away} avg {away_avg_scored:.1f} goals."
            result["prediction_hint"] = f"📊 High scoring match expected! Over 2.5 likely."
        
        # ----- ONE LEAKY + ONE HIGH SCORING -----
        elif (result["home_leaky"] and result["away_high_scoring"]) or (result["away_leaky"] and result["home_high_scoring"]):
            result["over25_boost"] = 0.12
            result["btts_boost"] = 0.08
            if not result["warning"]:
                result["warning"] = f"⚡ Leaky defense meets high scoring team! Goals expected."
            result["prediction_hint"] = f"📈 Good chance of goals. Over 2.5 is a solid bet."
        
        # ----- SINGLE LEAKY = SMALL BOOST -----
        elif result["home_leaky"] or result["away_leaky"]:
            result["over25_boost"] = 0.05
            result["btts_boost"] = 0.03
            if not result["warning"]:
                leaky_team = home if result["home_leaky"] else away
                result["warning"] = f"⚠️ {leaky_team} has a leaky defense."
        
        # ----- AVERAGE GOALS HIGH -----
        total_avg_goals = home_avg_scored + away_avg_scored + home_avg_conceded + away_avg_conceded
        if total_avg_goals >= 4.0:
            result["over25_boost"] = max(result["over25_boost"], 0.10)
            if not result["warning"]:
                result["warning"] = f"📊 Combined average goals: {total_avg_goals:.1f}. Expect goals!"
        
        # ----- MASSACRE BOOST -----
        if result["massacre_detected"]:
            result["over25_boost"] += 0.10
            result["btts_boost"] += 0.05
            if result["warning"]:
                result["warning"] += " Expect either a collapse or a fightback with goals!"
        
        # Clamp boosts
        result["over25_boost"] = min(result["over25_boost"], 0.40)
        result["btts_boost"] = min(result["btts_boost"], 0.30)
        
        return result


class FormTrendDetector:
    """
    Detects if a team is on upward, downward, or stable trend.
    """
    def __init__(self, window=5):
        self.window = window
        self.results_history = defaultdict(list)
        self.goals_history = defaultdict(list)
    
    def add_match(self, team, result, goals_scored, goals_conceded):
        """result: 'W', 'D', 'L'"""
        self.results_history[team].append(result)
        self.goals_history[team].append((goals_scored, goals_conceded))
        
        if len(self.results_history[team]) > self.window:
            self.results_history[team] = self.results_history[team][-self.window:]
            self.goals_history[team] = self.goals_history[team][-self.window:]
    
    def get_trend(self, team):
        """
        Returns: ('up', 'down', 'stable', 'unknown')
        """
        results = self.results_history.get(team, [])
        if len(results) < 3:
            return 'unknown'
        
        # Points: W=3, D=1, L=0
        points = [3 if r == 'W' else 1 if r == 'D' else 0 for r in results]
        
        if len(points) >= 4:
            recent = sum(points[-2:])
            previous = sum(points[-4:-2])
            
            if recent > previous:
                return 'up'
            elif recent < previous:
                return 'down'
            else:
                return 'stable'
        return 'unknown'
    
    def get_form_string(self, team):
        """Returns form string like 'W L D W W'"""
        results = self.results_history.get(team, [])
        return ' '.join(results[-5:][::-1]) if results else 'N/A'
    
    def get_form_score(self, team):
        """Returns points from last 5 matches"""
        results = self.results_history.get(team, [])
        points = [3 if r == 'W' else 1 if r == 'D' else 0 for r in results[-5:]]
        return sum(points)


class CorrectScorePredictor:
    """
    Predicts top 3 most likely exact scores.
    """
    @staticmethod
    def predict(home_lambda, away_lambda, top_n=3):
        """
        Returns top N most likely exact scores with probabilities.

        """
        from scipy.stats import poisson
        
        scores = []
        max_score = 6
        for h in range(max_score + 1):
            for a in range(max_score + 1):
                prob = poisson.pmf(h, home_lambda) * poisson.pmf(a, away_lambda)
                scores.append((f"{h}-{a}", prob))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        
        result = []
        for score, prob in scores[:top_n]:
            result.append(f"{score} ({prob*100:.1f}%)")
        
        return result