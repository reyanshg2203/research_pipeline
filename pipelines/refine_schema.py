"""
Pipeline 3: Prolog validation ↔ Haiku schema repair loop

1. Run SWI-Prolog validation (validate.validate) on the input ProblemSchema.
2. If status is pass and error_count is 0, stop — no repair needed.
3. Otherwise, Haiku revises the schema using validator gate feedback only.
4. Re-validate; repeat for up to max_iterations (default 3).

Writes under validated/:
  - schema_<problem_id>_refined.json
  - schema_<problem_id>_refined.txt   (student-facing prose via Haiku prose layer)
  - schema_<problem_id>_refined_trace.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PIPELINES = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PIPELINES))

from prose_nl import normalize_lesson_id, prose_from_schema  # noqa: E402
from schema import ProblemSchema  # noqa: E402
from validate import ValidationEngineError, validate  # noqa: E402

# Scope/difficulty gate, run AFTER validation passes but BEFORE the prose layer.
# Validation says "solvable by SOME path"; calibration says "solvable IN SCOPE."
# A problem solvable only via a method the lesson does not teach passes
# validation but must NOT reach prose, or the prose will faithfully narrate an
# intended method that doesn't actually work.
try:
    from calibrate import calibrate  # noqa: E402

    _CALIBRATION_AVAILABLE = True
except Exception:  # calibration.pl / lesson_data.pl absent, or import failure
    _CALIBRATION_AVAILABLE = False

# Pipeline-3-only few-shot: the lesson's own at-level problems, surfaced to Haiku
# during repair. This is the ONLY place lesson-specific guidance now enters the
# repair loop — it replaces the hand-authored per-lesson/per-unit prompt rules,
# which were researcher bias. Degrades to a no-op if the helper/corpus is absent.
try:
    from exemplars import format_exemplar_block  # noqa: E402
except Exception:
    def format_exemplar_block(_lesson_id: str, **_kwargs: Any) -> str:  # type: ignore
        return ""

load_dotenv(ROOT / ".env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

DEFAULT_HAIKU = "claude-haiku-4-5-20251001"
DEFAULT_MAX_ITERATIONS = 3

VALIDATED_DIR = ROOT / "validated"
OUTPUTS_DIR = ROOT / "outputs"
LESSONS_DIR = ROOT / "lessons"

SYSTEM_PROMPT = """You are repairing a structured 10th-grade geometry problem schema (JSON).

You receive:
1. The current schema (facts, relationships, target).
2. Output from a deterministic Prolog validator listing every failing gate.
3. Optionally, an at-level example problem from this lesson, as a guide to what an in-scope, on-topic problem looks like.

Your job is to produce a corrected schema that resolves EVERY validator error while preserving the problem's pedagogical intent (same lesson topic, same kind of question, same target quantity).

Rules:
- Make the SMALLEST change that fixes a Prolog gate error — but when the feedback includes a LESSON-SCOPE / DIFFICULTY / ALIGNMENT FAILURE, a larger structural restructure is required and expected. Do not add rubric commentary or NL prose.
- All declared numeric values must remain internally consistent.
- Use null for unknown values (not omitted keys where the schema expects them).
- Relationship types must be valid enum values.
- The target must be uniquely derivable from declared facts after your edits.
- Do not invoke two relationships redundantly on the same entity pair unless the validator allows it.
- Remove vacuous relationships (e.g. angle_sum_triangle with no declared angles) or add the angles needed to make them meaningful.
- Follow naming conventions: triangle ids ABC (3 caps), segment AB, point A, line m, circle c; target uses dot notation (e.g. sides.AB).
- Only declare entities that have an independent role; do not declare vertices as separate Point entities.
- Use only allowed attribute keys per relationship type.
- Angle correspondences use the key `congruent_angle_pairs` with a list of two-element lists, e.g. [["B","Y"]]. NEVER use a key like `corresponding_angles` and NEVER use a dict like {"B":"Y"}.
- NEVER fill in the target attribute's value; the target must stay null so there is something to solve.

CRITICAL - DETERMINACY PRINCIPLE (a green Prolog validation is necessary but NOT sufficient):
A correct repair must leave the target reachable from the GIVEN (non-null) values through a method that is in scope for this lesson. If the only way to reach the target is a method the lesson does not teach, the repair is WRONG even though Prolog passes. When the feedback below includes a LESSON-SCOPE / DIFFICULTY / ALIGNMENT FAILURE, you must RESTRUCTURE the problem so an in-scope method reaches the target — changing which quantity is given, changing the target, or changing the declared relationship as needed. Do not merely tweak attributes to silence Prolog.

CRITICAL - Restructuring uses ONLY existing schema keys. NEVER invent a new attribute key to express a restructure:
A restructure changes VALUES (which sides/angles are null vs. given), the TARGET, the relationship TYPE, or the congruent_angle_pairs — it NEVER adds new attribute keys. The allowed keys per relationship type are fixed; if you think you need a key that is not in the allowed list, the information is already expressed another way.

CRITICAL - Do not introduce NEW errors while repairing:
- Do NOT invent a relationship the target does not need, and do NOT add one to satisfy a connection gate if the figures are already tied by a shared side, segment, or existing relationship.
- NEVER strip the attributes off a relationship that already had them and was not the source of the error. Repairs are additive/corrective, never destructive to already-valid relationships.
- NEVER introduce a geometrically impossible figure: keep the triangle inequality (each known side < sum of the other two) and right-triangle consistency (the side opposite a 90-degree vertex is the longest; leg^2 + leg^2 = hypotenuse^2). If a value is unknown, leave it null rather than inventing a number that breaks these.

Return the full corrected schema via the tool."""


def _validation_passed(validation: dict[str, Any]) -> bool:
    return validation.get("status") == "pass" and validation.get("error_count", 0) == 0


def _format_validation_errors(validation: dict[str, Any]) -> str:
    errors = validation.get("errors") or []
    if not errors:
        return "(no error details)"
    lines: list[str] = []
    for i, err in enumerate(errors, start=1):
        lines.append(
            f"{i}. gate: {err.get('gate', '?')}\n"
            f"   severity: {err.get('severity', '?')}\n"
            f"   checks: {err.get('checks', '')}\n"
            f"   failed: {err.get('failed', '')}"
        )
    return "\n\n".join(lines)


def _format_calibration_feedback(calibration: dict[str, Any] | None) -> str:
    """Render the calibration verdict as an actionable repair instruction.
    Only emitted when calibration is present and NOT accepted (out_of_scope,
    alignment_fail, or off-band under a strict policy).

    Guidance here is UNIT-AGNOSTIC: it names the failure and the general
    restructuring lever, but never hard-codes per-lesson or per-theorem hints.
    The lesson-specific signal comes from the at-level exemplar surfaced in the
    repair prompt, not from prose written here."""
    if not calibration or calibration.get("accepted", True):
        return ""
    verdict = calibration.get("verdict", "?")
    reason = calibration.get("reason", "")
    concepts = calibration.get("out_of_scope_concepts") or []
    lines = [
        "=== LESSON-SCOPE / DIFFICULTY FAILURE (counts as an error; must be fixed) ===",
        "",
        f"verdict: {verdict}",
        f"reason: {reason}",
    ]
    if verdict == "out_of_scope":
        if concepts:
            lines.append(
                f"the target depends on concept(s) this lesson does not teach: {', '.join(concepts)}"
            )
        lines.append(
            "This problem is solvable ONLY by a method this lesson does not teach. "
            "A green Prolog validation is NOT enough. RESTRUCTURE the problem so the "
            "target is reachable by an in-scope method — change which quantity is given, "
            "change the target, or change the declared relationship. Do not merely tweak "
            "attributes to silence Prolog."
        )
    elif verdict == "too_easy":
        lines.append(
            "The problem is solvable in fewer steps than this lesson intends. Make the "
            "intended method necessary (e.g. give fewer/less-direct quantities) without "
            "introducing an out-of-scope method."
        )
    elif verdict == "too_hard":
        lines.append(
            "The problem requires more steps than this lesson intends. Simplify the "
            "structure so the target is reached within the lesson's step range."
        )
    elif verdict == "alignment_fail":
        lines.append(
            "This problem is well-posed and in scope, but it does NOT exercise this "
            "lesson's own skill — it is solvable by a prior-lesson method, or a cheaper "
            "prior-lesson shortcut exists. A green Prolog validation is NOT enough. "
            "REBUILD so the lesson's intended method is the load-bearing step: change the "
            "TARGET, the GIVENS, or the declared RELATIONSHIP so the intended method is "
            "required to reach the target. Do not merely tweak attributes. Use the at-level "
            "example problem shown above as a guide to what this lesson's own skill looks like."
        )
    return "\n".join(lines)


def _build_repair_user_prompt(
    schema: ProblemSchema,
    validation: dict[str, Any],
    iteration: int,
    calibration: dict[str, Any] | None = None,
) -> str:
    schema_json = json.dumps(schema.model_dump(), indent=2)

    # Pipeline-3-only few-shot: the lesson's own at-level problems. Empty string
    # when the corpus is absent/unfilled, so this is a no-op in that case.
    exemplar_block = format_exemplar_block(schema.lesson)
    exemplar_section = f"\n{exemplar_block}\n" if exemplar_block else ""

    prolog_section = f"""=== PROLOG VALIDATOR OUTPUT ===

status: {validation.get("status")}
error_count: {validation.get("error_count", 0)}

=== FAILING GATES (fix every one) ===

{_format_validation_errors(validation)}"""

    calibration_section = _format_calibration_feedback(calibration)
    if calibration_section:
        calibration_section = "\n\n" + calibration_section

    return f"""=== ITERATION {iteration} — SCHEMA TO REPAIR ===

{schema_json}
{exemplar_section}
{prolog_section}{calibration_section}

Submit the corrected schema using the tool."""


def refine_schema_with_haiku(
    schema: ProblemSchema,
    validation: dict[str, Any],
    iteration: int,
    model: str = DEFAULT_HAIKU,
    calibration: dict[str, Any] | None = None,
) -> ProblemSchema:
    """Ask Haiku for a corrected ProblemSchema from validator + calibration feedback."""
    user_prompt = _build_repair_user_prompt(schema, validation, iteration, calibration)

    message = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[
            {
                "name": "submit_corrected_schema",
                "description": "Submit the repaired geometry problem schema.",
                "input_schema": ProblemSchema.model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": "submit_corrected_schema"},
    )

    tool_use = None
    for block in message.content:
        if block.type == "tool_use":
            tool_use = block
            break
    if tool_use is None:
        raise RuntimeError("Haiku did not return a tool_use block.")

    raw = tool_use.input
    try:
        return ProblemSchema(**raw)
    except Exception as exc:
        raise RuntimeError(f"Haiku returned an invalid ProblemSchema: {exc}") from exc


def refinement_loop(
    schema: ProblemSchema,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    haiku_model: str = DEFAULT_HAIKU,
    enable_calibration: bool = True,
    accept_off_band: bool = True,
) -> dict[str, Any]:
    """
    Validate (Prolog) + calibrate (lesson scope/difficulty) -> Haiku repair, up
    to max_iterations. The per-iteration error count is the SUM of Prolog errors
    and calibration errors; the loop stops early only when BOTH are clean.

    Calibration runs only when Prolog validation passes for that iteration (a
    schema with structural/mathematical errors isn't meaningfully scoreable for
    scope yet — fix the math first, then scope). An out-of-scope (or, under a
    strict policy, off-band) verdict counts as one error and is fed back to Haiku
    as a restructure instruction.
    """
    current = schema
    iterations: list[dict[str, Any]] = []

    # Track the BEST (lowest COMBINED-error) schema across iterations, so a
    # repair that makes things worse never overwrites a better earlier version.
    # The combined count = Prolog errors + calibration errors, so the guard will
    # not prefer a Prolog-clean-but-out-of-scope schema over a fully in-scope one.
    best_schema = schema
    best_combined: int | None = None
    best_prolog_errs: int = 0
    best_validation: dict[str, Any] | None = None
    best_calibration: dict[str, Any] | None = None

    for i in range(1, max_iterations + 1):
        print(f"\n--- Iteration {i}/{max_iterations}: Prolog validation ---")
        try:
            validation = validate(current)
        except ValidationEngineError as exc:
            raise RuntimeError(f"Validation engine failed: {exc}") from exc

        prolog_passed = _validation_passed(validation)
        prolog_errs = validation.get("error_count", 0)
        print(
            f"  status={validation.get('status', '?')} "
            f"prolog_errors={prolog_errs} [{'PASS' if prolog_passed else 'FAIL'}]"
        )

        # Calibration runs only on a Prolog-clean schema (scope is only
        # meaningful once the figure is mathematically/structurally valid).
        calibration: dict[str, Any] | None = None
        cal_errs = 0
        if prolog_passed and enable_calibration and _CALIBRATION_AVAILABLE:
            try:
                calibration = calibrate(current, accept_off_band=accept_off_band)
                if not calibration.get("accepted", True):
                    cal_errs = 1  # out_of_scope (or off-band under strict) = 1 error
                    print(
                        f"  calibration={calibration.get('verdict', '?')} "
                        f"[SCOPE FAIL] {calibration.get('reason', '')}"
                    )
                else:
                    print(f"  calibration={calibration.get('verdict', '?')} [OK]")
            except Exception as exc:
                # Calibration must never crash the loop; treat as 0 cal errors.
                print(f"  calibration skipped (error: {exc})")
                calibration = None
                cal_errs = 0

        combined = prolog_errs + cal_errs
        passed = (combined == 0)
        print(f"  combined_error_count={combined} [{'PASS' if passed else 'FAIL'}]")

        # Best-schema guard on the COMBINED count, with a tie-break that prefers
        # FEWER PROLOG (hard) errors. A Prolog-clean-but-out-of-scope schema
        # (combined=1 from a scope failure) is strictly closer to usable than a
        # Prolog-broken schema with the same combined count (a real contradiction),
        # so on a tie we keep the one with fewer hard errors. This makes the loop
        # return its genuinely-best attempt rather than the earliest one to reach
        # the minimum combined count.
        is_better = (
            best_combined is None
            or combined < best_combined
            or (combined == best_combined and prolog_errs < best_prolog_errs)
        )
        if is_better:
            best_combined = combined
            best_prolog_errs = prolog_errs
            best_schema = current
            best_validation = validation
            best_calibration = calibration

        entry: dict[str, Any] = {
            "iteration": i,
            "input_schema": current.model_dump(),
            "validation": validation,
            "calibration": calibration,
            "combined_error_count": combined,
            "haiku_correction": None,
        }
        iterations.append(entry)

        if passed:
            print("  Prolog + calibration both clean — stopping early.")
            break

        if i == max_iterations:
            print("  Max iterations reached — keeping best schema.")
            break

        print(f"--- Iteration {i}: Haiku repairing schema ---")
        try:
            corrected = refine_schema_with_haiku(
                current, validation, i, model=haiku_model, calibration=calibration
            )
        except RuntimeError as exc:
            # Haiku produced an unparseable/invalid schema. Don't crash the
            # file — stop and keep the best valid schema seen so far.
            print(f"  Haiku repair produced an invalid schema; keeping best schema. ({exc})")
            break
        entry["haiku_correction"] = corrected.model_dump()
        current = corrected
        print(f"  Corrected problem_id={corrected.problem_id}")

    # Prefer the best (lowest combined-error) schema over the last iteration's.
    final_schema_obj = best_schema
    final_validation = best_validation if best_validation is not None else iterations[-1]["validation"]
    final_calibration = best_calibration
    final_combined = best_combined if best_combined is not None else final_validation.get("error_count", 0)
    final_passed = (final_combined == 0)
    return {
        "problem_id": final_schema_obj.problem_id,
        "lesson_id": final_schema_obj.lesson,
        "max_iterations": max_iterations,
        "iterations_used": len(iterations),
        "stopped_early": final_passed and len(iterations) < max_iterations,
        "final_passed": final_passed,
        "final_error_count": final_combined,
        "final_prolog_error_count": final_validation.get("error_count", 0),
        "calibration": final_calibration,
        "final_schema": final_schema_obj.model_dump(),
        "iterations": iterations,
    }


def _output_stem(problem_id: str) -> str:
    return f"schema_{problem_id}_refined"


def _save_results(
    trace: dict[str, Any],
    output_dir: Path,
    *,
    lessons_dir: Path = LESSONS_DIR,
    haiku_model: str = DEFAULT_HAIKU,
    skip_prose: bool = False,
    enable_calibration: bool = True,
    accept_off_band: bool = True,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _output_stem(trace["problem_id"])

    json_path = output_dir / f"{stem}.json"
    txt_path = output_dir / f"{stem}.txt"
    trace_path = output_dir / f"{stem}_trace.json"

    final_schema = trace["final_schema"]
    json_path.write_text(json.dumps(final_schema, indent=2), encoding="utf-8")

    raw_lesson = trace.get("lesson_id") or final_schema.get("lesson", "")
    lesson_id = normalize_lesson_id(raw_lesson) if raw_lesson else ""
    functional_path = output_dir / f"schema_{trace['problem_id']}_functional.txt"

    # --- Scope/difficulty calibration gate (between validation and prose) ---
    # Only meaningful when the schema actually PASSED validation; a still-failing
    # schema is already a known reject. When calibration reports out_of_scope
    # (target solvable ONLY via forbidden theorems) — or off-band under a strict
    # policy — we do NOT run the prose layer, because prose would faithfully
    # narrate an intended method that does not actually work. We emit the
    # function-translated NL as a placeholder and flag the trace so the host can
    # send the problem back for regeneration.
    #
    # The refinement loop already ran calibration on the best schema and stored
    # the verdict in trace["calibration"]; we read it here rather than re-running
    # (avoids a redundant Prolog/calibration call). Prose is blocked when a
    # calibration verdict exists and was NOT accepted.
    calibration_result = trace.get("calibration")
    calibration_blocks_prose = bool(
        calibration_result is not None
        and not calibration_result.get("accepted", True)
        and not force_prose          # <-- force_prose overrides the gate
    )
    )
    if calibration_blocks_prose:
        print(
            f"--- Calibration gate: "
            f"{calibration_result.get('verdict', '?').upper()} — skipping prose."
        )
        print(f"    {calibration_result.get('reason', '')}")

    if skip_prose or calibration_blocks_prose:
        from schema_to_text import schema_to_problem_text  # noqa: E402

        function_translated = schema_to_problem_text(final_schema)
        functional_path.write_text(function_translated, encoding="utf-8")
        txt_path.write_text(function_translated, encoding="utf-8")
        trace["function_translated_nl"] = function_translated
        trace["prose_skipped"] = True
        if calibration_blocks_prose:
            trace["calibration_rejected"] = True
    else:
        print("--- Haiku prose layer ---")
        function_translated, prose = prose_from_schema(
            final_schema,
            lesson_id,
            lessons_dir=lessons_dir,
            model=haiku_model,
        )
        functional_path.write_text(function_translated, encoding="utf-8")
        txt_path.write_text(prose, encoding="utf-8")
        trace["function_translated_nl"] = function_translated
        trace["student_facing_prose"] = prose
        print(f"  Functional NL: {functional_path.name}")
        print(f"  Prose NL:      {txt_path.name}")

    trace_out = {k: v for k, v in trace.items() if k != "final_schema"}
    trace_path.write_text(json.dumps(trace_out, indent=2), encoding="utf-8")

    return json_path, txt_path, trace_path


def refine_one_file(
    schema_path: Path,
    output_dir: Path,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    haiku_model: str = DEFAULT_HAIKU,
    lessons_dir: Path = LESSONS_DIR,
    skip_prose: bool = False,
    enable_calibration: bool = True,
    accept_off_band: bool = True,
) -> dict[str, Any] | None:
    """Run the refinement loop for one schema JSON file."""
    if not schema_path.exists():
        print(f"Skipping {schema_path.name} — file not found.")
        return None

    try:
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        schema = ProblemSchema.model_validate(data)
    except Exception as exc:
        print(f"Skipping {schema_path.name} — invalid schema: {exc}")
        return None

    print(f"\n{'=' * 60}")
    print(
        f"Refining {schema_path.name} "
        f"(problem_id={schema.problem_id}, lesson={schema.lesson}), "
        f"max {max_iterations} iteration(s)"
    )

    try:
        trace = refinement_loop(
            schema,
            max_iterations=max_iterations,
            haiku_model=haiku_model,
            enable_calibration=enable_calibration,
            accept_off_band=accept_off_band,
        )
    except Exception as exc:
        print(f"  Error: {exc}")
        return None

    json_path, txt_path, trace_path = _save_results(
        trace,
        output_dir,
        lessons_dir=lessons_dir,
        haiku_model=haiku_model,
        skip_prose=skip_prose,
    )
    status = "PASS" if trace["final_passed"] else "FAIL"
    print(
        f"\n  Done [{status}] errors={trace['final_error_count']} "
        f"iterations={trace['iterations_used']}"
    )
    print(f"  Schema: {json_path.relative_to(ROOT)}")
    print(f"  NL:     {txt_path.relative_to(ROOT)}")
    print(f"  Trace:  {trace_path.relative_to(ROOT)}")
    return trace


def refine_directory(
    schemas_dir: Path,
    output_dir: Path,
    *,
    lesson_filter: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    haiku_model: str = DEFAULT_HAIKU,
    lessons_dir: Path = LESSONS_DIR,
    skip_prose: bool = False,
    enable_calibration: bool = True,
    accept_off_band: bool = True,
) -> list[dict[str, Any]]:
    """Refine every schema_lesson_*.json under schemas_dir (optional --lesson filter)."""
    paths = sorted(schemas_dir.glob("schema_lesson_*.json"))
    if lesson_filter:
        m = re.search(r"(\d+)$", lesson_filter.replace(".txt", "").strip())
        if not m:
            raise ValueError(f"Could not parse lesson number from {lesson_filter!r}")
        suffix = f"lesson_{int(m.group(1)):02d}"
        paths = [p for p in paths if suffix in p.stem]

    if not paths:
        print(f"No matching schema JSON files under {schemas_dir}")
        return []

    print(f"Batch refine: {len(paths)} file(s) from {schemas_dir}")
    results: list[dict[str, Any]] = []

    for schema_path in paths:
        trace = refine_one_file(
            schema_path,
            output_dir,
            max_iterations=max_iterations,
            haiku_model=haiku_model,
            lessons_dir=lessons_dir,
            skip_prose=skip_prose,
            enable_calibration=enable_calibration,
            accept_off_band=accept_off_band,
        )
        if trace is not None:
            results.append({"file": schema_path.name, "trace": trace})

    passed = sum(1 for r in results if r["trace"]["final_passed"])
    print(f"\n{'=' * 60}")
    print(f"Batch complete: {len(results)}/{len(paths)} refined ({passed} passed)")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prolog validation ↔ Haiku repair loop for ProblemSchema JSON."
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Single schema JSON file. If omitted, batch mode on --schemas-dir.",
    )
    parser.add_argument(
        "--schemas-dir",
        type=Path,
        default=OUTPUTS_DIR,
        help="Directory of schema_lesson_*.json files (batch mode).",
    )
    parser.add_argument(
        "--lesson",
        type=str,
        default=None,
        metavar="N",
        help='Batch filter, e.g. "03" or "16" for only that lesson\'s schemas.',
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=VALIDATED_DIR,
        help="Where to write refined schema, NL text, and trace JSON.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help="Maximum validate/repair cycles (default 3).",
    )
    parser.add_argument(
        "--haiku-model",
        type=str,
        default=DEFAULT_HAIKU,
        help="Anthropic model for schema repair and prose layer.",
    )
    parser.add_argument(
        "--lessons-dir",
        type=Path,
        default=LESSONS_DIR,
        help="Directory containing lesson source files for the prose layer.",
    )
    parser.add_argument(
        "--skip-prose",
        action="store_true",
        help="Write function-translated NL only (skip Haiku prose layer).",
    )
    parser.add_argument(
        "--no-calibration",
        action="store_true",
        help="Disable the scope/difficulty calibration gate before the prose layer.",
    )
    parser.add_argument(
        "--strict-band",
        action="store_true",
        help="Calibration also rejects too_easy/too_hard (not just out_of_scope).",
    )
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Add it to .env in the repo root.")

    if args.schema:
        if not args.schema.exists():
            sys.exit(f"Schema file not found: {args.schema}")
        trace = refine_one_file(
            args.schema,
            args.output_dir,
            max_iterations=args.max_iterations,
            haiku_model=args.haiku_model,
            lessons_dir=args.lessons_dir,
            skip_prose=args.skip_prose,
            enable_calibration=not args.no_calibration,
            accept_off_band=not args.strict_band,
        )
        if trace is None:
            sys.exit(1)
        sys.exit(0 if trace["final_passed"] else 1)
    else:
        refine_directory(
            args.schemas_dir,
            args.output_dir,
            lesson_filter=args.lesson,
            max_iterations=args.max_iterations,
            haiku_model=args.haiku_model,
            lessons_dir=args.lessons_dir,
            skip_prose=args.skip_prose,
            enable_calibration=not args.no_calibration,
            accept_off_band=not args.strict_band,
        )


if __name__ == "__main__":
    main()