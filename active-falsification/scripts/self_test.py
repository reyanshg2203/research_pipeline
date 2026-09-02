"""Mandatory pre-flight check (spec S.23, S.27.A).

Runs, in order:
  1. import + registry checks,
  2. the full mathematical unit-test suite,
  3. a broad generation sweep with independent revalidation of every problem,
  4. the split-disjointness check,
  5. the prompt-leakage sweep,
  6. the feature/label determinacy audit (informational).

Exits non-zero on any failure.  Do NOT run a model until this passes.
"""

import argparse
import os
import random
import subprocess
import sys
import time
import zlib

import _bootstrap  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def check_imports() -> int:
    section("1. imports and registry")
    import prompts  # noqa: F401
    from families import all_families
    from grading import grade  # noqa: F401
    from models import MODEL_REGISTRY

    fams = all_families()
    print(f"  families      : {sorted(fams)}")
    for name, fam in fams.items():
        print(f"    {name:26} version={fam.version_hash()} "
              f"templates={fam.base_templates + fam.challenge_templates}")
    print(f"  model aliases : {sorted(MODEL_REGISTRY)}")
    print(f"  prompt hash   : {prompts.prompts_hash()} (v{prompts.PROMPT_VERSION})")
    return 0


def run_unit_tests() -> int:
    section("2. mathematical unit tests")
    try:
        import pytest  # noqa: F401
    except ImportError:
        print("  [SKIP] pytest is not installed; run `pip install -r requirements.txt`")
        return 1
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", os.path.join(ROOT, "tests"), "-q"],
        cwd=ROOT,
    )
    return proc.returncode


def generation_sweep(n_per_cell: int) -> int:
    section("3. generation sweep with independent revalidation")
    from families import all_families

    failures = 0
    total = 0
    started = time.time()
    for name, fam in all_families().items():
        for difficulty in fam.difficulties:
            for template in fam.base_templates + fam.challenge_templates:
                for want in (True, False):
                    rng = random.Random(zlib.crc32(f"{name}|{difficulty}|{template}|{want}".encode()))
                    for _ in range(n_per_cell):
                        total += 1
                        try:
                            p = fam.sample_random(rng, difficulty, template, want_applies=want)
                            fam.validate_problem(p)
                            if p.strategy_applies is not want:
                                raise ValueError(
                                    f"requested want_applies={want} but got "
                                    f"{p.strategy_applies}"
                                )
                        except Exception as exc:  # noqa: BLE001
                            failures += 1
                            print(f"  FAIL {name}/{difficulty}/{template}/"
                                  f"want={want}: {type(exc).__name__}: {exc}")
        print(f"  {name:26} swept all tiers and templates")
    print(f"  {total} problems generated and revalidated in "
          f"{time.time() - started:.1f}s, {failures} failure(s)")
    return 1 if failures else 0


def split_check() -> int:
    section("4. split disjointness and label balance")
    from families import all_families
    from sampling import assert_disjoint, label_balance

    for name, fam in all_families().items():
        seeds = fam.generate_seed_candidates(random.Random(1), 6, "medium")
        used = {p.content_key() for p in seeds}
        pilot = fam.generate_iid_test(random.Random(2), 10, "medium", exclude=used)
        used |= {p.content_key() for p in pilot}
        iid = fam.generate_iid_test(random.Random(3), 20, "medium", exclude=used)
        used |= {p.content_key() for p in iid}
        ch = fam.generate_challenge_test(random.Random(4), 12, "medium", exclude=used)
        assert_disjoint({"seeds": seeds, "pilot": pilot, "iid": iid, "challenge": ch})
        print(f"  {name:26} iid={label_balance(iid)} challenge={label_balance(ch)}")
    return 0


def leakage_check() -> int:
    section("5. prompt leakage sweep")
    import prompts as P
    from families import all_families

    banned = ["strategy_applies", "latent_parameters", "instance_key"]
    failures = 0
    for name, fam in all_families().items():
        rng = random.Random(5)
        for template in fam.base_templates + fam.challenge_templates:
            for want in (True, False):
                p = fam.sample_random(rng, "medium", template, want_applies=want)
                texts = [
                    P.solve_prompt(p),
                    P.classify_prompt("S_hat", "H", p),
                ]
                for prompt in texts:
                    blob = prompt["system"] + prompt["user"]
                    for token in banned + [fam.strategy_description]:
                        if token and token in blob:
                            failures += 1
                            print(f"  LEAK in {name}/{template}: {token[:60]!r}")
        print(f"  {name:26} solve + classify prompts clean")
    return 1 if failures else 0


def determinacy_audit() -> int:
    section("6. feature/label determinacy audit (informational)")
    from audit_schema import audit

    report = audit(n_per_family=200, seed=0)
    flagged = []
    for family, rows in report.items():
        det = [f"{r['feature']}={r['value']}" for r in rows if r["deterministic"]]
        flagged.extend(f"{family}:{d}" for d in det)
        print(f"  {family:26} {len(det)} label-determining feature value(s)")
    if flagged:
        print("\n  These schema values (near-)determine the hidden label:")
        for f in flagged:
            print(f"    - {f}")
        print("  They are exposed by the spec's default schema. Set "
              "`active_schema_profile: label_decoupled`")
        print("  in the config to remove them.  # HUMAN_REVIEW_REQUIRED")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="fewer generation samples")
    ap.add_argument("--skip-unit-tests", action="store_true")
    args = ap.parse_args()

    rc = 0
    rc |= check_imports()
    if not args.skip_unit_tests:
        rc |= run_unit_tests()
    rc |= generation_sweep(2 if args.quick else 5)
    rc |= split_check()
    rc |= leakage_check()
    rc |= determinacy_audit()

    print("\n" + "=" * 78)
    if rc == 0:
        print("SELF TEST PASSED -- safe to run models")
    else:
        print("SELF TEST FAILED -- do NOT run models until this is fixed")
    print("=" * 78)
    return rc


if __name__ == "__main__":
    sys.exit(main())
