# utils/accuracy_tracker_over25.py
"""
Tracks prediction accuracy for Over 2.5 (primary focus) and BTTS (secondary).
Reads accuracy_data.json, compares predictions vs results, and stores stats.
"""

import json
import os
from datetime import datetime
from collections import defaultdict

DATA_FILE = "accuracy_data.json"
STATS_FILE = "accuracy_stats.json"


# ---------------- LOAD HELPERS ----------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def load_stats():
    if not os.path.exists(STATS_FILE):
        return {
            "over25": {"total": 0, "correct": 0, "history": []},
            "btts":   {"total": 0, "correct": 0, "history": []},
            "by_matchday": {},
            "by_confidence": defaultdict(lambda: {"total": 0, "correct": 0}),
        }
    try:
        with open(STATS_FILE) as f:
            stats = json.load(f)
            # Convert by_confidence back to defaultdict
            bc = stats.get("by_confidence", {})
            stats["by_confidence"] = defaultdict(lambda: {"total": 0, "correct": 0}, bc)
            return stats
    except Exception:
        return {
            "over25": {"total": 0, "correct": 0, "history": []},
            "btts":   {"total": 0, "correct": 0, "history": []},
            "by_matchday": {},
            "by_confidence": defaultdict(lambda: {"total": 0, "correct": 0}),
        }


def save_stats(stats):
    """Atomic save, converting defaultdicts to plain dicts."""
    out = dict(stats)
    out["by_confidence"] = dict(out.get("by_confidence", {}))
    tmp = STATS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=2, default=str)
    os.replace(tmp, STATS_FILE)


# ---------------- CORE TRACKING ----------------
def _normalize_pair(home, away):
    """Case-insensitive match key."""
    return (home.strip().upper(), away.strip().upper())


def evaluate_matchday(md_key, md_entry):
    """
    Compare predictions vs results for a single matchday.
    Returns dict with per-MD stats.
    """
    preds = md_entry.get("predictions", [])
    results = md_entry.get("results", [])

    if not preds or not results:
        return None

    # Map results by (home, away)
    result_map = {}
    for r in results:
        key = _normalize_pair(r["home"], r["away"])
        result_map[key] = r

    md_over25_total = 0
    md_over25_correct = 0
    md_btts_total = 0
    md_btts_correct = 0
    detail = []

    for p in preds:
        key = _normalize_pair(p["home"], p["away"])
        r = result_map.get(key)
        if not r:
            continue

        # Predicted Over 2.5 (threshold: >= 55% means we're calling "Over")
        pred_over25 = p.get("over25_pct", 0) >= 55
        actual_over25 = r.get("over25_actual", False)

        # Predicted BTTS (threshold: >= 60%)
        pred_btts = p.get("btts_pct", 0) >= 60
        actual_btts = r.get("btts_actual", False)

        md_over25_total += 1
        if pred_over25 == actual_over25:
            md_over25_correct += 1

        md_btts_total += 1
        if pred_btts == actual_btts:
            md_btts_correct += 1

        detail.append({
            "home": p["home"], "away": p["away"],
            "pred_o25_pct": p.get("over25_pct", 0),
            "pred_o25": pred_over25,
            "actual_o25": actual_over25,
            "correct_o25": pred_over25 == actual_over25,
            "pred_btts_pct": p.get("btts_pct", 0),
            "pred_btts": pred_btts,
            "actual_btts": actual_btts,
            "correct_btts": pred_btts == actual_btts,
            "actual_ft": f"{r['ft_h']}-{r['ft_a']}",
        })

    if md_over25_total == 0:
        return None

    return {
        "matchday": md_key,
        "matches": md_over25_total,
        "over25_accuracy": md_over25_correct / md_over25_total,
        "over25_correct": md_over25_correct,
        "btts_accuracy": md_btts_correct / md_btts_total if md_btts_total else 0,
        "btts_correct": md_btts_correct,
        "detail": detail,
    }


def update_accuracy_stats():
    """
    Scan accuracy_data.json, evaluate every completed matchday,
    update stats file. Idempotent — re-running won't double-count.
    """
    data = load_data()
    stats = load_stats()

    md_keys = sorted([k for k in data.keys() if k.isdigit()], key=int)
    updated = 0

    for md in md_keys:
        # Skip if already evaluated
        if md in stats["by_matchday"]:
            continue

        result = evaluate_matchday(md, data[md])
        if not result:
            continue

        # Update aggregate Over 2.5
        stats["over25"]["total"] += result["over25_correct"] + (
            result["matches"] - result["over25_correct"]
        )
        stats["over25"]["correct"] += result["over25_correct"]
        stats["over25"]["history"].append({
            "matchday": md,
            "accuracy": result["over25_accuracy"],
            "matches": result["matches"],
            "ts": datetime.now().isoformat(),
        })

        # Update aggregate BTTS
        stats["btts"]["total"] += result["matches"]
        stats["btts"]["correct"] += result["btts_correct"]
        stats["btts"]["history"].append({
            "matchday": md,
            "accuracy": result["btts_accuracy"],
            "matches": result["matches"],
            "ts": datetime.now().isoformat(),
        })

        # Per-MD snapshot
        stats["by_matchday"][md] = {
            "matches": result["matches"],
            "over25_accuracy": result["over25_accuracy"],
            "over25_correct": result["over25_correct"],
            "btts_accuracy": result["btts_accuracy"],
            "btts_correct": result["btts_correct"],
        }

        # By confidence bucket (Over 2.5 only — primary focus)
        for d in result["detail"]:
            bucket = min(int(d["pred_o25_pct"] // 10) * 10, 90)
            key = f"{bucket}-{bucket+10}%"
            stats["by_confidence"][key]["total"] += 1
            if d["correct_o25"]:
                stats["by_confidence"][key]["correct"] += 1

        updated += 1

    if updated:
        save_stats(stats)

    return updated


# ---------------- SUMMARY HELPERS ----------------
def get_summary():
    """Return high-level accuracy summary."""
    stats = load_stats()
    o25 = stats["over25"]
    btts = stats["btts"]

    o25_acc = o25["correct"] / o25["total"] if o25["total"] else 0
    btts_acc = btts["correct"] / btts["total"] if btts["total"] else 0

    # Confidence table
    conf_table = []
    for key in sorted(stats["by_confidence"].keys(),
                      key=lambda k: int(k.split("-")[0])):
        v = stats["by_confidence"][key]
        if v["total"] > 0:
            conf_table.append({
                "Bucket": key,
                "Predictions": v["total"],
                "Correct": v["correct"],
                "Accuracy": v["correct"] / v["total"],
            })

    return {
        "over25": {
            "total": o25["total"],
            "correct": o25["correct"],
            "accuracy": o25_acc,
            "history": o25["history"],
        },
        "btts": {
            "total": btts["total"],
            "correct": btts["correct"],
            "accuracy": btts_acc,
            "history": btts["history"],
        },
        "by_matchday": stats["by_matchday"],
        "by_confidence": conf_table,
    }


def get_matchday_detail(md_key):
    """Return detailed per-match breakdown for a matchday."""
    data = load_data()
    if md_key not in data:
        return []
    result = evaluate_matchday(md_key, data[md_key])
    return result["detail"] if result else []


def reset_stats():
    """Delete stats file (forces re-evaluation)."""
    if os.path.exists(STATS_FILE):
        os.remove(STATS_FILE)