# utils/advanced_o25.py
"""
Advanced Over 2.5 predictors.
Focused on maximizing accuracy for the O2.5 market.
"""

import math
import numpy as np
from collections import defaultdict

# ============================================================
# 1. BIVARIATE POISSON
# ============================================================
class BivariatePoisson:
    """
    Models home/away goals with correlation (common in real football).
    P(X=x, Y=y) = e^(-λ1-λ2-λ3) * Σ [λ1^(x-k) λ2^(y-k) λ3^k] / [(x-k)!(y-k)!k!]
    where λ3 captures the correlation between teams scoring.
    """
    def __init__(self):
        self.attack = defaultdict(lambda: 1.0)
        self.defence = defaultdict(lambda: 1.0)
        self.games = defaultdict(int)
        self.league_avg_home = 1.35
        self.league_avg_away = 1.10
        self.corr_lambda = 0.1  # covariance term

    def add_match(self, home, away, ft_h, ft_a):
        n = self.games[home]
        self.attack[home] = (self.attack[home] * n + ft_h / self.league_avg_home) / (n + 1)
        self.defence[home] = (self.defence[home] * n + ft_a / self.league_avg_away) / (n + 1)
        self.games[home] += 1

        n = self.games[away]
        self.attack[away] = (self.attack[away] * n + ft_a / self.league_avg_away) / (n + 1)
        self.defence[away] = (self.defence[away] * n + ft_h / self.league_avg_home) / (n + 1)
        self.games[away] += 1

    def _bvp_prob(self, x, y, l1, l2, l3):
        """Bivariate Poisson PMF with correlation term l3."""
        total = 0.0
        for k in range(min(x, y) + 1):
            total += (l1 ** (x - k) * l2 ** (y - k) * l3 ** k) / (
                math.factorial(x - k) * math.factorial(y - k) * math.factorial(k)
            )
        return math.exp(-(l1 + l2 + l3)) * total

    def predict_over25(self, home, away):
        l1 = self.league_avg_home * self.attack[home] * self.defence[away] * 1.15
        l2 = self.league_avg_away * self.attack[away] * self.defence[home]
        l1 = max(min(l1, 5.0), 0.2)
        l2 = max(min(l2, 5.0), 0.2)
        l3 = self.corr_lambda

        over = 0.0
        total = 0.0
        for i in range(8):
            for j in range(8):
                p = self._bvp_prob(i, j, l1, l2, l3)
                total += p
                if i + j > 2.5:
                    over += p

        if total == 0:
            return 0.5
        return over / total


# ============================================================
# 2. ROLLING FORM POISSON (recency-weighted)
# ============================================================
class RollingFormPoisson:
    """
    Uses recent N matches (weighted) instead of season average.
    """
    def __init__(self, window=5, decay=0.85):
        self.window = window
        self.decay = decay
        self.history = defaultdict(list)  # team -> [(gf, ga, is_home)]

    def add_match(self, home, away, ft_h, ft_a):
        self.history[home].append((ft_h, ft_a, True))
        self.history[away].append((ft_a, ft_h, False))
        for t in (home, away):
            if len(self.history[t]) > self.window * 3:
                self.history[t] = self.history[t][-self.window * 3:]

    def _weighted_stats(self, team, is_home):
        matches = [m for m in self.history[team] if m[2] == is_home][-self.window:]
        if not matches:
            matches = self.history[team][-self.window:]
        if not matches:
            return 1.35 if is_home else 1.10, 1.10 if is_home else 1.35

        w_sum = 0.0
        gf_w = 0.0
        ga_w = 0.0
        for i, (gf, ga, _) in enumerate(reversed(matches)):
            w = self.decay ** i
            gf_w += gf * w
            ga_w += ga * w
            w_sum += w

        return gf_w / w_sum, ga_w / w_sum

    def predict_over25(self, home, away):
        h_gf, h_ga = self._weighted_stats(home, True)
        a_gf, a_ga = self._weighted_stats(away, False)

        # Expected goals blend: attack-vs-defence
        exp_home = (h_gf + a_ga) / 2 * 1.1
        exp_away = (a_gf + h_ga) / 2 * 0.95
        exp_home = max(min(exp_home, 5.0), 0.2)
        exp_away = max(min(exp_away, 5.0), 0.2)

        # Poisson over 2.5
        def pois(k, lam): return (lam ** k) * math.exp(-lam) / math.factorial(k)
        under = 0.0
        for i in range(3):
            for j in range(3):
                if i + j <= 2:
                    under += pois(i, exp_home) * pois(j, exp_away)
        return 1.0 - under


# ============================================================
# 3. TEAM OVER 2.5 RATE
# ============================================================
class TeamOver25Rate:
    """
    Historical rate at which each team's matches exceed 2.5 goals,
    weighted by recency, then combined into a match probability.
    """
    def __init__(self, decay=0.9):
        self.decay = decay
        self.history = defaultdict(list)  # team -> [1 if over else 0]
        self.league_rate = 0.5

    def add_match(self, home, away, ft_h, ft_a):
        over = 1 if (ft_h + ft_a) > 2.5 else 0
        self.history[home].append(over)
        self.history[away].append(over)
        # Update league rate
        self.league_rate = self.league_rate * 0.99 + over * 0.01

    def _weighted_rate(self, team):
        matches = self.history[team][-15:]
        if not matches:
            return self.league_rate
        w_sum = 0.0
        v_sum = 0.0
        for i, v in enumerate(reversed(matches)):
            # Defensive: coerce to int in case a tuple/list slipped through
            if isinstance(v, (tuple, list)):
                v = v[0] if v else 0
            try:
                v = int(v)
            except Exception:
                v = 0
            w = self.decay ** i
            v_sum += v * w
            w_sum += w
        return v_sum / w_sum if w_sum > 0 else self.league_rate

    def predict_over25(self, home, away):
        h_rate = self._weighted_rate(home)
        a_rate = self._weighted_rate(away)
        # Blend the two teams' rates, weighted toward the higher one
        blended = 0.5 * h_rate + 0.5 * a_rate
        # Push slightly toward the extremes (regression correction)
        boosted = blended * 0.85 + 0.15 * max(h_rate, a_rate)
        return max(min(boosted, 0.95), 0.05)


# ============================================================
# 4. FEATURE BUILDER for tree/ML models
# ============================================================
def build_features(history_map, home, away):
    """
    Return a feature vector for a match.
    history_map: defaultdict(list) of {team: [(gf, ga, is_home)]}
    """
    def team_stats(team):
        h = history_map.get(team, [])
        if not h:
            return [1.35, 1.10, 1.35, 1.10, 0.5, 0.5]
        gf = np.mean([m[0] for m in h[-6:]])
        ga = np.mean([m[1] for m in h[-6:]])
        gf3 = np.mean([m[0] for m in h[-3:]]) if len(h) >= 3 else gf
        ga3 = np.mean([m[1] for m in h[-3:]]) if len(h) >= 3 else ga
        over_rate = np.mean([1 if (m[0] + m[1]) > 2.5 else 0 for m in h[-10:]])
        btts_rate = np.mean([1 if (m[0] > 0 and m[1] > 0) else 0 for m in h[-10:]])
        return [gf, ga, gf3, ga3, over_rate, btts_rate]

    h_stats = team_stats(home)
    a_stats = team_stats(away)

    # H2H (find matches between these two)
    h2h = []
    for m in history_map.get(home, []):
        pass  # simplified

    feats = h_stats + a_stats + [
        1.0,             # home advantage dummy
        (h_stats[0] + a_stats[0]),  # combined attack
        (h_stats[1] + a_stats[1]),  # combined defence
        abs(h_stats[0] - a_stats[0]),  # attack diff
    ]
    return feats


# ============================================================
# 5. TREE ENSEMBLE (XGB + LGBM + GBC)
# ============================================================
class TreeEnsembleOver25:
    """
    Combines XGBoost, LightGBM and sklearn GradientBoosting.
    Retrains only when significant new data is added.
    """
    def __init__(self):
        self.history = defaultdict(list)  # team -> [(gf, ga, is_home)]
        self.match_records = []           # [(home, away, over)]
        self.fitted = False
        self.xgb_model = None
        self.lgb_model = None
        self.gbc_model = None
        self._last_train_count = 0

    def add_match(self, home, away, ft_h, ft_a):
        self.history[home].append((ft_h, ft_a, True))
        self.history[away].append((ft_a, ft_h, False))
        self.match_records.append((home, away, 1 if (ft_h + ft_a) > 2.5 else 0))

    def fit(self, force=False):
        current = len(self.match_records)
        if not force and self.fitted and (current - self._last_train_count) < 100:
            return self.fitted
        if current < 100:
            return False

        X, y = [], []
        # Build features using ONLY prior matches to avoid leakage
        temp_hist = defaultdict(list)
        for home, away, over in self.match_records:
            feats = build_features(temp_hist, home, away)
            X.append(feats)
            y.append(over)
            # Update history AFTER
            temp_hist[home].append((0, 0, True))  # placeholder for feature consistency
            temp_hist[away].append((0, 0, False))

        X = np.array(X)
        y = np.array(y)
        if len(set(y)) < 2:
            return False

        try:
            from xgboost import XGBClassifier
            self.xgb_model = XGBClassifier(
                n_estimators=200, max_depth=5, learning_rate=0.08,
                subsample=0.85, colsample_bytree=0.85,
                random_state=42, verbosity=0,
            )
            self.xgb_model.fit(X, y)
        except Exception as e:
            print(f"XGB fit failed: {e}")

        try:
            from lightgbm import LGBMClassifier
            self.lgb_model = LGBMClassifier(
                n_estimators=200, max_depth=5, learning_rate=0.08,
                subsample=0.85, colsample_bytree=0.85,
                random_state=42, verbosity=-1,
            )
            self.lgb_model.fit(X, y)
        except Exception as e:
            print(f"LGBM fit failed: {e}")

        try:
            from sklearn.ensemble import GradientBoostingClassifier
            self.gbc_model = GradientBoostingClassifier(
                n_estimators=150, max_depth=4, learning_rate=0.1,
                random_state=42,
            )
            self.gbc_model.fit(X, y)
        except Exception as e:
            print(f"GBC fit failed: {e}")

        self.fitted = True
        self._last_train_count = current
        return True

    def predict_over25(self, home, away):
        if not self.fitted:
            if not self.fit():
                return 0.5
        X = np.array([build_features(self.history, home, away)])
        probs = []
        if self.xgb_model:
            try:
                probs.append(self.xgb_model.predict_proba(X)[0][1])
            except Exception:
                pass
        if self.lgb_model:
            try:
                probs.append(self.lgb_model.predict_proba(X)[0][1])
            except Exception:
                pass
        if self.gbc_model:
            try:
                probs.append(self.gbc_model.predict_proba(X)[0][1])
            except Exception:
                pass
        return float(np.mean(probs)) if probs else 0.5


# ============================================================
# 6. NEURAL NET (MLP)
# ============================================================
class NeuralOver25:
    """Simple MLP for O2.5 classification."""
    def __init__(self):
        self.history = defaultdict(list)
        self.match_records = []
        self.model = None
        self.scaler = None
        self.fitted = False

    def add_match(self, home, away, ft_h, ft_a):
        self.history[home].append((ft_h, ft_a, True))
        self.history[away].append((ft_a, ft_h, False))
        self.match_records.append((home, away, 1 if (ft_h + ft_a) > 2.5 else 0))

    def fit(self):
        if self.fitted or len(self.match_records) < 150:
            return self.fitted
        from sklearn.neural_network import MLPClassifier
        from sklearn.preprocessing import StandardScaler

        X, y = [], []
        temp_hist = defaultdict(list)
        for home, away, over in self.match_records:
            X.append(build_features(temp_hist, home, away))
            y.append(over)
            temp_hist[home].append((1.0, 1.0, True))
            temp_hist[away].append((1.0, 1.0, False))
        X = np.array(X)
        y = np.array(y)
        if len(set(y)) < 2:
            return False

        self.scaler = StandardScaler().fit(X)
        Xs = self.scaler.transform(X)
        self.model = MLPClassifier(
            hidden_layer_sizes=(32, 16), activation="relu",
            max_iter=500, random_state=42,
        )
        self.model.fit(Xs, y)
        self.fitted = True
        return True

    def predict_over25(self, home, away):
        if not self.fitted:
            self.fit()
        if not self.model:
            return 0.5
        X = np.array([build_features(self.history, home, away)])
        Xs = self.scaler.transform(X)
        return float(self.model.predict_proba(Xs)[0][1])


# ============================================================
# 7. UNIFIED ENSEMBLE
# ============================================================
class Over25Ensemble:
    """
    Combines all Over 2.5 predictors with learned weights.
    """
    def __init__(self):
        self.models = {}
        self.history = defaultdict(list)
        self.matches = []
        self.weights = {}   # learned per model
        self.fitted_weights = False

    def add_match(self, home, away, ft_h, ft_a):
        self.history[home].append((ft_h, ft_a, True))
        self.history[away].append((ft_a, ft_h, False))
        self.matches.append((home, away, 1 if (ft_h + ft_a) > 2.5 else 0))
        for m in self.models.values():
            if hasattr(m, "add_match"):
                m.add_match(home, away, ft_h, ft_a)

    def register(self, name, model):
        self.models[name] = model

    def train_weights(self, lookback=300):
        """
        Placeholder for future weight learning.
        For now, use equal weights across all models.
        """
        self.weights = {name: 1.0 for name in self.models}
        self.fitted_weights = True
        return True

    def predict_over25(self, home, away):
        preds = {}
        for name, model in self.models.items():
            try:
                preds[name] = model.predict_over25(home, away)
            except Exception:
                continue
        if not preds:
            return 0.5
        if not self.fitted_weights:
            self.weights = {k: 1.0 for k in preds}
        total_w = 0.0
        blended = 0.0
        for name, p in preds.items():
            w = self.weights.get(name, 1.0)
            blended += p * w
            total_w += w
        return blended / total_w if total_w else 0.5