"""Rebuild every reported table from the raw per-item evaluation rows.

    python scripts/make_tables.py --run-dir outputs/<RUN_ID>

Recomputing from ``evaluation_raw.jsonl`` -- one row per classified problem,
carrying the gold oracle label and the model's raw response -- means every
number in every table is traceable to a saved raw output (spec S.24.8).

Writes:
  main_table.csv          per model x family x split x repeat
  pooled_table.csv        pooled over repeats, and over families, per model
  confusion_matrices.csv
  summary_long.csv        (rebuilt)
  token_accounting.csv    exact adaptation output tokens and observation counts
"""

import argparse
import collections
import csv
import json
import os
import sys

import _bootstrap  # noqa: F401
from metrics import bootstrap_ci, paired_bootstrap_delta, summarise

CONDITIONS = ("H0", "Passive", "Active")


def read_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_csv(path, rows):
    if not rows:
        open(path, "w", encoding="utf-8").close()
        return
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def fmt(v, nd=4):
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return round(v, nd) if isinstance(v, float) else v


def load_repeat_index(run_dir):
    """Map (model, family, repeat) -> token/observation accounting from traces."""
    index = {}
    for name in os.listdir(run_dir):
        if not (name.startswith("active_trace_") or name.startswith("passive_trace_")):
            continue
        with open(os.path.join(run_dir, name), "r", encoding="utf-8") as fh:
            trace = json.load(fh)
        repeat = 0
        stem = name.rsplit(".", 1)[0]
        if "_r" in stem:
            try:
                repeat = int(stem.rsplit("_r", 1)[1])
            except ValueError:
                repeat = 0
        key = (trace["model"], trace["family"], repeat)
        entry = index.setdefault(key, {})
        entry[trace["condition"]] = trace
    return index


def group(rows, keyfn):
    out = collections.defaultdict(list)
    for r in rows:
        out[keyfn(r)].append(r)
    return out


def metrics_for(rows):
    y_true = [bool(r["gold_strategy_applies"]) for r in rows]
    y_pred = [r["predicted"] if r["parsed"] else None for r in rows]
    stats = summarise(y_true, y_pred)
    lo, hi = bootstrap_ci(y_true, y_pred, seed=0)
    stats["ci95_lo"], stats["ci95_hi"] = lo, hi
    return stats, y_true, y_pred


def aligned_preds(rows_by_condition):
    """Align conditions on shared problem ids so deltas are genuinely paired."""
    ids = None
    for cond in CONDITIONS:
        rows = rows_by_condition.get(cond, [])
        s = {r["problem_id"] for r in rows}
        ids = s if ids is None else (ids & s)
    ids = sorted(ids or [])
    y_true, preds = [], {c: [] for c in CONDITIONS}
    lookup = {
        c: {r["problem_id"]: r for r in rows_by_condition.get(c, [])}
        for c in CONDITIONS
    }
    for pid in ids:
        base = lookup["Active"].get(pid) or lookup["H0"].get(pid)
        if base is None:
            continue
        y_true.append(bool(base["gold_strategy_applies"]))
        for c in CONDITIONS:
            r = lookup[c].get(pid)
            preds[c].append(r["predicted"] if (r and r["parsed"]) else None)
    return y_true, preds


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args()
    run_dir = args.run_dir

    raw = [
        r for r in read_jsonl(os.path.join(run_dir, "evaluation_raw.jsonl"))
        if r.get("split") in ("iid", "challenge")
    ]
    if not raw:
        print(f"no evaluation rows found in {run_dir}/evaluation_raw.jsonl",
              file=sys.stderr)
        return 1
    # per-item rows do not carry the repeat index; recover it from the row order
    # by trusting the summary file when it exists
    summary_rows = []
    summary_path = os.path.join(run_dir, "summary_long.csv")
    if os.path.exists(summary_path):
        with open(summary_path, newline="", encoding="utf-8") as fh:
            summary_rows = list(csv.DictReader(fh))
    repeat_by_key = {}
    for r in summary_rows:
        repeat_by_key[(r["model"], r["family"], r["split"], r["condition"])] = r.get(
            "repeat", "0"
        )

    traces = load_repeat_index(run_dir)
    manifest_path = os.path.join(run_dir, "run_manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    is_mock = bool(manifest.get("contains_mock_model"))
    precision = manifest.get("precision", "")

    # ---------------- main table -------------------------------------
    main_rows, conf_rows, long_rows, token_rows = [], [], [], []
    by_cell = group(raw, lambda r: (r["model"], r["family"], r["split"]))
    for (model, family, split), rows in sorted(by_cell.items()):
        by_cond = group(rows, lambda r: r["condition"])
        y_true, preds = aligned_preds(by_cond)
        cell = {"model": model, "family": family, "split": split,
                "n_test": len(y_true), "is_mock": is_mock, "precision": precision}
        for cond in CONDITIONS:
            stats, _, _ = metrics_for(by_cond.get(cond, []))
            cell[cond] = fmt(stats["accuracy"])
            cell[f"{cond}_ci_lo"] = fmt(stats["ci95_lo"])
            cell[f"{cond}_ci_hi"] = fmt(stats["ci95_hi"])
            cell[f"unparsed_{cond}"] = stats["unparsed"]
            conf_rows.append({
                "model": model, "family": family, "split": split, "condition": cond,
                "tp": stats["tp"], "fp": stats["fp"], "tn": stats["tn"],
                "fn": stats["fn"], "unparsed": stats["unparsed"],
                "accuracy": fmt(stats["accuracy"]),
                "precision_applies": fmt(stats["precision_applies"]),
                "recall_applies": fmt(stats["recall_applies"]),
                "f1_applies": fmt(stats["f1_applies"]),
                "base_rate_positive": fmt(stats["base_rate_positive"]),
                "ci95_lo": fmt(stats["ci95_lo"]), "ci95_hi": fmt(stats["ci95_hi"]),
            })
            long_rows.append({
                "model": model, "family": family, "split": split, "condition": cond,
                **{k: fmt(v) for k, v in stats.items()},
            })
        for a, b in (("Active", "Passive"), ("Active", "H0"), ("Passive", "H0")):
            d = paired_bootstrap_delta(y_true, preds[a], preds[b], seed=0)
            cell[f"delta_{a.lower()}_{b.lower()}"] = fmt(d["delta"])
            cell[f"delta_{a.lower()}_{b.lower()}_ci_lo"] = fmt(d["lo"])
            cell[f"delta_{a.lower()}_{b.lower()}_ci_hi"] = fmt(d["hi"])

        active = [t.get("active") for k, t in traces.items()
                  if k[0] == model and k[1] == family and "active" in t]
        pas = [t.get("passive") for k, t in traces.items()
               if k[0] == model and k[1] == family and "passive" in t]
        if active:
            cell["A_tokens"] = sum(t["adaptation_output_tokens"] for t in active) / len(active)
            cell["A_obs"] = sum(t["n_observations"] for t in active) / len(active)
            cell["A_unsat"] = sum(t["n_unsatisfiable"] for t in active) / len(active)
            cell["A_revisions"] = sum(t["n_revisions"] for t in active) / len(active)
        if pas:
            cell["P_tokens"] = sum(t["adaptation_output_tokens"] for t in pas) / len(pas)
            cell["P_obs"] = sum(t["n_observations"] for t in pas) / len(pas)
            cell["P_revisions"] = sum(t["n_revisions"] for t in pas) / len(pas)
        if active and pas:
            at = cell["A_tokens"]
            cell["token_mismatch_pct"] = fmt(
                100.0 * (cell["P_tokens"] - at) / at if at else float("nan"), 2
            )
        cell["n_repeats"] = len(active) or 1
        main_rows.append(cell)

    # ---------------- pooled table ------------------------------------
    pooled_rows = []
    for split in ("iid", "challenge"):
        for model in sorted({r["model"] for r in raw}):
            rows = [r for r in raw if r["split"] == split and r["model"] == model]
            if not rows:
                continue
            by_cond = group(rows, lambda r: r["condition"])
            y_true, preds = aligned_preds(by_cond)
            row = {"model": model, "family": "POOLED", "split": split,
                   "n_test": len(y_true), "is_mock": is_mock}
            for cond in CONDITIONS:
                stats, _, _ = metrics_for(by_cond.get(cond, []))
                row[cond] = fmt(stats["accuracy"])
                row[f"{cond}_ci_lo"] = fmt(stats["ci95_lo"])
                row[f"{cond}_ci_hi"] = fmt(stats["ci95_hi"])
            for a, b in (("Active", "Passive"), ("Active", "H0")):
                d = paired_bootstrap_delta(y_true, preds[a], preds[b], seed=0)
                row[f"delta_{a.lower()}_{b.lower()}"] = fmt(d["delta"])
                row[f"delta_{a.lower()}_{b.lower()}_ci_lo"] = fmt(d["lo"])
                row[f"delta_{a.lower()}_{b.lower()}_ci_hi"] = fmt(d["hi"])
            pooled_rows.append(row)

    # ---------------- token accounting --------------------------------
    for (model, family, repeat), t in sorted(traces.items()):
        a, p = t.get("active"), t.get("passive")
        token_rows.append({
            "model": model, "family": family, "repeat": repeat,
            "A_tokens": a and a["adaptation_output_tokens"],
            "P_tokens": p and p["adaptation_output_tokens"],
            "relative_mismatch_pct": fmt(
                100.0 * p["notes"]["relative_mismatch"], 2) if p else "",
            "A_obs": a and a["n_observations"], "P_obs": p and p["n_observations"],
            "A_revisions": a and a["n_revisions"], "P_revisions": p and p["n_revisions"],
            "A_query_generations": a and a["n_query_generations"],
            "A_unsatisfiable": a and a["n_unsatisfiable"],
            "A_unsat_rate": fmt(a["notes"]["unsat_rate"]) if a else "",
            "passive_budget_cap_binding": p and p["notes"]["budget_cap_binding"],
        })

    write_csv(os.path.join(run_dir, "main_table.csv"), main_rows)
    write_csv(os.path.join(run_dir, "pooled_table.csv"), pooled_rows)
    write_csv(os.path.join(run_dir, "confusion_matrices.csv"), conf_rows)
    write_csv(os.path.join(run_dir, "summary_long.csv"), long_rows)
    write_csv(os.path.join(run_dir, "token_accounting.csv"), token_rows)

    print(f"rebuilt tables in {run_dir} from {len(raw)} raw evaluation rows")
    for name in ("main_table.csv", "pooled_table.csv", "confusion_matrices.csv",
                 "summary_long.csv", "token_accounting.csv"):
        print(f"  {name}")
    if is_mock:
        print("\n[!] this run contains the MOCK model: the numbers are NOT results.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
