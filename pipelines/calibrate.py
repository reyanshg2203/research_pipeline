"""
Pipeline: SWI-Prolog scope / difficulty / alignment calibration.

SECOND gate, run AFTER validation passes but BEFORE the prose layer.
  validation : "well-posed and solvable by SOME path?"
  calibration: "solvable by an IN-SCOPE path that USES THE LESSON SKILL, at the
                right difficulty?"

Verdicts:
  in_band | too_easy | too_hard              (difficulty band)
  out_of_scope    no allowed derivation at all (only forbidden theorems reach
                  the target)                -> restructure away from them.
  alignment_fail  an allowed derivation exists, but none uses this lesson's own
                  skill (the problem is solved entirely by a prior-lesson
                  method), OR a cheaper allowed derivation skips the skill
                  -> rebuild so the lesson skill is load-bearing.

out_of_scope, alignment_fail, and too_easy are never accepted. too_hard is
accepted unless accept_off_band is False.

Reuses validate.py's fact-assertion machinery; consults calibration.pl +
lesson_data.pl on top of the traced validator. Requires SWI-Prolog + pyswip.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pyswip import Prolog

from validate import (  # noqa: E402
    ROOT,
    ValidationEngineError,
    _assert_schema,
    _load_validator,
    _retract_state,
)

CALIBRATION_PL = ROOT / "calibration.pl"
LESSON_DATA_PL = ROOT / "lesson_data.pl"

ACCEPTABLE_IN_BAND = "in_band"

# Policy for targets the step-counting engine cannot trace at all (verdict
# "untraceable"): these pass validation but have an answer type target_derivable/3
# doesn't model (scale-factor readout, perimeter, classification, inequality).
# True  -> accept and let prose proceed (defer to validation; recommended so the
#          gate doesn't reject well-posed problems it simply can't score).
# False -> reject, so these are flagged for manual review / regeneration.
ACCEPT_UNTRACEABLE = False

_CALIBRATION_LOADED = False


def _normalize_lesson_atom(lesson: str) -> str:
    s = lesson.strip().replace(".txt", "")
    if s.startswith("lesson_"):
        parts = s.split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            return f"lesson_{int(parts[1]):02d}"
    digits = "".join(c for c in s if c.isdigit())
    if digits:
        return f"lesson_{int(digits):02d}"
    return s


def _load_calibration(prolog: Prolog) -> None:
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
    if isinstance(trace, (list, tuple)):
        out: list[str] = []
        for t in trace:
            if isinstance(t, (list, tuple)):
                out.extend(_pl_text(x) for x in t)
            else:
                out.append(_pl_text(t))
        return out
    return [_pl_text(trace)]


def _lesson_allowed_set(prolog: Prolog, lesson_atom: str) -> set[str]:
    try:
        rows = list(prolog.query(f"lesson_allows({lesson_atom}, A)"))
    except Exception:
        return set()
    if rows:
        return {_pl_text(x) for x in _flatten_trace(rows[0].get("A"))}
    return set()


def _extract_oos_concepts(allowed: set[str], out_of_scope: Any) -> list[str]:
    forbidden: list[str] = []
    seen: set[str] = set()
    if isinstance(out_of_scope, (list, tuple)):
        for trace in out_of_scope:
            for theorem in _flatten_trace(trace):
                if theorem not in allowed and theorem not in seen:
                    seen.add(theorem)
                    forbidden.append(theorem)
    return sorted(forbidden)


def _as_int_or_none(s: str | None) -> int | None:
    if s is None or s == "none":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def calibrate(schema: "Any", *, accept_off_band: bool = True) -> dict[str, Any]:
    """
    Score a (validation-passing) ProblemSchema for scope, alignment, difficulty.

    Returns a dict with keys:
      lesson, min_steps, best_trace, any_min_steps, n_out_of_scope,
      out_of_scope_concepts, verdict, accepted, reason
    """
    prolog = Prolog()
    _load_validator(prolog)
    _load_calibration(prolog)
    _retract_state(prolog)
    _assert_schema(prolog, schema)

    lesson_atom = _normalize_lesson_atom(schema.lesson)
    allowed = _lesson_allowed_set(prolog, lesson_atom)

    # (1) shortest in-scope + requirement-satisfying
    try:
        req_rows = list(
            prolog.query(f"shortest_in_scope({lesson_atom}, Min, Trace, OOS)")
        )
    except Exception as exc:
        raise ValidationEngineError(
            f"shortest_in_scope/4 failed for {lesson_atom}: {exc}"
        ) from exc
    if req_rows:
        req_min = _as_int_or_none(_pl_text(req_rows[0]["Min"]))
        rt = req_rows[0].get("Trace")
        req_trace = [_pl_text(t) for t in rt] if isinstance(rt, list) else []
        oos = req_rows[0].get("OOS") or []
    else:
        req_min, req_trace, oos = None, [], []

    # (2) shortest in-scope ignoring requirement
    try:
        any_rows = list(
            prolog.query(f"shortest_allowed_any({lesson_atom}, Min, Trace)")
        )
    except Exception as exc:
        raise ValidationEngineError(
            f"shortest_allowed_any/3 failed for {lesson_atom}: {exc}"
        ) from exc
    any_min = _as_int_or_none(_pl_text(any_rows[0]["Min"])) if any_rows else None

    n_oos = len(oos) if isinstance(oos, list) else 0
    oos_concepts = _extract_oos_concepts(allowed, oos)

    base = {
        "lesson": lesson_atom,
        "n_out_of_scope": n_oos,
        "out_of_scope_concepts": oos_concepts,
        "any_min_steps": any_min,
    }

    # (A) No allowed, requirement-satisfying derivation was found. This splits
    # into two DIFFERENT situations that must not be conflated:
    if any_min is None:
        if n_oos > 0:
            # Genuinely OUT OF SCOPE: derivations of the target exist, but every
            # one uses a method this lesson does not teach.
            return {
                **base, "min_steps": None, "best_trace": [],
                "verdict": "out_of_scope", "accepted": False,
                "reason": (
                    f"Out of scope: the only derivation(s) of the target use "
                    f"{', '.join(oos_concepts) if oos_concepts else f'{n_oos} method(s)'} "
                    f"that lesson {lesson_atom} does not teach. Restructure so an "
                    f"allowed method reaches the target."
                ),
            }
        # n_oos == 0: target_derivable/3 produced NO trace at all — not an
        # allowed one, not a forbidden one. This is NOT out of scope; the traced
        # reachability engine simply cannot express this target's answer type
        # (e.g. a scale-factor readout, a perimeter, a classification, or an
        # inequality bound). Validation already vouched for the schema, so we
        # defer to it rather than fabricating a "0 forbidden paths" scope failure.
        return {
            **base, "min_steps": None, "best_trace": [],
            "verdict": "untraceable", "accepted": ACCEPT_UNTRACEABLE,
            "reason": (
                f"Calibration could not trace any derivation of the target for "
                f"lesson {lesson_atom}: target_derivable/3 yields no path, so scope "
                f"and difficulty cannot be scored. This is a coverage limit of the "
                f"step-counting engine (the target's answer type is not a "
                f"length/angle derivation), NOT an out-of-scope condition. "
                f"Validation already passed this schema."
            ),
        }

    # (B) ALIGNMENT FAIL — no skill-using path (solved only by prior methods).
    if req_min is None:
        return {
            **base, "min_steps": None, "best_trace": [],
            "verdict": "alignment_fail", "accepted": False,
            "reason": (
                f"Solvable in {any_min} in-scope step(s), but NO derivation uses "
                f"lesson {lesson_atom}'s own skill — the problem is solved "
                f"entirely with prior-lesson methods. Rebuild so the lesson's "
                f"skill is load-bearing: change the target, the givens, or the "
                f"declared relationship so the intended method is required."
            ),
        }

    # (C) ALIGNMENT FAIL — a cheaper allowed path skips the skill.
    if any_min < req_min:
        return {
            **base, "min_steps": req_min, "best_trace": req_trace,
            "verdict": "alignment_fail", "accepted": False,
            "reason": (
                f"A {req_min}-step path uses the lesson skill, but a cheaper "
                f"{any_min}-step in-scope path skips it, so a student can solve "
                f"this below level. Retarget or change the givens so the skill "
                f"path is the shortest route (for altitude/geometric-mean "
                f"lessons, target the altitude or a hypotenuse segment rather "
                f"than a leg or the hypotenuse)."
            ),
        }

    # (D) In scope, skill-using: classify difficulty band.
    floor_rows = list(prolog.query(f"lesson_min_steps({lesson_atom}, F)"))
    ceil_rows = list(prolog.query(f"lesson_max_steps({lesson_atom}, C)"))
    floor = int(_pl_text(floor_rows[0]["F"])) if floor_rows else None
    ceil = int(_pl_text(ceil_rows[0]["C"])) if ceil_rows else None

    if floor is None or ceil is None:
        verdict, reason = ACCEPTABLE_IN_BAND, "No band data; skill derivation exists, accepting."
    elif req_min < floor:
        verdict = "too_easy"
        reason = f"{req_min} in-scope steps is below the lesson floor of {floor}."
    elif req_min > ceil:
        verdict = "too_hard"
        reason = f"{req_min} in-scope steps exceeds the lesson ceiling of {ceil}."
    else:
        verdict = ACCEPTABLE_IN_BAND
        reason = f"{req_min} in-scope steps lands in band [{floor}..{ceil}]."

    accepted = verdict == ACCEPTABLE_IN_BAND or (accept_off_band and verdict == "too_hard")

    return {
        **base, "min_steps": req_min, "best_trace": req_trace,
        "verdict": verdict, "accepted": accepted, "reason": reason,
    }


def calibrate_file(path: str | Path, *, accept_off_band: bool = True) -> dict[str, Any]:
    from schema import ProblemSchema  # local import; mirrors validate.py layering

    data = json.loads(Path(path).read_text())
    schema = ProblemSchema.model_validate(data)
    return calibrate(schema, accept_off_band=accept_off_band)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scope/alignment/difficulty calibration for a ProblemSchema JSON file."
    )
    parser.add_argument("schema", type=Path, help="Path to schema JSON")
    parser.add_argument(
        "--strict-band", action="store_true",
        help="Also reject too_hard (too_easy and alignment_fail are always rejected).",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    result = calibrate_file(args.schema, accept_off_band=not args.strict_band)
    print(json.dumps(result, indent=2 if args.pretty else None))
    return 0 if result.get("accepted") else 1


if __name__ == "__main__":
    raise SystemExit(main())