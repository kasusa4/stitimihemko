import requests
import json
import os
from datetime import datetime
from utils.betpawa_parser import parse_events_response
from blackboxprotobuf import decode_message

BASE_URL = "https://www.betpawa.co.tz/api/sportsbook/virtual"

HEADERS = {
    "accept": "application/x-protobuf",
    "x-pawa-brand": "betpawa-tanzania",
    "x-pawa-language": "en",
    "devicetype": "web",
    "user-agent": "Mozilla/5.0",
    "content-type": "application/x-protobuf",
}

def _to_str(val):
    if isinstance(val, bytes):
        return val.decode()
    return str(val) if val is not None else None

def get_active_seasons():
    """
    Return active seasons with rounds sorted by round_id (correct MD order).

    BetPawa stores rounds across keys "6" and "6-1":
      - "6"   : MD 1-9 (real) + MD 14/24/34 (placeholders with field2=None)
      - "6-1" : MD 10-33 (except 14, 24, 34)

    Round IDs are sequential integers, so sorting by int(round_id)
    gives us the exact matchday order.
    """
    url = f"{BASE_URL}/v2/seasons/list/actual"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    decoded, _ = decode_message(resp.content)

    seasons = []
    for season in decoded.get("1", []):
        sid = _to_str(season.get("1"))

        # Collect ALL rounds from all keys, dedupe by round_id
        all_rounds = {}
        for key in ("6", "6-1", "6-2"):
            for r in season.get(key, []):
                rid = _to_str(r.get("1"))
                if not rid:
                    continue
                if rid not in all_rounds:
                    all_rounds[rid] = r

        # Sort round IDs by integer → correct matchday order
        try:
            sorted_rids = sorted(all_rounds.keys(), key=lambda x: int(x))
        except (ValueError, TypeError):
            sorted_rids = list(all_rounds.keys())

        rounds = [(rid, idx) for idx, rid in enumerate(sorted_rids, start=1)]

        seasons.append({
            "season_id": sid,
            "label": _to_str(season.get("2")),
            "rounds": rounds,               # [(round_id, md_index), ...]
            "round_ids": sorted_rids,   # for debugging
        })

    return seasons

def get_events_for_round(round_id):
    url = f"{BASE_URL}/v3/events/list/by-round/{round_id}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return parse_events_response(resp.content)

def sync_matchday_to_json(season_id, matchday_number, json_path="accuracy_data.json"):
    """
    Fetch a matchday from BetPawa and merge results + fixtures into accuracy_data.json.
    """
    seasons = get_active_seasons()
    target_season = next((s for s in seasons if s["season_id"] == str(season_id)), None)
    if not target_season:
        print(f"❌ Season {season_id} not found. Available: {[s['season_id'] for s in seasons]}")
        return 0, []

    target_round = None
    for rid, rnum in target_season["rounds"]:
        if str(rnum) == str(matchday_number):
            target_round = rid
            break
    if not target_round:
        print(f"❌ Matchday {matchday_number} not found in season {season_id}")
        return 0, []

    events = get_events_for_round(target_round)
    print(f"📥 Fetched {len(events)} events for round {target_round}")

    results = []
    fixtures = []
    for ev in events:
        home = ev.get("home_team")
        away = ev.get("away_team")
        ft_h = ev.get("ft_home")
        ft_a = ev.get("ft_away")
        if not home or not away:
            continue
        if ft_h is not None and ft_a is not None:
            if ft_h > ft_a:
                result_str = "Home Win"
            elif ft_h < ft_a:
                result_str = "Away Win"
            else:
                result_str = "Draw"
            results.append({
                "home": home,
                "away": away,
                "result": result_str,
                "ft_h": ft_h,
                "ft_a": ft_a,
                "over25_actual": (ft_h + ft_a) > 2.5,
                "btts_actual": ft_h > 0 and ft_a > 0
            })
        else:
            fixtures.append({
                "home": home,
                "away": away,
                "league": ev.get("league")
            })

    # Load JSON
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            data = json.load(f)
    else:
        data = {}

    key = str(matchday_number)
    if key not in data:
        data[key] = {"predictions": [], "results": [], "accuracy": None}

    existing = {(r["home"], r["away"]) for r in data[key]["results"]}
    for r in results:
        if (r["home"], r["away"]) not in existing:
            data[key]["results"].append(r)

    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✅ Matchday {matchday_number}: {len(results)} results stored, {len(fixtures)} fixtures pending")
    return len(results), fixtures

# ============================================================
# AUTO-SYNC LATEST SEASON
# ============================================================
def classify_season(season):
    """
    Classify a season as 'past', 'live', 'future', or 'unknown' by checking
    the first and last rounds:
      - Future : first round has 0 results (not started)
      - Live   : first round has results AND last round has fixtures
      - Past   : first round has results AND last round has results
    """
    if not season.get("rounds"):
        return "unknown"

    first_rid = season["rounds"][0][0]
    last_rid = season["rounds"][-1][0]
    if not first_rid or not last_rid:
        return "unknown"

    try:
        first_events = get_events_for_round(first_rid)
        first_results = sum(1 for ev in first_events if ev.get("ft_home") is not None)
    except Exception as e:
        print(f"Season {season['season_id']} first-round check failed: {e}")
        return "unknown"

    if first_results == 0:
        return "future"

    # First round has results — check the last round
    try:
        last_events = get_events_for_round(last_rid)
        last_results = sum(1 for ev in last_events if ev.get("ft_home") is not None)
        last_total = len(last_events)
    except Exception as e:
        print(f"Season {season['season_id']} last-round check failed: {e}")
        return "live"  # assume live if we can't check

    if last_results == last_total and last_results > 0:
        return "past"   # all rounds played
    else:
        return "live"   # some rounds pending



def sync_latest_season(json_path="accuracy_data.json", force=False):
    """
    Auto-detect the live season, fetch all its rounds, store results + fixtures.
    ALWAYS returns a 4-tuple (season_id, total_results, fixtures_md, fixtures_count).
    Returns (None, 0, None, 0) on any failure — never None.
    """
    import json, os, datetime as _dt
    from concurrent.futures import ThreadPoolExecutor, as_completed

    try:
        seasons = get_active_seasons()
    except Exception as e:
        print(f"❌ sync_latest_season: seasons fetch failed: {e}")
        return None, 0, None, 0

    if not seasons:
        print("❌ sync_latest_season: no active seasons")
        return None, 0, None, 0

    seasons_sorted = sorted(seasons, key=lambda s: int(s["season_id"]), reverse=True)

    # ---- Pick live season ----
    live = None
    for s in seasons_sorted:
        valid = [(rid, md) for rid, md in s["rounds"] if rid]
        if not valid:
            continue
        try:
            first_events = get_events_for_round(valid[0][0])
            first_results = sum(1 for e in first_events if e.get("ft_home") is not None)
        except Exception:
            continue
        if first_results == 0:
            continue
        # check if any round is unfinished
        has_unfinished = False
        for rid, _ in valid:
            try:
                evs = get_events_for_round(rid)
                r = sum(1 for e in evs if e.get("ft_home") is not None)
                if r < len(evs):
                    has_unfinished = True
                    break
            except Exception:
                continue
        if has_unfinished:
            live = s
            break

    if not live:
        # fallback: second-highest
        live = seasons_sorted[1] if len(seasons_sorted) > 1 else seasons_sorted[0]

    season_id = live["season_id"]
    print(f"🎯 Sync target: season {season_id}")

    # ---- Fetch all rounds in parallel ----
    def fetch_one(idx_rid):
        idx, rid = idx_rid
        try:
            return idx, get_events_for_round(rid)
        except Exception as e:
            print(f"  ⚠️ Round {rid} error: {e}")
            return idx, []

    total_results = 0
    fixtures_md = None
    fixtures_count = 0
    round_results = {}

    tasks = [(i, rid) for i, (rid, _) in enumerate(live["rounds"], start=1) if rid]
    with ThreadPoolExecutor(max_workers=3) as executor:  # reduced from 6
        futures = [executor.submit(fetch_one, t) for t in tasks]
        for fut in as_completed(futures):
            idx, events = fut.result()
            if not events:
                continue
            results, fixtures = [], []
            for ev in events:
                home = ev.get("home_team")
                away = ev.get("away_team")
                ft_h = ev.get("ft_home")
                ft_a = ev.get("ft_away")
                if not home or not away:
                    continue
                if ft_h is not None and ft_a is not None:
                    result_str = "Home Win" if ft_h > ft_a else ("Away Win" if ft_h < ft_a else "Draw")
                    results.append({
                        "home": home, "away": away, "result": result_str,
                        "ft_h": ft_h, "ft_a": ft_a,
                        "over25_actual": (ft_h + ft_a) > 2.5,
                        "btts_actual": ft_h > 0 and ft_a > 0
                    })
                else:
                    fixtures.append({"home": home, "away": away, "league": ev.get("league")})
            round_results[idx] = {"results": results, "fixtures": fixtures}

    # ---- Save ----
    data = {}
    for idx in sorted(round_results.keys()):
        key = str(idx)
        res = round_results[idx]["results"]
        fix = round_results[idx]["fixtures"]
        total = len(res) + len(fix)
        if len(fix) == 0 and len(res) > 0:
            data[key] = {"predictions": [], "results": res, "fixtures": []}
            total_results += len(res)
        else:
            data[key] = {"predictions": [], "results": [], "fixtures": fix}
            if fix and fixtures_md is None:
                fixtures_md = idx
                fixtures_count = len(fix)

    data["_meta"] = {
        "season_id": season_id,
        "last_sync": _dt.datetime.now().isoformat(),
    }

    tmp = json_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, json_path)

    print(f"✅ Season {season_id}: {total_results} results, MD {fixtures_md} ({fixtures_count} fixtures)")
    return season_id, total_results, fixtures_md, fixtures_count
   

def detect_current_state():
    """
    Return the live season, its current (unfinished) round, and matchday index.
    Current MD = first round with fewer results than total events.
    """
    try:
        seasons = get_active_seasons()
    except Exception as e:
        print(f"detect_current_state: seasons fetch failed: {e}")
        return None

    if not seasons:
        return None

    seasons_sorted = sorted(seasons, key=lambda s: int(s["season_id"]), reverse=True)

    # ---- 1. Pick live season ----
    live = None
    for s in seasons_sorted:
        valid = [(rid, md) for rid, md in s["rounds"] if rid]
        if not valid:
            continue
        try:
            events = get_events_for_round(valid[0][0])
            first_results = sum(1 for e in events if e.get("ft_home") is not None)
        except Exception:
            continue
        if first_results == 0:
            continue  # future season — no results at all

        # This season has started — check if it has any unfinished round
        # to confirm it's the LIVE one (not a completed past season)
        has_unfinished = False
        for rid, _ in valid:
            try:
                evs = get_events_for_round(rid)
                r = sum(1 for e in evs if e.get("ft_home") is not None)
                if r < len(evs):
                    has_unfinished = True
                    break
            except Exception:
                continue

        if has_unfinished:
            live = s
            print(f"🎯 Live season detected: {s['season_id']}")
            break

    if not live:
        # Fallback: use second-highest season
        live = seasons_sorted[1] if len(seasons_sorted) > 1 else seasons_sorted[0]
        print(f"⚠️ No live season found — using fallback {live['season_id']}")

    # ---- 2. Find current MD: first with results < total ----
    for idx, (rid, _) in enumerate(live["rounds"], start=1):
        if not rid:
            continue
        try:
            events = get_events_for_round(rid)
        except Exception:
            continue
        results = sum(1 for e in events if e.get("ft_home") is not None)
        total = len(events)
        if results < total:
            print(f"🎯 Current MD: {idx} ({results}/{total} results)")
            return {
                "live_season_id": live["season_id"],
                "current_round_id": rid,
                "current_matchday_num": idx,
                "results_so_far": results,
                "total_matches": total,
            }

    # All rounds complete
    print(f"✅ Season {live['season_id']} complete")
    return {
        "live_season_id": live["season_id"],
        "current_round_id": live["rounds"][-1][0],
        "current_matchday_num": len(live["rounds"]),
        "results_so_far": 0,
        "total_matches": 0,
    }


import time as _time
from datetime import datetime as _dt

def run_continuous_pipeline(
    json_path="accuracy_data.json",
    poll_interval=10,
    stop_flag=None,
    log_func=print,
):
    """
    Continuously:
      1. Detect live season & current matchday (first with 0 results).
      2. Sync results for all played matchdays.
      3. Predict fixtures of the current matchday.
      4. Wait for results to appear (poll every `poll_interval` seconds).
      5. Store results, advance to next matchday.
      6. Repeat until MD 34, then restart on new season.
    """
    while True:
        # Check stop signal
        if stop_flag and stop_flag():
            log_func("⏹️ Stop signal received – exiting continuous pipeline.")
            break

        try:
            seasons = get_active_seasons()
        except Exception as e:
            log_func(f"⚠️ API unreachable: {e}. Retrying in {poll_interval}s...")
            _time.sleep(poll_interval)
            continue

        if not seasons:
            log_func("⚠️ No active seasons found.")
            _time.sleep(poll_interval)
            continue

        seasons_sorted = sorted(seasons, key=lambda s: int(s["season_id"]), reverse=True)

        # ---- 1. Find live season ----
        live = None
        for s in seasons_sorted:
            valid = [(rid, rnum) for rid, rnum in s["rounds"] if rid]
            if not valid:
                continue
            # Quick check: first & last round status
            try:
                first_events = get_events_for_round(valid[0][0])
                first_results = sum(1 for ev in first_events if ev.get("ft_home") is not None)
            except Exception:
                continue
            if first_results == 0:
                continue  # future season
            # Check last round
            try:
                last_events = get_events_for_round(valid[-1][0])
                last_results = sum(1 for ev in last_events if ev.get("ft_home") is not None)
                last_total = len(last_events)
            except Exception:
                last_results, last_total = 0, 0
            if last_results < last_total:
                live = s
                break
        if not live:
            # fall back to highest with results
            for s in seasons_sorted:
                if s["rounds"]:
                    live = s
                    break
        if not live:
            log_func("⚠️ No live season found.")
            _time.sleep(poll_interval)
            continue

        season_id = live["season_id"]
        log_func(f"📡 Live season: {season_id}")
    

        # ---- 2. Find current matchday (first with 0 results) ----
        current_md = None
        current_rid = None
        for idx, (rid, rnum) in enumerate(live["rounds"], start=1):
            if not rid:
                continue
            try:
                events = get_events_for_round(rid)
            except Exception:
                continue
            results = sum(1 for ev in events if ev.get("ft_home") is not None)
            fixtures = sum(1 for ev in events if ev.get("ft_home") is None)
            if results == 0 and fixtures > 0:
                current_md = idx
                current_rid = rid
                break

        if current_md is None:
            log_func("✅ Season complete. Waiting for next season...")
            _time.sleep(60)
            continue

        log_func(f"🎯 Current matchday: MD {current_md} (round {current_rid})")

        # ---- 3. Sync all played matchdays + predict current ----
        try:
            # Sync results for all earlier MDs
            sync_season_results(live, json_path, log_func)

            # Predict current MD
            predict_matchday(live, current_md, json_path, log_func)
        except Exception as e:
            log_func(f"❌ Sync/predict error: {e}")
            _time.sleep(poll_interval)
            continue

        # ---- 4. Wait for results of current MD to appear ----
        log_func(f"⏳ Waiting for MD {current_md} results...")
        while True:
            if stop_flag and stop_flag():
                break
            try:
                events = get_events_for_round(current_rid)
                results_count = sum(1 for ev in events if ev.get("ft_home") is not None)
                total = len(events)
            except Exception:
                _time.sleep(poll_interval)
                continue
            if results_count == total and total > 0:
                log_func(f"✅ MD {current_md} results complete ({total}/{total}).")
                # Store results and advance
                store_matchday_results(live, current_md, json_path, log_func)
                break
            _time.sleep(poll_interval)

        # Loop continues to next matchday
        log_func(f"➡️ Advancing to next matchday...")
        _time.sleep(2)  # tiny pause

    log_func("🔚 Continuous pipeline stopped.")

def sync_season_results(season, json_path, log_func):
    """Store results for all fully played matchdays in the season."""
    import json, os
    if os.path.exists(json_path):
        with open(json_path) as f:
            data = json.load(f)
    else:
        data = {}

    for idx, (rid, rnum) in enumerate(season["rounds"], start=1):
        if not rid:
            continue
        try:
            events = get_events_for_round(rid)
        except Exception:
            continue
        results = []
        fixtures = []
        for ev in events:
            home = ev.get("home_team")
            away = ev.get("away_team")
            ft_h = ev.get("ft_home")
            ft_a = ev.get("ft_away")
            if not home or not away:
                continue
            if ft_h is not None and ft_a is not None:
                result_str = "Home Win" if ft_h > ft_a else ("Away Win" if ft_h < ft_a else "Draw")
                results.append({
                    "home": home, "away": away, "result": result_str,
                    "ft_h": ft_h, "ft_a": ft_a,
                    "over25_actual": (ft_h + ft_a) > 2.5,
                    "btts_actual": ft_h > 0 and ft_a > 0
                })
            else:
                fixtures.append({"home": home, "away": away, "league": ev.get("league")})

        key = str(idx)
        if key not in data:
            data[key] = {"predictions": [], "results": [], "fixtures": []}
        data[key]["results"] = results
        # Clear fixtures if results now exist for this MD
        if results:
            data[key]["fixtures"] = []
        else:
            data[key]["fixtures"] = fixtures

    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    log_func(f"   ✅ Synced results for {len(season['rounds'])} matchdays.")


def predict_matchday(season, md_num, json_path, log_func):
    """Run predictions for a specific matchday and store them."""
    import json, os
    from utils.automation_engine import _run_predictions_core   # reuse your 11-algo core

    if not os.path.exists(json_path):
        return
    with open(json_path) as f:
        data = json.load(f)

    key = str(md_num)
    if key not in data or not data[key].get("fixtures"):
        log_func(f"   ⚠️ No fixtures for MD {md_num}.")
        return

    fixtures = data[key]["fixtures"]
    # Build training set from all earlier matchdays
    training = []
    for md in data:
        if not md.isdigit() or int(md) >= md_num:
            continue
        for r in data[md].get("results", []):
            training.append({
                "home": r["home"], "away": r["away"],
                "ft_h": r["ft_h"], "ft_a": r["ft_a"]
            })

    if len(training) < 50:
        log_func(f"   ⚠️ Only {len(training)} training matches – need 50+.")
        return

    predictions = _run_predictions_core(training, fixtures)
    data[key]["predictions"] = predictions

    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    log_func(f"   ✅ Predicted {len(predictions)} fixtures for MD {md_num}.")


def store_matchday_results(season, md_num, json_path, log_func):
    """Store the completed results for a matchday."""
    import json, os
    rid = None
    for idx, (r_id, r_num) in enumerate(season["rounds"], start=1):
        if idx == md_num:
            rid = r_id
            break
    if not rid:
        return
    try:
        events = get_events_for_round(rid)
    except Exception as e:
        log_func(f"   ❌ Fetch results failed: {e}")
        return

    results = []
    for ev in events:
        home = ev.get("home_team")
        away = ev.get("away_team")
        ft_h = ev.get("ft_home")
        ft_a = ev.get("ft_away")
        if not home or not away or ft_h is None or ft_a is None:
            continue
        result_str = "Home Win" if ft_h > ft_a else ("Away Win" if ft_h < ft_a else "Draw")
        results.append({
            "home": home, "away": away, "result": result_str,
            "ft_h": ft_h, "ft_a": ft_a,
            "over25_actual": (ft_h + ft_a) > 2.5,
            "btts_actual": ft_h > 0 and ft_a > 0
        })

    with open(json_path) as f:
        data = json.load(f)
    data[str(md_num)]["results"] = results
    data[str(md_num)]["fixtures"] = []   # clear fixtures now that they're played
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    log_func(f"   📥 Stored {len(results)} results for MD {md_num}.")