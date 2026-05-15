import argparse
import json
import os
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# Repo root (parent of pipelines/)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schema import ProblemSchema  # noqa: E402

load_dotenv(ROOT / ".env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

LESSONS_DIR = ROOT / "lessons"
OUTPUTS_DIR = ROOT / "outputs"


def _lesson_paths(single: str | None) -> list[Path]:
    """Sorted list of lesson_*.txt paths; optional filter --lesson 03 -> lesson_03.txt."""
    pattern = re.compile(r"^lesson_\d+\.txt$", re.IGNORECASE)
    all_files = sorted(
        p for p in LESSONS_DIR.iterdir() if p.is_file() and pattern.match(p.name)
    )
    if not all_files:
        raise FileNotFoundError(f"No lesson_*.txt files under {LESSONS_DIR}")

    if single is None:
        return all_files

    # Accept "3", "03", "lesson_03", "lesson_03.txt"
    m = re.search(r"(\d+)$", single.replace(".txt", "").strip())
    if not m:
        raise FileNotFoundError(f"Could not parse lesson number from --lesson {single!r}")
    suffix = m.group(1)
    wanted = f"lesson_{int(suffix):02d}.txt"
    for p in all_files:
        if p.name.lower() == wanted.lower():
            return [p]
    raise FileNotFoundError(f"No file matching --lesson {single!r} (expected {wanted} in {LESSONS_DIR})")


def _build_prompt(lesson_path: Path, lesson_content: str) -> str:
    label = lesson_path.stem.replace("_", " ")
    return f"""You are a math problem designer for a 10th grade geometry class.

Below is the source material from {lesson_path.name} ({label}):

<lesson>
{lesson_content}
</lesson>

Your job is to invent ONE original math problem based on this lesson and represent it as a structured JSON object. Do not copy problems from the lesson. The problem must have a single numerical or yes/no answer.

Rules:
1. Only use mathematical concepts explicitly taught in this lesson
2. The problem must be solvable using only words and numbers — no diagrams
3. All declared values must be internally consistent
4. The target must be uniquely determinable from the declared facts
5. Use null for any unknown values
6. The relationship type must be one of the allowed enum values

CRITICAL — Naming conventions (these must be followed exactly):
- Triangle ids: use bare letters ONLY. Write "ABC" — NOT "triangle_ABC", NOT "triangleABC", NOT "Triangle ABC"
- Polygon ids: use bare letters ONLY. Write "ABCD" — NOT "polygon_ABCD"
- Segment ids: use bare letters ONLY. Write "AB" — NOT "segment_AB"
- Point ids: use single capital letters or letters with primes. Write "A" or "A'" — NOT "point_A"
- Line ids: use lowercase single letters. Write "m" or "n" — NOT "line_m"
- Circle ids: use single lowercase letters. Write "c" — NOT "circle_c"
- Target attribute uses dot notation: "sides.AB", "angles.A", "length", "radius"

CRITICAL — Entity declaration rules:
- Only declare an entity if it has a role INDEPENDENT of being part of another entity
- DO NOT declare points A, B, C as separate Point entities just because they are vertices of triangle ABC. Vertices are implicit in the triangle.
- DO NOT declare side AB as a separate Segment entity just because it is a side of triangle ABC. Sides are implicit in the triangle.
- DO declare a point as a separate Point entity if it serves a special role like a dilation center, intersection point, or center of a circle
- DO declare a segment as a separate Segment entity if it has properties that don't belong to any single polygon — like a midsegment, an altitude, or a transversal

CRITICAL — Attribute keys (DO NOT invent new keys):
Only use the keys listed below for each relationship type. Do not add extra keys for explanations, descriptions, or context. If a relationship has no required attributes, use an empty dictionary.

similar_AA, similar_SAS, similar_SSS, similar_unspecified:
  scale_factor (float or null), pre_image (str), image (str), congruent_angle_pairs (list of [str, str])

dilation:
  scale_factor (float), center (str or null), pre_image (str), image (str)

scaled_copy, scaled_copy_unspecified:
  scale_factor (float or null), pre_image (str), image (str)

proportional_segments:
  ratio (float)

midsegment_ratio:
  ratio (always 0.5)

triangle_proportionality:
  parallel_side (str), segment1 (str), segment2 (str)

altitude_to_hypotenuse:
  altitude_id (str), hypotenuse (str), segment1 (str), segment2 (str)

geometric_mean_altitude:
  altitude_id (str), segment1 (str), segment2 (str)

geometric_mean_leg:
  leg_id (str), hypotenuse (str), adjacent_segment (str)

transversal_cut:
  transversal (str), line1 (str), line2 (str)

congruent_angles, congruent_segments:
  ids (list of str)

congruent_triangles:
  pre_image (str), image (str), criterion (str)

collinear_dilation:
  center (str), pre_image_point (str), image_point (str)

All other relationship types use an empty attributes dictionary."""


def generate_for_lesson(lesson_path: Path) -> Path | None:
    lesson_content = lesson_path.read_text(encoding="utf-8")
    if not lesson_content.strip():
        print(f"Skipping empty file: {lesson_path.name}")
        return None

    prompt = _build_prompt(lesson_path, lesson_content)
    print(f"\n--- Calling API for {lesson_path.name} ---")

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "name": "generate_problem",
                "description": "Generate a geometry problem in structured schema format",
                "input_schema": ProblemSchema.model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": "generate_problem"},
    )

    tool_use = None
    for block in message.content:
        if block.type == "tool_use":
            tool_use = block
            break
    if tool_use is None:
        print("No tool_use block in response; skipping save.")
        return None

    raw = tool_use.input
    print("Raw output from Haiku:")
    print(json.dumps(raw, indent=2))

    try:
        ProblemSchema(**raw)
        print("Pydantic validation passed")
    except Exception as e:
        print(f"Pydantic validation failed: {e}")
        return None

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_name = f"schema_{lesson_path.stem}.json"
    out_path = OUTPUTS_DIR / out_name
    out_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    print(f"Saved to {out_path.relative_to(ROOT)}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate problem JSON schemas from lesson text files (Anthropic tool call)."
    )
    parser.add_argument(
        "--lesson",
        type=str,
        default=None,
        metavar="N",
        help='Only run one file, e.g. "03" or "3" for lessons/lesson_03.txt',
    )
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Add it to .env in the repo root.")

    paths = _lesson_paths(args.lesson)
    for lesson_path in paths:
        try:
            generate_for_lesson(lesson_path)
        except Exception as e:
            print(f"Error on {lesson_path.name}: {e}")
            continue


if __name__ == "__main__":
    main()
