"""Family 1 mathematical checks (spec S.23).

The oracle is brute-forced against direct modular exponentiation; nothing here
trusts the closed-form shortcut it is testing.
"""

import collections
import random
import zlib
from math import gcd

import pytest
from sympy import factorint, n_order, reduced_totient

from families.order_minus_one import (
    OrderMinusOneFamily,
    count_minus_one_upto,
    scan_least_minus_one,
    strategy_succeeds,
    two_adic,
)



def _seed(*parts) -> int:
    """Process-stable seed: built-in hash() is salted per process."""
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8"))

def brute_force_least(a: int, m: int):
    """Independent brute force over one full cycle of a^n mod m."""
    limit = int(reduced_totient(m)) + 128
    x = 1 % m
    for n in range(1, limit + 1):
        x = (x * a) % m
        if x == m - 1:
            return n
    return None


def test_oracle_matches_brute_force_over_all_small_coprime_pairs():
    checked = 0
    for m in range(3, 200):
        for a in range(2, m):
            if gcd(a, m) != 1:
                continue
            expected = brute_force_least(a, m)
            assert strategy_succeeds(a, m) == (expected is not None), (a, m)
            assert scan_least_minus_one(a, m) == expected, (a, m)
            checked += 1
    assert checked > 10000


def test_sympy_order_agrees_with_brute_force_order():
    rng = random.Random(0)
    for _ in range(300):
        m = rng.randint(3, 500)
        a = rng.randint(2, m - 1)
        if gcd(a, m) != 1:
            continue
        d = int(n_order(a, m))
        x = 1 % m
        found = None
        for n in range(1, d + 2):
            x = (x * a) % m
            if x == 1:
                found = n
                break
        assert found == d, (a, m, d, found)


def test_least_exponent_is_half_the_order_when_the_strategy_applies():
    rng = random.Random(1)
    hits = 0
    for _ in range(4000):
        m = rng.randint(3, 3000)
        a = rng.randint(2, m - 1)
        if gcd(a, m) != 1 or not strategy_succeeds(a, m):
            continue
        d = int(n_order(a, m))
        assert scan_least_minus_one(a, m) == d // 2, (a, m)
        hits += 1
    assert hits > 200


def test_non_coprime_bases_never_solve_the_congruence():
    for m in range(3, 260):
        for a in range(2, m):
            if gcd(a, m) == 1:
                continue
            assert strategy_succeeds(a, m) is False
            assert scan_least_minus_one(a, m) is None, (a, m)


def test_two_adic_alignment_criterion_for_cyclic_components():
    """For odd prime-power components, success <=> all v_2(local order) agree."""
    rng = random.Random(2)
    checked = 0
    for _ in range(4000):
        m = rng.randint(3, 4000)
        comps = [q ** e for q, e in factorint(m).items()]
        if any(q % 2 == 0 for q in comps):
            continue  # (Z/2^k)* is not cyclic for k >= 3; criterion does not apply
        a = rng.randint(2, m - 1)
        if gcd(a, m) != 1:
            continue
        locals_ = [int(n_order(a % q, q)) for q in comps]
        vs = [two_adic(x) for x in locals_]
        expected = min(vs) >= 1 and len(set(vs)) == 1
        assert strategy_succeeds(a, m) == expected, (a, m, locals_)
        checked += 1
    assert checked > 500


def test_prime_modulus_with_even_order_gives_minus_one_at_half_order():
    """Revision memo S.7: prime + even order -> half-order gives -1 (when it does)."""
    checked = 0
    for m in [11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53]:
        for a in range(2, m):
            d = int(n_order(a, m))
            if d % 2 != 0:
                assert strategy_succeeds(a, m) is False, (a, m)
                continue
            # for a prime modulus the group is cyclic, so the unique element of
            # order 2 is -1: an even order always yields -1 at d/2
            assert pow(a, d // 2, m) == m - 1, (a, m, d)
            assert strategy_succeeds(a, m) is True
            assert scan_least_minus_one(a, m) == d // 2
            checked += 1
    assert checked > 200


def test_composite_modulus_with_even_global_order_can_fail():
    """Revision memo S.7: composite + even global order can still fail."""
    failures = []
    for m in [15, 21, 33, 35, 39, 55, 65, 77, 91, 105, 143]:
        for a in range(2, m):
            if gcd(a, m) != 1:
                continue
            d = int(n_order(a, m))
            if d % 2 == 0 and pow(a, d // 2, m) != m - 1:
                failures.append((a, m))
                assert strategy_succeeds(a, m) is False
                assert scan_least_minus_one(a, m) is None
    assert len(failures) > 50, "expected many even-order composite failures"


def test_composite_modulus_successful_half_order_cases_exist():
    """Revision memo S.7: successful composite cases must exist, for seeding."""
    successes = []
    for m in [15, 21, 33, 35, 39, 55, 65, 77, 85, 91, 115, 143]:
        for a in range(2, m):
            if gcd(a, m) != 1:
                continue
            if strategy_succeeds(a, m):
                successes.append((a, m))
                d = int(n_order(a, m))
                assert scan_least_minus_one(a, m) == d // 2
    assert len(successes) > 50, "expected many successful composite cases"
    assert len({m for _, m in successes}) >= 6


def test_non_coprime_answer_comes_from_independent_enumeration():
    """Revision memo S.1/S.7: "shortcut does not apply" is NOT "no solution".

    The exact answer must be produced by enumeration, never assumed from the
    applicability label.
    """
    for m in range(3, 200):
        for a in range(2, m):
            if gcd(a, m) == 1:
                continue
            assert strategy_succeeds(a, m) is False
            # independent brute force, no order shortcut anywhere in the path
            found = None
            x = 1 % m
            for n in range(1, 4 * m + 200):
                x = (x * a) % m
                if x == m - 1:
                    found = n
                    break
            assert scan_least_minus_one(a, m) == found, (a, m)


def test_applicability_reason_names_the_failing_condition():
    from families.order_minus_one import applicability_reason

    assert "not a unit" in applicability_reason(6, 15)
    assert "is odd" in applicability_reason(2, 7)          # ord_7(2) = 3
    assert "does not produce -1" in applicability_reason(2, 15)  # even order, no -1
    assert "the shortcut returns" in applicability_reason(2, 5)  # ord_5(2)=4, 2^2=4=-1


def test_seed_candidates_are_never_all_prime_moduli():
    """Revision memo S.1: the seeds must not suggest "works iff m is prime".

    Since the redesign, `medium` and `hard` produce only multi-component moduli,
    so at those tiers every seed is composite -- the opposite of the failure
    mode the memo guards against. `easy` admits one- and two-component moduli,
    so a mixed seed set is still reachable there.
    """
    fam = OrderMinusOneFamily()
    for difficulty in ("easy", "medium", "hard"):
        seeds = fam.generate_seed_candidates(random.Random(3), 6, difficulty)
        kinds = collections.Counter(p.query_features["modulus_type"] for p in seeds)
        assert len(seeds) == 6
        assert all(p.strategy_applies for p in seeds)
        assert all(p.human_solution.strip() for p in seeds)
        assert kinds["prime"] < len(seeds), (difficulty, kinds)
        if difficulty in ("medium", "hard"):
            assert kinds["composite"] == 6, (difficulty, kinds)
    easy_kinds = collections.Counter(
        p.query_features["modulus_type"]
        for p in fam.generate_seed_candidates(random.Random(3), 6, "easy")
    )
    assert len(easy_kinds) >= 2, easy_kinds


def test_count_template_matches_arithmetic_progression():
    rng = random.Random(3)
    fam = OrderMinusOneFamily()
    for _ in range(60):
        p = fam.sample_random(rng, "medium", "count_up_to", want_applies=None)
        fam.validate_problem(p)
        a, m = p.latent_parameters["a"], p.latent_parameters["m"]
        L = p.latent_parameters["L"]
        assert int(p.exact_answer) == count_minus_one_upto(a, m, L)
        if p.strategy_applies:
            d = int(n_order(a, m))
            expected = len([n for n in range(1, L + 1) if (n - d // 2) % d == 0])
            assert int(p.exact_answer) == expected


# --------------------------------------------------------------------------
# the structural difficulty design
# --------------------------------------------------------------------------


def test_construction_pins_the_outcome_via_local_2adic_valuations():
    """Equal positive valuations succeed; unequal ones fail. Checked by oracle."""
    from families.order_minus_one import (
        _pick_components, build_instance, order_data,
    )

    rng = random.Random(11)
    positives = negatives = 0
    for _ in range(120):
        for profile, expect in (([2, 2, 2], True), ([1, 2, 2], False),
                                ([3, 3], True), ([1, 3], False)):
            comps = _pick_components(rng, len(profile), profile, 200, 500000)
            if comps is None:
                continue
            built = build_instance(rng, comps, profile)
            if built is None:
                continue
            a, m = built
            info = order_data(a, m)
            local_v2 = [
                two_adic(info["local_orders"][str(q)]) for q in info["components"]
            ]
            assert sorted(local_v2) == sorted(profile), (a, m, local_v2, profile)
            assert strategy_succeeds(a, m) is expect, (a, m, profile)
            assert (scan_least_minus_one(a, m) is not None) is expect
            positives += expect
            negatives += not expect
    assert positives > 50 and negatives > 50


def test_easy_tier_is_mostly_single_component_and_small():
    fam = OrderMinusOneFamily()
    rng = random.Random(12)
    kinds = collections.Counter()
    for _ in range(120):
        p = fam.sample_random(rng, "easy", "least_n_congruence")
        fam.validate_problem(p)
        kinds[p.query_features["number_of_factors"]] += 1
        assert p.query_features["modulus_size"] == "small"
        assert p.latent_parameters["m"] < 200
    assert kinds["1"] > kinds["2"], kinds
    assert kinds["2"] > 0, "easy should occasionally produce two components"


def test_medium_tier_is_exactly_two_prime_power_components():
    fam = OrderMinusOneFamily()
    rng = random.Random(13)
    for _ in range(120):
        p = fam.sample_random(rng, "medium", "least_n_congruence")
        fam.validate_problem(p)
        assert p.query_features["number_of_factors"] == "2"
        assert p.query_features["modulus_type"] == "composite"
        assert p.query_features["modulus_size"] == "medium"
        assert len(p.latent_parameters["components"]) == 2


def test_hard_tier_prefers_three_components_and_is_never_small():
    fam = OrderMinusOneFamily()
    rng = random.Random(14)
    counts = collections.Counter()
    for _ in range(150):
        p = fam.sample_random(rng, "hard", "least_n_congruence")
        fam.validate_problem(p)
        counts[p.query_features["number_of_factors"]] += 1
        assert p.query_features["modulus_size"] in ("medium", "large")
    assert counts["3"] > counts["2"], counts
    assert counts["1"] == 0


def test_hard_produces_both_answer_kinds_not_overwhelmingly_none():
    """The defect being fixed: random multi-component moduli were almost all NONE."""
    fam = OrderMinusOneFamily()
    rng = random.Random(15)
    finite = 0
    total = 200
    for _ in range(total):
        p = fam.sample_random(rng, "hard", "least_n_congruence")
        finite += p.exact_answer != "NONE"
    assert 0.35 * total <= finite <= 0.65 * total, finite


def test_hard_negatives_are_near_boundary_not_trivial():
    """gcd(a,m)=1, global order even, every local order even, still no solution."""
    fam = OrderMinusOneFamily()
    rng = random.Random(16)
    checked = 0
    for _ in range(120):
        p = fam.sample_random(rng, "hard", "least_n_congruence", want_applies=False)
        fam.validate_problem(p)
        assert p.exact_answer == "NONE"
        assert p.query_features["base_coprime"] == "yes"
        assert p.oracle_features["global_order_parity"] == "even"
        assert p.oracle_features["local_order_2adic_pattern"] == "misaligned"
        info = p.latent_parameters
        local_v2 = [two_adic(v) for v in info["local_orders"].values()]
        assert min(local_v2) >= 1, "a local order was odd: that is a trivial failure"
        assert len(set(local_v2)) > 1, "valuations must actually disagree"
        checked += 1
    assert checked == 120


def test_hard_positives_have_aligned_valuations_and_a_finite_answer():
    fam = OrderMinusOneFamily()
    rng = random.Random(17)
    for _ in range(120):
        p = fam.sample_random(rng, "hard", "least_n_congruence", want_applies=True)
        fam.validate_problem(p)
        info = p.latent_parameters
        local_v2 = [two_adic(v) for v in info["local_orders"].values()]
        assert len(set(local_v2)) == 1 and local_v2[0] >= 1, local_v2
        d = info["global_order"]
        assert d % 2 == 0
        a, m = info["a"], info["m"]
        assert pow(a, d // 2, m) == m - 1
        assert p.exact_answer != "NONE"
        assert int(p.exact_answer) == d // 2


def test_calibration_plan_is_half_finite_half_none_and_deterministic():
    fam = OrderMinusOneFamily()
    plan = fam.calibration_plan(10, "hard")
    assert len(plan) == 10
    assert sum(1 for x in plan if x) == 5
    assert plan == fam.calibration_plan(10, "hard")          # deterministic
    assert plan != [True] * 5 + [False] * 5, "the plan must be shuffled"
    # different tiers get different orders, so the shuffle is not a constant
    assert any(
        fam.calibration_plan(10, d) != plan for d in ("easy", "medium")
    )


def test_calibration_slots_deliver_the_requested_answer_kind():
    fam = OrderMinusOneFamily()
    for difficulty in ("easy", "medium", "hard"):
        rng = random.Random(18)
        plan = fam.calibration_plan(10, difficulty)
        produced = []
        for i in range(10):
            p = fam.sample_for_calibration(
                rng, difficulty, "least_n_congruence", i, 10
            )
            fam.validate_problem(p)
            produced.append(p.exact_answer != "NONE")
        assert produced == plan, (difficulty, produced, plan)
        assert sum(produced) == 5


def test_difficulty_is_structural_not_merely_larger_integers():
    """Tiers must differ in component structure, not only in modulus size."""
    fam = OrderMinusOneFamily()
    structure = {}
    for difficulty in ("easy", "medium", "hard"):
        rng = random.Random(19)
        comps = collections.Counter()
        for _ in range(80):
            p = fam.sample_random(rng, difficulty, "least_n_congruence")
            comps[p.query_features["number_of_factors"]] += 1
        structure[difficulty] = comps
    assert structure["easy"].most_common(1)[0][0] == "1"
    assert set(structure["medium"]) == {"2"}
    assert structure["hard"].most_common(1)[0][0] == "3"


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
def test_generated_problems_validate(difficulty):
    fam = OrderMinusOneFamily()
    rng = random.Random(_seed(difficulty))
    for template in fam.base_templates + fam.challenge_templates:
        for want in (True, False):
            for _ in range(6):
                p = fam.sample_random(rng, difficulty, template, want_applies=want)
                assert fam.validate_problem(p)
                assert p.strategy_applies is want


def test_balanced_split_generation():
    fam = OrderMinusOneFamily()
    rng = random.Random(7)
    items = fam.generate_iid_test(rng, 20, "medium", balanced=True)
    pos = sum(1 for p in items if p.strategy_applies)
    assert pos == 10
    assert len({p.content_key() for p in items}) == 20
