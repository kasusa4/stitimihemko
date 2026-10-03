# utils/auto_bettor.py
"""
Auto-bettor for BetPawa.
Reads predictions from accuracy_data.json, checks conditions,
places bets via BetPawa API (or simulates).

SAFETY: starts in SIMULATION mode by default. Live mode requires
explicit toggle AND password re-entry for each betting session.
"""

import os
import json
import time
import hashlib
from datetime import datetime

# ---------------- CONFIG ----------------
CONFIG_FILE = "bettor_config.json"
BETS_LOG = "bets_log.json"

DEFAULT_CONFIG = {
    "max_stake_tzs": 500,         # max per bet
    "daily_limit": 3,             # max bets per day
    "min_over25_pct": 85.0,
    "min_expected_goals": 6.0,
    "min_btts_pct": 77.0,
    "min_score_total": 4,         # 🎯 "3-2" → 3+2 = 5 >= 4 ✓
    "cooldown_seconds": 120,      # wait between bets
    "phone": "",
    "pw_hash": "",                # sha256 of password
    "saved_at": "",

    "last_balance": None,          # ← NEW
    "last_balance_ts": "",         # ← NEW
    "live_enabled": False,     # ← NEW: replaces "mode"
    "headless": False,          # ← NEW
}


# ---------------- CREDENTIALS ----------------
def _hash_pw(pw):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def save_credentials(phone, password):
    cfg = load_config()
    cfg["phone"] = phone
    cfg["pw_hash"] = _hash_pw(password)
    cfg["saved_at"] = datetime.now().isoformat()
    _save_config(cfg)


def get_stored_phone():
    return load_config().get("phone", "")


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    else:
        cfg = {}
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def _save_config(cfg):
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_FILE)

def save_last_balance(balance):
    cfg = load_config()
    cfg["last_balance"] = float(balance)
    cfg["last_balance_ts"] = datetime.now().isoformat()
    _save_config(cfg)


def get_last_balance():
    cfg = load_config()
    return cfg.get("last_balance"), cfg.get("last_balance_ts")


def save_settings(**kwargs):
    cfg = load_config()
    cfg.update(kwargs)
    _save_config(cfg)
    return cfg


# ---------------- BET HISTORY ----------------
def load_bets_log():
    if not os.path.exists(BETS_LOG):
        return []
    try:
        with open(BETS_LOG) as f:
            return json.load(f)
    except Exception:
        return []


def save_bets_log(log):
    tmp = BETS_LOG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(log, f, indent=2)
    os.replace(tmp, BETS_LOG)


def log_bet(bet):
    log = load_bets_log()
    log.append(bet)
    save_bets_log(log)


def get_daily_bet_count():
    today = datetime.now().strftime("%Y-%m-%d")
    log = load_bets_log()
    return sum(1 for b in log if b.get("placed_at", "").startswith(today))


# ---------------- CONDITIONS ----------------
def check_conditions(prediction, config=None):
    cfg = config or load_config()
    over25 = prediction.get("over25_pct", 0)
    btts = prediction.get("btts_pct", 0)
    exp_goals = prediction.get("expected_goals", 0)
    score = prediction.get("most_likely_score", "0-0")

    try:
        h, a = score.split("-")
        score_total = int(h) + int(a)
    except Exception:
        score_total = 0

    reasons = []
    ok = True

    if over25 < cfg["min_over25_pct"]:
        ok = False
        reasons.append(f"Over 2.5 {over25}% < {cfg['min_over25_pct']}%")
    if exp_goals < cfg["min_expected_goals"]:
        ok = False
        reasons.append(f"Expected goals {exp_goals} < {cfg['min_expected_goals']}")
    if btts < cfg["min_btts_pct"]:
        ok = False
        reasons.append(f"BTTS {btts}% < {cfg['min_btts_pct']}%")
    if score_total < cfg["min_score_total"]:
        ok = False
        reasons.append(f"Score {score} total {score_total} < {cfg['min_score_total']}")

    return ok, reasons


def scan_for_qualified_bets(md_num=None, json_path="accuracy_data.json"):
    if not os.path.exists(json_path):
        return []
    with open(json_path) as f:
        data = json.load(f)

    if md_num is None:
        mds = [k for k in data if k.isdigit() and data[k].get("predictions")]
        if not mds:
            return []
        md_num = max(mds, key=int)

    preds = data.get(str(md_num), {}).get("predictions", [])
    qualified = []
    for p in preds:
        ok, _ = check_conditions(p)
        if ok:
            qualified.append({"prediction": p, "matchday": md_num})
    return qualified


# ---------------- BETPAWA CLIENT ----------------
class BetPawaClient:
    """
    BetPawa client using session cookies (x-pawa-token) for auth.
    """

    BASE = "https://www.betpawa.co.tz"
    AUTH_ENDPOINT = "/api/user/v3/authenticate"
    BALANCE_ENDPOINT = "/api/ledger/v2/funds/balance/list"

    def __init__(self):
        self.user_uuid = None
        self.phone = None
        self.logged_in = False
        self.session = None
        self.pawa_token = None

    def _headers(self):
        return {
            "accept": "*/*",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "x-pawa-brand": "betpawa-tanzania",
            "x-pawa-language": "en",
            "devicetype": "web",
            "origin": self.BASE,
            "referer": self.BASE + "/login",
        }

    def login(self, phone, password):
        """Authenticate. Returns True on success."""
        import requests

        # Normalize phone: 0712345678 → 712345678
        phone = str(phone).strip()
        if phone.startswith("+255"):
            phone = phone[4:]
        elif phone.startswith("255"):
            phone = phone[3:]
        elif phone.startswith("0"):
            phone = phone[1:]

        if not self.session:
            self.session = requests.Session()

        url = self.BASE + self.AUTH_ENDPOINT
        payload = {
            "username": phone,
            "password": password,
            "rememberMe": False,
        }

        try:
            r = self.session.post(url, json=payload,
                                  headers=self._headers(), timeout=15)
            print(f"Login status: {r.status_code}")

            if r.status_code == 200:
                j = r.json()
                self.user_uuid = j.get("userUuid")
                if self.user_uuid:
                    self.logged_in = True
                    self.phone = phone
                    # Capture session token from cookie
                    self.pawa_token = self.session.cookies.get("x-pawa-token")
                    token_preview = self.pawa_token[:20] if self.pawa_token else "NONE"
                    print(f"✅ Login OK — uuid={self.user_uuid[:8]}... token={token_preview}...")
                    return True
                print("⚠️ Login 200 but no userUuid in response")
                return False
            elif r.status_code in (401, 403):
                print("❌ Wrong username or password")
                return False
            else:
                print(f"❌ Login HTTP {r.status_code}: {r.text[:200]}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False

    def get_balance(self):
        """Get current TZS balance. Returns float or None."""
        if not self.logged_in:
            return None

        url = f"{self.BASE}{self.BALANCE_ENDPOINT}"
        params = {"uuid": self.user_uuid}

        try:
            r = self.session.post(url, params=params, headers=self._headers(),
                                  json={}, timeout=10)
            if r.status_code == 200:
                j = r.json()
                # Response: [{"balance": 20.004, "currency": "TZS"}]
                if isinstance(j, list) and j:
                    item = j[0]
                    for key in ("balance", "amount", "available"):
                        if key in item:
                            return float(item[key])
                elif isinstance(j, dict):
                    for key in ("balance", "amount", "available"):
                        if key in j:
                            return float(j[key])
                print(f"⚠️ Unexpected balance structure: {j}")
                return None
            print(f"⚠️ Balance HTTP {r.status_code}: {r.text[:200]}")
            return None
        except Exception as e:
            print(f"❌ Balance error: {e}")
            return None

    def place_bet(self, selection_id, odds, stake_tzs, bet_type="SINGLE"):
        """
        Place a bet on BetPawa virtuals.

        Args:
            selection_id: the unique selection ID for Over 2.5 (from odds API)
            odds: current price (float)
            stake_tzs: stake amount in TZS
            bet_type: "SINGLE" (default)

        Returns:
            dict: {"success": bool, "response": ..., "error": ...}
        """
        if not self.logged_in:
            return {"success": False, "error": "Not logged in"}

        import uuid
        endpoint = self.BASE + "/api/betslip/validator/v2/place-bet/virtual"

        payload = {
            "stake": int(stake_tzs),
            "stakeType": "STAKE",
            "currency": "TZS",
            "calculatorVersion": "V10",
            "legs": [{
                "selectionIds": [str(selection_id)],
                "price": float(odds),
                "type": bet_type,
            }],
            "bonus": {
                "configurationId": "6a2bb7ba748eb4e9e34d1aec",
                "calculatorVersion": "V10",
            },
            "configurationId": "6a2bb7ba748eb4e9e34d1aec",
            "meta": {
                "requestUuid": str(uuid.uuid4()),   # unique per request
                "cashoutable": False,
                "acceptAnyPrice": False,
            },
        }

        try:
            r = self.session.post(
                endpoint,
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            if r.status_code == 200:
                return {"success": True, "response": r.json()}
            return {
                "success": False,
                "error": f"HTTP {r.status_code}: {r.text[:300]}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}



    def place_virtual_over25(self, selection_id, price, stake_tzs):
        """
        Place an Over 2.5 bet on a virtual match.
        Confirmed from DevTools capture (2026-10-01).

        Args:
            selection_id: e.g. "1559391830" (from events API)
            price: e.g. 2.25 (Over 2.5 odds)
            stake_tzs: e.g. 500

        Returns:
            {"success": True, "betslip_id": "...", "response": {...}}
            OR {"success": False, "error": "..."}
        """
        import uuid as _uuid

        if not self.logged_in:
            return {"success": False, "error": "Not logged in"}

        endpoint = self.BASE + "/api/betslip/validator/v2/place-bet/virtual"

        payload = {
            "stake": int(stake_tzs),
            "stakeType": "STAKE",
            "legs": [{
                "selectionIds": [str(selection_id)],
                "price": float(price),
                "type": "SINGLE",
            }],
            "bonus": {
                "configurationId": "6a2bb7ba748eb4e9e34d1aec",
                "calculatorVersion": "V10",
            },
            "calculatorVersion": "V10",
            "configurationId": "6a2bb7ba748eb4e9e34d1aec",
            "currency": "TZS",
            "meta": {
                "requestUuid": str(_uuid.uuid4()),
                "cashoutable": False,
                "acceptAnyPrice": False,
            },
        }

        headers = self._headers()
        headers["referer"] = self.BASE + "/virtual-sports?virtualTab=upcoming"

        try:
            r = self.session.post(endpoint, json=payload,
                                  headers=headers, timeout=15)
            print(f"Bet placement status: {r.status_code}")

            if r.status_code == 200:
                j = r.json()
                if j.get("placed"):
                    return {
                        "success": True,
                        "betslip_id": j.get("betslipId"),
                        "betslip_uuid": j.get("betslipUuid"),
                        "response": j,
                    }
                return {"success": False,
                        "error": "Not placed (no 'placed:true')",
                        "response": j}
            return {"success": False,
                    "error": f"HTTP {r.status_code}: {r.text[:300]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

        
# ---------------- THE MAIN ACTION ----------------
def attempt_bets(json_path="accuracy_data.json", force_md=None):
    """
    Find qualified bets, place them (or simulate), log everything.
    Returns a list of action dicts.
    """
    cfg = load_config()

    # Daily limit check
    today_count = get_daily_bet_count()
    if today_count >= cfg["daily_limit"]:
        return [{"action": "skipped",
                 "reason": f"Daily limit ({today_count}/{cfg['daily_limit']})"}]

    qualified = scan_for_qualified_bets(md_num=force_md, json_path=json_path)
    if not qualified:
        return [{"action": "none", "reason": "No qualifying predictions"}]

    actions = []
    for item in qualified:
        p = item["prediction"]
        match_str = f"{p['home']} vs {p['away']}"
        bet = {
            "matchday": item["matchday"],
            "match": match_str,
            "over25_pct": p["over25_pct"],
            "btts_pct": p["btts_pct"],
            "expected_goals": p["expected_goals"],
            "most_likely_score": p["most_likely_score"],
            "stake": cfg["max_stake_tzs"],
            "mode": cfg["mode"],
            "placed_at": datetime.now().isoformat(),
        }

        if cfg["mode"] == "simulation":
            bet["result"] = "SIMULATED"
            log_bet(bet)
            actions.append({"action": "simulated", "match": match_str})
        else:
            actions.append({
                "action": "needs_password",
                "match": match_str,
                "hint": "Use attempt_bets_with_pw(phone, password) for live betting"
            })

    return actions



def attempt_bets_with_pw(phone, password,
                         json_path="accuracy_data.json",
                         force_md=None,
                         headless=False):
    """
    Live betting — logs into BetPawa via Selenium and places bets on
    all predictions that meet the conditions.

    Args:
        phone: BetPawa phone number
        password: BetPawa password
        json_path: path to accuracy_data.json
        force_md: override matchday (optional)
        headless: run browser in background (True) or visible (False)

    Returns:
        list of action dicts (one per qualified match)
    """
    cfg = load_config()
    if cfg["mode"] != "live":
        return [{"action": "error",
                 "reason": "Live mode not enabled in Settings"}]

    # Check daily limit
    if get_daily_bet_count() >= cfg["daily_limit"]:
        return [{"action": "skipped",
                 "reason": f"Daily limit reached ({get_daily_bet_count()}/{cfg['daily_limit']})"}]

    # Get qualified bets
    qualified = scan_for_qualified_bets(md_num=force_md, json_path=json_path)
    if not qualified:
        return [{"action": "none", "reason": "No qualifying predictions"}]

    print(f"\n🎯 {len(qualified)} matches qualified for betting")

    # Import Selenium bot
    from utils.selenium_bettor import BetPawaSelenium

    bot = BetPawaSelenium(headless=headless)
    actions = []

    try:
        # ---------- LOGIN ----------
        if not bot.login(phone, password):
            return [{"action": "error", "reason": "Login failed"}]

        # ---------- NAVIGATE TO VIRTUALS ----------
        bot.go_to_virtuals()
        import time as _t
        _t.sleep(5)

        # ---------- PLACE BETS ----------
        stake_per_bet = cfg["max_stake_tzs"]
        placed_count = 0

        for item in qualified:
            p = item["prediction"]
            home = p["home"]
            away = p["away"]
            match_str = f"{home} vs {away}"

            # Stop if daily limit reached
            if get_daily_bet_count() >= cfg["daily_limit"]:
                actions.append({
                    "action": "skipped",
                    "match": match_str,
                    "reason": "Daily limit reached"
                })
                break

            # Map league to UI label
            league_raw = p.get("league", "") or ""
            league_label = _map_league_to_ui_label(league_raw)

            print(f"\n🎰 Placing bet {placed_count + 1}: {match_str}")
            print(f"   League: {league_label}")
            print(f"   Over 2.5: {p.get('over25_pct')}%")
            print(f"   Expected goals: {p.get('expected_goals')}")
            print(f"   BTTS: {p.get('btts_pct')}%")
            print(f"   Score: {p.get('most_likely_score')}")
            print(f"   Stake: {stake_per_bet} TZS")

            result = bot.place_over25_bet(
                home_team=home,
                away_team=away,
                stake_tzs=stake_per_bet,
                league_name=league_label,
                debug=False,
            )

            # Log the bet
            bet = {
                "matchday": item["matchday"],
                "match": match_str,
                "league": league_label,
                "over25_pct": p.get("over25_pct"),
                "btts_pct": p.get("btts_pct"),
                "expected_goals": p.get("expected_goals"),
                "most_likely_score": p.get("most_likely_score"),
                "stake": stake_per_bet,
                "mode": "live-selenium",
                "placed_at": datetime.now().isoformat(),
                "result": "PLACED" if result.get("success") else "FAILED",
                "message": result.get("message", ""),
            }
            log_bet(bet)

            actions.append({
                "action": bet["result"],
                "match": match_str,
                "league": league_label,
                "message": result.get("message", ""),
            })

            if result.get("success"):
                placed_count += 1
                print(f"   ✅ Bet placed successfully")
            else:
                print(f"   ❌ Bet failed: {result.get('message')}")

            # Refresh the page before the next bet (betslip needs reset)
            if placed_count < len(qualified):
                _t.sleep(cfg["cooldown_seconds"])
                bot.go_to_virtuals()
                _t.sleep(4)

    finally:
        try:
            bot.close()
        except Exception:
            pass

    return actions


def _map_league_to_ui_label(league_raw):
    """
    Convert internal league names to BetPawa UI chip labels.
    Examples:
      'BetPawa French'    → 'French League'
      'French League'     → 'French League'
      'English'           → 'English League'
    """
    if not league_raw:
        return None

    s = league_raw.strip()

    # Strip common prefixes
    for prefix in ["BetPawa ", "betpawa ", "Betpawa "]:
        if s.startswith(prefix):
            s = s[len(prefix):]

    # Map short names → full UI labels
    mapping = {
        "English":            "English League",
        "English League":     "English League",
        "Spanish":            "Spanish League",
        "Spanish League":     "Spanish League",
        "Italian":            "Italian League",
        "Italian League":     "Italian League",
        "German":             "German League",
        "German League":      "German League",
        "French":             "French League",
        "French League":      "French League",
        "Dutch":              "Dutch League",
        "Dutch League":       "Dutch League",
        "Portuguese":         "Portuguese League",
        "Portuguese League":  "Portuguese League",
    }

    return mapping.get(s, s if s.endswith("League") else f"{s} League")




def attempt_live_bet_selenium(home_team, away_team, stake_tzs, headless=False):
    """
    Place a live bet using Selenium (browser automation).
    """
    from utils.selenium_bettor import BetPawaSelenium
    from utils.auto_bettor import load_config

    cfg = load_config()
    phone = cfg.get("phone")
    if not phone:
        return {"success": False, "message": "No phone saved in config"}

    # Get password at runtime (from caller)
    # In your UI, pass the password here
    password = cfg.get("_temp_pw")   # caller must set this

    if not password:
        return {"success": False, "message": "Password required for live bet"}

    bot = BetPawaSelenium(headless=headless)
    try:
        if not bot.login(phone, password):
            return {"success": False, "message": "Login failed"}

        bot.go_to_virtuals()
        result = bot.place_over25_bet(home_team, away_team, stake_tzs)

        # Log the bet
        bet = {
            "match": f"{home_team} vs {away_team}",
            "stake": stake_tzs,
            "mode": "live-selenium",
            "placed_at": datetime.now().isoformat(),
            "result": "PLACED" if result["success"] else "FAILED",
            "message": result["message"],
        }
        log_bet(bet)
        return result
    finally:
        bot.close()


# ============================================================
# BEST 3 OVER 2.5 SELECTION (quality-filtered)
# ============================================================
def select_best_three_o25(predictions):
    """
    Pick the top 3 Over 2.5 picks with quality safeguards.
    Filters out garbage, ranks by combined quality score.
    """
    if not predictions:
        return []

    qualified = []
    for p in predictions:
        o25 = p.get("over25_pct", 0)
        xg = p.get("expected_goals", 0)
        btts = p.get("btts_pct", 0)
        agreement_str = p.get("agreement", "0/0")
        try:
            agree = int(agreement_str.split("/")[0])
            total = int(agreement_str.split("/")[1])
            agree_ratio = agree / total if total else 0
        except Exception:
            agree_ratio = 0

        # Quality scoring
        quality = (
            o25 * 0.5 +
            min(xg / 7.0, 1.0) * 100 * 0.25 +
            btts * 0.15 +
            agree_ratio * 100 * 0.10
        )

        # Filters: reject garbage
        if o25 < 55:
            continue
        if xg < 3.0:
            continue
        if agree_ratio < 0.5:
            continue

        qualified.append({**p, "_quality": quality})

    qualified.sort(key=lambda x: x["_quality"], reverse=True)
    return qualified[:3]