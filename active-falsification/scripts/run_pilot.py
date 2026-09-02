"""Pilot run: small models, 4-bit, small counts (spec S.20, S.21).

    python scripts/run_pilot.py --config configs/pilot.yaml
"""

import os
import sys

import _bootstrap  # noqa: F401
from run_experiment import main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--config" not in argv:
        argv += ["--config", os.path.join(ROOT, "configs", "pilot.yaml")]
    sys.exit(main(argv))
