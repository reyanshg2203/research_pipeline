"""
Pipeline: SWI-Prolog scope / difficulty calibration.

This is the SECOND gate, run AFTER validation passes but BEFORE the prose
layer. Validation answers "is this problem well-posed and solvable by SOME
path?" Calibration answers a different question: "is it solvable by an
IN-SCOPE path, and at the right difficulty for its lesson?"

The distinction matters because the validator's target-resolvability check
accepts ANY derivation path — including theorems the lesson does not permit
(e.g. law_of_cosines in a similarity unit). A problem can therefore pass
validation while being solvable ONLY via a forbidden method. Such a problem
should never reach the prose layer, because the prose would faithfully narrate
an intended method that doesn't actually work. `shortest_in_scope/4` filters
derivations to the lesson's allow-list; when nothing in scope remains it
returns `none` → verdict `out_of_scope`, and we reject back to regeneration.

Reuses validate.py's fact-assertion machinery verbatim (same Layer-0 predicates,
same _pl_value encoding) so the asserted Prolog state is identical to what the
validator saw. Adds consulting of calibration.pl and lesson_data.pl on top of
geometry_validator.pl (which the traced derivation predicates live in).

Requires SWI-Prolog and pyswip, exactly like validate.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pyswip import Prolog

# Reuse validate.py's engine: the Prolog() singleton, the validator consult,
# the dynamic declarations, the schema-assertion helpers, and the state
# retraction. We layer calibration on the SAME asserted facts.
from validate import (  # noqa: E402
    ROOT,
    ValidationEngineError,
    _assert_schema,
    _load_validator,
    _retract_state,
)

CALIBRATION_PL = ROOT / "calibration.pl"
LESSON_DATA_PL = ROOT / "lesson_data.pl"

# In-scope verdict tags that are acceptable to send to the prose layer.
# `in_band` is the clean case. Whether to also accept `too_easy` / `too_hard`
# is a policy choice exposed via `accept_off_band` below; `out_of_scope` is
# NEVER acceptable (the problem has no in-scope solution at all).
ACCEPTABLE_IN_BAND = "in_band"

_CALIBRATION_LOADED = False


def _normalize_lesson_atom(lesson: str) -> str:
    """
    calibration.pl keys lessons as atoms like `lesson_10`. Schemas carry the
    lesson in the same form, but be defensive: strip a trailing '.txt', and if
    given a bare number or 'lesson_10_001'-style id, reduce to 'lesson_NN'.
    """
    s = lesson.strip().replace(".txt", "")
    # already canonical
    if s.startswith("lesson_"):
        parts = s.split("_")
        # lesson_10  ->  lesson_10 ;  lesson_10_001 -> lesson_10
        if len(parts) >= 2 and parts[1].isdigit():
            return f"lesson_{int(parts[1]):02d}"
    # bare number
    digits = "".join(c for c in s if c.isdigit())
    if digits:
        return f"lesson_{int(digits):02d}"
    return s


def _load_calibration(prolog: Prolog) -> None:
    """Consult calibration.pl + lesson_data.pl once per process (singleton)."""
    global _CALIBRATION_LOADED
    if _CALIBRATION_LOADED:
        return
    for pl_file in (LESSON_DATA_PL, CALIBRATION_PL):
        if not pl_file.is_file():
            raise ValidationEngineError(f"Calibration file not found: {pl_file}")
        prolog.consult(str(pl_file))
    _CALIBRATION_LOADED = True


def _pl_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _flatten_trace(trace: Any) -> list[str]:
    """A single OOS trace is a Prolog list of theorem atoms; pyswip hands it
    back as a Python list (possibly of bytes/atoms). Flatten one level and
    stringify, tolerating a bare scalar."""
    if isinstance(trace, (list, tuple)):
        out: list[str] = []
        for t in trace:
            if isinstance(t, (list, tuple)):
                out.extend(_pl_text(x) for x in t)
            else:
                out.append(_pl_text(t))
        return out
    return [_pl_text(trace)]


def _extract_oos_concepts(
    prolog: Prolog, lesson_atom: str, out_of_scope: Any
) -> list[str]:
    """Return the distinct theorem names that appear in out-of-scope derivation
    paths but are NOT in the lesson's allow-list — i.e. the forbidden concepts
    that make the target reachable only out of scope. This is the actionable
    feedback: it names WHICH concept the problem illegitimately depends on, so
    the repair step can be told to restructure away from it."""
    # The lesson's allowed theorems.
    try:
        allow_rows = list(prolog.query(f"lesson_allows({lesson_atom}, A)"))
    except Exception:
        allow_rows = []
    allowed: set[str] = set()
    if allow_rows:
        allowed = {_pl_text(x) for x in _flatten_trace(allow_rows[0].get("A"))}

    forbidden: list[str] = []
    seen: set[str] = set()
    if isinstance(out_of_scope, (list, tuple)):
        for trace in out_of_scope:
            for theorem in _flatten_trace(trace):
                if theorem not in allowed and theorem not in seen:
                    seen.add(theorem)
                    forbidden.append(theorem)
    return sorted(forbidden)


def calibrate(schema: "Any", *, accept_off_band: bool = True) -> dict[str, Any]:
    """
    Score a (already validation-passing) ProblemSchema for scope and difficulty.

    Returns a dict:
      {
        "lesson": "lesson_10",
        "min_steps": <int> | None,        # None == no in-scope derivation
        "best_trace": [...],              # the cheapest in-scope theorem list
        "n_out_of_scope": <int>,          # how many forbidden-only paths exist
        "verdict": "in_band" | "too_easy" | "too_hard" | "out_of_scope",
        "accepted": <bool>,               # may this go to the prose layer?
        "reason": "<human-readable>",
      }

    `accepted` is False when verdict == 'out_of_scope' (always) and when verdict
    == 'too_easy' (always — the floor is trusted, so a below-floor problem is a
    defect to repair). 'too_hard' is accepted unless accept_off_band is False. The
    caller (refine_schema) uses `accepted` to decide prose vs. reject/repair.
    """
    prolog = Prolog()
    _load_validator(prolog)       # geometry_validator.pl (traced derivations)
    _load_calibration(prolog)     # lesson_data.pl + calibration.pl
    _retract_state(prolog)        # clear any prior schema's facts
    _assert_schema(prolog, schema)  # assert THIS schema's Layer-0 facts

    lesson_atom = _normalize_lesson_atom(schema.lesson)

    # shortest_in_scope(+Lesson, -MinSteps, -BestTrace, -OutOfScope)
    try:
        rows = list(
            prolog.query(
                f"shortest_in_scope({lesson_atom}, Min, Trace, OOS)"
            )
        )
    except Exception as exc:  # PrologError or pyswip wrapping
        raise ValidationEngineError(
            f"shortest_in_scope/4 failed for {lesson_atom}: {exc}"
        ) from exc

    if not rows:
        # No solution to the query at all — treat as out_of_scope/unsolvable.
        return {
            "lesson": lesson_atom,
            "min_steps": None,
            "best_trace": [],
            "n_out_of_scope": 0,
            "out_of_scope_concepts": [],
            "verdict": "out_of_scope",
            "accepted": False,
            "reason": "shortest_in_scope/4 produced no solution (no derivation found).",
        }

    row = rows[0]
    raw_min = _pl_text(row["Min"])
    out_of_scope = row.get("OOS") or []
    n_oos = len(out_of_scope) if isinstance(out_of_scope, list) else 0
    oos_concepts = _extract_oos_concepts(prolog, lesson_atom, out_of_scope)

    # MinSteps is the atom `none` when no in-scope derivation exists.
    if raw_min == "none":
        if oos_concepts:
            concept_phrase = ", ".join(oos_concepts)
            reason = (
                f"No in-scope derivation: the target is reachable only via "
                f"{concept_phrase}, which lesson {lesson_atom} does not teach. "
                f"Restructure so an allowed method reaches the target."
            )
        else:
            reason = (
                f"No in-scope derivation: target is solvable only via "
                f"{n_oos} forbidden-theorem path(s) the lesson does not allow."
            )
        return {
            "lesson": lesson_atom,
            "min_steps": None,
            "best_trace": [],
            "n_out_of_scope": n_oos,
            "out_of_scope_concepts": oos_concepts,
            "verdict": "out_of_scope",
            "accepted": False,
            "reason": reason,
        }

    try:
        min_steps = int(raw_min)
    except ValueError:
        raise ValidationEngineError(
            f"Unexpected MinSteps from shortest_in_scope: {raw_min!r}"
        )

    best_trace = [
        _pl_text(t) for t in (row.get("Trace") or [])
    ] if isinstance(row.get("Trace"), list) else []

    # Now band classification, mirroring calibration.pl's verdict/1:
    #   Min < floor -> too_easy ; Min > ceil -> too_hard ; else in_band
    floor_rows = list(prolog.query(f"lesson_min_steps({lesson_atom}, F)"))
    ceil_rows = list(prolog.query(f"lesson_max_steps({lesson_atom}, C)"))
    floor = int(_pl_text(floor_rows[0]["F"])) if floor_rows else None
    ceil = int(_pl_text(ceil_rows[0]["C"])) if ceil_rows else None

    if floor is None or ceil is None:
        verdict = ACCEPTABLE_IN_BAND  # no band data: don't block on difficulty
        reason = "No band data for lesson; in-scope derivation exists, accepting."
    elif min_steps < floor:
        verdict = "too_easy"
        reason = f"{min_steps} in-scope steps is below the lesson floor of {floor}."
    elif min_steps > ceil:
        verdict = "too_hard"
        reason = f"{min_steps} in-scope steps exceeds the lesson ceiling of {ceil}."
    else:
        verdict = ACCEPTABLE_IN_BAND
        reason = f"{min_steps} in-scope steps lands in band [{floor}..{ceil}]."

    # The lesson FLOOR is trusted, so `too_easy` is a genuine quality defect:
    # the problem is solvable below the intended step count and does not exercise
    # the method the lesson teaches. It is therefore NOT accepted — it counts as a
    # calibration error so the repair loop tries to make the intended method
    # necessary (add an in-scope step). `too_hard` remains governed by
    # accept_off_band, because lesson CEILINGS are still estimates and we do not
    # want to reject an otherwise-valid problem against an untrusted upper bound.
    accepted = verdict == ACCEPTABLE_IN_BAND or (
        accept_off_band and verdict == "too_hard"
    )

    return {
        "lesson": lesson_atom,
        "min_steps": min_steps,
        "best_trace": best_trace,
        "n_out_of_scope": n_oos,
        "out_of_scope_concepts": oos_concepts,
        "verdict": verdict,
        "accepted": accepted,
        "reason": reason,
    }


def calibrate_file(path: str | Path, *, accept_off_band: bool = True) -> dict[str, Any]:
    """Load a JSON schema file and calibrate it."""
    from schema import ProblemSchema  # local import; mirrors validate.py layering

    data = json.loads(Path(path).read_text())
    schema = ProblemSchema.model_validate(data)
    return calibrate(schema, accept_off_band=accept_off_band)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scope/difficulty calibration for a ProblemSchema JSON file."
    )
    parser.add_argument("schema", type=Path, help="Path to schema JSON")
    parser.add_argument(
        "--strict-band",
        action="store_true",
        help="Also reject too_hard (default accepts too_hard against the estimated ceiling; too_easy is always rejected since the floor is trusted).",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    result = calibrate_file(args.schema, accept_off_band=not args.strict_band)
    print(json.dumps(result, indent=2 if args.pretty else None))
    return 0 if result.get("accepted") else 1


if __name__ == "__main__":
    raise SystemExit(main())