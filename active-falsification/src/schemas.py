"""Core data objects shared by every problem family and every experiment stage.

The single most important invariant in this file:

    Problem.public_view()      -> what an LLM is ever allowed to see
    Problem.researcher_view()  -> everything, including hidden oracle labels

`strategy_applies`, `features` and `latent_parameters` are researcher-side
metadata.  They must never appear inside a prompt.  `tests/test_no_leakage.py`
enforces this mechanically.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------
# Problem
# --------------------------------------------------------------------------

#: Keys that must never be rendered into a prompt.
HIDDEN_KEYS = ("strategy_applies", "latent_parameters", "features", "human_solution")


@dataclass
class Problem:
    """A single generated mathematical problem.

    Attributes
    ----------
    id
        Stable identifier, unique inside a run.
    family
        Registry name of the generating family.
    template
        Surface-form identifier (families render the same mathematical content
        through several templates; challenge splits use held-out templates).
    difficulty
        'easy' | 'medium' | 'hard'.
    text
        The problem statement shown to the model.  PUBLIC.
    exact_answer
        Canonical answer string, produced by exact arithmetic (never by an LLM).
    strategy_applies
        Programmatic oracle label: does the family's intended strategy S yield
        the correct result on this instance?  HIDDEN.
    features
        Categorical researcher-side features.  These form the vocabulary the
        Active condition may use to request experiments.  HIDDEN as labels;
        only the *schema* (names and allowed values) is shown to the model.
    human_solution
        Worked solution used for seed demonstrations.  Shown to the model ONLY
        for the six seed problems during strategy/H0 induction.
    latent_parameters
        Generator internals.  HIDDEN.
    generation_seed
        Seed of the RNG stream that produced this problem.
    """

    id: str
    family: str
    template: str
    difficulty: str
    text: str
    exact_answer: str
    strategy_applies: bool
    features: Dict[str, Any] = field(default_factory=dict)
    human_solution: str = ""
    latent_parameters: Dict[str, Any] = field(default_factory=dict)
    generation_seed: int = 0

    # -- views ------------------------------------------------------------
    def public_view(self) -> Dict[str, Any]:
        """Everything an LLM may see about an ordinary (non-seed) problem."""
        return {"id": self.id, "template": self.template, "text": self.text}

    def seed_view(self) -> Dict[str, Any]:
        """Public view plus the verified worked solution.

        Used ONLY for the six seed demonstrations during induction (spec S.11).
        """
        return {
            "id": self.id,
            "template": self.template,
            "text": self.text,
            "solution": self.human_solution,
            "answer": self.exact_answer,
        }

    def researcher_view(self) -> Dict[str, Any]:
        return asdict(self)

    # -- identity ---------------------------------------------------------
    def content_key(self) -> str:
        """Key used for de-duplication across seed / adaptation / test splits.

        Two problems collide when they share the same *mathematical* instance,
        independent of surface template.  Families put the defining parameters
        into ``latent_parameters['instance_key']``.
        """
        key = self.latent_parameters.get("instance_key")
        if key is None:  # pragma: no cover - families must supply this
            raise ValueError(f"family {self.family} did not set instance_key")
        return f"{self.family}|{key}"

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "Problem":
        return Problem(**d)


# --------------------------------------------------------------------------
# Adaptation records
# --------------------------------------------------------------------------


@dataclass
class Observation:
    """One practice datum shown to the model during adaptation.

    ``outcome`` is derived from the programmatic oracle, never from a model.
    """

    problem_id: str
    text: str
    outcome: str  # "SUCCESS" | "FAILURE"
    shown_features: Dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        lines = [f"Problem: {self.text}", f"Outcome of applying the strategy: {self.outcome}"]
        if self.shown_features:
            feats = ", ".join(f"{k}={v}" for k, v in sorted(self.shown_features.items()))
            lines.insert(1, f"Features: {feats}")
        return "\n".join(lines)


@dataclass
class Generation:
    """A single raw model call, retained verbatim for auditing."""

    stage: str
    model: str
    family: str
    prompt: str
    response: str
    output_tokens: int
    prompt_tokens: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AdaptationRound:
    round_index: int
    hypothesis_before: str
    hypothesis_after: str
    constraints: Optional[Dict[str, str]]
    constraint_reason: str
    unsatisfiable_attempts: int
    observations: List[Observation]
    generations: List[Generation]

    def to_json(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class AdaptationResult:
    """Outcome of one condition (active or passive) for one model x family."""

    condition: str  # "active" | "passive"
    model: str
    family: str
    h0: str
    strategy: str
    final_hypothesis: str
    rounds: List[AdaptationRound]
    adaptation_output_tokens: int
    n_observations: int
    n_revisions: int
    n_unsatisfiable: int
    n_query_generations: int
    notes: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def stable_hash(obj: Any) -> str:
    """Deterministic short hash used for family/prompt versioning."""
    blob = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]
