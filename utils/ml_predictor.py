# utils/ml_predictor.py
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score
import joblib
import os
import streamlit as st
from .advanced_algorithms import ELO_Rating

MODEL_PATH = "ml_models/"
os.makedirs(MODEL_PATH, exist_ok=True)

class MLPredictor:
    def __init__(self):
        self.models = {}
        self.feature_columns = None
        self._load_models()

    def _load_models(self):
        for target in ['over25', 'btts', 'result']:
            path = os.path.join(MODEL_PATH, f"{target}_model.pkl")
            if os.path.exists(path):
                self.models[target] = joblib.load(path)
                print(f"✅ Loaded {target} model")
            else:
                self.models[target] = None

    def train(self, league_accum):
        """Train models on all historical data."""
        print("🧠 Training ML models...")
        X, y = self._extract_features_and_labels(league_accum)

        if len(X) == 0:
            print("❌ No training data available. Skipping ML training.")
            return False

        self.feature_columns = X.columns.tolist()
        print(f"   Features: {self.feature_columns}")

        # Convert y lists to pandas Series
        for target in ['over25', 'btts', 'result']:
            # Convert to pandas Series
            y_series = pd.Series(y[target])
            
            # Remove rows with NaN labels (if any)
            mask = y_series.notna()
            X_train_all = X[mask]
            y_train_all = y_series[mask]

            if len(X_train_all) < 100:
                print(f"⚠️ Not enough data for {target} (needs 100, has {len(X_train_all)})")
                continue

            # Split
            X_train, X_test, y_train, y_test = train_test_split(
                X_train_all, y_train_all, test_size=0.2, random_state=42,
                stratify=y_train_all if target != 'result' else None
            )

            if target == 'result':
                model = xgb.XGBClassifier(
                    n_estimators=200, max_depth=6, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    objective='multi:softprob', num_class=3,
                    random_state=42, eval_metric='mlogloss'
                )
            else:
                model = xgb.XGBClassifier(
                    n_estimators=200, max_depth=6, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    random_state=42, eval_metric='logloss'
                )

            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            acc = accuracy_score(y_test, y_pred)
            if target != 'result':
                auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
                print(f"   {target.upper()} – Acc: {acc*100:.1f}%, AUC: {auc*100:.1f}%")
            else:
                print(f"   {target.upper()} – Acc: {acc*100:.1f}%")

            joblib.dump(model, os.path.join(MODEL_PATH, f"{target}_model.pkl"))
            self.models[target] = model

        print("✅ ML models trained and saved.")
        return True

    def predict_match(self, home, away):
        """Predict probabilities for a match using ML models."""
        # Use session state for context
        if 'league_accum' not in st.session_state:
            return self._default_probs()

        # Find league for this match
        from config import LEAGUE_TEAMS
        league = None
        for l, teams in LEAGUE_TEAMS.items():
            if home in teams:
                league = l
                break
        if league is None:
            return self._default_probs()

        accum = st.session_state.league_accum.get(league)
        if not accum:
            return self._default_probs()

        matchday = st.session_state.get('current_matchday', 0)

        # Build ELO from all matches before this matchday
        elo = ELO_Rating()
        for entry in accum['results']:
            if entry['day'] >= matchday:
                break
            for (h, a), data in entry['data'].items():
                ft_h, ft_a = data['ft']
                elo.update_ratings(h, a, ft_h, ft_a)

        # Extract features
        feat = self._extract_features_for_match(home, away, league, accum, matchday, elo.ratings)
        if feat is None:
            return self._default_probs()

        X = pd.DataFrame([feat])
        if self.feature_columns:
            X = X[self.feature_columns]

        probs = {}
        for target, model in self.models.items():
            if model:
                if target == 'result':
                    proba = model.predict_proba(X)[0]
                    probs['home_win'] = proba[0]
                    probs['draw'] = proba[1]
                    probs['away_win'] = proba[2]
                else:
                    probs[target] = model.predict_proba(X)[0][1]

        return {
            'home_win': probs.get('home_win', 0.33),
            'draw': probs.get('draw', 0.33),
            'away_win': probs.get('away_win', 0.33),
            'over25': probs.get('over25', 0.5),
            'btts': probs.get('btts', 0.5)
        }

    def _default_probs(self):
        return {'home_win': 0.33, 'draw': 0.33, 'away_win': 0.33, 'over25': 0.5, 'btts': 0.5}

    def _extract_features_and_labels(self, league_accum):
        rows = []
        labels = {'over25': [], 'btts': [], 'result': []}

        for league, accum in league_accum.items():
            results_sorted = sorted(accum['results'], key=lambda x: x['day'])
            elo = ELO_Rating()

            for entry in results_sorted:
                day = entry['day']
                data = entry['data']
                for (home, away), scores in data.items():
                    ft_h, ft_a = scores['ft']
                    feat = self._extract_features_for_match(
                        home, away, league, accum, day, elo.ratings
                    )
                    if feat is None:
                        continue
                    rows.append(feat)
                    labels['over25'].append(1 if (ft_h + ft_a) >= 3 else 0)
                    labels['btts'].append(1 if (ft_h > 0 and ft_a > 0) else 0)
                    if ft_h > ft_a:
                        labels['result'].append(0)
                    elif ft_h == ft_a:
                        labels['result'].append(1)
                    else:
                        labels['result'].append(2)
                    elo.update_ratings(home, away, ft_h, ft_a)

        if not rows:
            return pd.DataFrame(), labels

        X = pd.DataFrame(rows)
        self.feature_columns = X.columns.tolist()
        return X, labels

    def _extract_features_for_match(self, home, away, league, accum, matchday, elo_ratings):
        def get_team_matches(team, before_day):
            matches = []
            for entry in accum['results']:
                if entry['day'] >= before_day:
                    break
                for (h, a), data in entry['data'].items():
                    if h == team or a == team:
                        matches.append((entry['day'], data, h == team))
            return matches

        home_matches = get_team_matches(home, matchday)
        away_matches = get_team_matches(away, matchday)

        if not home_matches or not away_matches:
            return None

        def compute_stats(matches, team, is_home):
            if not matches:
                return (0, 0, 0, 0, 0)
            gs = []
            gc = []
            over25 = 0
            btts = 0
            for _, data, was_home in matches:
                if (is_home and was_home) or (not is_home and not was_home):
                    if was_home:
                        sg, cg = data['ft'][0], data['ft'][1]
                    else:
                        sg, cg = data['ft'][1], data['ft'][0]
                    gs.append(sg)
                    gc.append(cg)
                    if sg + cg >= 3:
                        over25 += 1
                    if sg > 0 and cg > 0:
                        btts += 1
            count = len(gs)
            if count == 0:
                return (0, 0, 0, 0, 0)
            return (sum(gs)/count, sum(gc)/count, count, over25/count, btts/count)

        h_avg_scored, h_avg_conceded, h_count, h_over25, h_btts = compute_stats(home_matches, home, True)
        a_avg_scored, a_avg_conceded, a_count, a_over25, a_btts = compute_stats(away_matches, away, False)

        home_last5 = home_matches[-5:]
        away_last5 = away_matches[-5:]

        def form_score(matches, team):
            points = 0
            for _, data, was_home in matches:
                if was_home:
                    gs, gc = data['ft'][0], data['ft'][1]
                else:
                    gs, gc = data['ft'][1], data['ft'][0]
                if gs > gc:
                    points += 3
                elif gs == gc:
                    points += 1
            return points / len(matches) if matches else 0

        home_form = form_score(home_last5, home)
        away_form = form_score(away_last5, away)

        home_elo = elo_ratings.get(home, 1500)
        away_elo = elo_ratings.get(away, 1500)
        elo_diff = home_elo - away_elo

        feat = {
            'h_avg_scored': h_avg_scored,
            'h_avg_conceded': h_avg_conceded,
            'a_avg_scored': a_avg_scored,
            'a_avg_conceded': a_avg_conceded,
            'h_over25': h_over25,
            'h_btts': h_btts,
            'a_over25': a_over25,
            'a_btts': a_btts,
            'home_form': home_form,
            'away_form': away_form,
            'elo_diff': elo_diff,
            'h_count': h_count,
            'a_count': a_count,
        }
        return feat