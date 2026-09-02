"""Family 2 mathematical checks -- theorem-domain applicability.

Revision memo S.2 and S.7: applicability is the LTE theorem's domain, not
numerical coincidence.  A shortcut that happens to return the right number
outside the domain is a NEGATIVE, recorded as an accidental match.
"""

import collections
import random
import zlib

import pytest

from families.lte_valuation import (
    LteValuationFamily,
    accidental_match,
    applicability_reason,
    exact_valuation,
    nonapplicability_reason,
    shortcut_prediction,
    theorem_applicable,
    v_p,
)


def _seed(*parts) -> int:
    """Process-stable seed: built-in hash() is salted per process."""
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8"))


def naive_v_p(x: int, p: int) -> int:
    assert x != 0
    x = abs(x)
    k = 0
    while x % p == 0:
        x //= p
        k += 1
    return k


# --------------------------------------------------------------------------
# exact arithmetic
# --------------------------------------------------------------------------


def test_v_p_against_reference_and_divisibility():
    rng = random.Random(0)
    for _ in range(2000):
        x = rng.randint(1, 10 ** 12) * rng.choice([1, -1])
        p = rng.choice([2, 3, 5, 7, 11, 13])
        k = v_p(x, p)
        assert k == naive_v_p(x, p)
        assert abs(x) % (p ** k) == 0
        assert abs(x) % (p ** (k + 1)) != 0


def test_exact_valuation_is_direct_computation():
    rng = random.Random(1)
    for _ in range(400):
        a, b = rng.randint(2, 60), rng.randint(2, 60)
        if a == b:
            continue
        n = rng.randint(2, 20)
        p = rng.choice([2, 3, 5, 7, 11])
        assert exact_valuation(a, b, n, p) == naive_v_p(a ** n - b ** n, p)


# --------------------------------------------------------------------------
# the applicability oracle  (revision memo S.7)
# --------------------------------------------------------------------------


def test_standard_odd_prime_lte_examples_are_applies():
    """Odd p, p | a-b, p divides neither base -> APPLIES, and shortcut is exact."""
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
        assert theorem_applicable(a, b, n, p) is True, (a, b, n, p)
        # inside the domain the theorem is a theorem: the shortcut must be exact
        assert exact_valuation(a, b, n, p) == shortcut_prediction(a, b, n, p)
        assert accidental_match(a, b, n, p) is False
        checked += 1
    assert checked > 1000


def test_p_equals_two_is_does_not_apply_even_when_the_number_is_right():
    """p = 2 is outside this theorem form, whatever the arithmetic does."""
    rng = random.Random(3)
    lucky = 0
    for _ in range(400):
        b = rng.randrange(3, 81, 2)
        a = b + 2 * rng.randint(1, 40)
        n = rng.choice([3, 5, 7, 9, 11])
        assert theorem_applicable(a, b, n, 2) is False
        assert nonapplicability_reason(a, b, n, 2) == "p_is_two"
        # for odd bases and odd n the shortcut IS numerically right, which is
        # exactly the accidental-match case the memo asks us to log separately
        assert exact_valuation(a, b, n, 2) == v_p(a - b, 2)
        assert accidental_match(a, b, n, 2) is True
        lucky += 1
    assert lucky == 400


def test_p_not_dividing_the_difference_is_does_not_apply_even_on_a_lucky_match():
    """Revision memo S.7: an accidental numerical hit must not count as APPLIES."""
    rng = random.Random(4)
    accidental = 0
    checked = 0
    for _ in range(2000):
        p = rng.choice([3, 5, 7, 11, 13])
        a, b = rng.randint(2, 90), rng.randint(2, 90)
        if a == b or (a - b) % p == 0 or a % p == 0 or b % p == 0:
            continue
        assert theorem_applicable(a, b, n=rng.randint(2, 30), p=p) is False
        n = rng.randint(2, 30)
        assert nonapplicability_reason(a, b, n, p) == "p_does_not_divide_difference"
        if exact_valuation(a, b, n, p) == shortcut_prediction(a, b, n, p):
            assert accidental_match(a, b, n, p) is True
            accidental += 1
        checked += 1
    assert checked > 500
    assert accidental > 100, "expected many accidental matches outside the domain"


def test_p_dividing_a_or_b_is_does_not_apply():
    rng = random.Random(5)
    checked = 0
    for _ in range(600):
        p = rng.choice([3, 5, 7])
        a = p * rng.randint(1, 20)
        b = rng.randint(2, 90)
        if a == b or a < 2:
            continue
        assert theorem_applicable(a, b, rng.randint(2, 20), p) is False
        assert nonapplicability_reason(a, b, 5, p) == "p_divides_a_or_b"
        checked += 1
    assert checked > 300


def test_oracle_is_exactly_the_theorem_domain_not_numerical_equality():
    """The two definitions must genuinely differ, or the revision changed nothing."""
    rng = random.Random(6)
    differ = 0
    for _ in range(2000):
        a, b = rng.randint(2, 100), rng.randint(2, 100)
        if a == b:
            continue
        n = rng.randint(2, 25)
        p = rng.choice([2, 3, 5, 7, 11])
        domain = theorem_applicable(a, b, n, p)
        numeric = exact_valuation(a, b, n, p) == shortcut_prediction(a, b, n, p)
        assert domain == (
            p != 2 and (a - b) % p == 0 and a % p != 0 and b % p != 0
        )
        if domain != numeric:
            assert numeric and not domain          # the theorem never fails inside
            assert accidental_match(a, b, n, p) is True
            differ += 1
    assert differ > 300, "the two definitions barely differ; check the sampler"


def test_accidental_match_is_logged_separately():
    fam = LteValuationFamily()
    rng = random.Random(7)
    seen = collections.Counter()
    for _ in range(200):
        p = fam.sample_random(rng, "medium", "valuation", want_applies=False)
        fam.validate_problem(p)
        seen[p.oracle_features["accidental_match_outside_domain"]] += 1
        assert p.strategy_applies is False
        lp = p.latent_parameters
        assert lp["accidental_match_outside_domain"] == (
            lp["exact_valuation"] == lp["shortcut_prediction"]
        )
    assert seen["yes"] > 20 and seen["no"] > 20, seen


def test_applicability_reason_names_the_failing_hypothesis():
    # p = 2
    assert nonapplicability_reason(9, 5, 3, 2) == "p_is_two"
    assert "not an odd prime" in applicability_reason(9, 5, 3, 2)
    # p odd, divides neither base, does not divide a - b = 4
    assert nonapplicability_reason(7, 3, 4, 5) == "p_does_not_divide_difference"
    assert "does not divide 7 - 3" in applicability_reason(7, 3, 4, 5)
    # p divides a
    assert nonapplicability_reason(15, 4, 3, 5) == "p_divides_a_or_b"
    assert "forbids" in applicability_reason(15, 4, 3, 5)
    # inside the domain: 5 | 17 - 2 = 15, and 5 divides neither base
    assert nonapplicability_reason(17, 2, 3, 5) == "none"
    assert "hypotheses hold" in applicability_reason(17, 2, 3, 5)


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------


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


def test_negatives_span_all_three_failure_reasons():
    """Revision memo S.2: the negative class must not be dominated by p = 2."""
    fam = LteValuationFamily()
    rng = random.Random(8)
    reasons = collections.Counter()
    for _ in range(300):
        p = fam.sample_random(rng, "medium", "valuation", want_applies=False)
        reasons[p.oracle_features["nonapplicability_reason"]] += 1
    assert set(reasons) == {
        "p_is_two", "p_divides_a_or_b", "p_does_not_divide_difference"
    }, reasons
    assert min(reasons.values()) >= 40, reasons


def test_positive_seeds_are_not_dominated_by_valuation_zero():
    """Revision memo S.2/S.7: a spread over exact valuations 1, 2, 3+."""
    fam = LteValuationFamily()
    seeds = fam.generate_seed_candidates(random.Random(9), 6, "medium")
    buckets = collections.Counter(
        p.oracle_features["exact_valuation_bucket"] for p in seeds
    )
    assert all(p.strategy_applies for p in seeds)
    assert buckets["0"] == 0, buckets
    assert len(buckets) >= 3, buckets
    for p in seeds:
        assert int(p.exact_answer) >= 1


def test_challenge_templates_do_not_change_the_boundary():
    """Same (a,b,n,p) must get the same label under every surface form."""
    fam = LteValuationFamily()
    rng = random.Random(10)
    for _ in range(30):
        base = fam.sample_random(rng, "medium", "valuation", want_applies=None)
        lp = base.latent_parameters
        for template in fam.base_templates + fam.challenge_templates:
            other = fam._build(
                rng, lp["a"], lp["b"], lp["n"], lp["p"], "medium", template, 0
            )
            assert other.strategy_applies == base.strategy_applies
            assert other.exact_answer == base.exact_answer
