"""Feature/label determinacy audit (revision memo S.4 acceptance criteria).

Two things must be checked before any experiment is believed:

1. **No single QUERY feature value may be a synonym for the hidden label.**
   If one were, Active could read the answer off the schema instead of
   designing an experiment.  This is the acceptance criterion.

2. **How much of the label a CONJUNCTION of query features explains.**
   Active may use up to three constraints, so a three-feature conjunction that
   pins the label exactly is scientifically material even though no single
   feature does.  For Family 2 the theorem's own hypotheses are three
   observable conditions, so such a conjunction necessarily exists -- that is
   what makes the boundary learnable in principle, and it must be stated in the
   paper rather than discovered by a reader.

Oracle features are reported separately.  Several of them ARE the label; that is
why they live in the researcher-only namespace and never reach a model.
"""

import argparse
import collections
import itertools
import json
import random
import sys

import _bootstrap  # noqa: F401
from families import all_families

DETERMINISTIC_EPS = 0.02


def collect(family, n: int, seed: int, difficulty: str):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        template = family.base_templates[i % len(family.base_templates)]
        p = family.sample_random(rng, difficulty, template, want_applies=None)
        rows.append((p.query_features, p.oracle_features, p.strategy_applies))
    return rows


def single_feature_table(rows, picker):
    """Per-feature label rates.

    A feature is a LABEL SYNONYM only when it determines the label on BOTH
    sides: every supported value is pure, and both classes are represented.
    A single pure value (e.g. "p = 2 always fails") is a ONE-SIDED implication:
    it is a genuine, observable mathematical fact that the model has to learn,
    not a leak of the answer, and the revision memo prescribes several such
    features as queryable controls.
    """
    counts = collections.defaultdict(lambda: [0, 0])
    for feats, oracle, label in rows:
        for key, value in picker(feats, oracle).items():
            cell = counts[(key, str(value))]
            cell[0] += int(label)
            cell[1] += 1

    by_feature = collections.defaultdict(list)
    for (key, value), (pos, n) in counts.items():
        by_feature[key].append((value, pos, n))

    synonyms = set()
    for key, cells in by_feature.items():
        supported = [(v, pos, n) for v, pos, n in cells if n >= 10]
        if len(supported) < 2:
            continue
        rates = [pos / n for _, pos, n in supported]
        all_pure = all(r <= DETERMINISTIC_EPS or r >= 1 - DETERMINISTIC_EPS for r in rates)
        both_classes = any(r <= DETERMINISTIC_EPS for r in rates) and any(
            r >= 1 - DETERMINISTIC_EPS for r in rates
        )
        if all_pure and both_classes:
            synonyms.add(key)

    out = []
    for (key, value), (pos, n) in sorted(counts.items()):
        rate = pos / n if n else float("nan")
        pure = n >= 10 and (rate <= DETERMINISTIC_EPS or rate >= 1 - DETERMINISTIC_EPS)
        out.append({
            "feature": key, "value": value, "n": n, "p_applies": round(rate, 4),
            "pure_value": pure,
            "label_synonym_feature": key in synonyms,
            "one_sided": pure and key not in synonyms,
        })
    return out


def conjunction_table(rows, max_size=3, min_support=10):
    """Smallest query-feature conjunctions that pin the label on both sides."""
    keys = sorted(rows[0][0]) if rows else []
    found = []
    for size in range(1, max_size + 1):
        for combo in itertools.combinations(keys, size):
            groups = collections.defaultdict(lambda: [0, 0])
            for feats, _oracle, label in rows:
                cell = groups[tuple(str(feats[k]) for k in combo)]
                cell[0] += int(label)
                cell[1] += 1
            supported = [(v, c) for v, c in groups.items() if c[1] >= min_support]
            if not supported:
                continue
            pure = [
                (v, c) for v, c in supported
                if (c[0] / c[1]) <= DETERMINISTIC_EPS or (c[0] / c[1]) >= 1 - DETERMINISTIC_EPS
            ]
            covered = sum(c[1] for _, c in pure)
            total = sum(c[1] for _, c in supported)
            if pure and covered / total >= 0.98:
                found.append({
                    "features": list(combo),
                    "cells": len(supported),
                    "coverage": round(covered / total, 4),
                    "note": "this conjunction determines the label on its support",
                })
        if found:
            break  # report only the smallest determining conjunctions
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--difficulty", default="medium")
    ap.add_argument("--json", help="write the full report to this path")
    args = ap.parse_args()

    report = {}
    violations = 0
    for name, fam in all_families().items():
        rows = collect(fam, args.n, args.seed, args.difficulty)
        query = single_feature_table(rows, lambda q, o: q)
        oracle = single_feature_table(rows, lambda q, o: o)
        conj = conjunction_table(rows)
        report[name] = {"query": query, "oracle": oracle, "conjunctions": conj}

        print(f"\n=== {name} (difficulty={args.difficulty}, n={args.n}) ===")
        print("\n  QUERY features -- shown to Active. None may be a label SYNONYM.")
        print(f"  {'feature':34} {'value':26} {'n':>5} {'P(applies)':>11}  flag")
        for r in query:
            if r["label_synonym_feature"]:
                flag = "LABEL SYNONYM (must move to oracle namespace)"
                violations += 1
            elif r["one_sided"]:
                flag = "one-sided implication (observable, learnable)"
            else:
                flag = ""
            print(f"  {r['feature']:34} {r['value']:26} {r['n']:5d} "
                  f"{r['p_applies']:11.3f}  {flag}")

        print("\n  ORACLE features -- researcher-only, never shown to a model.")
        print(f"  {'feature':34} {'value':26} {'n':>5} {'P(applies)':>11}  flag")
        for r in oracle:
            flag = "= the label" if r["label_synonym_feature"] else (
                "one-sided" if r["one_sided"] else "")
            print(f"  {r['feature']:34} {r['value']:26} {r['n']:5d} "
                  f"{r['p_applies']:11.3f}  {flag}")

        if conj:
            print("\n  Smallest QUERY-feature conjunctions that determine the label:")
            for c in conj:
                print(f"    {' AND '.join(c['features'])}   "
                      f"({c['cells']} cells, {c['coverage']:.0%} coverage)")
        else:
            print("\n  No query-feature conjunction of size <= 3 determines the label.")

    print("\n" + "=" * 78)
    if violations:
        print(f"FAIL: {violations} QUERY feature value(s) belong to a label-synonym "
              f"feature.")
        print("Move that feature to the oracle-only namespace before experimenting.")
    else:
        print("PASS: no query feature is a synonym for the hidden label.")
        print("One-sided implications are listed above: they are observable "
              "mathematical")
        print("facts the model must learn, not leaks, and several are prescribed by "
              "the design.")
    print("Conjunction findings above are NOT failures, but they are scientifically")
    print("material and must be stated in the paper.  # HUMAN_REVIEW_REQUIRED")
    print("=" * 78)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"wrote {args.json}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
