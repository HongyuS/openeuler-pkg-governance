"""Re-runnable collection job shared by the CLI and the web UI.

`run_build` performs the whole public-API collection + governance pass and
rewrites ``packages.json``. Scopes let the UI offer a fast online refresh
without forcing a full multi-minute sweep:

* ``quick``  — re-discover the stream catalogue (new RC / daily builds), re-pull
  the **default pair's** package metadata (picking up ``update`` repos and new
  packages), refresh the Ubuntu baseline, and rebuild. Reuses the cached
  activity / PyPI / npm / ISO / SIG data.
* ``full``   — everything in ``quick`` plus every selectable stream's version
  matrix and a forced re-collection of activity, PyPI, npm, oemaker and SIG.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app import config
from app.collectors import gitcode, npm, oemaker, openeuler, pypi, repos, sig, ubuntu
from app.engine import pipeline
from app.utils import LOG

Progress = Callable[[str, int, str], None]


def _noop(step: str, pct: int, message: str) -> None:  # pragma: no cover - default
    LOG.info("[%s%%] %s — %s", pct, step, message)


def pick_activity_targets(inventory: dict[str, dict], limit: int) -> list[str]:
    """Priority-ordered activity targets: P0/P1/special first, then the rest."""
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


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_build(
    scope: str = "quick",
    *,
    activity_limit: int | None = None,
    progress: Progress | None = None,
) -> dict:
    """Collect from the live public APIs and rewrite the dataset.

    Returns the ``meta`` block that was written into ``packages.json``.
    """
    emit = progress or _noop
    full = scope == "full"
    limit = config.ACTIVITY_SAMPLE_LIMIT if activity_limit is None else activity_limit

    emit("catalogue", 2, "发现最新 LTS / 创新版 / DevStation RC 与每日构建…")
    catalog = openeuler.stream_catalog()
    default = openeuler.discover_latest()
    LOG.info("stream catalogue: %d streams; default pair %s", len(catalog), default)

    # 1) Per-stream version matrix. `quick` forces the default pair (the streams
    #    actually on screen) and picks up any newly discovered stream; `full`
    #    forces every stream.
    sv_cache = config.STREAM_VERSIONS_CACHE
    stream_versions: dict[str, dict[str, dict]] = {}
    if sv_cache.exists():
        try:
            stream_versions = json.loads(sv_cache.read_text(encoding="utf-8"))
        except Exception:  # ruff: ignore[blind-except]
            stream_versions = {}
    force_ids = {s["id"] for s in catalog} if full else set(default.values())
    for idx, s in enumerate(catalog):
        sid = s["id"]
        cached = stream_versions.get(sid) or {}
        # Entries must carry the in_os tag (added 2026-09); older caches are
        # re-collected so per-stream ISO tags stay consistent.
        cache_ok = bool(cached) and all(isinstance(v, dict) and "in_os" in v for v in cached.values())
        if cache_ok and sid not in force_ids:
            continue
        emit("streams", 5 + int(35 * idx / max(1, len(catalog))), f"采集流版本：{sid}")
        LOG.info("collecting stream versions for %s …", sid)
        try:
            stream_versions[sid] = openeuler.collect_stream_versions(sid)
        except Exception as exc:  # ruff: ignore[blind-except]
            LOG.warning("stream %s failed: %s", sid, exc)
            if not cached:
                stream_versions[sid] = {}

    # 2) Canonical (default-pair) full inventory for the governance graph.
    emit("inventory", 45, "聚合 OS / everything / EPOL / debuginfo / source / update…")
    LOG.info("collecting canonical openEuler inventory (dependency graph)…")
    inventory = openeuler.collect(default)
    LOG.info("canonical inventory: %d source packages", len(inventory))
    _write(config.CACHE_DIR / "inventory.json", {"streams": default, "packages": inventory})

    # 3) ISO composition lists (oemaker) — per stream, merged into the matrix.
    emit("iso", 55, "解析官方 ISO 组成清单（oemaker）…")
    iso_tags: dict[str, dict] = {}
    stream_tags: dict[str, dict] = {}
    try:
        iso_data = oemaker.collect([s["id"] for s in catalog], force=full)
        iso_tags = iso_data.get("tags", {})
        stream_tags = iso_data.get("stream_tags", {})
    except Exception as exc:  # ruff: ignore[blind-except]
        LOG.warning("oemaker collection failed: %s", exc)
    for sid, recs in stream_versions.items():
        stags = stream_tags.get(sid, {})
        for sname, rec in recs.items():
            if not isinstance(rec, dict):
                continue
            flags = stags.get(sname, {})
            rec["in_iso"] = bool(rec.get("in_os")) or bool(flags.get("devstation"))
            if flags:
                rec["iso_baseline"] = bool(flags.get("baseline"))
                rec["iso_excluded"] = bool(flags.get("excluded"))
                rec["iso_desktop"] = bool(flags.get("desktop"))
                rec["iso_edge"] = bool(flags.get("edge"))
    sv_cache.parent.mkdir(parents=True, exist_ok=True)
    sv_cache.write_text(json.dumps(stream_versions, ensure_ascii=False), encoding="utf-8")

    # 4) SIG ownership map.
    emit("sig", 60, "解析 SIG 归属（community repo）…")
    sig_map: dict[str, list[str]] = {}
    sigs_meta: dict[str, dict] = {}
    try:
        sig_data = sig.collect(force=full)
        sig_map = sig_data.get("pkg_sig", {})
        sigs_meta = sig_data.get("sigs", {})
    except Exception as exc:  # ruff: ignore[blind-except]
        LOG.warning("sig collection failed: %s", exc)

    # 5) Ubuntu baseline.
    emit("ubuntu", 65, "刷新 Ubuntu LTS / 前沿基线…")
    ubuntu_data = ubuntu.collect(force=True)
    ub_versions = ubuntu_data["versions"]
    slim = {
        "ubuntu_LTS": {k: v for k, v in ub_versions.get("ubuntu_LTS", {}).items() if k in inventory},
        "ubuntu_interim": {k: v for k, v in ub_versions.get("ubuntu_interim", {}).items() if k in inventory},
    }

    # 6) Activity (measured grades). Reuses the cache unless scope=full.
    emit("activity", 70, "采集仓库活跃度 / 待办…")
    targets = pick_activity_targets(inventory, limit)
    resolver = repos.build_resolver(list(inventory.keys()))
    activity = gitcode.collect_many(targets, cache=config.ACTIVITY_CACHE, resolve=resolver, force=full)
    LOG.info("activity collected for %d packages", len(activity))

    # 7) Ecosystem registry profiles.
    rules = __import__("app").engine.rules_loader.rules()
    special = {s["name"]: s["note"] for s in rules.get("special_packages", [])}
    emit("registry", 80, "刷新 PyPI / npm 上游画像…")
    pip_mods = [n for n in inventory if pypi.is_pip_module(n)]
    npm_mods = [n for n in inventory if npm.is_npm_module(n)]
    pypi_profiles = pypi.collect(pip_mods, cache=config.CACHE_DIR / "pypi.json", force=full)
    npm_profiles = npm.collect(npm_mods, cache=config.CACHE_DIR / "npm.json", force=full)

    # 8) Governance pipeline.
    emit("pipeline", 90, "运行治理引擎…")
    packages = pipeline.build_packages(
        inventory,
        ub_versions,
        activity,
        special=special,
        pypi_profiles=pypi_profiles,
        npm_profiles=npm_profiles,
        iso_tags=iso_tags,
        iso_protection=bool(rules.get("sunset_protection", {}).get("iso_baseline", False)),
        sig_map=sig_map,
    )

    meta: dict[str, Any] = {
        "streams": [
            {
                "id": s["id"],
                "label": s["label"],
                "kind": s["kind"],
                "source": s["source"],
                "date": s.get("date", ""),
                "rc": s.get("rc", False),
                "release": s.get("release", ""),
            }
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
        "sigs": sigs_meta,
        "scope": scope,
    }
    _write(config.PACKAGES_CACHE, {"meta": meta, "packages": [p.to_dict() for p in packages]})
    emit("done", 100, f"完成：{len(packages)} 个源包")
    LOG.info("WROTE %s", config.PACKAGES_CACHE)
    return meta
