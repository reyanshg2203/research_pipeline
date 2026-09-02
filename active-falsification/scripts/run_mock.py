"""Offline end-to-end pipeline test with the deterministic mock model.

    python scripts/run_mock.py

Exercises calibration -> seeds -> frozen tests -> induction -> Active ->
compute-matched Passive -> evaluation -> main_table.csv without a GPU.
The resulting numbers are meaningless and are stamped ``is_mock`` everywhere.
"""

import os
import sys

import _bootstrap  # noqa: F401
from run_experiment import main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--config" not in argv:
        argv += ["--config", os.path.join(ROOT, "configs", "mock.yaml")]
    sys.exit(main(argv))
