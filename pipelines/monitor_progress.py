#!/usr/bin/env python3
"""
monitor_progress.py — watch evaluator progress live.

The survey app writes one JSON file per rater to
pipelines/survey_responses/progress/. This polls them and prints a table.

    python3 pipelines/monitor_progress.py            # one snapshot
    python3 pipelines/monitor_progress.py --watch    # refresh every 10s
    python3 pipelines/monitor_progress.py --watch --interval 30
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRESS_DIR = ROOT / "pipelines" / "survey_responses" / "progress"
RESPONSES_JSONL = ROOT / "pipelines" / "survey_responses" / "evaluator_responses.jsonl"


def _age(iso: str) -> str:
    try:
        then = datetime.fromisoformat(iso)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return "?"
    secs = (datetime.now(timezone.utc) - then).total_seconds()
    if secs < 90:
        return f"{int(secs)}s ago"
    if secs < 5400:
        return f"{int(secs // 60)}m ago"
    return f"{int(secs // 3600)}h ago"


def _bar(pct: float, width: int = 24) -> str:
    filled = int(round(width * pct / 100))
    return "█" * filled + "·" * (width - filled)


def submitted_emails() -> set[str]:
    done: set[str] = set()
    if RESPONSES_JSONL.is_file():
        for line in RESPONSES_JSONL.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line).get("evaluator_email", "").lower())
            except json.JSONDecodeError:
                continue
    return done


def snapshot() -> None:
    if not PROGRESS_DIR.is_dir():
        print("No progress yet (no rater has started).")
        return
    done = submitted_emails()
    rows = []
    for p in sorted(PROGRESS_DIR.glob("*.json")):
        try:
            rows.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    if not rows:
        print("No progress yet (no rater has started).")
        return

    print(f"{'rater':<22} {'progress':<26} {'done':>7}  {'at':>6}  {'last active':>12}  status")
    print("-" * 96)
    for r in sorted(rows, key=lambda x: -x.get("percent", 0)):
        name = (r.get("evaluator_name") or r.get("evaluator_email", "?"))[:20]
        pct = r.get("percent", 0.0)
        status = "SUBMITTED" if r.get("evaluator_email", "").lower() in done else "in progress"
        print(f"{name:<22} {_bar(pct):<26} "
              f"{r.get('answered',0):>3}/{r.get('total',0):<3} "
              f"{r.get('current_problem','?'):>6}  "
              f"{_age(r.get('last_active','')):>12}  {status}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help="refresh continuously")
    ap.add_argument("--interval", type=int, default=10, help="seconds between refreshes")
    args = ap.parse_args()

    if not args.watch:
        snapshot()
        return
    try:
        while True:
            os.system("clear" if os.name != "nt" else "cls")
            print(f"evaluator progress — {datetime.now().strftime('%H:%M:%S')} "
                  f"(refresh {args.interval}s, Ctrl-C to stop)\n")
            snapshot()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()