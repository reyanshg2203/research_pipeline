"""
Pipeline 3: Haiku ↔ Opus refinement loop

1. Opus judges the current NL problem (evaluate_schema.judge_problem).
2. If not passing, Haiku revises the NL using feedback_for_haiku and specific_issues.
3. Repeat for up to max_iterations (default 3); stop early only when all rubric scores are 4/4.

Writes:
  - refined/<stem>_refined.txt     — final NL problem
  - refined/<stem>_refined_trace.json — iteration history (scores, feedback, NL versions)
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
sys.path.insert(0, str(PIPELINES))

from evaluate_schema import PASS_THRESHOLD, judge_problem  # noqa: E402  # PASS_THRESHOLD used in Haiku prompt

PERFECT_SCORE = 4


def _is_perfect(judgment: dict[str, Any]) -> bool:
    """True when geometric accuracy, lesson alignment, and clarity are all 4/4."""
    s = judgment["scores"]
    return (
        s["geometric_accuracy"] == PERFECT_SCORE
        and s["lesson_alignment"] == PERFECT_SCORE
        and s["linguistic_clarity"] == PERFECT_SCORE
    )

load_dotenv(ROOT / ".env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

DEFAULT_HAIKU = "claude-haiku-4-5-20251001"
DEFAULT_OPUS = "claude-opus-4-7"
DEFAULT_MAX_ITERATIONS = 3

REFINED_PROBLEM_SCHEMA = {
    "type": "object",
    "properties": {
        "nl_problem": {
            "type": "string",
            "description": "The complete revised geometry word problem, ready for a student.",
        },
    },
    "required": ["nl_problem"],
}


def _format_issues(issues: list[dict[str, str]]) -> str:
    if not issues:
        return "(none)"
    lines = []
    for i, item in enumerate(issues, start=1):
        lines.append(
            f"{i}. [{item['severity']}] {item['category']}: {item['issue']}\n"
            f"   Fix: {item['suggested_fix']}"
        )
    return "\n".join(lines)


def _build_refine_prompt(
    nl_problem: str,
    lesson_text: str,
    lesson_id: str,
    judgment: dict[str, Any],
    iteration: int,
) -> str:
    scores = judgment["scores"]
    return f"""You are revising a 10th-grade geometry word problem based on expert reviewer feedback.

=== LESSON ({lesson_id}) ===

{lesson_text}

=== CURRENT PROBLEM (iteration {iteration}) ===

{nl_problem}

=== REVIEWER FEEDBACK ===

{judgment["feedback_for_haiku"]}

=== SPECIFIC ISSUES TO ADDRESS ===

{_format_issues(judgment["specific_issues"])}

=== SCORES FROM LAST REVIEW (for your awareness; do not mention scores in the problem) ===

- Geometric accuracy: {scores["geometric_accuracy"]}/4
- Lesson alignment: {scores["lesson_alignment"]}/4
- Linguistic clarity: {scores["linguistic_clarity"]}/4
- Overall: {judgment["overall_score"]:.2f} (pass threshold: {PASS_THRESHOLD})

=== REVISION RULES ===

1. Fix every critical and major issue; address minor issues when feasible.
2. Keep the problem aligned to concepts taught in the lesson above.
3. The problem must be solvable from words and numbers only — no diagrams.
4. It must have a single numerical or yes/no answer; do not state the answer in the prompt.
5. All given values must be internally consistent; do not introduce new contradictions.
6. Preserve what already works unless the feedback asks you to change it.
7. Return only the revised problem text — no preamble, rubric commentary, or meta-notes.

Submit the revised problem using the tool."""


def refine_nl_with_haiku(
    nl_problem: str,
    lesson_text: str,
    lesson_id: str,
    judgment: dict[str, Any],
    iteration: int,
    model: str = DEFAULT_HAIKU,
) -> str:
    """Ask Haiku to produce a revised NL problem from Opus judgment."""
    prompt = _build_refine_prompt(nl_problem, lesson_text, lesson_id, judgment, iteration)

    message = client.messages.create(
        model=model,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "name": "submit_refined_problem",
                "description": "Submit the revised natural-language geometry problem.",
                "input_schema": REFINED_PROBLEM_SCHEMA,
            }
        ],
        tool_choice={"type": "tool", "name": "submit_refined_problem"},
    )

    tool_use = None
    for block in message.content:
        if block.type == "tool_use":
            tool_use = block
            break
    if tool_use is None:
        raise RuntimeError("Haiku did not return a tool_use block.")

    refined = tool_use.input.get("nl_problem", "").strip()
    if not refined:
        raise RuntimeError("Haiku returned an empty nl_problem.")
    return refined


def refinement_loop(
    nl_problem: str,
    lesson_text: str,
    lesson_id: str,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    haiku_model: str = DEFAULT_HAIKU,
    judge_model: str = DEFAULT_OPUS,
) -> dict[str, Any]:
    """
    Run up to max_iterations of judge → (optional) Haiku refine.
    Stops early only when every rubric dimension scores 4/4.
    Returns trace dict with final_nl, pass/perfect status, and per-iteration history.
    """
    current = nl_problem.strip()
    iterations: list[dict[str, Any]] = []

    for i in range(1, max_iterations + 1):
        print(f"\n--- Iteration {i}/{max_iterations}: Opus judging ---")
        judgment = judge_problem(current, lesson_text, lesson_id, model=judge_model)

        perfect = _is_perfect(judgment)
        if perfect:
            verdict = "PERFECT"
        elif judgment["passed"]:
            verdict = "PASS"
        else:
            verdict = "FAIL"
        print(
            f"  Overall: {judgment['overall_score']:.2f} [{verdict}] "
            f"(GA={judgment['scores']['geometric_accuracy']}, "
            f"LA={judgment['scores']['lesson_alignment']}, "
            f"LC={judgment['scores']['linguistic_clarity']})"
        )

        iterations.append(
            {
                "iteration": i,
                "nl_problem": current,
                "judgment": judgment,
            }
        )

        if perfect:
            print("  Perfect 4/4 on all criteria — stopping early.")
            break

        if i == max_iterations:
            print("  Max iterations reached — keeping last revision attempt.")
            break

        print(f"--- Iteration {i}: Haiku revising ---")
        current = refine_nl_with_haiku(
            current, lesson_text, lesson_id, judgment, i, model=haiku_model
        )
        print(f"  Revised length: {len(current)} chars")

    final_judgment = iterations[-1]["judgment"]
    return {
        "lesson_id": lesson_id,
        "max_iterations": max_iterations,
        "iterations_used": len(iterations),
        "stopped_early": _is_perfect(final_judgment) and len(iterations) < max_iterations,
        "final_perfect": _is_perfect(final_judgment),
        "final_passed": final_judgment["passed"],
        "final_overall_score": final_judgment["overall_score"],
        "final_nl": iterations[-1]["nl_problem"],
        "iterations": iterations,
    }


def _lesson_id_from_problem_path(path: Path) -> str | None:
    match = re.search(r"lesson_(\d+)", path.stem)
    if not match:
        return None
    return f"lesson_{match.group(1).zfill(2)}"


def _save_results(trace: dict[str, Any], source_stem: str, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / f"{source_stem}_refined.txt"
    trace_path = output_dir / f"{source_stem}_refined_trace.json"

    txt_path.write_text(trace["final_nl"], encoding="utf-8")
    trace_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")
    return txt_path, trace_path


def _status_label(trace: dict[str, Any]) -> str:
    if trace["final_perfect"]:
        return "PERFECT"
    if trace["final_passed"]:
        return "PASS"
    return "FAIL"


def refine_one_file(
    problem_path: Path,
    lessons_dir: Path,
    output_dir: Path,
    *,
    lesson_id: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    haiku_model: str = DEFAULT_HAIKU,
    judge_model: str = DEFAULT_OPUS,
) -> dict[str, Any] | None:
    """Run the refinement loop for one .txt file. Returns trace or None on skip/error."""
    lid = lesson_id or _lesson_id_from_problem_path(problem_path)
    if not lid:
        print(f"Skipping {problem_path.name} — couldn't parse lesson id.")
        return None

    lesson_path = lessons_dir / f"{lid}.txt"
    if not lesson_path.exists():
        print(f"Skipping {problem_path.name} — lesson file {lesson_path.name} not found.")
        return None

    initial_nl = problem_path.read_text(encoding="utf-8").strip()
    if not initial_nl:
        print(f"Skipping {problem_path.name} — empty file.")
        return None

    lesson_text = lesson_path.read_text(encoding="utf-8")
    print(f"\n{'=' * 60}")
    print(f"Refining {problem_path.name} ({lid}), max {max_iterations} iteration(s)")

    try:
        trace = refinement_loop(
            initial_nl,
            lesson_text,
            lid,
            max_iterations=max_iterations,
            haiku_model=haiku_model,
            judge_model=judge_model,
        )
    except Exception as e:
        print(f"  Error: {e}")
        return None

    txt_path, trace_path = _save_results(trace, problem_path.stem, output_dir)
    status = _status_label(trace)
    print(f"\n  Done [{status}] score={trace['final_overall_score']:.2f} "
          f"iterations={trace['iterations_used']}")
    print(f"  Refined NL: {txt_path.relative_to(ROOT)}")
    print(f"  Trace: {trace_path.relative_to(ROOT)}")
    return trace


def refine_directory(
    problems_dir: Path,
    lessons_dir: Path,
    output_dir: Path,
    *,
    lesson_filter: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    haiku_model: str = DEFAULT_HAIKU,
    judge_model: str = DEFAULT_OPUS,
) -> list[dict[str, Any]]:
    """Refine every schema_lesson_*.txt under problems_dir (optional --lesson filter)."""
    paths = sorted(problems_dir.glob("schema_lesson_*.txt"))
    if lesson_filter:
        m = re.search(r"(\d+)$", lesson_filter.replace(".txt", "").strip())
        if not m:
            raise ValueError(f"Could not parse lesson number from {lesson_filter!r}")
        suffix = f"lesson_{int(m.group(1)):02d}"
        paths = [p for p in paths if suffix in p.stem]

    if not paths:
        print(f"No matching .txt files under {problems_dir}")
        return []

    print(f"Batch refine: {len(paths)} file(s) from {problems_dir}")
    results: list[dict[str, Any]] = []

    for problem_path in paths:
        trace = refine_one_file(
            problem_path,
            lessons_dir,
            output_dir,
            max_iterations=max_iterations,
            haiku_model=haiku_model,
            judge_model=judge_model,
        )
        if trace is not None:
            results.append({"file": problem_path.name, "trace": trace})

    perfect = sum(1 for r in results if r["trace"]["final_perfect"])
    passed = sum(1 for r in results if r["trace"]["final_passed"])
    print(f"\n{'=' * 60}")
    print(f"Batch complete: {len(results)}/{len(paths)} refined "
          f"({perfect} perfect, {passed} passed)")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Haiku ↔ Opus refinement loop for NL geometry problems."
    )
    parser.add_argument(
        "--problem",
        type=Path,
        default=None,
        help="Single NL problem .txt. If omitted, refines all schema_lesson_*.txt in --problems-dir.",
    )
    parser.add_argument(
        "--problems-dir",
        type=Path,
        default=ROOT / "outputs",
        help="Directory of NL problem .txt files (batch mode).",
    )
    parser.add_argument(
        "--lesson",
        type=str,
        default=None,
        metavar="N",
        help='Batch filter, e.g. "03" or "16" for only that lesson\'s outputs.',
    )
    parser.add_argument(
        "--lesson-id",
        type=str,
        default=None,
        help="Lesson id (e.g. lesson_16). Inferred from filename if omitted.",
    )
    parser.add_argument(
        "--lessons-dir",
        type=Path,
        default=ROOT / "lessons",
        help="Directory containing lesson source files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "refined",
        help="Where to write refined NL and trace JSON.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help="Maximum judge/refine cycles (default 3).",
    )
    parser.add_argument(
        "--haiku-model",
        type=str,
        default=DEFAULT_HAIKU,
        help="Anthropic model for NL revision.",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=DEFAULT_OPUS,
        help="Anthropic model for rubric judging.",
    )
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Add it to .env in the repo root.")

    if args.problem:
        if not args.problem.exists():
            sys.exit(f"Problem file not found: {args.problem}")
        trace = refine_one_file(
            args.problem,
            args.lessons_dir,
            args.output_dir,
            lesson_id=args.lesson_id,
            max_iterations=args.max_iterations,
            haiku_model=args.haiku_model,
            judge_model=args.judge_model,
        )
        if trace is None:
            sys.exit(1)
    else:
        refine_directory(
            args.problems_dir,
            args.lessons_dir,
            args.output_dir,
            lesson_filter=args.lesson,
            max_iterations=args.max_iterations,
            haiku_model=args.haiku_model,
            judge_model=args.judge_model,
        )


if __name__ == "__main__":
    main()
