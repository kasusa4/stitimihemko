# utils/pattern_utils.py
from collections import defaultdict
import re

class PatternDetector:
    def __init__(self, results_data):
        """
        results_data: list of dicts with 'day' and 'data' (parsed matches)
        Each match data is a dict with keys 'ft' and 'ht' containing (home_goals, away_goals)
        """
        self.results = results_data
        self.patterns = []
        self.detect_all_patterns()
    
    def detect_all_patterns(self):
        """Run all pattern detectors"""
        self.detect_streaks()
        self.detect_home_away_trends()
        self.detect_scoring_patterns()
        self.detect_common_scorelines()
        self.detect_comeback_patterns()
        self.detect_clean_sheet_patterns()
        self.detect_goal_timing_patterns()
    
    def detect_streaks(self):
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
                        'strength': 'high'
                    })
                elif all(r[0] == 'L' for r in last_5[:3]):
                    self.patterns.append({
                        'type': 'losing_streak',
                        'team': team,
                        'details': f"⚠️ {team} is on a {len([r for r in last_5 if r[0]=='L'])}-match losing streak!",
                        'strength': 'medium'
                    })
                elif all(r[0] == 'D' for r in last_5[:3]):
                    self.patterns.append({
                        'type': 'draw_streak',
                        'team': team,
                        'details': f"🤝 {team} is on a {len([r for r in last_5 if r[0]=='D'])}-match draw streak!",
                        'strength': 'medium'
                    })
    
    def detect_home_away_trends(self):
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
                    'strength': 'high'
                })
            elif away_avg > 0.5 and away_avg > home_avg + 0.5:
                self.patterns.append({
                    'type': 'away_specialist',
                    'team': team,
                    'details': f"✈️ {team} is an AWAY SPECIALIST! Avg goal difference: +{away_avg:.1f} away vs {home_avg:.1f} home",
                    'strength': 'high'
                })
    
    def detect_scoring_patterns(self):
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
                    'strength': 'high'
                })
            if avg_conceded <= 0.8:
                self.patterns.append({
                    'type': 'tight_defense',
                    'team': team,
                    'details': f"🛡️ {team} has a TIGHT DEFENSE! Only {avg_conceded:.1f} goals conceded/match",
                    'strength': 'high'
                })
            if avg_scored <= 0.7:
                self.patterns.append({
                    'type': 'low_scoring',
                    'team': team,
                    'details': f"🐌 {team} is LOW SCORING! Only {avg_scored:.1f} goals/match",
                    'strength': 'medium'
                })
    
    def detect_common_scorelines(self):
        team_scorelines = defaultdict(list)
        
        for item in self.results:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data["ft"]
                team_scorelines[home].append(f"{ft_h}-{ft_a}")
                team_scorelines[away].append(f"{ft_a}-{ft_h}")
        
        from collections import Counter
        for team, scorelines in team_scorelines.items():
            counter = Counter(scorelines)
            most_common = counter.most_common(1)[0]
            if most_common[1] >= 3:
                self.patterns.append({
                    'type': 'recurring_score',
                    'team': team,
                    'details': f"📊 {team}'s most common score is {most_common[0]} (appeared {most_common[1]} times)",
                    'strength': 'medium'
                })
    
    def detect_comeback_patterns(self):
        for item in self.results:
            for (home, away), data in item['data'].items():
                ht_h, ht_a = data["ht"]
                ft_h, ft_a = data["ft"]
                
                if ht_h < ht_a and ft_h > ft_a:
                    self.patterns.append({
                        'type': 'comeback_specialist',
                        'team': home,
                        'details': f"💪 {home} is a COMEBACK SPECIALIST! Came from behind to win against {away}",
                        'strength': 'high'
                    })
                elif ht_a < ht_h and ft_a > ft_h:
                    self.patterns.append({
                        'type': 'comeback_specialist',
                        'team': away,
                        'details': f"💪 {away} is a COMEBACK SPECIALIST! Came from behind to win against {home}",
                        'strength': 'high'
                    })
    
    def detect_clean_sheet_patterns(self):
        clean_sheets = defaultdict(int)
        matches_played = defaultdict(int)
        
        for item in self.results:
            for (home, away), data in item['data'].items():
                ft_h, ft_a = data["ft"]
                matches_played[home] += 1
                matches_played[away] += 1
                if ft_a == 0:
                    clean_sheets[home] += 1
                if ft_h == 0:
                    clean_sheets[away] += 1
        
        for team in clean_sheets:
            if matches_played[team] >= 5:
                ratio = clean_sheets[team] / matches_played[team]
                if ratio >= 0.4:
                    self.patterns.append({
                        'type': 'clean_sheet_specialist',
                        'team': team,
                        'details': f"🧤 {team} keeps CLEAN SHEETS! {clean_sheets[team]} clean sheets in {matches_played[team]} matches ({ratio*100:.0f}%)",
                        'strength': 'high'
                    })
    
    def detect_goal_timing_patterns(self):
        for item in self.results:
            for (home, away), data in item['data'].items():
                ht_h, ht_a = data["ht"]
                ft_h, ft_a = data["ft"]
                
                if (ft_h - ht_h) > ht_h and (ft_h - ht_h) >= 2:
                    self.patterns.append({
                        'type': 'second_half_specialist',
                        'team': home,
                        'details': f"⚡ {home} is a 2nd HALF SPECIALIST! Scored {(ft_h - ht_h)} goals after halftime",
                        'strength': 'medium'
                    })
                if (ft_a - ht_a) > ht_a and (ft_a - ht_a) >= 2:
                    self.patterns.append({
                        'type': 'second_half_specialist',
                        'team': away,
                        'details': f"⚡ {away} is a 2nd HALF SPECIALIST! Scored {(ft_a - ht_a)} goals after halftime",
                        'strength': 'medium'
                    })
    
    def get_pattern_summary(self):
        if not self.patterns:
            return "No significant patterns detected yet. Add more matchdays for better pattern recognition."
        
        summary = "## 🧠 Pattern Detection Report\n\n"
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
                'second_half_specialist': '⚡'
            }.get(ptype, '📌')
            
            summary += f"### {icon} {ptype.replace('_', ' ').title()}\n"
            for p in patterns:
                summary += f"- {p['details']}\n"
            summary += "\n"
        
        return summary
    
    def get_impact_on_prediction(self, home, away):
        relevant = []
        for p in self.patterns:
            if p['team'] == home or p['team'] == away:
                relevant.append(p)
        return relevant


def detect_math_patterns(results):
    """
    Detect mathematical patterns in results.
    results: list of day dicts (same as PatternDetector)
    """
    patterns = []
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
    
    results_for_teams = defaultdict(list)
    for item in results:
        for (home, away), data in item['data'].items():
            ft_h, ft_a = data["ft"]
            for team, goals in [(home, ft_h), (away, ft_a)]:
                result = 'W' if (goals == ft_h and ft_h > ft_a) or (goals == ft_a and ft_a > ft_h) else 'D' if (goals == ft_h and ft_h == ft_a) or (goals == ft_a and ft_h == ft_a) else 'L'
                results_for_teams[team].append(result)
    
    for team, results_list in results_for_teams.items():
        if len(results_list) >= 4:
            if all(results_list[i] != results_list[i+1] for i in range(len(results_list)-1)):
                patterns.append({
                    'type': 'alternating_form',
                    'team': team,
                    'details': f"🔄 {team} has alternating form! Cannot predict their next result reliably.",
                    'strength': 'medium'
                })
    
    return patterns