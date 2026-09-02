#!/usr/bin/env python3
"""Generate a deterministic demo dataset with no network access.

PREFERS existing real caches (inventory.json / ubuntu.json / activity.json) when
present — so `make seed` after a `make build` simply re-master the same real data.
Otherwise it synthesises a realistic, representative package set so the interactive
dashboard works out of the box on a fresh clone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app import config  # noqa: E402
from app.engine import pipeline  # noqa: E402
from app.models import RepoSignals  # noqa: E402
from app.utils import iso_today, LOG, setup_logging  # noqa: E402

setup_logging()


def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return default


def _synthetic_inventory() -> dict[str, dict]:
    """A small, realistic stand-in inventory (used only if real caches are absent)."""
    rules = __import__("app").engine.rules_loader.rules()
    inv: dict[str, dict] = {}
    base = [
        ("kernel", "0:6.18.40", "The Linux kernel", "GPL-2.0", (0,)),
        ("glibc", "0:2.38", "The GNU libc libraries", "GPL-2.0", (50,)),
        ("openssl", "1:3.5.8", "A toolkit for SSL/TLS", "Apache-2.0", (40,)),
        ("systemd", "0:255", "System and service manager", "LGPL-2.1", (30,)),
        ("bash", "0:5.2.37", "The Bourne Again Shell", "GPL-3.0", (20,)),
        ("python3", "0:3.11.13", "Interpreter of the Python language", "PSF", (25,)),
        ("vim", "2:9.2.0954", "Vi IMproved", "Vim", (4,)),
        ("nginx", "1:1.30.4", "HTTP and reverse proxy server", "BSD-2", (1,)),
        ("nodejs", "1:24.18.1", "JavaScript runtime", "MIT", (3,)),
        ("mariadb", "4:11.8.9", "MariaDB database server", "GPL-2.0", (2,)),
        ("podman", "1:4.9.4", "Container engine", "Apache-2.0", (2,)),
    ]
    for name, ver, summary, lic, rd in base:
        inv[name] = {
            "name": name,
            "versions": {"openEuler_LTS": ver, "openEuler_innovation": ver,
                         "openEuler_26.09-DevStation": ver},
            "arches": ["x86_64"],
            "summary": summary,
            "license": lic,
            "reverse": rd[0],
            "provides": [name],
            "requires": ["glibc", "openssl"],
        }
    return inv


def main() -> None:
    inventory = _load(config.CACHE_DIR / "inventory.json", {}).get("packages", None)
    if not inventory:
        inventory = _synthetic_inventory()
    ubuntu = _load(config.UBUNTU_CACHE, {}).get("versions", None)
    if not ubuntu:
        ubuntu = {
            "ubuntu_LTS": {n: v for n, v in {}.items()},
            "ubuntu_interim": {},
        }
    activity_raw = _load(config.CACHE_DIR / "activity.json", {})
    activity = {k: RepoSignals(**v) for k, v in activity_raw.items() if isinstance(v, dict)}

    special = {s["name"]: s["note"] for s in __import__("app").engine.rules_loader.rules().get("special_packages", [])}
    packages = pipeline.build_packages(inventory, ubuntu, activity, special=special)

    streams = {"openEuler_LTS": "openEuler-24.03-LTS-SP4", "openEuler_innovation": "openEuler-26.09-DevStation"}
    meta = {
        "streams": streams,
        "baselines": {"ubuntu_LTS": "resolute", "ubuntu_interim": "stonking"},
        "data_date": iso_today(),
        "activity_measured": len([p for p in packages if p.activity.source == "measured"]),
        "total_sources": len(packages),
        "seed": True,
    }
    config.PACKAGES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    config.PACKAGES_CACHE.write_text(
        json.dumps({"meta": meta, "packages": [p.to_dict() for p in packages]}, ensure_ascii=False, indent=2)
    )
    LOG.info("seed wrote %d packages -> %s", len(packages), config.PACKAGES_CACHE)


if __name__ == "__main__":
    main()
