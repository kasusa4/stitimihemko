# utils/automation_engine.py
import time
from datetime import datetime
import streamlit as st
from .live_results_scraper import LiveResultsScraper, LEAGUES
from .simulation_utils import LeagueStats
from .advanced_algorithms import ELO_Rating, MarkovChainPredictor, LogisticPredictor, HighConcedingDetector, ConsensusVoter
from .prediction_boost import LeakyDefenseDetector, FormTrendDetector, CorrectScorePredictor
from .apex_utils import generate_summary
from .accuracy_tracker import AccuracyTracker
from .api_client import BetpawaAPIClient
from config import LEAGUE_TEAMS, ROUND_IDS
import os
import json

from collections import defaultdict
from .ml_predictor import MLPredictor
from .advanced_algorithms import MLPredictorWrapper

class AutomationEngine:
    def __init__(self):
        self.scraper = LiveResultsScraper()
        self.api = BetpawaAPIClient()
        self.last_run = None
        self.predictions_cache = None
        self.results_cache = None

        #modellllll
        self.ml_predictor = MLPredictor()
        # Train if needed
        if not any(self.ml_predictor.models.values()):
            self.ml_predictor.train(st.session_state.league_accum)

    def _update_accum(self, live):
        md = live['matchday']
        for league, matches in live['results'].items():
            if league not in st.session_state.league_accum:
                continue
            accum = st.session_state.league_accum[league]
            existing = [item['day'] for item in accum['results'] if isinstance(item.get('day'), int)]
            if md not in existing:
                data = {}
                for m in matches:
                    data[(m['home'], m['away'])] = {'ft': (m['ft_h'], m['ft_a']), 'ht': (m['ht_h'], m['ht_a'])}
                accum['results'].append({'day': md, 'data': data})
                print(f"   ✅ Added MD{md} to {league} ({len(matches)} matches)")

    def _store_results_for_accuracy(self, matchday, results_by_league):
        tracker = AccuracyTracker()
        results = []
        for league, matches in results_by_league.items():
            for m in matches:
                ft_h = m['ft_h']; ft_a = m['ft_a']
                if ft_h > ft_a:
                    result = 'Home Win'
                elif ft_h == ft_a:
                    result = 'Draw'
                else:
                    result = 'Away Win'
                results.append({
                    'home': m['home'],
                    'away': m['away'],
                    'result': result,
                    'ft_h': ft_h,
                    'ft_a': ft_a,
                    'over25_actual': (ft_h + ft_a) >= 3,
                    'btts_actual': (ft_h > 0 and ft_a > 0)
                })
        tracker.add_results(matchday, results)

    def _store_predictions_for_accuracy(self, matchday, predictions):
        tracker = AccuracyTracker()
        preds = []
        for p in predictions:
            # Extract home and away from 'Match' field
            match_str = p.get('Match', '')
            if ' vs ' in match_str:
                home, away = match_str.split(' vs ', 1)
            elif ' - ' in match_str:
                home, away = match_str.split(' - ', 1)
            else:
                home, away = 'Unknown', 'Unknown'

            # Determine top pick
            if p['home_win'] > p['draw'] and p['home_win'] > p['away_win']:
                top_pick = 'Home Win'
            elif p['away_win'] > p['draw'] and p['away_win'] > p['home_win']:
                top_pick = 'Away Win'
            else:
                top_pick = 'Draw'

            confidence = max(p['home_win'], p['draw'], p['away_win'])
            over25 = p['over25'] > 0.5
            btts = p['btts'] > 0.5

            # Add to tracker (per league)
            league = p.get('League', 'Unknown')
            tracker.add_prediction_for_league(league, home, away, top_pick, confidence, over25, btts)

            # Also add to the general predictions list
            preds.append({
                'home': home,
                'away': away,
                'top_pick': top_pick,
                'confidence': confidence,
                'over25': over25,
                'btts': btts,
                'home_win': p['home_win'],
                'draw': p['draw'],
                'away_win': p['away_win']
            })

        tracker.add_predictions(matchday, preds)

    def _generate_early_picks(self, limit=2, sims=2000):
        from config import LEAGUE_TEAMS
        all_picks = []
        for league_name in LEAGUE_TEAMS.keys():
            if league_name not in st.session_state.league_accum:
                continue
            accum = st.session_state.league_accum[league_name]
            days = [item['day'] for item in accum['results'] if isinstance(item.get('day'), int)]
            if len(days) < 3:
                continue
            if not accum.get('fixtures_data'):
                continue
            master = LEAGUE_TEAMS[league_name]
            preds = self._run_consensus(league_name, accum, master, sims=sims)
            if not preds:
                continue
            sorted_preds = sorted(preds, key=lambda x: x.get('over25_raw', 0), reverse=True)
            for p in sorted_preds[:limit]:
                match_str = p.get('Match', '')
                if ' vs ' in match_str:
                    home, away = match_str.split(' vs ', 1)
                elif ' - ' in match_str:
                    home, away = match_str.split(' - ', 1)
                else:
                    home, away = 'Unknown', 'Unknown'
                all_picks.append({
                    'league': league_name,  # <-- ADDED
                    'match': (home, away),
                    'home_win': float(p.get('Home Win', '0%').replace('%', '')) / 100,
                    'draw': float(p.get('Draw', '0%').replace('%', '')) / 100,
                    'away_win': float(p.get('Away Win', '0%').replace('%', '')) / 100,
                    'over25': p.get('over25_raw', 0),
                    'btts': float(p.get('BTTS', '0%').replace('%', '')) / 100,
                    'most_likely': p.get('Most Likely', 'N/A'),
                    'Confidence': p.get('Confidence', 0),
                    'Top Pick': p.get('Top Pick', 'N/A'),
                    'Rating': p.get('Rating', 'N/A')
                })
        return all_picks

    def get_early_over25_picks(self, limit=2, sims=2000):
        return self._generate_early_picks(limit=limit, sims=sims)

    def _run_predictions(self):
        from config import LEAGUE_TEAMS
        all_predictions = []
        for league_name in LEAGUE_TEAMS.keys():
            if league_name not in st.session_state.league_accum:
                continue
            accum = st.session_state.league_accum[league_name]
            days = [item['day'] for item in accum['results'] if isinstance(item.get('day'), int)]
            if len(days) >= 15 and accum.get('fixtures_data'):
                master_teams = LEAGUE_TEAMS[league_name]
                preds = self._run_consensus(league_name, accum, master_teams)
                if preds:
                    all_predictions.extend(preds)
                    print(f"   🧠 {league_name}: {len(preds)} predictions")
        return all_predictions

    def _run_consensus(self, league, accum, master, sims=10000):
        stats = LeagueStats(league)
        elo = ELO_Rating()
        markov = MarkovChainPredictor()
        logistic = LogisticPredictor()
        high = HighConcedingDetector()
        leaky = LeakyDefenseDetector()
        form = FormTrendDetector()
        correct = CorrectScorePredictor()

        for item in accum['results']:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data['ft']; ht_h, ht_a = data['ht']
                stats.add_match(home, away, ft_h, ft_a, ht_h, ht_a)
                elo.update_ratings(home, away, ft_h, ft_a)
                if ft_h > ft_a:
                    markov.add_result(home,'W'); markov.add_result(away,'L')
                elif ft_h == ft_a:
                    markov.add_result(home,'D'); markov.add_result(away,'D')
                else:
                    markov.add_result(home,'L'); markov.add_result(away,'W')
                logistic.add_match(home, away, ft_h, ft_a)
                high.add_match(home, away, ft_h, ft_a)
                leaky.add_match(home, away, ft_h, ft_a)
                if ft_h > ft_a:
                    form.add_match(home,'W',ft_h,ft_a); form.add_match(away,'L',ft_a,ft_h)
                elif ft_h == ft_a:
                    form.add_match(home,'D',ft_h,ft_a); form.add_match(away,'D',ft_a,ft_h)
                else:
                    form.add_match(home,'L',ft_h,ft_a); form.add_match(away,'W',ft_a,ft_h)

        strong = [t for t in master if elo.ratings.get(t,1500)>1600]
        high.set_strong_teams(strong)

        voter = ConsensusVoter()
        voter.add_algorithm('poisson', stats)
        voter.add_algorithm('elo', elo)
        voter.add_algorithm('markov', markov)
        voter.add_algorithm('logistic', logistic)

        # Add ML algorithm
        ml_wrapper = MLPredictorWrapper(self.ml_predictor)
        voter.add_algorithm('ml', ml_wrapper)

        preds = []
        for home, away in accum['fixtures_data']:
            cons = voter.predict_match(home, away)
            poiss = stats.predict_match(home, away, patterns=None, simulations=sims)
            leaky_analysis = leaky.analyze_match(home, away)
            ht = form.get_trend(home); at = form.get_trend(away)
            hf = form.get_form_string(home); af = form.get_form_string(away)
            scores = correct.predict(poiss.get('home_lambda',1.0), poiss.get('away_lambda',1.0), top_n=3)
            hc = high.check_match(home, away)
            warnings = [w for w in [hc.get('warning'), leaky_analysis.get('warning')] if w]
            pred = {
                "match": (home, away),
                "home_win": cons['home_win'],
                "draw": cons['draw'],
                "away_win": cons['away_win'],
                "most_likely": poiss['most_likely'],
                "btts": poiss['btts'],
                "over25": poiss['over25'],
                "agreement": cons['agreement'],
                "algorithms_used": cons['algorithms_used'],
                "warnings": warnings,
                "home_trend": ht, "away_trend": at,
                "home_form": hf, "away_form": af,
                "correct_scores": scores,
                "leaky_warning": leaky_analysis.get('warning'),
                "leaky_hint": leaky_analysis.get('prediction_hint'),
                "over25_boost": leaky_analysis.get('over25_boost',0),
                "btts_boost": leaky_analysis.get('btts_boost',0),
                "both_leaky": leaky_analysis.get('both_leaky',False),
                "massacre": leaky_analysis.get('massacre_detected',False)
            }
            preds.append(pred)

        enriched = generate_summary(preds, league)
        for e,p in zip(enriched, preds):
            e['Agreement'] = f"{p['agreement']*100:.0f}%"
            e['Algorithms'] = p['algorithms_used']
            if p.get('warnings'): e['Warning'] = p['warnings'][0][:100]
            if p.get('over25_boost',0)>0: e['O2.5 Boost'] = f"+{p['over25_boost']*100:.0f}%"
            if p.get('home_trend'): e['H Trend'] = '⬆️' if p['home_trend']=='up' else '⬇️' if p['home_trend']=='down' else '➡️'
            if p.get('away_trend'): e['A Trend'] = '⬆️' if p['away_trend']=='up' else '⬇️' if p['away_trend']=='down' else '➡️'
            if p.get('correct_scores'): e['Top Scores'] = ' | '.join(p['correct_scores'][:3])
            e['over25_raw'] = p['over25']
        return enriched
    
    

    # utils/automation_engine.py (inside class AutomationEngine)

    def fetch_fixtures_for_all_leagues(self):
        """
        Fetch fixtures for all 5 VunjaBei leagues.
        Always stores fixtures if none exist yet; otherwise, updates only if newer.
        """
        from .virtual_api import VirtualAPI
        from config import LEAGUE_TEAMS

        if 'vunja_league_accum' not in st.session_state:
            st.session_state.vunja_league_accum = {}
            for name in LEAGUE_TEAMS.keys():
                st.session_state.vunja_league_accum[name] = {
                    'results': [],
                    'fixtures_data': None,
                    'processed': False
                }

        vunja_accum = st.session_state.vunja_league_accum
        api = VirtualAPI()

        vunja_leagues = [
            'English League',
            'Spanish League',
            'Italian League',
            'German League',
            'French League'
        ]

        for league_name in vunja_leagues:
            if league_name not in vunja_accum:
                continue

            accum = vunja_accum[league_name]
            existing_weeks = [item['day'] for item in accum['results'] if isinstance(item.get('day'), int)]
            last_week = max(existing_weeks) if existing_weeks else 0

            data = api.fetch_fixtures_for_league(league_name)
            if data and data.get('matches'):
                fixture_week = data.get('week_id')
                if fixture_week is None:
                    print(f"   ⚠️ No week_id for {league_name}, skipping.")
                    continue

                # --- NEW LOGIC: Always store if none exist, or if newer ---
                if accum['fixtures_data'] is None or fixture_week > last_week:
                    fixture_tuples = [(m['home'], m['away']) for m in data['matches']]
                    accum['fixtures_data'] = fixture_tuples
                    print(f"   📋 Stored fixtures for {league_name} (Week {fixture_week})")
                else:
                    print(f"   ⏭️ Fixtures for {league_name} (Week {fixture_week}) not newer than last result week ({last_week}), skipping.")
            else:
                print(f"   ⚠️ No fixtures for {league_name}")
        return vunja_accum


    def run_vunja_pipeline(self):
        """
        Incremental sync: one week per run, but always refresh predictions
        with the latest fixtures and all available data.
        """
        from .virtual_api import VirtualAPI
        from config import LEAGUE_TEAMS
        import os
        import json

        # ---------- 1. ENSURE DATA STORE ----------
        if 'vunja_league_accum' not in st.session_state:
            st.session_state.vunja_league_accum = {}
            for name in LEAGUE_TEAMS.keys():
                st.session_state.vunja_league_accum[name] = {
                    'results': [],
                    'fixtures_data': None,
                    'fixtures_week': None,
                    'processed': False
                }

        vunja_accum = st.session_state.vunja_league_accum
        api = VirtualAPI()

        # ---------- 2. LOAD PROGRESS ----------
        progress = self._load_progress()
        if 'leagues' not in progress:
            progress['leagues'] = {}

        # ---------- 3. LEAGUE CONFIG ----------
        vunja_leagues = ['English League', 'Spanish League', 'Italian League', 'German League', 'French League']
        CHAMP_MAP = {
            'English League': 1,
            'Spanish League': 4,
            'Italian League': 0,
            'German League': 3,
            'French League': 2,
        }

        # ---------- 4. FETCH COMPETITIONS (optional) ----------
        comps = api.fetch_competitions()
        if comps:
            print(f"   📡 Competitions: {dict(zip(comps['ids'], comps['names']))}")

        newly_inserted = False

        # ---------- 5. FETCH FIXTURES FOR ALL LEAGUES (REFRESH) ----------
        print("   🔄 Refreshing fixtures for all leagues...")
        self.fetch_fixtures_for_all_leagues()  # updates accum['fixtures_data'] and accum['fixtures_week']

        # ---------- 6. PROCESS EACH LEAGUE (ONE WEEK RESULTS) ----------
        for league_name in vunja_leagues:
            champ_type = CHAMP_MAP.get(league_name)
            if champ_type is None:
                continue

            current_info = api.fetch_current_week(champ_type)
            if not current_info:
                print(f"   ⚠️ Could not fetch current info for {league_name}")
                continue

            current_season_id = current_info.get('season_id')
            current_week = current_info.get('week_id')

            # Initialize progress
            if league_name not in progress['leagues']:
                progress['leagues'][league_name] = {
                    'last_completed_week': 0,
                    'season_id': current_season_id,
                    'season_complete': False
                }

            league_progress = progress['leagues'][league_name]
            season_id = league_progress.get('season_id', current_season_id)
            last_completed = league_progress.get('last_completed_week', 0)
            season_complete = league_progress.get('season_complete', False)

            # New season detection
            if season_complete and current_season_id and current_season_id != season_id:
                print(f"   🆕 New season detected for {league_name}: {current_season_id}")
                league_progress['last_completed_week'] = 0
                league_progress['season_id'] = current_season_id
                league_progress['season_complete'] = False
                self._save_progress(progress)
                season_id = current_season_id
                last_completed = 0
                season_complete = False

            if season_complete:
                print(f"   ⏭️ {league_name} season complete, waiting for new season.")
                continue

            # Consistency check
            accum = vunja_accum[league_name]
            stored_weeks = [item['day'] for item in accum['results'] if isinstance(item.get('day'), int)]
            if stored_weeks:
                max_stored = max(stored_weeks)
                if max_stored > last_completed:
                    print(f"   ⏫ Correcting progress for {league_name}: last_completed {last_completed} → {max_stored}")
                    league_progress['last_completed_week'] = max_stored
                    self._save_progress(progress)
                    last_completed = max_stored

            next_week = last_completed + 1

            print(f"   🔍 Checking {league_name} – last completed: {last_completed}, next: {next_week}")

            # Fetch results for next week
            try:
                data = api.fetch_results(next_week, season_id)
            except Exception as e:
                if "400" in str(e) or "Bad Request" in str(e) or "404" in str(e):
                    if next_week == 1 and current_week and current_week > 1:
                        print(f"   ⏭️ Week 1 not found, jumping to current week {current_week}.")
                        league_progress['last_completed_week'] = current_week - 1
                        self._save_progress(progress)
                        continue
                    else:
                        league_progress['season_complete'] = True
                        self._save_progress(progress)
                        print(f"   🏁 {league_name} season complete (no data for week {next_week}).")
                        continue
                else:
                    raise e

            if not data or not data.get('matches'):
                print(f"   ⏹️ No data for week {next_week} in {league_name}.")
                continue

            # Store results if not already present
            if next_week in stored_weeks:
                print(f"   ⏭️ Week {next_week} already stored in {league_name}, skipping.")
            else:
                matches_by_league = self._assign_leagues(data['matches'])
                league_matches = matches_by_league.get(league_name, [])
                if league_matches:
                    data_dict = {}
                    for m in league_matches:
                        data_dict[(m['home'], m['away'])] = {
                            'ft': (m['ft_h'], m['ft_a']),
                            'ht': (m['ht_h'], m['ht_a'])
                        }
                    accum['results'].append({'day': next_week, 'data': data_dict})
                    print(f"   📦 Added {len(league_matches)} matches to {league_name} (Week {next_week})")
                    newly_inserted = True
                    # Update progress only if we inserted a new week
                    league_progress['last_completed_week'] = next_week
                    self._save_progress(progress)

            # (Fixtures are already refreshed, no need to fetch again)

        # ---------- 7. GENERATE PREDICTIONS FOR ALL LEAGUES WITH FIXTURES ----------
        all_predictions = []
        for league_name in vunja_leagues:
            accum = vunja_accum.get(league_name)
            if not accum:
                continue
            fixtures = accum.get('fixtures_data')
            if fixtures:
                master_teams = LEAGUE_TEAMS.get(league_name, [])
                preds = self._run_consensus_on_accum(league_name, accum, master_teams)
                if preds:
                    all_predictions.extend(preds)
                    print(f"   🧠 {league_name}: {len(preds)} predictions")
            else:
                print(f"   ⏸️ {league_name}: predictions skipped (no fixtures).")

        # ---------- 8. STORE PREDICTIONS (ALWAYS OVERWRITE) ----------
        if all_predictions:
            st.session_state.current_predictions = all_predictions
            st.session_state.vunja_predictions = all_predictions
            st.session_state.vunja_last_update = datetime.now()
            print(f"   ✅ Stored {len(all_predictions)} predictions in session state")
        else:
            # If no predictions, keep existing but still update timestamp? (optional)
            # We'll keep existing and not overwrite.
            print("   ⚠️ No predictions generated – keeping existing ones.")
            # Optionally, you can still update timestamp to show last check:
            # st.session_state.vunja_last_update = datetime.now()

        # ---------- 9. SAVE SESSION ----------
        session_id = None
        try:
            from .session_manager import SessionManager
            sm = SessionManager(max_sessions=50)
            all_weeks = []
            for acc in vunja_accum.values():
                all_weeks.extend([item['day'] for item in acc['results'] if isinstance(item.get('day'), int)])
            next_md = max(all_weeks) + 1 if all_weeks else 26
            metadata = {'platform': 'vunja', 'fetched_weeks': list(progress['leagues'].keys())}
            session_id = sm.save_session(
                vunja_accum,
                all_predictions,
                list(LEAGUE_TEAMS.keys()),
                metadata=metadata,
                matchday=next_md
            )
            print(f"   💾 Session {session_id} saved.")
        except Exception as e:
            print(f"   ⚠️ Session save failed: {e}")

        st.session_state.pipeline_running = False
        return {
            'platform': 'vunja',
            'next_matchday': next_md if 'next_md' in locals() else 26,
            'matches_fetched': 1 if newly_inserted else 0,
            'predictions': all_predictions,
            'session_id': session_id,
            'newly_inserted': newly_inserted
        }

    def _assign_leagues(self, matches):
            """Assign matches to the 5 VunjaBei leagues based on team names."""
            from config import LEAGUE_TEAMS
            from collections import defaultdict

            VUNJA_LEAGUES = [
                'English League',
                'Spanish League',
                'Italian League',
                'German League',
                'French League'
            ]

            result = defaultdict(list)
            all_teams = {}
            for league in VUNJA_LEAGUES:
                if league in LEAGUE_TEAMS:
                    for team in LEAGUE_TEAMS[league]:
                        all_teams[team] = league

            for m in matches:
                home = m['home']
                away = m['away']
                league = all_teams.get(home) or all_teams.get(away)
                if not league:
                    league = 'English League'  # fallback
                result[league].append(m)
            return result

        

    def _run_consensus_on_accum(self, league_name, accum, master_teams, sims=10000):
        """
        Run consensus prediction on a given accum (VunjaBei or any other).
        Returns enriched predictions list.
        """
        stats = LeagueStats(league_name)
        elo = ELO_Rating()
        markov = MarkovChainPredictor()
        logistic = LogisticPredictor()
        high = HighConcedingDetector()
        leaky = LeakyDefenseDetector()
        form = FormTrendDetector()
        correct = CorrectScorePredictor()

        for item in accum['results']:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data['ft']
                ht_h, ht_a = data['ht']
                stats.add_match(home, away, ft_h, ft_a, ht_h, ht_a)
                elo.update_ratings(home, away, ft_h, ft_a)
                if ft_h > ft_a:
                    markov.add_result(home, 'W')
                    markov.add_result(away, 'L')
                elif ft_h == ft_a:
                    markov.add_result(home, 'D')
                    markov.add_result(away, 'D')
                else:
                    markov.add_result(home, 'L')
                    markov.add_result(away, 'W')
                logistic.add_match(home, away, ft_h, ft_a)
                high.add_match(home, away, ft_h, ft_a)
                leaky.add_match(home, away, ft_h, ft_a)
                if ft_h > ft_a:
                    form.add_match(home, 'W', ft_h, ft_a)
                    form.add_match(away, 'L', ft_a, ft_h)
                elif ft_h == ft_a:
                    form.add_match(home, 'D', ft_h, ft_a)
                    form.add_match(away, 'D', ft_a, ft_h)
                else:
                    form.add_match(home, 'L', ft_h, ft_a)
                    form.add_match(away, 'W', ft_a, ft_h)

        strong = [t for t in master_teams if elo.ratings.get(t, 1500) > 1600]
        high.set_strong_teams(strong)

        voter = ConsensusVoter()
        voter.add_algorithm('poisson', stats)
        voter.add_algorithm('elo', elo)
        voter.add_algorithm('markov', markov)
        voter.add_algorithm('logistic', logistic)

        # Add ML algorithm if available
        if hasattr(self, 'ml_predictor'):
            from .advanced_algorithms import MLPredictorWrapper
            ml_wrapper = MLPredictorWrapper(self.ml_predictor)
            voter.add_algorithm('ml', ml_wrapper)

        preds = []
        for home, away in accum['fixtures_data']:
            cons = voter.predict_match(home, away)
            poiss = stats.predict_match(home, away, patterns=None, simulations=sims)
            leaky_analysis = leaky.analyze_match(home, away)
            ht = form.get_trend(home)
            at = form.get_trend(away)
            hf = form.get_form_string(home)
            af = form.get_form_string(away)
            scores = correct.predict(poiss.get('home_lambda', 1.0), poiss.get('away_lambda', 1.0), top_n=3)
            hc = high.check_match(home, away)
            warnings = [w for w in [hc.get('warning'), leaky_analysis.get('warning')] if w]

            pred = {
                "match": (home, away),
                "home_win": cons['home_win'],
                "draw": cons['draw'],
                "away_win": cons['away_win'],
                "most_likely": poiss['most_likely'],
                "btts": poiss['btts'],
                "over25": poiss['over25'],
                "agreement": cons['agreement'],
                "algorithms_used": cons['algorithms_used'],
                "warnings": warnings,
                "home_trend": ht,
                "away_trend": at,
                "home_form": hf,
                "away_form": af,
                "correct_scores": scores,
                "leaky_warning": leaky_analysis.get('warning'),
                "leaky_hint": leaky_analysis.get('prediction_hint'),
                "over25_boost": leaky_analysis.get('over25_boost', 0),
                "btts_boost": leaky_analysis.get('btts_boost', 0),
                "both_leaky": leaky_analysis.get('both_leaky', False),
                "massacre": leaky_analysis.get('massacre_detected', False)
            }
            preds.append(pred)

        enriched = generate_summary(preds, league_name)
        for e, p in zip(enriched, preds):
            e['Agreement'] = f"{p['agreement']*100:.0f}%"
            e['Algorithms'] = p['algorithms_used']
            if p.get('warnings'):
                e['Warning'] = p['warnings'][0][:100]
            if p.get('over25_boost', 0) > 0:
                e['O2.5 Boost'] = f"+{p['over25_boost']*100:.0f}%"
            if p.get('home_trend'):
                e['H Trend'] = '⬆️' if p['home_trend'] == 'up' else '⬇️' if p['home_trend'] == 'down' else '➡️' if p['home_trend'] == 'stable' else '❓'
            if p.get('away_trend'):
                e['A Trend'] = '⬆️' if p['away_trend'] == 'up' else '⬇️' if p['away_trend'] == 'down' else '➡️' if p['away_trend'] == 'stable' else '❓'
            if p.get('correct_scores'):
                e['Top Scores'] = ' | '.join(p['correct_scores'][:3])
            e['over25_raw'] = p['over25']

        return enriched
    

    # utils/automation_engine.py – inside AutomationEngine class

    def _load_progress(self):
        """Load progress from JSON file."""
        if os.path.exists('vunja_progress.json'):
            try:
                with open('vunja_progress.json', 'r') as f:
                    return json.load(f)
            except:
                return {'leagues': {}}
        return {'leagues': {}}

    def _save_progress(self, progress):
        """Save progress to JSON file."""
        with open('vunja_progress.json', 'w') as f:
            json.dump(progress, f, indent=2)