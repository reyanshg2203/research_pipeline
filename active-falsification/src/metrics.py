"""Boundary-evaluation metrics (spec S.16)."""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Sequence, Tuple


def confusion(y_true: Sequence[bool], y_pred: Sequence[Optional[bool]]) -> Dict[str, int]:
    """Confusion counts for the APPLIES class.

    Predictions that could not be parsed are counted in ``unparsed`` and are
    excluded from precision/recall/F1; ``accuracy`` scores them as incorrect,
    which is the conservative choice.  Both figures are reported.
    """
    tp = fp = tn = fn = unparsed = 0
    for t, p in zip(y_true, y_pred):
        if p is None:
            unparsed += 1
        elif p and t:
            tp += 1
        elif p and not t:
            fp += 1
        elif not p and not t:
            tn += 1
        else:
            fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "unparsed": unparsed}


def summarise(y_true: Sequence[bool], y_pred: Sequence[Optional[bool]]) -> Dict[str, float]:
    c = confusion(y_true, y_pred)
    n = len(y_true)
    correct = c["tp"] + c["tn"]
    scored = n - c["unparsed"]
    precision = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else float("nan")
    recall = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else float("nan")
    if precision == precision and recall == recall and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = float("nan")
    return {
        "n": n,
        "accuracy": correct / n if n else float("nan"),
        "accuracy_parsed_only": correct / scored if scored else float("nan"),
        "precision_applies": precision,
        "recall_applies": recall,
        "f1_applies": f1,
        "unparsed": c["unparsed"],
        "unparsed_rate": c["unparsed"] / n if n else float("nan"),
        "predicted_positive_rate": (c["tp"] + c["fp"]) / n if n else float("nan"),
        "base_rate_positive": sum(1 for t in y_true if t) / n if n else float("nan"),
        **c,
    }


def bootstrap_ci(
    y_true: Sequence[bool],
    y_pred: Sequence[Optional[bool]],
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> Tuple[float, float]:
    """Percentile bootstrap 95% CI for accuracy (unparsed counted as incorrect)."""
    n = len(y_true)
    if n == 0:
        return (float("nan"), float("nan"))
    hits = [1.0 if (p is not None and p == t) else 0.0 for t, p in zip(y_true, y_pred)]
    rng = random.Random(seed)
    means: List[float] = []
    for _ in range(n_boot):
        s = sum(hits[rng.randrange(n)] for _ in range(n))
        means.append(s / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (lo, hi)


def paired_bootstrap_delta(
    y_true: Sequence[bool],
    pred_a: Sequence[Optional[bool]],
    pred_b: Sequence[Optional[bool]],
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> Dict[str, float]:
    """Paired bootstrap for accuracy(A) - accuracy(B) on the same test items."""
    n = len(y_true)
    if n == 0:
        return {"delta": float("nan"), "lo": float("nan"), "hi": float("nan")}
    ha = [1.0 if (p is not None and p == t) else 0.0 for t, p in zip(y_true, pred_a)]
    hb = [1.0 if (p is not None and p == t) else 0.0 for t, p in zip(y_true, pred_b)]
    point = (sum(ha) - sum(hb)) / n
    rng = random.Random(seed)
    deltas: List[float] = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        deltas.append(sum(ha[i] - hb[i] for i in idx) / n)
    deltas.sort()
    return {
        "delta": point,
        "lo": deltas[int((alpha / 2) * n_boot)],
        "hi": deltas[min(n_boot - 1, int((1 - alpha / 2) * n_boot))],
    }
