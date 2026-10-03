# utils/advanced_pattern_detector.py
import re
import pandas as pd
import numpy as np
from collections import defaultdict, Counter
from datetime import datetime

class AdvancedPatternDetector:
    def __init__(self, results_data):
        """
        results_data: list of dicts with 'day' and 'data' (parsed matches)
        Each match data has 'ft' and 'ht' with (home_goals, away_goals)
        """
        self.results = results_data
        self.patterns = []
        self.formulas = []
        self.confidence_scores = {}
        self._analyze_all()
    
    def _analyze_all(self):
        """Run all analysis methods and generate formulas."""
        self._detect_streaks()
        self._detect_home_away_trends()
        self._detect_scoring_patterns()
        self._detect_first_goal_patterns()
        self._detect_second_half_comebacks()
        self._detect_goal_timing_patterns()
        self._detect_head_to_head_patterns()
        self._detect_scoreline_sequences()
        self._detect_goal_difference_patterns()
        self._generate_formulas()
        self._rank_formulas_by_confidence()
    
    def _detect_streaks(self):
        """Detect winning/losing/drawing streaks"""
        team_performance = defaultdict(list)
        
        for item in self.results:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data["ft"]
                team_performance[home].append(('W' if ft_h > ft_a else 'D' if ft_h == ft_a else 'L', 'H'))
                team_performance[away].append(('W' if ft_a > ft_h else 'D' if ft_h == ft_a else 'L', 'A'))
        
        for team, results in team_performance.items():
            last_5 = results[-5:] if len(results) >= 5 else results
            if len(last_5) >= 3:
                if all(r[0] == 'W' for r in last_5[:3]):
                    self.patterns.append({
                        'type': 'winning_streak',
                        'team': team,
                        'details': f"🔥 {team} is on a {len([r for r in last_5 if r[0]=='W'])}-match winning streak!",
                        'strength': 'high',
                        'confidence': 0.9
                    })
                elif all(r[0] == 'L' for r in last_5[:3]):
                    self.patterns.append({
                        'type': 'losing_streak',
                        'team': team,
                        'details': f"⚠️ {team} is on a {len([r for r in last_5 if r[0]=='L'])}-match losing streak!",
                        'strength': 'medium',
                        'confidence': 0.7
                    })
                elif all(r[0] == 'D' for r in last_5[:3]):
                    self.patterns.append({
                        'type': 'draw_streak',
                        'team': team,
                        'details': f"🤝 {team} is on a {len([r for r in last_5 if r[0]=='D'])}-match draw streak!",
                        'strength': 'medium',
                        'confidence': 0.6
                    })
    
    def _detect_home_away_trends(self):
        """Detect strong home/away performance"""
        home_results = defaultdict(list)
        away_results = defaultdict(list)
        
        for item in self.results:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data["ft"]
                home_results[home].append(ft_h - ft_a)
                away_results[away].append(ft_a - ft_h)
        
        for team in home_results:
            home_avg = sum(home_results[team]) / len(home_results[team]) if home_results[team] else 0
            away_avg = sum(away_results[team]) / len(away_results[team]) if away_results[team] else 0
            
            if home_avg > 0.5 and home_avg > away_avg + 0.5:
                self.patterns.append({
                    'type': 'home_specialist',
                    'team': team,
                    'details': f"🏠 {team} is a HOME SPECIALIST! Avg goal difference: +{home_avg:.1f} at home vs {away_avg:.1f} away",
                    'strength': 'high',
                    'confidence': 0.85
                })
            elif away_avg > 0.5 and away_avg > home_avg + 0.5:
                self.patterns.append({
                    'type': 'away_specialist',
                    'team': team,
                    'details': f"✈️ {team} is an AWAY SPECIALIST! Avg goal difference: +{away_avg:.1f} away vs {home_avg:.1f} home",
                    'strength': 'high',
                    'confidence': 0.85
                })
    
    def _detect_scoring_patterns(self):
        """Detect teams that score/concede consistently"""
        team_goals_scored = defaultdict(list)
        team_goals_conceded = defaultdict(list)
        
        for item in self.results:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data["ft"]
                team_goals_scored[home].append(ft_h)
                team_goals_scored[away].append(ft_a)
                team_goals_conceded[home].append(ft_a)
                team_goals_conceded[away].append(ft_h)
        
        for team in team_goals_scored:
            avg_scored = sum(team_goals_scored[team]) / len(team_goals_scored[team])
            avg_conceded = sum(team_goals_conceded[team]) / len(team_goals_conceded[team])
            
            if avg_scored >= 2.0:
                self.patterns.append({
                    'type': 'high_scoring',
                    'team': team,
                    'details': f"⚽ {team} is HIGH SCORING! Avg {avg_scored:.1f} goals/match",
                    'strength': 'high',
                    'confidence': 0.85
                })
            if avg_conceded <= 0.8:
                self.patterns.append({
                    'type': 'tight_defense',
                    'team': team,
                    'details': f"🛡️ {team} has a TIGHT DEFENSE! Only {avg_conceded:.1f} goals conceded/match",
                    'strength': 'high',
                    'confidence': 0.85
                })
            if avg_scored <= 0.7:
                self.patterns.append({
                    'type': 'low_scoring',
                    'team': team,
                    'details': f"🐌 {team} is LOW SCORING! Only {avg_scored:.1f} goals/match",
                    'strength': 'medium',
                    'confidence': 0.7
                })
    
    def _detect_first_goal_patterns(self):
        """Detect patterns around who scores first."""
        for item in self.results:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data["ft"]
                ht_h, ht_a = data["ht"]
                
                # First goal patterns
                if ft_h > 0 or ft_a > 0:
                    first_goal = 'home' if ft_h > 0 and (ft_h > ft_a or ft_a == 0) else 'away' if ft_a > 0 else 'draw'
                    if first_goal == 'home' and ft_h > ft_a:
                        self.patterns.append({
                            'type': 'first_goal_wins',
                            'team': home,
                            'opponent': away,
                            'details': f"⚡ When {home} scores first against {away}, they win!",
                            'strength': 'high',
                            'confidence': 0.85
                        })
    
    def _detect_second_half_comebacks(self):
        """Detect teams that consistently come back in the second half."""
        comeback_data = defaultdict(lambda: {'wins': 0, 'total': 0})
        for item in self.results:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data["ft"]
                ht_h, ht_a = data["ht"]
                for team, ht_score, ft_score in [(home, ht_h, ft_h), (away, ht_a, ft_a)]:
                    if ht_score < ft_score:
                        comeback_data[team]['wins'] += 1
                        comeback_data[team]['total'] += 1
        for team, stats in comeback_data.items():
            if stats['total'] >= 3:
                ratio = stats['wins'] / stats['total']
                if ratio >= 0.6:
                    self.patterns.append({
                        'type': 'second_half_comeback',
                        'team': team,
                        'details': f"💪 {team} is a 2nd HALF COMEBACK specialist! {ratio*100:.0f}% of wins come from behind.",
                        'strength': 'high',
                        'confidence': ratio
                    })
    
    def _detect_goal_timing_patterns(self):
        """Detect patterns in goal timing (early/late goals)."""
        early_goals = defaultdict(int)
        late_goals = defaultdict(int)
        total_matches = defaultdict(int)
        
        for item in self.results:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data["ft"]
                ht_h, ht_a = data["ht"]
                total_matches[home] += 1
                total_matches[away] += 1
                
                # Early goals (first 15 min) – we simulate from HT/FT
                if ht_h > 0:
                    early_goals[home] += 1
                if ht_a > 0:
                    early_goals[away] += 1
                
                # Late goals (second half)
                if ft_h - ht_h > 0:
                    late_goals[home] += 1
                if ft_a - ht_a > 0:
                    late_goals[away] += 1
        
        for team in total_matches:
            if total_matches[team] >= 3:
                early_ratio = early_goals[team] / total_matches[team]
                late_ratio = late_goals[team] / total_matches[team]
                
                if early_ratio >= 0.6:
                    self.patterns.append({
                        'type': 'early_goal_specialist',
                        'team': team,
                        'details': f"⏰ {team} scores EARLY! {early_ratio*100:.0f}% of matches have a first-half goal.",
                        'strength': 'medium',
                        'confidence': early_ratio
                    })
                if late_ratio >= 0.6:
                    self.patterns.append({
                        'type': 'late_goal_specialist',
                        'team': team,
                        'details': f"⏰ {team} scores LATE! {late_ratio*100:.0f}% of matches have a second-half goal.",
                        'strength': 'medium',
                        'confidence': late_ratio
                    })
    
    def _detect_head_to_head_patterns(self):
        """Detect head-to-head patterns between specific teams."""
        h2h_data = defaultdict(lambda: {'home_wins': 0, 'away_wins': 0, 'draws': 0, 'over25': 0, 'btts': 0})
        
        for item in self.results:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data["ft"]
                key = tuple(sorted([home, away]))
                h2h_data[key]['total'] = h2h_data[key].get('total', 0) + 1
                if ft_h > ft_a:
                    h2h_data[key]['home_wins'] += 1
                elif ft_a > ft_h:
                    h2h_data[key]['away_wins'] += 1
                else:
                    h2h_data[key]['draws'] += 1
                if ft_h + ft_a >= 3:
                    h2h_data[key]['over25'] += 1
                if ft_h > 0 and ft_a > 0:
                    h2h_data[key]['btts'] += 1
        
        for (home, away), stats in h2h_data.items():
            if stats.get('total', 0) >= 2:
                total = stats['total']
                over25_ratio = stats['over25'] / total
                btts_ratio = stats['btts'] / total
                home_win_ratio = stats['home_wins'] / total
                
                if over25_ratio >= 0.6:
                    self.patterns.append({
                        'type': 'h2h_over25',
                        'teams': f"{home} vs {away}",
                        'details': f"⚽ {home} vs {away}: {over25_ratio*100:.0f}% of meetings go Over 2.5!",
                        'strength': 'high',
                        'confidence': over25_ratio
                    })
                if btts_ratio >= 0.6:
                    self.patterns.append({
                        'type': 'h2h_btts',
                        'teams': f"{home} vs {away}",
                        'details': f"🧤 {home} vs {away}: {btts_ratio*100:.0f}% of meetings have BTTS!",
                        'strength': 'high',
                        'confidence': btts_ratio
                    })
    
    def _detect_scoreline_sequences(self):
        """Detect repeating scoreline patterns."""
        score_sequences = defaultdict(list)
        for item in self.results:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data["ft"]
                score = f"{ft_h}-{ft_a}"
                score_sequences[home].append(score)
                score_sequences[away].append(score)
        
        for team, scores in score_sequences.items():
            if len(scores) >= 5:
                # Find most common score
                from collections import Counter
                counter = Counter(scores)
                most_common = counter.most_common(1)
                if most_common and most_common[0][1] >= 3:
                    score, count = most_common[0]
                    ratio = count / len(scores)
                    self.patterns.append({
                        'type': 'scoreline_pattern',
                        'team': team,
                        'details': f"📊 {team}'s most common score is {score} ({ratio*100:.0f}% of matches)",
                        'strength': 'medium',
                        'confidence': ratio
                    })
    
    def _detect_goal_difference_patterns(self):
        """Detect patterns in goal difference (e.g., always win by 1)."""
        goal_diffs = defaultdict(list)
        for item in self.results:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data["ft"]
                for team, goals, conceded in [(home, ft_h, ft_a), (away, ft_a, ft_h)]:
                    if goals > conceded:
                        goal_diffs[team].append(goals - conceded)
        
        for team, diffs in goal_diffs.items():
            if len(diffs) >= 3:
                avg_diff = np.mean(diffs)
                std_diff = np.std(diffs)
                if std_diff < 0.5:  # Very consistent
                    self.patterns.append({
                        'type': 'consistent_win_margin',
                        'team': team,
                        'details': f"📐 {team} consistently wins by {avg_diff:.1f} goals (σ={std_diff:.2f})",
                        'strength': 'high',
                        'confidence': 0.85
                    })
    
    def _generate_formulas(self):
        """Generate actionable formulas from detected patterns."""
        formulas = []
        
        # Formula 1: If team on winning streak and playing at home
        for p in self.patterns:
            if p['type'] == 'winning_streak':
                formulas.append({
                    'formula': f"IF {p['team']} is on a winning streak AND playing at home → Bet on {p['team']} to win",
                    'confidence': p.get('confidence', 0.8),
                    'type': 'match_outcome',
                    'priority': 'high'
                })
        
        # Formula 2: If both teams are high scoring
        for p in self.patterns:
            if p['type'] == 'high_scoring':
                formulas.append({
                    'formula': f"IF {p['team']} is playing → Bet Over 2.5 goals (high scoring team)",
                    'confidence': p.get('confidence', 0.7),
                    'type': 'over_under',
                    'priority': 'high'
                })
        
        # Formula 3: Clean sheet patterns
        for p in self.patterns:
            if p['type'] == 'clean_sheet_specialist':
                formulas.append({
                    'formula': f"IF {p['team']} is playing at home → Bet Under 2.5 goals",
                    'confidence': p.get('confidence', 0.7),
                    'type': 'over_under',
                    'priority': 'medium'
                })
        
        # Formula 4: H2H Over 2.5 patterns
        for p in self.patterns:
            if p['type'] == 'h2h_over25':
                formulas.append({
                    'formula': f"IF {p['teams']} are playing → Bet Over 2.5 goals ({p['confidence']*100:.0f}% historical)",
                    'confidence': p.get('confidence', 0.7),
                    'type': 'over_under',
                    'priority': 'high'
                })
        
        # Formula 5: First goal wins pattern
        for p in self.patterns:
            if p['type'] == 'first_goal_wins':
                formulas.append({
                    'formula': f"IF {p['team']} scores first against {p['opponent']} → Bet on {p['team']} to win",
                    'confidence': p.get('confidence', 0.7),
                    'type': 'match_outcome',
                    'priority': 'medium'
                })
        
        # Formula 6: Second half comeback
        for p in self.patterns:
            if p['type'] == 'second_half_comeback':
                formulas.append({
                    'formula': f"IF {p['team']} is trailing at half-time → Bet on {p['team']} to win or draw (Double Chance)",
                    'confidence': p.get('confidence', 0.7),
                    'type': 'double_chance',
                    'priority': 'high'
                })
        
        self.formulas = formulas
    
    def _rank_formulas_by_confidence(self):
        """Rank formulas by confidence score."""
        self.formulas.sort(key=lambda x: x['confidence'], reverse=True)
    
    def get_pattern_summary(self):
        """Generate a comprehensive pattern report with formulas."""
        if not self.patterns and not self.formulas:
            return "No significant patterns detected yet. Add more matchdays for better pattern recognition."
        
        summary = "## 🧠 Advanced Pattern Detection Report\n\n"
        
        # 1. Patterns
        summary += "### 📊 Detected Patterns\n\n"
        pattern_types = {}
        for p in self.patterns:
            if p['type'] not in pattern_types:
                pattern_types[p['type']] = []
            pattern_types[p['type']].append(p)
        
        for ptype, patterns in pattern_types.items():
            icon = {
                'winning_streak': '🔥',
                'losing_streak': '⚠️',
                'draw_streak': '🤝',
                'home_specialist': '🏠',
                'away_specialist': '✈️',
                'high_scoring': '⚽',
                'tight_defense': '🛡️',
                'low_scoring': '🐌',
                'recurring_score': '📊',
                'comeback_specialist': '💪',
                'clean_sheet_specialist': '🧤',
                'second_half_specialist': '⚡',
                'first_goal_wins': '⚡',
                'second_half_comeback': '💪',
                'early_goal_specialist': '⏰',
                'late_goal_specialist': '⏰',
                'h2h_over25': '⚽',
                'h2h_btts': '🧤',
                'scoreline_pattern': '📊',
                'consistent_win_margin': '📐'
            }.get(ptype, '📌')
            
            summary += f"#### {icon} {ptype.replace('_', ' ').title()}\n"
            for p in patterns:
                conf = p.get('confidence', 0) * 100
                summary += f"- {p['details']} (Confidence: {conf:.0f}%)\n"
            summary += "\n"
        
        # 2. Actionable Formulas
        if self.formulas:
            summary += "### 🧮 Actionable Formulas (High Confidence)\n\n"
            for i, formula in enumerate(self.formulas[:10], 1):
                conf = formula.get('confidence', 0) * 100
                summary += f"{i}. **{formula['formula']}** (Confidence: {conf:.0f}%)\n"
                summary += f"   - Type: {formula['type']} | Priority: {formula.get('priority', 'medium')}\n\n"
        
        # 3. Summary Statistics
        summary += "### 📈 Pattern Statistics\n\n"
        total_patterns = len(self.patterns)
        total_formulas = len(self.formulas)
        summary += f"- Total patterns detected: {total_patterns}\n"
        summary += f"- Actionable formulas generated: {total_formulas}\n"
        if self.formulas:
            summary += f"- Top confidence: {self.formulas[0]['confidence']*100:.0f}%\n\n"
        
        return summary
    
    def get_formulas(self, min_confidence=0.6, max_count=10):
        """Return actionable formulas with confidence > min_confidence."""
        return [f for f in self.formulas if f['confidence'] >= min_confidence][:max_count]
    
    def get_patterns_for_match(self, home, away):
        """Get patterns that apply to a specific match."""
        relevant = []
        for p in self.patterns:
            if p.get('team') == home or p.get('team') == away:
                relevant.append(p)
            if p.get('teams') and (home in p['teams'] and away in p['teams']):
                relevant.append(p)
        return relevant


def detect_math_patterns(results):
    """
    Detect mathematical patterns in results.
    Returns list of pattern dicts.
    """
    patterns = []
    from collections import Counter
    
    # Look for repeating scorelines
    scoreline_sequence = []
    for item in results:
        for (home, away), data in item['data'].items():
            ft_h, ft_a = data["ft"]
            scoreline = f"{ft_h}-{ft_a}"
            scoreline_sequence.append(scoreline)
    
    for i in range(len(scoreline_sequence) - 2):
        if scoreline_sequence[i] == scoreline_sequence[i+1] == scoreline_sequence[i+2]:
            patterns.append({
                'type': 'repeating_scoreline',
                'pattern': scoreline_sequence[i],
                'details': f"🔁 Scoreline {scoreline_sequence[i]} appears 3 times in a row!",
                'strength': 'high'
            })
    
    # Look for alternating W-L patterns
    results_for_teams = defaultdict(list)
    for item in results:
        for (home, away), data in item['data'].items():
            ft_h, ft_a = data["ft"]
            for team, goals in [(home, ft_h), (away, ft_a)]:
                if ft_h > ft_a:
                    result = 'W' if goals == ft_h else 'L'
                elif ft_h == ft_a:
                    result = 'D'
                else:
                    result = 'L' if goals == ft_h else 'W'
                results_for_teams[team].append(result)
    
    for team, results_list in results_for_teams.items():
        if len(results_list) >= 4:
            if all(results_list[i] != results_list[i+1] for i in range(len(results_list)-1)):
                patterns.append({
                    'type': 'alternating_form',
                    'team': team,
                    'details': f"🔄 {team} has alternating form! Cannot predict reliably.",
                    'strength': 'medium'
                })
    
    return patterns