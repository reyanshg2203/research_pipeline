"""Family 3 -- nonlinear rational recurrence linearised by y_n = 1/(x_n - c).

MATHEMATICAL BASIS (see docs/FAMILY_SPEC.md S.3 for the full note)
------------------------------------------------------------------
For a rational map f and a constant c, put y = 1/(x - c).  As y -> infinity we
have x -> c, so y_{n+1} = 1/(f(x_n) - c) stays bounded unless f(c) = c.  Hence

    y = 1/(x - c) can linearise f  ONLY IF c is a fixed point of f,

and for a Mobius map f(x) = (Ax+B)/(Cx+D) with C != 0 the substitution at a
fixed point c always yields an affine recurrence.  Therefore

    strategy_applies  <=>  f has a RATIONAL fixed point
                      <=>  disc = (D-A)^2 + 4CB is a perfect square   (Mobius case)

Both equivalences are verified symbolically in tests/test_recurrence_family.py.

# HUMAN_REVIEW_REQUIRED  (most important review item in the repository)
The spec (S.9.3) phrases the oracle as "there EXISTS the designated seed-family
shift c".  We implement the EXISTENTIAL reading: the oracle searches every
rational shift, not one privileged value.  Rationale: a boundary defined by a
hidden designated constant that is invisible in the rendered problem would be
unlearnable in principle, and several perturbations suggested by the spec
(e.g. "add a small constant to the numerator") frequently leave the map
linearisable through a *different* rational fixed point.  Every generated
negative is therefore verified to admit no linearising shift at all.
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


def strategy_succeeds(num: List[int], den: List[int]) -> bool:
    """Programmatic oracle for Family 3."""
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
# family
# --------------------------------------------------------------------------


class RecurrenceSubstitutionFamily(ProblemFamily):
    name = "recurrence_substitution"

    strategy_description = (
        "Recognise that a rational recurrence x_{n+1} = f(x_n) becomes affine under "
        "the shift-and-reciprocal substitution y_n = 1/(x_n - c), where c is a fixed "
        "point of f; solve the resulting affine recurrence in closed form and invert."
    )

    active_query_schema = {
        "shift_structure": ["aligned", "mismatched"],
        "numerator_structure": ["proportional_to_shifted_x", "additive_perturbation"],
        "denominator_relation": ["affine_compatible", "perturbed"],
        "transformed_dynamics": ["affine", "non_affine"],
        "singularity_risk": ["none_in_horizon", "boundary_case"],
        "horizon_size": ["small", "medium", "large"],
    }

    label_determining_features = ["transformed_dynamics", "shift_structure"]

    base_templates = ["compute_term", "find_index"]
    challenge_templates = ["implicit_form", "transformed_value"]

    # ------------------------------------------------------------ construction
    def _positive_map(self, rng: random.Random, coef: int) -> Optional[Dict[str, Any]]:
        """Build (A,B,C,D) from a hidden (c, r, s) so that y=1/(x-c) linearises it.

        x_{n+1} = c + (x_n - c) / (r + s*(x_n - c))
                = ((c*s+1) x + c*r - c^2*s - c) / (s x + r - s*c)
        """
        for _ in range(80):
            c = rng.randint(-coef, coef)
            r = rng.choice([1, 2, -1, 3, -2, 2, 3])
            s = rng.choice([k for k in range(-coef, coef + 1) if k != 0])
            A = c * s + 1
            B = c * r - c * c * s - c
            C = s
            D = r - s * c
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
        """Controlled perturbation of a positive map (spec S.9.3).

        The perturbation is applied to the normalised rational coefficients so
        that the rendered surface form is indistinguishable from a positive.
        The caller re-runs the oracle: perturbations that happen to remain
        linearisable through some other rational fixed point are kept, but
        relabelled as positives rather than mislabelled as negatives.
        """
        num = list(base["num"])
        den = list(base["den"])
        # A quadratic numerator is a *perfect* predictor of non-applicability
        # (a genuine degree-2 map is never linearised by a shift-and-reciprocal
        # substitution), so it is down-weighted to keep that shortcut from
        # dominating the negative class.  scripts/audit_schema.py reports how
        # much of the label it explains.
        # HUMAN_REVIEW_REQUIRED
        kind = rng.choices(
            [
                "numerator_constant",
                "numerator_slope",
                "denominator_constant",
                "denominator_slope",
                "quadratic_term",
            ],
            weights=[3, 3, 3, 3, 1],
        )[0]
        delta = rng.choice([-3, -2, -1, 1, 2, 3])
        if kind == "numerator_constant":
            num[-1] += delta
            nstruct, dstruct = "additive_perturbation", "affine_compatible"
        elif kind == "numerator_slope":
            num[-2] += delta
            nstruct, dstruct = "additive_perturbation", "affine_compatible"
        elif kind == "denominator_constant":
            den[-1] += delta
            nstruct, dstruct = "proportional_to_shifted_x", "perturbed"
        elif kind == "denominator_slope":
            den[-2] += delta
            nstruct, dstruct = "proportional_to_shifted_x", "perturbed"
        else:
            num = [delta] + num
            nstruct, dstruct = "additive_perturbation", "affine_compatible"
            # A quadratic numerator sharing the denominator's root cancels down
            # to an affine map (e.g. (-x^2-3x+4)/(5x-5) = -(x+4)/5), which then
            # DOES admit a linearising shift.  Such instances are mathematically
            # fine but render as an unreduced fraction, so we drop them and keep
            # every degree-2 instance genuinely degree-2.
            if den[0] != 0 and poly_eval(num, Fraction(-den[1], den[0])) == 0:
                return None
        if all(v == 0 for v in den):
            return None
        if all(v == 0 for v in num):
            return None
        num, den = normalise(num, den)
        if len(num) == 2 and len(den) == 2:
            A, B = num
            C, D = den
            if C == 0 or A * D - B * C == 0:
                return None
        if max(abs(v) for v in num + den) > 60 * coef:
            return None
        return {
            "num": num,
            "den": den,
            "c": base["c"],
            "r": base["r"],
            "s": base["s"],
            "numerator_structure": nstruct,
            "denominator_relation": dstruct,
            "perturbation": kind,
        }

    def _choose_x0(
        self, rng: random.Random, num: List[int], den: List[int], horizon: int, coef: int
    ) -> Optional[Tuple[Fraction, List[Fraction], str]]:
        """Pick x_0 with a well-defined orbit; classify singularity risk."""
        cands = [Fraction(k) for k in range(-coef, coef + 1)]
        cands += [Fraction(k, 2) for k in range(-2 * coef, 2 * coef + 1) if k % 2]
        rng.shuffle(cands)
        for x0 in cands:
            terms = iterate_terms(num, den, x0, horizon)
            if terms is None:
                continue
            if len(set(terms)) < len(terms):
                continue  # periodic / constant orbits are degenerate
            extended = iterate_terms(num, den, x0, horizon + 2)
            risk = "none_in_horizon" if extended is not None else "boundary_case"
            return x0, terms, risk
        return None

    # ---------------------------------------------------------------- building
    def _build(
        self,
        rng: random.Random,
        spec: Dict[str, Any],
        difficulty: str,
        template: str,
        horizon: int,
        x0: Fraction,
        terms: List[Fraction],
        risk: str,
        seed_value: int,
    ) -> Optional[Problem]:
        num, den = spec["num"], spec["den"]
        shifts = linearising_shifts(num, den)
        applies = len(shifts) > 0
        c_designated = Fraction(spec["c"])
        aligned = any(c == c_designated for c, _, _ in shifts)

        features = {
            "shift_structure": "aligned" if aligned else "mismatched",
            "numerator_structure": spec.get(
                "numerator_structure", "proportional_to_shifted_x"
            ),
            "denominator_relation": spec.get(
                "denominator_relation", "affine_compatible"
            ),
            "transformed_dynamics": "affine" if applies else "non_affine",
            "singularity_risk": risk,
            "horizon_size": horizon_bucket(horizon),
        }

        latent: Dict[str, Any] = {
            "num": num,
            "den": den,
            "x0": frac_str(x0),
            "horizon": horizon,
            "c_designated": frac_str(c_designated),
            "r": spec["r"],
            "s": spec["s"],
            "perturbation": spec.get("perturbation"),
            "linearising_shifts": [
                [frac_str(c), frac_str(r), frac_str(s)] for c, r, s in shifts
            ],
            "instance_key": f"{num}|{den}|{frac_str(x0)}|{horizon}",
            "terms": [frac_str(t) for t in terms],
        }

        num_s = render_linear(num, "x_n")
        den_s = render_linear(den, "x_n")
        rec = f"x_(n+1) = ({num_s}) / ({den_s})"

        if template == "compute_term":
            text = (
                f"A sequence of rational numbers satisfies "
                f"x_0 = {frac_str(x0)} and {rec} for all n ≥ 0. "
                f"Compute x_{horizon}. "
                f"Give the exact value as an integer or a reduced fraction."
            )
            answer = frac_str(terms[horizon])
        elif template == "find_index":
            target = terms[horizon]
            lo, hi = 1, max(HORIZON_BUCKETS["large"][1], horizon)
            probe = iterate_terms(num, den, x0, hi)
            if probe is None:
                return None
            if sum(1 for t in probe[lo:] if t == target) != 1:
                return None
            text = (
                f"A sequence of rational numbers satisfies "
                f"x_0 = {frac_str(x0)} and {rec} for all n ≥ 0. "
                f"There is exactly one index N with {lo} ≤ N ≤ {hi} for which "
                f"x_N = {frac_str(target)}. Find N. "
                f"Answer with a single integer."
            )
            answer = str(horizon)
            latent["index_search_range"] = [lo, hi]
        elif template == "implicit_form":
            # x_(n+1) * (den0*x_n + den1) = num(x_n), written out flat
            lhs = render_terms(
                [(den[0], "x_n x_(n+1)"), (den[1], "x_(n+1)")]
            )
            rhs = render_linear(num, "x_n")
            text = (
                f"A sequence of rational numbers satisfies x_0 = {frac_str(x0)} and "
                f"{lhs} = {rhs} for all n ≥ 0. "
                f"Compute x_{horizon}. "
                f"Give the exact value as an integer or a reduced fraction."
            )
            answer = frac_str(terms[horizon])
        elif template == "transformed_value":
            k = c_designated
            if terms[horizon] == k:
                return None
            text = (
                f"A sequence of rational numbers satisfies "
                f"x_0 = {frac_str(x0)} and {rec} for all n ≥ 0. "
                f"Compute the exact value of 1/(x_{horizon} - ({frac_str(k)})). "
                f"Give the exact value as an integer or a reduced fraction."
            )
            answer = frac_str(1 / (terms[horizon] - k))
            latent["transformed_shift"] = frac_str(k)
        else:
            raise ValueError(f"unknown template {template!r}")

        if len(answer) > 44:
            return None

        solution = (
            self._write_solution(spec, shifts, x0, horizon, terms, answer, template)
            if applies
            else ""
        )
        # zlib.crc32, NOT the built-in hash(): string hashing is salted per
        # process, so ids built from hash() would differ between runs and break
        # reproducibility of the frozen test files.
        digest = zlib.crc32(latent["instance_key"].encode("utf-8"))
        pid = f"{self.name}-{template}-{digest:08x}-{seed_value}"
        return Problem(
            id=pid,
            family=self.name,
            template=template,
            difficulty=difficulty,
            text=text,
            exact_answer=answer,
            strategy_applies=applies,
            features=features,
            human_solution=solution,
            latent_parameters=latent,
            generation_seed=seed_value,
        )

    def _write_solution(
        self,
        spec: Dict[str, Any],
        shifts: List[Tuple[Fraction, Fraction, Fraction]],
        x0: Fraction,
        horizon: int,
        terms: List[Fraction],
        answer: str,
        template: str,
    ) -> str:
        c, r, s = shifts[0]
        y0 = 1 / (x0 - c)
        ys = [y0]
        for _ in range(horizon):
            ys.append(r * ys[-1] + s)
        if c == 0:
            shift = "x_n"
        elif c < 0:
            shift = f"(x_n + {frac_str(-c)})"
        else:
            shift = f"(x_n - {frac_str(c)})"
        coef = "" if r == 1 else ("-" if r == -1 else f"{frac_str(r)}·")
        tail = "" if s == 0 else (f" - {frac_str(-s)}" if s < 0 else f" + {frac_str(s)}")
        invert = "1/y" if c == 0 else f"{frac_str(c)} + 1/y"
        lines = [
            f"Look for a constant c fixed by the map: solving f(c) = c gives "
            f"c = {frac_str(c)}.",
            f"Substitute y_n = 1/{shift}.",
            f"A short computation turns the recurrence into the affine recurrence "
            f"y_(n+1) = {coef}y_n{tail}.",
            f"From x_0 = {frac_str(x0)} we get y_0 = {frac_str(y0)}.",
            f"Iterating the affine recurrence {horizon} times gives "
            f"y_{horizon} = {frac_str(ys[horizon])}.",
            f"Inverting, x_{horizon} = {invert}_{horizon} = "
            f"{frac_str(terms[horizon])}.",
        ]
        if template != "compute_term":
            lines.append(f"The requested quantity is therefore {answer}.")
        return " ".join(lines)

    # ------------------------------------------------------------------- API
    def sample_random(
        self,
        rng: random.Random,
        difficulty: str,
        template: str,
        want_applies: Optional[bool] = None,
    ) -> Problem:
        tier = TIERS[difficulty]
        coef = tier["coef"]
        for _ in range(4000):
            base = self._positive_map(rng, coef)
            if base is None:
                continue
            # Positives are used directly; candidate negatives are perturbations
            # of a positive, so every negative is near the boundary.
            make_negative = (
                want_applies is False
                if want_applies is not None
                else rng.random() < 0.5
            )
            spec = base
            if make_negative:
                spec = self._perturb(rng, base, coef)
                if spec is None:
                    continue
            # A perturbation may stay linearisable through a *different* rational
            # fixed point.  Such instances are genuine near-boundary positives;
            # the oracle in _build assigns the true label and the want_applies
            # check below discards anything the caller did not ask for.
            bucket = rng.choice(tier["horizons"])
            hlo, hhi = HORIZON_BUCKETS[bucket]
            horizon = rng.randint(hlo, hhi)
            chosen = self._choose_x0(rng, spec["num"], spec["den"], horizon, coef)
            if chosen is None:
                continue
            x0, terms, risk = chosen
            problem = self._build(
                rng, spec, difficulty, template, horizon, x0, terms, risk,
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
        self,
        rng: random.Random,
        constraints: Dict[str, str],
        difficulty: str,
        template: str,
    ) -> Optional[Problem]:
        self.check_constraints_wellformed(constraints)
        tier = TIERS[difficulty]

        want_h = constraints.get("horizon_size")
        if want_h is not None:
            wanted = {str(v) for v in _listify(want_h)}
            if not wanted & set(tier["horizons"]):
                raise UnsatisfiableConstraints(
                    f"difficulty '{difficulty}' only produces horizon sizes "
                    f"{tier['horizons']}",
                    constraints,
                )
        shift = constraints.get("shift_structure")
        dyn = constraints.get("transformed_dynamics")
        if shift is not None and dyn is not None:
            if {str(v) for v in _listify(shift)} == {"aligned"} and {
                str(v) for v in _listify(dyn)
            } == {"non_affine"}:
                raise UnsatisfiableConstraints(
                    "shift_structure='aligned' means the designated shift does "
                    "linearise the recurrence, so transformed_dynamics is 'affine'",
                    constraints,
                )

        want_applies = None
        if dyn is not None:
            dv = {str(v) for v in _listify(dyn)}
            if dv == {"affine"}:
                want_applies = True
            elif dv == {"non_affine"}:
                want_applies = False

        for _ in range(6000):
            try:
                p = self.sample_random(rng, difficulty, template, want_applies)
            except RuntimeError:
                return None
            if self.matches(p.features, constraints):
                return p
        return None

    # ------------------------------------------------------------ recompute
    def recompute_answer(self, problem: Problem) -> str:
        lp = problem.latent_parameters
        num, den = lp["num"], lp["den"]
        x0 = Fraction(lp["x0"])
        horizon = lp["horizon"]
        terms = iterate_terms(num, den, x0, horizon)
        if terms is None:
            raise ValueError(f"{problem.id}: orbit became undefined on recompute")
        t = problem.template
        if t in ("compute_term", "implicit_form"):
            return frac_str(terms[horizon])
        if t == "find_index":
            return str(horizon)
        if t == "transformed_value":
            k = Fraction(lp["transformed_shift"])
            return frac_str(1 / (terms[horizon] - k))
        raise ValueError(f"unknown template {t!r}")

    def recompute_strategy_applies(self, problem: Problem) -> bool:
        lp = problem.latent_parameters
        return strategy_succeeds(lp["num"], lp["den"])


def _listify(value: Any) -> List[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]
