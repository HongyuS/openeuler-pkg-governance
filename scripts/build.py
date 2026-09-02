#!/usr/bin/env python3
"""Build the full package-governance dataset from live public APIs.

Collects:
  1. the selectable **stream catalogue** (maintained LTS + released innovation +
     every DevStation RC / daily build),
  2. a per-stream *version* matrix (``stream_versions.json``),
  3. the canonical (default-pair) openEuler inventory with dependency graph,
  4. Ubuntu LTS + frontier baseline versions,
  5. per-package activity/backlog from the public GitCode API (full scan by
     default; the activity cache makes reruns incremental),

then runs the governance engine and writes ``backend/data/cache/packages.json``.

Usage:
    python scripts/build.py [--no-activity] [--activity-limit N]
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

from app import config  # noqa: E402
from app.collectors import gitcode, npm, openeuler, pypi, repos, ubuntu  # noqa: E402
from app.engine import pipeline  # noqa: E402
from app.utils import LOG, setup_logging  # noqa: E402

setup_logging()


def pick_activity_targets(inventory: dict[str, dict], limit: int) -> list[str]:
    """Priority-ordered activity targets: P0/P1/special packages first, then
    everything else, so an interrupted run still covers the important repos."""
    rules = __import__("app").engine.rules_loader.rules()
    p0 = {p for p in set(rules.get("P0_critical", [])) | set(rules.get("python_closure_seeds", [])) if p in inventory}
    p1 = {p for p in rules.get("P1_base", []) if p in inventory}
    special = {s["name"] for s in rules.get("special_packages", []) if s.get("name") in inventory}
    selected: list[str] = []
    for group in (sorted(p0), sorted(p1 - p0), sorted(special - p0 - p1)):
        for name in group:
            if name not in selected:
                selected.append(name)
    for name in sorted(inventory):
        if name not in selected:
            selected.append(name)
    return selected[:limit] if limit else selected


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-activity", action="store_true")
    ap.add_argument("--no-pypi", action="store_true")
    ap.add_argument("--no-npm", action="store_true")
    ap.add_argument("--activity-limit", type=int, default=config.ACTIVITY_SAMPLE_LIMIT)
    args = ap.parse_args()

    catalog = openeuler.stream_catalog()
    LOG.info("stream catalogue: %d selectable streams", len(catalog))
    default = openeuler.discover_latest()
    LOG.info("default pair: %s", default)

    # 1) Per-stream version matrix.
    stream_versions: dict[str, dict[str, str]] = {}
    sv_cache = config.STREAM_VERSIONS_CACHE
    if sv_cache.exists():
        try:
            stream_versions = json.loads(sv_cache.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            stream_versions = {}
    for s in catalog:
        sid = s["id"]
        cached = stream_versions.get(sid)
        if cached and all(isinstance(v, dict) for v in cached.values()):
            continue
        LOG.info("collecting stream versions for %s …", sid)
        try:
            stream_versions[sid] = openeuler.collect_stream_versions(sid)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("stream %s failed: %s", sid, exc)
            stream_versions[sid] = {}
    sv_cache.parent.mkdir(parents=True, exist_ok=True)
    sv_cache.write_text(json.dumps(stream_versions, ensure_ascii=False))

    # 2) Canonical (default-pair) full inventory for the governance graph.
    LOG.info("collecting canonical openEuler inventory (dependency graph)…")
    inventory = openeuler.collect(default)
    LOG.info("canonical inventory: %d source packages", len(inventory))
    _write(config.CACHE_DIR / "inventory.json", {"streams": default, "packages": inventory})

    # 3) Ubuntu baseline.
    LOG.info("collecting Ubuntu baseline versions…")
    ubuntu_data = ubuntu.collect()
    ub_versions = ubuntu_data["versions"]
    # Slim ubuntu maps to only packages present in the openEuler inventory.
    slim = {
        "ubuntu_LTS": {k: v for k, v in ub_versions.get("ubuntu_LTS", {}).items() if k in inventory},
        "ubuntu_interim": {k: v for k, v in ub_versions.get("ubuntu_interim", {}).items() if k in inventory},
    }

    # 4) Activity (full scan by default; cache makes reruns incremental).
    activity: dict = {}
    if not args.no_activity:
        targets = pick_activity_targets(inventory, args.activity_limit)
        LOG.info("collecting activity for %d package repos via GitCode API…", len(targets))
        resolver = repos.build_resolver(list(inventory.keys()))
        activity = gitcode.collect_many(targets, cache=config.ACTIVITY_CACHE, resolve=resolver)
        LOG.info("activity collected for %d packages", len(activity))

    # 5) Governance pipeline.
    LOG.info("running governance engine…")
    rules = __import__("app").engine.rules_loader.rules()
    special = {s["name"]: s["note"] for s in rules.get("special_packages", [])}
    pypi_profiles: dict[str, dict] = {}
    if not args.no_pypi:
        pip_mods = [n for n in inventory if pypi.is_pip_module(n)]
        LOG.info("fetching PyPI profiles for %d pip modules…", len(pip_mods))
        pypi_profiles = pypi.collect(pip_mods, cache=config.CACHE_DIR / "pypi.json")
    npm_profiles: dict[str, dict] = {}
    if not args.no_npm:
        npm_mods = [n for n in inventory if npm.is_npm_module(n)]
        LOG.info("fetching npm profiles for %d npm modules…", len(npm_mods))
        npm_profiles = npm.collect(npm_mods, cache=config.CACHE_DIR / "npm.json")
    packages = pipeline.build_packages(
        inventory, ub_versions, activity, special=special,
        pypi_profiles=pypi_profiles, npm_profiles=npm_profiles,
    )

    meta = {
        "streams": [
            {"id": s["id"], "label": s["label"], "kind": s["kind"], "source": s["source"],
             "date": s.get("date", ""), "rc": s.get("rc", False), "release": s.get("release", "")}
            for s in catalog
        ],
        "default": default,
        "baselines": ubuntu_data["meta"],
        "ubuntu_lts": slim["ubuntu_LTS"],
        "ubuntu_interim": slim["ubuntu_interim"],
        "data_date": packages[0].data_date if packages else "",
        "activity_measured": len([p for p in packages if p.activity.source == "measured"]),
        "activity_sampled": len(activity),
        "total_sources": len(packages),
    }
    _write(config.PACKAGES_CACHE, {"meta": meta, "packages": [p.to_dict() for p in packages]})
    LOG.info("WROTE %s", config.PACKAGES_CACHE)
    print(json.dumps({"streams": len(meta["streams"]), "default": default, "total": len(packages),
                      "activity_measured": meta["activity_measured"]}, ensure_ascii=False, indent=2))


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
