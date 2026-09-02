# Seed review -- family `recurrence_substitution`

The authors must read every seed below, check the mathematics, and tick
the box before this seed set is used in a publication run.

Canonical strategy (RESEARCHER-ONLY, never shown to a model):

> Recognise that a rational recurrence x_{n+1} = f(x_n) becomes affine under the shift-and-reciprocal substitution y_n = 1/(x_n - c), where c is a fixed point of f; solve the resulting affine recurrence in closed form and invert.

---

## Seed 1 -- `recurrence_substitution-compute_term-12848187-152492487`

- template: `compute_term`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> A sequence of rational numbers satisfies x_0 = 7/2 and x_(n+1) = (-x_n - 6) / (x_n + 4) for all n ≥ 0. Compute x_4. Give the exact value as an integer or a reduced fraction.

**Verified solution shown to the model**

> Look for a constant c making the map fix c: solving f(c) = c gives c = -3. Substitute y_n = 1/(x_n - -3). A short computation turns the recurrence into the affine recurrence y_(n+1) = 1/2·y_n + 1/2. From x_0 = 7/2 we get y_0 = 2/13. Iterating the affine recurrence 4 times gives y_4 = 197/208. Inverting, x_4 = -3 + 1/y_4 = -383/197.

**Exact answer:** `-383/197`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "num": [
    -1,
    -6
  ],
  "den": [
    1,
    4
  ],
  "x0": "7/2",
  "horizon": 4,
  "c_designated": "-2",
  "r": 2,
  "s": 1,
  "perturbation": null,
  "linearising_shifts": [
    [
      "-3",
      "1/2",
      "1/2"
    ],
    [
      "-2",
      "2",
      "1"
    ]
  ],
  "instance_key": "[-1, -6]|[1, 4]|7/2|4",
  "terms": [
    "7/2",
    "-19/15",
    "-71/41",
    "-175/93",
    "-383/197"
  ]
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 2 -- `recurrence_substitution-compute_term-17321504-280027953`

- template: `compute_term`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> A sequence of rational numbers satisfies x_0 = -2 and x_(n+1) = (x_n) / (3x_n + 2) for all n ≥ 0. Compute x_4. Give the exact value as an integer or a reduced fraction.

**Verified solution shown to the model**

> Look for a constant c making the map fix c: solving f(c) = c gives c = -1/3. Substitute y_n = 1/(x_n - -1/3). A short computation turns the recurrence into the affine recurrence y_(n+1) = 1/2·y_n + 3/2. From x_0 = -2 we get y_0 = -3/5. Iterating the affine recurrence 4 times gives y_4 = 111/40. Inverting, x_4 = -1/3 + 1/y_4 = 1/37.

**Exact answer:** `1/37`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "num": [
    1,
    0
  ],
  "den": [
    3,
    2
  ],
  "x0": "-2",
  "horizon": 4,
  "c_designated": "0",
  "r": 2,
  "s": 3,
  "perturbation": null,
  "linearising_shifts": [
    [
      "-1/3",
      "1/2",
      "3/2"
    ],
    [
      "0",
      "2",
      "3"
    ]
  ],
  "instance_key": "[1, 0]|[3, 2]|-2|4",
  "terms": [
    "-2",
    "1/2",
    "1/7",
    "1/17",
    "1/37"
  ]
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 3 -- `recurrence_substitution-compute_term-50317396-467675918`

- template: `compute_term`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> A sequence of rational numbers satisfies x_0 = 4 and x_(n+1) = (-4x_n - 6) / (x_n + 1) for all n ≥ 0. Compute x_4. Give the exact value as an integer or a reduced fraction.

**Verified solution shown to the model**

> Look for a constant c making the map fix c: solving f(c) = c gives c = -3. Substitute y_n = 1/(x_n - -3). A short computation turns the recurrence into the affine recurrence y_(n+1) = 2·y_n + -1. From x_0 = 4 we get y_0 = 1/7. Iterating the affine recurrence 4 times gives y_4 = -89/7. Inverting, x_4 = -3 + 1/y_4 = -274/89.

**Exact answer:** `-274/89`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "num": [
    -4,
    -6
  ],
  "den": [
    1,
    1
  ],
  "x0": "4",
  "horizon": 4,
  "c_designated": "-3",
  "r": 2,
  "s": -1,
  "perturbation": null,
  "linearising_shifts": [
    [
      "-3",
      "2",
      "-1"
    ],
    [
      "-2",
      "1/2",
      "-1/2"
    ]
  ],
  "instance_key": "[-4, -6]|[1, 1]|4|4",
  "terms": [
    "4",
    "-22/5",
    "-58/17",
    "-130/41",
    "-274/89"
  ]
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 4 -- `recurrence_substitution-compute_term-98822856-408110380`

- template: `compute_term`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> A sequence of rational numbers satisfies x_0 = -4 and x_(n+1) = (-x_n) / (x_n - 2) for all n ≥ 0. Compute x_3. Give the exact value as an integer or a reduced fraction.

**Verified solution shown to the model**

> Look for a constant c making the map fix c: solving f(c) = c gives c = 0. Substitute y_n = 1/(x_n - 0). A short computation turns the recurrence into the affine recurrence y_(n+1) = 2·y_n + -1. From x_0 = -4 we get y_0 = -1/4. Iterating the affine recurrence 3 times gives y_3 = -9. Inverting, x_3 = 0 + 1/y_3 = -1/9.

**Exact answer:** `-1/9`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "num": [
    -1,
    0
  ],
  "den": [
    1,
    -2
  ],
  "x0": "-4",
  "horizon": 3,
  "c_designated": "0",
  "r": 2,
  "s": -1,
  "perturbation": null,
  "linearising_shifts": [
    [
      "0",
      "2",
      "-1"
    ],
    [
      "1",
      "1/2",
      "-1/2"
    ]
  ],
  "instance_key": "[-1, 0]|[1, -2]|-4|3",
  "terms": [
    "-4",
    "-2/3",
    "-1/4",
    "-1/9"
  ]
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 5 -- `recurrence_substitution-find_index-12499745-1794034387`

- template: `find_index`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> A sequence of rational numbers satisfies x_0 = -1/2 and x_(n+1) = (3x_n - 4) / (x_n - 2) for all n ≥ 0. There is exactly one index N with 1 ≤ N ≤ 8 for which x_N = 35/11. Find N. Answer with a single integer.

**Verified solution shown to the model**

> Look for a constant c making the map fix c: solving f(c) = c gives c = 1. Substitute y_n = 1/(x_n - 1). A short computation turns the recurrence into the affine recurrence y_(n+1) = -1/2·y_n + 1/2. From x_0 = -1/2 we get y_0 = -2/3. Iterating the affine recurrence 3 times gives y_3 = 11/24. Inverting, x_3 = 1 + 1/y_3 = 35/11. The requested quantity is therefore 3.

**Exact answer:** `3`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "num": [
    3,
    -4
  ],
  "den": [
    1,
    -2
  ],
  "x0": "-1/2",
  "horizon": 3,
  "c_designated": "4",
  "r": -2,
  "s": -1,
  "perturbation": null,
  "linearising_shifts": [
    [
      "1",
      "-1/2",
      "1/2"
    ],
    [
      "4",
      "-2",
      "-1"
    ]
  ],
  "instance_key": "[3, -4]|[1, -2]|-1/2|3",
  "terms": [
    "-1/2",
    "11/5",
    "13",
    "35/11"
  ],
  "index_search_range": [
    1,
    8
  ]
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---

## Seed 6 -- `recurrence_substitution-find_index-27446766-699824873`

- template: `find_index`  |  difficulty: `easy`
- pooled zero-shot solve count: **0**
- oracle `strategy_applies`: **True**

**Problem**

> A sequence of rational numbers satisfies x_0 = -5/2 and x_(n+1) = (x_n - 8) / (x_n - 5) for all n ≥ 0. There is exactly one index N with 1 ≤ N ≤ 8 for which x_N = 37/19. Find N. Answer with a single integer.

**Verified solution shown to the model**

> Look for a constant c making the map fix c: solving f(c) = c gives c = 2. Substitute y_n = 1/(x_n - 2). A short computation turns the recurrence into the affine recurrence y_(n+1) = 3·y_n + -1. From x_0 = -5/2 we get y_0 = -2/9. Iterating the affine recurrence 3 times gives y_3 = -19. Inverting, x_3 = 2 + 1/y_3 = 37/19. The requested quantity is therefore 3.

**Exact answer:** `3`

**Researcher-side metadata (NOT shown to the model)**

```json
{
  "num": [
    1,
    -8
  ],
  "den": [
    1,
    -5
  ],
  "x0": "-5/2",
  "horizon": 3,
  "c_designated": "2",
  "r": 3,
  "s": -1,
  "perturbation": null,
  "linearising_shifts": [
    [
      "2",
      "3",
      "-1"
    ],
    [
      "4",
      "1/3",
      "-1/3"
    ]
  ],
  "instance_key": "[1, -8]|[1, -5]|-5/2|3",
  "terms": [
    "-5/2",
    "7/5",
    "11/6",
    "37/19"
  ],
  "index_search_range": [
    1,
    8
  ]
}
```

- [ ] I have verified this problem, this solution and this answer by hand.

---
