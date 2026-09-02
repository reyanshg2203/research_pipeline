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

These are the ONLY family internals the Active condition ever sees. The `full` profile follows the spec; `label_decoupled` removes the features that determine the oracle label.

### profile `full`

**order_minus_one**

- `modulus_structure`: `prime`, `prime_power`, `two_coprime_prime_power_factors`, `three_coprime_prime_power_factors`
- `base_coprime`: `yes`, `no`
- `global_order_parity`: `even`, `odd`, `undefined`
- `local_order_2adic_pattern`: `aligned_positive`, `misaligned`, `contains_odd`, `undefined`
- `number_of_components`: `1`, `2`, `3`
- `modulus_size`: `small`, `medium`, `large`

**lte_valuation**

- `prime_type`: `odd`, `two`
- `p_divides_difference`: `yes`, `no`
- `p_divides_sum`: `yes`, `no`
- `p_divides_a_or_b`: `yes`, `no`
- `n_parity`: `odd`, `even`
- `n_divisible_by_p`: `yes`, `no`
- `difference_valuation`: `0`, `1`, `2plus`
- `exponent_size`: `small`, `medium`, `large`

**recurrence_substitution**

- `shift_structure`: `aligned`, `mismatched`
- `numerator_structure`: `proportional_to_shifted_x`, `additive_perturbation`
- `denominator_relation`: `affine_compatible`, `perturbed`
- `transformed_dynamics`: `affine`, `non_affine`
- `singularity_risk`: `none_in_horizon`, `boundary_case`
- `horizon_size`: `small`, `medium`, `large`

### profile `label_decoupled`

**order_minus_one**

- `modulus_structure`: `prime`, `prime_power`, `two_coprime_prime_power_factors`, `three_coprime_prime_power_factors`
- `base_coprime`: `yes`, `no`
- `global_order_parity`: `even`, `odd`, `undefined`
- `number_of_components`: `1`, `2`, `3`
- `modulus_size`: `small`, `medium`, `large`

**lte_valuation**

- `prime_type`: `odd`, `two`
- `p_divides_difference`: `yes`, `no`
- `p_divides_sum`: `yes`, `no`
- `p_divides_a_or_b`: `yes`, `no`
- `n_parity`: `odd`, `even`
- `n_divisible_by_p`: `yes`, `no`
- `difference_valuation`: `0`, `1`, `2plus`
- `exponent_size`: `small`, `medium`, `large`

**recurrence_substitution**

- `numerator_structure`: `proportional_to_shifted_x`, `additive_perturbation`
- `denominator_relation`: `affine_compatible`, `perturbed`
- `singularity_risk`: `none_in_horizon`, `boundary_case`
- `horizon_size`: `small`, `medium`, `large`
