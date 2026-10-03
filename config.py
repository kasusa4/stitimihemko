# config.py

# ---------- LEAGUE IDS ----------
LEAGUES = {
    'English League': 7794,
    'Spanish League': 7795,
    'Italian League': 7796,
    'German League': 9184,
    'French League': 9183,
    'Dutch League': 13774,
    'Portuguese League': 13773
}

# ---------- LEAGUE TEAM CODES (for algorithms) ----------
LEAGUE_TEAMS = {
    'English League': [
        'ARS', 'MCI', 'LIV', 'CHE', 'TOT', 'MUN', 'BHA', 'CRY', 'EVE', 'FUL',
        'LEE', 'NEW', 'NOT', 'SUN', 'WHU', 'WOL', 'BOU', 'BRE', 'BUR', 'AST'
    ],
    'Spanish League': [
        'BAR', 'RMA', 'ATM', 'SEV', 'VAL', 'VIL', 'RSO', 'BET', 'ATH', 'CEL',
        'GET', 'OSA', 'RAY', 'ELC', 'ESP', 'GIR', 'LEV', 'MAL', 'OVI', 'ALA'
    ],
    'Italian League': [
        'JUV', 'MIL', 'INT', 'NAP', 'ROM', 'LAZ', 'FIO', 'ATA', 'BOL', 'TOR',
        'UDI', 'SAS', 'EMP', 'LEC', 'VER', 'CAG', 'GEN', 'CRE', 'SPE', 'SAL'
    ],
    'German League': [
        'BAY', 'BVB', 'RBL', 'UNB', 'FRA', 'WOB', 'MAI', 'GLD', 'SCF', 'KOL',
        'HOF', 'STU', 'AUG', 'BOC', 'HER', 'SCH', 'DRE', 'HEI', 'MON', 'LEV'
    ],
    'French League': [
        'PSG', 'MAR', 'MON', 'LIL', 'REN', 'OL', 'NIC', 'LMO', 'TRO', 'REI',
        'STR', 'CLM', 'AUX', 'TOU', 'LOR', 'ANG', 'BRT', 'HAV', 'MET', 'NAN'
    ],
    'Dutch League': [
        'AJA', 'PSV', 'FEB', 'TWE', 'ALK', 'GAE', 'UTR', 'HEE', 'SPA', 'FOR',
        'NEC', 'VIT', 'RKC', 'GRA', 'VOL', 'EXC', 'EMM', 'DOR', 'GRO', 'AZA'
    ],
    'Portuguese League': [
        'BEN', 'POR', 'SPO', 'BRA', 'VGU', 'FAM', 'CHV', 'BOA', 'CAS', 'PAS',
        'VSC', 'ARU', 'EST', 'RIO', 'MOR', 'FAR', 'GIL', 'VIT', 'GUI', 'TRO'
    ]
}

# ---------- FLAT LIST OF ALL KNOWN TEAMS (for validation) ----------
KNOWN_TEAMS = []
for teams in LEAGUE_TEAMS.values():
    KNOWN_TEAMS.extend(teams)
KNOWN_TEAMS = set(KNOWN_TEAMS)  # unique

# ---------- API ENDPOINTS ----------
API_BASE = "https://www.betpawa.co.tz/api/sportsbook"
SEASONS_URL = f"{API_BASE}/virtual/v2/seasons/list/actual"
EVENTS_URL = f"{API_BASE}/virtual/v3/events/list/by-round/"

# All the round IDs you discovered (for reference / debugging)
ROUND_IDS = [1453744, 1453745, 1453746, 1453747, 1453748, 1453749,
             1453750, 1453751, 1453752, 1453753, 1453754]

# ---------- API HEADERS ----------
HEADERS = {
    'accept': 'application/json',  # Try JSON first
    'accept-language': 'en-US,en;q=0.9',
    'devicetype': 'web',
    'x-pawa-brand': 'betpawa-tanzania',
    'x-pawa-language': 'en',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (Chrome/149.0.0.0)'
}