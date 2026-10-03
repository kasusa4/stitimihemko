# utils/xgb_predictor.py
import numpy as np
import pandas as pd
from collections import defaultdict

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("⚠️ XGBoost not installed — run: pip install xgboost")

class XGBGoalPredictor:
    """
    Gradient-boosted trees for total goals and match outcome.
    Uses features engineered from recent team history.
    """
    def __init__(self):
        self.history = defaultdict(list)   # team -> [(goals_for, goals_against, points)]
        self.result_history = defaultdict(list)  # team -> [W/D/L]
        self.fitted = False
        self.model_home = None
        self.model_away = None
        self.model_over25 = None

    def add_match(self, home, away, ft_h, ft_a):
        if ft_h > ft_a:
            hp, ap = 3, 0
            hr, ar = 1, 0
        elif ft_h == ft_a:
            hp, ap = 1, 1
            hr, ar = 0.5, 0.5
        else:
            hp, ap = 0, 3
            hr, ar = 0, 1
        self.history[home].append((ft_h, ft_a, hp))
        self.history[away].append((ft_a, ft_h, ap))
        self.result_history[home].append(hr)
        self.result_history[away].append(ar)

    def _team_features(self, team, is_home):
        hist = self.history[team][-6:]   # last 6 matches
        if not hist:
            return [1.0, 1.0, 1.5, 0.5, 0.0, 1.0]
        gf = np.mean([h[0] for h in hist])
        ga = np.mean([h[1] for h in hist])
        pts = np.mean([h[2] for h in hist])
        win_rate = sum(1 for r in self.result_history[team][-6:] if r == 1) / max(len(self.result_history[team][-6:]), 1)
        home_advantage = 1.0 if is_home else 0.0
        return [gf, ga, pts, win_rate, home_advantage, len(hist)]

    def _build_dataset(self):
        X, y_home, y_away, y_over = [], [], [], []
        teams = list(self.history.keys())
        for team in teams:
            for i, (gf, ga, pts) in enumerate(self.history[team]):
                # We need both home & away feature vectors
                # Simplified: use the same features for both teams from perspective of this team
                feats = self._team_features(team, True)
                X.append(feats)
                y_home.append(gf)
                y_away.append(ga)
                y_over.append(1 if gf + ga > 2.5 else 0)
        return np.array(X), np.array(y_home), np.array(y_away), np.array(y_over)

    def fit(self):
        if not HAS_XGB:
            return False
        X, y_home, y_away, y_over = self._build_dataset()
        if len(X) < 50:
            return False

        # Regression for home goals
        self.model_home = xgb.XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.1, verbosity=0)
        self.model_home.fit(X, y_home)

        # Regression for away goals
        self.model_away = xgb.XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.1, verbosity=0)
        self.model_away.fit(X, y_away)

        # Binary classification for Over 2.5
        self.model_over25 = xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, verbosity=0)
        self.model_over25.fit(X, y_over)

        self.fitted = True
        return True

    def predict_match(self, home, away):
        if not self.fitted:
            ok = self.fit()
            if not ok:
                # fallback: neutral prediction
                return {"home_win": 0.33, "draw": 0.33, "away_win": 0.33,
                        "expected_home_goals": 1.3, "expected_away_goals": 1.1}

        X_home = np.array([self._team_features(home, True)])
        X_away = np.array([self._team_features(away, False)])

        lam_home = float(self.model_home.predict(X_home)[0])
        lam_away = float(self.model_away.predict(X_away)[0])
        lam_home = max(min(lam_home, 5.0), 0.2)
        lam_away = max(min(lam_away, 5.0), 0.2)

        # Convert expected goals to probabilities via Poisson
        import math
        def pois(k, lam): return (lam ** k) * math.exp(-lam) / math.factorial(k)
        home_win = draw = away_win = 0.0
        for i in range(8):
            for j in range(8):
                p = pois(i, lam_home) * pois(j, lam_away)
                if i > j: home_win += p
                elif i == j: draw += p
                else: away_win += p
        total = home_win + draw + away_win

        over25 = 1.0 - sum(pois(i, lam_home) * pois(j, lam_away)
                           for i in range(3) for j in range(3) if i + j <= 2)

        return {
            "home_win": home_win / total,
            "draw": draw / total,
            "away_win": away_win / total,
            "expected_home_goals": lam_home,
            "expected_away_goals": lam_away,
            "over25": over25,
        }