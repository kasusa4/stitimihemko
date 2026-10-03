# utils/apex_utils.py

def get_apex_rating(prob):
    if prob >= 0.72:
        return "S : Elite", "#FFD700"
    elif prob >= 0.62:
        return "A : High", "#00FF88"
    elif prob >= 0.55:
        return "B : Medium", "#4FC3F7"
    elif prob >= 0.48:
        return "RISKY : Low Conf", "#FFA726"
    else:
        return "SKIP : Avoid", "#808080"

def generate_summary(predictions, league_name):
    enriched = []
    for pred in predictions:
        home, away = pred["match"]
        home_prob = pred["home_win"]
        away_prob = pred["away_win"]
        draw_prob = pred["draw"]
        
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
        
        # Build the row
        row = {
            "League": league_name,
            "Match": f"{home} vs {away}",
            "Home Win": f"{home_prob*100:.1f}%",
            "Draw": f"{draw_prob*100:.1f}%",
            "Away Win": f"{away_prob*100:.1f}%",
            "Most Likely": pred.get("most_likely", "N/A"),
            "BTTS": f"{pred.get('btts', 0)*100:.1f}%",
            "O/U 2.5": f"{pred.get('over25', 0)*100:.1f}%",
            "Var": f"{variance:.2f}",
            "Rating": rating,
            "Top Pick": f"{fav_team} ({pick})",
            "Confidence": fav_prob,
            "Color": color
        }
        
        # Add correct scores if available
        if "correct_scores" in pred:
            row["Top Scores"] = " | ".join(pred["correct_scores"][:3])
        
        # Add trend info if available
        if "home_trend" in pred:
            row["H Trend"] = "⬆️" if pred["home_trend"] == "up" else "⬇️" if pred["home_trend"] == "down" else "➡️" if pred["home_trend"] == "stable" else "❓"
        if "away_trend" in pred:
            row["A Trend"] = "⬆️" if pred["away_trend"] == "up" else "⬇️" if pred["away_trend"] == "down" else "➡️" if pred["away_trend"] == "stable" else "❓"
        
        # Add leaky warning if available
        if "leaky_warning" in pred and pred["leaky_warning"]:
            row["⚠️ Warning"] = pred["leaky_warning"][:80] + "..." if len(pred["leaky_warning"]) > 80 else pred["leaky_warning"]
        
        # Add boost info
        if "over25_boost" in pred:
            row["⚡ O2.5 Boost"] = f"+{pred['over25_boost']*100:.0f}%"
        
        enriched.append(row)
    
    return enriched