"""Shared entry point for every run (spec S.21).

    python scripts/run_experiment.py --config configs/pilot.yaml

Refuses to start unless the mathematical self-test passes, unless you pass
--skip-self-test (never do that for a publication run).
"""

import argparse
import os
import subprocess
import sys
import time

import _bootstrap  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_run_id(config_path: str, tag: str) -> str:
    stem = os.path.splitext(os.path.basename(config_path))[0]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{stamp}_{stem}" + (f"_{tag}" if tag else "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--outputs", default=os.path.join(ROOT, "outputs"))
    ap.add_argument("--skip-self-test", action="store_true",
                    help="NOT for publication runs")
    ap.add_argument("--models", nargs="*", default=None,
                    help="override the model list in the config")
    args = ap.parse_args(argv)

    if not args.skip_self_test:
        print("running scripts/self_test.py --quick before touching a model ...")
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "self_test.py"), "--quick"],
            cwd=ROOT,
        )
        if proc.returncode != 0:
            print("\nself-test FAILED; refusing to run models.", file=sys.stderr)
            return proc.returncode
    else:
        print("[WARN] self-test skipped -- this run must not be used in a publication")

    from runner import Runner, load_config

    config = load_config(args.config)
    if args.models:
        config["models"] = args.models
    run_id = args.run_id or build_run_id(args.config, args.tag)
    run_dir = os.path.join(args.outputs, run_id)
    print(f"\nrun directory: {run_dir}")
    result = Runner(config, run_dir).run()
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
