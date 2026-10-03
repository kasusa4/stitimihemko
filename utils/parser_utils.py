# utils/parser_utils.py
import re
from fuzzywuzzy import process

def correct_team_name(ocr_text, master_list):
    if not ocr_text or len(ocr_text) < 2:
        return ocr_text.upper()
    match, score = process.extractOne(ocr_text.upper(), master_list)
    if score >= 70:
        return match
    return ocr_text.upper()

def parse_results(text, master_teams):
    pattern = r"([A-Z]{2,4})\s*-\s*([A-Z]{2,4})\s*\(\s*(\d)\s*-\s*(\d)\s*\)\s*(\d)\s*-\s*(\d)"
    raw_matches = re.findall(pattern, text)
    results = {}
    for raw_home, raw_away, ht_h, ht_a, ft_h, ft_a in raw_matches:
        home = correct_team_name(raw_home, master_teams)
        away = correct_team_name(raw_away, master_teams)
        results[(home, away)] = {
            "ft": (int(ft_h), int(ft_a)),
            "ht": (int(ht_h), int(ht_a))
        }
    return results

def parse_fixtures(text, master_teams):
    pattern = r"([A-Z]{2,4})\s*-\s*([A-Z]{2,4})"
    raw_fixtures = re.findall(pattern, text)
    fixtures = []
    for raw_home, raw_away in raw_fixtures:
        home = correct_team_name(raw_home, master_teams)
        away = correct_team_name(raw_away, master_teams)
        fixtures.append((home, away))
    return fixtures

def clean_fixtures_from_text(text):
    """
    Remove scores and brackets from both:
    - Horizontal: 'ARS - MCI (2-0)' → 'ARS - MCI'
    - Vertical: 'ARS - MCI' (team line) then '(2-0)' (score line) → keep only team lines
    Also preserves league headers and Matchday lines.
    """
    lines = text.split('\n')
    clean_lines = []
    
    for line in lines:
        original = line
        line = line.strip()
        if not line:
            clean_lines.append('')   # preserve blank lines
            continue
        
        # Keep league headers and matchday lines
        if 'League' in line or 'Matchday' in line:
            clean_lines.append(line)
            continue
        
        # If line is a score line (starts with '(' and contains '-')
        if re.match(r'^\(\s*\d\s*[-–—]\s*\d\s*\)', line):
            # This is a score line – skip it entirely
            continue
        
        # If line looks like a team pair (with or without scores), extract only the pair
        match = re.match(r'^([A-Z]{2,4})\s*[-–—]\s*([A-Z]{2,4})', line)
        if match:
            clean_lines.append(f"{match.group(1)} - {match.group(2)}")
        else:
            # Keep everything else (just in case)
            clean_lines.append(line)
    
    return '\n'.join(clean_lines)

def parse_batch(text, league_names, master_teams_dict):
    lines = text.split('\n')
    lines = [line.strip() for line in lines if line.strip()]
    league_sections = []
    current_league = None
    start_idx = 0
    
    for i, line in enumerate(lines):
        found = None
        for name in league_names:
            if line.lower() == name.lower() or line.lower().startswith(name.lower()):
                found = name
                break
        if found:
            if current_league is not None:
                league_sections.append((current_league, start_idx, i-1))
            current_league = found
            start_idx = i + 1
    if current_league is not None:
        league_sections.append((current_league, start_idx, len(lines)-1))
    
    result = {}
    for league, start, end in league_sections:
        section_text = '\n'.join(lines[start:end+1])
        master_teams = master_teams_dict.get(league, [])
        parsed = parse_results(section_text, master_teams)
        if parsed:
            matches = []
            for (home, away), data in parsed.items():
                matches.append({
                    'home': home,
                    'away': away,
                    'ft_h': data['ft'][0],
                    'ft_a': data['ft'][1],
                    'ht_h': data['ht'][0],
                    'ht_a': data['ht'][1]
                })
            result[league] = matches
    return result

def parse_batch_fixtures(text, league_names, master_teams_dict):
    lines = text.split('\n')
    lines = [line.strip() for line in lines if line.strip()]
    league_sections = []
    current_league = None
    start_idx = 0
    
    for i, line in enumerate(lines):
        found = None
        for name in league_names:
            if line.lower() == name.lower() or line.lower().startswith(name.lower()):
                found = name
                break
        if found:
            if current_league is not None:
                league_sections.append((current_league, start_idx, i-1))
            current_league = found
            start_idx = i + 1
    if current_league is not None:
        league_sections.append((current_league, start_idx, len(lines)-1))
    
    result = {}
    for league, start, end in league_sections:
        section_text = '\n'.join(lines[start:end+1])
        master_teams = master_teams_dict.get(league, [])
        fixtures = parse_fixtures(section_text, master_teams)
        if fixtures:
            result[league] = fixtures
    return result