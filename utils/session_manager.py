# utils/session_manager.py
import json
import os
from datetime import datetime
from collections import defaultdict

class SessionManager:
    """
    Manages prediction sessions with JSON file storage.
    Auto-prunes to last 50 sessions.
    """
    def __init__(self, max_sessions=50):
        self.max_sessions = max_sessions
        self.data_file = 'apex_sessions.json'
        self.sessions = []
        self._load_from_json()
    
    def _load_from_json(self):
        """Load sessions from JSON file"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.sessions = data.get('sessions', [])
            except:
                self.sessions = []
        else:
            self.sessions = []
    
    def _save_to_json(self):
        """Save sessions to JSON file"""
        with open(self.data_file, 'w') as f:
            json.dump({'sessions': self.sessions}, f, indent=2, default=str)
    
    def _get_next_session_id(self):
        """Generate next session ID (padded 6 digits)"""
        if not self.sessions:
            return "000001"
        last_id = self.sessions[-1]['session_id']
        num = int(last_id) + 1
        return str(num).zfill(6)
    
    def _prune(self):
        """Remove oldest sessions if exceeding max_sessions"""
        if len(self.sessions) > self.max_sessions:
            self.sessions = self.sessions[-self.max_sessions:]
    
    def save_session(self, league_accum, all_predictions, league_names, metadata=None, matchday=None):
        """
        Save a new session with the current state.
        
        Args:
            league_accum: dict with league data (results, fixtures)
            all_predictions: list of prediction dicts (enriched)
            league_names: list of league names
            metadata: optional dict with extra info (platform, week_id, etc.)
            matchday: optional int (the matchday number for this session)
        
        Returns:
            session_id (str)
        """
        if metadata is None:
            metadata = {}
        if matchday is not None:
            metadata['matchday'] = matchday

        session_id = self._get_next_session_id()
        session_data = {
            'session_id': session_id,
            'created_at': datetime.now().isoformat(),
            'matchday': matchday,
            'leagues': {},
            'metadata': metadata,
            'predictions_by_league': {}
        }

        # Group predictions by league
        preds_by_league = {}
        for p in all_predictions:
            league = p.get('League', 'Unknown')
            if league not in preds_by_league:
                preds_by_league[league] = []
            preds_by_league[league].append(p)
        session_data['predictions_by_league'] = preds_by_league

        # Compute league metrics (from results & fixtures)
        for league in league_names:
            if league not in league_accum:
                continue
            accum = league_accum[league]
            results = accum.get('results', [])
            fixtures = accum.get('fixtures_data', [])
            metrics = self._extract_league_metrics(league, results, fixtures, all_predictions)
            session_data['leagues'][league] = metrics

        # Global metrics
        session_data['global'] = self._extract_global_metrics(all_predictions)

        self.sessions.append(session_data)
        self._prune()
        self._save_to_json()
        return session_id
    
    def _extract_league_metrics(self, league, results, fixtures, all_predictions):
        """Extract key metrics for a league."""
        metrics = {
            'total_matches': sum(len(item['data']) for item in results),
            'matchdays': len(results),
            'fixtures_count': len(fixtures) if fixtures else 0,
            'predictions': []
        }
        
        # Extract predictions for this league
        league_preds = [p for p in all_predictions if p.get('League') == league]
        if league_preds:
            sorted_preds = sorted(league_preds, key=lambda x: x.get('Confidence', 0), reverse=True)
            metrics['predictions'] = [
                {
                    'match': p['Match'],
                    'top_pick': p['Top Pick'],
                    'confidence': p['Confidence'],
                    'most_likely': p['Most Likely'],
                    'rating': p['Rating']
                }
                for p in sorted_preds[:5]
            ]
            
            home_win_avg = sum(p.get('Confidence', 0) for p in league_preds) / len(league_preds) if league_preds else 0
            metrics['avg_confidence'] = home_win_avg
            metrics['elite_count'] = sum(1 for p in league_preds if 'Elite' in p.get('Rating', ''))
            metrics['high_count'] = sum(1 for p in league_preds if 'High' in p.get('Rating', ''))
        
        # Compute dashboard-style metrics from results
        if results:
            team_goals = defaultdict(list)
            team_conceded = defaultdict(list)
            team_btts = defaultdict(int)
            team_over25 = defaultdict(int)
            team_matches = defaultdict(int)
            
            for item in results:
                for (home, away), data in item['data'].items():
                    ft_h, ft_a = data['ft']
                    team_goals[home].append(ft_h)
                    team_goals[away].append(ft_a)
                    team_conceded[home].append(ft_a)
                    team_conceded[away].append(ft_h)
                    team_matches[home] += 1
                    team_matches[away] += 1
                    if ft_h > 0 and ft_a > 0:
                        team_btts[home] += 1
                        team_btts[away] += 1
                    if ft_h + ft_a >= 3:
                        team_over25[home] += 1
                        team_over25[away] += 1
            
            # Over 2.5 leaders
            over25_leaders = sorted(
                [(team, team_over25[team]/team_matches[team]) for team in team_matches if team_matches[team] > 0],
                key=lambda x: x[1],
                reverse=True
            )[:5]
            metrics['over25_leaders'] = [{'team': t, 'pct': pct} for t, pct in over25_leaders]
            
            # BTTS leaders
            btts_leaders = sorted(
                [(team, team_btts[team]/team_matches[team]) for team in team_matches if team_matches[team] > 0],
                key=lambda x: x[1],
                reverse=True
            )[:5]
            metrics['btts_leaders'] = [{'team': t, 'pct': pct} for t, pct in btts_leaders]
            
            # Highest scoring teams
            high_scoring = sorted(
                [(team, sum(team_goals[team])/team_matches[team]) for team in team_matches if team_matches[team] > 0],
                key=lambda x: x[1],
                reverse=True
            )[:5]
            metrics['high_scoring'] = [{'team': t, 'avg': avg} for t, avg in high_scoring]
        
        return metrics
    
    def _extract_global_metrics(self, all_predictions):
        """Extract global metrics across all leagues."""
        if not all_predictions:
            return {}
        
        total = len(all_predictions)
        elite = sum(1 for p in all_predictions if 'Elite' in p.get('Rating', ''))
        high = sum(1 for p in all_predictions if 'High' in p.get('Rating', ''))
        avg_confidence = sum(p.get('Confidence', 0) for p in all_predictions) / total if total > 0 else 0
        
        sorted_picks = sorted(all_predictions, key=lambda x: x.get('Confidence', 0), reverse=True)[:5]
        top_picks = [
            {
                'league': p['League'],
                'match': p['Match'],
                'pick': p['Top Pick'],
                'confidence': p['Confidence']
            }
            for p in sorted_picks
        ]
        
        return {
            'total_predictions': total,
            'elite_count': elite,
            'high_count': high,
            'avg_confidence': avg_confidence,
            'top_picks': top_picks
        }
    
    def get_all_sessions(self):
        """Return all sessions"""
        return self.sessions
    
    def get_session(self, session_id):
        """Get a specific session by ID"""
        for s in self.sessions:
            if s['session_id'] == session_id:
                return s
        return None
    
    def compare_sessions(self):
        """Analyze patterns across sessions."""
        if len(self.sessions) < 2:
            return {"message": "Need at least 2 sessions to compare"}
        
        over25_teams = defaultdict(int)
        btts_teams = defaultdict(int)
        strong_teams = defaultdict(int)
        top_picks = defaultdict(int)
        
        for session in self.sessions:
            for league, metrics in session.get('leagues', {}).items():
                for leader in metrics.get('over25_leaders', []):
                    over25_teams[leader['team']] += 1
                for leader in metrics.get('btts_leaders', []):
                    btts_teams[leader['team']] += 1
                for scorer in metrics.get('high_scoring', []):
                    strong_teams[scorer['team']] += 1
            
            global_metrics = session.get('global', {})
            for pick in global_metrics.get('top_picks', []):
                top_picks[pick['pick']] += 1
        
        num_sessions = len(self.sessions)
        threshold = num_sessions * 0.5
        
        return {
            'over25_teams': [t for t, c in over25_teams.items() if c >= threshold],
            'btts_teams': [t for t, c in btts_teams.items() if c >= threshold],
            'strong_teams': [t for t, c in strong_teams.items() if c >= threshold],
            'top_picks': [p for p, c in top_picks.items() if c >= threshold],
            'total_sessions': num_sessions
        }
    
    def delete_all_sessions(self):
        """Delete all sessions"""
        self.sessions = []
        self._save_to_json()

    def delete_session(self, session_id):
        """Delete a specific session by ID."""
        self.sessions = [s for s in self.sessions if s['session_id'] != session_id]
        self._save_to_json()
        return True