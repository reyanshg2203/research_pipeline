"""Family 2 -- p-adic valuation of a^n - b^n / LTE-style reasoning.

Operational applicability oracle (spec S.8.3, docs/FAMILY_SPEC.md S.2):

    shortcut_prediction = v_p(a - b) + v_p(n)
    actual              = v_p(a^n - b^n)          (exact big-integer arithmetic)
    strategy_applies    = (actual == shortcut_prediction)

Applicability is defined by whether the shortcut *produces the right number*,
not by whether the textbook hypotheses of the Lifting-the-Exponent lemma
happen to hold.  That is deliberate: it admits near-boundary instances where a
familiar-looking shortcut silently fails.

# HUMAN_REVIEW_REQUIRED -- the operational definition above is a scientific
choice and must be approved by the authors.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from sympy import primerange, primitive_root

from families.base import ProblemFamily, UnsatisfiableConstraints
from schemas import Problem

_PRIMES: List[int] = list(primerange(2, 60))
_ODD_PRIMES: List[int] = [p for p in _PRIMES if p != 2]

#: difficulty tier -> (base range, exponent range, exponent-size buckets)
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


def actual_valuation(a: int, b: int, n: int, p: int) -> int:
    """v_p(a^n - b^n) by direct exact computation."""
    value = a ** n - b ** n
    if value == 0:
        raise ValueError("a^n - b^n is zero; instance is degenerate")
    return v_p(value, p)


def shortcut_valuation(a: int, b: int, n: int, p: int) -> int:
    """The shortcut the strategy proposes: v_p(a-b) + v_p(n)."""
    if a - b == 0:
        raise ValueError("a - b is zero; instance is degenerate")
    return v_p(a - b, p) + v_p(n, p)


def strategy_succeeds(a: int, b: int, n: int, p: int) -> bool:
    return actual_valuation(a, b, n, p) == shortcut_valuation(a, b, n, p)


class LteValuationFamily(ProblemFamily):
    name = "lte_valuation"

    strategy_description = (
        "Use the difference form of the Lifting-the-Exponent lemma: for a prime p "
        "dividing a-b but dividing neither a nor b, v_p(a^n - b^n) = v_p(a-b) + v_p(n). "
        "Applicability here is operational: the strategy applies exactly when this "
        "formula returns the true valuation on the instance."
    )

    active_query_schema = {
        "prime_type": ["odd", "two"],
        "p_divides_difference": ["yes", "no"],
        "p_divides_sum": ["yes", "no"],
        "p_divides_a_or_b": ["yes", "no"],
        "n_parity": ["odd", "even"],
        "n_divisible_by_p": ["yes", "no"],
        "difference_valuation": ["0", "1", "2plus"],
        "exponent_size": ["small", "medium", "large"],
    }

    label_determining_features = []

    base_templates = ["valuation", "exponent_in_factorization"]
    challenge_templates = ["largest_k", "factor_out_prime"]

    # ---------------------------------------------------------------- features
    def compute_features(self, a: int, b: int, n: int, p: int) -> Dict[str, str]:
        diff_val = v_p(a - b, p) if (a - b) % p == 0 else 0
        return {
            "prime_type": "two" if p == 2 else "odd",
            "p_divides_difference": "yes" if (a - b) % p == 0 else "no",
            "p_divides_sum": "yes" if (a + b) % p == 0 else "no",
            "p_divides_a_or_b": "yes" if (a % p == 0 or b % p == 0) else "no",
            "n_parity": "even" if n % 2 == 0 else "odd",
            "n_divisible_by_p": "yes" if n % p == 0 else "no",
            "difference_valuation": (
                "0" if diff_val == 0 else "1" if diff_val == 1 else "2plus"
            ),
            "exponent_size": exponent_bucket(n),
        }

    # ---------------------------------------------------------------- building
    def _build(
        self,
        rng: random.Random,
        a: int,
        b: int,
        n: int,
        p: int,
        difficulty: str,
        template: str,
        seed_value: int,
    ) -> Problem:
        actual = actual_valuation(a, b, n, p)
        shortcut = shortcut_valuation(a, b, n, p)
        applies = actual == shortcut
        features = self.compute_features(a, b, n, p)

        latent: Dict[str, Any] = {
            "a": a,
            "b": b,
            "n": n,
            "p": p,
            "instance_key": f"v_{p}({a}^{n}-{b}^{n})",
            "actual_valuation": actual,
            "shortcut_prediction": shortcut,
        }

        if template == "valuation":
            text = (
                f"Let N = {a}^{n} - {b}^{n}. Compute v_{p}(N), the exponent of "
                f"the prime {p} in the prime factorization of N. "
                f"Answer with a single non-negative integer."
            )
        elif template == "exponent_in_factorization":
            text = (
                f"Find the exponent of {p} in the prime factorization of "
                f"{a}^{n} - {b}^{n}. Answer with a single non-negative integer."
            )
        elif template == "largest_k":
            text = (
                f"Find the largest integer k ≥ 0 such that {p}^k divides "
                f"{a}^{n} - {b}^{n}. Answer with a single non-negative integer."
            )
        elif template == "factor_out_prime":
            text = (
                f"Write {a}^{n} - {b}^{n} = {p}^k · M where M is an integer not "
                f"divisible by {p}. Determine k. "
                f"Answer with a single non-negative integer."
            )
        else:
            raise ValueError(f"unknown template {template!r}")

        solution = (
            self._write_solution(a, b, n, p, actual) if applies else ""
        )
        pid = f"{self.name}-{template}-{p}-{a}-{b}-{n}-{seed_value}"
        return Problem(
            id=pid,
            family=self.name,
            template=template,
            difficulty=difficulty,
            text=text,
            exact_answer=str(actual),
            strategy_applies=applies,
            features=features,
            human_solution=solution,
            latent_parameters=latent,
            generation_seed=seed_value,
        )

    def _write_solution(self, a: int, b: int, n: int, p: int, actual: int) -> str:
        """Worked solution for a positive instance.

        Shows genuine valuation reasoning.  Deliberately does not enumerate the
        failure conditions (spec S.8.5).
        """
        vd = v_p(a - b, p)
        vn = v_p(n, p)
        lines = [
            f"Set N = {a}^{n} - {b}^{n}.",
            f"First, {a} - {b} = {a - b} and v_{p}({a - b}) = {vd}, so {p} divides {a} - {b}"
            if vd > 0
            else f"First, {a} - {b} = {a - b} and v_{p}({a - b}) = 0.",
        ]
        if a % p != 0 and b % p != 0:
            lines.append(f"Neither {a} nor {b} is divisible by {p}.")
        lines.append(
            f"Writing {a}^{n} - {b}^{n} = ({a} - {b}) · Σ_{{i=0}}^{{{n}-1}} {a}^i {b}^{{{n}-1-i}}, "
            f"the valuation of the cofactor is governed by v_{p}({n}) = {vn}."
        )
        lines.append(
            f"This gives v_{p}(N) = v_{p}({a} - {b}) + v_{p}({n}) = {vd} + {vn} = {actual}."
        )
        lines.append(f"Hence the answer is {actual}.")
        return " ".join(lines)

    # ------------------------------------------------------------------- API
    # Construction modes.  Rejection sampling alone collapses the negative class
    # onto p = 2 (odd-prime counterexamples to the shortcut are rare under a
    # uniform draw), which would make the boundary trivially "p = 2 fails".
    # These modes construct positives and negatives at BOTH prime types so that
    # `prime_type` is not a surrogate for the label.
    # HUMAN_REVIEW_REQUIRED -- the mode mixture defines the adaptation
    # distribution and therefore what "random practice" means for Passive.
    POSITIVE_MODES = ["pos_lte_odd", "pos_two_odd_n", "pos_coprime_odd"]
    NEGATIVE_MODES = ["neg_two_even_n", "neg_p_divides_both", "neg_order_divides"]

    def _n_range(self, rng: random.Random, difficulty: str) -> Optional[tuple]:
        tier = TIERS[difficulty]
        size = rng.choice(tier["sizes"])
        nlo, nhi = EXPONENT_BUCKETS[size]
        nlo = max(nlo, tier["n"][0])
        nhi = min(nhi, tier["n"][1])
        if nlo > nhi:
            return None
        return nlo, nhi

    def _draw_mode(
        self, rng: random.Random, difficulty: str, mode: str
    ) -> Optional[tuple]:
        """Return (a, b, n, p) for one construction mode, or None on failure."""
        tier = TIERS[difficulty]
        lo, hi = tier["base"]
        rng_n = self._n_range(rng, difficulty)
        if rng_n is None:
            return None
        nlo, nhi = rng_n

        if mode == "pos_lte_odd":
            # p odd, p | a-b, p divides neither a nor b -> LTE holds exactly
            for _ in range(80):
                p = rng.choice(_ODD_PRIMES)
                n = rng.randint(nlo, nhi)
                b = rng.randint(lo, hi)
                if b % p == 0:
                    continue
                e = rng.choice([1, 1, 2])
                step = p ** e
                t = rng.randint(1, max(1, (hi - lo) // step))
                a = b + t * step
                if a == b or a % p == 0 or a > 4 * hi:
                    continue
                return a, b, n, p

        elif mode == "pos_two_odd_n":
            # p = 2 with n odd: v_2(a^n - b^n) = v_2(a - b), so the shortcut is exact
            for _ in range(80):
                n = rng.randint(nlo, nhi)
                if n % 2 == 0:
                    n += 1
                if not (nlo <= n <= nhi):
                    continue
                b = rng.randint(lo, hi)
                a = b + rng.randint(1, max(2, hi // 2))
                if a == b:
                    continue
                return a, b, n, 2

        elif mode == "pos_coprime_odd":
            # p odd, p divides neither a-b nor a^n-b^n, and p does not divide n
            for _ in range(120):
                p = rng.choice(_ODD_PRIMES)
                n = rng.randint(nlo, nhi)
                if n % p == 0:
                    continue
                b = rng.randint(lo, hi)
                a = rng.randint(lo, hi)
                if a == b or (a - b) % p == 0 or a % p == 0 or b % p == 0:
                    continue
                return a, b, n, p

        elif mode == "neg_two_even_n":
            # p = 2 with n even: the shortcut ignores the v_2(a+b) term
            for _ in range(80):
                n = rng.randint(nlo, nhi)
                if n % 2 == 1:
                    n += 1
                if not (nlo <= n <= nhi):
                    continue
                b = rng.randint(lo, hi)
                a = b + rng.randint(1, max(2, hi // 2))
                if a == b:
                    continue
                return a, b, n, 2

        elif mode == "neg_p_divides_both":
            # p odd dividing both bases: v_p(a^n-b^n) >= n, the shortcut is small
            for _ in range(80):
                p = rng.choice(_ODD_PRIMES)
                n = rng.randint(nlo, nhi)
                bp = rng.randint(1, max(1, hi // p))
                ap = rng.randint(1, max(1, hi // p))
                a, b = p * ap, p * bp
                if a == b or a < 2 or b < 2:
                    continue
                return a, b, n, p

        elif mode == "neg_order_divides":
            # p odd, p does not divide a-b, but ord_p(a/b) | n forces p | a^n-b^n
            for _ in range(160):
                n = rng.randint(nlo, nhi)
                divisors = [d for d in range(2, n + 1) if n % d == 0]
                if not divisors:
                    continue
                d = rng.choice(divisors)
                cands = [q for q in _ODD_PRIMES if (q - 1) % d == 0 and n % q != 0]
                if not cands:
                    continue
                p = rng.choice(cands)
                g = int(primitive_root(p))
                rho = pow(g, (p - 1) // d, p)
                if rho == 1:
                    continue
                b = rng.randint(lo, hi)
                if b % p == 0:
                    continue
                target = (rho * b) % p
                if target == 0:
                    continue
                base = lo + ((target - lo) % p)
                if base > hi:
                    continue
                choices = list(range(base, hi + 1, p))
                choices = [x for x in choices if x != b and x >= 2]
                if not choices:
                    continue
                a = rng.choice(choices)
                return a, b, n, p

        elif mode == "random":
            for _ in range(80):
                p = rng.choice(_PRIMES)
                n = rng.randint(nlo, nhi)
                a = rng.randint(lo + 1, hi)
                b = rng.randint(lo, max(lo, a - 1))
                if a == b:
                    continue
                return a, b, n, p
        return None

    def _draw(
        self, rng: random.Random, difficulty: str, want_applies: Optional[bool]
    ) -> Optional[tuple]:
        if want_applies is True:
            mode = rng.choice(self.POSITIVE_MODES)
        elif want_applies is False:
            mode = rng.choice(self.NEGATIVE_MODES)
        else:
            mode = rng.choice(
                self.POSITIVE_MODES + self.NEGATIVE_MODES + ["random", "random"]
            )
        return self._draw_mode(rng, difficulty, mode)

    def sample_random(
        self,
        rng: random.Random,
        difficulty: str,
        template: str,
        want_applies: Optional[bool] = None,
    ) -> Problem:
        for _ in range(600):
            drawn = self._draw(rng, difficulty, want_applies)
            if drawn is None:
                continue
            a, b, n, p = drawn
            if a == b:
                continue
            if want_applies is not None and strategy_succeeds(a, b, n, p) != want_applies:
                continue
            return self._build(
                rng, a, b, n, p, difficulty, template, rng.randrange(2 ** 31)
            )
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

        # ---- provable impossibilities -----------------------------------
        want_size = constraints.get("exponent_size")
        if want_size is not None:
            wanted = {str(v) for v in _listify(want_size)}
            if not wanted & set(tier["sizes"]):
                raise UnsatisfiableConstraints(
                    f"difficulty '{difficulty}' only produces exponent sizes "
                    f"{tier['sizes']}",
                    constraints,
                )
        pdd = constraints.get("p_divides_difference")
        dval = constraints.get("difference_valuation")
        if pdd is not None and dval is not None:
            pdd_v = {str(v) for v in _listify(pdd)}
            dv_v = {str(v) for v in _listify(dval)}
            if pdd_v == {"yes"} and dv_v == {"0"}:
                raise UnsatisfiableConstraints(
                    "difference_valuation='0' means p does NOT divide a-b; "
                    "it contradicts p_divides_difference='yes'",
                    constraints,
                )
            if pdd_v == {"no"} and not (dv_v & {"0"}):
                raise UnsatisfiableConstraints(
                    "p_divides_difference='no' forces difference_valuation='0'",
                    constraints,
                )
        ptype = constraints.get("prime_type")
        ndivp = constraints.get("n_divisible_by_p")
        npar = constraints.get("n_parity")
        if ptype is not None and ndivp is not None and npar is not None:
            if (
                {str(v) for v in _listify(ptype)} == {"two"}
                and {str(v) for v in _listify(ndivp)} == {"yes"}
                and {str(v) for v in _listify(npar)} == {"odd"}
            ):
                raise UnsatisfiableConstraints(
                    "for p=2, n divisible by p is equivalent to n even",
                    constraints,
                )
        # ---- rejection sampling -----------------------------------------
        want_two = ptype is not None and {str(v) for v in _listify(ptype)} == {"two"}
        attempts = 0
        while attempts < 6000:
            attempts += 1
            drawn = self._draw(rng, difficulty, None)
            if drawn is None:
                continue
            a, b, n, p = drawn
            if want_two:
                p = 2
            if a == b:
                continue
            feats = self.compute_features(a, b, n, p)
            if not self.matches(feats, constraints):
                continue
            return self._build(
                rng, a, b, n, p, difficulty, template, rng.randrange(2 ** 31)
            )
        return None

    # ------------------------------------------------------------ recompute
    def recompute_answer(self, problem: Problem) -> str:
        lp = problem.latent_parameters
        return str(actual_valuation(lp["a"], lp["b"], lp["n"], lp["p"]))

    def recompute_strategy_applies(self, problem: Problem) -> bool:
        lp = problem.latent_parameters
        return strategy_succeeds(lp["a"], lp["b"], lp["n"], lp["p"])


def _listify(value: Any) -> List[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]
