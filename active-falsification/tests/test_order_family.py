"""Family 1 mathematical checks (spec S.23).

The oracle is brute-forced against direct modular exponentiation; nothing here
trusts the closed-form shortcut it is testing.
"""

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


def test_composite_even_order_without_minus_one_half_power():
    """The scientifically important negative class: d even but a^(d/2) != -1."""
    found = []
    for m in range(3, 800):
        for a in range(2, min(m, 60)):
            if gcd(a, m) != 1:
                continue
            d = int(n_order(a, m))
            if d % 2 == 0 and pow(a, d // 2, m) != m - 1:
                found.append((a, m))
                assert strategy_succeeds(a, m) is False
                assert scan_least_minus_one(a, m) is None
    assert len(found) > 100, "expected many even-order non-solving cases"


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
