"""Print generated problems for manual inspection (spec S.27.B).

Shows positive and negative examples per family, with the researcher-side
oracle metadata alongside, so an author can check the mathematics by hand.
"""

import argparse
import json
import random
import sys

import _bootstrap  # noqa: F401
from families import all_families


def show(problem, index: int, verbose: bool) -> None:
    label = "APPLIES" if problem.strategy_applies else "DOES_NOT_APPLY"
    print(f"\n  [{index}] {label}   template={problem.template}  id={problem.id}")
    print(f"      {problem.text}")
    print(f"      exact answer : {problem.exact_answer}")
    feats = ", ".join(f"{k}={v}" for k, v in sorted(problem.features.items()))
    print(f"      features     : {feats}")
    if verbose:
        print("      latent       : " + json.dumps(problem.latent_parameters, default=str))
        if problem.human_solution:
            print(f"      solution     : {problem.human_solution}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=5,
                    help="positive AND negative examples per family")
    ap.add_argument("--difficulty", default="medium",
                    choices=["easy", "medium", "hard"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--verbose", action="store_true",
                    help="also print latent parameters and worked solutions")
    ap.add_argument("--challenge", action="store_true",
                    help="use the held-out challenge templates instead")
    args = ap.parse_args()

    failures = 0
    for name, fam in all_families().items():
        templates = fam.challenge_templates if args.challenge else fam.base_templates
        print("\n" + "=" * 78)
        print(f"FAMILY {name}   (difficulty={args.difficulty}, templates={templates})")
        print("=" * 78)
        print(f"canonical strategy S (RESEARCHER-ONLY, never shown to a model):")
        print(f"  {fam.strategy_description}")
        rng = random.Random(args.seed)
        for want, header in ((True, "POSITIVE -- the intended strategy succeeds"),
                             (False, "NEGATIVE -- the intended strategy fails")):
            print(f"\n{header}")
            for i in range(args.n):
                template = templates[i % len(templates)]
                p = fam.sample_random(rng, args.difficulty, template, want_applies=want)
                try:
                    fam.validate_problem(p)
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    print(f"  [{i + 1}] VALIDATION FAILED: {exc}")
                    continue
                show(p, i + 1, args.verbose)
    print("\n" + "=" * 78)
    if failures:
        print(f"{failures} problem(s) FAILED validation")
        return 1
    print("all previewed problems passed independent revalidation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
