# utils/apex_utils.py

def get_apex_rating(prob):
    """
    prob: The win probability of the favorite (0 to 1).
    Returns: (Rating string, Hex Color)
    """
    if prob >= 0.72:
        return "S : Elite", "#FFD700"
    elif prob >= 0.62:
        return "A : High", "#00FF00"
    elif prob >= 0.55:
        return "B : Medium", "#1E90FF"
    elif prob >= 0.48:
        return "RISKY : Low Conf", "#FFA500"
    else:
        return "SKIP : Avoid", "#808080"

def generate_summary(predictions, league_name):
    """
    Takes a list of prediction dicts and adds the APEX rating.
    """
    enriched = []
    for pred in predictions:
        home, away = pred["match"]
        home_prob = pred["home_win"]
        away_prob = pred["away_win"]
        
        if home_prob >= away_prob:
            fav_prob = home_prob
            fav_team = home
            pick = "Home Win"
        else:
            fav_prob = away_prob
            fav_team = away
            pick = "Away Win"
        
        rating, color = get_apex_rating(fav_prob)
        variance = home_prob - away_prob
        
        enriched.append({
            "League": league_name,
            "Match": f"{home} vs {away}",
            "Home Win": f"{home_prob*100:.1f}%",
            "Draw": f"{pred['draw']*100:.1f}%",
            "Away Win": f"{away_prob*100:.1f}%",
            "Most Likely": pred["most_likely"],
            "BTTS": f"{pred['btts']*100:.1f}%",
            "O/U 2.5": f"{pred['over25']*100:.1f}%",
            "Var": f"{variance:.2f}",
            "Rating": rating,
            "Top Pick": f"{fav_team} ({pick})",
            "Confidence": fav_prob,
            "Color": color
        })
    return enriched