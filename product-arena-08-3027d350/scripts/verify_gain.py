#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recompute the v3 acceptance rule from the actual metrics artifact."""
import json
import os
import sys


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    metrics_path = os.path.join(os.path.dirname(here), "execution", "results", "metrics.json")
    with open(metrics_path, encoding="utf-8") as handle:
        metrics = json.load(handle)
    continuity = metrics["column_continuity"]
    skill_continuity = continuity["skill_column_continuity"]
    naive_continuity = continuity["naive_column_continuity"]
    skill_concordance = metrics["controlled_ground_truth"]["reading_order_concordance"]
    naive_concordance = metrics["naive_baseline_order_concordance"]
    base_ok = (skill_continuity > naive_continuity and skill_concordance >= naive_concordance
               and skill_concordance >= 0.99)
    advanced_ok = metrics["advanced_controlled_checks"]["all_passed"]
    integration_ok = metrics["memory_and_workflow"]["all_passed"]
    anchors_ok = all(item["reading_anchor_coverage"] == 1.0 and not item["reading_anchor_errors"]
                     for item in metrics["verification"].values() if isinstance(item, dict))
    accepted = base_ok and advanced_ok and integration_ok and anchors_ok and all(metrics["acceptance"].values())
    print(json.dumps({
        "score": 1.0 if accepted else 0.0,
        "base_gain_ok": base_ok, "advanced_ok": advanced_ok,
        "integration_ok": integration_ok, "anchors_ok": anchors_ok,
        "skill_column_continuity": skill_continuity, "naive_column_continuity": naive_continuity,
        "skill_concordance": skill_concordance, "naive_concordance": naive_concordance,
    }))
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
