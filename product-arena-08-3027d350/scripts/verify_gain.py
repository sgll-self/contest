#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_gain.py — domain-rule verifier for the 'order_gain_vs_baseline' deviation.

Recomputes a binary physical_consistency score from the actual metrics artifact:
the skill must strictly improve line-level column continuity AND reading-order
concordance over the naive pure-y baseline on the controlled ground-truth document.
Returns 1.0 when the rule holds, else 0.0. Reads only the produced metrics.json.
"""
import json, os, sys

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    metrics_path = os.path.join(os.path.dirname(here), "execution", "results", "metrics.json")
    m = json.load(open(metrics_path, encoding="utf-8"))
    cc = m["column_continuity"]
    skill_cc = cc["skill_column_continuity"]
    naive_cc = cc["naive_column_continuity"]
    skill_conc = m["controlled_ground_truth"]["reading_order_concordance"]
    naive_conc = m["naive_baseline_order_concordance"]
    ok = (skill_cc > naive_cc) and (skill_conc >= naive_conc) and (skill_conc >= 0.99)
    print(json.dumps({"score": 1.0 if ok else 0.0,
                      "skill_column_continuity": skill_cc, "naive_column_continuity": naive_cc,
                      "skill_concordance": skill_conc, "naive_concordance": naive_conc}))
    return 0

if __name__ == "__main__":
    sys.exit(main())