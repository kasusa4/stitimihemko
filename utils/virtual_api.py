# utils/virtual_api.py
import requests
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class VirtualAPI:
    BASE_URL = "https://tz.api.vunjabeibet.co.tz/api/virtuals/games"

    # Map internal league names to API championshipType
    LEAGUE_CHAMPIONSHIP_MAP = {
        'English League': 1,
        'Spanish League': 4,
        'Italian League': 0,
        'German League': 3,
        'French League': 2,
    }

    def __init__(self, timeout: int = 70):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        })

    # ---------- FIXTURES ----------
    def fetch_current_week(self, championship_type: int = 1) -> Optional[Dict]:
        """
        Fetch the current week's scheduled fixtures for a given championship type.
        """
        url = f"{self.BASE_URL}/getCurrentWeek/scheduled"
        params = {
            'championshipType': championship_type,
            'v_': 5,
            'src': 'mobile'
        }
        try:
            logger.info(f"Fetching fixtures for championshipType={championship_type}...")
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return self._parse_fixtures_response(data)
        except Exception as e:
            logger.error(f"fetch_current_week error for type {championship_type}: {e}")
            return None

    def fetch_fixtures_for_league(self, league_name: str) -> Optional[Dict]:
        """
        Fetch fixtures for a specific league using its championship type.
        """
        championship_type = self.LEAGUE_CHAMPIONSHIP_MAP.get(league_name)
        if championship_type is None:
            logger.warning(f"No championship type mapped for league: {league_name}")
            return None
        return self.fetch_current_week(championship_type)

    def _parse_fixtures_response(self, data: Dict) -> Dict:
        """
        Parse the /getCurrentWeek/scheduled response.
        Expected format: { "seasonId": ..., "week": { "id": ... }, "matches": { "ids": [...] } }
        """
        season_id = data.get('seasonId')
        week_id = data.get('week', {}).get('id')
        raw_matches = data.get('matches', {}).get('ids', [])

        parsed_matches = []
        for match_str in raw_matches:
            if '-' not in match_str:
                continue
            home, away = match_str.split('-', 1)
            parsed_matches.append({
                'home': home.strip().upper(),
                'away': away.strip().upper()
            })

        return {
            'season_id': season_id,
            'week_id': week_id,
            'matches': parsed_matches
        }

    # ---------- RESULTS ----------
    def fetch_results(self, week_num: int, season_id: int) -> Optional[Dict]:
        """
        Fetch results for a specific week and season.
        """
        url = f"{self.BASE_URL}/getResults/scheduled"
        params = {
            'weekNum': week_num,
            'seasonId': season_id,
            'v_': 5,
            'src': 'mobile'
        }
        try:
            logger.info(f"Fetching results for week {week_num}, season {season_id}...")
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return self._parse_results_response(data)
        except Exception as e:
            logger.error(f"fetch_results error: {e}")
            return None

    def _parse_results_response(self, data: Dict) -> Dict:
        """
        Parse the /getResults/scheduled response.
        Expected format: {
            "matches": ["HOF-UBE", "FRE-HEI", ...],
            "outcomes": ["2-2", "2-1", ...],
            "goals": [{...}, {...}, ...]
        }
        """
        matches_raw = data.get('matches', [])
        outcomes = data.get('outcomes', [])
        goals = data.get('goals', [])

        parsed = []
        for idx, pair in enumerate(matches_raw):
            if '-' not in pair:
                continue
            home, away = pair.split('-', 1)
            home = home.strip(); away = away.strip()

            outcome = outcomes[idx] if idx < len(outcomes) else "0-0"
            ft_h, ft_a = outcome.split('-', 1) if '-' in outcome else ('0', '0')
            ft_h = int(ft_h); ft_a = int(ft_a)

            # Half-time goals from goals dict (if available)
            ht_h = ht_a = 0
            if idx < len(goals):
                g = goals[idx]
                if isinstance(g, dict):
                    for minute, team in g.items():
                        try:
                            if int(minute) < 45:
                                if team == 'H':
                                    ht_h += 1
                                elif team == 'A':
                                    ht_a += 1
                        except:
                            pass

            parsed.append({
                'home': home.upper(),
                'away': away.upper(),
                'ft_h': ft_h,
                'ft_a': ft_a,
                'ht_h': ht_h,
                'ht_a': ht_a
            })
        return {'matches': parsed}
    

    def fetch_competitions(self):
        """Fetch the competition list from /init endpoint."""
        url = f"{self.BASE_URL}/init"
        params = {'v_': 5, 'src': 'mobile'}
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return {
                'ids': data.get('competitions', {}).get('ids', []),
                'names': data.get('competitions', {}).get('names', [])
            }
        except Exception as e:
            logger.error(f"fetch_competitions error: {e}")
            return None
        
    def get_league_info(self, league_name):
        """Get current season ID and week for a league."""
        champ_type = self.CHAMP_MAP.get(league_name)
        if champ_type is None:
            return None
        data = self.fetch_current_week(champ_type)
        if data:
            return {
                'season_id': data.get('season_id'),
                'current_week': data.get('week_id')
            }
        return None