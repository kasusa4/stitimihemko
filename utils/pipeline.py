# utils/pipeline.py
"""
The async pipeline. Called by the listener when a change is detected.
"""

import json
import os
import asyncio
import functools


def run_predictions_for_md(md_num, json_path):
    """
    Run predictions for a specific matchday and store them.
    This is CPU-heavy so it's called from run_in_executor.
    """
    from utils.automation_engine import _run_predictions_core

    if not os.path.exists(json_path):
        return []

    with open(json_path) as f:
        data = json.load(f)

    key = str(md_num)
    if key not in data or not data[key].get("fixtures"):
        print(f"⚠️ No fixtures for MD {md_num}")
        return []

    fixtures = data[key]["fixtures"]
    training = []
    for md in data:
        if not md.isdigit() or int(md) >= md_num:
            continue
        for r in data[md].get("results", []):
            training.append({
                "home": r["home"], "away": r["away"],
                "ft_h": r["ft_h"], "ft_a": r["ft_a"]
            })

    if len(training) < 50:
        print(f"⚠️ Only {len(training)} training matches (need 50+)")
        return []

    predictions = _run_predictions_core(training, fixtures)

    data[key]["predictions"] = predictions
    tmp = json_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, json_path)

    return predictions