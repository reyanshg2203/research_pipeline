"""Family 2 mathematical checks (spec S.23)."""

import random
import zlib
from fractions import Fraction

import pytest

from families.lte_valuation import (
    LteValuationFamily,
    actual_valuation,
    shortcut_valuation,
    strategy_succeeds,
    v_p,
)



def _seed(*parts) -> int:
    """Process-stable seed: built-in hash() is salted per process."""
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8"))

def naive_v_p(x: int, p: int) -> int:
    """Reference implementation used only in tests."""
    assert x != 0
    x = abs(x)
    k = 0
    while x % p == 0:
        x //= p
        k += 1
    return k


def test_v_p_against_reference_and_divisibility():
    rng = random.Random(0)
    for _ in range(2000):
        x = rng.randint(1, 10 ** 12) * rng.choice([1, -1])
        p = rng.choice([2, 3, 5, 7, 11, 13])
        k = v_p(x, p)
        assert k == naive_v_p(x, p)
        assert abs(x) % (p ** k) == 0
        assert abs(x) % (p ** (k + 1)) != 0


def test_actual_valuation_is_direct_computation():
    rng = random.Random(1)
    for _ in range(400):
        a = rng.randint(2, 60)
        b = rng.randint(2, 60)
        if a == b:
            continue
        n = rng.randint(2, 20)
        p = rng.choice([2, 3, 5, 7, 11])
        assert actual_valuation(a, b, n, p) == naive_v_p(a ** n - b ** n, p)


def test_lte_theorem_holds_where_its_hypotheses_hold():
    """Odd p, p | a-b, p divides neither a nor b: the shortcut must be exact."""
    rng = random.Random(2)
    checked = 0
    for _ in range(3000):
        p = rng.choice([3, 5, 7, 11, 13, 17])
        b = rng.randint(2, 80)
        if b % p == 0:
            continue
        a = b + p * rng.randint(1, 12)
        if a % p == 0 or a == b:
            continue
        n = rng.randint(2, 40)
        assert strategy_succeeds(a, b, n, p) is True, (a, b, n, p)
        assert actual_valuation(a, b, n, p) == v_p(a - b, p) + v_p(n, p)
        checked += 1
    assert checked > 1000


def test_p_equals_two_odd_exponent_is_positive():
    """For ODD a, b and odd n, v_2(a^n - b^n) = v_2(a-b), so the shortcut is exact.

    The oddness of the bases is essential: for a = 108, b = 32, n = 11 the two
    sides are 22 and 2.
    """
    rng = random.Random(3)
    for _ in range(300):
        b = rng.randrange(3, 81, 2)
        a = b + 2 * rng.randint(1, 40)
        n = rng.choice([3, 5, 7, 9, 11, 13])
        assert actual_valuation(a, b, n, 2) == v_p(a - b, 2), (a, b, n)
        assert strategy_succeeds(a, b, n, 2) is True


def test_p_equals_two_even_bases_can_break_the_odd_exponent_identity():
    assert actual_valuation(108, 32, 11, 2) == 22
    assert v_p(108 - 32, 2) == 2
    assert strategy_succeeds(108, 32, 11, 2) is False


def test_p_equals_two_even_exponent_follows_the_full_lte_formula():
    """v_2(a^n - b^n) = v_2(a-b) + v_2(a+b) + v_2(n) - 1 for odd a,b and even n."""
    rng = random.Random(4)
    checked = 0
    for _ in range(600):
        a = rng.randrange(3, 121, 2)
        b = rng.randrange(3, 121, 2)
        if a == b:
            continue
        n = rng.randrange(2, 40, 2)
        expected = v_p(a - b, 2) + v_p(a + b, 2) + v_p(n, 2) - 1
        assert actual_valuation(a, b, n, 2) == expected, (a, b, n)
        # the naive shortcut omits v_2(a+b) - 1, so it is wrong whenever that is non-zero
        assert strategy_succeeds(a, b, n, 2) == (v_p(a + b, 2) - 1 == 0)
        checked += 1
    assert checked > 300


def test_p_dividing_both_bases_breaks_the_shortcut():
    rng = random.Random(5)
    found = 0
    for _ in range(400):
        p = rng.choice([3, 5, 7])
        a, b = p * rng.randint(1, 20), p * rng.randint(1, 20)
        if a == b:
            continue
        n = rng.randint(3, 15)
        actual = actual_valuation(a, b, n, p)
        assert actual >= n * 1
        if not strategy_succeeds(a, b, n, p):
            found += 1
    assert found > 300


def test_oracle_is_exactly_actual_equals_shortcut():
    rng = random.Random(6)
    for _ in range(500):
        a = rng.randint(2, 100)
        b = rng.randint(2, 100)
        if a == b:
            continue
        n = rng.randint(2, 25)
        p = rng.choice([2, 3, 5, 7, 11])
        assert strategy_succeeds(a, b, n, p) == (
            actual_valuation(a, b, n, p) == shortcut_valuation(a, b, n, p)
        )


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
def test_generated_problems_validate(difficulty):
    fam = LteValuationFamily()
    rng = random.Random(_seed(difficulty))
    for template in fam.base_templates + fam.challenge_templates:
        for want in (True, False):
            for _ in range(5):
                p = fam.sample_random(rng, difficulty, template, want_applies=want)
                assert fam.validate_problem(p)
                assert p.strategy_applies is want


def test_prime_type_is_not_a_surrogate_for_the_label():
    """Both labels must occur at both prime types, or the boundary is trivial."""
    fam = LteValuationFamily()
    rng = random.Random(11)
    seen = set()
    for _ in range(120):
        for want in (True, False):
            p = fam.sample_random(rng, "medium", "valuation", want_applies=want)
            seen.add((want, p.features["prime_type"]))
    assert seen == {
        (True, "odd"), (True, "two"), (False, "odd"), (False, "two")
    }, seen
