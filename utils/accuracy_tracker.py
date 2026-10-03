# utils/accuracy_tracker.py
import json
import os
from datetime import datetime
from collections import defaultdict

ACCURACY_FILE = "accuracy_data.json"
MAX_MATCHDAYS = 20
START_FROM_MATCHDAY = 3  # Start tracking from matchday 4


class AccuracyTracker:
    def __init__(self):
        self.data = self._load()
        self.league_accuracy = {} 


    def _load(self):
        if os.path.exists(ACCURACY_FILE):
            try:
                with open(ACCURACY_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save(self):
        with open(ACCURACY_FILE, 'w') as f:
            json.dump(self.data, f, indent=2)

    def add_predictions(self, matchday, predictions):
        """Store predictions for a matchday (only if matchday >= 4)."""
        if matchday < START_FROM_MATCHDAY:
            return

        if str(matchday) not in self.data:
            self.data[str(matchday)] = {'predictions': [], 'results': [], 'accuracy': None}
        self.data[str(matchday)]['predictions'] = predictions
        self._prune()
        self._save()

    def add_results(self, matchday, results):
        """Store actual results for a matchday and compute accuracy (only if matchday >= 4)."""
        if matchday < START_FROM_MATCHDAY:
            return

        md_str = str(matchday)
        if md_str not in self.data:
            # No predictions for this matchday, skip
            return
        self.data[md_str]['results'] = results
        # Compute accuracy for this matchday
        accuracy = self._compute_matchday_accuracy(matchday)
        self.data[md_str]['accuracy'] = accuracy
        self._prune()
        self._save()

    def _compute_matchday_accuracy(self, matchday):
        md_str = str(matchday)
        if md_str not in self.data:
            return None
        preds = self.data[md_str]['predictions']
        results = self.data[md_str]['results']
        if not preds or not results:
            return None

        actual = {}
        for r in results:
            key = (r['home'], r['away'])
            actual[key] = r['result']

        correct = 0
        total = 0
        over25_correct = 0
        over25_total = 0
        btts_correct = 0
        btts_total = 0

        for p in preds:
            key = (p['home'], p['away'])
            if key in actual:
                total += 1
                if p['top_pick'] == actual[key]:
                    correct += 1
                if 'over25_actual' in r:
                    over25_total += 1
                    if p['over25'] == r['over25_actual']:
                        over25_correct += 1
                if 'btts_actual' in r:
                    btts_total += 1
                    if p['btts'] == r['btts_actual']:
                        btts_correct += 1

        return {
            'total': total,
            'correct': correct,
            'accuracy': correct / total if total > 0 else 0,
            'over25': {'total': over25_total, 'correct': over25_correct, 'accuracy': over25_correct / over25_total if over25_total > 0 else 0},
            'btts': {'total': btts_total, 'correct': btts_correct, 'accuracy': btts_correct / btts_total if btts_total > 0 else 0}
        }

    def _prune(self):
        """Keep only the last MAX_MATCHDAYS matchdays (starting from matchday 4)."""
        keys = [int(k) for k in self.data.keys() if k.isdigit() and int(k) >= START_FROM_MATCHDAY]
        if len(keys) > MAX_MATCHDAYS:
            sorted_keys = sorted(keys)
            to_remove = sorted_keys[:-MAX_MATCHDAYS]
            for k in to_remove:
                del self.data[str(k)]

    def get_overall_accuracy(self):
        """Compute overall accuracy over all stored matchdays (>=4)."""
        total_correct = 0
        total_matches = 0
        over25_correct = 0
        over25_total = 0
        btts_correct = 0
        btts_total = 0
        days_count = 0
        for md, entry in self.data.items():
            if not md.isdigit():
                continue
            if int(md) < START_FROM_MATCHDAY:
                continue
            acc = entry.get('accuracy')
            if acc:
                days_count += 1
                total_correct += acc.get('correct', 0)
                total_matches += acc.get('total', 0)
                if acc.get('over25'):
                    over25_correct += acc['over25'].get('correct', 0)
                    over25_total += acc['over25'].get('total', 0)
                if acc.get('btts'):
                    btts_correct += acc['btts'].get('correct', 0)
                    btts_total += acc['btts'].get('total', 0)
        return {
            'overall': total_correct / total_matches if total_matches > 0 else 0,
            'over25': over25_correct / over25_total if over25_total > 0 else 0,
            'btts': btts_correct / btts_total if btts_total > 0 else 0,
            'matches': total_matches,
            'matchdays': days_count
        }

    def get_matchday_accuracy(self, matchday):
        return self.data.get(str(matchday), {}).get('accuracy')

    def get_all_matchdays(self):
        """Return sorted list of matchdays with data (>=4)."""
        return sorted([int(k) for k in self.data.keys() if k.isdigit() and int(k) >= START_FROM_MATCHDAY])
    

    def add_prediction_for_league(self, league, home, away, top_pick, confidence, over25, btts):
        if league not in self.league_accuracy:
            self.league_accuracy[league] = {'total': 0, 'correct': 0, 'history': []}
        # We'll store the prediction for later comparison (in a queue)
        if 'pending' not in self.league_accuracy[league]:
            self.league_accuracy[league]['pending'] = []
        self.league_accuracy[league]['pending'].append({
            'home': home, 'away': away, 'top_pick': top_pick,
            'confidence': confidence, 'over25': over25, 'btts': btts
        })

    def add_result_for_league(self, league, home, away, actual_result):
        """Compare stored prediction with actual result for a league."""
        # This will be called when results are added
        # We need to store predictions and results in a queue per league
        pass