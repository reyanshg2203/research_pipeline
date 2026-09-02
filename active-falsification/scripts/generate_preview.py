"""Human-review preview of generated problems (revision memo S.8).

Every displayed problem shows, on the researcher side:
  * the problem text and the exact answer;
  * `strategy_applies` and the reason it holds or fails;
  * the QUERY features (what Active may request);
  * the ORACLE features, in a clearly separate block (never shown to a model);
  * family-specific extras, e.g. the LTE shortcut prediction versus the exact
    valuation, or the fixed point and the transformed recurrence.

This preview is for human review only. Nothing in the pipeline reads it.
"""

import argparse
import json
import random
import sys

import _bootstrap  # noqa: F401
from families import all_families


def show(family, problem, index: int, verbose: bool) -> None:
    label = "APPLIES" if problem.strategy_applies else "DOES_NOT_APPLY"
    print(f"\n  [{index:>2}] strategy_applies = {label}    "
          f"template={problem.template}")
    print(f"       id            : {problem.id}")
    print(f"       problem       : {problem.text}")
    print(f"       exact_answer  : {problem.exact_answer}")
    print(f"       reason        : {problem.applicability_reason}")
    extras = family.preview_extras(problem)
    if extras:
        print("       -- family detail --")
        for key, value in extras.items():
            print(f"       {key:<32}: {value}")
    print("       -- QUERY features (Active may request these) --")
    for key, value in sorted(problem.query_features.items()):
        print(f"       {key:<32}: {value}")
    print("       -- ORACLE features (researcher-only, NEVER shown to a model) --")
    for key, value in sorted(problem.oracle_features.items()):
        print(f"       {key:<32}: {value}")
    if verbose:
        print("       -- latent parameters --")
        print("       " + json.dumps(problem.latent_parameters, default=str))
        if problem.human_solution:
            print(f"       -- worked solution --\n       {problem.human_solution}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=10,
                    help="positive AND negative examples per family")
    ap.add_argument("--difficulty", default="medium",
                    choices=["easy", "medium", "hard"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--challenge", action="store_true",
                    help="use the held-out challenge templates instead")
    ap.add_argument("--seeds", action="store_true",
                    help="preview the seed demonstrations instead of a random draw")
    args = ap.parse_args()

    failures = 0
    for name, fam in all_families().items():
        print("\n" + "=" * 78)
        print(f"FAMILY {name}   (difficulty={args.difficulty})")
        print("=" * 78)
        print("canonical strategy S -- RESEARCHER-ONLY, never shown to a model:")
        print(f"  {fam.strategy_description}")
        print(f"\nActive query schema : "
              f"{json.dumps(fam.query_schema(), indent=2)[:2000]}")
        print(f"Oracle-only features: {sorted(fam.oracle_feature_schema)}")

        if args.seeds:
            print(f"\nSEED DEMONSTRATIONS (all positive, with worked solutions)")
            seeds = fam.generate_seed_candidates(
                random.Random(args.seed), args.n, args.difficulty
            )
            for i, p in enumerate(seeds, 1):
                try:
                    fam.validate_problem(p)
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    print(f"  [{i}] VALIDATION FAILED: {exc}")
                    continue
                show(fam, p, i, True)
            continue

        templates = fam.challenge_templates if args.challenge else fam.base_templates
        print(f"templates           : {templates}")
        rng = random.Random(args.seed)
        for want, header in (
            (True, "POSITIVE -- the intended strategy is applicable"),
            (False, "NEGATIVE -- the intended strategy is NOT applicable"),
        ):
            print(f"\n{'-' * 78}\n{header}\n{'-' * 78}")
            for i in range(args.n):
                template = templates[i % len(templates)]
                p = fam.sample_random(rng, args.difficulty, template, want_applies=want)
                try:
                    fam.validate_problem(p)
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    print(f"  [{i + 1}] VALIDATION FAILED: {exc}")
                    continue
                show(fam, p, i + 1, args.verbose)

    print("\n" + "=" * 78)
    if failures:
        print(f"{failures} problem(s) FAILED independent revalidation")
        return 1
    print("all previewed problems passed independent revalidation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
