# utils/betpawa_odds.py
"""Fetch BetPawa virtual odds with selectionIds."""

import requests

BASE = "https://www.betpawa.co.tz"
HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "x-pawa-brand": "betpawa-tanzania",
    "x-pawa-language": "en",
    "devicetype": "web",
    "user-agent": "Mozilla/5.0",
}


def get_market_selection_ids(round_id):
    """
    Fetch all markets for a round and return a dict:
      { "HOME-AWAY": { "OVER_2_5": "1559393598", "BTTS_YES": "..." , ... } }
    """
    # Try the events endpoint first
    url = f"{BASE}/api/sportsbook/virtual/v3/events/list/by-round/{round_id}"
    r = requests.get(url, headers=HEADERS, timeout=10)

    # If this endpoint doesn't include odds, you'll need the odds endpoint
    # Look for one in DevTools — it may look like:
    #   /api/odds/v2/events/{eventId}
    #   /api/markets/v1/rounds/{round_id}/markets
    #
    # The response should contain for each event:
    #   markets: [{ name: "OVER_UNDER", outcomes: [
    #       { name: "Over 2.5", selectionId: "1559393598", odds: 1.34 }
    #   ]}]

    # Parse structure (adjust based on actual response)
    data = r.json()
    result = {}
    for event in data.get("events", []):
        key = f"{event['home']}-{event['away']}"
        markets = {}
        for m in event.get("markets", []):
            for outcome in m.get("outcomes", []):
                markets[outcome["name"]] = outcome["selectionId"]
        result[key] = markets
    return result