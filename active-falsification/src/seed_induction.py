"""Stage 2 -- strategy (S_hat) and initial hypothesis (H0) induction (spec S.11).

The model sees ONLY the six seed problem statements and their verified
solutions.  It never sees the canonical strategy description, the oracle, or
any hidden label.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

from families.base import ProblemFamily
from models import BaseModel
from prompts import induction_prompt
from sampling import derive_seed
from schemas import Problem

#: Spec S.11 diagnostic bands for H0 boundary accuracy.  These are recorded for
#: transparency; they do NOT trigger automatic family exclusion.
H0_BANDS = {
    "too_unclear_below": 0.55,
    "attractive_lo": 0.60,
    "attractive_hi": 0.85,
    "little_headroom_above": 0.90,
}


def extract_json_object(response: str) -> Optional[Dict[str, Any]]:
    """Pull the last complete JSON object out of a raw response.

    Reasoning models wrap JSON in prose or <think> spans, so we scan for
    balanced brace spans rather than trusting the whole response to parse.
    """
    if not response:
        return None
    text = response
    # strip a leading reasoning span if the model emitted one
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE)
    candidates: List[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    candidates.append(text[start : i + 1])
    for blob in reversed(candidates):
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


class InductionFailure(RuntimeError):
    """Raised when a model does not produce a usable strategy/hypothesis pair.

    Spec S.27(G): this is surfaced, never patched over with a default rule.
    """


def induce_strategy_and_h0(
    model: BaseModel,
    family: ProblemFamily,
    seeds: Sequence[Problem],
    max_new_tokens: int,
    master_seed: int,
    retries: int = 2,
) -> Dict[str, Any]:
    """Return {'strategy', 'hypothesis', 'generations', 'attempts'}."""
    prompt = induction_prompt(seeds)
    generations = []
    for attempt in range(retries + 1):
        seed = derive_seed(master_seed, "induce", model.spec.alias, family.name, attempt)
        gen = model.generate(
            stage="induce",
            family=family.name,
            system=prompt["system"],
            user=prompt["user"],
            max_new_tokens=max_new_tokens,
            seed=seed % (2 ** 31),
            meta={"attempt": attempt, "seed_ids": [p.id for p in seeds]},
        )
        generations.append(gen)
        parsed = extract_json_object(gen.response)
        if parsed and parsed.get("strategy") and parsed.get("hypothesis"):
            return {
                "model": model.spec.alias,
                "family": family.name,
                "strategy": str(parsed["strategy"]).strip(),
                "hypothesis": str(parsed["hypothesis"]).strip(),
                "attempts": attempt + 1,
                "seed_ids": [p.id for p in seeds],
                "generations": [g.to_json() for g in generations],
                "output_tokens": sum(g.output_tokens for g in generations),
            }
    raise InductionFailure(
        f"{model.spec.alias}/{family.name}: no parseable "
        f'{{"strategy", "hypothesis"}} object after {retries + 1} attempts. '
        f"Last response (truncated): {generations[-1].response[:500]!r}"
    )


def classify_h0_band(accuracy: float) -> str:
    if accuracy != accuracy:
        return "undefined"
    if accuracy < H0_BANDS["too_unclear_below"]:
        return "likely_too_unclear"
    if accuracy > H0_BANDS["little_headroom_above"]:
        return "little_headroom"
    if H0_BANDS["attractive_lo"] <= accuracy <= H0_BANDS["attractive_hi"]:
        return "attractive"
    return "borderline"
