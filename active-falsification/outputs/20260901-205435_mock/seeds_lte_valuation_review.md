# Seed review -- family `lte_valuation`

The authors must read every seed below, check the mathematics, and tick
the box before this seed set is used in a publication run.

Canonical strategy (RESEARCHER-ONLY, never shown to a model):

> Use the difference form of the Lifting-the-Exponent lemma: for a prime p dividing a-b but dividing neither a nor b, v_p(a^n - b^n) = v_p(a-b) + v_p(n). Applicability here is operational: the strategy applies exactly when this formula returns the true valuation on the instance.

---

## Seed 1 -- `lte_valuation-exponent_in_factorization-19-21-2-3-1950959574`

- template: `exponent_in_factorization`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Find the exponent of 19 in the prime factorization of 21^3 - 2^3. Answer with a single non-negative integer.

**Verified solution shown to the model**

> Set N = 21^3 - 2^3. First, 21 - 2 = 19 and v_19(19) = 1, so 19 divides 21 - 2 Neither 21 nor 2 is divisible by 19. Writing 21^3 - 2^3 = (21 - 2) · Σ_{i=0}^{3-1} 21^i 2^{3-1-i}, the valuation of the cofactor is governed by v_19(3) = 0. This gives v_19(N) = v_19(21 - 2) + v_19(3) = 1 + 0 = 1. Hence the answer is 1.

**Exact answer:** `1`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 21,
  "b": 2,
  "n": 3,
  "p": 19,
  "instance_key": "v_19(21^3-2^3)",
  "actual_valuation": 1,
  "shortcut_prediction": 1
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 2 -- `lte_valuation-exponent_in_factorization-19-48-29-12-1777713482`

- template: `exponent_in_factorization`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Find the exponent of 19 in the prime factorization of 48^12 - 29^12. Answer with a single non-negative integer.

**Verified solution shown to the model**

> Set N = 48^12 - 29^12. First, 48 - 29 = 19 and v_19(19) = 1, so 19 divides 48 - 29 Neither 48 nor 29 is divisible by 19. Writing 48^12 - 29^12 = (48 - 29) · Σ_{i=0}^{12-1} 48^i 29^{12-1-i}, the valuation of the cofactor is governed by v_19(12) = 0. This gives v_19(N) = v_19(48 - 29) + v_19(12) = 1 + 0 = 1. Hence the answer is 1.

**Exact answer:** `1`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 48,
  "b": 29,
  "n": 12,
  "p": 19,
  "instance_key": "v_19(48^12-29^12)",
  "actual_valuation": 1,
  "shortcut_prediction": 1
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 3 -- `lte_valuation-exponent_in_factorization-2-41-28-3-160080246`

- template: `exponent_in_factorization`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Find the exponent of 2 in the prime factorization of 41^3 - 28^3. Answer with a single non-negative integer.

**Verified solution shown to the model**

> Set N = 41^3 - 28^3. First, 41 - 28 = 13 and v_2(13) = 0. Writing 41^3 - 28^3 = (41 - 28) · Σ_{i=0}^{3-1} 41^i 28^{3-1-i}, the valuation of the cofactor is governed by v_2(3) = 0. This gives v_2(N) = v_2(41 - 28) + v_2(3) = 0 + 0 = 0. Hence the answer is 0.

**Exact answer:** `0`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 41,
  "b": 28,
  "n": 3,
  "p": 2,
  "instance_key": "v_2(41^3-28^3)",
  "actual_valuation": 0,
  "shortcut_prediction": 0
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 4 -- `lte_valuation-exponent_in_factorization-59-66-7-9-409972890`

- template: `exponent_in_factorization`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Find the exponent of 59 in the prime factorization of 66^9 - 7^9. Answer with a single non-negative integer.

**Verified solution shown to the model**

> Set N = 66^9 - 7^9. First, 66 - 7 = 59 and v_59(59) = 1, so 59 divides 66 - 7 Neither 66 nor 7 is divisible by 59. Writing 66^9 - 7^9 = (66 - 7) · Σ_{i=0}^{9-1} 66^i 7^{9-1-i}, the valuation of the cofactor is governed by v_59(9) = 0. This gives v_59(N) = v_59(66 - 7) + v_59(9) = 1 + 0 = 1. Hence the answer is 1.

**Exact answer:** `1`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 66,
  "b": 7,
  "n": 9,
  "p": 59,
  "instance_key": "v_59(66^9-7^9)",
  "actual_valuation": 1,
  "shortcut_prediction": 1
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 5 -- `lte_valuation-valuation-2-21-14-5-898441411`

- template: `valuation`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Let N = 21^5 - 14^5. Compute v_2(N), the exponent of the prime 2 in the prime factorization of N. Answer with a single non-negative integer.

**Verified solution shown to the model**

> Set N = 21^5 - 14^5. First, 21 - 14 = 7 and v_2(7) = 0. Writing 21^5 - 14^5 = (21 - 14) · Σ_{i=0}^{5-1} 21^i 14^{5-1-i}, the valuation of the cofactor is governed by v_2(5) = 0. This gives v_2(N) = v_2(21 - 14) + v_2(5) = 0 + 0 = 0. Hence the answer is 0.

**Exact answer:** `0`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 21,
  "b": 14,
  "n": 5,
  "p": 2,
  "instance_key": "v_2(21^5-14^5)",
  "actual_valuation": 0,
  "shortcut_prediction": 0
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 6 -- `lte_valuation-valuation-2-22-9-3-1600337260`

- template: `valuation`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Let N = 22^3 - 9^3. Compute v_2(N), the exponent of the prime 2 in the prime factorization of N. Answer with a single non-negative integer.

**Verified solution shown to the model**

> Set N = 22^3 - 9^3. First, 22 - 9 = 13 and v_2(13) = 0. Writing 22^3 - 9^3 = (22 - 9) · Σ_{i=0}^{3-1} 22^i 9^{3-1-i}, the valuation of the cofactor is governed by v_2(3) = 0. This gives v_2(N) = v_2(22 - 9) + v_2(3) = 0 + 0 = 0. Hence the answer is 0.

**Exact answer:** `0`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 22,
  "b": 9,
  "n": 3,
  "p": 2,
  "instance_key": "v_2(22^3-9^3)",
  "actual_valuation": 0,
  "shortcut_prediction": 0
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---
