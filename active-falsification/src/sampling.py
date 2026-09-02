"""Deterministic RNG discipline.

Every stage draws from its own named, derived stream so that changing the
number of draws in one stage cannot perturb another.  All seeds are recorded in
``run_manifest.json``.
"""

from __future__ import annotations

import hashlib
import random
from typing import Dict, Iterable, List, Set

from schemas import Problem


def derive_seed(master_seed: int, *parts: object) -> int:
    """Deterministically derive a sub-seed from the master seed and a label."""
    label = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(f"{master_seed}|{label}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def stream(master_seed: int, *parts: object) -> random.Random:
    """A fresh, independently seeded RNG for one named stage."""
    return random.Random(derive_seed(master_seed, *parts))


def content_keys(problems: Iterable[Problem]) -> Set[str]:
    return {p.content_key() for p in problems}


def assert_disjoint(named_splits: Dict[str, List[Problem]]) -> None:
    """Hard check that no mathematical instance appears in two splits.

    Spec S.15: hidden tests must not overlap seeds or adaptation data.  A
    violation raises rather than warning.
    """
    keys = {name: content_keys(ps) for name, ps in named_splits.items()}
    names = list(keys)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            overlap = keys[a] & keys[b]
            if overlap:
                raise ValueError(
                    f"split leakage between {a!r} and {b!r}: "
                    f"{len(overlap)} shared instances, e.g. {sorted(overlap)[:3]}"
                )


def label_balance(problems: Iterable[Problem]) -> Dict[str, int]:
    items = list(problems)
    pos = sum(1 for p in items if p.strategy_applies)
    return {"n": len(items), "positive": pos, "negative": len(items) - pos}
