# Seed review -- family `order_minus_one`

The authors must read every seed below, check the mathematics, and tick
the box before this seed set is used in a publication run.

Canonical strategy (RESEARCHER-ONLY, never shown to a model):

> Factor the modulus into coprime prime-power components, compute the multiplicative order d of the base, and use the fact that a solution of a^n = -1 exists exactly when d is even and a^(d/2) = -1 on every component simultaneously, in which case the least exponent is d/2.

---

## Seed 1 -- `order_minus_one-least_n_congruence-10-23-1217540276`

- template: `least_n_congruence`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Find the least positive integer n such that 10^n ≡ -1 (mod 23). If no such n exists, answer NONE.

**Verified solution shown to the model**

> Since gcd(10, 23) = 1, the base is a unit modulo 23. The multiplicative order of 10 modulo 23 is d = 22. If 10^n ≡ -1 (mod 23) then squaring gives 10^(2n) ≡ 1, so d | 2n, while d does not divide n. Therefore n must be an odd multiple of d/2 = 11. Direct computation gives 10^11 ≡ 22 ≡ -1 (mod 23), so the exponent d/2 does produce -1. The least such n is therefore 11.

**Exact answer:** `11`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 10,
  "m": 23,
  "instance_key": "10^n=-1 mod 23",
  "least_n": 11,
  "components": [
    23
  ],
  "global_order": 22,
  "local_orders": {
    "23": 22
  }
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 2 -- `order_minus_one-least_n_congruence-30-47-868881799`

- template: `least_n_congruence`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Find the least positive integer n such that 30^n ≡ -1 (mod 47). If no such n exists, answer NONE.

**Verified solution shown to the model**

> Since gcd(30, 47) = 1, the base is a unit modulo 47. The multiplicative order of 30 modulo 47 is d = 46. If 30^n ≡ -1 (mod 47) then squaring gives 30^(2n) ≡ 1, so d | 2n, while d does not divide n. Therefore n must be an odd multiple of d/2 = 23. Direct computation gives 30^23 ≡ 46 ≡ -1 (mod 47), so the exponent d/2 does produce -1. The least such n is therefore 23.

**Exact answer:** `23`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 30,
  "m": 47,
  "instance_key": "30^n=-1 mod 47",
  "least_n": 23,
  "components": [
    47
  ],
  "global_order": 46,
  "local_orders": {
    "47": 46
  }
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 3 -- `order_minus_one-least_n_congruence-72-89-888018540`

- template: `least_n_congruence`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Find the least positive integer n such that 72^n ≡ -1 (mod 89). If no such n exists, answer NONE.

**Verified solution shown to the model**

> Since gcd(72, 89) = 1, the base is a unit modulo 89. The multiplicative order of 72 modulo 89 is d = 44. If 72^n ≡ -1 (mod 89) then squaring gives 72^(2n) ≡ 1, so d | 2n, while d does not divide n. Therefore n must be an odd multiple of d/2 = 22. Direct computation gives 72^22 ≡ 88 ≡ -1 (mod 89), so the exponent d/2 does produce -1. The least such n is therefore 22.

**Exact answer:** `22`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 72,
  "m": 89,
  "instance_key": "72^n=-1 mod 89",
  "least_n": 22,
  "components": [
    89
  ],
  "global_order": 44,
  "local_orders": {
    "89": 44
  }
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 4 -- `order_minus_one-least_n_congruence-8-11-1155420311`

- template: `least_n_congruence`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Find the least positive integer n such that 8^n ≡ -1 (mod 11). If no such n exists, answer NONE.

**Verified solution shown to the model**

> Since gcd(8, 11) = 1, the base is a unit modulo 11. The multiplicative order of 8 modulo 11 is d = 10. If 8^n ≡ -1 (mod 11) then squaring gives 8^(2n) ≡ 1, so d | 2n, while d does not divide n. Therefore n must be an odd multiple of d/2 = 5. Direct computation gives 8^5 ≡ 10 ≡ -1 (mod 11), so the exponent d/2 does produce -1. The least such n is therefore 5.

**Exact answer:** `5`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 8,
  "m": 11,
  "instance_key": "8^n=-1 mod 11",
  "least_n": 5,
  "components": [
    11
  ],
  "global_order": 10,
  "local_orders": {
    "11": 10
  }
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 5 -- `order_minus_one-least_n_divisibility-10-19-1619328863`

- template: `least_n_divisibility`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Find the least positive integer n such that 19 divides 10^n + 1. If no such n exists, answer NONE.

**Verified solution shown to the model**

> Since gcd(10, 19) = 1, the base is a unit modulo 19. The multiplicative order of 10 modulo 19 is d = 18. If 10^n ≡ -1 (mod 19) then squaring gives 10^(2n) ≡ 1, so d | 2n, while d does not divide n. Therefore n must be an odd multiple of d/2 = 9. Direct computation gives 10^9 ≡ 18 ≡ -1 (mod 19), so the exponent d/2 does produce -1. The least such n is therefore 9.

**Exact answer:** `9`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 10,
  "m": 19,
  "instance_key": "10^n=-1 mod 19",
  "least_n": 9,
  "components": [
    19
  ],
  "global_order": 18,
  "local_orders": {
    "19": 18
  }
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 6 -- `order_minus_one-least_n_divisibility-10-89-1698824592`

- template: `least_n_divisibility`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> Find the least positive integer n such that 89 divides 10^n + 1. If no such n exists, answer NONE.

**Verified solution shown to the model**

> Since gcd(10, 89) = 1, the base is a unit modulo 89. The multiplicative order of 10 modulo 89 is d = 44. If 10^n ≡ -1 (mod 89) then squaring gives 10^(2n) ≡ 1, so d | 2n, while d does not divide n. Therefore n must be an odd multiple of d/2 = 22. Direct computation gives 10^22 ≡ 88 ≡ -1 (mod 89), so the exponent d/2 does produce -1. The least such n is therefore 22.

**Exact answer:** `22`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "a": 10,
  "m": 89,
  "instance_key": "10^n=-1 mod 89",
  "least_n": 22,
  "components": [
    89
  ],
  "global_order": 44,
  "local_orders": {
    "89": 44
  }
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---
