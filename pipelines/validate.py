"""
Pipeline: SWI-Prolog geometry schema validation.

Loads `geometry_validator.pl`, asserts facts from a `ProblemSchema`, runs
`feedback_bundle/1` and `emit_json/0`, and returns the parsed JSON feedback dict.

Requires SWI-Prolog (for pyswip) and the `pyswip` package.

NOTE: pyswip's `Prolog()` is a process-wide singleton. Each call to
`validate()` therefore reuses the same Prolog database. We explicitly
retract all Layer-0 facts before asserting a new schema so iterations
in a repair loop don't see stale facts from previous schemas.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from pyswip import Prolog
from pyswip.prolog import PrologError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schema import (  # noqa: E402
    Circle,
    Line,
    Point,
    Polygon,
    ProblemSchema,
    Relationship,
    Segment,
    Shapes,
    Triangle,
)

VALIDATOR_PL = ROOT / "geometry_validator.pl"
LESSON_DATA_PL = ROOT / "lesson_data.pl"     # difficulty: per-lesson allow-lists + step bands
CALIBRATION_PL = ROOT / "calibration.pl"     # difficulty: shortest_in_scope / verdict scorer

# Layer-0 fact predicates (host-asserted; must be declared dynamic when empty
# AND must be retracted before each fresh validation to avoid stale state
# across calls — pyswip uses a process-wide singleton Prolog engine).
LAYER0_PREDICATES = (
    ("problem", 2),
    ("entity", 2),
    ("triangle_side", 3),
    ("triangle_angle", 3),
    ("triangle_flag", 2),
    ("polygon_n_sides", 2),
    ("polygon_side", 3),
    ("polygon_angle", 3),
    ("segment_length", 2),
    ("segment_flag", 2),
    ("segment_parallel_to", 2),
    ("segment_perpendicular_to", 2),
    ("segment_ratio_to", 3),
    ("line_parallel_to", 2),
    ("line_perpendicular_to", 2),
    ("point_lies_on", 2),
    ("point_intersection_of", 2),
    ("circle_radius", 2),
    ("relationship", 3),
    ("rel_attr", 3),
    ("target", 2),
)

# Also retract error-accumulator state, which the validator asserts during runs.
RUNTIME_PREDICATES = (
    ("collected_error", 1),
)


class ValidationEngineError(RuntimeError):
    """SWI-Prolog / pyswip setup or query failure."""


_VALIDATOR_LOADED = False


def _pl_atom(value: str) -> str:
    """Quote a string as a Prolog atom (handles uppercase / special chars)."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _pl_value(value: Any) -> str:
    """Convert a Python JSON value to a Prolog term string."""
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _pl_atom(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[" + ", ".join(_pl_value(item) for item in value) + "]"
    raise TypeError(f"Unsupported attribute value type: {type(value)!r}")


def _assert_fact(prolog: Prolog, functor: str, *args: Any) -> None:
    terms = ", ".join(
        arg if isinstance(arg, str) and not arg.startswith("'") else str(arg)
        for arg in args
    )
    prolog.assertz(f"{functor}({terms})")


def _declare_dynamic(prolog: Prolog) -> None:
    """Declare every host-asserted predicate as dynamic so retractall works."""
    for functor, arity in LAYER0_PREDICATES + RUNTIME_PREDICATES:
        list(prolog.query(f"dynamic({functor}/{arity})"))


def _retract_state(prolog: Prolog) -> None:
    """Clear all schema facts and error state from a previous run."""
    for functor, arity in LAYER0_PREDICATES + RUNTIME_PREDICATES:
        args = ", ".join("_" for _ in range(arity))
        list(prolog.query(f"retractall({functor}({args}))"))


def _load_validator(prolog: Prolog) -> None:
    """Consult the validator once per process (pyswip Prolog is a singleton)."""
    global _VALIDATOR_LOADED
    if _VALIDATOR_LOADED:
        return
    if not VALIDATOR_PL.is_file():
        raise ValidationEngineError(f"Validator not found: {VALIDATOR_PL}")
    prolog.consult(str(VALIDATOR_PL))
    # Difficulty layer: load the lesson data (allow-lists + bands) and the
    # calibration scorer. Optional — validity still works without them.
    if LESSON_DATA_PL.is_file():
        prolog.consult(str(LESSON_DATA_PL))
    if CALIBRATION_PL.is_file():
        prolog.consult(str(CALIBRATION_PL))
    _declare_dynamic(prolog)
    _VALIDATOR_LOADED = True


def _assert_triangle(prolog: Prolog, tri: Triangle) -> None:
    _assert_fact(prolog, "entity", "triangle", _pl_atom(tri.id))
    for key, val in (tri.sides or {}).items():
        _assert_fact(
            prolog,
            "triangle_side",
            _pl_atom(tri.id),
            _pl_atom(key),
            _pl_value(val),
        )
    for key, val in (tri.angles or {}).items():
        _assert_fact(
            prolog,
            "triangle_angle",
            _pl_atom(tri.id),
            _pl_atom(key),
            _pl_value(val),
        )
    for flag, enabled in (
        ("is_right", tri.is_right),
        ("is_isosceles", tri.is_isosceles),
        ("is_equilateral", tri.is_equilateral),
    ):
        if enabled:
            _assert_fact(prolog, "triangle_flag", _pl_atom(tri.id), flag)


def _assert_segment(prolog: Prolog, seg: Segment) -> None:
    _assert_fact(prolog, "entity", "segment", _pl_atom(seg.id))
    if seg.length is not None:
        _assert_fact(
            prolog, "segment_length", _pl_atom(seg.id), _pl_value(seg.length)
        )
    if seg.parallel_to:
        _assert_fact(
            prolog,
            "segment_parallel_to",
            _pl_atom(seg.id),
            _pl_atom(seg.parallel_to),
        )
    if seg.perpendicular_to:
        _assert_fact(
            prolog,
            "segment_perpendicular_to",
            _pl_atom(seg.id),
            _pl_atom(seg.perpendicular_to),
        )
    for other_id, ratio in (seg.ratio_to or {}).items():
        _assert_fact(
            prolog,
            "segment_ratio_to",
            _pl_atom(seg.id),
            _pl_atom(other_id),
            _pl_value(ratio),
        )
    for flag, enabled in (("is_midsegment", seg.is_midsegment), ("is_altitude", seg.is_altitude)):
        if enabled:
            _assert_fact(prolog, "segment_flag", _pl_atom(seg.id), flag)


def _assert_polygon(prolog: Prolog, poly: Polygon) -> None:
    _assert_fact(prolog, "entity", "polygon", _pl_atom(poly.id))
    _assert_fact(prolog, "polygon_n_sides", _pl_atom(poly.id), poly.n_sides)
    for key, val in (poly.sides or {}).items():
        _assert_fact(
            prolog,
            "polygon_side",
            _pl_atom(poly.id),
            _pl_atom(key),
            _pl_value(val),
        )
    for key, val in (poly.angles or {}).items():
        _assert_fact(
            prolog,
            "polygon_angle",
            _pl_atom(poly.id),
            _pl_atom(key),
            _pl_value(val),
        )


def _assert_line(prolog: Prolog, line: Line) -> None:
    _assert_fact(prolog, "entity", "line", _pl_atom(line.id))
    for other in line.parallel_to or []:
        _assert_fact(
            prolog, "line_parallel_to", _pl_atom(line.id), _pl_atom(other)
        )
    for other in line.perpendicular_to or []:
        _assert_fact(
            prolog,
            "line_perpendicular_to",
            _pl_atom(line.id),
            _pl_atom(other),
        )


def _assert_point(prolog: Prolog, point: Point) -> None:
    _assert_fact(prolog, "entity", "point", _pl_atom(point.id))
    for entity_id in point.lies_on or []:
        _assert_fact(
            prolog, "point_lies_on", _pl_atom(point.id), _pl_atom(entity_id)
        )
    for entity_id in point.is_intersection_of or []:
        _assert_fact(
            prolog,
            "point_intersection_of",
            _pl_atom(point.id),
            _pl_atom(entity_id),
        )


def _assert_circle(prolog: Prolog, circle: Circle) -> None:
    _assert_fact(prolog, "entity", "circle", _pl_atom(circle.id))
    if circle.radius is not None:
        _assert_fact(
            prolog, "circle_radius", _pl_atom(circle.id), _pl_value(circle.radius)
        )


def _assert_entities(prolog: Prolog, entities: Shapes) -> None:
    for tri in entities.triangles or []:
        _assert_triangle(prolog, tri)
    for seg in entities.segments or []:
        _assert_segment(prolog, seg)
    for poly in entities.polygons or []:
        _assert_polygon(prolog, poly)
    for line in entities.lines or []:
        _assert_line(prolog, line)
    for point in entities.points or []:
        _assert_point(prolog, point)
    for circle in entities.circles or []:
        _assert_circle(prolog, circle)


def _assert_relationship(prolog: Prolog, index: int, rel: Relationship) -> None:
    entity_list = "[" + ", ".join(_pl_atom(e) for e in rel.entities) + "]"
    rel_type = rel.type.value if hasattr(rel.type, "value") else str(rel.type)
    _assert_fact(prolog, "relationship", index, rel_type, entity_list)
    for key, value in (rel.attributes or {}).items():
        _assert_fact(prolog, "rel_attr", index, key, _pl_value(value))


def _assert_schema(prolog: Prolog, schema: ProblemSchema) -> None:
    _assert_fact(
        prolog,
        "problem",
        _pl_atom(schema.problem_id),
        _pl_atom(schema.lesson),
    )
    _assert_entities(prolog, schema.entities)
    for index, rel in enumerate(schema.relationships, start=1):
        _assert_relationship(prolog, index, rel)
    _assert_fact(
        prolog,
        "target",
        _pl_atom(schema.target.entity),
        _pl_atom(schema.target.attribute),
    )


def _prolog_json_to_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


@contextmanager
def _silence_stdout() -> Iterator[None]:
    """Silence fd 1 while Prolog writes via emit_json/0 (not Python sys.stdout)."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(1)
    try:
        os.dup2(devnull, 1)
        yield
    finally:
        os.dup2(saved, 1)
        os.close(saved)
        os.close(devnull)


def _run_feedback(prolog: Prolog) -> dict[str, Any]:
    """Call feedback_bundle/1 and emit_json/0; return parsed JSON dict."""
    try:
        json_rows = list(
            prolog.query("feedback_bundle(_Bundle), bundle_to_json(_Bundle, Json)")
        )
    except PrologError as exc:
        raise ValidationEngineError(
            f"feedback_bundle/1 or bundle_to_json/2 failed: {exc}"
        ) from exc

    if not json_rows:
        raise ValidationEngineError("feedback_bundle/1 returned no solutions")

    try:
        with _silence_stdout():
            list(prolog.query("emit_json"))
    except PrologError as exc:
        raise ValidationEngineError(f"emit_json/0 failed: {exc}") from exc

    raw = _prolog_json_to_str(json_rows[0]["Json"])
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationEngineError(f"Invalid JSON from validator: {raw!r}") from exc


def validate(schema: ProblemSchema) -> dict[str, Any]:
    """
    Validate a ProblemSchema with SWI-Prolog and return the feedback JSON dict.

    Keys: ``status`` (``pass`` | ``fail``), ``error_count``, ``errors`` (list).
    Each error has ``gate``, ``severity``, ``checks``, ``failed``.

    Safe to call repeatedly in the same process: every call clears the
    previous schema's facts from the Prolog database before asserting the
    new schema's facts.
    """
    prolog = Prolog()
    _load_validator(prolog)
    _retract_state(prolog)   # ← clear stale facts from any prior call
    _assert_schema(prolog, schema)
    return _run_feedback(prolog)



# ---------------------------------------------------------------------
# DIFFICULTY LAYER
#
# The validator (Layer 4) can now report *how* a target is derived, not just
# *that* it is: `target_derivable/3` returns a Trace — a list of theorem atoms.
# Two files turn that into a difficulty judgment:
#   lesson_data.pl  — per-lesson allow-lists (which theorems are taught) and
#                     step bands (min/max acceptable solution length).
#   calibration.pl  — `shortest_in_scope/4`, which filters a target's derivations
#                     to only lesson-allowed theorems and returns the shortest.
# We compare that shortest in-scope length to the lesson's band to get a verdict.
#
# IMPORTANT: difficulty is only meaningful for VALID problems. A schema with
# broken math has no trustworthy solve path, so always gate difficulty scoring
# behind a passing `validate()` (see `validate_and_score`).
# ---------------------------------------------------------------------

def _safe_lesson_atom(lesson: str) -> str:
    """Render a lesson id as a Prolog atom (bare if it already is a valid atom)."""
    if re.match(r"^[a-z][a-zA-Z0-9_]*$", lesson):
        return lesson
    return _pl_atom(lesson)


def _atoms_to_list(value: Any) -> list[str]:
    """Convert a pyswip-returned Prolog list of atoms into a list of strings."""
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    out = []
    for item in value:
        s = item.decode() if isinstance(item, bytes) else str(item)
        out.append(s)
    return out


def _coerce_min(value: Any) -> int | None:
    """shortest_in_scope returns an int step count, or the atom `none`."""
    if isinstance(value, int):
        return value
    s = value.decode() if isinstance(value, bytes) else str(value)
    return None if s == "none" else int(s)


def _run_difficulty(prolog: Prolog, lesson: str) -> dict[str, Any]:
    """
    Query the calibration layer for the asserted schema and return a verdict.

    Returns a dict with:
      ``verdict``     one of in_band | too_easy | too_hard | out_of_scope |
                      unknown_lesson
      ``min_steps``   shortest in-scope solution length (None if out_of_scope)
      ``trace``       the theorem atoms of that shortest solution
      ``band``        [floor, ceil] for the lesson (None if unknown_lesson)
      ``out_of_scope_paths``  count of derivations that exist but use
                      forbidden theorems (diagnostic)
    """
    lesson_atom = _safe_lesson_atom(lesson)

    try:
        rows = list(
            prolog.query(
                f"shortest_in_scope({lesson_atom}, Min, Trace, OOS), "
                f"length(OOS, NOos)"
            )
        )
    except PrologError as exc:
        raise ValidationEngineError(f"shortest_in_scope/4 failed: {exc}") from exc

    if not rows:
        # No solutions at all (target not derivable even out of scope).
        return {
            "verdict": "out_of_scope",
            "min_steps": None,
            "trace": [],
            "band": None,
            "out_of_scope_paths": 0,
        }

    row = rows[0]
    min_steps = _coerce_min(row["Min"])
    trace = _atoms_to_list(row["Trace"])
    n_oos = int(row["NOos"])

    band_rows = list(
        prolog.query(
            f"lesson_min_steps({lesson_atom}, F), lesson_max_steps({lesson_atom}, C)"
        )
    )
    if not band_rows:
        return {
            "verdict": "unknown_lesson",
            "min_steps": min_steps,
            "trace": trace,
            "band": None,
            "out_of_scope_paths": n_oos,
        }

    floor = int(band_rows[0]["F"])
    ceil = int(band_rows[0]["C"])

    if min_steps is None:
        verdict = "out_of_scope"
    elif min_steps < floor:
        verdict = "too_easy"
    elif min_steps > ceil:
        verdict = "too_hard"
    else:
        verdict = "in_band"

    return {
        "verdict": verdict,
        "min_steps": min_steps,
        "trace": trace,
        "band": [floor, ceil],
        "out_of_scope_paths": n_oos,
    }


def difficulty(schema: ProblemSchema) -> dict[str, Any]:
    """
    Score a schema's difficulty against its own lesson (schema.lesson).

    NOTE: does not check validity. Prefer `validate_and_score`, which only
    scores difficulty when the schema passes validation.
    """
    prolog = Prolog()
    _load_validator(prolog)
    _retract_state(prolog)
    _assert_schema(prolog, schema)
    return _run_difficulty(prolog, schema.lesson)


def validate_and_score(schema: ProblemSchema) -> dict[str, Any]:
    """
    Validate a schema and, only if it passes, also score its difficulty.

    Asserts the schema once, runs the validity pipeline, and — when
    ``status == "pass"`` — attaches a ``difficulty`` key with the verdict.
    This is the function the repair loop should call: an invalid problem
    has no trustworthy solve path, so difficulty is withheld until it passes.
    """
    prolog = Prolog()
    _load_validator(prolog)
    _retract_state(prolog)
    _assert_schema(prolog, schema)
    feedback = _run_feedback(prolog)
    if feedback.get("status") == "pass":
        feedback["difficulty"] = _run_difficulty(prolog, schema.lesson)
    return feedback


def validate_file(path: str | Path) -> dict[str, Any]:
    """Load a JSON schema file and validate it."""
    data = json.loads(Path(path).read_text())
    schema = ProblemSchema.model_validate(data)
    return validate(schema)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a ProblemSchema JSON file.")
    parser.add_argument("schema", type=Path, help="Path to schema JSON")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print feedback JSON to stdout",
    )
    args = parser.parse_args(argv)

    result = validate_file(args.schema)
    if args.pretty:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result))
    return 0 if result.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())