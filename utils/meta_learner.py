# utils/meta_learner.py
import numpy as np
from sklearn.linear_model import LogisticRegression
from collections import defaultdict

class MetaLearner:
    """
    Learns a weight for each algorithm based on historical accuracy.
    The final prediction is a weighted blend of all algorithms.
    """
    def __init__(self):
        self.predictions_log = []    # list of dicts: {algo_name: {'home': p, 'draw': p, 'away': p}, 'actual': 'home'/'draw'/'away'}
        self.weights = defaultdict(lambda: 1.0)
        self.fitted = False

    def log_prediction(self, algo_predictions, actual_result):
        """
        algo_predictions: dict {algo_name: {'home_win': .., 'draw': .., 'away_win': ..}}
        actual_result: 'home' | 'draw' | 'away'
        """
        self.predictions_log.append({
            'preds': algo_predictions,
            'actual': actual_result,
        })

    def fit_weights(self):
        """Compute accuracy-based weight for each algorithm."""
        if len(self.predictions_log) < 30:
            return False

        algo_correct = defaultdict(int)
        algo_total = defaultdict(int)

        for entry in self.predictions_log:
            actual = entry['actual']
            for algo, pred in entry['preds'].items():
                algo_total[algo] += 1
                # Which outcome did this algorithm pick?
                picked = max(['home', 'draw', 'away'],
                             key=lambda k: pred.get(f'{k}_win', 0))
                if picked == actual:
                    algo_correct[algo] += 1

        # Weight = accuracy with Laplace smoothing, scaled up for stability
        for algo in algo_total:
            acc = (algo_correct[algo] + 2) / (algo_total[algo] + 4)   # Laplace prior
            self.weights[algo] = acc
        self.fitted = True
        return True

    def blend(self, algo_predictions):
        """
        Weighted blend based on learned weights.
        algo_predictions: dict {algo_name: {'home_win': .., 'draw': .., 'away_win': ..}}
        """
        if not self.fitted:
            self.fit_weights()

        total_w = 0.0
        agg = {'home_win': 0.0, 'draw': 0.0, 'away_win': 0.0}
        for algo, pred in algo_predictions.items():
            w = self.weights.get(algo, 1.0)
            for k in agg:
                agg[k] += pred.get(k, 0.33) * w
            total_w += w

        if total_w > 0:
            for k in agg:
                agg[k] /= total_w

        winner = max(['home', 'draw', 'away'],
                     key=lambda k: agg.get(f'{k}_win', 0))
        return {
            'home_win': agg['home_win'],
            'draw': agg['draw'],
            'away_win': agg['away_win'],
            'winner': winner,
            'weights': dict(self.weights),
        }