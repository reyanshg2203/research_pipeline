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

from sympy import (
    factorint,
    isprime,
    n_order,
    primerange,
    primitive_root,
    reduced_totient,
    totient,
)

from families.base import ProblemFamily, UnsatisfiableConstraints
from sampling import derive_seed
from schemas import Problem

# --------------------------------------------------------------------------
# component pools
# --------------------------------------------------------------------------
#
# DIFFICULTY IS STRUCTURAL, NOT NUMERICAL.
#
# For m a product of coprime ODD prime powers q_i and gcd(a, m) = 1, each local
# unit group is cyclic, so -1 is its unique element of order 2 and
#
#     a^(d/2) = -1 (mod m)   <=>   all v_2(ord_{q_i}(a)) are equal and >= 1
#
# where d = ord_m(a).  So the outcome is decided entirely by whether the local
# 2-adic valuations AGREE -- not by how large m is.  The tiers below vary that
# agreement structure and the number of components; modulus size is a
# consequence of the structure, not the difficulty knob.
#
# Drawing a base uniformly at random from a multi-component modulus makes the
# valuations disagree almost always, which is why an unstructured "hard" tier
# degenerates into nearly all NONE.  Instances are therefore CONSTRUCTED to a
# chosen valuation profile and then checked by the independent oracle.
#
# HUMAN_REVIEW_REQUIRED

_ALL_PRIMES: List[int] = list(primerange(2, 1200))
_ODD_PRIMES: List[int] = [p for p in _ALL_PRIMES if p != 2]


def two_adic(n: int) -> int:
    return ((n & -n).bit_length() - 1) if n else 0


#: odd prime powers q = p^k, grouped by v_2(phi(q)) = v_2(p-1).  A component can
#: host a local order with 2-adic valuation e for any 0 <= e <= v_2(phi(q)).
_PRIME_POWERS_BY_V2: Dict[int, List[int]] = {}
_COMPONENT_PRIME: Dict[int, int] = {}
for _p in _ODD_PRIMES:
    _v = two_adic(_p - 1)
    for _k in (1, 2, 3):
        _q = _p ** _k
        if _q > 300000:
            break
        _PRIME_POWERS_BY_V2.setdefault(_v, []).append(_q)
        _COMPONENT_PRIME[_q] = _p
_ALL_COMPONENTS: List[int] = sorted(_COMPONENT_PRIME)

#: components able to host local 2-adic valuation at least e
_COMPONENTS_WITH_V2_AT_LEAST: Dict[int, List[int]] = {
    e: sorted(q for v, qs in _PRIME_POWERS_BY_V2.items() if v >= e for q in qs)
    for e in range(0, 6)
}

SIZE_BUCKETS: Dict[str, Tuple[int, int]] = {
    "small": (3, 200),
    "medium": (200, 20000),
    "large": (20000, 500000),
}

#: difficulty tier -> (allowed component counts, allowed size buckets)
TIERS: Dict[str, Tuple[List[str], List[str]]] = {
    "easy": (["1", "2"], ["small"]),
    "medium": (["2"], ["medium"]),
    "hard": (["2", "3"], ["medium", "large"]),
}

#: Per-tier construction plan.  ``components`` is drawn from with replacement,
#: so easy is mostly single-component with the occasional two-component case.
TIER_PLAN: Dict[str, Dict[str, Any]] = {
    "easy": {
        "components": [1, 1, 1, 1, 2],
        "max_e": 2,
        "allow_non_coprime_negatives": True,
        "require_nontrivial_two_component": False,
    },
    "medium": {
        "components": [2],
        "max_e": 3,
        "allow_non_coprime_negatives": False,
        "require_nontrivial_two_component": False,
    },
    "hard": {
        # three components preferred; two-component cases must be structurally
        # nontrivial (a true prime power, or a common valuation of at least 2)
        "components": [3, 3, 3, 2],
        "max_e": 4,
        "allow_non_coprime_negatives": False,
        "require_nontrivial_two_component": True,
    },
}

#: keep independent cycle enumeration and the count template affordable
MAX_CARMICHAEL_FOR_ENUMERATION = 200000
MAX_COUNT_TEMPLATE_LIMIT = 200000


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


# --------------------------------------------------------------------------
# structured construction: build an instance to a chosen valuation profile
# --------------------------------------------------------------------------


def element_with_2adic_valuation(
    q: int, e: int, rng: random.Random
) -> Optional[int]:
    """A unit modulo the odd prime power ``q`` whose order has v_2 exactly ``e``.

    ``(Z/q)*`` is cyclic of order N = phi(q).  Writing g for a primitive root,
    ``g^t`` has order ``N / gcd(N, t)``, whose 2-adic valuation is
    ``v_2(N) - min(v_2(N), v_2(t))``.  Choosing ``t = 2^(v_2(N) - e) * u`` with
    ``u`` odd therefore pins the valuation to exactly ``e``, while ``u`` varies
    the odd part so the orders are not all the same shape.
    """
    n_units = int(totient(q))
    v2_units = two_adic(n_units)
    if e > v2_units or n_units < 2:
        return None
    g = int(primitive_root(q))
    for _ in range(12):
        u = rng.randrange(1, max(3, n_units), 2)
        a = pow(g, (2 ** (v2_units - e)) * u, q)
        if a > 1:
            return a
    return None


def crt_combine(residues: List[int], moduli: List[int]) -> Tuple[int, int]:
    """Exact CRT over pairwise-coprime moduli.  Returns (residue, product)."""
    x, modulus = 0, 1
    for r, q in zip(residues, moduli):
        # solve x = r (mod q) keeping x = current value (mod modulus)
        step = modulus
        target = r % q
        while x % q != target:
            x += step
        modulus *= q
    return x, modulus


def build_instance(
    rng: random.Random, components: List[int], valuations: List[int]
) -> Optional[Tuple[int, int]]:
    """Construct (a, m) with ord_{q_i}(a) having 2-adic valuation valuations[i].

    By the equivalence at the top of this module the outcome is then decided:
    equal, positive valuations succeed; anything else fails.  The caller still
    passes the result through the independent oracle.
    """
    parts = [
        element_with_2adic_valuation(q, e, rng)
        for q, e in zip(components, valuations)
    ]
    if any(part is None for part in parts):
        return None
    a, m = crt_combine([int(x) for x in parts], components)
    if a <= 1 or m < 3 or gcd(a, m) != 1:
        return None
    return a, m


def _pick_components(
    rng: random.Random,
    n_components: int,
    valuations: List[int],
    size_lo: int,
    size_hi: int,
    require_prime_power: bool = False,
) -> Optional[List[int]]:
    """Distinct odd prime powers hosting the requested valuations, sized to fit.

    Components are chosen against a running size budget rather than picked
    freely and rejected afterwards.  Choosing freely makes three-component
    moduli overshoot the window most of the time, which silently biases the hard
    tier back towards two components -- the very degeneracy this redesign is
    meant to remove.
    """
    for _ in range(400):
        chosen: List[int] = []
        used_primes: set = set()
        product = 1
        order = list(range(n_components))
        # place the most constrained valuation first: it has the smallest pool
        order.sort(key=lambda i: -valuations[i])
        placed: Dict[int, int] = {}
        ok = True
        for position, index in enumerate(order):
            e = valuations[index]
            pool = _COMPONENTS_WITH_V2_AT_LEAST.get(e)
            if not pool:
                return None
            remaining = n_components - position - 1
            # leave room for the components still to come (each at least 3)
            budget = size_hi // (product * (3 ** remaining) or 1)
            candidates = [
                q for q in pool
                if q <= budget and _COMPONENT_PRIME[q] not in used_primes
            ]
            if not candidates:
                ok = False
                break
            q = rng.choice(candidates)
            used_primes.add(_COMPONENT_PRIME[q])
            placed[index] = q
            product *= q
        if not ok or len(placed) != n_components:
            continue
        if not (size_lo <= product < size_hi):
            continue
        chosen = [placed[i] for i in range(n_components)]
        if require_prime_power and not any(
            q != _COMPONENT_PRIME[q] for q in chosen
        ):
            continue
        if int(reduced_totient(product)) > MAX_CARMICHAEL_FOR_ENUMERATION:
            continue
        return chosen
    return None


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
            L = min(rng.randint(2 * base, 5 * base), MAX_COUNT_TEMPLATE_LIMIT)
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
    def _valuation_profile(
        self, rng: random.Random, difficulty: str, n_components: int,
        want_finite: bool,
    ) -> Optional[List[int]]:
        """Local 2-adic valuations realising the requested outcome.

        Equal and positive  -> the half-order shortcut succeeds, so the problem
                               has a genuine finite least n.
        Unequal, all >= 1   -> NEAR-BOUNDARY failure: the base is coprime, the
                               global order is even, every local order is even,
                               and the shortcut still fails purely because the
                               valuations disagree.
        Contains a zero     -> a local order is odd; an easier failure, used
                               only where the tier calls for straightforward
                               cases.
        """
        plan = TIER_PLAN[difficulty]
        max_e = plan["max_e"]
        if want_finite:
            e = rng.randint(1, max_e)
            return [e] * n_components
        if n_components == 1:
            # a single component cannot disagree with itself: the only coprime
            # failure available is an odd local order
            return [0]
        if difficulty == "easy" and rng.random() < 0.35:
            profile = [rng.randint(1, max_e) for _ in range(n_components)]
            profile[rng.randrange(n_components)] = 0
            return profile
        # near-boundary: all valuations at least 1, but not all equal
        for _ in range(40):
            profile = [rng.randint(1, max_e) for _ in range(n_components)]
            if len(set(profile)) > 1:
                return profile
        return None

    def _construct(
        self, rng: random.Random, difficulty: str, want_finite: Optional[bool]
    ) -> Optional[Tuple[int, int]]:
        """Draw one (a, m) for this tier, targeting a finite answer or NONE."""
        plan = TIER_PLAN[difficulty]
        comps_allowed, buckets_allowed = TIERS[difficulty]
        if want_finite is None:
            want_finite = rng.random() < 0.5

        # a small share of straightforward non-coprime failures, easy tier only
        if (not want_finite and plan["allow_non_coprime_negatives"]
                and rng.random() < 0.25):
            bucket = rng.choice(buckets_allowed)
            lo, hi = SIZE_BUCKETS[bucket]
            n_comp = int(rng.choice(comps_allowed))
            m = self._sample_modulus(rng, n_comp, bucket, False)
            if m is not None:
                a = self._sample_base(rng, m, coprime=False)
                if a is not None:
                    return a, m
            return None

        n_components = rng.choice(plan["components"])
        if str(n_components) not in comps_allowed:
            n_components = int(rng.choice(comps_allowed))
        profile = self._valuation_profile(rng, difficulty, n_components, want_finite)
        if profile is None:
            return None
        bucket = rng.choice(buckets_allowed)
        lo, hi = SIZE_BUCKETS[bucket]
        require_prime_power = bool(
            plan["require_nontrivial_two_component"]
            and n_components == 2
            and max(profile) < 2
        )
        components = _pick_components(
            rng, n_components, profile, lo, hi, require_prime_power
        )
        if components is None:
            return None
        return build_instance(rng, components, profile)

    def sample_random(
        self, rng: random.Random, difficulty: str, template: str,
        want_applies: Optional[bool] = None,
    ) -> Problem:
        for _ in range(800):
            drawn = self._construct(rng, difficulty, want_applies)
            if drawn is None:
                continue
            a, m = drawn
            if want_applies is not None and strategy_succeeds(a, m) != want_applies:
                continue
            return self._build(rng, a, m, difficulty, template, rng.randrange(2 ** 31))
        raise RuntimeError(
            f"{self.name}: sample_random exhausted (difficulty={difficulty}, "
            f"want_applies={want_applies})"
        )

    # ------------------------------------------------- Stage-1 calibration
    def calibration_plan(self, per_tier: int, difficulty: str) -> List[Optional[bool]]:
        """Half genuine finite answers, half NONE, in a deterministic order.

        Stated in terms of the PUBLIC EXACT ANSWER, not the applicability label:
        a slot asks for "an instance whose answer is a number" or "an instance
        whose answer is NONE".  The model is never told which is which, and the
        balance is not recorded on any row it can see.
        """
        n_finite = (per_tier + 1) // 2
        plan: List[Optional[bool]] = [True] * n_finite + [False] * (per_tier - n_finite)
        random.Random(derive_seed(0, "order_minus_one_plan", difficulty, per_tier)).shuffle(plan)
        return plan

    def sample_for_calibration(
        self, rng: random.Random, difficulty: str, template: str,
        slot_index: int, per_tier: int,
    ) -> Problem:
        plan = self.calibration_plan(per_tier, difficulty)
        want_finite = plan[slot_index % len(plan)]
        return self._sample_with_answer_kind(rng, difficulty, template, want_finite)

    def _sample_with_answer_kind(
        self, rng: random.Random, difficulty: str, template: str,
        want_finite: Optional[bool],
    ) -> Problem:
        """Draw until the PUBLIC EXACT ANSWER is of the requested kind.

        The acceptance test reads ``scan_least_minus_one``, the independent
        cycle enumeration, so it is a statement about the answer rather than
        about the applicability oracle.
        """
        for _ in range(1200):
            drawn = self._construct(rng, difficulty, want_finite)
            if drawn is None:
                continue
            a, m = drawn
            if want_finite is not None:
                has_answer = scan_least_minus_one(a, m) is not None
                if has_answer != want_finite:
                    continue
            return self._build(rng, a, m, difficulty, template, rng.randrange(2 ** 31))
        raise RuntimeError(
            f"{self.name}: could not draw a calibration problem with "
            f"finite_answer={want_finite} at difficulty={difficulty}"
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
        components = lp.get("components") or []
        local = lp.get("local_orders") or {}
        m = lp["m"]
        factorisation = " * ".join(
            (f"{q}" if q in components and q == _COMPONENT_PRIME.get(q, q)
             else f"{q}")
            for q in components
        ) or str(m)
        pretty = " * ".join(
            f"{base}^{exp}" if exp > 1 else f"{base}"
            for base, exp in sorted(factorint(m).items())
        )
        d = lp.get("global_order")
        half_ok = "n/a (base not coprime to m)"
        if d is not None:
            half_ok = (
                f"yes: {lp['a']}^{d // 2} = {m - 1} = -1 (mod {m})"
                if problem.strategy_applies
                else (
                    f"no: order is odd, there is no half-order exponent"
                    if d % 2 else
                    f"no: {lp['a']}^{d // 2} = {pow(lp['a'], d // 2, m)} != -1 (mod {m})"
                )
            )
        return {
            "factorisation_of_m": pretty,
            "components": str(components) if components else "n/a (not coprime)",
            "local_orders": (
                ", ".join(f"ord_{q}({lp['a']}) = {local[str(q)]}"
                          for q in components)
                if local else "n/a (base not coprime to m)"
            ),
            "local_order_2adic_valuations": (
                ", ".join(f"v_2(ord_{q}) = {two_adic(local[str(q)])}"
                          for q in components)
                if local else "n/a"
            ),
            "global_order": str(d) if d is not None else "undefined (not coprime)",
            "half_order_succeeds": half_ok,
            "shortcut_candidate_exponent": str(lp.get("shortcut_candidate_exponent")),
            "least_n_independently_enumerated": str(
                lp.get("least_n_independently_enumerated")
            ),
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
