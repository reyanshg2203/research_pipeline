"""Frozen-hypothesis boundary evaluation (spec S.16).

The model is shown S_hat, a frozen hypothesis H, and one problem statement, and
must emit APPLIES or DOES_NOT_APPLY.  It is never asked to solve the problem and
never sees the oracle label.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from grading import parse_boundary_label
from metrics import bootstrap_ci, summarise
from models import BaseModel
from prompts import classify_prompt
from sampling import derive_seed
from schemas import Problem


def evaluate_hypothesis(
    model: BaseModel,
    family: str,
    condition: str,
    split: str,
    strategy: str,
    hypothesis: str,
    problems: Sequence[Problem],
    max_new_tokens: int,
    master_seed: int,
) -> Dict[str, Any]:
    """Classify every problem under a frozen hypothesis; return metrics + rows."""
    rows: List[Dict[str, Any]] = []
    y_true: List[bool] = []
    y_pred: List[Optional[bool]] = []

    for i, problem in enumerate(problems):
        prompt = classify_prompt(strategy, hypothesis, problem)
        seed = derive_seed(master_seed, "classify", model.spec.alias, family, condition, split, i)
        gen = model.generate(
            stage="classify",
            family=family,
            system=prompt["system"],
            user=prompt["user"],
            max_new_tokens=max_new_tokens,
            seed=seed % (2 ** 31),
            meta={"condition": condition, "split": split, "problem_id": problem.id},
        )
        pred = parse_boundary_label(gen.response)
        y_true.append(problem.strategy_applies)
        y_pred.append(pred)
        rows.append(
            {
                "model": model.spec.alias,
                "family": family,
                "condition": condition,
                "split": split,
                "problem_id": problem.id,
                "template": problem.template,
                "gold_strategy_applies": problem.strategy_applies,
                "predicted": pred,
                "parsed": pred is not None,
                "correct": (pred is not None and pred == problem.strategy_applies),
                "raw_response": gen.response,
                "output_tokens": gen.output_tokens,
            }
        )

    stats = summarise(y_true, y_pred)
    lo, hi = bootstrap_ci(y_true, y_pred, seed=master_seed % (2 ** 31))
    stats["ci95_lo"] = lo
    stats["ci95_hi"] = hi
    return {
        "model": model.spec.alias,
        "family": family,
        "condition": condition,
        "split": split,
        "metrics": stats,
        "rows": rows,
        "y_true": y_true,
        "y_pred": y_pred,
    }
