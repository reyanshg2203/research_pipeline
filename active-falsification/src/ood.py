"""Optional real-competition OOD extension (spec S.15.3).

The authors may hand-curate a small set of genuine competition problems in

    data/competition_ood.jsonl

with one JSON object per line:

    {"family": "lte_valuation",
     "problem": "<statement>",
     "expected_strategy_applicability": true,
     "source": "<competition, year, problem number>",
     "source_solution_notes": "<why the intended strategy does or does not work>"}

This file is NEVER populated automatically.  Scraping or bulk-copying contest
statements would raise copyright and provenance problems, so the only way an
entry gets in is for a human author to add it after a source/usage review.

Entries are used for boundary classification only.  They are not validated by a
family oracle -- the label comes from the author's own review, which is exactly
why they are reported as a separate split.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from schemas import Problem

REQUIRED_FIELDS = (
    "family",
    "problem",
    "expected_strategy_applicability",
    "source",
    "source_solution_notes",
)

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "competition_ood.jsonl",
)


def load_competition_ood(path: str = DEFAULT_PATH) -> Dict[str, List[Problem]]:
    """Load author-curated OOD problems, grouped by family. Empty if absent."""
    if not os.path.exists(path):
        return {}
    out: Dict[str, List[Problem]] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                entry: Dict[str, Any] = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON ({exc})") from exc
            missing = [f for f in REQUIRED_FIELDS if f not in entry]
            if missing:
                raise ValueError(f"{path}:{lineno}: missing field(s) {missing}")
            if not isinstance(entry["expected_strategy_applicability"], bool):
                raise ValueError(
                    f"{path}:{lineno}: expected_strategy_applicability must be "
                    f"true or false, got {entry['expected_strategy_applicability']!r}"
                )
            problem = Problem(
                id=f"ood-{entry['family']}-{lineno}",
                family=entry["family"],
                template="competition_ood",
                difficulty="curated",
                text=str(entry["problem"]),
                exact_answer="",
                strategy_applies=bool(entry["expected_strategy_applicability"]),
                features={},
                human_solution="",
                latent_parameters={
                    "instance_key": f"ood:{entry['source']}:{lineno}",
                    "source": entry["source"],
                    "source_solution_notes": entry["source_solution_notes"],
                    "label_provenance": "human author review, not a programmatic oracle",
                },
                generation_seed=0,
            )
            out.setdefault(entry["family"], []).append(problem)
    return out
