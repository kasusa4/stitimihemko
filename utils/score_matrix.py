# utils/score_matrix.py
import math

def build_score_matrix(lam_home, lam_away, max_goals=8):
    """Return a (max_goals+1) x (max_goals+1) matrix of score probabilities."""
    def pois(k, lam):
        return (lam ** k) * math.exp(-lam) / math.factorial(k)

    matrix = [[pois(i, lam_home) * pois(j, lam_away)
               for j in range(max_goals + 1)]
              for i in range(max_goals + 1)]
    return matrix

def summarize_matrix(matrix):
    """Extract O2.5, BTTS, most likely score from a score matrix."""
    n = len(matrix)
    over25 = sum(matrix[i][j] for i in range(n) for j in range(n) if i + j > 2.5)
    btts = sum(matrix[i][j] for i in range(1, n) for j in range(1, n))
    home_win = sum(matrix[i][j] for i in range(n) for j in range(n) if i > j)
    draw = sum(matrix[i][i] for i in range(n))
    away_win = 1 - home_win - draw

    # Most likely score
    best = (0, 0, 0)
    for i in range(n):
        for j in range(n):
            if matrix[i][j] > best[2]:
                best = (i, j, matrix[i][j])

    return {
        "over25": over25,
        "btts": btts,
        "home_win": home_win,
        "draw": draw,
        "away_win": away_win,
        "most_likely_score": f"{best[0]}-{best[1]}",
        "most_likely_prob": best[2],
    }