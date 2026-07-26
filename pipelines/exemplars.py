"""
Few-shot exemplar access for Pipeline 3's repair loop ONLY.

The exemplars are each lesson's own at-level practice problems (IM, CC BY 4.0),
stored in lessons/exemplars.json. They are surfaced exclusively inside Pipeline
3's Haiku repair step (refine_schema.py) so the shared schema generation in
generate_schema.py stays identical across all three pipelines -- keeping the QC
mechanism the sole independent variable. Pipelines 1 and 2 never import this.

Public API:
    exemplars_for(lesson_id)            -> list[str]
    format_exemplar_block(lesson_id)    -> str   (empty string if none/unfilled)
    exemplar_feedback_for_schema(schema)-> str   (convenience: reads schema['lesson'])
    max_exemplar_overlap(text, lesson)  -> float (novelty guard, 0..1)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# pipelines/exemplars.py -> repo root is two levels up
ROOT = Path(__file__).resolve().parent.parent
EXEMPLARS_PATH = ROOT / "lessons" / "exemplars.json"

CONTAM_NGRAM = 4

_CACHE: dict | None = None


def load_exemplars() -> dict:
    """Load lessons/exemplars.json once. {lesson_id: [problem_str, ...]}.

    Missing file -> {}. Placeholder entries (empty, or starting with '<') are
    dropped, so an unfilled template behaves as 'no exemplars for that lesson'.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not EXEMPLARS_PATH.exists():
        _CACHE = {}
        return _CACHE
    raw = json.loads(EXEMPLARS_PATH.read_text(encoding="utf-8"))
    cleaned: dict[str, list[str]] = {}
    for key, val in raw.items():
        if key.startswith("_") or not isinstance(val, list):
            continue
        kept = [
            s.strip()
            for s in val
            if isinstance(s, str) and s.strip() and not s.strip().startswith("<")
        ]
        if kept:
            cleaned[key] = kept
    _CACHE = cleaned
    return _CACHE


def exemplars_for(lesson_id: str) -> list[str]:
    return load_exemplars().get(lesson_id, [])


def format_exemplar_block(lesson_id: str, *, max_examples: int = 3) -> str:
    """Few-shot block for the repair prompt. Empty string when no exemplars."""
    ex = exemplars_for(lesson_id)[:max_examples]
    if not ex:
        return ""
    lines = [
        "",
        "Here are representative AT-LEVEL problems from this exact lesson. They show "
        "the kind of task, the core skill, and the intended difficulty this lesson is "
        "meant to exercise. Use them only as a guide to what a well-aligned problem "
        "looks like -- rebuild the problem so it exercises that same skill. Do NOT "
        "copy, translate, or lightly paraphrase them; the repaired problem must stay a "
        "distinct problem with its own figures and numbers.",
        "<lesson_exemplars>",
    ]
    for i, e in enumerate(ex, start=1):
        lines.append(f"Example {i}: {e}")
    lines.append("</lesson_exemplars>")
    return "\n".join(lines)


def exemplar_feedback_for_schema(schema: dict, *, max_examples: int = 3) -> str:
    """Convenience: derive the lesson id from a schema dict and format the block.

    Works with either schema['lesson'] (e.g. 'lesson_14') or a problem_id like
    'lesson_14_001'. Returns '' if neither is present or no exemplars exist.
    """
    lesson_id = (schema or {}).get("lesson")
    if not lesson_id:
        pid = (schema or {}).get("problem_id", "")
        m = re.match(r"(lesson_\d+)", str(pid))
        lesson_id = m.group(1) if m else None
    if not lesson_id:
        return ""
    return format_exemplar_block(lesson_id, max_examples=max_examples)


# --- novelty guard (deterministic, MathCAMPS-style) ------------------
def _token_ngrams(text: str, n: int = CONTAM_NGRAM) -> set:
    toks = re.findall(r"[a-z0-9]+", text.lower())
    if len(toks) < n:
        return set()
    return {tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def max_exemplar_overlap(text: str, lesson_id: str, n: int = CONTAM_NGRAM) -> float:
    """Max fraction of `text`'s n-grams that also appear in any exemplar for the
    lesson. Use on the final repaired prose to flag copying. 0.0 if nothing to
    compare."""
    g = _token_ngrams(text, n)
    if not g:
        return 0.0
    best = 0.0
    for e in exemplars_for(lesson_id):
        eg = _token_ngrams(e, n)
        if eg:
            best = max(best, len(g & eg) / len(g))
    return best