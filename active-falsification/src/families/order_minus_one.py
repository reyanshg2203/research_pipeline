"""Family 1 -- the half-order shortcut for a^n = -1 (mod m).

CANONICAL STRATEGY S1 (revision memo S.1) -- deliberately NARROW:

    Given a^n = -1 (mod m), compute d = ord_m(a); when d is even, use n = d/2
    as the candidate exponent.

The strategy is *only* the shortcut.  It does not include factoring the
modulus, analysing local prime-power components, or deciding on its own that no
solution exists.  Keeping it narrow is what makes DOES_NOT_APPLY meaningful: a
problem where the shortcut does not produce -1 is one the shortcut cannot
answer, whatever a fuller analysis might conclude.

APPLICABILITY ORACLE

    strategy_applies = 1  iff  gcd(a, m) = 1
                       and  d = ord_m(a) exists
                       and  d is even
                       and  a^(d/2) = -1 (mod m)

EXACT ANSWER IS COMPUTED SEPARATELY.  "The shortcut does not apply" is NOT the
same claim as "the problem has no solution", and the code never conflates them:
every answer comes from independent bounded cycle enumeration.

# HUMAN_REVIEW_REQUIRED
"""

from __future__ import annotations

import random
from math import gcd
from typing import Any, Dict, List, Optional, Tuple

from sympy import factorint, isprime, n_order, primerange, reduced_totient

from families.base import ProblemFamily, UnsatisfiableConstraints
from schemas import Problem

# --------------------------------------------------------------------------
# prime pools
# --------------------------------------------------------------------------

_ALL_PRIMES: List[int] = list(primerange(2, 1200))
_ODD_PRIMES: List[int] = [p for p in _ALL_PRIMES if p != 2]

#: odd primes grouped by v_2(p-1); used to build multi-component moduli whose
#: local orders can share a 2-adic valuation, which is what lets the half-order
#: shortcut succeed on every component at once.
_BY_2ADIC: Dict[int, List[int]] = {}
for _p in _ODD_PRIMES:
    _v = ((_p - 1) & -(_p - 1)).bit_length() - 1
    _BY_2ADIC.setdefault(_v, []).append(_p)

SIZE_BUCKETS: Dict[str, Tuple[int, int]] = {
    "small": (3, 100),
    "medium": (100, 3000),
    "large": (3000, 100000),
}

#: difficulty tier -> (allowed component counts, allowed size buckets).
#: Every tier admits composite moduli so that a seed set can contain successful
#: composite demonstrations (revision memo S.1).
TIERS: Dict[str, Tuple[List[str], List[str]]] = {
    "easy": (["1", "2"], ["small"]),
    "medium": (["1", "2"], ["small", "medium"]),
    "hard": (["2", "3"], ["medium", "large"]),
}


def size_bucket(m: int) -> str:
    for name, (lo, hi) in SIZE_BUCKETS.items():
        if lo <= m < hi:
            return name
    raise ValueError(f"modulus {m} outside all size buckets")


# --------------------------------------------------------------------------
# exact arithmetic -- ground truth
# --------------------------------------------------------------------------


def scan_least_minus_one(a: int, m: int, extra: int = 96) -> Optional[int]:
    """Independent bounded enumeration of the least n with a^n = -1 (mod m).

    The sequence a^n mod m is eventually periodic with pre-period at most
    log2(m) and eventual period dividing lambda(m), so scanning lambda(m)+extra
    terms observes every value it ever takes.  This routine never uses the
    order-based shortcut, which is what makes it a valid cross-check -- and what
    keeps "the shortcut does not apply" separate from "there is no solution".
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


def strategy_succeeds(a: int, m: int) -> bool:
    """The half-order shortcut oracle (revision memo S.1).

    # HUMAN_REVIEW_REQUIRED -- this is the definition of `strategy_applies`.
    """
    if m < 3 or gcd(a, m) != 1:
        return False
    d = int(n_order(a, m))
    return d % 2 == 0 and pow(a, d // 2, m) == m - 1


def applicability_reason(a: int, m: int) -> str:
    """Human-readable justification for the label, stored for author review."""
    if m < 3:
        return "modulus below 3: -1 is not distinct from 1, instance excluded"
    if gcd(a, m) != 1:
        return (
            f"gcd({a}, {m}) = {gcd(a, m)} > 1, so {a} is not a unit mod {m} and the "
            f"multiplicative order is undefined: the shortcut cannot be started"
        )
    d = int(n_order(a, m))
    if d % 2 != 0:
        return f"ord_{m}({a}) = {d} is odd, so there is no half-order exponent d/2"
    half = pow(a, d // 2, m)
    if half == m - 1:
        return (
            f"gcd({a}, {m}) = 1, ord_{m}({a}) = {d} is even, and "
            f"{a}^{d // 2} = {half} = -1 (mod {m}): the shortcut returns n = {d // 2}"
        )
    return (
        f"ord_{m}({a}) = {d} is even but {a}^{d // 2} = {half} != {m - 1} (mod {m}), "
        f"so the half-order exponent does not produce -1"
    )


def two_adic(n: int) -> int:
    return ((n & -n).bit_length() - 1) if n else 0


def order_data(a: int, m: int) -> Dict[str, Any]:
    components = sorted(q ** e for q, e in factorint(m).items())
    return {
        "components": components,
        "global_order": int(n_order(a, m)),
        "local_orders": {str(q): int(n_order(a % q, q)) for q in components},
    }


# --------------------------------------------------------------------------
# family
# --------------------------------------------------------------------------


class OrderMinusOneFamily(ProblemFamily):
    name = "order_minus_one"

    strategy_description = (
        "Half-order shortcut: for a^n = -1 (mod m), compute d = ord_m(a) and, when "
        "d is even, take n = d/2 as the candidate exponent."
    )

    #: Observable controls Active may request.  Each is readable off the problem
    #: statement: the modulus factors, how many factors there are, whether the
    #: base shares a factor with the modulus, and how big the modulus is.
    queryable_features = {
        "modulus_type": ["prime", "prime_power", "composite"],
        "number_of_factors": ["1", "2", "3"],
        "base_coprime": ["yes", "no"],
        "modulus_size": ["small", "medium", "large"],
    }

    #: Researcher-only.  `half_order_gives_minus_one` and
    #: `local_order_2adic_pattern` are deterministic synonyms for the label,
    #: which is exactly why they are confined to this namespace.
    oracle_feature_schema = {
        "global_order_parity": ["even", "odd", "undefined"],
        "local_order_2adic_pattern": [
            "aligned_positive",
            "misaligned",
            "contains_odd",
            "undefined",
        ],
        "half_order_gives_minus_one": ["yes", "no", "undefined"],
        "solution_exists": ["yes", "no"],
    }

    base_templates = ["least_n_congruence", "least_n_divisibility"]
    challenge_templates = ["existence", "count_up_to"]

    # ---------------------------------------------------------------- features
    def compute_query_features(self, a: int, m: int, template: str) -> Dict[str, str]:
        comps = sorted(q ** e for q, e in factorint(m).items())
        n_comp = len(comps)
        if n_comp == 1:
            modulus_type = "prime" if isprime(m) else "prime_power"
        else:
            modulus_type = "composite"
        return {
            "modulus_type": modulus_type,
            "number_of_factors": str(n_comp),
            "base_coprime": "yes" if gcd(a, m) == 1 else "no",
            "modulus_size": size_bucket(m),
            "task_form": template,
        }

    def compute_oracle_features(self, a: int, m: int) -> Dict[str, str]:
        comps = sorted(q ** e for q, e in factorint(m).items())
        coprime = gcd(a, m) == 1
        if not coprime:
            parity = pattern = half = "undefined"
        else:
            d = int(n_order(a, m))
            parity = "even" if d % 2 == 0 else "odd"
            local = [int(n_order(a % q, q)) for q in comps]
            if d % 2 == 0:
                half = "yes" if pow(a, d // 2, m) == m - 1 else "no"
            else:
                half = "undefined"
            if min(two_adic(x) for x in local) == 0:
                pattern = "contains_odd"
            elif half == "yes":
                pattern = "aligned_positive"
            else:
                pattern = "misaligned"
        return {
            "global_order_parity": parity,
            "local_order_2adic_pattern": pattern,
            "half_order_gives_minus_one": half,
            "solution_exists": "yes" if scan_least_minus_one(a, m) is not None else "no",
        }

    # ---------------------------------------------------------------- sampling
    def _sample_modulus(
        self, rng: random.Random, n_components: int, bucket: str, prefer_aligned: bool,
        modulus_type: Optional[str] = None,
    ) -> Optional[int]:
        lo, hi = SIZE_BUCKETS[bucket]
        for _ in range(500):
            if n_components == 1:
                p = rng.choice(_ALL_PRIMES)
                if modulus_type == "prime":
                    k = 1
                elif modulus_type == "prime_power":
                    k = rng.choice([2, 2, 3])
                else:
                    k = rng.choice([1, 1, 1, 2, 2, 3])
                m = p ** k
            else:
                if prefer_aligned:
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
            if lo <= m < hi and m >= 3 and len(factorint(m)) == n_components:
                return m
        return None

    def _sample_base(self, rng: random.Random, m: int, coprime: bool) -> Optional[int]:
        for _ in range(600):
            a = rng.randrange(2, m)
            if (gcd(a, m) == 1) == coprime:
                return a
        return None

    def _build(
        self, rng: random.Random, a: int, m: int, difficulty: str, template: str,
        seed_value: int,
    ) -> Problem:
        applies = strategy_succeeds(a, m)
        coprime = gcd(a, m) == 1
        info = order_data(a, m) if coprime else {
            "components": [], "global_order": None, "local_orders": {}
        }
        least = scan_least_minus_one(a, m)

        latent: Dict[str, Any] = {
            "a": a, "m": m,
            "instance_key": f"{a}^n=-1 mod {m}",
            "least_n_independently_enumerated": least,
            "shortcut_candidate_exponent": (
                info["global_order"] // 2
                if coprime and info["global_order"] % 2 == 0 else None
            ),
            **info,
        }

        if template == "least_n_congruence":
            text = (f"Find the least positive integer n such that {a}^n ≡ -1 (mod {m}). "
                    f"If no such n exists, answer NONE.")
            answer = str(least) if least is not None else "NONE"
        elif template == "least_n_divisibility":
            text = (f"Find the least positive integer n such that {m} divides {a}^n + 1. "
                    f"If no such n exists, answer NONE.")
            answer = str(least) if least is not None else "NONE"
        elif template == "existence":
            text = (f"Does there exist a positive integer n with {a}^n ≡ -1 (mod {m})? "
                    f"Answer YES or NO.")
            answer = "YES" if least is not None else "NO"
        elif template == "count_up_to":
            period = info["global_order"] if coprime else int(reduced_totient(m))
            base = max(period or 4, 4)
            L = rng.randint(2 * base, 5 * base)
            latent["L"] = L
            text = (f"How many positive integers n with n ≤ {L} satisfy "
                    f"{a}^n ≡ -1 (mod {m})? Answer with a single integer.")
            answer = str(count_minus_one_upto(a, m, L))
        else:
            raise ValueError(f"unknown template {template!r}")

        return Problem(
            id=f"{self.name}-{template}-{a}-{m}-{seed_value}",
            family=self.name,
            template=template,
            difficulty=difficulty,
            text=text,
            exact_answer=answer,
            strategy_applies=applies,
            query_features=self.compute_query_features(a, m, template),
            oracle_features=self.compute_oracle_features(a, m),
            applicability_reason=applicability_reason(a, m),
            human_solution=self._write_solution(a, m, info, least) if applies else "",
            latent_parameters=latent,
            generation_seed=seed_value,
        )

    def _write_solution(
        self, a: int, m: int, info: Dict[str, Any], least: Optional[int]
    ) -> str:
        """Worked solution demonstrating the NARROW half-order shortcut.

        It computes the order, checks the half-order power, and justifies
        minimality.  It deliberately does not walk through prime-power
        components, and it does not state the applicability boundary.
        """
        d = info["global_order"]
        return " ".join([
            f"Since gcd({a}, {m}) = 1, the base is a unit modulo {m}, "
            f"so its multiplicative order is defined.",
            f"Computing it gives d = ord_{m}({a}) = {d}, which is even.",
            f"Try the half-order exponent d/2 = {d // 2}: "
            f"{a}^{d // 2} ≡ {m - 1} ≡ -1 (mod {m}).",
            f"So n = {d // 2} works. It is the least such n, because "
            f"{a}^n ≡ -1 forces {a}^(2n) ≡ 1, hence d | 2n while d does not divide n, "
            f"so n must be a multiple of d/2.",
            f"The answer is {least}.",
        ])

    # ------------------------------------------------------------------- API
    def sample_random(
        self, rng: random.Random, difficulty: str, template: str,
        want_applies: Optional[bool] = None,
    ) -> Problem:
        comps_allowed, buckets_allowed = TIERS[difficulty]
        for _ in range(600):
            n_comp = int(rng.choice(comps_allowed))
            bucket = rng.choice(buckets_allowed)
            m = self._sample_modulus(rng, n_comp, bucket, prefer_aligned=bool(want_applies))
            if m is None:
                continue
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
        self, rng: random.Random, constraints: Dict[str, str], difficulty: str,
        template: str,
    ) -> Optional[Problem]:
        self.check_constraints_wellformed(constraints)
        comps_allowed, buckets_allowed = TIERS[difficulty]
        template = self.requested_template(constraints, template)

        want_comp = constraints.get("number_of_factors")
        if want_comp is not None:
            wanted = {str(v) for v in _listify(want_comp)}
            if not wanted & set(comps_allowed):
                raise UnsatisfiableConstraints(
                    f"difficulty '{difficulty}' only produces moduli with "
                    f"{comps_allowed} prime-power factors", constraints)
        want_size = constraints.get("modulus_size")
        if want_size is not None:
            wanted = {str(v) for v in _listify(want_size)}
            if not wanted & set(buckets_allowed):
                raise UnsatisfiableConstraints(
                    f"difficulty '{difficulty}' only produces moduli of size "
                    f"{buckets_allowed}", constraints)
        mtype = constraints.get("modulus_type")
        if mtype is not None:
            implied = {"prime": {"1"}, "prime_power": {"1"}, "composite": {"2", "3"}}
            need: set = set()
            for v in _listify(mtype):
                need |= implied[str(v)]
            if not need & set(comps_allowed):
                raise UnsatisfiableConstraints(
                    f"modulus_type {mtype!r} implies {sorted(need)} prime-power "
                    f"factors, but difficulty '{difficulty}' only produces "
                    f"{comps_allowed}", constraints)
            if want_comp is not None:
                if not need & {str(v) for v in _listify(want_comp)}:
                    raise UnsatisfiableConstraints(
                        f"modulus_type {mtype!r} contradicts number_of_factors "
                        f"{want_comp!r}", constraints)
            if {str(v) for v in _listify(mtype)} == {"prime"} and want_size is not None:
                pass  # every size bucket contains primes

        mtypes = {str(v) for v in _listify(mtype)} if mtype else None
        force_single = mtypes is not None and mtypes <= {"prime", "prime_power"}
        cop = constraints.get("base_coprime")
        want_noncoprime = (
            cop is not None and {str(v) for v in _listify(cop)} == {"no"}
        )

        for _ in range(6000):
            if force_single:
                n_comp = 1 if "1" in comps_allowed else int(rng.choice(comps_allowed))
            elif want_comp is not None:
                options = [v for v in {str(x) for x in _listify(want_comp)}
                           if v in comps_allowed]
                n_comp = int(rng.choice(options))
            else:
                n_comp = int(rng.choice(comps_allowed))
            if want_size is not None:
                options_b = [v for v in {str(x) for x in _listify(want_size)}
                             if v in buckets_allowed]
                bucket = rng.choice(options_b)
            else:
                bucket = rng.choice(buckets_allowed)
            single_type = (
                list(mtypes)[0] if (mtypes and len(mtypes) == 1 and force_single) else None
            )
            m = self._sample_modulus(rng, n_comp, bucket, False, single_type)
            if m is None:
                continue
            coprime = not want_noncoprime if cop else rng.random() > 0.3
            a = self._sample_base(rng, m, coprime)
            if a is None:
                continue
            feats = self.compute_query_features(a, m, template)
            if not self.matches(feats, constraints):
                continue
            return self._build(rng, a, m, difficulty, template, rng.randrange(2 ** 31))
        return None

    # ------------------------------------------------------------ seed strata
    def seed_strata(self, n_seeds: int) -> List[Dict[str, str]]:
        """Revision memo S.1: successful seeds must not all have prime moduli.

        Target roughly 2 primes, 1 prime power and 3 composites so the model
        cannot induce "the shortcut works exactly when the modulus is prime".
        """
        pattern = ["prime", "prime", "prime_power", "composite", "composite", "composite"]
        return [{"modulus_type": pattern[i % len(pattern)]} for i in range(n_seeds)]

    # ---------------------------------------------------------------- preview
    def preview_extras(self, problem: Problem) -> Dict[str, str]:
        lp = problem.latent_parameters
        return {
            "multiplicative_order": str(lp.get("global_order")),
            "shortcut_candidate_exponent": str(lp.get("shortcut_candidate_exponent")),
            "least_n_independently_enumerated": str(
                lp.get("least_n_independently_enumerated")
            ),
            "local_orders": str(lp.get("local_orders")),
        }

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
