# FAMILY_SPEC

Exact mathematical definition of every problem family, its intended strategy S,
and its programmatic applicability oracle.

**Every heading marked `# HUMAN_REVIEW_REQUIRED` encodes a scientifically
meaningful choice that the authors must approve before a publication run.**

Notation: `v_p(x)` is the p-adic valuation of `x`; `ord_m(a)` is the
multiplicative order of `a` modulo `m`.

Nothing in this file is ever shown to a model. Models see only rendered problem
statements, the six seed solutions, and the query schema.

---

## Three concepts, three names

The code never conflates these, and never uses a bare `success` or `correct`:

| concept | field |
|---|---|
| the correct answer to the mathematical problem as posed | `exact_answer` |
| whether the intended strategy S is mathematically applicable | `strategy_applies` |
| whether a tested model solved a problem on some run | `model_answer_correct` |
| whether a tested model predicted the boundary correctly | `model_boundary_correct` |

`strategy_applies` is *never* inferred from `exact_answer`, and "the strategy
does not apply" is *never* treated as "the problem has no solution".

## Two feature namespaces

| namespace | field | who sees it |
|---|---|---|
| observable experimental controls | `query_features` | the Active condition may request these |
| researcher-side diagnostics | `oracle_features` | validation, balancing and audit only — never any model |

Every query feature is readable off the problem statement by a competent
solver, so selecting a region is a genuine experiment rather than a lookup.
Several oracle features are deterministic synonyms for `strategy_applies`; that
is exactly why they live in the second namespace. Asking for one in an Active
constraint returns `unknown feature name`, so the model never learns they exist.

Run `python scripts/audit_schema.py` to measure this. Its pass criterion: **no
query feature may be a label synonym**, i.e. no feature whose every supported
value is pure and whose values cover both classes. One-sided implications (one
pure value, e.g. "p = 2 always fails") are allowed and reported — they are
genuine observable mathematics the model has to learn.

## Common invariants

| property | guarantee |
|---|---|
| answers | exact integer / `Fraction` / SymPy arithmetic, never an LLM |
| `strategy_applies` | a programmatic oracle, never an LLM, never a generator flag |
| validation | every problem is re-derived by an independent code path; a mismatch raises |
| splits | seeds, H0 pilot, hidden IID, hidden challenge and adaptation draws are checked disjoint on a mathematical `instance_key` |
| balance | hidden tests default to 50/50, so a constant "always APPLIES" rule scores 0.5 |
| reasons | every problem carries an `applicability_reason` naming the condition that holds or fails |

---

## Family 1 — `order_minus_one`

### Canonical strategy S1 — the half-order shortcut  # HUMAN_REVIEW_REQUIRED

> For a problem of the form `a^n ≡ -1 (mod m)`, compute `d = ord_m(a)` and, when
> `d` is even, use `n = d/2` as the candidate exponent.

The strategy is **only the shortcut**. It deliberately does not include
factoring the modulus, analysing local prime-power components, or concluding on
its own that no solution exists. Keeping it narrow is what makes
`DOES_NOT_APPLY` meaningful: a broader "strategy" that already contains the full
compatibility test could always answer correctly by concluding `NONE`, and then
non-applicability would have no content.

### Oracle

```
strategy_applies = 1  iff  gcd(a, m) = 1
                   and  d = ord_m(a) exists
                   and  d is even
                   and  a^(d/2) ≡ -1 (mod m)
```

### The exact answer is computed separately

`scan_least_minus_one` enumerates `λ(m) + 96` terms of `a^n mod m` — enough to
observe every value the eventually periodic sequence ever takes — and never
touches the order-based shortcut. `recompute_answer` uses that enumeration, so
the answer is an independent cross-check rather than a consequence of the label.

`tests/test_order_family.py` covers, per revision memo §7:

- prime modulus with even order ⇒ the half-order power is `-1` (>200 cases);
- composite modulus with even *global* order can still fail (>50 cases);
- successful composite cases exist, across ≥6 distinct moduli (>50 cases);
- non-coprime bases: the answer comes from independent brute force, and the
  label is `False` without assuming `NONE`;
- the oracle agrees with direct modular verification for **every** coprime pair
  with `m < 200` (>10 000 cases).

**Why the enumeration and the shortcut agree when they do.** If `a^n ≡ -1` then
`a^(2n) ≡ 1`, so `d | 2n` while `d ∤ n`; hence `d` is even and `n = (d/2)k`.
Writing `z = a^(d/2)`, which has order 2, `a^n = z^k = -1` forces `z = -1` and
`k` odd. The solution set is exactly `{n ≡ d/2 (mod d)}`, which also makes
`count_up_to` an arithmetic-progression count.

### Templates

| template | split | statement | answer |
|---|---|---|---|
| `least_n_congruence` | base | least `n` with `a^n ≡ -1 (mod m)`, else `NONE` | integer / `NONE` |
| `least_n_divisibility` | base | least `n` with `m │ a^n + 1`, else `NONE` | integer / `NONE` |
| `existence` | challenge | does such an `n` exist? | `YES` / `NO` |
| `count_up_to` | challenge | how many `n ≤ L`? | integer |

### Query features (shown to Active)

`modulus_type` (prime / prime_power / composite), `number_of_factors` (1/2/3),
`base_coprime` (yes/no), `modulus_size` (small/medium/large), `task_form`.
Exact orders are **not** exposed.

### Oracle features (researcher-only)

`global_order_parity`, `local_order_2adic_pattern`, `half_order_gives_minus_one`,
`solution_exists`. The last two are exact label synonyms.

### Seed distribution  # HUMAN_REVIEW_REQUIRED

Revision memo §1: successful seeds must not all have prime moduli, or the model
can induce "the shortcut works exactly when the modulus is prime" from the
demonstrations alone. `seed_strata` targets **2 prime, 1 prime power, 3
composite**, and every difficulty tier admits composite moduli so this is
reachable at any selected tier. A test asserts at least 2 composite and at
least 1 prime seed.

### Difficulty tiers

| tier | prime-power factors | modulus size |
|---|---|---|
| easy | 1–2 | small (3 ≤ m < 100) |
| medium | 1–2 | small, medium (m < 3000) |
| hard | 2–3 | medium, large (100 ≤ m < 100000) |

### Deviation notes

- Template **D** of the original spec ("classify possible n") is realised as
  `count_up_to`, because the solution set is the arithmetic progression
  `n ≡ d/2 (mod d)` and a count is exactly gradable where free text is not.
  The boundary is unchanged. **# HUMAN_REVIEW_REQUIRED**
- On the `existence` challenge template the answer coincides with
  `strategy_applies` in the coprime case, so there the boundary question and the
  problem question are the same question. `count_up_to` shares the split so the
  challenge results do not rest on that template alone.
  **# HUMAN_REVIEW_REQUIRED**

---

## Family 2 — `lte_valuation`

### Canonical strategy S2

> Odd-prime difference form of Lifting the Exponent:
> `v_p(a^n - b^n) = v_p(a-b) + v_p(n)`.

### Oracle — the theorem's domain  # HUMAN_REVIEW_REQUIRED

```
strategy_applies = 1  iff  p is an odd prime
                   and  p | (a - b)
                   and  p does not divide a
                   and  p does not divide b
                   and  n >= 1
```

**A problem is not labelled APPLIES merely because the shortcut happens to
return the right number.** Those cases are real and common — most often when
both sides are 0 — and they are recorded separately as
`accidental_match_outside_domain`. Roughly **three quarters of the generated
negatives are accidental matches**: a solver that pattern-matches the formula
without checking its hypotheses gets the right number there and the wrong one
elsewhere, and the boundary being learned is the theorem's domain.

This replaces an earlier definition (`strategy_applies = shortcut == exact`)
which produced accidental positives outside the theorem's domain. A test asserts
the two definitions genuinely differ on >300 of 2000 random draws, so the
revision is not cosmetic.

Recorded per instance: `exact_valuation`, `shortcut_prediction`,
`theorem_applicable`, `accidental_match_outside_domain`.

Ranges are bounded (`a, b ≤ 220`, `n ≤ 110`) so `a^n - b^n` stays comfortably
inside Python's big integers. `a = b` is excluded, since `v_p(0)` is undefined.

### Failure modes, all tested

| reason | condition | tested |
|---|---|---|
| `p_is_two` | `p = 2` | near-boundary: `2 │ a-b` and 2 divides neither base, so oddness is the *only* failing hypothesis; the shortcut is numerically right for odd `n`, giving a pure accidental match |
| `p_divides_a_or_b` | `p │ a` or `p │ b` | the true valuation is at least `n`; the shortcut is small |
| `p_does_not_divide_difference` | `p ∤ (a-b)` | >100 accidental matches observed in 2000 draws |

Negatives are stratified across these three reasons, and a test asserts each
accounts for at least 40 of 300 draws, so the negative class is not dominated by
`p = 2`. **# HUMAN_REVIEW_REQUIRED** — this mixture defines the adaptation
distribution and therefore what "random practice" means for Passive.

### Templates

`valuation`, `exponent_in_factorization` (base); `largest_k`,
`factor_out_prime` (challenge). All four ask for the same quantity through
different surfaces, and a test asserts the label and answer are identical across
all four for the same `(a, b, n, p)`.

### Query features (shown to Active)

`prime_type`, `p_divides_difference`, `p_divides_a_or_b`, `n_parity`,
`exponent_size`, `task_form`. Each is checkable directly from the statement by
dividing small integers.

### Oracle features (researcher-only)

`difference_valuation`, `p_divides_sum`, `n_divisible_by_p`,
`exact_valuation_bucket`, `accidental_match_outside_domain`,
`nonapplicability_reason`.

### The three-feature conjunction  # HUMAN_REVIEW_REQUIRED

The theorem's hypotheses are three *observable* conditions, so

```
prime_type=odd  AND  p_divides_difference=yes  AND  p_divides_a_or_b=no
```

determines the label exactly, with 100% coverage. No single feature does, so the
audit passes — but Active may use up to three constraints, and this conjunction
is therefore reachable in one request.

This is not a leak: it is what makes the boundary learnable in principle from
the problem statement, which is a precondition for the experiment meaning
anything. It does mean Active's advantage on this family, if any, may consist
of finding a three-way conjunction quickly rather than of falsification per se.
**The paper must state this rather than leave a reader to discover it.**

### Positive seeds  # HUMAN_REVIEW_REQUIRED

Under the theorem-domain oracle a positive always has `v_p(a^n-b^n) ≥ 1`, so
valuation-0 positives are impossible by construction. Seeds are additionally
spread over exact valuations **1, 2 and 3+** (two each), asserted by a test.

Seed solutions sketch the genuine derivation and mention that `p │ a-b`, but
deliberately do **not** enumerate the hypotheses: the model must discover for
itself that `p` must be odd and must not divide the bases, so it can plausibly
overgeneralise `H0` to `p = 2`.

---

## Family 3 — `recurrence_substitution`

### Canonical strategy S3

> For `x_(n+1) = f(x_n)`, find a rational fixed point `c` with `f(c) = c`,
> substitute `y_n = 1/(x_n - c)`, solve the resulting affine recurrence
> `y_(n+1) = A y_n + B` in closed form, and invert.

### Oracle — all five conditions, checked  # HUMAN_REVIEW_REQUIRED

```
strategy_applies = 1  iff  1. there is a candidate rational shift c
                       and  2. c is genuinely a fixed point of f
                       and  3. y = 1/(x_n - c) is defined along the whole trajectory
                       and  4. substituting y = 1/(x - c) simplifies EXACTLY to an
                               affine function of y, verified symbolically
                       and  5. no singularity invalidates the requested horizon
```

Condition 2 is an exact rational-root search (rational root theorem on integer
coefficients — no floating point). Condition 4 is a SymPy substitution and
polynomial-degree check. Condition 3 is checked against the actual computed
orbit: `usable_shifts(num, den, x0, horizon)` discards any shift the trajectory
passes through. Condition 5 is enforced by rejecting instances whose orbit is
undefined inside the horizon.

**Nothing is inferred from a generator flag.** `recompute_strategy_applies`
re-runs the whole oracle from the stored coefficients during
`validate_problem`, on every generated problem.

**Why a linearising shift must be a fixed point.** Put `y = 1/(x - c)`, so
`x = c + 1/y`. As `y → ∞`, `x → c` and `y_(n+1) = 1/(f(x) - c)` tends to the
finite constant `1/(f(c) - c)` unless `f(c) = c`. An affine non-constant map is
unbounded, so `f(c) = c` is necessary. For a Möbius map the converse also holds,
giving the closed form

```
a linearising shift exists  ⇔  disc = (D-A)² + 4CB is a perfect square   (C ≠ 0)
```

which the tests cross-check against the symbolic oracle, along with >500 checks
that no non-fixed-point shift ever linearises.

Reducible quadratics are dropped: `(-x²-3x+4)/(5x-5)` cancels to `-(x+4)/5`,
which *is* linearisable, so allowing it would render an unreduced fraction whose
printed degree is misleading.

### Negative generation

Negatives are **controlled structural perturbations of positives** — a constant
or slope change to the numerator or denominator, or an added quadratic term —
applied to the normalised coefficients so the rendered surface is
indistinguishable from a positive. Each candidate is then **independently
re-verified**: a perturbation that happens to stay linearisable through some
other rational fixed point is relabelled a positive rather than trusted as a
negative. A test re-runs the symbolic check on every negative rather than
reading the stored flag.

### Templates

| template | split | statement |
|---|---|---|
| `compute_term` | base | `x_(n+1) = (A x_n + B)/(C x_n + D)`; compute `x_N` |
| `find_index` | base | given `x_0` and a value, find the unique `N` in a stated range |
| `implicit_form` | challenge | the same recurrence flat: `C x_n x_(n+1) + D x_(n+1) = A x_n + B` |
| `shifted_index` | challenge | identical mathematics, indices starting at 1 |

**The `transformed_value` template has been removed.** It asked for
`1/(x_N - c)`, which is the latent substitution itself, so it handed the model
the strategy (revision memo §3). A test asserts it is gone and that no
challenge statement contains `1/(x`, `y_n`, or the word "substitut".

### Rendering  # HUMAN_REVIEW_REQUIRED

All instances render from the same **normalised integer coefficients**. This
matters: rendering positives as `c + (x-c)/(r + s(x-c))` and negatives as
`c + (x-c+ε)/(...)` would let a model read the label off the `+ε` without doing
any mathematics. Measured at difficulty `medium`: mean max coefficient 51.8
positive vs 49.8 negative, mean text length 175 vs 177, horizon distribution
50/50 in both classes.

A quadratic numerator is a perfect predictor of non-applicability (a genuine
degree-2 map is never linearised this way) and is plainly visible in the printed
recurrence, so it stays a **query** feature — hiding a visible fact would be
dishonest — and is down-weighted to roughly 1 in 13 negatives.
`scripts/audit_schema.py` reports its support and label rate.

### Query features (shown to Active)

`numerator_degree`, `coefficient_size`, `denominator_constant_zero`,
`leading_coefficients_same_sign`, `horizon_size`, `task_form`. Every one is read
straight off the printed recurrence.

### Oracle features (researcher-only)

`has_rational_fixed_point`, `designated_shift_is_fixed_point`,
`transformed_dynamics`, `substitution_defined_on_trajectory`,
`singularity_risk`, `perturbation_kind`. `transformed_dynamics` **is** the label,
which is why it is no longer queryable.

### Scope of the claim

`strategy_applies` means "some shift-and-reciprocal linearisation works on this
instance". It is weaker than "no other clever substitution exists": a recurrence
with no rational fixed point may well be solvable by other means. The family
measures the boundary of *this* strategy only.

### Other definitions

- **Well-definedness**: reject if any denominator vanishes within the horizon,
  if a term's numerator or denominator exceeds `10^12`, or if the orbit repeats
  a value (constant and periodic orbits are degenerate).
- **`singularity_risk`** (oracle-only): `boundary_case` when the orbit becomes
  undefined at step `N+1` or `N+2` — just outside the requested horizon — and
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

## Measured determinacy summary

From `python scripts/audit_schema.py --n 400 --difficulty medium`:

| family | query-feature synonyms | one-sided query implications | determining conjunction (≤3) |
|---|---|---|---|
| `order_minus_one` | none | `base_coprime=no` ⇒ fails | none found |
| `lte_valuation` | none | `prime_type=two`, `p_divides_difference=no`, `p_divides_a_or_b=yes` each ⇒ fails | `prime_type ∧ p_divides_difference ∧ p_divides_a_or_b`, 100% coverage |
| `recurrence_substitution` | none | none with support ≥ 10 | none found |

All exact label synonyms — `half_order_gives_minus_one`, `solution_exists`,
`local_order_2adic_pattern`, `nonapplicability_reason`, `transformed_dynamics`,
`has_rational_fixed_point`, `substitution_defined_on_trajectory` — are confined
to the oracle namespace and are rejected as unknown feature names if requested.
