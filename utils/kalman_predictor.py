# utils/kalman_predictor.py
import numpy as np

class KalmanTeamStrength:
    """
    Kalman filter for team attack & defence strengths.
    State: [attack, defence] per team.
    Observation: goals scored and conceded in a match.
    """
    def __init__(self, process_noise=0.05, measurement_noise=0.3):
        # State vectors
        self.attack = {}      # team -> mean
        self.attack_var = {}  # team -> variance
        self.defence = {}
        self.defence_var = {}
        self.games = {}

        # Hyperparams
        self.Q = process_noise       # process noise (how much can strength change between matches)
        self.R = measurement_noise   # measurement noise (how noisy are goals as a signal)

        # League averages
        self.league_avg_home = 1.35
        self.league_avg_away = 1.10

    def _init_team(self, team):
        if team not in self.attack:
            self.attack[team] = 1.0
            self.attack_var[team] = 1.0
            self.defence[team] = 1.0
            self.defence_var[team] = 1.0
            self.games[team] = 0

    def add_match(self, home, away, ft_h, ft_a):
        self._init_team(home)
        self._init_team(away)

        # Observations: goals scored by each team, relative to league avg
        obs_home_attack = ft_h / self.league_avg_home
        obs_away_attack = ft_a / self.league_avg_away
        obs_home_defence = ft_a / self.league_avg_away
        obs_away_defence = ft_h / self.league_avg_home

        # --- Update home team ---
        self._update(home, "attack", obs_home_attack)
        self._update(home, "defence", obs_home_defence)

        # --- Update away team ---
        self._update(away, "attack", obs_away_attack)
        self._update(away, "defence", obs_away_defence)

        self.games[home] += 1
        self.games[away] += 1

    def _update(self, team, field, observation):
        """One Kalman step for (team, field)."""
        if field == "attack":
            mean = self.attack[team]
            var = self.attack_var[team]
        else:
            mean = self.defence[team]
            var = self.defence_var[team]

        # Predict
        var_pred = var + self.Q

        # Kalman gain
        K = var_pred / (var_pred + self.R)

        # Update
        mean_new = mean + K * (observation - mean)
        var_new = (1 - K) * var_pred

        if field == "attack":
            self.attack[team] = mean_new
            self.attack_var[team] = var_new
        else:
            self.defence[team] = mean_new
            self.defence_var[team] = var_new

    def predict_match(self, home, away):
        self._init_team(home)
        self._init_team(away)

        exp_home = self.league_avg_home * self.attack[home] * self.defence[away]
        exp_away = self.league_avg_away * self.attack[away] * self.defence[home]

        # Convert expected goals to H/D/A probabilities using Poisson
        import math
        def pois(k, lam):
            return (lam ** k) * math.exp(-lam) / math.factorial(k)

        home_win = draw = away_win = 0.0
        for i in range(8):
            for j in range(8):
                p = pois(i, exp_home) * pois(j, exp_away)
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
            "expected_home_goals": exp_home,
            "expected_away_goals": exp_away,
        }