"""Family 3 -- rational recurrences linearised by y_n = 1/(x_n - c).

CANONICAL STRATEGY S3

    For x_(n+1) = f(x_n), find a rational fixed point c with f(c) = c, substitute
    y_n = 1/(x_n - c), solve the resulting affine recurrence y_(n+1) = A y_n + B
    in closed form, and invert.

APPLICABILITY ORACLE (revision memo S.3) -- all five conditions, checked:

    1. there is a candidate rational shift c;
    2. c is genuinely a fixed point of f  (exact rational-root search);
    3. y = 1/(x_n - c) is well defined along the whole requested trajectory;
    4. substituting y = 1/(x - c) simplifies EXACTLY to an affine function of y,
       verified symbolically with SymPy, not inferred from a generator flag;
    5. no singularity invalidates the requested horizon.

Why the fixed-point condition is necessary: put y = 1/(x - c), so x = c + 1/y.
As y -> infinity, x -> c and y_(n+1) = 1/(f(x) - c) tends to the finite constant
1/(f(c) - c) unless f(c) = c.  An affine non-constant map is unbounded, so a
linearising shift must be a fixed point.  For a Mobius map the converse also
holds, giving the closed form

    a linearising shift exists  <=>  disc = (D-A)^2 + 4CB is a perfect square,

which tests/test_recurrence_family.py cross-checks against the symbolic oracle.

Negatives are produced by controlled structural perturbations and then
INDEPENDENTLY VERIFIED to admit no linearising shift; a perturbation that
happens to remain linearisable through another rational fixed point is
relabelled a positive rather than trusted as a negative.

# HUMAN_REVIEW_REQUIRED
"""

from __future__ import annotations

import math
import random
import zlib
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

from sympy import Poly, Rational, cancel, symbols, together

from families.base import ProblemFamily, UnsatisfiableConstraints
from schemas import Problem

_X, _Y = symbols("x y")

#: reject instances whose exact terms grow past this magnitude -- keeps answers
#: gradable by a human and by exact string comparison
MAX_TERM_MAGNITUDE = 10 ** 12

HORIZON_BUCKETS = {"small": (3, 4), "medium": (5, 6), "large": (7, 8)}

TIERS: Dict[str, Dict[str, Any]] = {
    "easy": {"horizons": ["small"], "coef": 4},
    "medium": {"horizons": ["small", "medium"], "coef": 6},
    "hard": {"horizons": ["medium", "large"], "coef": 8},
}


def horizon_bucket(n: int) -> str:
    for name, (lo, hi) in HORIZON_BUCKETS.items():
        if lo <= n <= hi:
            return name
    raise ValueError(f"horizon {n} outside all buckets")


# --------------------------------------------------------------------------
# exact rational-map machinery
# --------------------------------------------------------------------------


def normalise(num: List[int], den: List[int]) -> Tuple[List[int], List[int]]:
    """Divide out the common integer content and fix the leading sign.

    Rendering positives and negatives from the same normalised representation
    is what prevents the surface form from leaking the label.
    """
    coeffs = [c for c in list(num) + list(den) if c != 0]
    g = 0
    for c in coeffs:
        g = math.gcd(g, abs(c))
    g = g or 1
    num = [c // g for c in num]
    den = [c // g for c in den]
    lead = next((c for c in den if c != 0), 1)
    if lead < 0:
        num = [-c for c in num]
        den = [-c for c in den]
    return num, den


def poly_eval(coeffs: List[int], x: Fraction) -> Fraction:
    """Horner evaluation of a coefficient list given highest degree first."""
    acc = Fraction(0)
    for c in coeffs:
        acc = acc * x + c
    return acc


def apply_map(num: List[int], den: List[int], x: Fraction) -> Optional[Fraction]:
    d = poly_eval(den, x)
    if d == 0:
        return None
    return poly_eval(num, x) / d


def iterate_terms(
    num: List[int], den: List[int], x0: Fraction, steps: int
) -> Optional[List[Fraction]]:
    """Exact orbit x_0 .. x_steps, or None if undefined / numerically unwieldy."""
    terms = [x0]
    x = x0
    for _ in range(steps):
        nxt = apply_map(num, den, x)
        if nxt is None:
            return None
        if (
            abs(nxt.numerator) > MAX_TERM_MAGNITUDE
            or abs(nxt.denominator) > MAX_TERM_MAGNITUDE
        ):
            return None
        terms.append(nxt)
        x = nxt
    return terms


def rational_fixed_points(num: List[int], den: List[int]) -> List[Fraction]:
    """Rational roots of N(x) - x*D(x) = 0, exactly.

    Uses the rational root theorem on integer coefficients, so no floating
    point and no symbolic solver is involved.
    """
    # build coefficients of N(x) - x*D(x), highest degree first
    deg = max(len(num) - 1, len(den))
    coeffs = [0] * (deg + 1)

    def add(poly: List[int], shift: int, sign: int) -> None:
        d = len(poly) - 1
        for i, c in enumerate(poly):
            power = d - i + shift
            coeffs[deg - power] += sign * c

    add(num, 0, 1)
    add(den, 1, -1)
    while coeffs and coeffs[0] == 0:
        coeffs.pop(0)
    if not coeffs:
        return []  # identity map: every point is fixed; excluded by construction
    if len(coeffs) == 1:
        return []
    g = 0
    for c in coeffs:
        g = math.gcd(g, abs(c))
    if g > 1:
        coeffs = [c // g for c in coeffs]
    lead, const = coeffs[0], coeffs[-1]
    if const == 0:
        roots = {Fraction(0)}
        trimmed = coeffs[:-1]
        roots |= set(_rational_roots(trimmed))
        return sorted(roots)
    return sorted(_rational_roots(coeffs))


def _divisors(n: int) -> List[int]:
    n = abs(n)
    out = []
    i = 1
    while i * i <= n:
        if n % i == 0:
            out.append(i)
            out.append(n // i)
        i += 1
    return sorted(set(out))


def _rational_roots(coeffs: List[int]) -> List[Fraction]:
    while coeffs and coeffs[0] == 0:
        coeffs = coeffs[1:]
    if len(coeffs) <= 1:
        return []
    lead, const = coeffs[0], coeffs[-1]
    if const == 0:
        return sorted(set([Fraction(0)] + _rational_roots(coeffs[:-1])))
    out = []
    for pnum in _divisors(const):
        for q in _divisors(lead):
            for sign in (1, -1):
                cand = Fraction(sign * pnum, q)
                if poly_eval(coeffs, cand) == 0:
                    out.append(cand)
    return sorted(set(out))


def linearising_shifts(
    num: List[int], den: List[int]
) -> List[Tuple[Fraction, Fraction, Fraction]]:
    """All (c, r, s) with y=1/(x-c) turning the map into y_{n+1} = r*y_n + s.

    Candidates are exactly the rational fixed points (necessary condition proved
    in the module docstring); each is then verified symbolically.
    """
    out = []
    for c in rational_fixed_points(num, den):
        res = _verify_shift(num, den, c)
        if res is not None:
            out.append((c, res[0], res[1]))
    return out


def _verify_shift(
    num: List[int], den: List[int], c: Fraction
) -> Optional[Tuple[Fraction, Fraction]]:
    """Symbolic check that y=1/(x-c) gives a non-constant affine y-recurrence."""
    cc = Rational(c.numerator, c.denominator)
    xx = cc + 1 / _Y
    n_expr = sum(co * xx ** (len(num) - 1 - i) for i, co in enumerate(num))
    d_expr = sum(co * xx ** (len(den) - 1 - i) for i, co in enumerate(den))
    fx = cancel(n_expr / d_expr)
    shifted = cancel(fx - cc)
    if shifted == 0:
        return None
    ynext = cancel(1 / shifted)
    p, q = together(ynext).as_numer_denom()
    p, q = cancel(p / q).as_numer_denom()
    try:
        pp, pq = Poly(p, _Y), Poly(q, _Y)
    except Exception:  # pragma: no cover - non-polynomial shapes
        return None
    if pq.degree() != 0 or pp.degree() != 1:
        return None
    scale = pq.all_coeffs()[0]
    a1, a0 = pp.all_coeffs()
    r = cancel(a1 / scale)
    s = cancel(a0 / scale)
    if r == 0:
        return None
    return Fraction(int(Rational(r).p), int(Rational(r).q)), Fraction(
        int(Rational(s).p), int(Rational(s).q)
    )


def has_linearising_shift(num: List[int], den: List[int]) -> bool:
    """Map-level test: does ANY rational shift linearise this map?

    The full applicability oracle is :func:`strategy_succeeds_on`, which also
    requires the substitution to be defined along the requested trajectory.
    """
    return len(linearising_shifts(num, den)) > 0


def frac_str(v: Fraction) -> str:
    return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"


def _term(coef: int, var: str) -> str:
    if coef == 1:
        return var
    if coef == -1:
        return f"-{var}"
    return f"{coef}{var}"


def render_terms(pairs: List[Tuple[int, str]]) -> str:
    """Render sum(coef * symbol) with tidy signs, skipping zero coefficients."""
    parts: List[str] = []
    for coef, sym in pairs:
        if coef == 0:
            continue
        token = sym if abs(coef) == 1 else f"{abs(coef)} {sym}"
        if not parts:
            parts.append(("-" if coef < 0 else "") + token)
        else:
            parts.append(("- " if coef < 0 else "+ ") + token)
    return " ".join(parts) if parts else "0"


def render_linear(coeffs: List[int], var: str) -> str:
    """Render [a, b] as 'a*var + b' with tidy signs; also handles [a2, a1, a0]."""
    deg = len(coeffs) - 1
    parts: List[str] = []
    for i, c in enumerate(coeffs):
        power = deg - i
        if c == 0:
            continue
        if power == 0:
            token = str(abs(c))
        elif power == 1:
            token = _term(abs(c), var)
        else:
            token = _term(abs(c), f"{var}^{power}")
        if not parts:
            parts.append(("-" if c < 0 else "") + token)
        else:
            parts.append(("- " if c < 0 else "+ ") + token)
    return " ".join(parts) if parts else "0"


# --------------------------------------------------------------------------
# instance-level oracle (revision memo S.3, conditions 3 and 5)
# --------------------------------------------------------------------------


def usable_shifts(
    num: List[int], den: List[int], x0: Fraction, horizon: int
) -> List[Tuple[Fraction, Fraction, Fraction]]:
    """Linearising shifts that are also usable on THIS trajectory.

    A shift is usable only when y_n = 1/(x_n - c) is defined at every index the
    problem refers to, i.e. no trajectory point equals c.
    """
    terms = iterate_terms(num, den, x0, horizon)
    if terms is None:
        return []
    out = []
    for c, r, s in linearising_shifts(num, den):
        if any(t == c for t in terms):
            continue
        out.append((c, r, s))
    return out


def strategy_succeeds_on(
    num: List[int], den: List[int], x0: Fraction, horizon: int
) -> bool:
    """The Family 3 applicability oracle, evaluated on a concrete instance."""
    return len(usable_shifts(num, den, x0, horizon)) > 0


def _affine_str(r: Fraction, s: Fraction) -> str:
    """Render 'r*y + s' with a single sign on the constant term."""
    coef = "y" if r == 1 else ("-y" if r == -1 else f"{frac_str(r)}·y")
    if s == 0:
        return coef
    return f"{coef} - {frac_str(-s)}" if s < 0 else f"{coef} + {frac_str(s)}"


def _shift_expr(c: Fraction) -> str:
    """Render (x - c) with a single sign, e.g. '(x + 6)' rather than '(x - -6)'."""
    if c == 0:
        return "x"
    return f"(x + {frac_str(-c)})" if c < 0 else f"(x - {frac_str(c)})"


def _quadratic_str(a: int, b: int, c: int) -> str:
    """Render a c^2 + b c + c0 = 0 with tidy signs."""
    return render_terms([(a, "c^2"), (b, "c"), (c, "")]).replace(" ", " ").strip() + " = 0"


def applicability_reason(
    num: List[int], den: List[int], x0: Fraction, horizon: int
) -> str:
    fps = rational_fixed_points(num, den)
    shifts = linearising_shifts(num, den)
    usable = usable_shifts(num, den, x0, horizon)
    if usable:
        c, r, s = usable[0]
        return (
            f"f has the rational fixed point c = {frac_str(c)}; substituting "
            f"y = 1/{_shift_expr(c)} simplifies the recurrence symbolically to the "
            f"affine recurrence y_(n+1) = {_affine_str(r, s)}, and no "
            f"trajectory point x_0..x_{horizon} equals {frac_str(c)}, so the "
            f"substitution is defined throughout"
        )
    if not fps:
        if len(num) > 2:
            return (
                "the map has a genuine quadratic numerator and no rational fixed "
                "point, so no shift-and-reciprocal substitution linearises it"
            )
        A, B = num
        C, D = den
        disc = (D - A) ** 2 + 4 * C * B
        return (
            f"the fixed-point equation {_quadratic_str(C, D - A, -B)} has discriminant "
            f"{disc}, which is not a perfect square, so f has no rational fixed point "
            f"and no shift-and-reciprocal substitution linearises the recurrence"
        )
    if not shifts:
        return (
            f"f has rational fixed point(s) {[frac_str(c) for c in fps]}, but "
            f"substituting y = 1/(x - c) does not reduce the recurrence to an affine "
            f"function of y"
        )
    blocked = [frac_str(c) for c, _, _ in shifts]
    return (
        f"the only linearising shift(s) {blocked} lie on the trajectory "
        f"x_0..x_{horizon}, so y = 1/(x_n - c) is undefined at some requested index"
    )


def coefficient_size_bucket(num: List[int], den: List[int]) -> str:
    biggest = max(abs(v) for v in num + den)
    if biggest <= 12:
        return "small"
    if biggest <= 60:
        return "medium"
    return "large"


# --------------------------------------------------------------------------
# family
# --------------------------------------------------------------------------


class RecurrenceSubstitutionFamily(ProblemFamily):
    name = "recurrence_substitution"

    strategy_description = (
        "Find a rational fixed point c of the rational map f, substitute "
        "y_n = 1/(x_n - c) to turn the recurrence into an affine recurrence "
        "y_(n+1) = A y_n + B, solve that in closed form, and invert."
    )

    #: Observable controls Active may request.  Every one of these is read
    #: straight off the printed recurrence -- the degree of the numerator, how
    #: big the coefficients are, whether the denominator has a constant term,
    #: whether the two leading coefficients share a sign, how far out the
    #: requested term is, and which task form is asked.
    queryable_features = {
        "numerator_degree": ["linear", "quadratic"],
        "coefficient_size": ["small", "medium", "large"],
        "denominator_constant_zero": ["yes", "no"],
        "leading_coefficients_same_sign": ["yes", "no"],
        "horizon_size": ["small", "medium", "large"],
    }

    #: Researcher-only.  `transformed_dynamics` IS the label, and
    #: `designated_shift_is_fixed_point` is nearly so; both are confined here.
    oracle_feature_schema = {
        "has_rational_fixed_point": ["yes", "no"],
        "designated_shift_is_fixed_point": ["yes", "no"],
        "transformed_dynamics": ["affine", "non_affine"],
        "substitution_defined_on_trajectory": ["yes", "no", "not_applicable"],
        "singularity_risk": ["none_in_horizon", "boundary_case"],
        "perturbation_kind": [
            "none", "numerator_constant", "numerator_slope",
            "denominator_constant", "denominator_slope", "quadratic_term",
        ],
    }

    base_templates = ["compute_term", "find_index"]
    #: Revision memo S.3: the old `transformed_value` template asked for
    #: 1/(x_N - c), which is the latent substitution itself, so it leaked the
    #: strategy.  It is replaced by a changed indexing convention.
    challenge_templates = ["implicit_form", "shifted_index"]

    # ---------------------------------------------------------------- features
    def compute_query_features(
        self, num: List[int], den: List[int], horizon: int, template: str
    ) -> Dict[str, str]:
        return {
            "numerator_degree": "quadratic" if len(num) > 2 else "linear",
            "coefficient_size": coefficient_size_bucket(num, den),
            "denominator_constant_zero": "yes" if den[-1] == 0 else "no",
            "leading_coefficients_same_sign": (
                "yes" if num[0] * den[0] > 0 else "no"
            ),
            "horizon_size": horizon_bucket(horizon),
            "task_form": template,
        }

    def compute_oracle_features(
        self, num: List[int], den: List[int], x0: Fraction, horizon: int,
        c_designated: Fraction, perturbation: Optional[str],
    ) -> Dict[str, str]:
        fps = rational_fixed_points(num, den)
        shifts = linearising_shifts(num, den)
        usable = usable_shifts(num, den, x0, horizon)
        extended = iterate_terms(num, den, x0, horizon + 2)
        if not shifts:
            defined = "not_applicable"
        else:
            defined = "yes" if usable else "no"
        return {
            "has_rational_fixed_point": "yes" if fps else "no",
            "designated_shift_is_fixed_point": (
                "yes" if c_designated in fps else "no"
            ),
            "transformed_dynamics": "affine" if usable else "non_affine",
            "substitution_defined_on_trajectory": defined,
            "singularity_risk": (
                "none_in_horizon" if extended is not None else "boundary_case"
            ),
            "perturbation_kind": perturbation or "none",
        }

    # ------------------------------------------------------------ construction
    def _positive_map(self, rng: random.Random, coef: int) -> Optional[Dict[str, Any]]:
        """Build (A,B,C,D) from a hidden (c, r, s) so that y=1/(x-c) linearises it.

        x_(n+1) = c + (x_n - c) / (r + s*(x_n - c))
                = ((c*s+1) x + c*r - c^2*s - c) / (s x + r - s*c)
        """
        for _ in range(80):
            c = rng.randint(-coef, coef)
            r = rng.choice([1, 2, -1, 3, -2, 2, 3])
            s = rng.choice([k for k in range(-coef, coef + 1) if k != 0])
            A, B, C, D = c * s + 1, c * r - c * c * s - c, s, r - s * c
            if C == 0 or A * D - B * C == 0:
                continue
            num, den = normalise([A, B], [C, D])
            if max(abs(v) for v in num + den) > 40 * coef:
                continue
            return {"num": num, "den": den, "c": c, "r": r, "s": s}
        return None

    def _perturb(
        self, rng: random.Random, base: Dict[str, Any], coef: int
    ) -> Optional[Dict[str, Any]]:
        """Controlled structural perturbation of a positive map.

        Applied to the NORMALISED coefficients so the rendered surface form is
        indistinguishable from a positive.  The caller re-runs the oracle: a
        perturbation that stays linearisable is relabelled, never mislabelled.
        """
        num, den = list(base["num"]), list(base["den"])
        # A quadratic numerator is a perfect predictor of non-applicability, so
        # it is down-weighted; scripts/audit_schema.py reports how much of the
        # label it explains.  # HUMAN_REVIEW_REQUIRED
        kind = rng.choices(
            ["numerator_constant", "numerator_slope", "denominator_constant",
             "denominator_slope", "quadratic_term"],
            weights=[3, 3, 3, 3, 1],
        )[0]
        delta = rng.choice([-3, -2, -1, 1, 2, 3])
        if kind == "numerator_constant":
            num[-1] += delta
        elif kind == "numerator_slope":
            num[-2] += delta
        elif kind == "denominator_constant":
            den[-1] += delta
        elif kind == "denominator_slope":
            den[-2] += delta
        else:
            num = [delta] + num
            # a quadratic numerator sharing the denominator's root cancels to an
            # affine map, which renders as an unreduced fraction; drop those
            if den[0] != 0 and poly_eval(num, Fraction(-den[1], den[0])) == 0:
                return None
        if all(v == 0 for v in den) or all(v == 0 for v in num):
            return None
        num, den = normalise(num, den)
        if len(num) == 2 and len(den) == 2:
            A, B = num
            C, D = den
            if C == 0 or A * D - B * C == 0:
                return None
        if max(abs(v) for v in num + den) > 60 * coef:
            return None
        return {"num": num, "den": den, "c": base["c"], "r": base["r"],
                "s": base["s"], "perturbation": kind}

    def _choose_x0(
        self, rng: random.Random, num: List[int], den: List[int], horizon: int, coef: int
    ) -> Optional[Tuple[Fraction, List[Fraction]]]:
        cands = [Fraction(k) for k in range(-coef, coef + 1)]
        cands += [Fraction(k, 2) for k in range(-2 * coef, 2 * coef + 1) if k % 2]
        rng.shuffle(cands)
        for x0 in cands:
            terms = iterate_terms(num, den, x0, horizon)
            if terms is None:
                continue
            if len(set(terms)) < len(terms):
                continue  # periodic / constant orbits are degenerate
            return x0, terms
        return None

    # ---------------------------------------------------------------- building
    def _build(
        self, rng: random.Random, spec: Dict[str, Any], difficulty: str, template: str,
        horizon: int, x0: Fraction, terms: List[Fraction], seed_value: int,
    ) -> Optional[Problem]:
        num, den = spec["num"], spec["den"]
        c_designated = Fraction(spec["c"])
        usable = usable_shifts(num, den, x0, horizon)
        applies = bool(usable)

        latent: Dict[str, Any] = {
            "num": num, "den": den, "x0": frac_str(x0), "horizon": horizon,
            "c_designated": frac_str(c_designated), "r": spec["r"], "s": spec["s"],
            "perturbation": spec.get("perturbation"),
            "rational_fixed_points": [
                frac_str(c) for c in rational_fixed_points(num, den)
            ],
            "linearising_shifts": [
                [frac_str(c), frac_str(r), frac_str(s)]
                for c, r, s in linearising_shifts(num, den)
            ],
            "usable_shifts": [
                [frac_str(c), frac_str(r), frac_str(s)] for c, r, s in usable
            ],
            "symbolic_affine_check": "affine" if applies else "non_affine",
            "instance_key": f"{num}|{den}|{frac_str(x0)}|{horizon}",
            "terms": [frac_str(t) for t in terms],
        }

        rec = f"x_(n+1) = ({render_linear(num, 'x_n')}) / ({render_linear(den, 'x_n')})"

        if template == "compute_term":
            text = (f"A sequence of rational numbers satisfies x_0 = {frac_str(x0)} and "
                    f"{rec} for all n ≥ 0. Compute x_{horizon}. "
                    f"Give the exact value as an integer or a reduced fraction.")
            answer = frac_str(terms[horizon])
        elif template == "find_index":
            target = terms[horizon]
            lo, hi = 1, max(HORIZON_BUCKETS["large"][1], horizon)
            probe = iterate_terms(num, den, x0, hi)
            if probe is None or sum(1 for t in probe[lo:] if t == target) != 1:
                return None
            text = (f"A sequence of rational numbers satisfies x_0 = {frac_str(x0)} and "
                    f"{rec} for all n ≥ 0. There is exactly one index N with "
                    f"{lo} ≤ N ≤ {hi} for which x_N = {frac_str(target)}. Find N. "
                    f"Answer with a single integer.")
            answer = str(horizon)
            latent["index_search_range"] = [lo, hi]
        elif template == "implicit_form":
            lhs = render_terms([(den[0], "x_n x_(n+1)"), (den[1], "x_(n+1)")])
            text = (f"A sequence of rational numbers satisfies x_0 = {frac_str(x0)} and "
                    f"{lhs} = {render_linear(num, 'x_n')} for all n ≥ 0. "
                    f"Compute x_{horizon}. "
                    f"Give the exact value as an integer or a reduced fraction.")
            answer = frac_str(terms[horizon])
        elif template == "shifted_index":
            # identical mathematics, indices shifted to start at 1
            text = (f"A sequence of rational numbers satisfies x_1 = {frac_str(x0)} and "
                    f"{rec} for all n ≥ 1. Compute x_{horizon + 1}. "
                    f"Give the exact value as an integer or a reduced fraction.")
            answer = frac_str(terms[horizon])
            latent["index_offset"] = 1
        else:
            raise ValueError(f"unknown template {template!r}")

        if len(answer) > 44:
            return None

        return Problem(
            id=f"{self.name}-{template}-"
               f"{zlib.crc32(latent['instance_key'].encode('utf-8')):08x}-{seed_value}",
            family=self.name,
            template=template,
            difficulty=difficulty,
            text=text,
            exact_answer=answer,
            strategy_applies=applies,
            query_features=self.compute_query_features(num, den, horizon, template),
            oracle_features=self.compute_oracle_features(
                num, den, x0, horizon, c_designated, spec.get("perturbation")
            ),
            applicability_reason=applicability_reason(num, den, x0, horizon),
            human_solution=(
                self._write_solution(usable, x0, horizon, terms, answer, template)
                if applies else ""
            ),
            latent_parameters=latent,
            generation_seed=seed_value,
        )

    def _write_solution(
        self, usable: List[Tuple[Fraction, Fraction, Fraction]], x0: Fraction,
        horizon: int, terms: List[Fraction], answer: str, template: str,
    ) -> str:
        c, r, s = usable[0]
        y = 1 / (x0 - c)
        ys = [y]
        for _ in range(horizon):
            ys.append(r * ys[-1] + s)
        if c == 0:
            shift, invert = "x_n", "1/y"
        elif c < 0:
            shift, invert = f"(x_n + {frac_str(-c)})", f"{frac_str(c)} + 1/y"
        else:
            shift, invert = f"(x_n - {frac_str(c)})", f"{frac_str(c)} + 1/y"
        coef = "" if r == 1 else ("-" if r == -1 else f"{frac_str(r)}·")
        tail = "" if s == 0 else (f" - {frac_str(-s)}" if s < 0 else f" + {frac_str(s)}")
        lines = [
            f"Look for a constant fixed by the map: solving f(c) = c gives c = {frac_str(c)}.",
            f"Substitute y_n = 1/{shift}.",
            f"A short computation turns the recurrence into the affine recurrence "
            f"y_(n+1) = {coef}y_n{tail}.",
            f"From the initial term {frac_str(x0)} we get y_0 = {frac_str(ys[0])}.",
            f"Iterating the affine recurrence {horizon} times gives "
            f"y_{horizon} = {frac_str(ys[horizon])}.",
            f"Inverting, {invert}_{horizon} = {frac_str(terms[horizon])}.",
        ]
        if template != "compute_term":
            lines.append(f"The requested quantity is therefore {answer}.")
        return " ".join(lines)

    # ------------------------------------------------------------------- API
    def sample_random(
        self, rng: random.Random, difficulty: str, template: str,
        want_applies: Optional[bool] = None,
    ) -> Problem:
        tier = TIERS[difficulty]
        coef = tier["coef"]
        for _ in range(4000):
            base = self._positive_map(rng, coef)
            if base is None:
                continue
            make_negative = (
                want_applies is False if want_applies is not None else rng.random() < 0.5
            )
            spec = base
            if make_negative:
                spec = self._perturb(rng, base, coef)
                if spec is None:
                    continue
            bucket = rng.choice(tier["horizons"])
            hlo, hhi = HORIZON_BUCKETS[bucket]
            horizon = rng.randint(hlo, hhi)
            chosen = self._choose_x0(rng, spec["num"], spec["den"], horizon, coef)
            if chosen is None:
                continue
            x0, terms = chosen
            problem = self._build(
                rng, spec, difficulty, template, horizon, x0, terms,
                rng.randrange(2 ** 31),
            )
            if problem is None:
                continue
            if want_applies is not None and problem.strategy_applies != want_applies:
                continue
            return problem
        raise RuntimeError(
            f"{self.name}: sample_random exhausted (difficulty={difficulty}, "
            f"want_applies={want_applies})"
        )

    def sample_conditioned(
        self, rng: random.Random, constraints: Dict[str, str], difficulty: str,
        template: str,
    ) -> Optional[Problem]:
        self.check_constraints_wellformed(constraints)
        tier = TIERS[difficulty]
        template = self.requested_template(constraints, template)

        want_h = constraints.get("horizon_size")
        if want_h is not None:
            wanted = {str(v) for v in _listify(want_h)}
            if not wanted & set(tier["horizons"]):
                raise UnsatisfiableConstraints(
                    f"difficulty '{difficulty}' only produces horizon sizes "
                    f"{tier['horizons']}", constraints)

        for _ in range(6000):
            try:
                p = self.sample_random(rng, difficulty, template, None)
            except RuntimeError:
                return None
            if self.matches(p.query_features, constraints):
                return p
        return None

    # ------------------------------------------------------------ seed strata
    def seed_strata(self, n_seeds: int) -> List[Dict[str, str]]:
        """Spread seeds over coefficient size and horizon so the demonstrations
        vary in surface algebra rather than repeating one numeric recurrence."""
        combos = [
            {"coefficient_size": "small"},
            {"coefficient_size": "medium"},
            {"horizon_size": "small"},
            {"horizon_size": "medium"},
            {"denominator_constant_zero": "no"},
            {"leading_coefficients_same_sign": "no"},
        ]
        return [combos[i % len(combos)] for i in range(n_seeds)]

    # ---------------------------------------------------------------- preview
    def preview_extras(self, problem: Problem) -> Dict[str, str]:
        lp = problem.latent_parameters
        usable = lp["usable_shifts"]
        if usable:
            c, r, s = usable[0]
            transformed = f"y_(n+1) = {r}*y_n + {s}   with y_n = 1/(x_n - {c})"
            fixed = c
        else:
            transformed = "no substitution y = 1/(x - c) yields an affine recurrence"
            fixed = "none usable"
        return {
            "rational_fixed_points": ", ".join(lp["rational_fixed_points"]) or "none",
            "fixed_point_used": fixed,
            "transformed_recurrence": transformed,
            "symbolic_affine_check": lp["symbolic_affine_check"],
        }

    # ------------------------------------------------------------ recompute
    def recompute_answer(self, problem: Problem) -> str:
        lp = problem.latent_parameters
        num, den, horizon = lp["num"], lp["den"], lp["horizon"]
        terms = iterate_terms(num, den, Fraction(lp["x0"]), horizon)
        if terms is None:
            raise ValueError(f"{problem.id}: orbit became undefined on recompute")
        t = problem.template
        if t in ("compute_term", "implicit_form", "shifted_index"):
            return frac_str(terms[horizon])
        if t == "find_index":
            return str(horizon)
        raise ValueError(f"unknown template {t!r}")

    def recompute_strategy_applies(self, problem: Problem) -> bool:
        lp = problem.latent_parameters
        return strategy_succeeds_on(
            lp["num"], lp["den"], Fraction(lp["x0"]), lp["horizon"]
        )


def _listify(value: Any) -> List[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]
