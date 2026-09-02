"""Feature/label determinacy audit.

Some features in the Active query schema are near-deterministic functions of the
hidden oracle label (`transformed_dynamics` in Family 3 IS the label).  A model
in the Active condition can therefore steer the sampler straight at the
boundary.  That is a legitimate part of active experiment design, but the
authors must SEE how much of the label each feature explains before reading any
Active-vs-Passive result.

This script reports, per family and per feature value, the conditional
probability of `strategy_applies`.  It is diagnostic only; it changes nothing.
"""

import argparse
import collections
import json
import random
import sys

import _bootstrap  # noqa: F401
from families import all_families


def audit(n_per_family: int = 400, seed: int = 0, difficulty: str = "medium"):
    report = {}
    for name, fam in all_families().items():
        rng = random.Random(seed)
        counts = collections.defaultdict(lambda: [0, 0])  # (feature, value) -> [pos, n]
        for i in range(n_per_family):
            template = fam.base_templates[i % len(fam.base_templates)]
            p = fam.sample_random(rng, difficulty, template, want_applies=None)
            for key, value in p.features.items():
                cell = counts[(key, str(value))]
                cell[0] += int(p.strategy_applies)
                cell[1] += 1
        rows = []
        for (key, value), (pos, n) in sorted(counts.items()):
            rate = pos / n if n else float("nan")
            rows.append(
                {
                    "feature": key,
                    "value": value,
                    "n": n,
                    "p_applies": round(rate, 4),
                    "deterministic": n >= 10 and (rate <= 0.02 or rate >= 0.98),
                }
            )
        report[name] = rows
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=400, help="problems sampled per family")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--difficulty", default="medium")
    ap.add_argument("--json", help="write the full report to this path")
    args = ap.parse_args()

    report = audit(args.n, args.seed, args.difficulty)
    flagged = 0
    for family, rows in report.items():
        print(f"\n=== {family} (difficulty={args.difficulty}, n={args.n}) ===")
        print(f"{'feature':32} {'value':32} {'n':>5} {'P(applies)':>11}  flag")
        for r in rows:
            flag = "LABEL-DETERMINING" if r["deterministic"] else ""
            flagged += bool(r["deterministic"])
            print(
                f"{r['feature']:32} {r['value']:32} {r['n']:5d} "
                f"{r['p_applies']:11.3f}  {flag}"
            )
    print(
        f"\n{flagged} feature value(s) are (near-)deterministic for the label.\n"
        "These are legitimate experiment-design handles, but any Active advantage\n"
        "concentrated on them should be discussed explicitly in the paper.\n"
        "# HUMAN_REVIEW_REQUIRED"
    )
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
