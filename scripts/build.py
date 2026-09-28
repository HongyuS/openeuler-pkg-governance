#!/usr/bin/env python3
"""CLI entry point for the openEuler package-governance collection job.

The heavy lifting lives in :mod:`app.build_job` so the web UI can trigger the
exact same online refresh from the “刷新数据” button.

Usage:
    python scripts/build.py            # full online build
    python scripts/build.py --quick    # fast refresh (default pair + catalogue)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("PYTHONPATH", str(BACKEND))

from app import config  # ruff: ignore[module-import-not-at-top-of-file]
from app.build_job import run_build  # ruff: ignore[module-import-not-at-top-of-file]
from app.utils import setup_logging  # ruff: ignore[module-import-not-at-top-of-file]

setup_logging()


def main() -> None:
    """Parse CLI flags, run the collection job and print a summary."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="refresh only the default pair + catalogue")
    ap.add_argument("--scope", choices=["quick", "full"], default="")
    ap.add_argument("--activity-limit", type=int, default=config.ACTIVITY_SAMPLE_LIMIT)
    args = ap.parse_args()

    scope = args.scope or ("quick" if args.quick else "full")
    meta = run_build(scope, activity_limit=args.activity_limit)
    print(
        json.dumps(
            {
                "scope": meta.get("scope"),
                "streams": len(meta.get("streams", [])),
                "default": meta.get("default"),
                "total": meta.get("total_sources"),
                "activity_measured": meta.get("activity_measured"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
