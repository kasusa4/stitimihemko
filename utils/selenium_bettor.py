# utils/selenium_bettor.py
"""
Browser automation for BetPawa virtual betting.
Uses Selenium + human-like timing to place Over 2.5 bets.
"""

import time
import random
# --- Selenium imports made optional ---
try:
    from selenium import webdriver
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False
    # Placeholder - functions will check this flag
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

try:
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_WDM = True
except ImportError:
    HAS_WDM = False


# ============================================================
# HUMAN-LIKE HELPERS
# ============================================================
def _human_delay(min_s=0.6, max_s=2.2):
    """Random pause between actions (like a human reading)."""
    time.sleep(random.uniform(min_s, max_s))


def _human_click(driver, element):
    """Click with slight delay before and after."""
    _human_delay(0.3, 0.8)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    _human_delay(0.4, 1.2)


def _human_scroll_container(driver, container, pixels=400):
    """Scroll inside a container in small human-like steps."""
    if not container:
        return
    steps = random.randint(3, 6)
    per_step = pixels // steps
    for _ in range(steps):
        driver.execute_script(
            f"arguments[0].scrollTop += {per_step};", container
        )
        time.sleep(random.uniform(0.15, 0.35))


# ============================================================
# MAIN CLASS
# ============================================================
class BetPawaSelenium:
    """Automates BetPawa virtual betting via Selenium."""

    BASE = "https://www.betpawa.co.tz"

    def __init__(self, headless=False):
        opts = Options()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1366,768")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)

        if HAS_WDM:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=opts)
        else:
            self.driver = webdriver.Chrome(options=opts)

        # Hide webdriver flag
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
        )
        self.wait = WebDriverWait(self.driver, 20)

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------
    def login(self, phone, password, max_retries=3):
        for attempt in range(1, max_retries + 1):
            print(f"\n🔐 Login attempt {attempt}/{max_retries}")
            try:
                self.driver.get(self.BASE)
                _human_delay(3, 5)

                page = self.driver.page_source.lower()
                if "logout" in page or "my account" in page:
                    print("✅ Already logged in")
                    return True

                self._dismiss_popups()
                self.driver.get(f"{self.BASE}/login")
                _human_delay(4, 6)
                self._dismiss_popups()
                self.driver.execute_script("window.scrollTo(0, 0);")
                _human_delay(0.8, 1.5)

                # Phone input
                phone_input = self._find_input([
                    "input[type='tel']", "input[name='phone']",
                    "input[name='username']", "input[autocomplete='tel']",
                ])
                if not phone_input:
                    print(f"⚠️ Attempt {attempt}: phone input not found")
                    continue

                try:
                    phone_input.click()
                    phone_input.clear()
                    _human_delay(0.3, 0.7)
                    phone_input.send_keys(phone)
                except Exception:
                    self.driver.execute_script(
                        f"arguments[0].value = '{phone}';"
                        "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));",
                        phone_input
                    )
                _human_delay(0.5, 1.2)

                # Password input
                password_input = self._find_input([
                    "input[type='password']", "input[name='password']"
                ])
                if not password_input:
                    print(f"⚠️ Attempt {attempt}: password input not found")
                    continue

                try:
                    password_input.click()
                    password_input.clear()
                    _human_delay(0.3, 0.7)
                    password_input.send_keys(password)
                except Exception:
                    self.driver.execute_script(
                        f"arguments[0].value = '{password}';"
                        "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));",
                        password_input
                    )
                _human_delay(0.6, 1.4)

                # Submit
                submit_btn = None
                for xpath in [
                    "//button[@type='submit']",
                    "//button[contains(., 'Log In')]",
                    "//button[contains(., 'Login')]",
                ]:
                    els = self.driver.find_elements(By.XPATH, xpath)
                    for e in els:
                        if e.is_displayed() and e.is_enabled():
                            submit_btn = e
                            break
                    if submit_btn:
                        break

                if not submit_btn:
                    print(f"⚠️ Attempt {attempt}: submit button not found")
                    continue

                _human_click(self.driver, submit_btn)
                print("⏳ Waiting for login...")
                _human_delay(4, 6)
                self._dismiss_popups()

                url = self.driver.current_url.lower()
                page = self.driver.page_source.lower()
                if "login" not in url and any(k in page for k in ["logout", "balance"]):
                    print("✅ Login successful")
                    return True

                print(f"⚠️ Attempt {attempt}: login not confirmed")
                _human_delay(2, 4)

            except Exception as e:
                print(f"❌ Attempt {attempt} error: {e}")
                _human_delay(2, 3)

        print("❌ All login attempts failed")
        return False

    def _find_input(self, selectors):
        for sel in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for e in els:
                    if e.is_displayed() and e.is_enabled():
                        return e
            except Exception:
                continue
        return None

    def _dismiss_popups(self):
        patterns = [
            "//button[contains(translate(., 'ACCEPT', 'accept'), 'accept')]",
            "//button[contains(translate(., 'AGREE', 'agree'), 'agree')]",
            "//button[contains(translate(., 'OK', 'ok'), 'ok')]",
            "//button[@aria-label='Close']",
        ]
        for xpath in patterns:
            try:
                for e in self.driver.find_elements(By.XPATH, xpath):
                    if e.is_displayed() and e.is_enabled():
                        try:
                            e.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", e)
                        _human_delay(0.4, 0.9)
            except Exception:
                continue

    # --------------------------------------------------------
    # NAVIGATION
    # --------------------------------------------------------
    def go_to_virtuals(self):
        self.driver.get(f"{self.BASE}/virtual-sports?virtualTab=upcoming")
        _human_delay(4, 6)
        # small random scroll (looks human)
        try:
            for _ in range(random.randint(1, 3)):
                self.driver.execute_script(
                    f"window.scrollBy(0, {random.randint(80, 200)});"
                )
                _human_delay(0.3, 0.7)
            self.driver.execute_script("window.scrollTo(0, 0);")
        except Exception:
            pass
        print("📄 Loaded virtuals page")

    # --------------------------------------------------------
    # PLACE OVER 2.5 BET (Human-Like)
    # --------------------------------------------------------
    def place_over25_bet(self, home_team, away_team, stake_tzs,
                         league_name=None, debug=False):
        try:
            _human_delay(1, 2)

            # ---- STEP 1: Click O/U tab ----
            ou_tab = None
            for xpath in [
                "//button[@data-test-id='auto-virtual-upcoming-tab-tabs-tab' and normalize-space(.)='O/U']",
                "//*[@role='tab' and normalize-space(.)='O/U']",
            ]:
                els = self.driver.find_elements(By.XPATH, xpath)
                if els and els[0].is_displayed():
                    ou_tab = els[0]
                    break

            if not ou_tab:
                return {"success": False, "message": "O/U tab not found"}

            print("🎯 Clicking O/U tab...")
            _human_click(self.driver, ou_tab)
            _human_delay(1.5, 2.5)

            # ---- STEP 2: Click league chip ----
            if league_name:
                print(f"🏆 Filtering by: {league_name}")
                league_chip = None
                for xpath in [
                    f"//*[@data-test-id='auto-virtual-league-short-box-chip' and contains(normalize-space(.), '{league_name}')]",
                    f"//button[contains(normalize-space(.), '{league_name}')]",
                ]:
                    els = self.driver.find_elements(By.XPATH, xpath)
                    for e in els:
                        if e.is_displayed() and len(e.text.strip()) < 40:
                            league_chip = e
                            break
                    if league_chip:
                        break

                if league_chip:
                    _human_click(self.driver, league_chip)
                    print(f"✅ Filtered: {league_name}")
                    _human_delay(2, 3)

            # ---- STEP 3: Find match with human-like scroll ----
            match_label = f"{home_team} - {away_team}"
            print(f"🔍 Searching: {match_label}")
            match_el = self._find_match_with_human_scroll(match_label, debug=debug)

            if not match_el:
                return {
                    "success": False,
                    "message": f"Match '{match_label}' not found"
                }

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", match_el
            )
            _human_delay(0.8, 1.5)
            print("✅ Found match")

            # ---- STEP 4: Find match card ----
            match_card = match_el
            for _ in range(8):
                try:
                    parent = match_card.find_element(By.XPATH, "./..")
                    if "Over 2.5" in parent.text:
                        match_card = parent
                        break
                    match_card = parent
                except Exception:
                    break

            # ---- STEP 5: Click Over 2.5 ----
            over_btn = None
            for xpath in [
                ".//button[normalize-space(.)='Over 2.5']",
                ".//button[contains(normalize-space(.), 'Over 2.5')]",
            ]:
                els = match_card.find_elements(By.XPATH, xpath)
                if els:
                    over_btn = els[0]
                    break

            if not over_btn:
                all_btns = match_card.find_elements(By.XPATH, ".//button")
                if len(all_btns) >= 3:
                    over_btn = all_btns[2]

            if not over_btn:
                return {"success": False, "message": "Over 2.5 button not found"}

            print(f"🖱️ Clicking: '{over_btn.text[:40]}'")
            _human_click(self.driver, over_btn)
            _human_delay(2.5, 4)

            # ---- STEP 6: Enter stake ----
            stake_input = None
            for sel in [
                "input[type='number']",
                "input[inputmode='numeric']",
                "input[name='stake']",
                "input[placeholder*='stake' i]",
            ]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for e in els:
                    if e.is_displayed() and e.is_enabled():
                        stake_input = e
                        break
                if stake_input:
                    break

            if not stake_input:
                return {"success": False, "message": "Stake input not found"}

            stake_input.click()
            _human_delay(0.4, 0.9)
            stake_input.clear()
            _human_delay(0.3, 0.7)
            stake_input.send_keys(str(stake_tzs))
            _human_delay(0.8, 1.6)
            print(f"✅ Entered stake: {stake_tzs}")

            # ---- STEP 7: Place Bet ----
            place_btn = None
            for xpath in [
                "//button[contains(., 'Place Bet')]",
                "//button[contains(., 'Place bet')]",
                "//button[contains(., 'PLACE BET')]",
                "//button[contains(., 'Confirm')]",
            ]:
                els = self.driver.find_elements(By.XPATH, xpath)
                for e in els:
                    if e.is_displayed() and e.is_enabled():
                        place_btn = e
                        break
                if place_btn:
                    break

            if not place_btn:
                return {"success": False, "message": "Place Bet button not found"}

            _human_delay(0.6, 1.4)
            print("🖱️ Clicking Place Bet...")
            _human_click(self.driver, place_btn)
            _human_delay(4, 6)

            # ---- STEP 8: Verify ----
            page = self.driver.page_source.lower()
            if any(kw in page for kw in ["bet placed", "success", "accepted", "placed"]):
                return {"success": True, "message": "Bet placed successfully"}

            return {"success": False, "message": "Could not confirm placement"}

        except Exception as e:
            return {"success": False, "message": f"Error: {e}"}

    # --------------------------------------------------------
    # HELPER: find match with human-like scroll
    # --------------------------------------------------------
    def _find_match_with_human_scroll(self, match_label, debug=False, max_scrolls=25):
        # Find the biggest scrollable container
        container_js = """
        var best = null, maxH = 0;
        document.querySelectorAll('div').forEach(function(e){
            var s = getComputedStyle(e);
            if ((s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                e.scrollHeight > e.clientHeight + 100) {
                if (e.scrollHeight > maxH) { maxH = e.scrollHeight; best = e; }
            }
        });
        return best;
        """
        try:
            container = self.driver.execute_script(container_js)
        except Exception:
            container = None

        if debug:
            print(f"   container: {container is not None}")

        last_top = -1
        for i in range(max_scrolls):
            # Try find
            els = self.driver.find_elements(
                By.XPATH, f"//*[normalize-space(text())='{match_label}']"
            )
            if not els:
                for v in [match_label.upper(), match_label.lower()]:
                    els = self.driver.find_elements(
                        By.XPATH, f"//*[normalize-space(text())='{v}']"
                    )
                    if els:
                        break
            if els:
                return els[0]

            # Human-like scroll
            if container:
                new_top = self.driver.execute_script(
                    "arguments[0].scrollTop += %d; return arguments[0].scrollTop;"
                    % random.randint(250, 450),
                    container
                )
            else:
                self.driver.execute_script(
                    "window.scrollBy(0, %d);" % random.randint(250, 450)
                )
                new_top = self.driver.execute_script("return window.pageYOffset;")

            if new_top == last_top:
                # Bottom reached — scroll back to top once
                if i > 0:
                    if container:
                        self.driver.execute_script("arguments[0].scrollTop = 0;", container)
                    else:
                        self.driver.execute_script("window.scrollTo(0,0);")
                    _human_delay(1, 2)
                break
            last_top = new_top
            _human_delay(0.15, 0.35)

        return None

    # --------------------------------------------------------
    # CLOSE
    # --------------------------------------------------------
    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass