"""Final run: full precision, publication counts (spec S.20, S.21).

    python scripts/run_final.py --config configs/final.yaml
"""

import os
import sys

import _bootstrap  # noqa: F401
from run_experiment import main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--config" not in argv:
        argv += ["--config", os.path.join(ROOT, "configs", "final.yaml")]
    sys.exit(main(argv))
