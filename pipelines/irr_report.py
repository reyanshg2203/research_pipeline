#!/usr/bin/env python3
"""
irr_report.py — analyze the calibration ratings.

Reads pipelines/calibration_responses/calibration_responses.csv and prints:
  1. Krippendorff's alpha (ordinal) per dimension  -> the go / no-go number
  2. A disagreement table, sorted worst-first       -> your meeting agenda
  3. Per-rater severity vs the group mean           -> catches a systematically
                                                      harsh or lenient rater
  4. (optional) agreement with the design intent    -> --key calibration_problems.json

Usage:
    python3 pipelines/irr_report.py
    python3 pipelines/irr_report.py --key pipelines/survey_data/calibration_problems.json

No external stats packages required — alpha is computed directly.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CAL_CSV = ROOT / "pipelines" / "calibration_responses" / "calibration_responses.csv"
DIMS = ["geometric_accuracy", "lesson_alignment", "linguistic_clarity"]


# ---------------------------------------------------------- Krippendorff alpha
def krippendorff_alpha_ordinal(units: list[list[int]]) -> float | None:
    """
    units: one list of ratings per item (missing values simply absent).
    Ordinal metric. Returns None if undefined (no variation / too little data).
    """
    values = sorted({v for u in units for v in u})
    if len(values) < 2:
        return None
    idx = {v: i for i, v in enumerate(values)}

    # coincidence matrix
    n = len(values)
    coincidence = [[0.0] * n for _ in range(n)]
    total_pairable = 0
    for u in units:
        m = len(u)
        if m < 2:
            continue
        total_pairable += m
        for a, b in itertools.permutations(u, 2):
            coincidence[idx[a]][idx[b]] += 1.0 / (m - 1)

    if total_pairable < 2:
        return None

    n_c = [sum(row) for row in coincidence]
    n_total = sum(n_c)
    if n_total == 0:
        return None

    # ordinal difference function
    def delta2(i: int, j: int) -> float:
        lo, hi = (i, j) if i <= j else (j, i)
        s = sum(n_c[lo:hi + 1]) - (n_c[lo] + n_c[hi]) / 2.0
        return s ** 2

    d_obs = sum(coincidence[i][j] * delta2(i, j)
                for i in range(n) for j in range(n) if i != j)
    d_exp = sum(n_c[i] * n_c[j] * delta2(i, j)
                for i in range(n) for j in range(n) if i != j) / (n_total - 1)

    if d_exp == 0:
        return None
    return 1.0 - (d_obs / d_exp)


def interpret(a: float | None) -> str:
    if a is None:
        return "undefined (no variation)"
    if a >= 0.80:
        return "reliable — proceed"
    if a >= 0.667:
        return "tentative — reconcile first"
    return "TOO LOW — do not run the main study yet"


# ---------------------------------------------------------- report
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=CAL_CSV)
    ap.add_argument("--key", type=Path, default=None,
                    help="calibration_problems.json, to compare against design intent")
    args = ap.parse_args()

    if not args.csv.is_file():
        raise SystemExit(f"No calibration responses at {args.csv}")

    df = pd.read_csv(args.csv)
    raters = sorted(df["evaluator_name"].unique())
    items = sorted(df["item_id"].unique())
    print(f"{len(raters)} raters x {len(items)} items\n"
          f"raters: {', '.join(raters)}\n")

    # ---- 1. alpha per dimension
    print("=" * 74)
    print("1. INTER-RATER RELIABILITY  (Krippendorff's alpha, ordinal)")
    print("=" * 74)
    for dim in DIMS:
        units = []
        for item in items:
            vals = df.loc[df["item_id"] == item, dim].dropna().astype(int).tolist()
            if len(vals) >= 2:
                units.append(vals)
        a = krippendorff_alpha_ordinal(units)
        shown = f"{a:.3f}" if a is not None else "  n/a"
        print(f"  {dim:<22} alpha = {shown}   {interpret(a)}")
    print("\n  Thresholds: >=0.80 reliable | 0.667-0.80 tentative | <0.667 unusable\n")

    # ---- 2. disagreement table
    print("=" * 74)
    print("2. DISAGREEMENT  (max pairwise gap; discuss anything >= 2)")
    print("=" * 74)
    rows = []
    for item in items:
        sub = df[df["item_id"] == item]
        for dim in DIMS:
            vals = sub[dim].dropna().astype(int).tolist()
            if len(vals) >= 2:
                rows.append({"item": item, "dimension": dim,
                             "scores": vals, "spread": max(vals) - min(vals)})
    dis = pd.DataFrame(rows).sort_values("spread", ascending=False)
    flagged = dis[dis["spread"] >= 2]
    if flagged.empty:
        print("  No gaps >= 2. Strong agreement.\n")
    else:
        for _, r in flagged.iterrows():
            print(f"  {r['item']:<10} {r['dimension']:<22} "
                  f"scores={r['scores']}  spread={r['spread']}")
        print(f"\n  {len(flagged)} item-dimension(s) need discussion.\n")

    # ---- 3. per-rater severity
    print("=" * 74)
    print("3. RATER SEVERITY  (mean deviation from the group mean per item)")
    print("=" * 74)
    for dim in DIMS:
        print(f"\n  {dim}")
        item_means = df.groupby("item_id")[dim].mean()
        for r in raters:
            sub = df[df["evaluator_name"] == r]
            devs = [row[dim] - item_means[row["item_id"]] for _, row in sub.iterrows()]
            bias = sum(devs) / len(devs) if devs else 0.0
            tag = "harsher" if bias < -0.3 else ("more lenient" if bias > 0.3 else "aligned")
            print(f"    {r:<20} {bias:+.2f}  {tag}")
    print("\n  |bias| > 0.3 suggests a systematic offset worth discussing.\n")

    # ---- 4. optional: vs design intent
    if args.key and args.key.is_file():
        key = json.loads(args.key.read_text(encoding="utf-8"))
        exp = {p["item_id"]: p["expected"] for p in key["problems"]}
        print("=" * 74)
        print("4. VS DESIGN INTENT  (researcher key — a guide, not ground truth)")
        print("=" * 74)
        for item in items:
            if item not in exp:
                continue
            sub = df[df["item_id"] == item]
            parts = []
            for dim in DIMS:
                got = sub[dim].mean()
                want = exp[item][dim]
                mark = "!" if abs(got - want) >= 1.5 else " "
                parts.append(f"{dim.split('_')[0][:4]}: {got:.1f} vs {want}{mark}")
            print(f"  {item:<10} " + "   ".join(parts))
        print("\n  '!' = group mean differs from design intent by >= 1.5. "
              "That is a signal about the rubric OR about the item — not proof a rater is wrong.\n")


if __name__ == "__main__":
    main()
