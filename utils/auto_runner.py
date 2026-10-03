# utils/auto_runner.py
"""
Simple auto-runner: syncs BetPawa, finds the current MD with fixtures,
runs Over 2.5 predictions, saves to accuracy_data.json.
Runs on a background thread. Only acts when the current MD changes.
"""

import threading
import time
import json
import os

# ---------------- GLOBAL STATE ----------------
_runner_thread = None
_runner_stop = threading.Event()
_runner_status = {
    "running": False,
    "last_sync_ts": 0,
    "last_predict_ts": 0,
    "last_md": None,
    "last_season": None,
    "last_pred_md": None,       # ← NEW
    "last_pred_season": None,   # ← NEW
    "cycles": 0,
    "errors": 0,
    "last_error_ts": 0,       # ← add this
    "current_phase": "idle",
}
_status_lock = threading.Lock()

SYNC_INTERVAL = 30       # seconds between full syncs
PREDICT_COOLDOWN = 60    # seconds between predictions for the same MD


# ---------------- STATUS HELPERS ----------------
def _set_status(**kwargs):
    with _status_lock:
        _runner_status.update(kwargs)


def get_runner_status():
    with _status_lock:
        return dict(_runner_status)


# ---------------- AUTO-LOGIC ----------------
def _check_and_predict():
    """
    One cycle:
      1. Sync accuracy_data.json with latest BetPawa data.
      2. Find the current MD (first with fixtures but no results).
      3. If not yet predicted for this season → run predictions.
      4. Save.
    """
    from utils.betpawa_sync import sync_latest_season

    # ---- 1. Sync ----
    _set_status(current_phase="syncing")
    try:
        sync_result = sync_latest_season("accuracy_data.json", force=True)
    except Exception as e:
        print(f"❌ Auto-runner sync error: {e}")
        import traceback; traceback.print_exc()
        _set_status(errors=_runner_status["errors"] + 1,
                    last_error_ts=time.time())
        return False

    # Guard against None return
    if not sync_result or len(sync_result) != 4:
        print("⚠️ Sync returned no data — skipping this cycle")
        _set_status(current_phase="waiting")
        return False

    season_id, results, fx_md, fx_count = sync_result

    if not fx_md:
        _set_status(current_phase="idle", last_sync_ts=time.time())
        print("ℹ️ No matchday with fixtures — waiting...")
        return False

    _set_status(current_phase="sync done", last_sync_ts=time.time())

    # ---- 2. Load JSON ----
    data_path = "accuracy_data.json"
    try:
        with open(data_path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load accuracy_data.json: {e}")
        return False

    key = str(fx_md)
    entry = data.get(key, {})
    fixtures = entry.get("fixtures", [])
    existing_preds = entry.get("predictions", [])

    if not fixtures:
        _set_status(current_phase="idle")
        return False

    # ---- 3. Skip logic: use last PREDICTED (season, md) ----
    last_pred_season = _runner_status.get("last_pred_season")
    last_pred_md     = _runner_status.get("last_pred_md")
    last_pred_ts     = _runner_status.get("last_predict_ts", 0)

    same_target = (last_pred_season == season_id and last_pred_md == fx_md)

    if same_target and existing_preds:
        # Cooldown: don't re-predict the same MD more often than every 10 min
        age = time.time() - last_pred_ts
        if age < 600:
            _set_status(
                current_phase="cached",
                last_season=season_id,
                last_md=fx_md,
            )
            print(f"⏩ MD {fx_md} already predicted {int(age)}s ago — skipping")
            return False
        else:
            print(f"🔄 Re-predicting MD {fx_md} (cooldown expired, {int(age)}s old)")

    if not same_target:
        print(f"🔄 New target: season {season_id} MD {fx_md} "
              f"(was season {last_pred_season} MD {last_pred_md})")

    # ---- 4. Build training set ----
    training = []
    for md in data:
        if not md.isdigit() or int(md) >= int(fx_md):
            continue
        for r in data[md].get("results", []):
            training.append({
                "home": r["home"], "away": r["away"],
                "ft_h": r["ft_h"], "ft_a": r["ft_a"]
            })

    if len(training) < 50:
        print(f"⚠️ Only {len(training)} training matches (need 50+)")
        _set_status(current_phase="waiting for data")
        return False

    # ---- 5. Run predictions ----
    _set_status(current_phase=f"predicting MD {fx_md}")
    print(f"🔮 Running Over 2.5 predictions for MD {fx_md} ({len(fixtures)} fixtures)...")

    try:
        from utils.predictor_core import run_predictions_core
        preds = run_predictions_core(training, fixtures)
    except Exception as e:
        print(f"❌ Prediction error: {e}")
        import traceback; traceback.print_exc()
        _set_status(errors=_runner_status["errors"] + 1,
                    last_error_ts=time.time())
        return False

    if not preds:
        print("⚠️ Prediction returned empty list")
        _set_status(current_phase="error")
        return False

    # ---- 6. Save ----
    data[key]["predictions"] = preds
    tmp = data_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, data_path)

    _set_status(
        current_phase="done",
        last_predict_ts=time.time(),
        last_pred_season=season_id,     # ← NEW: separate tracker
        last_pred_md=fx_md,             # ← NEW: separate tracker
        last_season=season_id,
        last_md=fx_md,
    )
    print(f"✅ Predicted {len(preds)} fixtures for season {season_id} MD {fx_md}")

    # Update Streamlit session state (best-effort)
    try:
        import streamlit as st
        st.session_state.auto_last_md = fx_md
        st.session_state.auto_last_predict_ts = time.time()
    except Exception:
        pass

    return True


def _runner_loop():
    """Main loop — runs cycles with a sleep between them."""
    print("🚀 Auto-runner started")
    while not _runner_stop.is_set():
        try:
            _set_status(running=True, cycles=_runner_status["cycles"] + 1)
            _check_and_predict()
        except Exception as e:
            print(f"❌ Auto-runner loop error: {e}")
            _set_status(errors=_runner_status["errors"] + 1)

        # Sleep in small chunks so we can react to stop quickly
        for _ in range(SYNC_INTERVAL):
            if _runner_stop.is_set():
                break
            time.sleep(1)

    _set_status(running=False, current_phase="stopped")
    print("⏹️ Auto-runner stopped")


# ---------------- PUBLIC API ----------------
def start_runner():
    """Start the background auto-runner (idempotent)."""
    global _runner_thread
    if _runner_thread is not None and _runner_thread.is_alive():
        print("ℹ️ Auto-runner already running")
        return
    _runner_stop.clear()
    _runner_thread = threading.Thread(
        target=_runner_loop, daemon=True, name="auto-runner"
    )
    _runner_thread.start()


def stop_runner():
    """Request the runner to stop."""
    _runner_stop.set()
    print("⏹️ Stop requested")


def is_running():
    return _runner_thread is not None and _runner_thread.is_alive()