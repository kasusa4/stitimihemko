# utils/event_listener.py
"""
Background event-driven listener.
Polls all monitored entities every POLL_INTERVAL seconds.
Only triggers the pipeline when it detects a change (new week / new season).
"""

import asyncio
import json
import os
import threading
import time
from collections import defaultdict

import aiohttp

# ---------------- CONFIG ----------------
POLL_INTERVAL = 5          # seconds between polls
HTTP_TIMEOUT = 5           # seconds per API call
CACHE_TTL = 120            # seconds to cache identical API responses

PROGRESS_FILE = "listener_progress.json"
STATE_ARCHIVE = "listener_state_archive.json"

# ---------------- GLOBAL STATE ----------------
_listener_thread = None
_listener_stop = threading.Event()
_pipeline_lock = threading.Lock()          # only one pipeline at a time
_entity_running = set()                    # which entities are processing now
_entity_lock = threading.Lock()            # protects _entity_running
_last_poll_ts = 0
_poll_stats = {"polls": 0, "changes": 0, "errors": 0, "last_run": 0}


# ---------------- PROGRESS PERSISTENCE ----------------
def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return {}
    try:
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_progress(progress):
    tmp = PROGRESS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(progress, f, indent=2)
    os.replace(tmp, PROGRESS_FILE)


# ---------------- ENTITY DEFINITIONS ----------------
def get_entities():
    """
    Returns a dict of entities to monitor.
    Each entity: {"id": name, "type": "betpawa"|"vunjabei", "config": {...}}
    """
    return {
        "betpawa": {
            "id": "betpawa",
            "type": "betpawa",
            "config": {},
        },
        # Add more if you want to monitor VunjaBei in parallel:
        # "vunjabei_english": {"id": "vunjabei_english", "type": "vunjabei", "config": {"league": "English"}},
    }


# ---------------- ASYNC STATE FETCHER ----------------
async def fetch_betpawa_state(session):
    """
    Fetch the current live season + current matchday for BetPawa.
    Returns dict: {season_id, current_md, has_results, results_count, fixtures_count}
    """
    from utils.betpawa_sync import get_active_seasons, get_events_for_round

    # Seasons fetch (sync call → wrap in executor)
    loop = asyncio.get_event_loop()
    seasons = await loop.run_in_executor(None, get_active_seasons)
    if not seasons:
        return None

    seasons_sorted = sorted(seasons, key=lambda s: int(s["season_id"]), reverse=True)

    live = None
    for s in seasons_sorted:
        valid = [(rid, rnum) for rid, rnum in s["rounds"] if rid]
        if not valid:
            continue
        try:
            first_events = await loop.run_in_executor(None, get_events_for_round, valid[0][0])
            first_results = sum(1 for ev in first_events if ev.get("ft_home") is not None)
        except Exception:
            continue
        if first_results == 0:
            continue
        try:
            last_events = await loop.run_in_executor(None, get_events_for_round, valid[-1][0])
            last_results = sum(1 for ev in last_events if ev.get("ft_home") is not None)
            last_total = len(last_events)
        except Exception:
            last_results, last_total = 0, 0
        if last_results < last_total:
            live = s
            break

    if not live:
        return None

    # Find current MD = first with 0 results but >0 fixtures
    current_md = None
    current_round = None
    results_count = 0
    fixtures_count = 0
    for idx, (rid, rnum) in enumerate(live["rounds"], start=1):
        if not rid:
            continue
        try:
            events = await loop.run_in_executor(None, get_events_for_round, rid)
        except Exception:
            continue
        r = sum(1 for ev in events if ev.get("ft_home") is not None)
        f = sum(1 for ev in events if ev.get("ft_home") is None)
        results_count += r
        if r == 0 and f > 0:
            current_md = idx
            current_round = rid
            fixtures_count = f
            break

    return {
        "season_id": live["season_id"],
        "current_md": current_md,
        "current_round": current_round,
        "results_count": results_count,
        "fixtures_count": fixtures_count,
    }


# ---------------- CHANGE DETECTION ----------------
def detect_change(progress, entity_id, new_state):
    """
    Compare the new API state vs stored progress.
    Returns (event, message):
      - "season_rollover" : new season started
      - "new_week"        : new matchday available with results or fixtures
      - "no_change"       : nothing to do
    """
    prev = progress.get(entity_id, {})
    prev_season = prev.get("season_id")
    prev_md = prev.get("current_md")

    new_season = new_state.get("season_id")
    new_md = new_state.get("current_md")

    if prev_season != new_season:
        return "season_rollover", f"Season {prev_season} → {new_season}"

    if new_md is not None and new_md != prev_md:
        return "new_week", f"MD {prev_md} → {new_md}"

    return "no_change", ""


# ---------------- PIPELINE TRIGGER ----------------
async def trigger_pipeline(entity, state, session):
    """
    Run the full pipeline for this entity.
    Offloads heavy sync work to threads.
    """
    from utils.betpawa_sync import sync_latest_season, get_events_for_round

    loop = asyncio.get_event_loop()
    entity_id = entity["id"]

    # Per-entity lock
    with _entity_lock:
        if entity_id in _entity_running:
            print(f"⏭️ {entity_id} already running — skipping")
            return
        _entity_running.add(entity_id)

    try:
        print(f"🚀 Pipeline START [{entity_id}] season={state['season_id']} MD={state['current_md']}")

        # 1. Sync latest season (results + fixtures)
        synced = await loop.run_in_executor(
            None,
            lambda: sync_latest_season("accuracy_data.json", force=True)
        )
        season_id, results, fx_md, fx_count = synced
        print(f"   ✅ Synced: {results} results, MD {fx_md} ({fx_count} fixtures)")

        # 2. Run predictions
        from utils.pipeline import run_predictions_for_md
        preds = await loop.run_in_executor(
            None,
            lambda: run_predictions_for_md(fx_md, "accuracy_data.json")
        )
        print(f"   ✅ Predicted {len(preds) if preds else 0} fixtures for MD {fx_md}")

        # 3. Update Streamlit session state (best-effort)
        try:
            import streamlit as st
            st.session_state.last_pipeline_run = time.time()
            st.session_state.last_pipeline_md = fx_md
            st.session_state.last_pipeline_season = season_id
        except Exception:
            pass

        _poll_stats["last_run"] = time.time()

    except Exception as e:
        print(f"❌ Pipeline error [{entity_id}]: {e}")
        _poll_stats["errors"] += 1
    finally:
        with _entity_lock:
            _entity_running.discard(entity_id)


# ---------------- MAIN POLL LOOP ----------------
async def poll_loop():
    """Continuous async poll → detect → trigger pipeline."""
    global _last_poll_ts

    progress = load_progress()

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as session:
        while not _listener_stop.is_set():
            _poll_stats["polls"] += 1
            _last_poll_ts = time.time()

            for entity_id, entity in get_entities().items():
                try:
                    state = await fetch_betpawa_state(session)  # TODO: dispatch per type
                    if not state:
                        continue

                    event, msg = detect_change(progress, entity_id, state)
                    if event == "no_change":
                        continue

                    print(f"🔔 Change detected [{entity_id}]: {event} — {msg}")
                    _poll_stats["changes"] += 1

                    # Archive old state on season rollover
                    if event == "season_rollover":
                        archive = load_archive()
                        prev = progress.get(entity_id, {})
                        if prev.get("season_id"):
                            archive.append({
                                "entity": entity_id,
                                "season_id": prev.get("season_id"),
                                "archived_at": time.time(),
                            })
                            save_archive(archive)

                    # Update progress BEFORE running pipeline
                    progress[entity_id] = {
                        "season_id": state["season_id"],
                        "current_md": state["current_md"],
                        "results_count": state["results_count"],
                        "updated_at": time.time(),
                    }
                    save_progress(progress)

                    # Trigger pipeline
                    await trigger_pipeline(entity, state, session)

                except Exception as e:
                    print(f"❌ Poll error [{entity_id}]: {e}")
                    _poll_stats["errors"] += 1

            # Sleep until next poll
            await asyncio.sleep(POLL_INTERVAL)


def load_archive():
    if not os.path.exists(STATE_ARCHIVE):
        return []
    try:
        with open(STATE_ARCHIVE) as f:
            return json.load(f)
    except Exception:
        return []


def save_archive(archive):
    tmp = STATE_ARCHIVE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(archive, f, indent=2)
    os.replace(tmp, STATE_ARCHIVE)


# ---------------- PUBLIC API ----------------
def _thread_main():
    """Runs the async event loop inside the background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(poll_loop())
    except Exception as e:
        print(f"❌ Listener crashed: {e}")
    finally:
        loop.close()


def start_listener():
    """Start the background listener exactly once."""
    global _listener_thread
    if _listener_thread is not None and _listener_thread.is_alive():
        print("ℹ️ Listener already running")
        return

    _listener_stop.clear()
    _listener_thread = threading.Thread(
        target=_thread_main, daemon=True, name="event-listener"
    )
    _listener_thread.start()
    print("✅ Event listener started")


def stop_listener():
    """Signal the listener to stop."""
    _listener_stop.set()
    print("⏹️ Listener stop requested")


def get_listener_stats():
    """Return current stats for the UI."""
    return {
        **_poll_stats,
        "last_poll_ts": _last_poll_ts,
        "running": _listener_thread is not None and _listener_thread.is_alive(),
        "entities_running": list(_entity_running),
    }