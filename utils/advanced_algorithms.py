# utils/advanced_algorithms.py
import numpy as np
from collections import defaultdict

# ---------- ELO RATING ----------
class ELO_Rating:
    def __init__(self, initial_elo=1500, k_factor=32):
        self.ratings = defaultdict(lambda: initial_elo)
        self.k_factor = k_factor
        
    def update_ratings(self, home, away, ft_h, ft_a):
        home_rating = self.ratings[home]
        away_rating = self.ratings[away]
        home_expected = 1 / (1 + 10 ** ((away_rating - home_rating) / 400))
        away_expected = 1 / (1 + 10 ** ((home_rating - away_rating) / 400))
        if ft_h > ft_a:
            home_actual, away_actual = 1, 0
        elif ft_h == ft_a:
            home_actual, away_actual = 0.5, 0.5
        else:
            home_actual, away_actual = 0, 1
        self.ratings[home] = home_rating + self.k_factor * (home_actual - home_expected)
        self.ratings[away] = away_rating + self.k_factor * (away_actual - away_expected)
    
    def predict_match(self, home, away):
        home_rating = self.ratings.get(home, 1500)
        away_rating = self.ratings.get(away, 1500)
        home_win = 1 / (1 + 10 ** ((away_rating - home_rating) / 400))
        away_win = 1 / (1 + 10 ** ((home_rating - away_rating) / 400))
        draw = 1 - home_win - away_win
        return {
            "home_win": home_win,
            "draw": max(draw, 0.01),
            "away_win": away_win,
            "home_rating": home_rating,
            "away_rating": away_rating
        }

# ---------- MARKOV CHAIN ----------
class MarkovChainPredictor:
    def __init__(self):
        self.transition = defaultdict(lambda: {'W': 0, 'D': 0, 'L': 0})
        self.last_result = {}
        self.history = defaultdict(list)
    
    def add_result(self, team, result):
        if team in self.last_result:
            prev = self.last_result[team]
            self.transition[prev][result] += 1
        self.last_result[team] = result
        self.history[team].append(result)
    
    def get_streak(self, team):
        if team not in self.history or not self.history[team]:
            return 0, 'N'
        last = self.history[team][-1]
        streak = 1
        for r in reversed(self.history[team][:-1]):
            if r == last:
                streak += 1
            else:
                break
        return streak, last
    
    def predict_match(self, home, away):
        home_streak, home_last = self.get_streak(home)
        away_streak, away_last = self.get_streak(away)
        home_win = 0.4
        draw = 0.25
        away_win = 0.35
        if home_last == 'W' and home_streak >= 2:
            home_win += 0.10
        elif home_last == 'L' and home_streak >= 2:
            home_win -= 0.05
        if away_last == 'W' and away_streak >= 2:
            away_win += 0.10
        elif away_last == 'L' and away_streak >= 2:
            away_win -= 0.05
        total = home_win + draw + away_win
        return {
            "home_win": home_win / total,
            "draw": draw / total,
            "away_win": away_win / total,
            "home_streak": home_streak,
            "away_streak": away_streak
        }

# ---------- LOGISTIC REGRESSION STYLE ----------
class LogisticPredictor:
    def __init__(self):
        self.features = defaultdict(lambda: {
            'home_goals': 1.0,
            'away_goals': 0.8,
            'home_conceded': 0.9,
            'away_conceded': 1.1,
            'form': 3,
            'games': 0
        })
    
    def add_match(self, home, away, ft_h, ft_a):
        self.features[home]['home_goals'] = self.features[home]['home_goals'] * 0.9 + ft_h * 0.1
        self.features[home]['home_conceded'] = self.features[home]['home_conceded'] * 0.9 + ft_a * 0.1
        self.features[home]['games'] += 1
        self.features[away]['away_goals'] = self.features[away]['away_goals'] * 0.9 + ft_a * 0.1
        self.features[away]['away_conceded'] = self.features[away]['away_conceded'] * 0.9 + ft_h * 0.1
        self.features[away]['games'] += 1
        if ft_h > ft_a:
            home_form, away_form = 3, 0
        elif ft_h == ft_a:
            home_form, away_form = 1, 1
        else:
            home_form, away_form = 0, 3
        self.features[home]['form'] = self.features[home]['form'] * 0.7 + home_form * 0.3
        self.features[away]['form'] = self.features[away]['form'] * 0.7 + away_form * 0.3
    
    def predict_match(self, home, away):
        h = self.features[home]
        a = self.features[away]
        home_attack = h['home_goals'] / (h['home_goals'] + a['away_conceded'] + 0.1)
        away_attack = a['away_goals'] / (a['away_goals'] + h['home_conceded'] + 0.1)
        home_form = h['form'] / (h['form'] + a['form'] + 0.1)
        away_form = a['form'] / (h['form'] + a['form'] + 0.1)
        home_strength = (home_attack * 0.4 + home_form * 0.3 + 0.5) / 1.2
        away_strength = (away_attack * 0.4 + away_form * 0.3 + 0.5) / 1.2
        total = home_strength + away_strength
        home_win = (home_strength / total) * 0.7 + 0.15
        away_win = (away_strength / total) * 0.7 + 0.15
        draw = 1 - home_win - away_win
        return {
            "home_win": max(min(home_win, 1), 0),
            "draw": max(draw, 0.01),
            "away_win": max(min(away_win, 1), 0)
        }

# ---------- HIGH CONCEDING DETECTOR ----------
class HighConcedingDetector:
    def __init__(self, window=3, threshold=5):
        self.window = window
        self.threshold = threshold
        self.conceded_history = defaultdict(list)
        self.strong_teams = set()
    
    def add_match(self, home, away, ft_h, ft_a):
        self.conceded_history[home].append(ft_a)
        self.conceded_history[away].append(ft_h)
        if len(self.conceded_history[home]) > self.window:
            self.conceded_history[home] = self.conceded_history[home][-self.window:]
        if len(self.conceded_history[away]) > self.window:
            self.conceded_history[away] = self.conceded_history[away][-self.window:]
    
    def set_strong_teams(self, teams):
        self.strong_teams = set(teams)
    
    def check_match(self, home, away):
        result = {
            "home_high_conceding": False,
            "away_high_conceding": False,
            "home_faces_strong": away in self.strong_teams,
            "away_faces_strong": home in self.strong_teams,
            "warning": None
        }
        if home in self.conceded_history and len(self.conceded_history[home]) >= self.window:
            total_conceded = sum(self.conceded_history[home])
            if total_conceded >= self.threshold:
                result["home_high_conceding"] = True
        if away in self.conceded_history and len(self.conceded_history[away]) >= self.window:
            total_conceded = sum(self.conceded_history[away])
            if total_conceded >= self.threshold:
                result["away_high_conceding"] = True
        
        if result["home_high_conceding"] and result["home_faces_strong"]:
            result["warning"] = f"⚠️ {home} conceded {sum(self.conceded_history[home])} goals in last {self.window} matches and faces strong team {away}!"
        elif result["away_high_conceding"] and result["away_faces_strong"]:
            result["warning"] = f"⚠️ {away} conceded {sum(self.conceded_history[away])} goals in last {self.window} matches and faces strong team {home}!"
        return result



# ---------- CONSENSUS VOTER ----------
class ConsensusVoter:
    def __init__(self):
        self.algorithms = {}
    
    def add_algorithm(self, name, algo):
        self.algorithms[name] = algo
    
    def predict_match(self, home, away):
        results = {}
        votes = {'home': 0, 'draw': 0, 'away': 0}
        for name, algo in self.algorithms.items():
            try:
                if hasattr(algo, 'predict_match'):
                    pred = algo.predict_match(home, away)
                else:
                    continue
                results[name] = pred
                if pred['home_win'] > pred['away_win'] and pred['home_win'] > pred['draw']:
                    votes['home'] += 1
                elif pred['away_win'] > pred['home_win'] and pred['away_win'] > pred['draw']:
                    votes['away'] += 1
                else:
                    votes['draw'] += 1
            except:
                pass
        total = sum(votes.values())
        if total == 0:
            return {'home_win': 0.33, 'draw': 0.33, 'away_win': 0.33, 'winner': 'draw', 'agreement': 0, 'algorithms_used': 0}
        winner = max(votes, key=votes.get)
        agreement = votes[winner] / total
        avg_home = np.mean([r['home_win'] for r in results.values() if 'home_win' in r]) if results else 0.33
        avg_away = np.mean([r['away_win'] for r in results.values() if 'away_win' in r]) if results else 0.33
        avg_draw = np.mean([r['draw'] for r in results.values() if 'draw' in r]) if results else 0.33
        return {
            "home_win": avg_home,
            "draw": avg_draw,
            "away_win": avg_away,
            "winner": winner,
            "votes": votes,
            "agreement": agreement,
            "algorithms_used": len(results),
            "algorithm_results": results
        }
    

##ML start
# utils/advanced_algorithms.py (add this class)

class MLPredictorWrapper:
    """Wrapper to make ML predictor compatible with consensus voter."""
    def __init__(self, ml_predictor):
        self.ml = ml_predictor

    def predict_match(self, home, away):
        return self.ml.predict_match(home, away)



# ---------- POISSON DISTRIBUTION ----------
class PoissonPredictor:
    """
    Uses attack/defense strengths to compute expected goals,
    then Poisson distribution to derive match outcome probabilities.
    """
    def __init__(self, home_advantage=1.25):
        self.home_advantage = home_advantage
        self.attack = defaultdict(lambda: 1.0)
        self.defense = defaultdict(lambda: 1.0)
        self.league_avg_home = 1.35
        self.league_avg_away = 1.10
        self.games = defaultdict(int)

    def add_match(self, home, away, ft_h, ft_a):
        # Update attack strength (goals scored vs league avg)
        self.attack[home] = (self.attack[home] * self.games[home] + ft_h) / (self.games[home] + 1)
        self.attack[away] = (self.attack[away] * self.games[away] + ft_a) / (self.games[away] + 1)
        # Update defense strength (goals conceded vs league avg)
        self.defense[home] = (self.defense[home] * self.games[home] + ft_a) / (self.games[home] + 1)
        self.defense[away] = (self.defense[away] * self.games[away] + ft_h) / (self.games[away] + 1)
        self.games[home] += 1
        self.games[away] += 1

    def _poisson_prob(self, k, lam):
        import math
        return (lam ** k) * math.exp(-lam) / math.factorial(k)

    def predict_match(self, home, away):
        lam_home = self.league_avg_home * self.attack[home] * self.defense[away] * self.home_advantage
        lam_away = self.league_avg_away * self.attack[away] * self.defense[home]
        lam_home = max(min(lam_home, 5.0), 0.3)
        lam_away = max(min(lam_away, 5.0), 0.3)

        home_win = draw = away_win = 0.0
        for i in range(7):
            for j in range(7):
                p = self._poisson_prob(i, lam_home) * self._poisson_prob(j, lam_away)
                if i > j:
                    home_win += p
                elif i == j:
                    draw += p
                else:
                    away_win += p

        total = home_win + draw + away_win
        return {
            "home_win": home_win / total,
            "draw": draw / total,
            "away_win": away_win / total,
            "expected_home_goals": lam_home,
            "expected_away_goals": lam_away
        }


# ---------- DIXON-COLES ----------
class DixonColesPredictor:
    """
    Classic football model with low-score correction (rho parameter).
    """
    def __init__(self, xi=0.0018, rho=-0.05):
        self.xi = xi  # time decay
        self.rho = rho  # low-score correlation
        self.attack = defaultdict(lambda: 1.0)
        self.defense = defaultdict(lambda: 1.0)
        self.games = defaultdict(int)
        self.league_avg_home = 1.35
        self.league_avg_away = 1.10

    def add_match(self, home, away, ft_h, ft_a):
        w = 1.0  # could add time weighting with self.xi
        self.attack[home] = (self.attack[home] * self.games[home] + ft_h * w) / (self.games[home] + w)
        self.attack[away] = (self.attack[away] * self.games[away] + ft_a * w) / (self.games[away] + w)
        self.defense[home] = (self.defense[home] * self.games[home] + ft_a * w) / (self.games[home] + w)
        self.defense[away] = (self.defense[away] * self.games[away] + ft_h * w) / (self.games[away] + w)
        self.games[home] += 1
        self.games[away] += 1

    def _tau(self, x, y, lam, mu):
        if x == 0 and y == 0:
            return 1 - lam * mu * self.rho
        elif x == 0 and y == 1:
            return 1 + lam * self.rho
        elif x == 1 and y == 0:
            return 1 + mu * self.rho
        elif x == 1 and y == 1:
            return 1 - self.rho
        return 1.0

    def _poisson_prob(self, k, lam):
        import math
        return (lam ** k) * math.exp(-lam) / math.factorial(k)

    def predict_match(self, home, away):
        lam = self.league_avg_home * self.attack[home] * self.defense[away] * 1.25
        mu = self.league_avg_away * self.attack[away] * self.defense[home]
        lam = max(min(lam, 5.0), 0.3)
        mu = max(min(mu, 5.0), 0.3)

        home_win = draw = away_win = 0.0
        for i in range(7):
            for j in range(7):
                p = self._tau(i, j, lam, mu) * self._poisson_prob(i, lam) * self._poisson_prob(j, mu)
                if i > j:
                    home_win += p
                elif i == j:
                    draw += p
                else:
                    away_win += p

        total = home_win + draw + away_win
        return {
            "home_win": home_win / total,
            "draw": draw / total,
            "away_win": away_win / total,
            "rho": self.rho
        }


# ---------- BAYESIAN UPDATING ----------
class BayesianPredictor:
    """
    Maintains Beta-distributed priors for each team's win/draw/loss tendency.
    """
    def __init__(self):
        # alpha=1, beta=1 → uniform prior
        self.stats = defaultdict(lambda: {
            "home_wins": 1, "home_draws": 1, "home_losses": 1,
            "away_wins": 1, "away_draws": 1, "away_losses": 1,
            "games": 0
        })

    def add_match(self, home, away, ft_h, ft_a):
        self.stats[home]["games"] += 1
        self.stats[away]["games"] += 1
        if ft_h > ft_a:
            self.stats[home]["home_wins"] += 1
            self.stats[away]["away_losses"] += 1
        elif ft_h == ft_a:
            self.stats[home]["home_draws"] += 1
            self.stats[away]["away_draws"] += 1
        else:
            self.stats[home]["home_losses"] += 1
            self.stats[away]["away_wins"] += 1

    def predict_match(self, home, away):
        h = self.stats[home]
        a = self.stats[away]
        h_total = h["home_wins"] + h["home_draws"] + h["home_losses"]
        a_total = a["away_wins"] + a["away_draws"] + a["away_losses"]

        home_strength = (h["home_wins"] / h_total + a["away_losses"] / a_total) / 2
        away_strength = (a["away_wins"] / a_total + h["home_losses"] / h_total) / 2
        draw_strength = (h["home_draws"] / h_total + a["away_draws"] / a_total) / 2

        total = home_strength + draw_strength + away_strength
        return {
            "home_win": home_strength / total,
            "draw": draw_strength / total,
            "away_win": away_strength / total
        }


# ---------- WEIGHTED FORM ----------
class WeightedFormPredictor:
    """
    Uses exponentially-decayed recent form to predict.
    """
    def __init__(self, decay=0.85, window=6):
        self.decay = decay
        self.window = window
        self.history = defaultdict(list)  # team -> [(points, goals_for, goals_against)]

    def add_match(self, home, away, ft_h, ft_a):
        if ft_h > ft_a:
            hp, ap = 3, 0
        elif ft_h == ft_a:
            hp, ap = 1, 1
        else:
            hp, ap = 0, 3
        self.history[home].append((hp, ft_h, ft_a))
        self.history[away].append((ap, ft_a, ft_h))
        if len(self.history[home]) > self.window:
            self.history[home] = self.history[home][-self.window:]
        if len(self.history[away]) > self.window:
            self.history[away] = self.history[away][-self.window:]

    def _weighted_form(self, team):
        hist = self.history[team]
        if not hist:
            return 1.5, 1.0, 1.0  # neutral
        w_points = 0
        w_gf = 0
        w_ga = 0
        weight_sum = 0
        for i, (pts, gf, ga) in enumerate(reversed(hist)):
            w = self.decay ** i
            w_points += pts * w
            w_gf += gf * w
            w_ga += ga * w
            weight_sum += w
        return w_points / weight_sum, w_gf / weight_sum, w_ga / weight_sum

    def predict_match(self, home, away):
        h_form, h_gf, h_ga = self._weighted_form(home)
        a_form, a_gf, a_ga = self._weighted_form(away)

        # Home advantage factor
        h_score = h_form * 1.15 + h_gf * 0.5 - h_ga * 0.3
        a_score = a_form * 1.0 + a_gf * 0.5 - a_ga * 0.3

        total = h_score + a_score
        if total <= 0:
            return {"home_win": 0.33, "draw": 0.33, "away_win": 0.33}

        home_win = h_score / (total + 1.0)  # +1 makes draw more likely
        away_win = a_score / (total + 1.0)
        draw = 1 - home_win - away_win

        return {
            "home_win": max(home_win, 0.05),
            "draw": max(draw, 0.05),
            "away_win": max(away_win, 0.05)
        }
# ---------- CONFIDENCE SCORER ----------
def compute_confidence(all_predictions):
        """
        Given a list of prediction dicts (each with home_win/draw/away_win),
        return the consensus outcome, agreement ratio, and average confidence.
        """
        if not all_predictions:
            return {"winner": "unknown", "agreement": 0, "confidence": 0, "total": 0}

        votes = {"home": 0, "draw": 0, "away": 0}
        for p in all_predictions:
            hw = p.get("home_win", 0.33)
            d  = p.get("draw", 0.33)
            aw = p.get("away_win", 0.33)
            if hw >= d and hw >= aw:
                votes["home"] += 1
            elif aw >= hw and aw >= d:
                votes["away"] += 1
            else:
                votes["draw"] += 1

        winner = max(votes, key=votes.get)
        agreement = votes[winner] / len(all_predictions)

        avg = np.mean([
            {"home": p.get("home_win", 0), "draw": p.get("draw", 0), "away": p.get("away_win", 0)}[winner]
            for p in all_predictions
        ])

        return {
            "winner": winner,
            "agreement": agreement,
            "confidence": avg,
            "votes": votes,
            "total": len(all_predictions)
        }