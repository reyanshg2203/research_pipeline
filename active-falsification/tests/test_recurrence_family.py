"""Family 3 mathematical checks (spec S.23).

The oracle in the family is a rational-root search plus a symbolic verification.
These tests cross-check it against (a) the closed-form discriminant criterion
for Mobius maps and (b) an independent SymPy substitution, and confirm that the
transformed and visible recurrences agree term by term.
"""

import math
import random
import zlib
from fractions import Fraction

import pytest
from sympy import Poly, Rational, cancel, symbols, together

from families.recurrence_substitution import (
    RecurrenceSubstitutionFamily,
    frac_str,
    has_linearising_shift,
    iterate_terms,
    linearising_shifts,
    normalise,
    poly_eval as poly_eval_local,
    rational_fixed_points,
    strategy_succeeds_on,
    usable_shifts,
)

X, Y = symbols("x y")



def _seed(*parts) -> int:
    """Process-stable seed: built-in hash() is salted per process."""
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8"))

def sympy_linearises(num, den, c):
    """Fully independent SymPy check that y=1/(x-c) gives an affine y-recurrence."""
    cc = Rational(c.numerator, c.denominator)
    xx = cc + 1 / Y
    n = sum(co * xx ** (len(num) - 1 - i) for i, co in enumerate(num))
    d = sum(co * xx ** (len(den) - 1 - i) for i, co in enumerate(den))
    shifted = cancel(cancel(n / d) - cc)
    if shifted == 0:
        return None
    p, q = together(cancel(1 / shifted)).as_numer_denom()
    p, q = cancel(p / q).as_numer_denom()
    pp, pq = Poly(p, Y), Poly(q, Y)
    if pq.degree() != 0 or pp.degree() != 1:
        return None
    a1, a0 = pp.all_coeffs()
    scale = pq.all_coeffs()[0]
    return cancel(a1 / scale), cancel(a0 / scale)


def is_square(n: int) -> bool:
    return n >= 0 and math.isqrt(n) ** 2 == n


def test_mobius_oracle_matches_the_discriminant_criterion():
    """strategy_applies <=> (D-A)^2 + 4CB is a perfect square, for C != 0."""
    rng = random.Random(0)
    checked = 0
    for _ in range(400):
        A, B, C, D = [rng.randint(-9, 9) for _ in range(4)]
        if C == 0 or A * D - B * C == 0:
            continue
        num, den = normalise([A, B], [C, D])
        A2, B2 = num
        C2, D2 = den
        expected = is_square((D2 - A2) ** 2 + 4 * C2 * B2)
        assert has_linearising_shift(num, den) == expected, (num, den)
        checked += 1
    assert checked > 200


def test_only_fixed_points_can_linearise():
    """A shift that is not a fixed point never produces an affine recurrence."""
    rng = random.Random(1)
    checked = 0
    for _ in range(120):
        A, B, C, D = [rng.randint(-6, 6) for _ in range(4)]
        if C == 0 or A * D - B * C == 0:
            continue
        num, den = normalise([A, B], [C, D])
        fps = set(rational_fixed_points(num, den))
        for k in range(-4, 5):
            for q in (1, 2):
                c = Fraction(k, q)
                if c in fps:
                    continue
                assert sympy_linearises(num, den, c) is None, (num, den, c)
                checked += 1
    assert checked > 500


def test_family_oracle_agrees_with_independent_sympy_check():
    """Revision memo S.3 condition 4: verified symbolically, not by a flag."""
    rng = random.Random(2)
    fam = RecurrenceSubstitutionFamily()
    for difficulty in ("easy", "medium", "hard"):
        for want in (True, False):
            for _ in range(12):
                p = fam.sample_random(rng, difficulty, "compute_term", want_applies=want)
                lp = p.latent_parameters
                num, den = lp["num"], lp["den"]
                terms = iterate_terms(num, den, Fraction(lp["x0"]), lp["horizon"])
                independent = any(
                    sympy_linearises(num, den, c) is not None
                    and all(t != c for t in terms)
                    for c in rational_fixed_points(num, den)
                )
                assert independent == p.strategy_applies, (num, den)


def test_positive_instances_transform_to_an_affine_recurrence_and_match_terms():
    """Iterate the visible x-recurrence and the transformed y-recurrence and compare."""
    rng = random.Random(3)
    fam = RecurrenceSubstitutionFamily()
    checked = 0
    for _ in range(60):
        p = fam.sample_random(rng, "medium", "compute_term", want_applies=True)
        lp = p.latent_parameters
        num, den = lp["num"], lp["den"]
        x0 = Fraction(lp["x0"])
        horizon = lp["horizon"]
        shifts = linearising_shifts(num, den)
        assert shifts, (num, den)
        c, r, s = shifts[0]
        xs = iterate_terms(num, den, x0, horizon)
        assert xs is not None
        y = 1 / (x0 - c)
        for k in range(horizon):
            y = r * y + s
            assert xs[k + 1] == c + 1 / y, (num, den, k)
        assert frac_str(xs[horizon]) == p.exact_answer
        checked += 1
    assert checked == 60


def test_oracle_requires_the_substitution_to_be_defined_on_the_trajectory():
    """Revision memo S.3 condition 3.

    x_(n+1) = (2x - 1)/x has fixed point 1 and is linearisable, but a trajectory
    that passes through 1 makes y = 1/(x-1) undefined there, so the strategy is
    not usable on that instance.
    """
    num, den = normalise([2, -1], [1, 0])
    assert has_linearising_shift(num, den) is True
    assert Fraction(1) in rational_fixed_points(num, den)
    # a trajectory that never reaches the fixed point: usable
    assert strategy_succeeds_on(num, den, Fraction(3), 3) is True
    # starting exactly at the fixed point: y is undefined at every index
    assert strategy_succeeds_on(num, den, Fraction(1), 3) is False
    assert usable_shifts(num, den, Fraction(1), 3) == []


def test_every_generated_positive_has_a_usable_shift_on_its_own_trajectory():
    rng = random.Random(21)
    fam = RecurrenceSubstitutionFamily()
    for _ in range(40):
        p = fam.sample_random(rng, "medium", "compute_term", want_applies=True)
        lp = p.latent_parameters
        x0 = Fraction(lp["x0"])
        shifts = usable_shifts(lp["num"], lp["den"], x0, lp["horizon"])
        assert shifts, (lp["num"], lp["den"])
        terms = iterate_terms(lp["num"], lp["den"], x0, lp["horizon"])
        c = shifts[0][0]
        assert all(t != c for t in terms)
        assert p.oracle_features["substitution_defined_on_trajectory"] == "yes"


def test_no_singularity_over_the_requested_horizon_for_valid_positives():
    """Revision memo S.7: positives must be well defined across the horizon."""
    rng = random.Random(22)
    fam = RecurrenceSubstitutionFamily()
    for difficulty in ("easy", "medium", "hard"):
        for _ in range(15):
            p = fam.sample_random(rng, difficulty, "compute_term", want_applies=True)
            lp = p.latent_parameters
            terms = iterate_terms(
                lp["num"], lp["den"], Fraction(lp["x0"]), lp["horizon"]
            )
            assert terms is not None and len(terms) == lp["horizon"] + 1


def test_negative_perturbations_fail_the_symbolic_affine_test():
    """Revision memo S.3: negatives are VERIFIED, never trusted from a flag."""
    rng = random.Random(23)
    fam = RecurrenceSubstitutionFamily()
    for _ in range(40):
        p = fam.sample_random(rng, "medium", "compute_term", want_applies=False)
        lp = p.latent_parameters
        assert lp["perturbation"] is not None, "negatives must be perturbations"
        # independent symbolic re-check, not the stored flag
        for c in rational_fixed_points(lp["num"], lp["den"]):
            assert sympy_linearises(lp["num"], lp["den"], c) is None, lp
        assert lp["symbolic_affine_check"] == "non_affine"


def test_challenge_templates_never_reveal_the_substitution():
    """Revision memo S.3: the removed `transformed_value` template leaked 1/(x-c)."""
    fam = RecurrenceSubstitutionFamily()
    assert "transformed_value" not in fam.challenge_templates
    assert fam.challenge_templates == ["implicit_form", "shifted_index"]
    rng = random.Random(24)
    for template in fam.base_templates + fam.challenge_templates:
        for want in (True, False):
            for _ in range(6):
                p = fam.sample_random(rng, "medium", template, want_applies=want)
                text = p.text
                assert "1/(x" not in text.replace(" ", "")
                assert "y_" not in text
                for c in p.latent_parameters["linearising_shifts"]:
                    assert f"1/(x_{{}} - {c[0]})" not in text
                assert "substitut" not in text.lower()


def test_shifted_index_template_is_the_same_mathematics():
    rng = random.Random(25)
    fam = RecurrenceSubstitutionFamily()
    for _ in range(20):
        p = fam.sample_random(rng, "medium", "shifted_index", want_applies=None)
        lp = p.latent_parameters
        assert lp["index_offset"] == 1
        assert f"x_1 = {lp['x0']}" in p.text
        assert f"Compute x_{lp['horizon'] + 1}" in p.text
        terms = iterate_terms(lp["num"], lp["den"], Fraction(lp["x0"]), lp["horizon"])
        assert p.exact_answer == frac_str(terms[lp["horizon"]])


def test_negative_instances_admit_no_linearising_shift_at_all():
    rng = random.Random(4)
    fam = RecurrenceSubstitutionFamily()
    for _ in range(60):
        p = fam.sample_random(rng, "medium", "compute_term", want_applies=False)
        num, den = p.latent_parameters["num"], p.latent_parameters["den"]
        assert usable_shifts(num, den, Fraction(p.latent_parameters["x0"]),
                             p.latent_parameters["horizon"]) == []
        assert rational_fixed_points(num, den) == [] or all(
            sympy_linearises(num, den, c) is None
            for c in rational_fixed_points(num, den)
        )


def test_irreducible_quadratic_maps_are_never_linearisable():
    """A genuine degree-2 map admits no shift-and-reciprocal linearisation."""
    rng = random.Random(5)
    checked = 0
    for _ in range(200):
        a2 = rng.choice([-3, -2, -1, 1, 2, 3])
        a1, a0 = rng.randint(-8, 8), rng.randint(-8, 8)
        d1, d0 = rng.choice([-5, -3, -1, 1, 3, 5]), rng.randint(-8, 8)
        num, den = normalise([a2, a1, a0], [d1, d0])
        if len(num) != 3:
            continue
        # skip maps whose numerator shares the denominator's root: those cancel
        # to an affine map and are genuinely linearisable
        from families.recurrence_substitution import poly_eval

        if poly_eval(num, Fraction(-den[1], den[0])) == 0:
            continue
        assert has_linearising_shift(num, den) is False, (num, den)
        checked += 1
    assert checked > 100


def test_reducible_quadratic_map_is_correctly_treated_as_affine():
    """(-x^2-3x+4)/(5x-5) reduces to -(x+4)/5, which IS linearisable."""
    num, den = normalise([-1, -3, 4], [5, -5])
    assert poly_eval_local(num, Fraction(1)) == 0 and poly_eval_local(den, Fraction(1)) == 0
    assert has_linearising_shift(num, den) is True


def test_generator_never_emits_a_reducible_quadratic():
    rng = random.Random(15)
    fam = RecurrenceSubstitutionFamily()
    from families.recurrence_substitution import poly_eval

    for _ in range(150):
        p = fam.sample_random(rng, "medium", "compute_term", want_applies=None)
        num, den = p.latent_parameters["num"], p.latent_parameters["den"]
        if len(num) == 3 and den[0] != 0:
            assert poly_eval(num, Fraction(-den[1], den[0])) != 0, (num, den)


def test_undefined_orbits_are_rejected():
    """A denominator that vanishes inside the horizon makes the orbit undefined."""
    # x_{n+1} = 1/(x_n - 2) starting at x_0 = 3 gives x_1 = 1, x_2 = -1, ...
    assert iterate_terms([0, 1], [1, -2], Fraction(3), 3) is not None
    # starting exactly at the pole is undefined at the first step
    assert iterate_terms([0, 1], [1, -2], Fraction(2), 1) is None


def test_generated_problems_never_have_an_undefined_orbit():
    rng = random.Random(6)
    fam = RecurrenceSubstitutionFamily()
    for difficulty in ("easy", "medium", "hard"):
        for template in fam.base_templates + fam.challenge_templates:
            for want in (True, False):
                for _ in range(4):
                    p = fam.sample_random(rng, difficulty, template, want_applies=want)
                    assert fam.validate_problem(p)
                    lp = p.latent_parameters
                    assert (
                        iterate_terms(lp["num"], lp["den"], Fraction(lp["x0"]),
                                      lp["horizon"])
                        is not None
                    )


def test_positive_has_a_verified_rational_fixed_point():
    """Revision memo S.7: the fixed point is exact and re-verifiable."""
    rng = random.Random(26)
    fam = RecurrenceSubstitutionFamily()
    for _ in range(30):
        p = fam.sample_random(rng, "medium", "compute_term", want_applies=True)
        lp = p.latent_parameters
        num, den = lp["num"], lp["den"]
        c = Fraction(lp["usable_shifts"][0][0])
        # f(c) == c, checked directly from the coefficients
        fc = poly_eval_local(num, c) / poly_eval_local(den, c)
        assert fc == c, (num, den, c)
        assert p.oracle_features["has_rational_fixed_point"] == "yes"
        assert p.oracle_features["transformed_dynamics"] == "affine"


def test_rearranged_rendering_preserves_the_same_recurrence():
    """implicit_form must describe exactly the map its coefficients encode."""
    rng = random.Random(7)
    fam = RecurrenceSubstitutionFamily()
    for _ in range(30):
        p = fam.sample_random(rng, "medium", "implicit_form", want_applies=None)
        lp = p.latent_parameters
        num, den = lp["num"], lp["den"]
        xs = iterate_terms(num, den, Fraction(lp["x0"]), lp["horizon"])
        assert xs is not None
        for k in range(lp["horizon"]):
            x, xn = xs[k], xs[k + 1]
            lhs = den[0] * x * xn + den[1] * xn
            rhs = sum(
                co * x ** (len(num) - 1 - i) for i, co in enumerate(num)
            )
            assert lhs == rhs, (num, den, k)


def test_find_index_answer_is_unique_in_the_stated_range():
    rng = random.Random(8)
    fam = RecurrenceSubstitutionFamily()
    for _ in range(25):
        p = fam.sample_random(rng, "medium", "find_index", want_applies=None)
        lp = p.latent_parameters
        lo, hi = lp["index_search_range"]
        xs = iterate_terms(lp["num"], lp["den"], Fraction(lp["x0"]), hi)
        assert xs is not None
        target = xs[lp["horizon"]]
        assert sum(1 for t in xs[lo:] if t == target) == 1
        assert int(p.exact_answer) == lp["horizon"]


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
def test_balanced_splits(difficulty):
    fam = RecurrenceSubstitutionFamily()
    rng = random.Random(_seed(difficulty))
    items = fam.generate_iid_test(rng, 12, difficulty, balanced=True)
    assert sum(1 for p in items if p.strategy_applies) == 6
    assert len({p.content_key() for p in items}) == 12
