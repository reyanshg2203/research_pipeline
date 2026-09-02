# FAMILY_SPEC

Exact mathematical definition of every problem family, its intended strategy S,
and its programmatic applicability oracle.

**Every heading marked `# HUMAN_REVIEW_REQUIRED` encodes a scientifically
meaningful choice that the authors must approve before a publication run.**

Notation: `v_p(x)` is the p-adic valuation of `x`; `ord_m(a)` is the
multiplicative order of `a` modulo `m`.

Nothing in this file is ever shown to a model. The models see only rendered
problem statements, the six seed solutions, and the categorical query schema.

---

## Common invariants

| property | guarantee |
|---|---|
| answers | computed by exact integer / `Fraction` / SymPy arithmetic, never by an LLM |
| `strategy_applies` | computed by a programmatic oracle, never by an LLM |
| validation | every generated problem is re-derived from its latent parameters by an independent code path (`recompute_answer`, `recompute_strategy_applies`) and a mismatch raises |
| splits | seeds, H0 pilot, hidden IID, hidden challenge and adaptation draws are checked disjoint on a mathematical `instance_key`, not on rendered text |
| balance | hidden tests default to 50/50 applicability, so a constant "always APPLIES" rule scores 0.5 |
| leakage | `strategy_applies`, `features`, `latent_parameters` and `human_solution` never enter a prompt (except seed solutions in the induction prompt) |

Run `python scripts/audit_schema.py` to see, per family and feature value, the
measured conditional probability of `strategy_applies`. Several schema values
are near-deterministic for the label; see
[Schema/label determinacy](#schemalabel-determinacy) below.

---

## Family 1 — `order_minus_one`

### Task

Problems about `a^n ≡ -1 (mod m)`.

| template | split | statement | answer |
|---|---|---|---|
| `least_n_congruence` | base | least positive `n` with `a^n ≡ -1 (mod m)`, else `NONE` | integer or `NONE` |
| `least_n_divisibility` | base | least positive `n` with `m | a^n + 1`, else `NONE` | integer or `NONE` |
| `existence` | challenge | does such an `n` exist? | `YES` / `NO` |
| `count_up_to` | challenge | how many `n ≤ L` satisfy the congruence? | integer |

### Intended strategy S1

Factor `m` into coprime prime-power components, compute multiplicative orders,
translate the exponential congruence into constraints on `n`, and decide whether
the half-order exponent produces `-1` on all components simultaneously.

### Oracle  # HUMAN_REVIEW_REQUIRED

For `m ≥ 3` and `gcd(a, m) = 1`, with `d = ord_m(a)`:

```
strategy_applies  ⇔  d is even  AND  a^(d/2) ≡ m-1 (mod m)
least n           =  d/2       when it applies
```

For `gcd(a, m) > 1` the intended strategy is not applicable at all, so
`strategy_applies = False`.

**Applicability is not the same thing as solvability.** The code never assumes
`NONE` for a non-coprime base. The exact answer is always obtained by
independent bounded cycle enumeration (`scan_least_minus_one`), which scans
`λ(m) + 96` terms of `a^n mod m` — enough to observe every value the eventually
periodic sequence ever takes. That enumeration is what `recompute_answer` uses,
so the order-based shortcut is cross-checked rather than trusted.

`tests/test_order_family.py` brute-forces the oracle against direct modular
exponentiation for **every** coprime pair with `m < 200` (over 10 000 cases),
confirms that `gcd(a,m) > 1` admits no solution for `m < 260`, and specifically
exercises the composite cases where `d` is even but `a^(d/2) ≠ -1` (over 100 of
them).

**Why the criterion is exact.** If `a^n ≡ -1` then `a^(2n) ≡ 1`, so `d | 2n`
while `d ∤ n`; hence `d` is even and `n = (d/2)k`. Writing `z = a^(d/2)`, which
has order 2, `a^n = z^k = -1` forces `z = -1` and `k` odd. So the solution set
is exactly `{n ≡ d/2 (mod d)}` and the least element is `d/2`. This also makes
`count_up_to` an arithmetic-progression count, which the tests verify.

### 2-adic alignment

For a modulus whose components are all odd prime powers, each local unit group
is cyclic and `-1` is its unique element of order 2. Writing `d_i` for the local
orders and `e_i = v_2(d_i)`, the strategy succeeds iff every `e_i` is equal and
at least 1. `tests/test_order_family.py::test_two_adic_alignment_criterion_for_cyclic_components`
verifies this on several hundred cases. The criterion is **not** used as the
oracle, because `(Z/2^k)*` is not cyclic for `k ≥ 3`; the oracle is the direct
computation above, which is valid for every modulus.

### Difficulty tiers

| tier | components | modulus size |
|---|---|---|
| easy | 1 | small (3 ≤ m < 100) |
| medium | 1–2 | small, medium (m < 3000) |
| hard | 2–3 | medium, large (100 ≤ m < 100000) |

A constraint outside the selected tier is reported as `UNSATISFIABLE_REQUEST`.

### Features exposed to Active

`modulus_structure`, `base_coprime`, `global_order_parity`,
`local_order_2adic_pattern`, `number_of_components`, `modulus_size`.
Exact numerical orders are **not** exposed.

### Deviation notes

- Spec S.7.2 template **D** ("classify possible n") is realised as
  `count_up_to`, "how many `n ≤ L`", because the solution set is the arithmetic
  progression `n ≡ d/2 (mod d)` and a count is exactly gradable where a free-text
  classification is not. The underlying boundary is unchanged.
  **# HUMAN_REVIEW_REQUIRED**
- For the `existence` challenge template, the answer to the problem coincides
  with `strategy_applies` in the coprime case, so on that template the boundary
  question and the problem question are the same question. `count_up_to` is
  included in the same split so the challenge results do not rest on that
  template alone. **# HUMAN_REVIEW_REQUIRED**

---

## Family 2 — `lte_valuation`

### Task

| template | split | statement | answer |
|---|---|---|---|
| `valuation` | base | compute `v_p(a^n - b^n)` | integer |
| `exponent_in_factorization` | base | exponent of `p` in the factorisation of `a^n - b^n` | integer |
| `largest_k` | challenge | largest `k` with `p^k | a^n - b^n` | integer |
| `factor_out_prime` | challenge | write `a^n - b^n = p^k · M`, `p ∤ M`; find `k` | integer |

All four ask for the same quantity through different surfaces, so the boundary
is identical across splits.

### Intended strategy S2

The difference form of Lifting the Exponent:
`v_p(a^n - b^n) = v_p(a-b) + v_p(n)`.

### Oracle  # HUMAN_REVIEW_REQUIRED

Applicability is **operational**, not a check of the theorem's hypotheses:

```
actual              = v_p(a^n - b^n)            (exact big-integer arithmetic)
shortcut_prediction = v_p(a - b) + v_p(n)
strategy_applies    = (actual == shortcut_prediction)
```

This deliberately admits near-boundary instances where a familiar-looking
shortcut silently returns the wrong number, and it deliberately counts as
"applies" the cases where the shortcut happens to be right for a reason outside
the theorem (for example `p ∤ (a-b)` and `p ∤ n` with both sides zero).

Ranges are bounded (`a, b ≤ 220`, `n ≤ 110`) so `a^n - b^n` stays comfortably
inside Python's big integers. `a = b` is excluded, since `v_p(0)` is undefined.

### Where the shortcut fails

`tests/test_lte_family.py` pins each of these down:

- `p` odd, `p | a-b`, `p ∤ a`, `p ∤ b` — the theorem's own hypotheses; the
  shortcut is exact (verified on >1000 cases).
- `p = 2`, `a` and `b` odd, `n` odd — `v_2(a^n-b^n) = v_2(a-b)`; shortcut exact.
  The oddness of the bases is essential: for `a=108, b=32, n=11` the true value
  is 22 and `v_2(a-b) = 2`.
- `p = 2`, `a` and `b` odd, `n` even — the true value is
  `v_2(a-b) + v_2(a+b) + v_2(n) - 1`, so the shortcut is wrong exactly when
  `v_2(a+b) ≠ 1`.
- `p | a` and `p | b` — the true valuation is at least `n`; the shortcut is small.
- `p ∤ (a-b)` but `ord_p(a b^{-1}) | n` — then `p | a^n - b^n` while the shortcut
  returns `v_p(n)`.

### Construction modes  # HUMAN_REVIEW_REQUIRED

Uniform rejection sampling collapses the negative class onto `p = 2`, which
would make the boundary trivially "p = 2 fails". The generator therefore
constructs positives and negatives at **both** prime types
(`POSITIVE_MODES` / `NEGATIVE_MODES` in `src/families/lte_valuation.py`), and
`tests/test_lte_family.py::test_prime_type_is_not_a_surrogate_for_the_label`
asserts that all four (label, prime type) combinations occur. The mode mixture
defines the adaptation distribution and therefore what "random practice" means
for the Passive condition.

### Features exposed to Active

`prime_type`, `p_divides_difference`, `p_divides_sum`, `p_divides_a_or_b`,
`n_parity`, `n_divisible_by_p`, `difference_valuation`, `exponent_size`.

`difference_valuation = 0` and `p_divides_difference = no` denote the same
condition; contradictory pairs are rejected as `UNSATISFIABLE_REQUEST` with an
explanation rather than silently reinterpreted.

---

## Family 3 — `recurrence_substitution`

### Task

A sequence of rationals satisfies `x_0 = <value>` and a rational recurrence.

| template | split | statement | answer |
|---|---|---|---|
| `compute_term` | base | `x_(n+1) = (A x_n + B)/(C x_n + D)`; compute `x_N` | reduced fraction |
| `find_index` | base | given `x_0` and a value, find the unique `N` in a stated range | integer |
| `implicit_form` | challenge | same recurrence written flat: `C x_n x_(n+1) + D x_(n+1) = A x_n + B` | reduced fraction |
| `transformed_value` | challenge | compute `1/(x_N - k)` for a stated constant `k` | reduced fraction |

### Intended strategy S3

Find a shift-and-reciprocal substitution `y_n = 1/(x_n - c)` that turns the
recurrence into an affine one, `y_(n+1) = r y_n + s`, solve that, and invert.

### Oracle  # HUMAN_REVIEW_REQUIRED — the most important review item here

```
strategy_applies  ⇔  there exists a rational c such that
                     y = 1/(x - c) turns x_(n+1) = f(x_n) into y_(n+1) = r y_n + s
                     with r ≠ 0
```

**Necessary condition (proved, and tested).** Put `y = 1/(x - c)`, so
`x = c + 1/y`. As `y → ∞` we have `x → c`, hence `y_(n+1) = 1/(f(x) - c)` tends
to the finite constant `1/(f(c) - c)` unless `f(c) = c`. An affine non-constant
map is unbounded, so a linearising shift **must** be a fixed point of `f`.

**Sufficiency for Möbius maps.** For `f(x) = (Ax+B)/(Cx+D)` the substitution
gives `y_(n+1) = (Ry + C)/(Py + Q)` with `P = Ac + B - Cc² - Dc`, which is affine
exactly when `P = 0`, and `P = 0` is precisely the fixed-point equation
`Cc² + (D-A)c - B = 0`. Hence

```
strategy_applies  ⇔  disc = (D-A)² + 4CB is a perfect square      (C ≠ 0)
```

The implementation searches the rational roots of `N(x) - x·D(x)` exactly (via
the rational root theorem, no floating point) and then verifies each candidate
symbolically with SymPy. `tests/test_recurrence_family.py` cross-checks the
oracle against the discriminant criterion, against an independent SymPy
substitution, and confirms that no non-fixed-point shift ever linearises (over
500 checks).

### Deviation from the spec's wording  # HUMAN_REVIEW_REQUIRED

Spec S.9.3 phrases the oracle as "there EXISTS the designated seed-family shift
`c`". We implement the **existential** reading — the oracle quantifies over all
rational shifts, not one privileged hidden value. Two reasons:

1. A boundary defined by a hidden designated constant that is invisible in the
   rendered problem would be unlearnable in principle, so the primary metric
   would measure nothing.
2. Several perturbations the spec suggests do **not** reliably produce
   negatives. "Alter one denominator coefficient" applied to the nested form
   `c + (x-c)/(r + s(x-c))` merely changes `r` and `s` and leaves the map exactly
   as linearisable as before; and adding a constant to the numerator often
   leaves a *different* rational fixed point behind. Under the existential
   oracle these instances get the correct label instead of a wrong one.

Consequently `strategy_applies` here means "some shift-and-reciprocal
linearisation works", which is still weaker than "no other clever substitution
exists". A recurrence with no rational fixed point may well be solvable by other
means; the family measures the boundary of *this* strategy only.

### Negative construction

Negatives are **perturbations of positives**, so they sit near the boundary:
a constant or slope change to the numerator or denominator, or an added
quadratic term. Every candidate is then re-run through the oracle, and a
perturbation that happens to remain linearisable through another rational fixed
point is kept and relabelled as a positive rather than mislabelled.

Reducible quadratics are dropped: `(-x²-3x+4)/(5x-5)` cancels to `-(x+4)/5`,
which *is* linearisable, so allowing it would render an unreduced fraction whose
degree is misleading. `tests/test_recurrence_family.py::test_generator_never_emits_a_reducible_quadratic`
enforces this.

### Rendering  # HUMAN_REVIEW_REQUIRED

All instances are rendered from the same **normalised integer coefficients**.
This matters: rendering positives as `c + (x-c)/(r + s(x-c))` and negatives as
`c + (x-c+ε)/(...)` would let a model detect the label from the presence of a
`+ε` without doing any mathematics. `implicit_form` is the second, flat surface
required by spec S.9.4(D).

Measured surface statistics at difficulty `medium` (200 of each label): mean max
coefficient 51.8 positive vs 49.8 negative, mean text length 175 vs 177, mean
horizon 4.4 vs 4.3. Answer strings are longer for negatives (mean 10.9 vs 7.8
characters) because a linearisable map has controlled orbit growth — but the
answer is **not** shown in the boundary-classification prompt, so this affects
only zero-shot solving difficulty during calibration.

A quadratic numerator is a perfect predictor of non-applicability (a genuine
degree-2 map is never linearised this way), so that perturbation is
down-weighted to roughly 1 in 13 negatives. `scripts/audit_schema.py` reports
how much of the label it explains.

### Other definitions

- **Well-definedness**: a problem is rejected if any denominator vanishes within
  the horizon, or if a term's numerator or denominator exceeds `10^12`, or if the
  orbit repeats a value (constant and periodic orbits are degenerate).
- **`singularity_risk`**: `boundary_case` when the orbit becomes undefined at
  step `N+1` or `N+2` — just outside the requested horizon — and
  `none_in_horizon` otherwise. **# HUMAN_REVIEW_REQUIRED**
- **`find_index`** guarantees the answer is the unique index in the stated range
  producing that value.

### Difficulty tiers

| tier | horizon | coefficient scale |
|---|---|---|
| easy | 3–4 | 4 |
| medium | 3–6 | 6 |
| hard | 5–8 | 8 |

---

## Schema/label determinacy

`scripts/audit_schema.py` measures `P(strategy_applies | feature = value)`.
At difficulty `medium` the following schema values (near-)determine the label:

| family | feature = value | P(applies) | note |
|---|---|---|---|
| `order_minus_one` | `base_coprime = no` | 0.00 | one-sided: `yes` does not determine success |
| `order_minus_one` | `global_order_parity = odd` | 0.00 | one-sided |
| `order_minus_one` | `local_order_2adic_pattern = aligned_positive` | 1.00 | **two-sided: this feature is the label** |
| `order_minus_one` | `local_order_2adic_pattern = misaligned` / `undefined` | 0.00 | |
| `recurrence_substitution` | `transformed_dynamics = affine` / `non_affine` | 1.00 / 0.00 | **two-sided: this feature is the label** |
| `recurrence_substitution` | `shift_structure = aligned` | 1.00 | nearly two-sided |
| `lte_valuation` | — | — | no feature value determines the label |

The two-sided cases mean the Active condition can request "give me the cases
where the strategy fails" directly, which is a much weaker experiment than
designing a falsifying probe. These features are prescribed by spec S.7.5 and
S.9.5, so the **default** `active_schema_profile: full` exposes them exactly as
written.

Set `active_schema_profile: label_decoupled` in the config to drop
`local_order_2adic_pattern` (Family 1) and `transformed_dynamics` /
`shift_structure` (Family 3) from what Active may see and constrain. Generated
problems still carry all features, and `validate_problem` still checks them
against the full schema; only the Active interface is narrowed.

**# HUMAN_REVIEW_REQUIRED — the authors must decide which profile the paper
reports, and must say so explicitly. If the `full` profile is used, any Active
advantage concentrated on these features has to be discussed rather than
presented as evidence of falsification-driven learning.**
