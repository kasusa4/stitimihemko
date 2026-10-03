# utils/api_client.py
import requests
import json
from config import SEASONS_URL, EVENTS_URL, HEADERS, LEAGUES, KNOWN_TEAMS

class BetpawaAPIClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_current_round(self):
        try:
            resp = self.session.get(SEASONS_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('items', [])
                if items:
                    season = items[0]
                    rounds = season.get('rounds', [])
                    if rounds:
                        current_round = rounds[0]
                        round_id = current_round.get('id')
                        matchday_str = current_round.get('name')
                        try:
                            matchday = int(matchday_str) if matchday_str else None
                        except ValueError:
                            matchday = None
                        return {
                            'round_id': round_id,
                            'matchday': matchday,
                            'season_id': season.get('id')
                        }
            return None
        except Exception as e:
            print(f"❌ API error (round): {e}")
            return None

    def get_events(self, round_id):
        url = f"{EVENTS_URL}{round_id}"
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Try to parse as events
                if 'events' in data:
                    return self._parse_events(data)
                elif 'responses' in data:
                    # This might be live results – we'll parse as fixtures anyway
                    return self._parse_responses(data)
                else:
                    print("⚠️ Unknown response structure.")
                    return None
            else:
                print(f"⚠️ Events API returned {resp.status_code}")
                return None
        except Exception as e:
            print(f"❌ API error (events): {e}")
            return None

    def _parse_events(self, data):
        """Parse the standard events structure with odds."""
        matches_by_league = {}
        for ev in data.get('events', []):
            league_id = ev.get('leagueId')
            league_name = self._get_league_name(league_id)
            home = ev.get('homeTeam', {}).get('name', '')
            away = ev.get('awayTeam', {}).get('name', '')
            if not home or not away:
                continue
            if home not in KNOWN_TEAMS or away not in KNOWN_TEAMS:
                continue
            odds = ev.get('odds', {})
            match_data = {
                'home': home,
                'away': away,
                'event_id': ev.get('id'),
                'status': ev.get('status', 'scheduled'),
                'odds': {
                    'home': odds.get('home', 0),
                    'draw': odds.get('draw', 0),
                    'away': odds.get('away', 0),
                    'over25': odds.get('over', {}).get('2.5', 0),
                    'btts_yes': odds.get('btts', {}).get('yes', 0),
                }
            }
            if league_name not in matches_by_league:
                matches_by_league[league_name] = []
            matches_by_league[league_name].append(match_data)
        return matches_by_league

    def _parse_responses(self, data):
        """Parse the 'responses' structure (live results)."""
        matches_by_league = {}
        for item in data.get('responses', []):
            name = item.get('name', '')
            if ' - ' in name:
                home, away = name.split(' - ', 1)
            else:
                continue
            if home not in KNOWN_TEAMS or away not in KNOWN_TEAMS:
                continue
            # Try to extract score from results
            ft_h = ft_a = None
            results = item.get('results', {})
            participant_results = results.get('participantPeriodResults', [])
            for pr in participant_results:
                participant = pr.get('participant', {})
                p_type = participant.get('type')
                period_results = pr.get('periodResults', [])
                # Look for full-time (period id 3012 might be second half, but we can sum)
                # For simplicity, we'll take the last period result
                if period_results:
                    last = period_results[-1]
                    score = last.get('score', {})
                    if p_type == 'HOME':
                        ft_h = score.get('value')
                    elif p_type == 'AWAY':
                        ft_a = score.get('value')
            # We don't have league info in this response – we need to assign
            # For now, we'll put it in a "Unknown" league, or we can deduce from the round.
            # Since we're fetching fixtures, we might skip this for now.
            # We'll return an empty dict to fall back to scraper.
        return None  # fall back to scraper for live results

    def _get_league_name(self, league_id):
        for name, lid in LEAGUES.items():
            if lid == league_id:
                return name
        return "Unknown"
    

        # utils/api_client.py (add this method)
    def get_events_for_any_round(self, round_ids):
        """Try multiple round IDs and return the first one that has events."""
        for rid in round_ids:
            events = self.get_events(rid)
            if events:
                return events, rid
        return None, None
    
    def get_events_for_any_round(self, round_ids):
        """Try multiple round IDs and return the first one that has events."""
        for rid in round_ids:
            events = self.get_events(rid)
            if events:
                return events, rid
        return None, None