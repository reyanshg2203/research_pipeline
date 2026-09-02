"""Exact answer grading for the zero-shot calibration stage.

Rules (spec S.17):
  * a FINAL_ANSWER marker is requested in the prompt and parsed first;
  * \\boxed{...} is a fallback;
  * comparison is exact: integers, reduced fractions, NONE, YES/NO;
  * SymPy is used only for safe rational equivalence (e.g. 6/4 == 3/2);
  * NO LLM is ever used to judge correctness;
  * parse failures are reported separately, never silently scored as wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

FINAL_ANSWER_MARKER = "FINAL_ANSWER:"

_BOXED_RE = re.compile(r"\\boxed\s*\{")
_FRAC_CMD_RE = re.compile(r"\\[dt]?frac\s*\{\s*([+-]?\d+)\s*\}\s*\{\s*([+-]?\d+)\s*\}")
_RATIONAL_RE = re.compile(r"([+-]?)\(?([+-]?\d+)\)?(?:/\(?([+-]?\d+)\)?)?")


@dataclass
class GradeResult:
    correct: bool
    parsed: Optional[str]
    parse_failed: bool
    raw_span: str = ""

    def to_json(self) -> dict:
        return {
            "correct": self.correct,
            "parsed": self.parsed,
            "parse_failed": self.parse_failed,
            "raw_span": self.raw_span,
        }


def _extract_braced(text: str, open_index: int) -> Optional[str]:
    """Return the balanced-brace content starting at ``open_index`` ('{')."""
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : i]
    return None


def extract_answer_span(response: str) -> Optional[str]:
    """Pull the answer span out of a raw model response, or None."""
    idx = response.rfind(FINAL_ANSWER_MARKER)
    if idx != -1:
        tail = response[idx + len(FINAL_ANSWER_MARKER) :]
        line = tail.split("\n", 1)[0].strip()
        if line:
            return line
    # \boxed{...} fallback
    last = None
    for m in _BOXED_RE.finditer(response):
        brace = response.find("{", m.start())
        if brace != -1:
            content = _extract_braced(response, brace)
            if content is not None:
                last = content
    if last is not None:
        return last.strip()
    return None


def normalise_answer(span: str) -> Optional[str]:
    """Canonicalise an answer span, or return None if it cannot be parsed."""
    if span is None:
        return None
    s = span.strip().replace("$", " ")
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\u2212", "-").replace("\u2014", "-").replace("\u2013", "-")
    s = re.sub(r"\\text\s*\{([^}]*)\}", r"\1", s)
    s = s.strip().rstrip(".").strip()

    upper = s.upper().strip(".,;:{} ")
    if upper in ("NONE", "NO SUCH N", "DOES NOT EXIST", "NONEXISTENT", "NULL"):
        return "NONE"
    if upper in ("YES", "TRUE"):
        return "YES"
    if upper in ("NO", "FALSE"):
        return "NO"

    # \frac{a}{b}, \dfrac{a}{b}, \tfrac{a}{b}  ->  (a)/(b)
    s = _FRAC_CMD_RE.sub(r"(\1)/(\2)", s)
    compact = s.replace(" ", "").replace(",", "").replace("{", "").replace("}", "")
    m = _RATIONAL_RE.fullmatch(compact)
    if not m:
        return None
    sign = -1 if m.group(1) == "-" else 1
    try:
        numerator = int(m.group(2))
        denominator = int(m.group(3)) if m.group(3) is not None else 1
        if denominator == 0:
            return None
        return _canonical_fraction(Fraction(sign * numerator, denominator))
    except ValueError:
        return None


def _canonical_fraction(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else (
        f"{value.numerator}/{value.denominator}"
    )


def canonical_gold(answer: str) -> str:
    """Canonicalise a gold answer produced by a family generator."""
    norm = normalise_answer(answer)
    if norm is None:
        raise ValueError(f"gold answer {answer!r} is not in a gradable form")
    return norm


def grade(response: str, gold: str) -> GradeResult:
    """Exact-grade a raw model response against the gold answer."""
    span = extract_answer_span(response)
    if span is None:
        return GradeResult(False, None, True, "")
    parsed = normalise_answer(span)
    if parsed is None:
        return GradeResult(False, None, True, span[:200])
    return GradeResult(parsed == canonical_gold(gold), parsed, False, span[:200])


# --------------------------------------------------------------------------
# boundary-classification parsing
# --------------------------------------------------------------------------

APPLIES = "APPLIES"
DOES_NOT_APPLY = "DOES_NOT_APPLY"


def parse_boundary_label(response: str) -> Optional[bool]:
    """Parse APPLIES / DOES_NOT_APPLY out of a classification response.

    Returns True / False, or None when the response is unparseable.  Unparseable
    responses are counted separately and are never silently scored as a class.
    """
    if not response:
        return None
    text = response.upper()
    # look at the tail first: models often reason then state the label
    idx_neg = max(
        text.rfind("DOES_NOT_APPLY"),
        text.rfind("DOES NOT APPLY"),
        text.rfind("DOESNOTAPPLY"),
    )
    idx_pos = text.rfind("APPLIES")
    # "DOES_NOT_APPLY" contains "APPLY" but not "APPLIES"; guard anyway
    if idx_neg == -1 and idx_pos == -1:
        return None
    if idx_neg > idx_pos:
        return False
    if idx_pos > idx_neg:
        # make sure this APPLIES is not the tail of "DOES_NOT_APPLIES"
        prefix = text[max(0, idx_pos - 14) : idx_pos]
        if "DOES_NOT_" in prefix or "DOES NOT " in prefix:
            return False
        return True
    return None
