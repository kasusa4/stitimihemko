# ============================================================
# app.py – APEX Engine (FULLY RESTRUCTURED & WORKING)
# ============================================================
import streamlit as st
import pandas as pd
import numpy as np
from collections import defaultdict
import time
from datetime import datetime
import hashlib
import json
import os

# --- Your imports ---
from config import LEAGUE_TEAMS
from utils.ocr_utils import extract_text_from_image
from utils.parser_utils import (
    parse_results, parse_fixtures, parse_batch, parse_batch_fixtures,
    clean_fixtures_from_text
)
from utils.simulation_utils import LeagueStats
from utils.apex_utils import generate_summary
from utils.pattern_utils import PatternDetector, detect_math_patterns
from utils.advanced_algorithms import (
    ELO_Rating, MarkovChainPredictor, LogisticPredictor,
    HighConcedingDetector, ConsensusVoter,
    PoissonPredictor, DixonColesPredictor,
    BayesianPredictor, WeightedFormPredictor,
    compute_confidence
)
from utils.prediction_boost import (
    LeakyDefenseDetector, FormTrendDetector, CorrectScorePredictor
)
#from utils.htft_scraper import fetch_htft_odds, clear_htft_cache
from utils.session_manager import SessionManager
from utils.session_analyzer import display_session_comparison
from utils.virtual_odds_api import VirtualOddsAPI
#from utils.htft_dashboard import show_htft_dashboard
from utils.virtual_odds_integration import VirtualOddsIntegration
from utils.leagues_config import LEAGUES

from utils.kalman_predictor import KalmanTeamStrength
from utils.xgb_predictor import XGBGoalPredictor
from utils.meta_learner import MetaLearner
from utils.score_matrix import build_score_matrix, summarize_matrix
from utils.calibration import ConfidenceCalibrator


# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Kasusa Engine⚽",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=10000, key="auto_ui_refresh")   # 10s UI refresh

# ---------- START AUTO-RUNNER (ONCE AT BOOT) ----------
from utils.auto_runner import start_runner, is_running

if "auto_runner_started" not in st.session_state:
    start_runner()
    st.session_state.auto_runner_started = True
    print("✅ Auto-runner boot-strapped")





# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================
if 'league_accum' not in st.session_state:
    st.session_state.league_accum = {}
    for name in LEAGUE_TEAMS.keys():
        st.session_state.league_accum[name] = {
            'results': [],
            'fixtures_data': None,
            'processed': False
        }

if 'all_predictions' not in st.session_state:
    st.session_state.all_predictions = []

if 'processing_log' not in st.session_state:
    st.session_state.processing_log = []

if 'current_predictions' not in st.session_state:
    st.session_state.current_predictions = []
if 'current_matchday' not in st.session_state:
    st.session_state.current_matchday = None
if 'batch_matchday' not in st.session_state:
    st.session_state.batch_matchday = 1

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'user_data_loaded' not in st.session_state:
    st.session_state.user_data_loaded = False

if 'session_manager' not in st.session_state:
    st.session_state.session_manager = SessionManager(max_sessions=50)

# Automation engine
if 'auto_engine' not in st.session_state:
    st.session_state.auto_engine = AutomationEngine()


# ============================================================
# HELPER FUNCTIONS
# ============================================================
# ============================================================
# SAFE JSON HELPERS
# ============================================================
import tempfile

def to_json_safe(obj):
    """Recursively convert numpy types to native Python types for JSON serialization."""
    try:
        import numpy as np
    except ImportError:
        return obj
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_json_safe(v) for v in obj]
    elif isinstance(obj, tuple):
        return [to_json_safe(v) for v in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj


def safe_json_write(path, data):
    """Write JSON atomically — never leaves a corrupted file."""
    data = to_json_safe(data)
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)   # atomic on Windows & Linux
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


# ============================================================
# AUTO PILOT HELPERS
# ============================================================
# ============================================================
# AUTO PILOT — ROBUST VERSION
# ============================================================
import time as _time
import json as _json
import os as _os
import tempfile as _tmp
import threading as _threading
from datetime import datetime as _dt

STATE_FILE = "auto_pilot_state.json"
BACKUP_FILE = "accuracy_data.backup.json"
LOG_LIMIT = 500
MAX_CONSECUTIVE_ERRORS = 5
ERROR_BACKOFF_SECONDS = 60  # after too many errors, wait 1 min before retry

# Thread lock — prevents concurrent ticks
_ap_lock = _threading.Lock()


def _log_auto(msg):
    if 'auto_pilot_log' not in st.session_state:
        st.session_state.auto_pilot_log = []
    ts = _dt.now().strftime("%H:%M:%S")
    st.session_state.auto_pilot_log.append(f"[{ts}] {msg}")
    if len(st.session_state.auto_pilot_log) > LOG_LIMIT:
        st.session_state.auto_pilot_log = st.session_state.auto_pilot_log[-LOG_LIMIT:]


def _load_state():
    if _os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return _json.load(f)
        except Exception:
            pass
    return {
        "last_season_id": None,
        "last_round_id": None,
        "last_matchday": None,
        "last_success_ts": 0,
        "consecutive_errors": 0,
        "last_error_ts": 0,
    }


def _save_state(state):
    """Atomic state save."""
    dir_name = _os.path.dirname(STATE_FILE) or "."
    fd, tmp = _tmp.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with _os.fdopen(fd, "w") as f:
            _json.dump(state, f, indent=2)
        _os.replace(tmp, STATE_FILE)
    except Exception:
        if _os.path.exists(tmp):
            _os.remove(tmp)
        raise


def _backup_accuracy_data():
    """Backup accuracy_data.json before writing."""
    if _os.path.exists("accuracy_data.json"):
        try:
            import shutil
            shutil.copy2("accuracy_data.json", BACKUP_FILE)
        except Exception as e:
            _log_auto(f"⚠️ Backup failed: {e}")


def _restore_from_backup():
    """Restore accuracy_data.json from backup if the main file is corrupt."""
    if _os.path.exists(BACKUP_FILE):
        try:
            import shutil
            shutil.copy2(BACKUP_FILE, "accuracy_data.json")
            _log_auto("🔄 Restored accuracy_data.json from backup")
            return True
        except Exception:
            pass
    return False


def _is_api_healthy():
    """Quick ping to BetPawa — returns True if reachable."""
    try:
        from utils.betpawa_sync import get_active_seasons
        seasons = get_active_seasons()
        return bool(seasons)
    except Exception:
        return False


def _should_backoff(state):
    """Check if we should back off after repeated errors."""
    errs = state.get("consecutive_errors", 0)
    last_err_ts = state.get("last_error_ts", 0)
    if errs < MAX_CONSECUTIVE_ERRORS:
        return False
    # Backoff period passed?
    return (_time.time() - last_err_ts) < ERROR_BACKOFF_SECONDS


def _record_error(state):
    state["consecutive_errors"] = state.get("consecutive_errors", 0) + 1
    state["last_error_ts"] = _time.time()
    _save_state(state)


def _record_success(state):
    state["consecutive_errors"] = 0
    state["last_success_ts"] = _time.time()
    _save_state(state)


def _run_predictions_core(training_matches, fixtures):
    """Core prediction — 11 algorithms + meta-learner + score matrix."""
    from utils.advanced_algorithms import (
        ELO_Rating, MarkovChainPredictor, LogisticPredictor,
        ConsensusVoter, PoissonPredictor, DixonColesPredictor,
        BayesianPredictor, WeightedFormPredictor
    )
    from utils.kalman_predictor import KalmanTeamStrength
    from utils.xgb_predictor import XGBGoalPredictor
    from utils.meta_learner import MetaLearner
    from utils.score_matrix import build_score_matrix, summarize_matrix
    from utils.simulation_utils import LeagueStats
    from scipy.stats import poisson as _pd

    elo      = ELO_Rating()
    markov   = MarkovChainPredictor()
    logistic = LogisticPredictor()
    poisson  = PoissonPredictor()
    dixon    = DixonColesPredictor()
    bayes    = BayesianPredictor()
    form     = WeightedFormPredictor()
    stats    = LeagueStats("BetPawa")
    kalman   = KalmanTeamStrength()
    xgb_model = XGBGoalPredictor()
    meta     = MetaLearner()

    # Train all algorithms
    for m in training_matches:
        h, a, fh, fa = m["home"], m["away"], m["ft_h"], m["ft_a"]
        elo.update_ratings(h, a, fh, fa)
        if fh > fa:
            markov.add_result(h, 'W'); markov.add_result(a, 'L')
        elif fh == fa:
            markov.add_result(h, 'D'); markov.add_result(a, 'D')
        else:
            markov.add_result(h, 'L'); markov.add_result(a, 'W')
        logistic.add_match(h, a, fh, fa)
        poisson.add_match(h, a, fh, fa)
        dixon.add_match(h, a, fh, fa)
        bayes.add_match(h, a, fh, fa)
        form.add_match(h, a, fh, fa)
        stats.add_match(h, a, fh, fa, fh, fa)
        kalman.add_match(h, a, fh, fa)
        xgb_model.add_match(h, a, fh, fa)

    xgb_model.fit()

    # Train meta-learner
    for m in training_matches[-500:]:   # only recent 500 for speed
        h, a, fh, fa = m["home"], m["away"], m["ft_h"], m["ft_a"]
        actual = "home" if fh > fa else ("draw" if fh == fa else "away")
        try:
            algo_preds = {
                "elo": elo.predict_match(h, a),
                "markov": markov.predict_match(h, a),
                "poisson": poisson.predict_match(h, a),
                "dixon": dixon.predict_match(h, a),
                "bayes": bayes.predict_match(h, a),
                "form": form.predict_match(h, a),
                "kalman": kalman.predict_match(h, a),
                "xgb": xgb_model.predict_match(h, a),
            }
            meta.log_prediction(algo_preds, actual)
        except Exception:
            continue
    meta.fit_weights()

    voter = ConsensusVoter()
    voter.add_algorithm('stats_poisson', stats)
    voter.add_algorithm('elo', elo)
    voter.add_algorithm('markov', markov)
    voter.add_algorithm('logistic', logistic)
    voter.add_algorithm('dixon', dixon)
    voter.add_algorithm('bayesian', bayes)
    voter.add_algorithm('weighted_form', form)
    voter.add_algorithm('new_poisson', poisson)

    predictions = []
    for fx in fixtures:
        home, away = fx["home"], fx["away"]
        league = fx.get("league", "Unknown")
        try:
            cons = voter.predict_match(home, away)
            kal_pred = kalman.predict_match(home, away)
            xgb_pred = xgb_model.predict_match(home, away)
        except Exception:
            continue

        meta_result = meta.blend({"stats": cons, "kalman": kal_pred, "xgb": xgb_pred})

        lam_h = (kal_pred.get("expected_home_goals", 1.3) + xgb_pred.get("expected_home_goals", 1.3)) / 2
        lam_a = (kal_pred.get("expected_away_goals", 1.1) + xgb_pred.get("expected_away_goals", 1.1)) / 2
        matrix = build_score_matrix(lam_h, lam_a, max_goals=8)
        ms = summarize_matrix(matrix)

        try:
            sp = stats.predict_match(home, away, patterns=None, simulations=10000)
            stats_o25 = float(sp.get("over25", 0.5))
            stats_btts = float(sp.get("btts", 0.5))
        except Exception:
            stats_o25, stats_btts = 0.5, 0.5

        def pois_o25(lh, la):
            p_under = sum(_pd.pmf(i, lh) * _pd.pmf(j, la)
                          for i in range(10) for j in range(10) if i + j <= 2)
            return 1 - p_under

        poisson_o25 = pois_o25(lam_h, lam_a)
        over25 = round(ms["over25"] * 0.5 + stats_o25 * 0.25 + poisson_o25 * 0.25, 4)
        btts = round(ms["btts"] * 0.6 + stats_btts * 0.4, 4)

        algos_used = cons.get("algorithms_used", 0) + 2
        agreement = cons.get("agreement", 0)
        agreement_str = f"{int(round(agreement * algos_used))}/{algos_used}" if algos_used else "0/0"

        winner_code = meta_result.get("winner", "draw")
        if winner_code == "home":
            pick = f"{home} Win"; conf = meta_result.get("home_win", 0)
        elif winner_code == "away":
            pick = f"{away} Win"; conf = meta_result.get("away_win", 0)
        else:
            pick = "Draw"; conf = meta_result.get("draw", 0)

        if over25 >= 0.75: rating = "🥇 Elite O2.5"
        elif over25 >= 0.65: rating = "🥈 High O2.5"
        elif over25 >= 0.55: rating = "🥉 Medium O2.5"
        elif over25 >= 0.45: rating = "⚠️ Risky"
        else: rating = "❌ Skip"

        predictions.append({
            "home": home, "away": away, "league": league,
            "over25_pct": round(over25 * 100, 1),
            "btts_pct": round(btts * 100, 1),
            "expected_goals": round(lam_h + lam_a, 2),
            "most_likely_score": ms["most_likely_score"],
            "rating": rating,
            "agreement": agreement_str,
            "algorithms_used": algos_used,
            "winner_pick": pick,
            "winner_conf": round(conf, 3),
            "home_win": round(meta_result.get("home_win", 0), 3),
            "draw": round(meta_result.get("draw", 0), 3),
            "away_win": round(meta_result.get("away_win", 0), 3),
        })

    predictions.sort(key=lambda x: x["over25_pct"], reverse=True)
    return predictions


def _auto_predict_current_md(force=False):
    """Predict the latest MD with fixtures; save atomically."""
    data_path = "accuracy_data.json"
    if not _os.path.exists(data_path):
        _log_auto("   ⚠️ No accuracy_data.json")
        return

    # Auto-recover from corruption
    try:
        with open(data_path) as f:
            data = _json.load(f)
    except Exception as e:
        _log_auto(f"   ⚠️ JSON corrupt: {e}")
        if _restore_from_backup():
            try:
                with open(data_path) as f:
                    data = _json.load(f)
            except Exception:
                _log_auto("   ❌ Backup restore failed")
                return
        else:
            _log_auto("   ❌ No backup available")
            return

    mds_with_fixtures = [k for k in data.keys() if k.isdigit() and data[k].get("fixtures")]
    if not mds_with_fixtures:
        _log_auto("   ⚠️ No fixtures to predict")
        return

    target_md = max(mds_with_fixtures, key=int)

    # Skip if already predicted (unless force)
    if not force and data[target_md].get("predictions"):
        _log_auto(f"   ⏭️ MD {target_md} already predicted")
        return

    fixtures = data[target_md]["fixtures"]
    _log_auto(f"   🔮 Predicting MD {target_md} ({len(fixtures)} fixtures)...")
    t0 = _time.time()

    training_matches = []
    for md in data.keys():
        if not md.isdigit() or int(md) >= int(target_md):
            continue
        for r in data[md].get("results", []):
            training_matches.append({
                "home": r["home"], "away": r["away"],
                "ft_h": r["ft_h"], "ft_a": r["ft_a"]
            })

    if len(training_matches) < 50:
        _log_auto(f"   ⚠️ Only {len(training_matches)} training matches (need 50+)")
        return

    try:
        predictions = _run_predictions_core(training_matches, fixtures)
    except Exception as e:
        _log_auto(f"   ❌ Prediction error: {e}")
        return

    # Backup + atomic write
    _backup_accuracy_data()
    data[target_md]["predictions"] = predictions
    dir_name = _os.path.dirname(data_path) or "."
    fd, tmp = _tmp.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with _os.fdopen(fd, "w", encoding="utf-8") as f:
            _json.dump(to_json_safe(data), f, indent=2)
        _os.replace(tmp, data_path)
    except Exception as e:
        if _os.path.exists(tmp):
            _os.remove(tmp)
        _log_auto(f"   ❌ Write failed: {e}")
        return

    elapsed = _time.time() - t0
    _log_auto(f"   ✅ Predicted {len(predictions)} fixtures for MD {target_md} ({elapsed:.1f}s)")
    if predictions:
        top = predictions[0]
        _log_auto(f"   🏆 Top O2.5: {top['home']} vs {top['away']} — {top['over25_pct']}%")


def _auto_pilot_tick():
    """
    Robust tick. Returns (changed: bool, message: str).
    Skips if another tick is running.
    """
    # Concurrency guard
    if not _ap_lock.acquire(blocking=False):
        return False, "tick already running"

    try:
        state = _load_state()

        # Backoff check
        if _should_backoff(state):
            remaining = int(ERROR_BACKOFF_SECONDS - (_time.time() - state["last_error_ts"]))
            return False, f"backoff ({remaining}s left)"

        # API health check
        if not _is_api_healthy():
            _record_error(state)
            return False, "API unreachable"

        from utils.betpawa_sync import detect_current_state, sync_latest_season

        detected = detect_current_state()
        if not detected:
            _record_error(state)
            return False, "detect failed"

        live_season = detected["live_season_id"]
        current_round = detected["current_round_id"]
        current_md = detected["current_matchday_num"]

        prev_season = state.get("last_season_id")
        prev_round = state.get("last_round_id")

        # CASE 1: new season
        if live_season != prev_season:
            _log_auto(f"🆕 New season: {live_season}")
            try:
                season_id, results, fx_md, fx_count = sync_latest_season("accuracy_data.json")
                _log_auto(f"   ✅ Synced: {results} results, MD {fx_md} ({fx_count} fixtures)")
                _auto_predict_current_md()
                _record_success(state)
                state.update({
                    "last_season_id": live_season,
                    "last_round_id": current_round,
                    "last_matchday": current_md,
                })
                _save_state(state)
                return True, f"new season {live_season}"
            except Exception as e:
                _log_auto(f"   ❌ Sync failed: {e}")
                _record_error(state)
                return False, "sync failed"

        # CASE 2: new matchday
        if current_round != prev_round:
            _log_auto(f"🎯 New MD: {current_md} (round {current_round})")
            try:
                season_id, results, fx_md, fx_count = sync_latest_season("accuracy_data.json")
                _log_auto(f"   ✅ Refreshed: {results} total, MD {fx_md} ({fx_count} fixtures)")
                _auto_predict_current_md()
                _record_success(state)
                state.update({
                    "last_season_id": live_season,
                    "last_round_id": current_round,
                    "last_matchday": current_md,
                })
                _save_state(state)
                return True, f"new matchday {current_md}"
            except Exception as e:
                _log_auto(f"   ❌ Sync failed: {e}")
                _record_error(state)
                return False, "sync failed"

        # CASE 3: no change
        _record_success(state)  # reset error counter
        return False, "no change"

    finally:
        _ap_lock.release()


def show_auto_pilot():
    """Change-driven 24/7 automation with backoff and self-healing."""
    from streamlit_autorefresh import st_autorefresh

    st.markdown("## 🤖 Auto Pilot — Change‑Driven 24/7")
    st.caption("Polls every 20s. Only acts on new seasons/matchdays. Self-healing on errors.")

    for k, default in [
        ('auto_pilot_enabled', False),
        ('auto_pilot_log', []),
        ('auto_pilot_tick_count', 0),
    ]:
        if k not in st.session_state:
            st.session_state[k] = default

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        if not st.session_state.auto_pilot_enabled:
            if st.button("▶️ Start Auto Pilot", type="primary", use_container_width=True):
                st.session_state.auto_pilot_enabled = True
                st.session_state.auto_pilot_log = []
                st.session_state.auto_pilot_tick_count = 0
                _log_auto("🚀 Auto Pilot started")
                st.rerun()
        else:
            if st.button("⏹️ Stop Auto Pilot", type="secondary", use_container_width=True):
                st.session_state.auto_pilot_enabled = False
                _log_auto("⏹️ Stopped")
                st.rerun()
    with c2:
        if st.button("🔍 Force Check", use_container_width=True):
            changed, msg = _auto_pilot_tick()
            _log_auto(f"🔍 Manual: {'✅ ' + msg if changed else msg}")
            st.rerun()
    with c3:
        if st.button("🔄 Force Re-Predict", use_container_width=True):
            _auto_predict_current_md(force=True)
            _log_auto("🔄 Force re-predict done")
            st.rerun()

    if st.session_state.auto_pilot_enabled:
        st_autorefresh(interval=20000, key="ap_tick")
        st.success("🟢 Auto Pilot RUNNING — change-driven, self-healing")

        st.session_state.auto_pilot_tick_count += 1
        changed, msg = _auto_pilot_tick()
        if changed:
            st.toast(f"⚡ {msg}", icon="🎯")

        state = _load_state()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Live Season", state.get("last_season_id") or "—")
        c2.metric("Matchday", state.get("last_matchday") or "—")
        c3.metric("Errors", state.get("consecutive_errors", 0))
        last_ok = state.get("last_success_ts", 0)
        c4.metric("Last Success", _dt.fromtimestamp(last_ok).strftime("%H:%M") if last_ok else "—")
    else:
        st.info("⏸️ Auto Pilot OFF.")

    st.markdown("---")
    st.subheader("📜 Activity Log")
    if st.session_state.auto_pilot_log:
        for line in reversed(st.session_state.auto_pilot_log[-60:]):
            st.text(line)
    else:
        st.caption("Waiting for events...")

    st.markdown("---")
    st.subheader("🔮 Latest Predictions")
    if _os.path.exists("accuracy_data.json"):
        try:
            with open("accuracy_data.json") as f:
                data = _json.load(f)
            mds = [k for k in data.keys() if k.isdigit() and data[k].get("predictions")]
            if mds:
                latest = max(mds, key=int)
                preds = data[latest]["predictions"]
                st.caption(f"Matchday **{latest}** — {len(preds)} predictions (sorted by Over 2.5)")
                df = pd.DataFrame(preds)
                if not df.empty:
                    st.dataframe(df, use_container_width=True, hide_index=True, height=400)

                    # Best bets
                    st.markdown("#### 🎯 Top 5 Over 2.5")
                    for i, p in enumerate(preds[:5], 1):
                        st.write(f"**{i}.** {p['home']} vs {p['away']} — **{p['over25_pct']}%** | "
                                 f"BTTS {p['btts_pct']}% | Exp {p['expected_goals']} | {p['most_likely_score']} | {p['rating']}")
            else:
                st.info("No predictions yet.")
        except Exception as e:
            st.warning(f"Could not load: {e}")

    import threading
    from utils.betpawa_sync import run_continuous_pipeline

    # Session‑level stop flag
    if 'pipeline_stop' not in st.session_state:
        st.session_state.pipeline_stop = False

    def _start_background_pipeline():
        thread = threading.Thread(
            target=run_continuous_pipeline,
            kwargs=dict(
                json_path="accuracy_data.json",
                poll_interval=10,
                stop_flag=lambda: st.session_state.pipeline_stop,
                log_func=lambda msg: print(msg)   # or push to a queue for UI
            ),
            daemon=True,
        )
        thread.start()
        return thread

    # In your Streamlit UI, add a button:
    if st.button("▶️ Start Continuous Pipeline"):
        st.session_state.pipeline_stop = False
        _start_background_pipeline()
        st.success("Pipeline started in background.")

    if st.button("⏹️ Stop Pipeline"):
        st.session_state.pipeline_stop = True
        st.warning("Stop signal sent.")



#auto pilot end here:::

#auto pilod dashboard end hereeeee

def encode_match_key(home, away):
    return f"{home}||{away}"

def decode_match_key(key_str):
    home, away = key_str.split('||')
    return home, away

USERS_FILE = "users.json"
DATA_DIR = "user_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def load_user_data(username):
    filepath = os.path.join(DATA_DIR, f"{username}.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_user_data(username, data):
    filepath = os.path.join(DATA_DIR, f"{username}.json")
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def login_user(username, password):
    users = load_users()
    if username in users and users[username] == hash_password(password):
        return True
    return False

def register_user(username, password):
    users = load_users()
    if username in users:
        return False
    users[username] = hash_password(password)
    save_users(users)
    save_user_data(username, {})
    return True

def logout_user():
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_data_loaded = False
    st.rerun()

def auto_save_user_data():
    if st.session_state.logged_in and st.session_state.username:
        data_to_save = {}
        for league, accum in st.session_state.league_accum.items():
            results_to_save = []
            for entry in accum['results']:
                day = entry['day']
                data_dict = entry['data']
                encoded_data = {}
                for (home, away), score_data in data_dict.items():
                    key_str = encode_match_key(home, away)
                    encoded_data[key_str] = score_data
                results_to_save.append({'day': day, 'data': encoded_data})
            data_to_save[league] = {
                'results': results_to_save,
                'fixtures_data': accum['fixtures_data'],
                'processed': accum['processed']
            }
        save_user_data(st.session_state.username, data_to_save)

def get_uploaded_days(league_name):
    results = st.session_state.league_accum[league_name]['results']
    days = [item['day'] for item in results if item.get('day') is not None]
    return sorted(days)

def add_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.processing_log.append(f"[{timestamp}] {message}")

def load_user_data_into_session(username):
    data = load_user_data(username)
    if data:
        for league, league_data in data.items():
            if league in st.session_state.league_accum:
                results = []
                for entry in league_data.get('results', []):
                    day = entry['day']
                    encoded_data = entry['data']
                    decoded_data = {}
                    for key_str, score_data in encoded_data.items():
                        home, away = decode_match_key(key_str)
                        decoded_data[(home, away)] = score_data
                    results.append({'day': day, 'data': decoded_data})
                st.session_state.league_accum[league]['results'] = results
                st.session_state.league_accum[league]['fixtures_data'] = league_data.get('fixtures_data', None)
                st.session_state.league_accum[league]['processed'] = league_data.get('processed', False)
        st.session_state.user_data_loaded = True
        return True
    return False


# ============================================================
# DASHBOARD AND PREDICTION FUNCTIONS
# ============================================================
def show_dashboard(league_name, results_data, master_teams):
    if not results_data:
        st.info("📊 Upload matchdays to see dashboard.")
        return
    all_matches = []
    team_goals = defaultdict(list)
    team_conceded = defaultdict(list)
    team_results = defaultdict(list)
    team_clean_sheets = defaultdict(int)
    team_btts = defaultdict(int)
    team_over25 = defaultdict(int)
    team_matches = defaultdict(int)

    for item in results_data:
        for (home, away), data in item['data'].items():
            ft_h, ft_a = data["ft"]
            all_matches.append((home, away, ft_h, ft_a))
            team_goals[home].append(ft_h)
            team_goals[away].append(ft_a)
            team_conceded[home].append(ft_a)
            team_conceded[away].append(ft_h)
            team_matches[home] += 1
            team_matches[away] += 1
            if ft_h > ft_a:
                team_results[home].append('W')
                team_results[away].append('L')
            elif ft_h == ft_a:
                team_results[home].append('D')
                team_results[away].append('D')
            else:
                team_results[home].append('L')
                team_results[away].append('W')
            if ft_a == 0:
                team_clean_sheets[home] += 1
            if ft_h == 0:
                team_clean_sheets[away] += 1
            if ft_h > 0 and ft_a > 0:
                team_btts[home] += 1
                team_btts[away] += 1
            if ft_h + ft_a >= 3:
                team_over25[home] += 1
                team_over25[away] += 1

    elo = ELO_Rating()
    for home, away, ft_h, ft_a in all_matches:
        elo.update_ratings(home, away, ft_h, ft_a)

    team_stats = {}
    for team in master_teams:
        if team not in team_matches or team_matches[team] == 0:
            continue
        m = team_matches[team]
        avg_scored = sum(team_goals[team]) / m if team_goals[team] else 0
        avg_conceded = sum(team_conceded[team]) / m if team_conceded[team] else 0
        wins = team_results[team].count('W') if team in team_results else 0
        draws = team_results[team].count('D') if team in team_results else 0
        losses = team_results[team].count('L') if team in team_results else 0
        form = ''.join(team_results[team][-3:][::-1]) if team in team_results else ''
        clean_sheets = team_clean_sheets.get(team, 0)
        btts = team_btts.get(team, 0)
        over25 = team_over25.get(team, 0)
        elo_rating = elo.ratings.get(team, 1500)
        team_stats[team] = {
            'matches': m,
            'avg_scored': avg_scored,
            'avg_conceded': avg_conceded,
            'wins': wins, 'draws': draws, 'losses': losses,
            'form': form,
            'clean_sheets': clean_sheets,
            'btts': btts,
            'over25': over25,
            'elo': elo_rating,
            'btts_pct': btts/m if m>0 else 0,
            'over25_pct': over25/m if m>0 else 0
        }

    strong = [t for t, s in team_stats.items() if s['elo'] > 1600]
    weak = [t for t, s in team_stats.items() if s['elo'] < 1400]
    over25_leaders = sorted(team_stats.items(), key=lambda x: x[1]['over25_pct'], reverse=True)[:5]
    btts_leaders = sorted(team_stats.items(), key=lambda x: x[1]['btts_pct'], reverse=True)[:5]

    st.markdown("---")
    st.subheader("📊 Live Team Dashboard")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🔥 Strong Teams (ELO > 1600)")
        if strong:
            st.write(", ".join(strong))
        else:
            st.caption("None yet")
        st.markdown("#### 🐌 Weak Teams (ELO < 1400)")
        if weak:
            st.write(", ".join(weak))
        else:
            st.caption("None yet")
    with col2:
        st.markdown("#### ⚽ Over 2.5 Leaders")
        for team, stats in over25_leaders:
            st.write(f"**{team}** {stats['over25_pct']*100:.1f}% ({stats['over25']}/{stats['matches']})")
        st.markdown("#### 🧤 BTTS Kings")
        for team, stats in btts_leaders:
            st.write(f"**{team}** {stats['btts_pct']*100:.1f}% ({stats['btts']}/{stats['matches']})")
    st.markdown("#### 📋 Team Form (Last 3)")
    form_df = pd.DataFrame([
        {'Team': team, 'Form': stats['form'], 'ELO': stats['elo'],
         'Avg Scored': f"{stats['avg_scored']:.2f}",
         'Avg Conceded': f"{stats['avg_conceded']:.2f}"}
        for team, stats in team_stats.items()
    ]).sort_values('ELO', ascending=False)
    st.dataframe(form_df, use_container_width=True)


def run_consensus_prediction_for_league(league_name, accum, master_teams, next_md):
    """Run consensus prediction for a single league and return enriched predictions."""
    stats = LeagueStats(league_name)
    elo = ELO_Rating()
    markov = MarkovChainPredictor()
    logistic = LogisticPredictor()
    high_conceding = HighConcedingDetector(window=3, threshold=5)

    # New advanced algorithms
    dixon = DixonColesPredictor()
    bayes = BayesianPredictor()
    form  = WeightedFormPredictor()
    new_poisson = PoissonPredictor()   # separate from 'stats'

    leaky_detector = LeakyDefenseDetector(threshold=3, window=1)
    form_trend = FormTrendDetector()
    correct_score = CorrectScorePredictor()

    for item in accum['results']:
        for (home, away), data in item['data'].items():
            ft_h, ft_a = data["ft"]
            ht_h, ht_a = data["ht"]
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
            high_conceding.add_match(home, away, ft_h, ft_a)
            leaky_detector.add_match(home, away, ft_h, ft_a)

            dixon.add_match(home, away, ft_h, ft_a)
            bayes.add_match(home, away, ft_h, ft_a)
            form.add_match(home, away, ft_h, ft_a)
            new_poisson.add_match(home, away, ft_h, ft_a)


            if ft_h > ft_a:
                form_trend.add_match(home, 'W', ft_h, ft_a)
                form_trend.add_match(away, 'L', ft_a, ft_h)
            elif ft_h == ft_a:
                form_trend.add_match(home, 'D', ft_h, ft_a)
                form_trend.add_match(away, 'D', ft_a, ft_h)
            else:
                form_trend.add_match(home, 'L', ft_h, ft_a)
                form_trend.add_match(away, 'W', ft_a, ft_h)

    strong_teams = [t for t in master_teams if elo.ratings.get(t, 1500) > 1600]
    high_conceding.set_strong_teams(strong_teams)

    voter = ConsensusVoter()
    voter.add_algorithm('poisson', stats)
    voter.add_algorithm('elo', elo)
    voter.add_algorithm('markov', markov)
    voter.add_algorithm('logistic', logistic)

    # New:
    voter.add_algorithm('dixon', dixon)
    voter.add_algorithm('bayesian', bayes)
    voter.add_algorithm('weighted_form', form)
    voter.add_algorithm('new_poisson', new_poisson)


    predictions = []
    for home, away in accum['fixtures_data']:
        consensus = voter.predict_match(home, away)
        agreement = consensus.get("agreement", 0)
        total_algos = consensus.get("algorithms_used", 0)
        agreement_str = f"{int(agreement * total_algos)}/{total_algos}"


        poisson_pred = stats.predict_match(home, away, patterns=None, simulations=10000)
        leaky = leaky_detector.analyze_match(home, away)
        home_trend = form_trend.get_trend(home)
        away_trend = form_trend.get_trend(away)
        home_form = form_trend.get_form_string(home)
        away_form = form_trend.get_form_string(away)
        scores = correct_score.predict(
            poisson_pred.get('home_lambda', 1.0),
            poisson_pred.get('away_lambda', 1.0),
            top_n=3
        )
        hc = high_conceding.check_match(home, away)
        warnings = []
        if hc['warning']:
            warnings.append(hc['warning'])
        if leaky.get('warning'):
            warnings.append(leaky['warning'])

        pred = {
            "match": (home, away),
            "home_win": consensus['home_win'],
            "draw": consensus['draw'],
            "away_win": consensus['away_win'],
            "most_likely": poisson_pred['most_likely'],
            "btts": poisson_pred['btts'],
            "over25": poisson_pred['over25'],
            "agreement": consensus['agreement'],
            "algorithms_used": consensus['algorithms_used'],
            "warnings": warnings,
            "home_trend": home_trend,
            "away_trend": away_trend,
            "home_form": home_form,
            "away_form": away_form,
            "correct_scores": scores,
            "leaky_warning": leaky.get('warning', None),
            "leaky_hint": leaky.get('prediction_hint', None),
            "over25_boost": leaky.get('over25_boost', 0),
            "btts_boost": leaky.get('btts_boost', 0),
            "both_leaky": leaky.get('both_leaky', False),
            "massacre": leaky.get('massacre_detected', False)
        }
        predictions.append(pred)

    enriched = generate_summary(predictions, league_name)
    for e, p in zip(enriched, predictions):
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
    return enriched


# ============================================================
# PAGE FUNCTIONS
# ============================================================
def show_home_dashboard():
    st.markdown("## 🏠 Home Dashboard")

    # ---- Auto-Runner Hero Card ----
    from utils.auto_runner import get_runner_status
    import time as _t
    status = get_runner_status()

    running = status["running"]
    color = "#00FF88" if running else "#FF4444"
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1e1e2e,#2a2a3e);
                border-radius:12px;padding:20px;border-left:6px solid {color};">
        <div style="font-size:1.4rem;font-weight:800;color:{color};">
            {'🟢 AUTO-RUNNER ACTIVE' if running else '🔴 AUTO-RUNNER STOPPED'}
        </div>
        <div style="color:#aaa;margin-top:8px;font-size:0.95rem;">
            <b>Phase:</b> {status['current_phase']} &nbsp;|&nbsp;
            <b>Season:</b> {status['last_season'] or '—'} &nbsp;|&nbsp;
            <b>Current MD:</b> {status['last_md'] or '—'}
        </div>
        <div style="color:#888;margin-top:4px;font-size:0.85rem;">
            Cycles: {status['cycles']} &nbsp;|&nbsp;
            Errors: {status['errors']} &nbsp;|&nbsp;
            Last sync: {_t.strftime('%H:%M:%S', _t.localtime(status['last_sync_ts'])) if status['last_sync_ts'] else '—'} &nbsp;|&nbsp;
            Last predict: {_t.strftime('%H:%M:%S', _t.localtime(status['last_predict_ts'])) if status['last_predict_ts'] else '—'}
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # ---- Dashboard Metrics ----
    total_matchdays = 0
    total_matches = 0
    for league in st.session_state.league_accum.values():
        total_matchdays += len(league['results'])
        for entry in league['results']:
            total_matches += len(entry['data'])

    # Load accuracy_data.json for prediction counts
    import json, os
    from utils.auto_bettor import select_best_three_o25  
    pred_count = 0
    latest_md = None
    top3 = []
    if os.path.exists("accuracy_data.json"):
        try:
            with open("accuracy_data.json") as f:
                data = json.load(f)
            mds = [k for k in data.keys() if k.isdigit() and data[k].get("predictions")]
            pred_count = sum(len(data[k]["predictions"]) for k in mds)
            if mds:
                latest_md = max(mds, key=int)
                all_preds = data[latest_md]["predictions"]

                # top3 = sorted(data[latest_md]["predictions"],
                 #             key=lambda x: x.get("over25_pct", 0),
                  #            reverse=True)[:3]

                top3 = select_best_three_o25(all_preds)
        except Exception as e:
            st.warning(f"Could not load predictions: {e}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📦 Matchdays Uploaded", total_matchdays)
    col2.metric("📊 Matches Processed", total_matches)
    col3.metric("🏆 Leagues Active", len(st.session_state.league_accum))
    col4.metric("🔮 Total Predictions", pred_count)

    # ---- Top 3 Over 2.5 Picks from Auto-Runner ----
    if top3:
        st.markdown("---")
        st.subheader(f"🎯 Top Over 2.5 Picks — MD {latest_md}")

        cols = st.columns(3)
        for i, p in enumerate(top3):
            with cols[i]:
                border = "#FFD700" if p["over25_pct"] >= 75 else "#00FF88" if p["over25_pct"] >= 65 else "#4FC3F7"
                st.markdown(f"""
                <div style="background:#1e1e2e;border-radius:10px;padding:14px;
                            border:2px solid {border};text-align:center;">
                    <div style="font-size:0.7rem;color:#888;text-transform:uppercase;letter-spacing:1px;">{p.get('league','')}</div>
                    <div style="font-size:1.05rem;font-weight:700;margin:6px 0;color:#fff;">{p['home']} vs {p['away']}</div>
                    <div style="font-size:2rem;font-weight:900;color:#FFD700;">{p['over25_pct']}%</div>
                    <div style="font-size:0.8rem;color:#aaa;">Over 2.5</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:6px;">
                        ⚽ Exp goals: <b style="color:#fff;">{p['expected_goals']}</b><br>
                        🧤 BTTS: <b style="color:#fff;">{p['btts_pct']}%</b><br>
                        🎯 {p['most_likely_score']} • {p['rating']}<br>
                        ⭐ Quality: <b style="color:#FFD700;">{p.get('_quality', 0):.1f}</b>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("⏳ Waiting for the first prediction cycle to complete...")

    st.info("EPUKA mihemko. EPUKA MIHEMKO")
    

    # ============================================================
    # 🎰 AUTO-BETTING PANEL — LIVE ONLY
    # ============================================================
    st.markdown("---")
    st.subheader("🎰 Auto-Betting (LIVE)")

    from utils.auto_bettor import (
        load_config, save_credentials, get_stored_phone, save_settings,
        scan_for_qualified_bets, get_daily_bet_count, load_bets_log,
        save_last_balance, get_last_balance, BetPawaClient,
    )
    from utils.live_bet_bot import start_bot, stop_bot, is_running, get_bot_state

    cfg = load_config()
    bot_state = get_bot_state()

    # ---------- ACCOUNT STATUS ----------
    st.markdown("### 🔐 BetPawa Account")
    stored_phone = cfg.get("phone", "")
    last_bal, last_bal_ts = get_last_balance()

    if stored_phone:
        s1, s2, s3, s4 = st.columns([2, 2, 3, 1])
        s1.metric("📱 Phone", stored_phone)
        s2.metric("💰 Balance", f"{last_bal:.2f} TZS" if last_bal else "—")
        s3.caption(f"Last checked: {last_bal_ts[:19]}" if last_bal_ts else "Never checked")
        with s4:
            if st.button("🔄", key="refresh_bal", help="Refresh balance"):
                st.session_state["show_pw_prompt"] = True

        if st.session_state.get("show_pw_prompt"):
            with st.form("refresh_bal_form"):
                pw = st.text_input("Password to refresh balance", type="password")
                col_a, col_b = st.columns(2)
                ok = col_a.form_submit_button("Refresh", type="primary")
                cancel = col_b.form_submit_button("Cancel")
                if cancel:
                    st.session_state["show_pw_prompt"] = False
                    st.rerun()
                if ok and pw:
                    c = BetPawaClient()
                    if c.login(stored_phone, pw):
                        b = c.get_balance()
                        if b is not None:
                            save_last_balance(b)
                            st.session_state["show_pw_prompt"] = False
                            st.success(f"✅ {b:.2f} TZS")
                            st.rerun()
                        else:
                            st.warning("Could not fetch balance")
                    else:
                        st.error("❌ Login failed")
    else:
        st.info("No credentials saved yet.")

    st.markdown("---")

    # ---------- CREDENTIALS ----------
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🔐 Update Credentials")
        with st.form("bp_creds"):
            phone_input = st.text_input("Phone number",
                                        value=get_stored_phone(),
                                        placeholder="e.g. 712345678")
            password_input = st.text_input("Password",
                                           type="password",
                                           placeholder="BetPawa password")
            submit = st.form_submit_button("💾 Save & Login")

            if submit:
                if not phone_input or not password_input:
                    st.error("Both fields required.")
                else:
                    save_credentials(phone_input, password_input)
                    client = BetPawaClient()
                    if client.login(phone_input, password_input):
                        bal = client.get_balance()
                        if bal is not None:
                            save_last_balance(bal)
                        st.success(f"✅ Saved — Login OK")
                    else:
                        st.error("❌ Login failed")
                    time.sleep(1)
                    st.rerun()

    with col2:
        st.markdown("#### ⚙️ Settings")
        max_stake = st.number_input("Max stake per bet (TZS)",
                                    min_value=1, max_value=100000,
                                    value=int(cfg["max_stake_tzs"]), step=100)
        daily_limit = st.number_input("Daily bet limit",
                                      min_value=1, max_value=60,
                                      value=int(cfg["daily_limit"]))
        min_o25 = st.slider("Min Over 2.5 %", 50, 100, int(cfg["min_over25_pct"]))
        min_xg = st.slider("Min Expected Goals", 1.0, 10.0,
                           float(cfg["min_expected_goals"]), 0.1)
        min_btts = st.slider("Min BTTS %", 50, 100, int(cfg["min_btts_pct"]))
        min_score = st.slider("Min 🎯 score total", 1, 10, int(cfg["min_score_total"]))
        headless = st.checkbox("Run browser in background (headless)", value=cfg.get("headless", False))

        if st.button("💾 Save Settings", type="primary"):
            save_settings(
                max_stake_tzs=max_stake,
                daily_limit=daily_limit,
                min_over25_pct=float(min_o25),
                min_expected_goals=float(min_xg),
                min_btts_pct=float(min_btts),
                min_score_total=int(min_score),
                headless=headless,
            )
            st.success("✅ Settings saved")

    # ---------- LIVE TOGGLE ----------
    st.markdown("---")
    st.markdown("### 🎯 Live Mode")

    if not is_running():
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.info("🔴 Live mode is **OFF** — no bets will be placed")
        with col_b:
            if st.button("▶️ Turn ON", type="primary", use_container_width=True):
                if not cfg.get("phone"):
                    st.error("Save credentials first")
                else:
                    st.session_state["show_live_pw"] = True
    else:
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.success(f"🟢 **LIVE MODE ON** — phase: {bot_state['phase']}")
            st.caption(f"Bets today: {bot_state['bets_placed_today']}/{cfg['daily_limit']} | "
                       f"Session alive: {'✅' if bot_state['session_alive'] else '❌'}")
        with col_b:
            if st.button("⏹️ Turn OFF", type="secondary", use_container_width=True):
                stop_bot()
                st.toast("Stop signal sent...", icon="⏹️")
                time.sleep(2)
                st.rerun()

    # Password prompt (only shown when turning ON)
    if st.session_state.get("show_live_pw"):
        with st.form("live_pw_form"):
            st.warning("⚠️ Enter password. The bot will run until you switch it off.")
            live_pw = st.text_input("BetPawa Password", type="password")
            col_a, col_b = st.columns(2)
            ok = col_a.form_submit_button("🚀 Start Live Bot", type="primary")
            cancel = col_b.form_submit_button("Cancel")

            if cancel:
                st.session_state["show_live_pw"] = False
                st.rerun()

            if ok and live_pw:
                started = start_bot(
                    phone=cfg.get("phone"),
                    password=live_pw,
                    headless=cfg.get("headless", False),
                )
                st.session_state["show_live_pw"] = False
                if started:
                    st.success("✅ Bot started — see console for activity")
                else:
                    st.warning("Bot was already running")
                time.sleep(1)
                st.rerun()

    # ---------- QUALIFIED BETS ----------
    st.markdown("---")
    st.markdown("#### 🎯 Predictions Meeting All Conditions")
    qualified = scan_for_qualified_bets()
    if qualified:
        st.success(f"✅ {len(qualified)} match(es) qualify")
        preview = []
        for item in qualified:
            p = item["prediction"]
            preview.append({
                "MD": item["matchday"],
                "League": p.get("league"),
                "Match": f"{p['home']} vs {p['away']}",
                "Over 2.5 %": p["over25_pct"],
                "Exp Goals": p["expected_goals"],
                "BTTS %": p["btts_pct"],
                "Score": p["most_likely_score"],
                "Rating": p.get("rating"),
            })
        st.dataframe(preview, use_container_width=True)
    else:
        st.info("No qualifying matches right now.")

    # ---------- BETS LOG ----------
    with st.expander("📜 Recent Bets Log", expanded=False):
        log = load_bets_log()
        if log:
            st.dataframe(log[-20:], use_container_width=True)
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Today", f"{get_daily_bet_count()}/{cfg['daily_limit']}")
            with c2:
                if st.button("🗑️ Clear Log"):
                    from utils.auto_bettor import save_bets_log
                    save_bets_log([])
                    st.rerun()
        else:
            st.caption("No bets logged yet.")

    # Auto-refresh while bot is running
    if is_running():
        time.sleep(3)
        st.rerun()

    if st.button("💾 Auto‑Save Data", type="secondary"):
        auto_save_user_data()
        st.toast("✅ Data saved!", icon="💾")



def show_batch_upload():
    st.markdown("## 📦 Batch Upload")
    league_names = list(LEAGUE_TEAMS.keys())

    # ---------- BATCH RESULTS ----------
    st.markdown("---")
    st.markdown("### 📥 Batch Results (All Leagues)")
    with st.expander("📋 Click to paste all leagues at once", expanded=False):
        st.caption("Paste a block containing multiple leagues. Format:")
        st.code("""English League
AST - BHA
(0 - 1)0 - 2
...
Spanish League
ALA - ATM
(0 - 0)0 - 1
...""", language="text")
        batch_text = st.text_area("Paste all leagues' matches here:", height=300, key="batch_results_input",
                                  placeholder="English League\nAST - BHA\n(0 - 1)0 - 2\n...")
        batch_md = st.number_input("Matchday number for this batch:", min_value=1, max_value=34,
                                   value=st.session_state.batch_matchday, step=1, key="batch_md_number")
        if st.button("🚀 Batch Add All Leagues", type="primary", use_container_width=True):
            if not batch_text.strip():
                st.error("Please paste the batch text first.")
            else:
                with st.spinner("Processing batch..."):
                    parsed_batch = parse_batch(batch_text, league_names, LEAGUE_TEAMS)
                    if not parsed_batch:
                        st.error("Could not parse any matches. Check format and league headers.")
                    else:
                        added_count = 0
                        for league, matches in parsed_batch.items():
                            if league in st.session_state.league_accum:
                                accum = st.session_state.league_accum[league]
                                accum['results'] = [item for item in accum['results'] if item['day'] != batch_md]
                                data = {}
                                for m in matches:
                                    data[(m['home'], m['away'])] = {
                                        'ft': (m['ft_h'], m['ft_a']),
                                        'ht': (m['ht_h'], m['ht_a'])
                                    }
                                accum['results'].append({'day': batch_md, 'data': data})
                                added_count += len(matches)
                                add_log(f"Batch: Added MD{batch_md} to {league} ({len(matches)} matches)")
                            else:
                                st.warning(f"League '{league}' not recognized. Skipping.")
                        if added_count > 0:
                            if st.session_state.batch_matchday < 34:
                                st.session_state.batch_matchday += 1
                            st.balloons()
                            st.success(f"✅ Batch uploaded successfully! Added {added_count} matches. Next matchday is {st.session_state.batch_matchday}.")
                            auto_save_user_data()
                            st.rerun()
                        else:
                            st.warning("No matches were added. Check league names and match format.")

    # ---------- BATCH FIXTURES ----------
    st.markdown("---")
    st.markdown("### 📥 Batch Fixtures (All Leagues)")
    if 'cleaning_pending' not in st.session_state:
        st.session_state.cleaning_pending = False
    if 'cleaned_fixtures_text' not in st.session_state:
        st.session_state.cleaned_fixtures_text = ""
    if st.session_state.cleaning_pending:
        if st.session_state.cleaned_fixtures_text:
            st.session_state.batch_fixtures_input_global = st.session_state.cleaned_fixtures_text
        st.session_state.cleaning_pending = False

    with st.expander("📋 Click to paste all leagues' fixtures at once", expanded=False):
        st.caption("Paste a block containing multiple leagues with their fixtures. Format:")
        st.code("""English League
ARS - MCI
BHA - WHU
...
Spanish League
BAR - RMA
...
""", language="text")
        batch_fixtures_text = st.text_area("Paste all leagues' fixtures here:", height=200,
                                           key="batch_fixtures_input_global",
                                           placeholder="English League\nARS - MCI (2-0)\nBHA - WHU (1-1)\n...")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🧹 Clean Fixtures (Remove Scores)", type="secondary", use_container_width=True):
                current = st.session_state.get("batch_fixtures_input_global", "")
                if current.strip():
                    cleaned = clean_fixtures_from_text(current)
                    st.session_state.cleaned_fixtures_text = cleaned
                    st.session_state.cleaning_pending = True
                    st.toast("✅ Scores removed! Click 'Parse Fixtures' to store.", icon="🧹")
                    st.rerun()
                else:
                    st.warning("Please paste fixtures first.")
        with col2:
            if st.button("📝 Parse Fixtures", type="primary", use_container_width=True):
                text_to_parse = st.session_state.get("batch_fixtures_input_global", "")
                if not text_to_parse.strip():
                    st.error("Please paste the fixtures text first.")
                else:
                    with st.spinner("Parsing fixtures..."):
                        parsed_fixtures = parse_batch_fixtures(text_to_parse, league_names, LEAGUE_TEAMS)
                        if not parsed_fixtures:
                            st.error("Could not parse any fixtures. Check format and league headers.")
                            st.text("Text used for parsing (first 500 chars):")
                            st.code(text_to_parse[:500])
                        else:
                            added_count = 0
                            st.subheader("📋 Parsed Fixtures Preview")
                            for league, fixtures in parsed_fixtures.items():
                                if league in st.session_state.league_accum:
                                    st.session_state.league_accum[league]['fixtures_data'] = fixtures
                                    added_count += len(fixtures)
                                    add_log(f"Batch: Added {len(fixtures)} fixtures to {league}")
                                    fixture_str = " | ".join([f"{h} vs {a}" for h, a in fixtures])
                                    st.markdown(f"**{league}** ({len(fixtures)} fixtures):")
                                    st.code(fixture_str)
                                else:
                                    st.warning(f"League '{league}' not recognized. Skipping.")
                            if added_count > 0:
                                st.balloons()
                                st.success(f"✅ Batch fixtures uploaded successfully! Added {added_count} fixtures across {len(parsed_fixtures)} leagues.")
                                with st.expander("📊 View as Table"):
                                    rows = []
                                    for league, fixtures in parsed_fixtures.items():
                                        for home, away in fixtures:
                                            rows.append({"League": league, "Home": home, "Away": away})
                                    if rows:
                                        st.dataframe(pd.DataFrame(rows), use_container_width=True)
                                st.rerun()
                            else:
                                st.warning("No fixtures were added. Check league names and fixture format.")


def show_league_analysis():
    st.markdown("## ⚽ League Analysis")
    league_names = list(LEAGUE_TEAMS.keys())
    tabs = st.tabs([f"⚽ {name.split()[0]}" for name in league_names])
    for idx, league_name in enumerate(league_names):
        with tabs[idx]:
            master_teams = LEAGUE_TEAMS[league_name]
            accum = st.session_state.league_accum[league_name]
            uploaded_days = get_uploaded_days(league_name)
            fixtures_ready = accum['fixtures_data'] is not None

            show_dashboard(league_name, accum['results'], master_teams)

            next_md = max(uploaded_days)+1 if uploaded_days else 16
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📦 Matchdays", len(uploaded_days), delta=f"{len(uploaded_days)}/34")
            with col2:
                st.metric("📊 Matches", sum([len(item['data']) for item in accum['results']]))
            with col3:
                st.metric("📅 Next", f"MD{next_md}" if next_md <= 34 else "✅ Done")
            with col4:
                st.metric("⚡ Status", "✅ Active" if accum['processed'] else "⏳ Pending")
            st.markdown("---")

            if uploaded_days:
                st.info(f"📦 **Already uploaded:** {', '.join(map(str, uploaded_days))}")
                progress = len(uploaded_days) / 34
                st.progress(min(progress, 1.0), text=f"{len(uploaded_days)}/34 matchdays")
                if len(uploaded_days) >= 15 and len(uploaded_days) < 34:
                    st.success(f"🎯 {len(uploaded_days)} matchdays! Ready to predict MD{max(uploaded_days)+1}")
                elif len(uploaded_days) >= 34:
                    st.success("🎉 All 34 matchdays uploaded! All predictions complete.")
                else:
                    days_needed = 15 - len(uploaded_days)
                    if days_needed > 0:
                        st.warning(f"📊 Need {days_needed} more matchdays to start (need 15+)")
                if st.button(f"🗑️ Clear All", key=f"clear_{idx}"):
                    st.session_state.league_accum[league_name]['results'] = []
                    st.session_state.league_accum[league_name]['processed'] = False
                    st.rerun()
            else:
                st.warning("🚨 No matchday results uploaded yet. Start by pasting Matchday 1 below!")
            st.markdown("---")

            # Fixtures
            st.markdown(f"### 📅 Matchday {next_md if next_md <= 34 else 34} Fixtures")
            clean_key = f"clean_pending_{idx}"
            text_key = f"cleaned_text_{idx}"
            if clean_key not in st.session_state:
                st.session_state[clean_key] = False
            if text_key not in st.session_state:
                st.session_state[text_key] = ""
            if st.session_state[clean_key]:
                if st.session_state[text_key]:
                    st.session_state[f"fix_text_{idx}"] = st.session_state[text_key]
                st.session_state[clean_key] = False

            col_fix1, col_fix2 = st.columns([4, 1])
            with col_fix1:
                fixtures_text = st.text_area(f"Paste MD{next_md if next_md <= 34 else 34} fixtures",
                                             height=80, key=f"fix_text_{idx}",
                                             placeholder="BHA - BRE\nBOU - MUN\n...",
                                             label_visibility="collapsed")
            with col_fix2:
                st.write("")
                if st.button(f"🧹 Clean", key=f"clean_fix_{idx}", help="Remove scores and brackets"):
                    current = st.session_state.get(f"fix_text_{idx}", "")
                    if current.strip():
                        cleaned = clean_fixtures_from_text(current)
                        st.session_state[text_key] = cleaned
                        st.session_state[clean_key] = True
                        st.toast("✅ Cleaned!", icon="🧹")
                        st.rerun()
                    else:
                        st.warning("Paste fixtures first.")
            if st.button(f"📝 Parse MD{next_md if next_md <= 34 else 34} Fixtures", key=f"fix_parse_{idx}", use_container_width=True):
                text_to_parse = st.session_state.get(f"fix_text_{idx}", "")
                if text_to_parse.strip():
                    fixtures_data = parse_fixtures(text_to_parse, master_teams)
                    if fixtures_data:
                        st.session_state.league_accum[league_name]['fixtures_data'] = fixtures_data
                        st.success(f"✅ Found {len(fixtures_data)} fixtures!")
                        st.code(" | ".join([f"{h} vs {a}" for h,a in fixtures_data]))
                        add_log(f"{league_name}: fixtures parsed")
                    else:
                        st.error("No fixtures found.")
                else:
                    st.warning("Please paste fixtures first.")
            st.markdown("---")

            # Results Upload
            st.markdown("### 📊 Upload Matchday Results")
            st.caption("Paste results in this format (team line, then score line):")
            st.code("BHA - BRE\n(0 - 0)1 - 1\nBOU - MUN\n(0 - 3)0 - 3", language="text")
            col_md, col_btn = st.columns([3, 1])
            with col_md:
                selected_md = st.selectbox("Select Matchday", list(range(1, 35)), key=f"md_select_{idx}", index=0)
                if selected_md in uploaded_days:
                    st.info(f"⚠️ MD {selected_md} already uploaded (will replace)")
            with col_btn:
                st.write("")
                st.write("")
                if st.button("📋 Quick Example", key=f"quick_{idx}"):
                    example = """BHA - BRE\n(0 - 0)1 - 1\nBOU - MUN\n(0 - 3)0 - 3\nCHE - MCI\n(0 - 1)0 - 3\nCRY - ARS\n(0 - 1)1 - 3\nEVE - AST\n(1 - 0)1 - 0\nLEE - WOL\n(1 - 0)2 - 1\nNEW - SUN\n(2 - 0)3 - 1\nNOT - BUR\n(0 - 2)2 - 6\nTOT - FUL\n(1 - 1)3 - 1\nWHU - LIV\n(1 - 0)1 - 2"""
                    st.session_state[f"match_text_{idx}"] = example
                    st.rerun()
            text_key_match = f"match_text_{idx}"
            if text_key_match not in st.session_state:
                st.session_state[text_key_match] = ""
            match_text = st.text_area(f"Paste MD {selected_md} results:", value=st.session_state[text_key_match],
                                      height=250, key=text_key_match,
                                      placeholder="BHA - BRE\n(0 - 0)1 - 1\n...")
            col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
            with col_btn2:
                if st.button(f"🚀 ADD MATCHDAY {selected_md}", key=f"add_{idx}", type="primary", use_container_width=True):
                    if not match_text.strip():
                        st.error("Please paste match results first.")
                    else:
                        with st.spinner(f"Parsing MD {selected_md}..."):
                            parsed = parse_results(match_text, master_teams)
                            if parsed:
                                accum['results'] = [item for item in accum['results'] if item['day'] != selected_md]
                                accum['results'].append({'day': selected_md, 'data': parsed})
                                st.balloons()
                                st.toast(f"✅ MD {selected_md} added!", icon="✅")
                                st.success(f"✅ MD {selected_md} added! Found {len(parsed)} matches.")
                                add_log(f"{league_name}: MD {selected_md} added ({len(parsed)})")
                                st.rerun()
                            else:
                                st.error("Could not parse. Check format.")
            st.markdown("---")

            # Pattern Detection
            if len(uploaded_days) >= 3:
                with st.expander("🧠 Advanced Pattern Detection Report", expanded=False):
                    from utils.advanced_pattern_detector import AdvancedPatternDetector, detect_math_patterns
                    detector = AdvancedPatternDetector(accum['results'])
                    st.markdown(detector.get_pattern_summary())
                    math_patterns = detect_math_patterns(accum['results'])
                    if math_patterns:
                        st.markdown("### 📐 Mathematical Pattern Detection")
                        for p in math_patterns:
                            st.info(f"🔢 {p['details']}")
                    formulas = detector.get_formulas(min_confidence=0.5, max_count=10)
                    if formulas:
                        with st.expander("🧮 Top Actionable Formulas", expanded=True):
                            for i, f in enumerate(formulas, 1):
                                st.success(f"{i}. {f['formula']} (Confidence: {f['confidence']*100:.0f}%)")

            # Consensus Prediction
            st.markdown("### 🚀 Run Consensus Prediction")
            num_days = len(uploaded_days)
            next_md = max(uploaded_days)+1 if uploaded_days else 16
            status_col1, status_col2, status_col3 = st.columns(3)
            with status_col1:
                if num_days >= 15:
                    st.success(f"✅ {num_days} matchdays → Ready for MD{next_md}")
                else:
                    st.warning(f"⚠️ {num_days}/15 needed")
            with status_col2:
                if fixtures_ready:
                    st.success(f"✅ MD{next_md} fixtures ready")
                else:
                    st.error(f"❌ MD{next_md} fixtures missing")
            with status_col3:
                if num_days >= 15 and fixtures_ready:
                    st.success("🎯 Predict now")
                else:
                    st.warning("⏳ Waiting")

            if st.button(f"⚡ CONSENSUS PREDICT MD{next_md}", key=f"proc_{idx}", type="primary", use_container_width=True):
                if num_days < 15:
                    st.warning(f"Need 15 matchdays, have {num_days}.")
                elif not fixtures_ready:
                    st.warning("Please upload fixtures first.")
                else:
                    with st.spinner(f"🧠 Running 4 algorithms + Consensus + Leaky Detection..."):
                        enriched = run_consensus_prediction_for_league(league_name, accum, master_teams, next_md)
                        st.session_state.current_predictions = enriched
                        st.session_state.current_matchday = next_md

                        session_id = st.session_state.session_manager.save_session(
                            st.session_state.league_accum,
                            enriched,
                            league_names,
                            matchday=next_md
                        )
                        st.success(f"💾 Session {session_id} saved automatically!")

                        for p in enriched:
                            if p.get('Warning'):
                                st.markdown(f'<div class="warning-box">⚠️ {p["Warning"]}</div>', unsafe_allow_html=True)

                        st.subheader(f"📊 MD{next_md} Predictions - Consensus Table")
                        df = pd.DataFrame(enriched)

                        def color_rating(val):
                            if "Elite" in str(val):
                                return 'background-color: #FFD700; color: #000; font-weight: bold'
                            elif "High" in str(val):
                                return 'background-color: #00FF88; color: #000; font-weight: bold'
                            elif "Medium" in str(val):
                                return 'background-color: #4FC3F7; color: #000; font-weight: bold'
                            elif "Risky" in str(val):
                                return 'background-color: #FFA726; color: #000; font-weight: bold'
                            else:
                                return 'background-color: #555; color: #fff'

                        def color_confidence(val):
                            try:
                                if isinstance(val, str) and '%' in val:
                                    num = float(val.replace('%', ''))
                                    if num >= 72:
                                        return 'color: #FFD700; font-weight: bold'
                                    elif num >= 62:
                                        return 'color: #00FF88; font-weight: bold'
                                    elif num >= 55:
                                        return 'color: #4FC3F7'
                                    elif num >= 48:
                                        return 'color: #FFA726'
                                    else:
                                        return 'color: #888'
                            except:
                                pass
                            return ''

                        styled_df = df.style.map(color_rating, subset=['Rating'])
                        styled_df = styled_df.map(color_confidence, subset=['Confidence'])
                        st.dataframe(styled_df, use_container_width=True, height=500)

                        st.subheader("📈 Statistical Summary")
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            avg_home = df['Home Win'].str.replace('%', '').astype(float).mean()
                            st.metric("Avg Home Win %", f"{avg_home:.1f}%")
                        with col2:
                            avg_away = df['Away Win'].str.replace('%', '').astype(float).mean()
                            st.metric("Avg Away Win %", f"{avg_away:.1f}%")
                        with col3:
                            avg_draw = df['Draw'].str.replace('%', '').astype(float).mean()
                            st.metric("Avg Draw %", f"{avg_draw:.1f}%")
                        with col4:
                            avg_btts = df['BTTS'].str.replace('%', '').astype(float).mean()
                            st.metric("Avg BTTS %", f"{avg_btts:.1f}%")

                        csv = df.to_csv(index=False)
                        st.download_button("📥 Download CSV", data=csv, file_name=f"{league_name}_MD{next_md}_consensus.csv")

                        st.info(f"📊 **Next Step:** Add MD{next_md} results when available, then predict MD{next_md+1}!")



def show_event_listener():
    st.markdown("## 🎧 Event Listener — 24/7 Change-Driven")
    st.caption("Polls every 5 seconds. Runs the pipeline only when a change is detected.")

    stats = get_listener_stats()

    # Status metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", "🟢 Running" if stats["running"] else "🔴 Stopped")
    c2.metric("Polls", stats["polls"])
    c3.metric("Changes Detected", stats["changes"])
    c4.metric("Errors", stats["errors"])

    # Last poll / last pipeline run
    import time as _t
    last_poll = stats.get("last_poll_ts", 0)
    last_run = stats.get("last_run", 0)
    c1, c2 = st.columns(2)
    c1.metric("Last Poll",
              _t.strftime("%H:%M:%S", _t.localtime(last_poll)) if last_poll else "—")
    c2.metric("Last Pipeline Run",
              _t.strftime("%H:%M:%S", _t.localtime(last_run)) if last_run else "—")

    # Entities currently processing
    if stats["entities_running"]:
        st.info(f"⚙️ Currently processing: {', '.join(stats['entities_running'])}")
    else:
        st.success("💤 Idle — no entities running")

    # Progress file viewer
    with st.expander("📄 Listener Progress (JSON)", expanded=False):
        import json, os
        if os.path.exists("listener_progress.json"):
            with open("listener_progress.json") as f:
                prog = json.load(f)
            st.json(prog)
        else:
            st.info("No progress file yet — listener hasn't run.")

    # Controls
    from utils.event_listener import stop_listener, start_listener
    c1, c2 = st.columns(2)
    with c1:
        if st.button("⏹️ Stop Listener", use_container_width=True):
            stop_listener()
            st.warning("Stop signal sent — thread will exit on next poll.")
    with c2:
        if st.button("▶️ Restart Listener", type="primary", use_container_width=True):
            stop_listener()
            import time as _t2; _t2.sleep(1)
            start_listener()
            st.success("Listener restarted.")
            st.rerun()

    # Continuous auto-refresh to keep the dashboard fresh
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=5000, key="listener_refresh")

    # Show latest predictions (reads from accuracy_data.json)
    st.markdown("---")
    st.subheader("🔮 Latest Predictions")
    import json, os
    if os.path.exists("accuracy_data.json"):
        try:
            with open("accuracy_data.json") as f:
                data = json.load(f)
            mds = [k for k in data.keys() if k.isdigit() and data[k].get("predictions")]
            if mds:
                latest = max(mds, key=int)
                preds = data[latest]["predictions"]
                st.caption(f"Matchday **{latest}** — {len(preds)} predictions (sorted by Over 2.5)")
                import pandas as pd
                df = pd.DataFrame(preds)
                if not df.empty:
                    st.dataframe(df, use_container_width=True, hide_index=True, height=400)

                    st.markdown("#### 🎯 Top 5 Over 2.5")
                    for i, p in enumerate(preds[:5], 1):
                        st.write(
                            f"**{i}.** {p['home']} vs {p['away']} — "
                            f"**{p['over25_pct']}%** | "
                            f"BTTS {p['btts_pct']}% | "
                            f"Exp {p['expected_goals']} | "
                            f"{p['most_likely_score']} | {p['rating']}"
                        )
            else:
                st.info("No predictions yet — waiting for a change event.")
        except Exception as e:
            st.warning(f"Could not load: {e}")





def show_predictions():
    st.markdown("## 🔮 Predictions")
    if st.button("🔮 FIND TOP 3 BEST BETS", type="primary", use_container_width=True):
        all_predictions = []
        leagues_processed = 0
        league_names = list(LEAGUE_TEAMS.keys())
        with st.spinner("Running consensus predictions for all leagues..."):
            progress_bar = st.progress(0)
            total_leagues = len(league_names)
            for idx, league_name in enumerate(league_names):
                accum = st.session_state.league_accum[league_name]
                uploaded_days = get_uploaded_days(league_name)
                fixtures_ready = accum['fixtures_data'] is not None
                num_days = len(uploaded_days)
                if num_days >= 15 and fixtures_ready:
                    master_teams = LEAGUE_TEAMS[league_name]
                    next_md = max(uploaded_days) + 1 if uploaded_days else 16
                    try:
                        enriched = run_consensus_prediction_for_league(
                            league_name, accum, master_teams, next_md
                        )
                        all_predictions.extend(enriched)
                        add_log(f"Global: Processed {league_name} ({len(enriched)} predictions)")
                        leagues_processed += 1
                    except Exception as e:
                        st.warning(f"⚠️ Could not process {league_name}: {e}")
                progress_bar.progress((idx + 1) / total_leagues)
        if not all_predictions:
            st.warning("No predictions could be generated. Make sure you have at least 15 matchdays and fixtures for each league.")
        else:
            st.session_state.current_predictions = all_predictions
            st.session_state.current_matchday = max([p.get('current_md', 26) for p in all_predictions], default=26)
            st.success(f"✅ Processed {leagues_processed} leagues with {len(all_predictions)} total predictions!")

    col_clear1, col_clear2 = st.columns([5, 1])
    with col_clear2:
        if st.button("🗑️ Clear Picks", type="secondary", help="Clear the current global top picks display"):
            st.session_state.current_predictions = []
            st.session_state.current_matchday = None
            st.toast("🗑️ Global picks cleared!", icon="🗑️")
            st.rerun()

    current = st.session_state.get('current_predictions', [])
    if not current:
        st.info("📊 Click 'FIND TOP 3 BEST BETS' to run predictions across all leagues.")
    else:
        total = len(current)
        elite_count = sum(1 for p in current if "Elite" in p.get("Rating", ""))
        high_count = sum(1 for p in current if "High" in p.get("Rating", ""))
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📊 Total Predictions", total)
        with col2:
            st.metric("🥇 Elite Picks", elite_count)
        with col3:
            st.metric("🥈 High Picks", high_count)

        sorted_picks = sorted(current, key=lambda x: x["Confidence"], reverse=True)
        st.subheader("🔥 TOP 3 HIGH-CONFIDENCE SELECTIONS (All Leagues)")
        cols = st.columns(3)
        for i in range(min(3, len(sorted_picks))):
            pick = sorted_picks[i]
            with cols[i]:
                rating = pick['Rating']
                rating_class = "elite" if "Elite" in rating else "high" if "High" in rating else "medium" if "Medium" in rating else "risky" if "Risky" in rating else "skip"
                st.markdown(f"""
                <div class="metric-card">
                    <h3>{pick['League']}</h3>
                    <h2>{pick['Match']}</h2>
                    <h1 style="color: #FFD700;">{pick['Top Pick']}</h1>
                    <h3>{pick['Confidence']*100:.1f}% Confidence</h3>
                    <p>Most Likely: {pick['Most Likely']}</p>
                    <p class="{rating_class}">⭐ {rating}</p>
                    <p>Agreement: {pick.get('Agreement', 'N/A')}</p>
                </div>
                """, unsafe_allow_html=True)

        st.subheader("📊 All High-Confidence Picks (Sorted by Probability)")
        filtered = [p for p in sorted_picks if p["Confidence"] > 0.5]
        if filtered:
            display_data = []
            for idx, p in enumerate(filtered, 1):
                display_data.append({
                    "Rank": idx,
                    "League": p['League'],
                    "Match": p['Match'],
                    "Top Pick": p['Top Pick'],
                    "Confidence": f"{p['Confidence']*100:.1f}%",
                    "Most Likely": p['Most Likely'],
                    "Rating": p['Rating'],
                    "Agreement": p.get('Agreement', 'N/A'),

                })
            display_df = pd.DataFrame(display_data)
            st.dataframe(display_df, use_container_width=True, height=500)
            st.subheader("📋 Quick Summary – Top 8 Picks")
            summary_df = display_df.head(8)[['Rank', 'League', 'Match', 'Top Pick', 'Confidence', 'Rating']]
            st.dataframe(summary_df, use_container_width=True)

            st.subheader("⚽ Best Over 2.5 Picks")
            over25_filtered = sorted(
                [p for p in current if p.get('O/U 2.5', '0%').replace('%', '').replace('+', '').strip() and float(p.get('O/U 2.5', '0%').replace('%', '')) > 50],
                key=lambda x: float(x.get('O/U 2.5', '0%').replace('%', '')),
                reverse=True
            )[:5]
            if over25_filtered:
                over25_data = []
                for idx, p in enumerate(over25_filtered, 1):
                    over25_data.append({
                        "Rank": idx,
                        "League": p['League'],
                        "Match": p['Match'],
                        "O/U 2.5": p.get('O/U 2.5', 'N/A'),
                        "Boost": p.get('O2.5 Boost', 'N/A'),
                        "Most Likely": p['Most Likely'],
                        "Rating": p['Rating']
                    })
                st.dataframe(pd.DataFrame(over25_data), use_container_width=True)
            else:
                st.caption("No strong Over 2.5 picks (>50%) available.")
        else:
            st.warning("No picks with confidence > 50%.")


def show_betpawa_sync():
    st.markdown("## 🔄 Sync BetPawa Data")
    st.caption("Auto-fetch results and fixtures from BetPawa and store them in accuracy_data.json")

    from utils.betpawa_sync import get_active_seasons, get_events_for_round
    import json, os

    data_path = "accuracy_data.json"

    # Load existing data
    if os.path.exists(data_path):
        try:
            with open(data_path) as f:
                data = json.load(f)
        except Exception:
            data = {}
    else:
        data = {}

    stored_mds = sorted([k for k in data.keys() if k.isdigit()], key=int)

    # ---------- ACTIVE SEASONS ----------
    st.subheader("📊 Active Seasons")
    try:
        seasons = get_active_seasons()
        seasons_sorted = sorted(seasons, key=lambda s: s["season_id"])
    except Exception as e:
        st.error(f"❌ Could not fetch seasons from BetPawa: {e}")
        return

    if not seasons_sorted:
        st.warning("No active seasons available.")
        return

    current_season = seasons_sorted[-2] if len(seasons_sorted) >= 2 else seasons_sorted[-1]
    next_season = seasons_sorted[-1]

    season_df = pd.DataFrame([
        {
            "Season ID": s["season_id"],
            "Rounds": len(s["rounds"]),
            "Role": "🟢 Current (results)" if s["season_id"] == current_season["season_id"]
                    else "🔵 Next (fixtures)" if s["season_id"] == next_season["season_id"]
                    else "⚪ Past"
        }
        for s in seasons_sorted
    ])
    st.dataframe(season_df, use_container_width=True, hide_index=True)

    # ---------- ACTION BUTTONS ----------
    st.markdown("---")
    st.subheader("⚡ Auto‑Sync Actions")
    st.caption("Automatically detects the latest active season and fetches all its rounds in parallel.")

    if st.button("🔄 Auto‑Sync Latest Season", type="primary", use_container_width=True):
        from utils.betpawa_sync import sync_latest_season
        with st.spinner("Detecting latest season and fetching all rounds in parallel..."):
            season_id, results_count, fx_md, fx_count = sync_latest_season(data_path)

        if season_id:
            st.success(
                f"✅ Synced season **{season_id}** — **{results_count}** results stored across all rounds.\n\n"
                f"🎯 Current matchday: **{fx_md}** with **{fx_count}** fixtures ready to predict."
            )
            st.rerun()
        else:
            st.error("❌ Could not find any active season. Check your internet connection or BetPawa status.")

    # ---------- SEASON META ----------
    if "_meta" in data:
        meta = data["_meta"]
        sync_time = meta.get("last_sync", "")[:19].replace("T", " ")
        st.info(f"📡 Last synced from season **{meta.get('season_id')}** at **{sync_time}**")


    # ---------- STORAGE SUMMARY ----------
    st.markdown("---")
    st.subheader("📋 Storage Summary (accuracy_data.json)")
    if stored_mds:
        summary_rows = []
        for md in stored_mds:
            entry = data.get(md, {})
            summary_rows.append({
                "Matchday": md,
                "Results": len(entry.get("results", [])),
                "Fixtures": len(entry.get("fixtures", [])),
                "Predictions": len(entry.get("predictions", [])),
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        total_res = sum(row["Results"] for row in summary_rows)
        total_fix = sum(row["Fixtures"] for row in summary_rows)
        total_pred = sum(row["Predictions"] for row in summary_rows)
        c1, c2, c3 = st.columns(3)
        c1.metric("📊 Total Results", total_res)
        c2.metric("📅 Total Fixtures", total_fix)
        c3.metric("🔮 Total Predictions", total_pred)
    else:
        st.info("📭 No matchdays stored yet. Click 'Fetch & Store Results' to start.")

def show_predict_betpawa():
    st.markdown("## 🔮 Predict BetPawa – Over 2.5 Focus")
    st.caption("Ranks every fixture by Over 2.5 probability using 9-algorithm consensus")

    import json, os
    from scipy.stats import poisson as _poisson_dist

    data_path = "accuracy_data.json"
    if not os.path.exists(data_path):
        st.warning("⚠️ No accuracy_data.json found. Go to '🔄 Sync BetPawa' first.")
        return

    try:
        with open(data_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        st.error("⚠️ accuracy_data.json is missing or corrupted. Please re-sync from the Sync BetPawa page.")
        return

    stored_mds = sorted([k for k in data.keys() if k.isdigit()], key=int)
    if not stored_mds:
        st.warning("No matchdays stored yet.")
        return

    # Find matchdays that actually have fixtures (unplayed matches)
    mds_with_fixtures = [md for md in stored_mds if data[md].get("fixtures")]
    mds_complete      = [md for md in stored_mds if md not in mds_with_fixtures]

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("✅ Completed Matchdays", f"{len(mds_complete)} (MD {mds_complete[0]}–{mds_complete[-1]})" if mds_complete else "0")
    with col_b:
        st.metric("📅 Matchdays with Fixtures", f"{len(mds_with_fixtures)}")

    if not mds_with_fixtures:
        st.warning("⚠️ No matchdays have fixtures yet. Sync more data from the '🔄 Sync BetPawa' page.")
        return

    # Default to the LATEST matchday with fixtures
    default_md = mds_with_fixtures[-1]

    selected_md = st.selectbox(
        "Select matchday to predict:",
        options=mds_with_fixtures,   # only show those with fixtures
        index=mds_with_fixtures.index(default_md),
        key="bp_predict_md_select"
    )

    entry = data.get(selected_md, {})
    fixtures = entry.get("fixtures", [])
    if not fixtures:
        st.warning(f"⚠️ Matchday {selected_md} has no fixtures stored. Sync again.")
        return

    st.info(f"📅 Matchday **{selected_md}** — {len(fixtures)} fixtures ready.")
    # Progress
    total_mds = 34
    progress_pct = int(selected_md) / total_mds
    st.progress(min(progress_pct, 1.0), text=f"Season progress: MD {selected_md}/{total_mds}")


    # ---------- TRAIN HISTORY ----------
    training_matches = []
    for md in stored_mds:
        if int(md) >= int(selected_md):
            continue
        for r in data[md].get("results", []):
            training_matches.append({
                "home": r["home"], "away": r["away"],
                "ft_h": r["ft_h"], "ft_a": r["ft_a"]
            })

    st.caption(f"🧠 Training on **{len(training_matches)}** historical matches from matchdays before {selected_md}.")

    if len(training_matches) < 20:
        st.error("❌ Not enough historical data (need at least 20 matches). Sync more results first.")
        return

    # ---------- HELPER FUNCTIONS ----------
    def over25_prob(lam_h, lam_a, max_goals=10):
        """P(total goals > 2.5) from two Poisson lambdas."""
        p_under = 0.0
        for i in range(max_goals):
            for j in range(max_goals):
                if i + j <= 2:
                    p_under += _poisson_dist.pmf(i, lam_h) * _poisson_dist.pmf(j, lam_a)
        return max(0.0, min(1.0, 1.0 - p_under))

    def btts_prob(lam_h, lam_a):
        """P(both teams score) from two Poisson lambdas."""
        return (1 - _poisson_dist.pmf(0, lam_h)) * (1 - _poisson_dist.pmf(0, lam_a))

    def expected_goals_prob(lam_h, lam_a, line=2.5):
        return over25_prob(lam_h, lam_a)

    # ---------- RUN BUTTON ----------
    if st.button(f"🚀 RUN OVER 2.5 CONSENSUS ON MD {selected_md}", type="primary", use_container_width=True):
        with st.spinner(f"Training 9 algorithms on {len(training_matches)} matches..."):
            # Instantiate
            # ----- 9 original algorithms -----
            elo       = ELO_Rating()
            markov    = MarkovChainPredictor()
            logistic  = LogisticPredictor()
            poisson   = PoissonPredictor()
            dixon     = DixonColesPredictor()
            bayes     = BayesianPredictor()
            form      = WeightedFormPredictor()
            stats     = LeagueStats("BetPawa")

            # ----- 5 new power algorithms -----
            kalman    = KalmanTeamStrength(process_noise=0.05, measurement_noise=0.3)
            xgb_model = XGBGoalPredictor()
            meta      = MetaLearner()
            calibrator = ConfidenceCalibrator(n_bins=10)


            stats     = LeagueStats("BetPawa")

            # ---------- TRAIN ALL ALGORITHMS ON HISTORY ----------
            for m in training_matches:
                h, a, fh, fa = m["home"], m["away"], m["ft_h"], m["ft_a"]
                ht_h, ht_a = fh, fa

                elo.update_ratings(h, a, fh, fa)

                if fh > fa:
                    markov.add_result(h, 'W'); markov.add_result(a, 'L')
                elif fh == fa:
                    markov.add_result(h, 'D'); markov.add_result(a, 'D')
                else:
                    markov.add_result(h, 'L'); markov.add_result(a, 'W')

                logistic.add_match(h, a, fh, fa)
                poisson.add_match(h, a, fh, fa)
                dixon.add_match(h, a, fh, fa)
                bayes.add_match(h, a, fh, fa)
                form.add_match(h, a, fh, fa)
                stats.add_match(h, a, fh, fa, ht_h, ht_a)
                kalman.add_match(h, a, fh, fa)
                xgb_model.add_match(h, a, fh, fa)

            # ---------- TRAIN XGBOOST (needs data accumulated first) ----------
            xgb_model.fit()

            # ---------- TRAIN META-LEARNER ONCE ----------
            st.caption("🧠 Training meta-learner on historical accuracy...")
            meta_progress = st.progress(0)
            for i, m in enumerate(training_matches):
                h, a, fh, fa = m["home"], m["away"], m["ft_h"], m["ft_a"]
                actual = "home" if fh > fa else ("draw" if fh == fa else "away")

                try:
                    algo_preds = {
                        "elo":     elo.predict_match(h, a),
                        "markov":  markov.predict_match(h, a),
                        "poisson": poisson.predict_match(h, a),
                        "dixon":   dixon.predict_match(h, a),
                        "bayes":   bayes.predict_match(h, a),
                        "form":    form.predict_match(h, a),
                        "kalman":  kalman.predict_match(h, a),
                        "xgb":     xgb_model.predict_match(h, a),
                    }
                    meta.log_prediction(algo_preds, actual)
                except Exception:
                    continue

                if i % 50 == 0:
                    meta_progress.progress((i + 1) / len(training_matches))

            meta.fit_weights()
            meta_progress.progress(1.0)

            voter = ConsensusVoter()
            voter.add_algorithm('stats_poisson', stats)
            voter.add_algorithm('elo', elo)
            voter.add_algorithm('markov', markov)
            voter.add_algorithm('logistic', logistic)
            voter.add_algorithm('dixon', dixon)
            voter.add_algorithm('bayesian', bayes)
            voter.add_algorithm('weighted_form', form)
            voter.add_algorithm('new_poisson', poisson)

            # ---------- PREDICT EACH FIXTURE ----------
            predictions = []
            for fx in fixtures:
                home, away = fx["home"], fx["away"]
                league = fx.get("league", "Unknown")

                try:
                    cons = voter.predict_match(home, away)
                except Exception as e:
                    st.warning(f"⚠️ Failed to predict {home} vs {away}: {e}")
                    continue

                # ---------- NEW: Kalman prediction ----------
                try:
                    kal_pred = kalman.predict_match(home, away)
                except Exception:
                    kal_pred = {"home_win": 0.33, "draw": 0.33, "away_win": 0.33,
                                "expected_home_goals": 1.3, "expected_away_goals": 1.1}

                # ---------- NEW: XGBoost prediction ----------
                try:
                    xgb_pred = xgb_model.predict_match(home, away)
                except Exception:
                    xgb_pred = kal_pred  # fallback

                # ---------- NEW: Build consensus using Meta-Learner ----------
                algo_preds = {
                    "stats":  cons,          # the original 8-algo consensus
                    "kalman": kal_pred,
                    "xgb":    xgb_pred,
                }
                try:
                    meta_result = meta.blend(algo_preds)
                except Exception:
                    meta_result = {"home_win": cons["home_win"],
                                   "draw": cons["draw"],
                                   "away_win": cons["away_win"],
                                   "winner": cons.get("winner", "draw")}

                # ---------- NEW: Score Matrix from Kalman + XGBoost lambdas ----------
                lam_h = (kal_pred.get("expected_home_goals", 1.3) +
                         xgb_pred.get("expected_home_goals", 1.3)) / 2
                lam_a = (kal_pred.get("expected_away_goals", 1.1) +
                         xgb_pred.get("expected_away_goals", 1.1)) / 2

                matrix = build_score_matrix(lam_h, lam_a, max_goals=8)
                matrix_summary = summarize_matrix(matrix)

                # ---------- Blend Over 2.5: matrix + stats + poisson ----------
                try:
                    stats_pred = stats.predict_match(home, away, patterns=None, simulations=10000)
                    stats_over25 = float(stats_pred.get("over25", 0.5))
                    stats_btts    = float(stats_pred.get("btts", 0.5))
                except Exception:
                    stats_over25, stats_btts = 0.5, 0.5

                from scipy.stats import poisson as _pd
                def poisson_over25(lh, la):
                    p_under = sum(_pd.pmf(i, lh) * _pd.pmf(j, la)
                                  for i in range(10) for j in range(10) if i + j <= 2)
                    return 1 - p_under

                poisson_o25 = poisson_over25(lam_h, lam_a)

                # Final Over 2.5 = weighted blend of 3 sources
                over25 = round((matrix_summary["over25"] * 0.5 +
                                stats_over25 * 0.25 +
                                poisson_o25 * 0.25), 4)

                # BTTS blend
                btts = round((matrix_summary["btts"] * 0.6 +
                              stats_btts * 0.4), 4)

                expected_goals = round(lam_h + lam_a, 2)

                # ---------- Agreement ----------
                algos_used = cons.get("algorithms_used", 0)
                agreement = cons.get("agreement", 0)
                agreement_str = f"{int(round(agreement * algos_used))}/{algos_used}" if algos_used else "0/0"

                # ---------- Winner (from meta-learner) ----------
                winner_code = meta_result.get("winner", "draw")
                if winner_code == "home":
                    pick = f"{home} Win"; conf = meta_result.get("home_win", 0)
                elif winner_code == "away":
                    pick = f"{away} Win"; conf = meta_result.get("away_win", 0)
                else:
                    pick = "Draw"; conf = meta_result.get("draw", 0)

                # ---------- Calibrated Over 2.5 confidence ----------
                try:
                    over25_calibrated = calibrator.calibrate(over25)
                except Exception:
                    over25_calibrated = over25

                # ---------- Rating (Over 2.5 focused) ----------
                if over25 >= 0.85:
                    rating = "🥇 Elite O2.5"
                elif over25 >= 0.75:
                    rating = "🥈 High O2.5"
                elif over25 >= 0.50:
                    rating = "🥉 Medium O2.5"
                elif over25 >= 0.45:
                    rating = "⚠️ Risky"
                else:
                    rating = "❌ Skip"

                predictions.append({
                    "home": home,
                    "away": away,
                    "league": league,
                    "over25_pct": round(over25 * 100, 1),
                    "over25_calibrated_pct": round(over25_calibrated * 100, 1),
                    "btts_pct": round(btts * 100, 1),
                    "expected_goals": expected_goals,
                    "most_likely_score": matrix_summary["most_likely_score"],
                    "rating": rating,
                    "agreement": agreement_str,
                    "algorithms_used": algos_used + 2,   # +kalman +xgb
                    # Winner (secondary)
                    "winner_pick": pick,
                    "winner_conf": round(conf, 3),
                    "home_win": round(meta_result.get("home_win", 0), 3),
                    "draw": round(meta_result.get("draw", 0), 3),
                    "away_win": round(meta_result.get("away_win", 0), 3),
                    # Meta-learner weights (for display / debugging)
                    "meta_weights": meta_result.get("weights", {}),
                })

            # Sort by Over 2.5 descending
            predictions.sort(key=lambda x: x["over25_pct"], reverse=True)

            data[selected_md]["predictions"] = predictions
            safe_json_write(data_path, data)

            st.success(f"✅ Predicted {len(predictions)} fixtures for MD {selected_md} — sorted by Over 2.5.")
            st.rerun()

    # ---------- DISPLAY STORED PREDICTIONS ----------
    st.markdown("---")
    existing = entry.get("predictions", [])
    if existing:
        # Ensure sorted
        existing = sorted(existing, key=lambda x: x.get("over25_pct", 0), reverse=True)

        # ---------- TOP OVER 2.5 CARD ----------
        st.subheader("🔥 Top Over 2.5 Picks-chagua!!")
        top3 = existing[:3]
        cols = st.columns(3)
        for i, p in enumerate(top3):
            with cols[i]:
                border = "#FFD700" if p['over25_pct'] >= 85 else "#00FF88" if p['over25_pct'] >= 70 else "#4FC3F7"
                st.markdown(f"""
                <div style="background:#1e1e2e;border-radius:10px;padding:14px;
                            border:2px solid {border};text-align:center;">
                    <div style="font-size:0.7rem;color:#888;text-transform:uppercase;letter-spacing:1px;">{p.get('league','')}</div>
                    <div style="font-size:1.05rem;font-weight:700;margin:6px 0;color:#fff;">{p['home']} vs {p['away']}</div>
                    <div style="font-size:2rem;font-weight:900;color:#FFD700;">{p['over25_pct']}%</div>
                    <div style="font-size:0.8rem;color:#aaa;">Over 2.5</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:6px;">
                        ⚽ Expected goals: <b style="color:#fff;">{p['expected_goals']}</b><br>
                        🧤 BTTS: <b style="color:#fff;">{p['btts_pct']}%</b><br>
                        🤝 {p.get('agreement','N/A')} agree • {p.get('rating','')}
                    </div>
                </div>
                """, unsafe_allow_html=True)

        # ---------- FULL TABLE ----------
        st.subheader(f"📊 All {len(existing)} MD {selected_md} Predictions (Sorted by Over 2.5)")
        df = pd.DataFrame(existing)

        # Reorder columns — Over 2.5 first
        display_cols = ["rating", "league", "home", "away", "over25_pct",
                        "expected_goals", "btts_pct", "agreement",
                        "winner_pick", "winner_conf"]
        display_cols = [c for c in display_cols if c in df.columns]
        df_display = df[display_cols].copy()

        # Rename for readability
        df_display.columns = [
            "Rating", "League", "Home", "Away", "Over 2.5 %",
            "Exp Goals", "BTTS %", "Agreement",
            "Winner Pick", "Win Conf"
        ][:len(display_cols)]

        def colour_over25(val):
            try:
                n = float(val)
                if n >= 85: return "background-color:#1a4d1a;color:#00FF88;font-weight:bold"
                if n >= 70: return "background-color:#1a3d4d;color:#4FC3F7;font-weight:bold"
                if n >= 50: return "background-color:#4d4d1a;color:#FFD700"
                return ""
            except: return ""

        styled = df_display.style.map(colour_over25, subset=["Over 2.5 %"]) if "Over 2.5 %" in df_display.columns else df_display
        st.dataframe(styled, use_container_width=True, hide_index=True, height=600)

        # ---------- BTTS TOP PICKS ----------
        st.markdown("---")
        st.subheader("🧤 Top BTTS Picks")
        btts_sorted = sorted(existing, key=lambda x: x.get("btts_pct", 0), reverse=True)[:5]
        btts_df = pd.DataFrame([{
            "League": p["league"],
            "Match": f"{p['home']} vs {p['away']}",
            "BTTS %": p["btts_pct"],
            "Over 2.5 %": p["over25_pct"],
            "Exp Goals": p["expected_goals"]
        } for p in btts_sorted])
        st.dataframe(btts_df, use_container_width=True, hide_index=True)

        # ---------- QUICK SUMMARY ----------
        st.markdown("---")
        st.subheader("📋 Quick Summary")
        c1, c2, c3 = st.columns(3)
        elite  = sum(1 for p in existing if p.get("over25_pct", 0) >= 85)
        high   = sum(1 for p in existing if 65 <= p.get("over25_pct", 0) < 70)
        medium = sum(1 for p in existing if 55 <= p.get("over25_pct", 0) < 50)
        c1.metric("🥇 Elite O2.5 (≥85%)", elite)
        c2.metric("🥈 High O2.5 ", high)
        c3.metric("🥉 Medium O2.5 ", medium)

        # Download
        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Download MD Predictions CSV",
            data=csv,
            file_name=f"betpawa_md{selected_md}_over25_predictions.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.info("No predictions stored yet for this matchday. Click the RUN button above.")


def show_best_over25_picks():
    st.markdown("## ⚽ Best Over 2.5 Picks Per League")
    st.caption("Top 2 matches per league with highest Over 2.5 probability")
    predictions = st.session_state.get('current_predictions', [])
    if predictions:
        from collections import defaultdict
        league_picks = defaultdict(list)
        for p in predictions:
            league = p.get('League', 'Unknown')
            over25_str = p.get('O/U 2.5', '0%')
            try:
                over25 = float(over25_str.replace('%', ''))
            except:
                over25 = 0
            league_picks[league].append({
                'match': p.get('Match', ''),
                'over25': over25,
                'confidence': p.get('Confidence', 0),
                'most_likely': p.get('Most Likely', 'N/A'),
                'rating': p.get('Rating', 'N/A')
            })
        all_leagues = []
        for league, picks in league_picks.items():
            sorted_picks = sorted(picks, key=lambda x: x['over25'], reverse=True)
            for i, pick in enumerate(sorted_picks[:2]):
                all_leagues.append({
                    'League': league,
                    'Rank': i+1,
                    'Match': pick['match'],
                    'Over 2.5': f"{pick['over25']:.1f}%",
                    'Confidence': f"{pick['confidence']*100:.1f}%",
                    'Most Likely': pick['most_likely'],
                    'Rating': pick['rating']
                })
        if not all_leagues:
            st.info("No Over 2.5 picks available from full predictions.")
            return
        df = pd.DataFrame(all_leagues)
        st.dataframe(df, use_container_width=True)
        st.subheader("📋 Quick Summary (Top 2 per League)")
        for league in league_picks.keys():
            league_df = df[df['League'] == league]
            if not league_df.empty:
                st.markdown(f"**{league}**")
                for _, row in league_df.iterrows():
                    st.write(f"  {row['Rank']}. {row['Match']} – Over 2.5: {row['Over 2.5']} | Most Likely: {row['Most Likely']} | Rating: {row['Rating']}")
    else:
        from utils.automation_engine import AutomationEngine
        engine = AutomationEngine()
        with st.spinner("Generating early Over 2.5 picks..."):
            picks = engine.get_early_over25_picks(limit=2)
        if not picks:
            st.warning("⚠️ Not enough data. Please ensure you have at least 3 matchdays and fixtures for each league.")
            return
        display_data = []
        for p in picks:
            home, away = p['match']
            display_data.append({
                'Home': home,
                'Away': away,
                'Over 2.5': f"{p['over25']*100:.1f}%",
                'Confidence': f"{p['Confidence']*100:.1f}%",
                'Most Likely': p['most_likely'],
                'Rating': p['Rating']
            })
        if not display_data:
            st.info("No early picks available.")
            return
        df = pd.DataFrame(display_data)
        st.dataframe(df, use_container_width=True)
        st.subheader("📋 Quick Summary")
        for idx, row in df.iterrows():
            st.write(f"{idx+1}. {row['Home']} vs {row['Away']} – Over 2.5: {row['Over 2.5']} | Most Likely: {row['Most Likely']} | Rating: {row['Rating']}")


def show_accuracy_tracking():
    st.markdown("## 📊 Accuracy Tracking — Over 2.5 & BTTS")
    st.caption("Compares predictions against actual results. Over 2.5 is the primary focus.")

    from utils.accuracy_tracker_over25 import (
        update_accuracy_stats, get_summary, get_matchday_detail, reset_stats,
        load_data,
    )

    # Auto-update on load
    updated = update_accuracy_stats()
    if updated:
        st.toast(f"✅ Evaluated {updated} new matchday(s)", icon="📊")

    summary = get_summary()

    # ---------- HERO METRICS ----------
    c1, c2, c3, c4 = st.columns(4)
    o25 = summary["over25"]
    btts = summary["btts"]

    c1.metric("🎯 Over 2.5 — Predictions", o25["total"])
    c2.metric(
        "🎯 Over 2.5 — Accuracy",
        f"{o25['accuracy']*100:.1f}%",
        delta=f"{o25['correct']} correct",
    )
    c3.metric("🤝 BTTS — Predictions", btts["total"])
    c4.metric(
        "🤝 BTTS — Accuracy",
        f"{btts['accuracy']*100:.1f}%",
        delta=f"{btts['correct']} correct",
    )

    # ---------- OVER 2.5 CONFIDENCE BUCKETS (PRIMARY) ----------
    st.markdown("---")
    st.subheader("🎯 Over 2.5 — Accuracy by Confidence Bucket")
    if summary["by_confidence"]:
        import pandas as pd
        df = pd.DataFrame(summary["by_confidence"])
        df["Accuracy"] = (df["Accuracy"] * 100).round(1).astype(str) + "%"
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No Over 2.5 evaluations yet. Wait for the first matchday to complete.")

    # ---------- PER-MATCHDAY BREAKDOWN ----------
    st.markdown("---")
    st.subheader("📅 Per-Matchday Accuracy")
    if summary["by_matchday"]:
        import pandas as pd
        rows = []
        for md, v in sorted(summary["by_matchday"].items(), key=lambda x: int(x[0])):
            rows.append({
                "Matchday": md,
                "Matches": v["matches"],
                "Over 2.5 Acc": f"{v['over25_accuracy']*100:.1f}%",
                "O2.5 Correct": f"{v['over25_correct']}/{v['matches']}",
                "BTTS Acc": f"{v['btts_accuracy']*100:.1f}%",
                "BTTS Correct": f"{v['btts_correct']}/{v['matches']}",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No matchdays evaluated yet.")

    # ---------- DETAILED VIEW ----------
    st.markdown("---")
    st.subheader("🔍 Per-Match Detail")
    data = load_data()
    mds_with_both = sorted(
        [k for k in data.keys() if k.isdigit()
         and data[k].get("predictions") and data[k].get("results")],
        key=int, reverse=True
    )
    if mds_with_both:
        selected_md = st.selectbox(
            "Select matchday",
            options=mds_with_both,
            key="acc_detail_md"
        )
        detail = get_matchday_detail(selected_md)
        if detail:
            import pandas as pd
            df = pd.DataFrame(detail)
            df = df.rename(columns={
                "home": "Home", "away": "Away",
                "pred_o25_pct": "Pred O2.5 %",
                "pred_o25": "Pred O2.5",
                "actual_o25": "Actual O2.5",
                "correct_o25": "✓ O2.5",
                "pred_btts_pct": "Pred BTTS %",
                "pred_btts": "Pred BTTS",
                "actual_btts": "Actual BTTS",
                "correct_btts": "✓ BTTS",
                "actual_ft": "FT",
            })

            # Sort: correct O2.5 hits first, then by predicted %
            df = df.sort_values(["✓ O2.5", "Pred O2.5 %"], ascending=[False, False])

            # Colour
            def colour_row(row):
                if row["✓ O2.5"]:
                    return ["background-color:#1a4d1a"] * len(row)
                return ["background-color:#4d1a1a"] * len(row)

            styled = df.style.apply(colour_row, axis=1)
            st.dataframe(styled, use_container_width=True, hide_index=True, height=500)

            # Quick stats for this MD
            o25_hits = sum(1 for d in detail if d["correct_o25"])
            st.caption(
                f"MD {selected_md}: **{o25_hits}/{len(detail)}** Over 2.5 correct "
                f"({o25_hits/len(detail)*100:.1f}%)"
            )
    else:
        st.info("No matchdays have both predictions and results yet.")

    # ---------- HISTORY CHART ----------
    st.markdown("---")
    st.subheader("📈 Accuracy Trend")
    hist = summary["over25"]["history"]
    if len(hist) >= 2:
        import pandas as pd
        import plotly.graph_objects as go
        df = pd.DataFrame(hist)
        df["matchday"] = df["matchday"].astype(int)
        df = df.sort_values("matchday")
        df["accuracy_pct"] = df["accuracy"] * 100

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["matchday"], y=df["accuracy_pct"],
            mode="lines+markers", name="Over 2.5 Accuracy",
            line=dict(color="#FFD700", width=3),
            marker=dict(size=10)
        ))
        # BTTS line (secondary, muted)
        btts_hist = summary["btts"]["history"]
        if len(btts_hist) >= 2:
            df_btts = pd.DataFrame(btts_hist)
            df_btts["matchday"] = df_btts["matchday"].astype(int)
            df_btts = df_btts.sort_values("matchday")
            df_btts["accuracy_pct"] = df_btts["accuracy"] * 100
            fig.add_trace(go.Scatter(
                x=df_btts["matchday"], y=df_btts["accuracy_pct"],
                mode="lines+markers", name="BTTS Accuracy",
                line=dict(color="#4FC3F7", width=2, dash="dot"),
                marker=dict(size=8), opacity=0.6
            ))
        fig.update_layout(
            xaxis_title="Matchday",
            yaxis_title="Accuracy (%)",
            yaxis=dict(range=[0, 100]),
            template="plotly_dark",
            height=400,
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Need at least 2 evaluated matchdays to draw the trend.")

    # ---------- DANGER ZONE ----------
    st.markdown("---")
    with st.expander("⚠️ Reset Accuracy Stats", expanded=False):
        st.caption("Deletes the stats file. Will be rebuilt on next load.")
        if st.button("🗑️ Reset Accuracy Stats", type="secondary"):
            reset_stats()
            st.success("✅ Stats cleared. Reloading...")
            st.rerun()



def show_accuracy():
    st.markdown("## 📊 Prediction Accuracy")
    st.caption("Accuracy over the last 20 matchdays (from MD3 onward)")
    from utils.accuracy_tracker import AccuracyTracker
    tracker = AccuracyTracker()
    overall = tracker.get_overall_accuracy()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Overall Match Winner", f"{overall['overall']*100:.1f}%", f"{overall['matches']} matches")
    with col2:
        st.metric("Over 2.5 Accuracy", f"{overall['over25']*100:.1f}%")
    with col3:
        st.metric("BTTS Accuracy", f"{overall['btts']*100:.1f}%")
    st.divider()
    st.subheader("📋 Per Matchday Accuracy")
    matchdays = tracker.get_all_matchdays()
    if matchdays:
        rows = []
        for md in matchdays:
            acc = tracker.get_matchday_accuracy(md)
            if acc:
                rows.append({
                    "Matchday": md,
                    "Correct": acc['correct'],
                    "Total": acc['total'],
                    "Accuracy": f"{acc['accuracy']*100:.1f}%",
                    "O/U Acc": f"{acc['over25']['accuracy']*100:.1f}%",
                    "BTTS Acc": f"{acc['btts']['accuracy']*100:.1f}%"
                })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No accuracy data yet. Run the pipeline to start tracking.")


def show_league_performance():
    st.markdown("## 📊 League Performance & Confidence Trends")
    st.caption("Track accuracy and confidence per league over time")
    from utils.accuracy_tracker import AccuracyTracker
    tracker = AccuracyTracker()
    st.subheader("🏆 League Performance (Accuracy)")
    if hasattr(tracker, 'league_accuracy'):
        league_perf = []
        for league, stats in tracker.league_accuracy.items():
            if stats['total'] > 0:
                league_perf.append({
                    'League': league,
                    'Matches': stats['total'],
                    'Accuracy': f"{stats['correct']/stats['total']*100:.1f}%"
                })
        if league_perf:
            df = pd.DataFrame(league_perf)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("League performance data will appear after enough matchdays.")
    else:
        st.info("📊 Collecting data... League performance will appear after 5+ matchdays.")

    st.subheader("📈 Confidence Trend Over Time")
    if 'current_predictions' in st.session_state and st.session_state.current_predictions:
        predictions = st.session_state.current_predictions
        if predictions:
            avg_confidence = sum(p.get('Confidence', 0) for p in predictions) / len(predictions)
            current_md = st.session_state.get('current_matchday', 0)
            if 'confidence_history' not in st.session_state:
                st.session_state.confidence_history = []
            st.session_state.confidence_history.append({
                'matchday': current_md,
                'avg_confidence': avg_confidence * 100,
                'total_predictions': len(predictions)
            })
            if len(st.session_state.confidence_history) > 50:
                st.session_state.confidence_history = st.session_state.confidence_history[-50:]

    if 'confidence_history' in st.session_state and st.session_state.confidence_history:
        df_conf = pd.DataFrame(st.session_state.confidence_history)
        df_conf = df_conf.sort_values('matchday')
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_conf['matchday'],
            y=df_conf['avg_confidence'],
            mode='lines+markers',
            name='Avg Confidence (%)',
            line=dict(color='#FFD700', width=2),
            marker=dict(size=8)
        ))
        fig.update_layout(
            title='Average Confidence per Matchday',
            xaxis_title='Matchday',
            yaxis_title='Confidence (%)',
            template='plotly_dark',
            height=400,
            hovermode='x'
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Last 5 matchdays: {df_conf.tail(5).to_dict('records')}")
    else:
        st.info("📊 Confidence data will appear after running predictions.")


def show_session_management():
    st.markdown("## 📊 Session Management & Analysis")
    tab1, tab2 = st.tabs(["📈 Session Overview", "⚙️ Manage Sessions"])

    with tab1:
        if st.session_state.session_manager:
            display_session_comparison(st.session_state.session_manager)
        else:
            st.info("Session manager not initialized.")

    with tab2:
        col1, col2 = st.columns(2)

        with col1:
            # --- Delete all sessions (from apex_sessions.json) ---
            if st.button("🗑️ Delete All Sessions", type="secondary", width='stretch'):
                if st.session_state.session_manager:
                    st.session_state.session_manager.delete_all_sessions()
                    st.toast("🗑️ All sessions deleted!", icon="🗑️")
                    st.rerun()
                else:
                    st.warning("Session manager not available.")

            # --- Reset all VunjaBei data (progress + stored matches) ---
            if st.button("🧹 Reset All VunjaBei Data", type="secondary", width='stretch'):
                import os
                # Delete progress file
                if os.path.exists('vunja_progress.json'):
                    os.remove('vunja_progress.json')
                # Clear session state data
                if 'vunja_league_accum' in st.session_state:
                    st.session_state.vunja_league_accum = {}
                    for name in LEAGUE_TEAMS.keys():
                        st.session_state.vunja_league_accum[name] = {
                            'results': [],
                            'fixtures_data': None,
                            'processed': False
                        }
                st.session_state.vunja_predictions = []
                st.session_state.current_predictions = []
                st.toast("✅ All VunjaBei data cleared!", icon="🧹")
                st.rerun()

        with col2:
            # --- Export all sessions as JSON ---
            if st.button("📥 Export Sessions (JSON)", type="secondary", width='stretch'):
                if st.session_state.session_manager:
                    import json
                    data = json.dumps(st.session_state.session_manager.sessions, indent=2, default=str)
                    st.download_button(
                        label="📥 Download",
                        data=data,
                        file_name="apex_sessions_export.json",
                        mime="application/json",
                        width='stretch',
                        key="download_session_data"
                    )
                else:
                    st.warning("No sessions to export.")


def clear_fixtures_only():
    for name in LEAGUE_TEAMS.keys():
        st.session_state.league_accum[name]['fixtures_data'] = None
    st.success("✅ All fixtures cleared!")
    st.rerun()


def reset_all_data():
    for name in LEAGUE_TEAMS.keys():
        st.session_state.league_accum[name] = {
            'results': [],
            'fixtures_data': None,
            'processed': False
        }
    st.session_state.all_predictions = []
    st.session_state.current_predictions = []
    st.session_state.current_matchday = None
    st.session_state.processing_log = []
    st.session_state.batch_matchday = 1
    if st.session_state.logged_in and st.session_state.username:
        filepath = os.path.join(DATA_DIR, f"{st.session_state.username}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
        save_user_data(st.session_state.username, {})
    try:
        from utils.htft_scraper import clear_htft_cache
        clear_htft_cache()
    except:
        pass
    st.success("✅ All data (results, fixtures, predictions) has been reset!")
    st.rerun()


def show_login():
    st.title("🔐 APEX Engine - Login / Register")
    tab_login, tab_register = st.tabs(["Login", "Register"])
    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submit = st.form_submit_button("Login", use_container_width=True)
            if submit:
                if not username or not password:
                    st.error("Please enter both username and password.")
                elif login_user(username, password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.user_data_loaded = False
                    load_user_data_into_session(username)
                    st.success(f"✅ Welcome back, {username}!")
                    st.rerun()
                else:
                    st.error("❌ Invalid username or password.")
    with tab_register:
        with st.form("register_form"):
            new_user = st.text_input("Choose Username", key="reg_username")
            new_pass = st.text_input("Choose Password", type="password", key="reg_password")
            confirm_pass = st.text_input("Confirm Password", type="password", key="reg_confirm")
            submit_reg = st.form_submit_button("Register", use_container_width=True)
            if submit_reg:
                if not new_user or not new_pass:
                    st.error("Please fill all fields.")
                elif new_pass != confirm_pass:
                    st.error("Passwords do not match.")
                elif register_user(new_user, new_pass):
                    st.success("✅ User registered! Please login.")
                else:
                    st.error("❌ Username already exists.")


# ============================================================
# AUTHENTICATION
# ============================================================
if not st.session_state.logged_in:
    show_login()
    st.stop()

if not st.session_state.user_data_loaded:
    if st.session_state.username:
        load_user_data_into_session(st.session_state.username)


# ============================================================
# VUNJABEI DASHBOARD
# ============================================================

# ============================================================
# HEADER & SIDEBAR
# ============================================================
st.markdown("""
<style>
.main-header { font-size: 3rem; font-weight: 800; background: linear-gradient(45deg, #FFD700, #FF6B00); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; padding: 1rem 0; }
.sub-header { text-align: center; color: #888; font-size: 1.1rem; margin-bottom: 2rem; }
.metric-card { background: #1e1e2e; border-radius: 10px; padding: 1rem; text-align: center; border: 1px solid #333; }
.elite { color: #FFD700; font-weight: bold; }
.high { color: #00FF88; font-weight: bold; }
.medium { color: #4FC3F7; font-weight: bold; }
.risky { color: #FFA726; font-weight: bold; }
.skip { color: #888; font-weight: bold; }
.warning-box { background: #ff6b6b22; border-left: 4px solid #ff6b6b; padding: 0.5rem 1rem; border-radius: 5px; margin: 0.5rem 0; }
.stButton > button { font-weight: bold !important; font-size: 1.1rem !important; padding: 0.5rem 2rem !important; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">⚽ APEX - NT kasusa Engine</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header"> 9-Algorithm Consensus | Live Dashboard | Rolling Predictions | 7 Leagues | Leaky Defense Boost</div>', unsafe_allow_html=True)


# ============================================================
# PLATFORM SELECTOR
# ============================================================


# ============================================================
# SIDEBAR NAVIGATION
# ============================================================
with st.sidebar:
    st.markdown("---")
    st.markdown("### 🧭 Navigation")
    page = st.radio(
        "Go to",
        ["🏠 Home Dashboard", "📦 Batch Upload", "🔄 Sync BetPawa", "🔮 Predict BetPawa", "🤖 Auto Pilot", "📊 Accuracy Tracking", "🎧 Event Listener", "⚽ League Analysis", "🔮 Predictions",
            "🎯 HT/FT Best Bets", "📊 Session Management",
             "📊 Accuracy", "📊 Performance"],
        index=0,
        key="nav_radio_betpawa"
    )



    st.markdown("---")
    with st.expander("⚠️ Danger Zone", expanded=False):
        if st.button("🗑️ Reset All Data (Start Fresh)", type="secondary", use_container_width=True):
            st.warning("⚠️ This will delete ALL your data (results, fixtures, predictions, sessions).")
            confirm = st.checkbox("Yes, I want to delete all data and start fresh.")
            if confirm:
                if st.button("✅ Confirm Reset", type="primary"):
                    reset_all_data()
        if st.button("🗑️ Clear Fixtures Only", type="secondary", use_container_width=True):
            clear_fixtures_only()

    st.markdown("---")
    if st.button("🚪 Logout", type="secondary", use_container_width=True):
        logout_user()


# ============================================================
# PAGE ROUTING
# ============================================================
if page == "🏠 Home Dashboard":
    show_home_dashboard()
elif page == "📦 Batch Upload":
    show_batch_upload()
elif page == "🔄 Sync BetPawa":
    show_betpawa_sync()
elif page == "🔮 Predict BetPawa":
    show_predict_betpawa()
elif page == "🤖 Auto Pilot":
        show_auto_pilot()
elif page == "📊 Accuracy Tracking":
    show_accuracy_tracking()
elif page == "🎧 Event Listener":
    show_event_listener()
elif page == "⚽ League Analysis":
    show_league_analysis()
elif page == "🔮 Predictions":
    show_predictions()
elif page == "🎯 HT/FT Best Bets":
    from utils.htft_dashboard import show_htft_dashboard
    show_htft_dashboard()
elif page == "📊 Session Management":
    show_session_management()
elif page == "📊 Accuracy":
    show_accuracy()
elif page == "📊 Performance":
    show_league_performance()
else:
    st.info("Select a page from the sidebar.")


# ============================================================
# FOOTER
# ============================================================
with st.expander("Processing Log", expanded=False):
    if st.session_state.processing_log:
        for log in st.session_state.processing_log[-20:]:
            st.text(log)

st.caption("⚽ Kasusa Engine v1 | 4-Algorithm Consensus | Made with ❤️ & passion")