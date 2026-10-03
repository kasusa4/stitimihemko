import requests
import blackboxprotobuf
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

BASE_URL = "https://www.betpawa.co.tz/api/sportsbook/virtual"

HEADERS = {
    "accept": "application/x-protobuf",
    "x-pawa-brand": "betpawa-tanzania",
    "x-pawa-language": "en",
    "devicetype": "web",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36 Edg/153.0.0.0",
    "content-type": "application/x-protobuf",
}

# ---------- Simple cache ----------
_seasons_cache = None
_seasons_cache_time = 0
SEASONS_CACHE_TTL = 60   # seconds

_events_cache = {}
_events_cache_time = {}
EVENTS_CACHE_TTL = 30   # seconds

def _decode(data):
    decoded, _ = blackboxprotobuf.decode_message(data)
    return decoded

def _to_str(val):
    if isinstance(val, bytes):
        return val.decode()
    return str(val) if val is not None else None

def get_active_seasons(force_refresh=False):
    """Return list of active seasons with their rounds (cached for 60s)."""
    global _seasons_cache, _seasons_cache_time
    now = time.time()
    if not force_refresh and _seasons_cache and (now - _seasons_cache_time) < SEASONS_CACHE_TTL:
        return _seasons_cache

    url = f"{BASE_URL}/v2/seasons/list/actual"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    decoded = _decode(resp.content)
    seasons = []
    for season in decoded.get("1", []):
        sid = _to_str(season.get("1"))
        rounds = []
        for r in season.get("6", []):
            rid = _to_str(r.get("1"))
            rnum = None
            if isinstance(r.get("2"), dict) and "6" in r["2"]:
                rnum = r["2"]["6"]
            elif isinstance(r.get("2"), bytes):
                rnum = _to_str(r.get("2"))
            rounds.append((rid, rnum))
        for r in season.get("6-1", []):
            rid = _to_str(r.get("1"))
            rnum = _to_str(r.get("2")) if r.get("2") else None
            rounds.append((rid, rnum))
        seasons.append({
            "season_id": sid,
            "label": _to_str(season.get("2")),
            "rounds": rounds,
        })
    _seasons_cache = seasons
    _seasons_cache_time = now
    return seasons

def get_events_for_round(round_id, use_cache=True):
    """Return events for a specific round (cached for 30s)."""
    now = time.time()
    if use_cache and round_id in _events_cache and (now - _events_cache_time.get(round_id, 0)) < EVENTS_CACHE_TTL:
        return _events_cache[round_id]

    url = f"{BASE_URL}/v3/events/list/by-round/{round_id}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    decoded = _decode(resp.content)
    events = []
    for ev in decoded.get("2", []):
        event_id = _to_str(ev.get("1"))
        teams = ev.get("5", [])
        home_name = away_name = None
        if len(teams) >= 2:
            home_name = _to_str(teams[0].get("2"))
            away_name = _to_str(teams[1].get("2"))

        ft_home = ft_away = None
        scores = ev.get("3", {}).get("2", [])
        for side in scores:
            side_label = _to_str(side.get("1", {}).get("2"))
            for s in side.get("2", []):
                market = _to_str(s.get("1", {}).get("3"))
                if market == "FULL_TIME_EXCLUDING_OVERTIME":
                    val = _to_str(s.get("2"))
                    try:
                        val_int = int(val)
                    except (ValueError, TypeError):
                        continue
                    if side_label == "HOME":
                        ft_home = val_int
                    elif side_label == "AWAY":
                        ft_away = val_int

        league = _to_str(ev.get("12", {}).get("2"))
        start_ts = ev.get("6", {}).get("1")
        start_time = None
        if start_ts:
            try:
                start_time = datetime.fromtimestamp(start_ts).isoformat()
            except Exception:
                pass

        events.append({
            "event_id": event_id,
            "home_team": home_name,
            "away_team": away_name,
            "ft_home": ft_home,
            "ft_away": ft_away,
            "league": league,
            "start_time": start_time,
        })

    _events_cache[round_id] = events
    _events_cache_time[round_id] = now
    return events

def fetch_all_current_events(max_workers=8):
    """
    Fetch all events for the active season using a thread pool for speed.
    """
    seasons = get_active_seasons()
    all_events = []

    # Collect all round ids across seasons
    tasks = []
    for s in seasons:
        for rid, rnum in s["rounds"]:
            tasks.append((s["season_id"], rid, rnum))

    # Fetch rounds in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {}
        for sid, rid, rnum in tasks:
            future = executor.submit(get_events_for_round, rid)
            future_map[future] = (sid, rid, rnum)

        for future in as_completed(future_map):
            sid, rid, rnum = future_map[future]
            try:
                events = future.result()
                for ev in events:
                    ev["season_id"] = sid
                    ev["round_id"] = rid
                    ev["round_number"] = rnum
                all_events.extend(events)
            except Exception as e:
                print(f"Error fetching round {rid}: {e}")

    return all_events