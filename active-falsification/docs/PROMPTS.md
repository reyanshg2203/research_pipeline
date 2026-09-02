# PROMPTS

**This file is generated. Do not edit it by hand.**
Regenerate with `python scripts/export_prompts.py` after editing `src/prompts.py`.

- prompt version: `1.0.0`
- prompt hash: `cb3585a4f27e03fc`

Every prompt below is reproduced verbatim. Placeholders in braces are filled at run time.

## Leakage rules

No prompt may contain the oracle label `strategy_applies`, a family's
canonical `strategy_description`, hidden test membership, or latent
generator parameters that are not already visible in the rendered problem.
`tests/test_no_leakage.py` enforces this mechanically.

The only place a worked solution is ever shown is prompt B, and only for
the six approved seed problems.

---

## A. Zero-shot solver (calibration and seed screening)

### `A_solve_system` (system)

```text
You are a careful mathematician. Solve the problem exactly. Show concise reasoning, then finish with a single line of the form
FINAL_ANSWER: <answer>
The answer must be an exact integer, an exact reduced fraction such as -7/2, or one of the literal words NONE, YES, NO when the problem calls for them. Do not write anything after that line.
```

### `A_solve_user` (user)

```text
{problem_text}
```

---

## B. Strategy and H0 induction from seed demonstrations

### `B_induce_system` (system)

```text
You are a mathematician studying a collection of solved problems in order to extract a reusable solution method and to state precisely when that method works.
```

### `B_induce_user` (user)

```text
Below are {n} solved problems. They were all solved by the same underlying method.

{demonstrations}

Do two things.

1. STRATEGY: describe, in your own words, the general reusable method these solutions share. Describe the method itself, not the individual numbers.

2. HYPOTHESIS: state a falsifiable rule for WHEN this method will succeed on a new problem of this kind, and when it will fail. The rule must be checkable from the statement of a new problem. It must be a genuine applicability condition, not a restatement of the method. It must be specific enough that some problems of this kind would violate it.

Respond with a single JSON object and nothing else:

{{"strategy": "...", "hypothesis": "..."}}
```

---

## C. Boundary classification (primary evaluation)

### `C_classify_system` (system)

```text
You decide whether a solution method applies to a problem. You do not solve the problem.
```

### `C_classify_user` (user)

```text
Method:
{strategy}

Rule for when the method works:
{hypothesis}

New problem:
{problem_text}

Using the rule above, decide whether applying the method to this problem would succeed.

Answer with exactly one of these two tokens and nothing else:
APPLIES
DOES_NOT_APPLY
```

---

## D. Active experiment selection

### `D_query_system` (system)

```text
You are designing experiments to test and refine your own hypothesis. You cannot write code and you cannot choose specific numbers. You may only request problems by specifying values for the listed categorical features.
```

### `D_query_user` (user)

```text
Method:
{strategy}

Your current rule for when the method works:
{hypothesis}

{history}

You may now request a batch of {batch_size} fresh problems by constraining between 1 and 3 of the following features. Every problem you receive will satisfy your constraints, and you will be told, for each one, whether applying the method actually succeeded.

Available features and their allowed values:
{schema}

Choose constraints that are most likely to FALSIFY or sharpen your current rule: pick a region where your rule makes a confident prediction that you are least sure of.

Respond with a single JSON object and nothing else:

{{"constraints": {{"feature_name": "allowed_value"}}, "reason": "one or two sentences"}}
```

---

## E. Hypothesis revision (identical for Active and Passive)

### `E_revise_system` (system)

```text
You update a hypothesis in the light of new evidence. Be precise and conservative: keep what the evidence supports and change what it refutes.
```

### `E_revise_user` (user)

```text
Method:
{strategy}

Your current rule for when the method works:
{hypothesis}

New evidence. Each problem below was solved with the method, and the outcome says whether the method produced the correct result.

{observations}

Revise your rule so that it is consistent with all of the evidence you have seen. The revised rule must still be a falsifiable, checkable condition stated in terms of features of a problem statement, not a list of the specific problems above.

Respond with a single JSON object and nothing else:

{{"hypothesis": "..."}}
```

---

## F. Invalid Active request -- one reformulation attempt

### `F_unsat_system` (system)

```text
You are designing experiments to test and refine your own hypothesis. You cannot write code and you cannot choose specific numbers. You may only request problems by specifying values for the listed categorical features.
```

### `F_unsat_user` (user)

```text
UNSATISFIABLE_REQUEST

Your requested constraints could not be satisfied.

You requested:
{requested}

Reason: {reason}

Available features and their allowed values:
{schema}

Reformulate your request once, using only the feature names and values listed above, and using between 1 and 3 constraints.

Respond with a single JSON object and nothing else:

{{"constraints": {{"feature_name": "allowed_value"}}, "reason": "one or two sentences"}}
```

---

## Active query schemas shown to the model

These are the ONLY family internals the Active condition ever sees.
Every value is observable directly from a problem statement.

**order_minus_one**

- `modulus_type`: `prime`, `prime_power`, `composite`
- `number_of_factors`: `1`, `2`, `3`
- `base_coprime`: `yes`, `no`
- `modulus_size`: `small`, `medium`, `large`
- `task_form`: `least_n_congruence`, `least_n_divisibility`

**lte_valuation**

- `prime_type`: `odd`, `two`
- `p_divides_difference`: `yes`, `no`
- `p_divides_a_or_b`: `yes`, `no`
- `n_parity`: `odd`, `even`
- `exponent_size`: `small`, `medium`, `large`
- `task_form`: `valuation`, `exponent_in_factorization`

**recurrence_substitution**

- `numerator_degree`: `linear`, `quadratic`
- `coefficient_size`: `small`, `medium`, `large`
- `denominator_constant_zero`: `yes`, `no`
- `leading_coefficients_same_sign`: `yes`, `no`
- `horizon_size`: `small`, `medium`, `large`
- `task_form`: `compute_term`, `find_index`

---

## Oracle-only features -- NEVER shown to any model

These researcher-side diagnostics are used for validation, balancing and
audit. Several are deterministic synonyms for the hidden label, which is
exactly why they are confined to this namespace and are rejected as
unknown feature names if a model asks for one.

**order_minus_one**

- `global_order_parity`: `even`, `odd`, `undefined`
- `local_order_2adic_pattern`: `aligned_positive`, `misaligned`, `contains_odd`, `undefined`
- `half_order_gives_minus_one`: `yes`, `no`, `undefined`
- `solution_exists`: `yes`, `no`

**lte_valuation**

- `difference_valuation`: `0`, `1`, `2plus`
- `p_divides_sum`: `yes`, `no`
- `n_divisible_by_p`: `yes`, `no`
- `exact_valuation_bucket`: `0`, `1`, `2`, `3plus`
- `accidental_match_outside_domain`: `yes`, `no`
- `nonapplicability_reason`: `none`, `p_is_two`, `p_divides_a_or_b`, `p_does_not_divide_difference`

**recurrence_substitution**

- `has_rational_fixed_point`: `yes`, `no`
- `designated_shift_is_fixed_point`: `yes`, `no`
- `transformed_dynamics`: `affine`, `non_affine`
- `substitution_defined_on_trajectory`: `yes`, `no`, `not_applicable`
- `singularity_risk`: `none_in_horizon`, `boundary_case`
- `perturbation_kind`: `none`, `numerator_constant`, `numerator_slope`, `denominator_constant`, `denominator_slope`, `quadratic_term`
