"""
storage.py — one storage API, two backends.

    local   -> JSON/CSV files on disk (for your own testing)
    sheets  -> Google Sheets (for deployment; survives restarts)

Backend selection, in priority order:
  1. st.secrets["storage"]["backend"]      (set this in Streamlit Cloud)
  2. env var SURVEY_STORAGE                (export SURVEY_STORAGE=sheets)
  3. "local"                               (default — safe for testing)

The Sheet must have these tabs (exact names):
    cal_drafts, cal_responses, drafts, progress, responses,
    cal_prolific_drafts, cal_prolific_responses, consent_log

Every function takes a `scope`: "cal" for the (internal) calibration app,
"cal_prolific" for the Prolific calibration app, "main" for the 90-problem app.
That keeps every study's data separate in one spreadsheet.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# tab names per scope
TABS = {
    "cal": {"drafts": "cal_drafts", "responses": "cal_responses", "progress": "progress"},
    "cal_prolific": {"drafts": "cal_prolific_drafts",
                     "responses": "cal_prolific_responses", "progress": "progress"},
    "main": {"drafts": "drafts", "responses": "responses", "progress": "progress"},
}

# the shared consent-audit tab (one row per participant consent decision)
CONSENT_TAB = "consent_log"

# local directories per scope
LOCAL_DIR = {
    "cal": ROOT / "pipelines" / "calibration_responses",
    "cal_prolific": ROOT / "pipelines" / "calibration_prolific_responses",
    "main": ROOT / "pipelines" / "survey_responses",
}


# ------------------------------------------------------------------ backend
def _backend() -> str:
    try:
        import streamlit as st
        b = st.secrets.get("storage", {}).get("backend")
        if b:
            return b
    except Exception:
        pass
    return os.environ.get("SURVEY_STORAGE", "local")


def _safe(email: str) -> str:
    return email.strip().lower().replace("@", "_at_").replace(".", "_")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ sheets
_sheet_cache: Any = None


def _sheet():
    """Open the spreadsheet once and reuse it."""
    global _sheet_cache
    if _sheet_cache is not None:
        return _sheet_cache
    import gspread
    import streamlit as st
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=scopes)
    client = gspread.authorize(creds)
    _sheet_cache = client.open_by_key(st.secrets["sheets"]["sheet_id"])
    return _sheet_cache


def _tab(scope: str, kind: str):
    return _sheet().worksheet(TABS[scope][kind])


def _find_row(ws, email: str, extra_match: str | None = None) -> int | None:
    """Row index (1-based) whose col A == email (and col B == extra_match)."""
    for i, row in enumerate(ws.get_all_values(), start=1):
        if i == 1 or not row:
            continue
        if row[0].strip().lower() == email.strip().lower():
            if extra_match is None or (len(row) > 1 and row[1] == extra_match):
                return i
    return None


# ------------------------------------------------------------------ API
def save_draft(scope: str, email: str, payload: dict) -> None:
    """payload: whatever the app needs to resume (ratings, round, index, name)."""
    payload = {**payload, "updated_at": _now()}
    if _backend() == "sheets":
        ws = _tab(scope, "drafts")
        blob = json.dumps(payload)
        row = _find_row(ws, email)
        if row:
            ws.update(f"A{row}:C{row}", [[email, payload["updated_at"], blob]])
        else:
            ws.append_row([email, payload["updated_at"], blob])
    else:
        d = LOCAL_DIR[scope] / "drafts"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{_safe(email)}.json").write_text(json.dumps(payload, indent=2),
                                                encoding="utf-8")


def load_draft(scope: str, email: str) -> dict | None:
    if not email:
        return None
    if _backend() == "sheets":
        ws = _tab(scope, "drafts")
        row = _find_row(ws, email)
        if not row:
            return None
        vals = ws.row_values(row)
        if len(vals) < 3:
            return None
        try:
            return json.loads(vals[2])
        except json.JSONDecodeError:
            return None
    p = LOCAL_DIR[scope] / "drafts" / f"{_safe(email)}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def delete_draft(scope: str, email: str) -> None:
    if _backend() == "sheets":
        ws = _tab(scope, "drafts")
        row = _find_row(ws, email)
        if row:
            ws.delete_rows(row)
        return
    p = LOCAL_DIR[scope] / "drafts" / f"{_safe(email)}.json"
    p.unlink(missing_ok=True)


def save_progress(scope: str, email: str, name: str, answered: int, total: int,
                  where: str) -> None:
    """`where` is a human string, e.g. 'Round 2, problem 7 of 30'."""
    pct = round(100 * answered / total, 1) if total else 0.0
    if _backend() == "sheets":
        ws = _tab(scope, "progress")
        row = _find_row(ws, email, extra_match=scope)
        vals = [email, scope, name, answered, total, pct, where, _now()]
        if row:
            ws.update(f"A{row}:H{row}", [vals])
        else:
            ws.append_row(vals)
    else:
        d = LOCAL_DIR[scope] / "progress"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{_safe(email)}.json").write_text(json.dumps({
            "evaluator_email": email, "evaluator_name": name, "scope": scope,
            "answered": answered, "total": total, "percent": pct,
            "where": where, "last_active": _now(),
        }, indent=2), encoding="utf-8")


def submit_response(scope: str, email: str, name: str, ratings: dict,
                    dims: list[str]) -> None:
    """One row per (rater, item) — the shape irr_report.py and your analysis want."""
    ts = _now()
    rows = [[email, name, item_id, *[scores.get(d, "") for d in dims], ts]
            for item_id, scores in sorted(ratings.items())]
    if _backend() == "sheets":
        ws = _tab(scope, "responses")
        ws.append_rows(rows)
        return
    import pandas as pd
    d = LOCAL_DIR[scope]
    d.mkdir(parents=True, exist_ok=True)
    csv = d / ("calibration_responses.csv" if scope == "cal" else "responses.csv")
    cols = ["evaluator_email", "evaluator_name", "item_id", *dims, "submitted_at"]
    df = pd.DataFrame(rows, columns=cols)
    if csv.is_file():
        df = pd.concat([pd.read_csv(csv), df], ignore_index=True)
    df.to_csv(csv, index=False)


def has_submitted(scope: str, email: str) -> bool:
    if _backend() == "sheets":
        ws = _tab(scope, "responses")
        return any(r and r[0].strip().lower() == email.strip().lower()
                   for r in ws.get_all_values()[1:])
    csv = LOCAL_DIR[scope] / ("calibration_responses.csv" if scope == "cal"
                              else "responses.csv")
    if not csv.is_file():
        return False
    import pandas as pd
    df = pd.read_csv(csv)
    return email.strip().lower() in df["evaluator_email"].str.lower().values


def log_consent(scope: str, pid: str, agreed: bool,
                study_id: str = "", session_id: str = "") -> None:
    """Append one immutable row recording a participant's consent decision.

    This is the auditable consent record you cite in the IRB package: it proves
    each participant was shown the consent screen and made an explicit choice
    before any rating data was collected. Rows are append-only (never updated),
    so a decision is never silently overwritten.
    """
    row = [pid, scope, "agreed" if agreed else "declined",
           study_id, session_id, _now()]
    if _backend() == "sheets":
        _sheet().worksheet(CONSENT_TAB).append_row(row)
    else:
        d = LOCAL_DIR[scope] / "consent"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{_safe(pid)}.json").write_text(json.dumps({
            "prolific_pid": pid, "scope": scope,
            "consent": "agreed" if agreed else "declined",
            "study_id": study_id, "session_id": session_id,
            "logged_at": _now(),
        }, indent=2), encoding="utf-8")


def backend_name() -> str:
    return _backend()