"""Family 1 -- exponential congruences a^n = -1 (mod m) / multiplicative order.

See docs/FAMILY_SPEC.md S.1 for the full mathematical statement and the
human-review notes.  Short version:

    For gcd(a, m) = 1 and m >= 3 let d = ord_m(a).  Then a solution of
    a^n = -1 (mod m) exists  <=>  d is even and a^(d/2) = m-1 (mod m),
    and the least such n is d/2.

    For gcd(a, m) > 1 the intended half-order strategy does not apply.  The
    actual answer is still computed independently by bounded cycle
    enumeration rather than being assumed to be NONE.

# HUMAN_REVIEW_REQUIRED
Both the applicability oracle and the feature vocabulary below encode
scientifically meaningful choices.  `tests/test_order_family.py` brute-forces
the oracle against direct modular exponentiation over tens of thousands of
cases.
"""

from __future__ import annotations

import random
from math import gcd
from typing import Any, Dict, List, Optional, Tuple

from sympy import factorint, n_order, primerange, reduced_totient

from families.base import ProblemFamily, UnsatisfiableConstraints
from schemas import Problem

# --------------------------------------------------------------------------
# prime pools
# --------------------------------------------------------------------------

_ALL_PRIMES: List[int] = list(primerange(2, 1200))
_ODD_PRIMES: List[int] = [p for p in _ALL_PRIMES if p != 2]

#: odd primes grouped by v_2(p-1); used to build multi-component moduli whose
#: local orders can share a 2-adic valuation (a necessary condition for the
#: half-order strategy to succeed on every component simultaneously).
_BY_2ADIC: Dict[int, List[int]] = {}
for _p in _ODD_PRIMES:
    _v = ((_p - 1) & -(_p - 1)).bit_length() - 1
    _BY_2ADIC.setdefault(_v, []).append(_p)

SIZE_BUCKETS: Dict[str, Tuple[int, int]] = {
    # inclusive lower bound, exclusive upper bound
    "small": (3, 100),
    "medium": (100, 3000),
    "large": (3000, 100000),
}

#: difficulty tier -> (allowed component counts, allowed size buckets)
TIERS: Dict[str, Tuple[List[str], List[str]]] = {
    "easy": (["1"], ["small"]),
    "medium": (["1", "2"], ["small", "medium"]),
    "hard": (["2", "3"], ["medium", "large"]),
}


def size_bucket(m: int) -> str:
    for name, (lo, hi) in SIZE_BUCKETS.items():
        if lo <= m < hi:
            return name
    raise ValueError(f"modulus {m} outside all size buckets")


# --------------------------------------------------------------------------
# exact arithmetic helpers -- these are the ground truth
# --------------------------------------------------------------------------


def scan_least_minus_one(a: int, m: int, extra: int = 96) -> Optional[int]:
    """Independent bounded enumeration of the least n with a^n = -1 (mod m).

    The sequence a^n mod m is eventually periodic with pre-period at most
    log2(m) and eventual period dividing lambda(m/g) for the unit part, so
    scanning lambda(m) + extra terms observes every value the sequence ever
    takes.  This function never uses the order-based shortcut, which is what
    makes it a valid cross-check of the oracle.
    """
    if m < 2:
        return None
    limit = int(reduced_totient(m)) + extra
    x = 1 % m
    target = (m - 1) % m
    for n in range(1, limit + 1):
        x = (x * a) % m
        if x == target:
            return n
    return None


def count_minus_one_upto(a: int, m: int, L: int) -> int:
    """Independent enumeration of #{1 <= n <= L : a^n = -1 (mod m)}."""
    x = 1 % m
    target = (m - 1) % m
    count = 0
    for _ in range(L):
        x = (x * a) % m
        if x == target:
            count += 1
    return count


def order_data(a: int, m: int) -> Dict[str, Any]:
    """Researcher-side order information for a coprime pair (a, m)."""
    components = sorted(q ** e for q, e in factorint(m).items())
    d = int(n_order(a, m))
    local = {str(q): int(n_order(a % q, q)) for q in components}
    return {"components": components, "global_order": d, "local_orders": local}


def strategy_succeeds(a: int, m: int) -> bool:
    """The intended half-order strategy oracle.

    # HUMAN_REVIEW_REQUIRED -- this is the definition of `strategy_applies`
    for Family 1.  For gcd(a, m) > 1 the strategy is not applicable at all.
    """
    if m < 3 or gcd(a, m) != 1:
        return False
    d = int(n_order(a, m))
    return d % 2 == 0 and pow(a, d // 2, m) == m - 1


def two_adic(n: int) -> int:
    return ((n & -n).bit_length() - 1) if n else 0


# --------------------------------------------------------------------------
# family
# --------------------------------------------------------------------------


class OrderMinusOneFamily(ProblemFamily):
    name = "order_minus_one"

    strategy_description = (
        "Factor the modulus into coprime prime-power components, compute the "
        "multiplicative order d of the base, and use the fact that a solution of "
        "a^n = -1 exists exactly when d is even and a^(d/2) = -1 on every "
        "component simultaneously, in which case the least exponent is d/2."
    )

    active_query_schema = {
        "modulus_structure": [
            "prime",
            "prime_power",
            "two_coprime_prime_power_factors",
            "three_coprime_prime_power_factors",
        ],
        "base_coprime": ["yes", "no"],
        "global_order_parity": ["even", "odd", "undefined"],
        "local_order_2adic_pattern": [
            "aligned_positive",
            "misaligned",
            "contains_odd",
            "undefined",
        ],
        "number_of_components": ["1", "2", "3"],
        "modulus_size": ["small", "medium", "large"],
    }

    label_determining_features = ["local_order_2adic_pattern"]

    base_templates = ["least_n_congruence", "least_n_divisibility"]
    challenge_templates = ["existence", "count_up_to"]

    # ---------------------------------------------------------------- features
    def compute_features(self, a: int, m: int) -> Dict[str, str]:
        comps = sorted(q ** e for q, e in factorint(m).items())
        n_comp = len(comps)
        if n_comp == 1:
            structure = "prime" if comps[0] in _ALL_PRIMES else "prime_power"
        elif n_comp == 2:
            structure = "two_coprime_prime_power_factors"
        elif n_comp == 3:
            structure = "three_coprime_prime_power_factors"
        else:
            raise ValueError(f"modulus {m} has {n_comp} components; only 1-3 supported")

        coprime = gcd(a, m) == 1
        if not coprime:
            parity = "undefined"
            pattern = "undefined"
        else:
            d = int(n_order(a, m))
            parity = "even" if d % 2 == 0 else "odd"
            local = [int(n_order(a % q, q)) for q in comps]
            if min(two_adic(x) for x in local) == 0:
                pattern = "contains_odd"
            elif d % 2 == 0 and pow(a, d // 2, m) == m - 1:
                pattern = "aligned_positive"
            else:
                pattern = "misaligned"
        return {
            "modulus_structure": structure,
            "base_coprime": "yes" if coprime else "no",
            "global_order_parity": parity,
            "local_order_2adic_pattern": pattern,
            "number_of_components": str(n_comp),
            "modulus_size": size_bucket(m),
        }

    # ---------------------------------------------------------------- sampling
    def _sample_modulus(
        self,
        rng: random.Random,
        n_components: int,
        bucket: str,
        prefer_aligned: bool,
    ) -> Optional[int]:
        lo, hi = SIZE_BUCKETS[bucket]
        for _ in range(400):
            if n_components == 1:
                p = rng.choice(_ALL_PRIMES)
                k = rng.choice([1, 1, 1, 2, 2, 3])
                m = p ** k
            else:
                if prefer_aligned:
                    # pick all primes from one 2-adic class so local orders can align
                    classes = [v for v, ps in _BY_2ADIC.items() if len(ps) >= n_components]
                    pool = _BY_2ADIC[rng.choice(classes)]
                else:
                    pool = _ALL_PRIMES
                if len(pool) < n_components:
                    continue
                primes = rng.sample(pool, n_components)
                m = 1
                for p in primes:
                    m *= p ** rng.choice([1, 1, 1, 2])
            if lo <= m < hi and m >= 3:
                if len(factorint(m)) == n_components:
                    return m
        return None

    def _sample_base(
        self, rng: random.Random, m: int, coprime: bool
    ) -> Optional[int]:
        for _ in range(600):
            a = rng.randrange(2, m)
            if (gcd(a, m) == 1) == coprime:
                return a
        return None

    def _build(
        self,
        rng: random.Random,
        a: int,
        m: int,
        difficulty: str,
        template: str,
        seed_value: int,
    ) -> Problem:
        applies = strategy_succeeds(a, m)
        features = self.compute_features(a, m)
        coprime = gcd(a, m) == 1
        info = order_data(a, m) if coprime else {"components": [], "global_order": None,
                                                 "local_orders": {}}
        least = scan_least_minus_one(a, m)

        latent: Dict[str, Any] = {
            "a": a,
            "m": m,
            "instance_key": f"{a}^n=-1 mod {m}",
            "least_n": least,
            **info,
        }

        if template == "least_n_congruence":
            text = (
                f"Find the least positive integer n such that "
                f"{a}^n ≡ -1 (mod {m}). "
                f"If no such n exists, answer NONE."
            )
            answer = str(least) if least is not None else "NONE"
        elif template == "least_n_divisibility":
            text = (
                f"Find the least positive integer n such that "
                f"{m} divides {a}^n + 1. "
                f"If no such n exists, answer NONE."
            )
            answer = str(least) if least is not None else "NONE"
        elif template == "existence":
            text = (
                f"Does there exist a positive integer n with "
                f"{a}^n ≡ -1 (mod {m})? Answer YES or NO."
            )
            answer = "YES" if least is not None else "NO"
        elif template == "count_up_to":
            period = info["global_order"] if coprime else int(reduced_totient(m))
            base = max(period, 4)
            L = rng.randint(2 * base, 5 * base)
            latent["L"] = L
            text = (
                f"How many positive integers n with n ≤ {L} satisfy "
                f"{a}^n ≡ -1 (mod {m})? Answer with a single integer."
            )
            answer = str(count_minus_one_upto(a, m, L))
        else:
            raise ValueError(f"unknown template {template!r}")

        solution = self._write_solution(a, m, applies, info, least) if applies else ""

        pid = f"{self.name}-{template}-{a}-{m}-{seed_value}"
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
        self, a: int, m: int, applies: bool, info: Dict[str, Any], least: Optional[int]
    ) -> str:
        """Worked solution for a positive instance.

        Demonstrates genuine multiplicative-order reasoning.  Deliberately does
        NOT state the full applicability boundary (spec S.7.6).
        """
        d = info["global_order"]
        comps = info["components"]
        local = info["local_orders"]
        lines = [
            f"Since gcd({a}, {m}) = 1, the base is a unit modulo {m}.",
        ]
        if len(comps) > 1:
            parts = " * ".join(str(q) for q in comps)
            locs = ", ".join(f"ord_{q}({a}) = {local[str(q)]}" for q in comps)
            lines.append(f"Factor the modulus into coprime prime powers: {m} = {parts}.")
            lines.append(f"The local multiplicative orders are {locs}.")
            lines.append(
                f"Hence the order of {a} modulo {m} is d = lcm of these = {d}."
            )
        else:
            lines.append(f"The multiplicative order of {a} modulo {m} is d = {d}.")
        lines.append(
            f"If {a}^n ≡ -1 (mod {m}) then squaring gives {a}^(2n) ≡ 1, so d | 2n, "
            f"while d does not divide n. Therefore n must be an odd multiple of d/2 = {d // 2}."
        )
        lines.append(
            f"Direct computation gives {a}^{d // 2} ≡ {m - 1} ≡ -1 (mod {m}), "
            f"so the exponent d/2 does produce -1."
        )
        lines.append(f"The least such n is therefore {least}.")
        return " ".join(lines)

    # ------------------------------------------------------------------- API
    def sample_random(
        self,
        rng: random.Random,
        difficulty: str,
        template: str,
        want_applies: Optional[bool] = None,
    ) -> Problem:
        comps_allowed, buckets_allowed = TIERS[difficulty]
        prefer_aligned = bool(want_applies)
        for _ in range(500):
            n_comp = int(rng.choice(comps_allowed))
            bucket = rng.choice(buckets_allowed)
            m = self._sample_modulus(rng, n_comp, bucket, prefer_aligned)
            if m is None:
                continue
            # non-coprime bases can never satisfy the congruence, so only draw
            # them when we are explicitly allowed to produce a negative
            coprime = True if want_applies else rng.random() > 0.18
            a = self._sample_base(rng, m, coprime)
            if a is None:
                continue
            if want_applies is not None and strategy_succeeds(a, m) != want_applies:
                continue
            return self._build(rng, a, m, difficulty, template, rng.randrange(2 ** 31))
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
        comps_allowed, buckets_allowed = TIERS[difficulty]

        # ---- provable impossibilities -----------------------------------
        want_comp = constraints.get("number_of_components")
        if want_comp is not None:
            wanted = [str(v) for v in _listify(want_comp)]
            if not set(wanted) & set(comps_allowed):
                raise UnsatisfiableConstraints(
                    f"difficulty '{difficulty}' only produces moduli with "
                    f"{comps_allowed} coprime prime-power components",
                    constraints,
                )
        want_size = constraints.get("modulus_size")
        if want_size is not None:
            wanted = [str(v) for v in _listify(want_size)]
            if not set(wanted) & set(buckets_allowed):
                raise UnsatisfiableConstraints(
                    f"difficulty '{difficulty}' only produces moduli of size "
                    f"{buckets_allowed}",
                    constraints,
                )
        struct = constraints.get("modulus_structure")
        if struct is not None:
            implied = {
                "prime": "1",
                "prime_power": "1",
                "two_coprime_prime_power_factors": "2",
                "three_coprime_prime_power_factors": "3",
            }
            need = {implied[str(v)] for v in _listify(struct)}
            if not need & set(comps_allowed):
                raise UnsatisfiableConstraints(
                    f"modulus_structure {struct!r} implies "
                    f"{sorted(need)} components, but difficulty '{difficulty}' "
                    f"only produces {comps_allowed}",
                    constraints,
                )
            if want_comp is not None and not need & set(str(v) for v in _listify(want_comp)):
                raise UnsatisfiableConstraints(
                    f"modulus_structure {struct!r} contradicts "
                    f"number_of_components {want_comp!r}",
                    constraints,
                )
        cop = constraints.get("base_coprime")
        if cop is not None:
            cop_vals = {str(v) for v in _listify(cop)}
            for key in ("global_order_parity", "local_order_2adic_pattern"):
                if key in constraints:
                    vals = {str(v) for v in _listify(constraints[key])}
                    if cop_vals == {"no"} and vals != {"undefined"}:
                        raise UnsatisfiableConstraints(
                            f"{key} is 'undefined' whenever base_coprime='no'",
                            constraints,
                        )
                    if cop_vals == {"yes"} and vals == {"undefined"}:
                        raise UnsatisfiableConstraints(
                            f"{key}='undefined' requires base_coprime='no'",
                            constraints,
                        )
        pat = constraints.get("local_order_2adic_pattern")
        par = constraints.get("global_order_parity")
        if pat is not None and par is not None:
            pats = {str(v) for v in _listify(pat)}
            pars = {str(v) for v in _listify(par)}
            if pats == {"aligned_positive"} and pars == {"odd"}:
                raise UnsatisfiableConstraints(
                    "aligned_positive requires an even global order",
                    constraints,
                )
        # ---- constructive / rejection sampling ---------------------------
        prefer_aligned = "aligned_positive" in [
            str(v) for v in _listify(constraints.get("local_order_2adic_pattern", []))
        ]
        want_noncoprime = {str(v) for v in _listify(cop)} == {"no"} if cop else False
        if pat is not None and {str(v) for v in _listify(pat)} == {"undefined"}:
            want_noncoprime = True
        if par is not None and {str(v) for v in _listify(par)} == {"undefined"}:
            want_noncoprime = True

        attempts = 0
        max_attempts = 4000
        while attempts < max_attempts:
            attempts += 1
            n_comp = int(rng.choice(comps_allowed))
            bucket = rng.choice(buckets_allowed)
            m = self._sample_modulus(rng, n_comp, bucket, prefer_aligned)
            if m is None:
                continue
            coprime = not want_noncoprime if (want_noncoprime or cop) else rng.random() > 0.3
            a = self._sample_base(rng, m, coprime)
            if a is None:
                continue
            feats = self.compute_features(a, m)
            if not self.matches(feats, constraints):
                continue
            return self._build(rng, a, m, difficulty, template, rng.randrange(2 ** 31))
        return None

    # ------------------------------------------------------------ recompute
    def recompute_answer(self, problem: Problem) -> str:
        a = problem.latent_parameters["a"]
        m = problem.latent_parameters["m"]
        t = problem.template
        if t in ("least_n_congruence", "least_n_divisibility"):
            least = scan_least_minus_one(a, m)
            return str(least) if least is not None else "NONE"
        if t == "existence":
            return "YES" if scan_least_minus_one(a, m) is not None else "NO"
        if t == "count_up_to":
            return str(count_minus_one_upto(a, m, problem.latent_parameters["L"]))
        raise ValueError(f"unknown template {t!r}")

    def recompute_strategy_applies(self, problem: Problem) -> bool:
        return strategy_succeeds(
            problem.latent_parameters["a"], problem.latent_parameters["m"]
        )


def _listify(value: Any) -> List[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]
