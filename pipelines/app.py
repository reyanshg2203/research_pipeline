"""
Blind geometry-problem evaluation survey — one problem per page.

Reads pipelines/survey_data/survey_manifest.json (from prepare_blind_survey.py).
Never loads survey_key.json: raters see no pipeline/provenance information.

Design goals (reduce rater load):
  * one problem per screen, large readable type
  * rubric always visible in the sidebar
  * Previous / Next navigation + progress bar
  * every rating and every page turn autosaves
  * a per-rater progress file you can watch live (see monitor_progress.py)

Run: streamlit run pipelines/app.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
SURVEY_DATA = ROOT / "pipelines" / "survey_data"
MANIFEST_PATH = SURVEY_DATA / "survey_manifest.json"
RESPONSES_DIR = ROOT / "pipelines" / "survey_responses"
RESPONSES_CSV = RESPONSES_DIR / "evaluator_responses.csv"
RESPONSES_JSONL = RESPONSES_DIR / "evaluator_responses.jsonl"
DRAFTS_DIR = RESPONSES_DIR / "drafts"
PROGRESS_DIR = RESPONSES_DIR / "progress"

SECTION_ORDER = ["round1", "round2", "round3"]

RUBRIC = [
    ("geometric_accuracy", "Geometric accuracy",
     "Are the given measurements consistent, and does the problem have a correct, unique answer?"),
    ("lesson_alignment", "Lesson alignment",
     "Does solving it require the skill this lesson teaches, at an appropriate number of steps?"),
    ("linguistic_clarity", "Linguistic clarity",
     "Is the wording unambiguous, well-ordered, and free of distracting errors?"),
]

SCALE_HELP = {
    0: "0 — Unusable",
    1: "1 — Major problems",
    2: "2 — Acceptable with edits",
    3: "3 — Good",
    4: "4 — Excellent, use as-is",
}

CSS = """
<style>
  .problem-card {
      font-size: 1.35rem;
      line-height: 1.75;
      padding: 1.75rem 2rem;
      border: 1px solid rgba(128,128,128,.35);
      border-radius: 10px;
      margin-bottom: 1.5rem;
  }
  .counter { font-variant-numeric: tabular-nums; opacity:.7; font-size:.95rem; }
  .saved   { color:#2e7d32; font-size:.85rem; }
  div[role="radiogroup"] label { font-size: 1.02rem; }
</style>
"""


# --------------------------------------------------------------- data loading
def load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def flat_items(manifest: dict) -> list[dict]:
    """All 90 items in presentation order, tagged with their section index."""
    items: list[dict] = []
    for sec in SECTION_ORDER:
        for it in manifest.get(sec, []):
            items.append({"item_id": it["item_id"], "text": it["text"], "section": sec})
    return items


# --------------------------------------------------------------- persistence
def _safe(email: str) -> str:
    return email.strip().lower().replace("@", "_at_").replace(".", "_")


def draft_path(email: str) -> Path:
    return DRAFTS_DIR / f"{_safe(email)}.json"


def progress_path(email: str) -> Path:
    return PROGRESS_DIR / f"{_safe(email)}.json"


def save_draft(email: str, name: str, ratings: dict, idx: int, total: int) -> None:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    draft_path(email).write_text(json.dumps({
        "evaluator_name": name, "evaluator_email": email,
        "current_index": idx, "ratings": ratings,
    }, indent=2), encoding="utf-8")

    answered = sum(1 for v in ratings.values() if len(v) == len(RUBRIC))
    progress_path(email).write_text(json.dumps({
        "evaluator_name": name,
        "evaluator_email": email,
        "current_index": idx,
        "current_problem": idx + 1,
        "answered": answered,
        "total": total,
        "percent": round(100 * answered / total, 1) if total else 0.0,
        "last_active": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2), encoding="utf-8")


def load_draft(email: str) -> dict | None:
    p = draft_path(email)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def submit(email: str, name: str, ratings: dict) -> None:
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "evaluator_name": name, "evaluator_email": email, "ratings": ratings,
    }
    flat = {"submitted_at": payload["submitted_at"],
            "evaluator_name": name, "evaluator_email": email}
    for item_id, scores in ratings.items():
        for dim, val in scores.items():
            flat[f"{item_id}_{dim}"] = val
    row = pd.DataFrame([flat])
    if RESPONSES_CSV.is_file():
        row = pd.concat([pd.read_csv(RESPONSES_CSV), row], ignore_index=True)
    row.to_csv(RESPONSES_CSV, index=False)
    with RESPONSES_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


# --------------------------------------------------------------- UI pieces
def sidebar_rubric(answered: int, total: int) -> None:
    with st.sidebar:
        st.subheader("Rating guide")
        for _, label, blurb in RUBRIC:
            st.markdown(f"**{label}**  \n<span style='opacity:.75'>{blurb}</span>",
                        unsafe_allow_html=True)
        st.divider()
        st.caption("Scale")
        for _, text in sorted(SCALE_HELP.items()):
            st.caption(text)
        st.divider()
        st.caption(f"Answered {answered} of {total}")
        st.caption("Your progress saves automatically.")


def render_problem(item: dict, idx: int, total: int, ratings: dict) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.progress((idx) / total if total else 0.0)
    st.markdown(f"<div class='counter'>Problem {idx + 1} of {total}</div>",
                unsafe_allow_html=True)
    st.markdown(f"<div class='problem-card'>{item['text']}</div>", unsafe_allow_html=True)

    current = ratings.get(item["item_id"], {})
    cols = st.columns(len(RUBRIC))
    for col, (field, label, _) in zip(cols, RUBRIC):
        with col:
            prev = current.get(field)
            choice = st.radio(
                label,
                options=list(range(5)),
                index=prev if prev is not None else None,
                key=f"{item['item_id']}__{field}",
                horizontal=True,
            )
            if choice is not None:
                current[field] = choice
    ratings[item["item_id"]] = current


def nav_buttons(idx: int, total: int, complete: bool) -> str | None:
    left, mid, right = st.columns([1, 2, 1])
    action = None
    with left:
        if st.button("← Previous", disabled=(idx == 0), use_container_width=True):
            action = "prev"
    with right:
        if idx < total - 1:
            if st.button("Next →", type="primary", use_container_width=True):
                action = "next"
        else:
            if st.button("Submit all ratings", type="primary",
                         disabled=not complete, use_container_width=True):
                action = "submit"
    with mid:
        if idx == total - 1 and not complete:
            st.caption("Rate every problem on all three dimensions to submit.")
    return action


# --------------------------------------------------------------- main
def main() -> None:
    st.set_page_config(page_title="Geometry Problem Evaluation",
                       page_icon="📐", layout="centered")

    manifest = load_manifest()
    items = flat_items(manifest)
    total = len(items)

    if total == 0:
        st.error("No survey manifest found. Run prepare_blind_survey.py first.")
        return

    st.session_state.setdefault("step", "intro")
    st.session_state.setdefault("idx", 0)
    st.session_state.setdefault("ratings", {})

    if st.session_state.step == "done":
        st.success("All ratings submitted. Thank you.")
        return

    if st.session_state.step == "intro":
        st.title("Geometry Problem Evaluation")
        st.write(
            f"You'll review {total} geometry problems, one per screen. "
            "Rate each on three dimensions using the guide in the sidebar. "
            "Your progress saves as you go — you can close the tab and come back."
        )
        name = st.text_input("Name")
        email = st.text_input("Email")
        if name and email:
            d = load_draft(email)
            if d:
                answered = sum(1 for v in d.get("ratings", {}).values() if len(v) == len(RUBRIC))
                st.info(f"Found saved progress: {answered} of {total} problems rated.")
                if st.button("Resume where I left off", type="primary"):
                    st.session_state.update(
                        evaluator_name=d.get("evaluator_name", name),
                        evaluator_email=email,
                        ratings=d.get("ratings", {}),
                        idx=int(d.get("current_index", 0)),
                        step="survey",
                    )
                    st.rerun()
                if st.button("Start over"):
                    st.session_state.update(evaluator_name=name, evaluator_email=email,
                                            ratings={}, idx=0, step="survey")
                    st.rerun()
                return
        if st.button("Begin", type="primary", disabled=not (name and email)):
            st.session_state.update(evaluator_name=name, evaluator_email=email,
                                    ratings={}, idx=0, step="survey")
            st.rerun()
        return

    # ---- survey ----
    email = st.session_state["evaluator_email"]
    name = st.session_state["evaluator_name"]
    ratings = st.session_state["ratings"]
    idx = st.session_state["idx"]
    item = items[idx]

    answered = sum(1 for v in ratings.values() if len(v) == len(RUBRIC))
    sidebar_rubric(answered, total)

    render_problem(item, idx, total, ratings)
    complete = all(
        len(ratings.get(i["item_id"], {})) == len(RUBRIC) for i in items
    )
    action = nav_buttons(idx, total, complete)

    # autosave on every interaction (rating change or navigation)
    save_draft(email, name, ratings, idx, total)

    if action == "prev":
        st.session_state.idx = max(0, idx - 1)
        st.rerun()
    elif action == "next":
        st.session_state.idx = min(total - 1, idx + 1)
        st.rerun()
    elif action == "submit":
        submit(email, name, ratings)
        try:
            draft_path(email).unlink(missing_ok=True)
        except OSError:
            pass
        st.session_state.step = "done"
        st.rerun()


if __name__ == "__main__":
    main()
