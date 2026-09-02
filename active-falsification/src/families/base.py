"""Common interface for problem families.

A family owns:
  * the mathematical generator,
  * the exact answer computation,
  * the programmatic applicability oracle for its intended strategy S,
  * the categorical feature schema the Active condition may query.

Nothing in this module may ever put a hidden label into a prompt.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

from schemas import Problem, stable_hash


class UnsatisfiableConstraints(Exception):
    """Raised when a requested combination of feature values cannot be realised.

    Carries a machine-readable reason so the Active loop can hand the model an
    explicit ``UNSATISFIABLE_REQUEST`` message instead of silently substituting
    a different experiment (spec S.12).
    """

    def __init__(self, reason: str, constraints: Dict[str, Any]):
        super().__init__(reason)
        self.reason = reason
        self.constraints = constraints


class ProblemFamily(ABC):
    """Base class.  See docs/FAMILY_SPEC.md for the mathematics."""

    #: registry name
    name: str = "base"

    #: canonical description of the latent strategy S.  RESEARCHER-ONLY.
    #: Never rendered into any prompt; the model must induce its own S_hat.
    strategy_description: str = ""

    #: feature_name -> list of allowed categorical values.  The *schema* is
    #: shown to the Active condition; feature *values of specific problems*
    #: are not (unless config.show_features_in_observations is enabled).
    active_query_schema: Dict[str, List[str]] = {}

    #: Features whose value determines the hidden oracle label (or very nearly).
    #: They are part of the schema the spec prescribes, so the DEFAULT profile
    #: exposes them; the opt-in 'label_decoupled' profile removes them so that
    #: Active cannot request the answer directly.  Run
    #: `python scripts/audit_schema.py` to see the measured conditional label
    #: rates behind this list.
    # HUMAN_REVIEW_REQUIRED
    label_determining_features: List[str] = []

    #: 'full' (spec default) or 'label_decoupled'
    schema_profile: str = "full"

    def __init__(self, schema_profile: str = "full"):
        if schema_profile not in ("full", "label_decoupled"):
            raise ValueError(
                f"unknown schema_profile {schema_profile!r}; "
                "expected 'full' or 'label_decoupled'"
            )
        self.schema_profile = schema_profile

    def queryable_schema(self) -> Dict[str, List[str]]:
        """The schema the Active condition may see and constrain.

        Always a subset of ``active_query_schema``; ``validate_problem`` keeps
        checking generated features against the FULL schema.
        """
        if self.schema_profile == "label_decoupled":
            return {
                k: v
                for k, v in self.active_query_schema.items()
                if k not in self.label_determining_features
            }
        return dict(self.active_query_schema)

    #: templates used for seeds / calibration / IID practice+test
    base_templates: List[str] = []

    #: held-out templates used only for the challenge split
    challenge_templates: List[str] = []

    difficulties: List[str] = ["easy", "medium", "hard"]

    # ---------------------------------------------------------------- sampling
    @abstractmethod
    def sample_random(
        self,
        rng: random.Random,
        difficulty: str,
        template: str,
        want_applies: Optional[bool] = None,
    ) -> Problem:
        """Draw one problem from the family's distribution for ``difficulty``.

        ``want_applies`` optionally conditions on the hidden oracle label; this
        is used by the researcher-side balanced test builder, never by a model.
        """

    @abstractmethod
    def sample_conditioned(
        self,
        rng: random.Random,
        constraints: Dict[str, str],
        difficulty: str,
        template: str,
    ) -> Optional[Problem]:
        """Draw one problem satisfying ``constraints``.

        Returns ``None`` if the attempt budget was exhausted without success.
        Raises :class:`UnsatisfiableConstraints` when the request is provably
        impossible (unknown key, unknown value, contradictory combination, or
        outside the difficulty tier).
        """

    @abstractmethod
    def recompute_answer(self, problem: Problem) -> str:
        """Recompute ``exact_answer`` from scratch, independently of generation."""

    @abstractmethod
    def recompute_strategy_applies(self, problem: Problem) -> bool:
        """Recompute the oracle label from scratch, independently of generation."""

    # ------------------------------------------------------------- validation
    def validate_problem(self, problem: Problem) -> bool:
        """Hard self-check.  Raises on mathematical inconsistency.

        Spec S.27(G): validation failures are explicit; we never continue
        silently past one.
        """
        if problem.family != self.name:
            raise ValueError(f"{problem.id}: family mismatch {problem.family} != {self.name}")
        recomputed = self.recompute_answer(problem)
        if recomputed != problem.exact_answer:
            raise ValueError(
                f"{problem.id}: answer mismatch stored={problem.exact_answer!r} "
                f"recomputed={recomputed!r}"
            )
        applies = self.recompute_strategy_applies(problem)
        if applies != problem.strategy_applies:
            raise ValueError(
                f"{problem.id}: oracle mismatch stored={problem.strategy_applies} "
                f"recomputed={applies}"
            )
        for key, value in problem.features.items():
            if key not in self.active_query_schema:
                raise ValueError(f"{problem.id}: feature {key!r} not in query schema")
            allowed = self.active_query_schema[key]
            if str(value) not in allowed:
                raise ValueError(
                    f"{problem.id}: feature {key}={value!r} not in allowed {allowed}"
                )
        if "instance_key" not in problem.latent_parameters:
            raise ValueError(f"{problem.id}: missing latent_parameters['instance_key']")
        return True

    # --------------------------------------------------------- constraint util
    def check_constraints_wellformed(self, constraints: Dict[str, str]) -> None:
        """Validate feature names/values against the schema.

        Raises :class:`UnsatisfiableConstraints` with a descriptive reason.
        """
        if not isinstance(constraints, dict) or not constraints:
            raise UnsatisfiableConstraints("no constraints supplied", constraints or {})
        if len(constraints) > 3:
            raise UnsatisfiableConstraints(
                f"at most 3 constraints allowed, got {len(constraints)}", constraints
            )
        schema = self.queryable_schema()
        for key, value in constraints.items():
            if key not in schema:
                raise UnsatisfiableConstraints(
                    f"unknown feature name {key!r}", constraints
                )
            allowed = schema[key]
            for v in _as_value_list(value):
                if v not in allowed:
                    raise UnsatisfiableConstraints(
                        f"value {v!r} is not allowed for feature {key!r}; "
                        f"allowed values are {allowed}",
                        constraints,
                    )

    @staticmethod
    def matches(features: Dict[str, Any], constraints: Dict[str, str]) -> bool:
        """Subset-constraint matching: a constraint value may be a list."""
        for key, value in constraints.items():
            got = str(features.get(key))
            if got not in _as_value_list(value):
                return False
        return True

    # ------------------------------------------------------------ convenience
    def generate_seed_candidates(
        self, rng: random.Random, n: int, difficulty: str
    ) -> List[Problem]:
        """Successful (strategy_applies=True) demonstrations with worked solutions."""
        out: List[Problem] = []
        seen = set()
        guard = 0
        while len(out) < n and guard < 200 * n:
            guard += 1
            template = self.base_templates[len(out) % len(self.base_templates)]
            p = self.sample_random(rng, difficulty, template, want_applies=True)
            if not p.strategy_applies or not p.human_solution:
                continue
            if p.content_key() in seen:
                continue
            self.validate_problem(p)
            seen.add(p.content_key())
            out.append(p)
        if len(out) < n:
            raise RuntimeError(
                f"{self.name}: only produced {len(out)}/{n} seed candidates at "
                f"difficulty={difficulty}"
            )
        return out

    def generate_iid_test(
        self,
        rng: random.Random,
        n: int,
        difficulty: str,
        exclude: Optional[set] = None,
        balanced: bool = True,
    ) -> List[Problem]:
        return self._generate_split(
            rng, n, difficulty, self.base_templates, exclude, balanced
        )

    def generate_challenge_test(
        self,
        rng: random.Random,
        n: int,
        difficulty: str,
        exclude: Optional[set] = None,
        balanced: bool = True,
    ) -> List[Problem]:
        return self._generate_split(
            rng, n, difficulty, self.challenge_templates, exclude, balanced
        )

    def _generate_split(
        self,
        rng: random.Random,
        n: int,
        difficulty: str,
        templates: Sequence[str],
        exclude: Optional[set],
        balanced: bool,
    ) -> List[Problem]:
        exclude = set(exclude or ())
        out: List[Problem] = []
        seen: set = set()
        # Spec S.24(4): default to 50/50 applicability so a constant
        # "always APPLIES" rule cannot score highly.
        if balanced:
            wants = [True] * (n // 2) + [False] * (n - n // 2)
        else:
            wants = [None] * n
        rng.shuffle(wants)
        guard = 0
        for i, want in enumerate(wants):
            template = templates[i % len(templates)]
            while True:
                guard += 1
                if guard > 400 * n:
                    raise RuntimeError(
                        f"{self.name}: could not build {n} problems "
                        f"(difficulty={difficulty}, balanced={balanced}); got {len(out)}"
                    )
                p = self.sample_random(rng, difficulty, template, want_applies=want)
                if want is not None and p.strategy_applies != want:
                    continue
                key = p.content_key()
                if key in seen or key in exclude:
                    continue
                self.validate_problem(p)
                seen.add(key)
                out.append(p)
                break
        return out

    # -------------------------------------------------------------- versioning
    def version_hash(self) -> str:
        return stable_hash(
            {
                "name": self.name,
                "schema": self.active_query_schema,
                "schema_profile": self.schema_profile,
                "base_templates": self.base_templates,
                "challenge_templates": self.challenge_templates,
                "strategy": self.strategy_description,
            }
        )


def _as_value_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    return [str(value)]
