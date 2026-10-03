# utils/live_bet_bot.py
"""
Continuous live-betting bot.
- Runs in a background thread.
- Logs into BetPawa ONCE.
- Polls accuracy_data.json for qualified bets.
- Places bets automatically when matches appear.
- Respects daily limit — stops betting when hit, keeps running.
- Human-like delays to reduce detection risk.
"""

import threading
import time
import json
import os
import random
from datetime import datetime

# ---------------- GLOBAL STATE ----------------
_bot_thread = None
_bot_stop = threading.Event()
_bot_state = {
    "running": False,
    "phase": "idle",
    "session_alive": False,
    "bets_placed_today": 0,
    "last_bet_time": 0,
    "last_check": 0,
    "last_error": "",
    "started_at": 0,
    "seen_matches": set(),       # avoid re-betting same match in same session
    "daily_limit_hit": False,
}
_state_lock = threading.Lock()


def _set_state(**kwargs):
    with _state_lock:
        _bot_state.update(kwargs)


def get_bot_state():
    with _state_lock:
        s = dict(_bot_state)
        s["seen_matches"] = len(s["seen_matches"])  # return count, not set
        return s


def is_running():
    return _bot_thread is not None and _bot_thread.is_alive()


# ---------------- HUMAN-LIKE HELPERS ----------------
def _human_pause(short=True):
    """Random human-like pause."""
    if short:
        time.sleep(random.uniform(0.8, 2.2))
    else:
        time.sleep(random.uniform(2.5, 5.0))


def _human_scroll(driver, total_pixels=None):
    """Scroll in small human-like chunks with pauses."""
    if total_pixels is None:
        total_pixels = random.randint(200, 600)
    steps = random.randint(3, 7)
    per_step = total_pixels // steps
    for _ in range(steps):
        driver.execute_script(f"window.scrollBy(0, {per_step});")
        time.sleep(random.uniform(0.15, 0.4))


# ---------------- MAIN BOT LOOP ----------------
def _bot_loop(phone, password, headless):
    """The bot's continuous loop."""
    from utils.selenium_bettor import BetPawaSelenium
    from utils.auto_bettor import (
        load_config, scan_for_qualified_bets, log_bet, get_daily_bet_count,
    )

    bot = None
    try:
        _set_state(running=True, phase="launching browser",
                   started_at=time.time(), seen_matches=set())

        # ---------- START BROWSER ----------
        bot = BetPawaSelenium(headless=headless)
        _human_pause()
        _set_state(phase="logging in")

        if not bot.login(phone, password):
            _set_state(phase="error", last_error="Login failed",
                       running=False, session_alive=False)
            print("❌ Live bot: login failed")
            return

        _set_state(session_alive=True, phase="warmed up")
        print("✅ Live bot logged in. Starting main loop...")

        # ---------- MAIN LOOP ----------
        while not _bot_stop.is_set():
            try:
                cfg = load_config()

                # ---- Check daily limit ----
                today_count = get_daily_bet_count()
                if today_count >= cfg["daily_limit"]:
                    _set_state(phase="daily limit reached",
                               daily_limit_hit=True,
                               bets_placed_today=today_count)
                    print(f"⏸️ Daily limit hit ({today_count}/{cfg['daily_limit']}) — "
                          f"waiting for tomorrow")
                    # Sleep 5 min then re-check
                    for _ in range(300):
                        if _bot_stop.is_set():
                            break
                        time.sleep(1)
                    continue

                _set_state(phase="checking predictions",
                           last_check=time.time(),
                           bets_placed_today=today_count)

                # ---- Find qualified bets ----
                qualified = scan_for_qualified_bets()
                if not qualified:
                    _set_state(phase="waiting for predictions")
                    for _ in range(20):  # 20 sec
                        if _bot_stop.is_set():
                            break
                        time.sleep(1)
                    continue

                # ---- Filter out already-bet matches ----
                with _state_lock:
                    seen = set(_bot_state["seen_matches"])
                new_matches = [q for q in qualified
                               if f"{q['prediction']['home']}-{q['prediction']['away']}"
                               not in seen]

                if not new_matches:
                    _set_state(phase="all qualified bets already placed")
                    for _ in range(30):
                        if _bot_stop.is_set():
                            break
                        time.sleep(1)
                    continue

                # ---- Place bets ----
                for item in new_matches:
                    if _bot_stop.is_set():
                        break

                    # Re-check daily limit
                    if get_daily_bet_count() >= cfg["daily_limit"]:
                        break

                    p = item["prediction"]
                    home, away = p["home"], p["away"]
                    match_key = f"{home}-{away}"
                    stake = cfg["max_stake_tzs"]
                    league_raw = p.get("league", "") or ""

                    _set_state(phase=f"placing bet: {home} vs {away}")
                    print(f"\n🎰 Placing: {home} vs {away} ({league_raw}) — {stake} TZS")

                    # Human-like: navigate fresh each time
                    bot.go_to_virtuals()
                    time.sleep(random.uniform(4, 7))

                    from utils.auto_bettor import _map_league_to_ui_label
                    league_label = _map_league_to_ui_label(league_raw)

                    result = bot.place_over25_bet(
                        home_team=home,
                        away_team=away,
                        stake_tzs=stake,
                        league_name=league_label,
                        debug=False,
                    )

                    # Mark as seen (whether success or fail — avoid retry loop)
                    with _state_lock:
                        _bot_state["seen_matches"].add(match_key)

                    bet_record = {
                        "matchday": item["matchday"],
                        "match": f"{home} vs {away}",
                        "league": league_label,
                        "over25_pct": p.get("over25_pct"),
                        "btts_pct": p.get("btts_pct"),
                        "expected_goals": p.get("expected_goals"),
                        "most_likely_score": p.get("most_likely_score"),
                        "stake": stake,
                        "mode": "live-bot",
                        "placed_at": datetime.now().isoformat(),
                        "result": "PLACED" if result.get("success") else "FAILED",
                        "message": result.get("message", ""),
                    }
                    log_bet(bet_record)

                    if result.get("success"):
                        _set_state(last_bet_time=time.time(),
                                   bets_placed_today=get_daily_bet_count())
                        print(f"   ✅ Placed")

                        # Post-bet human pause
                        time.sleep(random.uniform(3, 6))
                    else:
                        print(f"   ❌ Failed: {result.get('message')}")
                        time.sleep(random.uniform(2, 4))

                # Wait before next check
                _set_state(phase="idle")
                for _ in range(15):
                    if _bot_stop.is_set():
                        break
                    time.sleep(1)

            except Exception as e:
                print(f"⚠️ Bot loop error: {e}")
                _set_state(last_error=str(e), phase="error")
                time.sleep(10)

        print("⏹️ Live bot stopped")
        _set_state(phase="stopped", running=False)

    finally:
        # Clean shutdown
        try:
            if bot:
                bot.close()
        except Exception:
            pass
        _set_state(running=False, session_alive=False, phase="stopped")


# ---------------- PUBLIC API ----------------
def start_bot(phone, password, headless=False):
    """Start the live betting bot (thread-safe)."""
    global _bot_thread
    if is_running():
        print("ℹ️ Bot already running")
        return False

    _bot_stop.clear()
    _bot_thread = threading.Thread(
        target=_bot_loop,
        args=(phone, password, headless),
        daemon=True,
        name="live-bet-bot",
    )
    _bot_thread.start()
    return True


def stop_bot():
    """Signal the bot to stop (browser will close gracefully)."""
    _bot_stop.set()
    print("⏹️ Stop signal sent to live bot")