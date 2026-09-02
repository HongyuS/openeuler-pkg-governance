"""npm registry profiles for vendored ``nodejs-*`` modules.

openEuler packages third-party Node.js modules as source packages named
``nodejs-<name>`` (e.g. ``nodejs-chalk``). Each corresponds to an npm package.
This collector gathers the upstream signals (latest release, last release date,
deprecation) used by the governance engine: an npm module whose upstream is
stale or deprecated is a stronger sunset candidate than a maintained one.
"""

from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import quote

from app import config
from app.utils import LOG, http_get, json_or_none

NPM_NAME_RE = re.compile(r"^nodejs-(?P<name>[a-zA-Z0-9@._].*)$")


def is_npm_module(source: str) -> bool:
    """Is this source a vendored npm module (vs. the Node.js toolchain)?"""
    return bool(NPM_NAME_RE.match(source))


def npm_project_name(source: str) -> list[str]:
    """Candidate npm package names for a source (order of preference)."""
    m = NPM_NAME_RE.match(source)
    if not m:
        return []
    stripped = m.group("name")
    # Most `nodejs-<x>` map to npm `<x>` (chalk -> chalk), but a handful are
    # published under the full `nodejs-<x>` name.
    return [stripped, source]


def fetch_profile(source: str) -> dict:
    """Return the npm profile for an npm-module source ({} if not found)."""
    results: list[dict] = []
    for project in npm_project_name(source):
        url = f"https://registry.npmjs.org/{quote(project, safe='@')}"
        try:
            data = json_or_none(http_get(url, timeout=20))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("npm fetch failed for %s: %s", project, exc)
            continue
        if not data or data.get("error"):
            continue
        latest = data.get("dist-tags", {}).get("latest", "")
        release_dates: list[dt.date] = []
        for ver, ts in data.get("time", {}).items():
            if ver in ("created", "modified"):
                continue
            try:
                release_dates.append(dt.date.fromisoformat(str(ts)[:10]))
            except ValueError:
                pass
        last_release = max(release_dates).isoformat() if release_dates else ""
        days = (
            (dt.date.today() - dt.date.fromisoformat(last_release)).days if last_release else None
        )
        latest_meta = data.get("versions", {}).get(latest, {}) if latest else {}
        results.append(
            {
                "npm_name": project,
                "npm_latest": latest,
                "npm_last_release": last_release,
                "npm_days_since_release": days,
                "npm_deprecated": bool(latest_meta.get("deprecated")),
                "npm_stale": bool(days is not None and days > 730),
                "npm_source": source,
                "_releases": len(release_dates),
            }
        )
    # Prefer the candidate that actually resolves to a real, released package.
    best = next((r for r in results if r["npm_latest"]), None) or (results[0] if results else None)
    if not best:
        return {
            "npm_name": source,
            "npm_source": source,
            "npm_stale": False,
            "npm_latest": "",
            "npm_last_release": "",
            "npm_days_since_release": None,
            "npm_deprecated": False,
        }
    best.pop("_releases", None)
    return best


def collect(packages: list[str], *, cache: Path | None = None) -> dict[str, dict]:
    """Fetch npm profiles for npm modules, caching results to disk."""
    cache = cache or (config.CACHE_DIR / "npm.json")
    cached: dict[str, dict] = {}
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cached = {}
    todo = [p for p in packages if p not in cached]
    LOG.info("npm: %d cached, fetching %d npm modules", len(cached), len(todo))

    def _w(p: str) -> tuple[str, dict]:
        try:
            return p, fetch_profile(p)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("npm %s failed: %s", p, exc)
            return p, {"npm_name": p, "npm_stale": False}

    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for p, prof in ex.map(_w, todo):
            cached[p] = prof

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(cached, ensure_ascii=False, indent=2))
    return cached
