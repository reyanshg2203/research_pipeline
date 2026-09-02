"""Regenerate docs/PROMPTS.md verbatim from src/prompts.py (spec S.18).

Keeping the documentation generated means it cannot drift from the code the
experiment actually runs.
"""

import os
import sys

import _bootstrap  # noqa: F401
import prompts as P
from families import all_families

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ORDER = [
    ("A. Zero-shot solver (calibration and seed screening)",
     ["A_solve_system", "A_solve_user"]),
    ("B. Strategy and H0 induction from seed demonstrations",
     ["B_induce_system", "B_induce_user"]),
    ("C. Boundary classification (primary evaluation)",
     ["C_classify_system", "C_classify_user"]),
    ("D. Active experiment selection",
     ["D_query_system", "D_query_user"]),
    ("E. Hypothesis revision (identical for Active and Passive)",
     ["E_revise_system", "E_revise_user"]),
    ("F. Invalid Active request -- one reformulation attempt",
     ["F_unsat_system", "F_unsat_user"]),
]


def main() -> int:
    lines = [
        "# PROMPTS",
        "",
        "**This file is generated. Do not edit it by hand.**",
        "Regenerate with `python scripts/export_prompts.py` after editing "
        "`src/prompts.py`.",
        "",
        f"- prompt version: `{P.PROMPT_VERSION}`",
        f"- prompt hash: `{P.prompts_hash()}`",
        "",
        "Every prompt below is reproduced verbatim. Placeholders in braces are "
        "filled at run time.",
        "",
        "## Leakage rules",
        "",
        "No prompt may contain the oracle label `strategy_applies`, a family's",
        "canonical `strategy_description`, hidden test membership, or latent",
        "generator parameters that are not already visible in the rendered problem.",
        "`tests/test_no_leakage.py` enforces this mechanically.",
        "",
        "The only place a worked solution is ever shown is prompt B, and only for",
        "the six approved seed problems.",
        "",
    ]
    for title, keys in ORDER:
        lines += ["---", "", f"## {title}", ""]
        for key in keys:
            role = "system" if key.endswith("_system") else "user"
            lines += [f"### `{key}` ({role})", "", "```text",
                      P.ALL_PROMPT_TEMPLATES[key], "```", ""]

    lines += [
        "---",
        "",
        "## Active query schemas shown to the model",
        "",
        "These are the ONLY family internals the Active condition ever sees.",
        "Every value is observable directly from a problem statement.",
        "",
    ]
    for name, fam in all_families().items():
        lines += [f"**{name}**", ""]
        for feature, values in fam.query_schema().items():
            lines.append(f"- `{feature}`: {', '.join(f'`{v}`' for v in values)}")
        lines.append("")

    lines += [
        "---",
        "",
        "## Oracle-only features -- NEVER shown to any model",
        "",
        "These researcher-side diagnostics are used for validation, balancing and",
        "audit. Several are deterministic synonyms for the hidden label, which is",
        "exactly why they are confined to this namespace and are rejected as",
        "unknown feature names if a model asks for one.",
        "",
    ]
    for name, fam in all_families().items():
        lines += [f"**{name}**", ""]
        for feature, values in fam.oracle_feature_schema.items():
            lines.append(f"- `{feature}`: {', '.join(f'`{v}`' for v in values)}")
        lines.append("")

    out = os.path.join(ROOT, "docs", "PROMPTS.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
