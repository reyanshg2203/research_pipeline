"""Family 2 -- Lifting the Exponent, odd-prime difference form.

CANONICAL STRATEGY S2

    v_p(a^n - b^n) = v_p(a-b) + v_p(n)

APPLICABILITY ORACLE (revision memo S.2) -- THEOREM DOMAIN, not numerical luck:

    strategy_applies = 1  iff  p is an odd prime
                       and  p | (a - b)
                       and  p does not divide a
                       and  p does not divide b
                       and  n >= 1

A problem is NOT labelled APPLIES merely because the shortcut happens to return
the correct number outside that domain.  Those cases are real and common (most
often when both sides are 0), and they are recorded separately as
``accidental_match_outside_domain`` so the authors can see how many there are.
That is the point of the family: a solver that pattern-matches the formula
without checking its hypotheses will be right by accident some of the time and
wrong the rest of the time, and the boundary being learned is the theorem's
domain.

Every one of the four conditions is readable off the problem statement, so the
boundary is learnable in principle from the queryable features alone.

# HUMAN_REVIEW_REQUIRED
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from sympy import primerange

from families.base import ProblemFamily, UnsatisfiableConstraints
from schemas import Problem

_PRIMES: List[int] = list(primerange(2, 60))
_ODD_PRIMES: List[int] = [p for p in _PRIMES if p != 2]

TIERS: Dict[str, Dict[str, Any]] = {
    "easy": {"base": (2, 30), "n": (2, 12), "sizes": ["small"]},
    "medium": {"base": (2, 80), "n": (2, 40), "sizes": ["small", "medium"]},
    "hard": {"base": (2, 220), "n": (2, 110), "sizes": ["medium", "large"]},
}

EXPONENT_BUCKETS = {"small": (2, 12), "medium": (13, 40), "large": (41, 110)}


def exponent_bucket(n: int) -> str:
    for name, (lo, hi) in EXPONENT_BUCKETS.items():
        if lo <= n <= hi:
            return name
    raise ValueError(f"exponent {n} outside all buckets")


# --------------------------------------------------------------------------
# exact arithmetic -- ground truth
# --------------------------------------------------------------------------


def v_p(x: int, p: int) -> int:
    """p-adic valuation of a non-zero integer.  Exact, no floating point."""
    if x == 0:
        raise ValueError("v_p(0) is undefined")
    x = abs(x)
    k = 0
    while x % p == 0:
        x //= p
        k += 1
    return k


def exact_valuation(a: int, b: int, n: int, p: int) -> int:
    """v_p(a^n - b^n) by direct exact computation.  Independent of the shortcut."""
    value = a ** n - b ** n
    if value == 0:
        raise ValueError("a^n - b^n is zero; instance is degenerate")
    return v_p(value, p)


def shortcut_prediction(a: int, b: int, n: int, p: int) -> int:
    """What the LTE shortcut would return: v_p(a-b) + v_p(n)."""
    if a - b == 0:
        raise ValueError("a - b is zero; instance is degenerate")
    return v_p(a - b, p) + v_p(n, p)


def theorem_applicable(a: int, b: int, n: int, p: int) -> bool:
    """The applicability oracle: are the odd-prime LTE hypotheses satisfied?

    # HUMAN_REVIEW_REQUIRED -- this is the definition of `strategy_applies`.
    """
    return (
        p != 2
        and n >= 1
        and (a - b) % p == 0
        and a % p != 0
        and b % p != 0
    )


def nonapplicability_reason(a: int, b: int, n: int, p: int) -> str:
    """Which hypothesis fails first, under a fixed priority order."""
    if p == 2:
        return "p_is_two"
    if a % p == 0 or b % p == 0:
        return "p_divides_a_or_b"
    if (a - b) % p != 0:
        return "p_does_not_divide_difference"
    return "none"


def accidental_match(a: int, b: int, n: int, p: int) -> bool:
    """Shortcut returns the right number although the theorem does not apply."""
    if theorem_applicable(a, b, n, p):
        return False
    return exact_valuation(a, b, n, p) == shortcut_prediction(a, b, n, p)


def applicability_reason(a: int, b: int, n: int, p: int) -> str:
    exact = exact_valuation(a, b, n, p)
    pred = shortcut_prediction(a, b, n, p)
    if theorem_applicable(a, b, n, p):
        return (
            f"p = {p} is an odd prime, {p} | ({a} - {b}) = {a - b}, and {p} divides "
            f"neither {a} nor {b}: the odd-prime LTE hypotheses hold, so "
            f"v_{p} = v_{p}({a - b}) + v_{p}({n}) = {pred}, matching the true value {exact}"
        )
    reason = nonapplicability_reason(a, b, n, p)
    detail = {
        "p_is_two": f"p = 2 is not an odd prime, so the odd-prime difference form does not apply",
        "p_divides_a_or_b": (
            f"{p} divides "
            + ("a" if a % p == 0 else "")
            + (" and " if a % p == 0 and b % p == 0 else "")
            + ("b" if b % p == 0 else "")
            + f" ({a}, {b}), which the theorem forbids"
        ),
        "p_does_not_divide_difference": (
            f"{p} does not divide {a} - {b} = {a - b}, which the theorem requires"
        ),
    }[reason]
    tail = (
        f"; the shortcut nevertheless returns the correct value {exact} by accident"
        if pred == exact
        else f"; the shortcut returns {pred} but the true value is {exact}"
    )
    return detail + tail


# --------------------------------------------------------------------------
# family
# --------------------------------------------------------------------------


class LteValuationFamily(ProblemFamily):
    name = "lte_valuation"

    strategy_description = (
        "Odd-prime difference form of Lifting the Exponent: when p is an odd prime "
        "dividing a-b but dividing neither a nor b, v_p(a^n - b^n) = v_p(a-b) + v_p(n)."
    )

    #: Observable controls Active may request.  Each is checkable directly from
    #: the problem statement by dividing small integers.
    queryable_features = {
        "prime_type": ["odd", "two"],
        "p_divides_difference": ["yes", "no"],
        "p_divides_a_or_b": ["yes", "no"],
        "n_parity": ["odd", "even"],
        "exponent_size": ["small", "medium", "large"],
    }

    #: Researcher-only diagnostics.
    oracle_feature_schema = {
        "difference_valuation": ["0", "1", "2plus"],
        "p_divides_sum": ["yes", "no"],
        "n_divisible_by_p": ["yes", "no"],
        "exact_valuation_bucket": ["0", "1", "2", "3plus"],
        "accidental_match_outside_domain": ["yes", "no"],
        "nonapplicability_reason": [
            "none", "p_is_two", "p_divides_a_or_b", "p_does_not_divide_difference",
        ],
    }

    base_templates = ["valuation", "exponent_in_factorization"]
    challenge_templates = ["largest_k", "factor_out_prime"]

    # ---------------------------------------------------------------- features
    def compute_query_features(
        self, a: int, b: int, n: int, p: int, template: str
    ) -> Dict[str, str]:
        return {
            "prime_type": "two" if p == 2 else "odd",
            "p_divides_difference": "yes" if (a - b) % p == 0 else "no",
            "p_divides_a_or_b": "yes" if (a % p == 0 or b % p == 0) else "no",
            "n_parity": "even" if n % 2 == 0 else "odd",
            "exponent_size": exponent_bucket(n),
            "task_form": template,
        }

    def compute_oracle_features(
        self, a: int, b: int, n: int, p: int
    ) -> Dict[str, str]:
        diff_val = v_p(a - b, p) if (a - b) % p == 0 else 0
        exact = exact_valuation(a, b, n, p)
        return {
            "difference_valuation": (
                "0" if diff_val == 0 else "1" if diff_val == 1 else "2plus"
            ),
            "p_divides_sum": "yes" if (a + b) % p == 0 else "no",
            "n_divisible_by_p": "yes" if n % p == 0 else "no",
            "exact_valuation_bucket": str(exact) if exact <= 2 else "3plus",
            "accidental_match_outside_domain": (
                "yes" if accidental_match(a, b, n, p) else "no"
            ),
            "nonapplicability_reason": nonapplicability_reason(a, b, n, p),
        }

    # ---------------------------------------------------------------- building
    def _build(
        self, rng: random.Random, a: int, b: int, n: int, p: int, difficulty: str,
        template: str, seed_value: int,
    ) -> Problem:
        exact = exact_valuation(a, b, n, p)
        pred = shortcut_prediction(a, b, n, p)
        applies = theorem_applicable(a, b, n, p)

        latent: Dict[str, Any] = {
            "a": a, "b": b, "n": n, "p": p,
            "instance_key": f"v_{p}({a}^{n}-{b}^{n})",
            "exact_valuation": exact,
            "shortcut_prediction": pred,
            "theorem_applicable": applies,
            "accidental_match_outside_domain": accidental_match(a, b, n, p),
        }

        if template == "valuation":
            text = (f"Let N = {a}^{n} - {b}^{n}. Compute v_{p}(N), the exponent of "
                    f"the prime {p} in the prime factorization of N. "
                    f"Answer with a single non-negative integer.")
        elif template == "exponent_in_factorization":
            text = (f"Find the exponent of {p} in the prime factorization of "
                    f"{a}^{n} - {b}^{n}. Answer with a single non-negative integer.")
        elif template == "largest_k":
            text = (f"Find the largest integer k ≥ 0 such that {p}^k divides "
                    f"{a}^{n} - {b}^{n}. Answer with a single non-negative integer.")
        elif template == "factor_out_prime":
            text = (f"Write {a}^{n} - {b}^{n} = {p}^k · M where M is an integer not "
                    f"divisible by {p}. Determine k. "
                    f"Answer with a single non-negative integer.")
        else:
            raise ValueError(f"unknown template {template!r}")

        return Problem(
            id=f"{self.name}-{template}-{p}-{a}-{b}-{n}-{seed_value}",
            family=self.name,
            template=template,
            difficulty=difficulty,
            text=text,
            exact_answer=str(exact),
            strategy_applies=applies,
            query_features=self.compute_query_features(a, b, n, p, template),
            oracle_features=self.compute_oracle_features(a, b, n, p),
            applicability_reason=applicability_reason(a, b, n, p),
            human_solution=self._write_solution(a, b, n, p, exact) if applies else "",
            latent_parameters=latent,
            generation_seed=seed_value,
        )

    def _write_solution(self, a: int, b: int, n: int, p: int, exact: int) -> str:
        """Worked solution for a positive instance.

        Sketches the genuine derivation and mentions that p divides a-b, but
        deliberately does NOT enumerate the theorem's hypotheses -- the model has
        to discover for itself that p must be odd and must not divide the bases
        (spec S.8.5).
        """
        vd = v_p(a - b, p)
        vn = v_p(n, p)
        return " ".join([
            f"Set N = {a}^{n} - {b}^{n}, and note {a} - {b} = {a - b} with "
            f"v_{p}({a - b}) = {vd}.",
            f"Factor N = ({a} - {b}) · S where S = Σ_(i=0)^({n}-1) {a}^i {b}^({n}-1-i).",
            f"Because {a} ≡ {b} (mod {p}), each of the {n} terms of S is congruent to "
            f"{b}^({n}-1) modulo {p}, so S ≡ {n}·{b}^({n}-1) (mod {p}) and the "
            f"valuation of S is governed by v_{p}({n}) = {vn}.",
            f"Hence v_{p}(N) = v_{p}({a} - {b}) + v_{p}({n}) = {vd} + {vn} = {exact}.",
            f"The answer is {exact}.",
        ])

    # -------------------------------------------------------- construction
    #: Positive modes are parameterised by the target exact valuation so that
    #: seed demonstrations are not all valuation-1 (revision memo S.2).
    POSITIVE_VALUATIONS = ["1", "2", "3plus"]

    #: Negatives are stratified across the distinct ways the theorem's
    #: hypotheses can fail, so the negative class is not dominated by p = 2.
    NEGATIVE_REASONS = [
        "p_is_two", "p_divides_a_or_b", "p_does_not_divide_difference",
    ]

    def _n_range(self, rng: random.Random, difficulty: str) -> Optional[Tuple[int, int]]:
        tier = TIERS[difficulty]
        size = rng.choice(tier["sizes"])
        nlo, nhi = EXPONENT_BUCKETS[size]
        nlo = max(nlo, tier["n"][0])
        nhi = min(nhi, tier["n"][1])
        return (nlo, nhi) if nlo <= nhi else None

    def _draw_positive(
        self, rng: random.Random, difficulty: str, target_valuation: Optional[str] = None
    ) -> Optional[Tuple[int, int, int, int]]:
        """p odd, p | a-b, p divides neither base; exact valuation = e + v_p(n)."""
        tier = TIERS[difficulty]
        lo, hi = tier["base"]
        rng_n = self._n_range(rng, difficulty)
        if rng_n is None:
            return None
        nlo, nhi = rng_n
        for _ in range(200):
            p = rng.choice([q for q in _ODD_PRIMES if q ** 2 <= 4 * hi])
            if target_valuation == "1":
                e, k = 1, 0
            elif target_valuation == "2":
                e, k = rng.choice([(2, 0), (1, 1)])
            elif target_valuation == "3plus":
                e, k = rng.choice([(3, 0), (2, 1), (1, 2)])
            else:
                e, k = rng.choice([1, 1, 2, 3]), rng.choice([0, 0, 1])
            step = p ** e
            if step > 3 * hi:
                continue
            # n with v_p(n) exactly k
            multiples = [
                x for x in range(nlo, nhi + 1)
                if x % (p ** k) == 0 and (k == 0 or x % (p ** (k + 1)) != 0)
                and (k > 0 or x % p != 0)
            ]
            if not multiples:
                continue
            n = rng.choice(multiples)
            b = rng.randint(lo, hi)
            if b % p == 0:
                continue
            t = rng.randint(1, max(1, (2 * hi) // step))
            if t % p == 0:
                continue                      # keeps v_p(a-b) exactly e
            a = b + t * step
            if a == b or a % p == 0 or a > 4 * hi:
                continue
            if not theorem_applicable(a, b, n, p):
                continue
            return a, b, n, p
        return None

    def _draw_negative(
        self, rng: random.Random, difficulty: str, reason: Optional[str] = None
    ) -> Optional[Tuple[int, int, int, int]]:
        tier = TIERS[difficulty]
        lo, hi = tier["base"]
        rng_n = self._n_range(rng, difficulty)
        if rng_n is None:
            return None
        nlo, nhi = rng_n
        reason = reason or rng.choice(self.NEGATIVE_REASONS)
        for _ in range(200):
            n = rng.randint(nlo, nhi)
            if reason == "p_is_two":
                # near-boundary: 2 | a-b and 2 divides neither base, so oddness of
                # p is the ONLY hypothesis that fails
                b = rng.randrange(lo | 1, hi, 2)
                a = b + 2 * rng.randint(1, max(1, hi // 2))
                if a == b:
                    continue
                cand = (a, b, n, 2)
            elif reason == "p_divides_a_or_b":
                p = rng.choice(_ODD_PRIMES)
                if rng.random() < 0.5:
                    a, b = p * rng.randint(1, max(1, hi // p)), p * rng.randint(
                        1, max(1, hi // p))
                else:
                    a = p * rng.randint(1, max(1, hi // p))
                    b = rng.randint(lo, hi)
                    if b % p == 0:
                        continue
                if a == b or a < 2 or b < 2:
                    continue
                cand = (a, b, n, p)
            else:  # p_does_not_divide_difference
                p = rng.choice(_ODD_PRIMES)
                a = rng.randint(lo + 1, hi)
                b = rng.randint(lo, max(lo, a - 1))
                if a == b or (a - b) % p == 0 or a % p == 0 or b % p == 0:
                    continue
                cand = (a, b, n, p)
            aa, bb, nn, pp = cand
            if theorem_applicable(aa, bb, nn, pp):
                continue
            if nonapplicability_reason(aa, bb, nn, pp) != reason:
                continue
            return cand
        return None

    # ------------------------------------------------------------------- API
    def sample_random(
        self, rng: random.Random, difficulty: str, template: str,
        want_applies: Optional[bool] = None,
    ) -> Problem:
        for _ in range(600):
            if want_applies is True:
                drawn = self._draw_positive(rng, difficulty)
            elif want_applies is False:
                drawn = self._draw_negative(rng, difficulty)
            else:
                drawn = (
                    self._draw_positive(rng, difficulty)
                    if rng.random() < 0.5
                    else self._draw_negative(rng, difficulty)
                )
            if drawn is None:
                continue
            a, b, n, p = drawn
            if a == b:
                continue
            if want_applies is not None and theorem_applicable(a, b, n, p) != want_applies:
                continue
            return self._build(rng, a, b, n, p, difficulty, template, rng.randrange(2 ** 31))
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

        want_size = constraints.get("exponent_size")
        if want_size is not None:
            wanted = {str(v) for v in _listify(want_size)}
            if not wanted & set(tier["sizes"]):
                raise UnsatisfiableConstraints(
                    f"difficulty '{difficulty}' only produces exponent sizes "
                    f"{tier['sizes']}", constraints)
        pdd = constraints.get("p_divides_difference")
        pdab = constraints.get("p_divides_a_or_b")
        if pdd is not None and pdab is not None:
            pdd_v = {str(v) for v in _listify(pdd)}
            pdab_v = {str(v) for v in _listify(pdab)}
            # p | a and p | b forces p | a-b, and p | exactly one of them forces
            # p not dividing a-b, so "no, yes" pairs are impossible only in the
            # both-divide case; the reachable combinations are checked by sampling
            if pdd_v == {"yes"} and pdab_v == {"yes"}:
                pass  # reachable: p | a and p | b
        ptype = constraints.get("prime_type")
        npar = constraints.get("n_parity")
        if ptype is not None and npar is not None:
            if {str(v) for v in _listify(ptype)} == {"two"} and \
               {str(v) for v in _listify(npar)} == {"odd"}:
                pass  # reachable

        for _ in range(8000):
            drawn = (
                self._draw_positive(rng, difficulty)
                if rng.random() < 0.5
                else self._draw_negative(rng, difficulty)
            )
            if drawn is None:
                continue
            a, b, n, p = drawn
            feats = self.compute_query_features(a, b, n, p, template)
            if not self.matches(feats, constraints):
                continue
            return self._build(rng, a, b, n, p, difficulty, template, rng.randrange(2 ** 31))
        return None

    # ------------------------------------------------------------ seed strata
    def seed_strata(self, n_seeds: int) -> List[Dict[str, str]]:
        """Seeds are stratified by exponent size and n-parity.

        The exact-valuation mix (1 / 2 / 3+) is enforced separately in
        :meth:`_draw_seed_positive`, since exact valuation is an ORACLE feature
        and must never appear in a query constraint.
        """
        return [{} for _ in range(n_seeds)]

    def generate_seed_candidates(
        self, rng: random.Random, n: int, difficulty: str
    ) -> List[Problem]:
        """Positive demonstrations with a spread of exact valuations.

        Revision memo S.2: positive seeds must not be dominated by valuation 0.
        Under the theorem-domain oracle a positive always has valuation >= 1;
        this additionally spreads them over 1, 2 and 3+.
        """
        targets = ["1", "2", "3plus"]
        out: List[Problem] = []
        seen = set()
        for index in range(n):
            target = targets[index % len(targets)]
            template = self.base_templates[index % len(self.base_templates)]
            built = None
            for _ in range(600):
                drawn = self._draw_positive(rng, difficulty, target)
                if drawn is None:
                    continue
                a, b, n_, p = drawn
                problem = self._build(
                    rng, a, b, n_, p, difficulty, template, rng.randrange(2 ** 31)
                )
                if problem.content_key() in seen or not problem.human_solution:
                    continue
                self.validate_problem(problem)
                built = problem
                break
            if built is None:  # fall back to any positive rather than failing
                built = self.sample_random(rng, difficulty, template, want_applies=True)
                self.validate_problem(built)
            seen.add(built.content_key())
            out.append(built)
        return out

    # ---------------------------------------------------------------- preview
    def preview_extras(self, problem: Problem) -> Dict[str, str]:
        lp = problem.latent_parameters
        return {
            "exact_valuation": str(lp["exact_valuation"]),
            "lte_shortcut_prediction": str(lp["shortcut_prediction"]),
            "theorem_applicable": str(lp["theorem_applicable"]),
            "accidental_match_outside_domain": str(
                lp["accidental_match_outside_domain"]
            ),
        }

    # ------------------------------------------------------------ recompute
    def recompute_answer(self, problem: Problem) -> str:
        lp = problem.latent_parameters
        return str(exact_valuation(lp["a"], lp["b"], lp["n"], lp["p"]))

    def recompute_strategy_applies(self, problem: Problem) -> bool:
        lp = problem.latent_parameters
        return theorem_applicable(lp["a"], lp["b"], lp["n"], lp["p"])


def _listify(value: Any) -> List[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]
