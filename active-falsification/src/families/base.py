"""Common interface for problem families.

A family owns:
  * the mathematical generator,
  * the exact answer computation,
  * the programmatic applicability oracle for its intended strategy S,
  * TWO separate feature namespaces (revision memo S.4).

Feature namespaces
------------------
``query_schema()``
    The observable experimental controls the Active condition may request.
    Every value must be readable off the problem statement by a competent
    solver, so that choosing a region is an experiment rather than a lookup.

``oracle_feature_schema``
    Researcher-only diagnostics for validation, balancing and audit.  Several
    are deterministic synonyms for ``strategy_applies`` -- that is precisely why
    they live here and are never shown to a model or accepted in a constraint.

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

    #: Observable controls Active may constrain.  feature -> allowed values.
    #: ``task_form`` is added automatically from ``base_templates``.
    queryable_features: Dict[str, List[str]] = {}

    #: Researcher-only diagnostics.  NEVER exposed to a model.
    oracle_feature_schema: Dict[str, List[str]] = {}

    #: templates used for seeds / calibration / IID practice+test
    base_templates: List[str] = []

    #: held-out templates used only for the challenge split
    challenge_templates: List[str] = []

    difficulties: List[str] = ["easy", "medium", "hard"]

    # ------------------------------------------------------------- schemas
    def query_schema(self) -> Dict[str, List[str]]:
        """What the Active condition sees and may constrain.

        ``task_form`` lists only the BASE templates: the challenge surfaces are
        held out, so Active must never be able to request one during adaptation.
        """
        schema = dict(self.queryable_features)
        schema["task_form"] = list(self.base_templates)
        return schema

    def _validation_domain(self) -> Dict[str, List[str]]:
        """Allowed query-feature values for validation.

        Identical to :meth:`query_schema` except that ``task_form`` also admits
        the challenge templates, since challenge problems carry one.
        """
        domain = dict(self.queryable_features)
        domain["task_form"] = list(self.base_templates) + list(self.challenge_templates)
        return domain

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
        domain = self._validation_domain()
        for key, value in problem.query_features.items():
            if key not in domain:
                raise ValueError(f"{problem.id}: query feature {key!r} not in schema")
            if str(value) not in domain[key]:
                raise ValueError(
                    f"{problem.id}: query feature {key}={value!r} not in {domain[key]}"
                )
        for key, value in problem.oracle_features.items():
            if key not in self.oracle_feature_schema:
                raise ValueError(f"{problem.id}: oracle feature {key!r} not in schema")
            if str(value) not in self.oracle_feature_schema[key]:
                raise ValueError(
                    f"{problem.id}: oracle feature {key}={value!r} not in "
                    f"{self.oracle_feature_schema[key]}"
                )
        overlap = set(problem.query_features) & set(problem.oracle_features)
        if overlap:
            raise ValueError(
                f"{problem.id}: features {sorted(overlap)} appear in both namespaces"
            )
        if not problem.applicability_reason:
            raise ValueError(f"{problem.id}: missing applicability_reason")
        if "instance_key" not in problem.latent_parameters:
            raise ValueError(f"{problem.id}: missing latent_parameters['instance_key']")
        return True

    # --------------------------------------------------------- constraint util
    def check_constraints_wellformed(self, constraints: Dict[str, str]) -> None:
        """Validate feature names/values against the QUERY schema.

        Oracle feature names are rejected exactly like unknown names: the model
        must not learn that they exist.
        """
        if not isinstance(constraints, dict) or not constraints:
            raise UnsatisfiableConstraints("no constraints supplied", constraints or {})
        if len(constraints) > 3:
            raise UnsatisfiableConstraints(
                f"at most 3 constraints allowed, got {len(constraints)}", constraints
            )
        schema = self.query_schema()
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

    @staticmethod
    def requested_template(
        constraints: Dict[str, str], default: str
    ) -> str:
        """Honour a ``task_form`` constraint by switching the rendered template."""
        want = constraints.get("task_form")
        if want is None:
            return default
        options = _as_value_list(want)
        return default if default in options else options[0]

    # ------------------------------------------------- Stage-1 calibration
    def calibration_plan(self, per_tier: int, difficulty: str) -> List[Optional[bool]]:
        """Optional per-slot plan of desired PUBLIC ANSWER kinds for the bank.

        ``True`` asks for an instance whose exact answer is a value, ``False``
        for one whose exact answer is "no solution", ``None`` for no preference.
        The default is no preference, which is an unconditional draw.

        This is stated in terms of the exact answer, never the applicability
        label: Stage 1 sees only the public problem and its exact answer.
        """
        return [None] * per_tier

    def sample_for_calibration(
        self,
        rng: random.Random,
        difficulty: str,
        template: str,
        slot_index: int,
        per_tier: int,
    ) -> Problem:
        """Draw one problem for slot ``slot_index`` of the Stage-1 bank.

        The default is exactly an unconditional ``sample_random``, so a family
        that does not override this behaves identically to a family with no
        calibration plan at all.
        """
        return self.sample_random(rng, difficulty, template, want_applies=None)

    # ------------------------------------------------------------ seed strata
    def seed_strata(self, n_seeds: int) -> List[Dict[str, str]]:
        """Constraint dicts stratifying the seed demonstrations.

        Revision memo S.1/S.2: the successful demonstrations must not all share
        one surface property (all-prime moduli, or all valuation-0 instances),
        or the model can induce a trivially wrong rule from the seeds alone.
        Strata are advisory: one that is unsatisfiable at the selected difficulty
        falls back to an unconstrained draw and is recorded as such.
        """
        return [{} for _ in range(n_seeds)]

    def generate_seed_candidates(
        self, rng: random.Random, n: int, difficulty: str
    ) -> List[Problem]:
        """Successful (strategy_applies=True) demonstrations with worked solutions."""
        strata = self.seed_strata(n)
        out: List[Problem] = []
        seen = set()
        for index in range(n):
            stratum = strata[index % len(strata)] if strata else {}
            problem = self._draw_seed(rng, difficulty, stratum, seen, index)
            if problem is None:
                problem = self._draw_seed(rng, difficulty, {}, seen, index)
            if problem is None:
                raise RuntimeError(
                    f"{self.name}: could not build seed candidate {index + 1}/{n} "
                    f"at difficulty={difficulty} (stratum={stratum})"
                )
            seen.add(problem.content_key())
            out.append(problem)
        return out

    def _draw_seed(
        self,
        rng: random.Random,
        difficulty: str,
        stratum: Dict[str, str],
        seen: set,
        index: int,
    ) -> Optional[Problem]:
        template = self.base_templates[index % len(self.base_templates)]
        for _ in range(400):
            if stratum:
                try:
                    p = self.sample_conditioned(rng, stratum, difficulty, template)
                except UnsatisfiableConstraints:
                    return None
                if p is None:
                    return None
                if not p.strategy_applies:
                    continue
            else:
                p = self.sample_random(rng, difficulty, template, want_applies=True)
            if not p.strategy_applies or not p.human_solution:
                continue
            if p.content_key() in seen:
                continue
            self.validate_problem(p)
            return p
        return None

    # ------------------------------------------------------------ test splits
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

    # ---------------------------------------------------------------- preview
    def preview_extras(self, problem: Problem) -> Dict[str, str]:
        """Family-specific researcher-side fields for the human review preview.

        Revision memo S.8.  Purely for inspection; nothing in the pipeline reads
        this.
        """
        return {}

    # -------------------------------------------------------------- versioning
    def version_hash(self) -> str:
        return stable_hash(
            {
                "name": self.name,
                "query_schema": self.query_schema(),
                "oracle_schema": self.oracle_feature_schema,
                "base_templates": self.base_templates,
                "challenge_templates": self.challenge_templates,
                "strategy": self.strategy_description,
            }
        )


def _as_value_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    return [str(value)]
