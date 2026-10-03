# utils/predictor_core.py
"""
Core prediction logic — trains 11 algorithms + meta-learner + score matrix.
Used by both Auto Pilot (app.py) and Auto-Runner (background thread).
"""

from utils.kalman_predictor import KalmanTeamStrength
from utils.xgb_predictor import XGBGoalPredictor
from utils.meta_learner import MetaLearner
from utils.score_matrix import build_score_matrix, summarize_matrix
from utils.simulation_utils import LeagueStats
from scipy.stats import poisson as _pd


def run_predictions_core(training_matches, fixtures):
    """Enhanced with new Over 2.5 ensemble."""
    from utils.advanced_algorithms import (
        ELO_Rating, MarkovChainPredictor, LogisticPredictor,
        ConsensusVoter, PoissonPredictor, DixonColesPredictor,
        BayesianPredictor, WeightedFormPredictor,
    )
    from utils.kalman_predictor import KalmanTeamStrength
    from utils.xgb_predictor import XGBGoalPredictor
    from utils.meta_learner import MetaLearner
    from utils.score_matrix import build_score_matrix, summarize_matrix
    from utils.simulation_utils import LeagueStats
    from utils.advanced_o25 import (
        BivariatePoisson, RollingFormPoisson, TeamOver25Rate,
        TreeEnsembleOver25, NeuralOver25, Over25Ensemble,
    )
    from scipy.stats import poisson as _pd

    # ---------- Standard 9 algorithms ----------
    elo = ELO_Rating(); markov = MarkovChainPredictor()
    logistic = LogisticPredictor(); poisson = PoissonPredictor()
    dixon = DixonColesPredictor(); bayes = BayesianPredictor()
    form = WeightedFormPredictor(); stats = LeagueStats("BetPawa")
    kalman = KalmanTeamStrength(); xgb_model = XGBGoalPredictor()
    meta = MetaLearner()

    # ---------- NEW Over 2.5 ensemble ----------
    o25 = Over25Ensemble()
    o25.register("bivariate", BivariatePoisson())
    o25.register("rolling_poisson", RollingFormPoisson(window=5, decay=0.85))
    o25.register("team_rate", TeamOver25Rate(decay=0.9))
    o25.register("tree", TreeEnsembleOver25())
    o25.register("nn", NeuralOver25())

    # ---------- Train ----------
    for m in training_matches:
        h, a, fh, fa = m["home"], m["away"], m["ft_h"], m["ft_a"]
        elo.update_ratings(h, a, fh, fa)
        if fh > fa: markov.add_result(h, 'W'); markov.add_result(a, 'L')
        elif fh == fa: markov.add_result(h, 'D'); markov.add_result(a, 'D')
        else: markov.add_result(h, 'L'); markov.add_result(a, 'W')
        logistic.add_match(h, a, fh, fa)
        poisson.add_match(h, a, fh, fa)
        dixon.add_match(h, a, fh, fa)
        bayes.add_match(h, a, fh, fa)
        form.add_match(h, a, fh, fa)
        stats.add_match(h, a, fh, fa, fh, fa)
        kalman.add_match(h, a, fh, fa)
        xgb_model.add_match(h, a, fh, fa)
        o25.add_match(h, a, fh, fa)

    xgb_model.fit()
    o25.train_weights(lookback=300)   # compute per-model weights

    # ---------- Predict each fixture ----------
    predictions = []
    for fx in fixtures:
        home, away = fx["home"], fx["away"]
        league = fx.get("league", "Unknown")

        # Standard consensus
        voter = ConsensusVoter()
        voter.add_algorithm("stats", stats)
        voter.add_algorithm("elo", elo)
        voter.add_algorithm("markov", markov)
        voter.add_algorithm("logistic", logistic)
        voter.add_algorithm("dixon", dixon)
        voter.add_algorithm("bayesian", bayes)
        voter.add_algorithm("form", form)
        voter.add_algorithm("poisson", poisson)
        voter.add_algorithm("kalman", kalman)
        voter.add_algorithm("xgb", xgb_model)
        cons = voter.predict_match(home, away)

        # New ensemble O2.5
        o25_prob = o25.predict_over25(home, away)

        # Score matrix from Dixon-Coles expected goals
        dc_pred = dixon.predict_match(home, away)
        kal = kalman.predict_match(home, away)
        lam_h = (kal.get("expected_home_goals", 1.3) + dc_pred.get("expected_home_goals", 1.3)) / 2
        lam_a = (kal.get("expected_away_goals", 1.1) + dc_pred.get("expected_away_goals", 1.1)) / 2
        matrix = build_score_matrix(lam_h, lam_a, max_goals=8)
        ms = summarize_matrix(matrix)

        # Blend: 60% new ensemble, 40% existing score matrix
        final_o25 = 0.6 * o25_prob + 0.4 * ms["over25"]
        final_o25 = max(min(final_o25, 0.98), 0.02)

        # BTTS: use score matrix
        btts = ms["btts"]

        algos_used = cons.get("algorithms_used", 0) + 5
        agreement = cons.get("agreement", 0)
        agreement_str = f"{int(round(agreement * algos_used))}/{algos_used}"

        winner_code = cons.get("winner", "draw")
        if winner_code == "home":
            pick = f"{home} Win"; conf = cons.get("home_win", 0)
        elif winner_code == "away":
            pick = f"{away} Win"; conf = cons.get("away_win", 0)
        else:
            pick = "Draw"; conf = cons.get("draw", 0)

        if final_o25 >= 0.75: rating = "🥇 Elite O2.5"
        elif final_o25 >= 0.65: rating = "🥈 High O2.5"
        elif final_o25 >= 0.55: rating = "🥉 Medium O2.5"
        elif final_o25 >= 0.45: rating = "⚠️ Risky"
        else: rating = "❌ Skip"

        predictions.append({
            "home": home, "away": away, "league": league,
            "over25_pct": round(final_o25 * 100, 1),
            "btts_pct": round(btts * 100, 1),
            "expected_goals": round(lam_h + lam_a, 2),
            "most_likely_score": ms["most_likely_score"],
            "rating": rating,
            "agreement": agreement_str,
            "algorithms_used": algos_used,
            "winner_pick": pick,
            "winner_conf": round(conf, 3),
            "home_win": round(cons.get("home_win", 0), 3),
            "draw": round(cons.get("draw", 0), 3),
            "away_win": round(cons.get("away_win", 0), 3),
            # Debug: individual model probabilities
            "o25_models": {
                "bivariate": round(o25.models["bivariate"].predict_over25(home, away), 3),
                "rolling": round(o25.models["rolling_poisson"].predict_over25(home, away), 3),
                "team_rate": round(o25.models["team_rate"].predict_over25(home, away), 3),
                "tree": round(o25.models["tree"].predict_over25(home, away), 3),
                "nn": round(o25.models["nn"].predict_over25(home, away), 3),
            },
            "weights": {k: round(v, 2) for k, v in o25.weights.items()},
        })

    predictions.sort(key=lambda x: x["over25_pct"], reverse=True)
    return predictions