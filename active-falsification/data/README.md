# `data/`

## `competition_ood.jsonl`

Optional, author-curated, real-competition out-of-distribution problems
(spec S.15.3). **The repository ships this file empty and nothing in the code
will ever populate it.**

Adding entries is a human decision that requires a source and usage review.
Do not scrape contest statements, and do not paste copyrighted problem text
without checking the source's terms.

One JSON object per line:

```json
{"family": "lte_valuation", "problem": "<statement>", "expected_strategy_applicability": true, "source": "<competition, year, problem number>", "source_solution_notes": "<why the intended strategy does or does not work here>"}
```

`family` must be one of `order_minus_one`, `lte_valuation`,
`recurrence_substitution`.

The label on these problems comes from the authors' own review rather than from
a programmatic oracle, so this split is always reported separately from the
generated IID and challenge splits and is never pooled with them.
