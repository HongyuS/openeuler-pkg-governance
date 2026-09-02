"""Python Package Index profiles for vendored ``python-*`` modules.

openEuler packages third-party Python modules as source packages named
``python-<name>`` (e.g. ``python-requests``). Each corresponds to a PyPI project.
Sunsetting such a package is genuinely tricky: whether a module can be dropped
depends on (a) whether its PyPI upstream is still maintained, (b) whether the
installed system Python satisfies the module's ``Requires-Python``, and (c) how
many other openEuler packages still depend on it. This collector gathers the
upstream signals (latest release, last release date, ``Requires-Python``).
"""

from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import re
from pathlib import Path

from app import config
from app.utils import LOG, http_get, json_or_none

PIP_NAME_RE = re.compile(r"^python([-_])(?P<name>[a-zA-Z0-9].*)$")


def is_pip_module(source: str) -> bool:
    """Is this source a vendored pip module (vs. the system Python runtime)?"""
    if not source.startswith("python"):
        return False
    # python3 / python3-libs / libpython* are the system runtime, not pip modules.
    if re.match(r"^python3", source) or source.startswith("libpython"):
        return False
    m = PIP_NAME_RE.match(source)
    return bool(m)


def pypi_project_name(source: str) -> list[str]:
    """Candidate PyPI project names for a source (order of preference)."""
    m = PIP_NAME_RE.match(source)
    if not m:
        return []
    stripped = m.group("name")
    # Most `python-<x>` map to PyPI `<x>` (requests -> requests), but a handful
    # are published under the full `python-<x>` name (python-dateutil).
    return [stripped, source]


def fetch_profile(source: str) -> dict:
    """Return the PyPI profile for a pip-module source ({} if not found)."""
    results: list[dict] = []
    for project in pypi_project_name(source):
        url = f"https://pypi.org/pypi/{project}/json"
        try:
            data = json_or_none(http_get(url, timeout=20))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("pypi fetch failed for %s: %s", project, exc)
            continue
        if not data:
            continue
        info = data.get("info", {})
        latest = info.get("version", "")
        release_dates: list[dt.date] = []
        for files in data.get("releases", {}).values():
            if files:
                d = files[0].get("upload_time", "")
                try:
                    release_dates.append(dt.date.fromisoformat(d[:10]))
                except ValueError:
                    pass
        last_release = max(release_dates).isoformat() if release_dates else ""
        days = (
            (dt.date.today() - dt.date.fromisoformat(last_release)).days if last_release else None
        )
        results.append(
            {
                "pypi_name": project,
                "pypi_latest": latest,
                "pypi_last_release": last_release,
                "pypi_days_since_release": days,
                "pypi_requires_python": info.get("requires_python", ""),
                "pypi_stale": bool(days is not None and days > 730),
                "pypi_source": source,
                "_releases": len(release_dates),
            }
        )
    # Prefer the candidate that actually resolves to a real, released project.
    best = next((r for r in results if r["pypi_latest"]), None) or (results[0] if results else None)
    if not best:
        return {
            "pypi_name": source,
            "pypi_source": source,
            "pypi_stale": False,
            "pypi_latest": "",
            "pypi_last_release": "",
            "pypi_days_since_release": None,
            "pypi_requires_python": "",
        }
    best.pop("_releases", None)
    return best


def collect(packages: list[str], *, cache: Path | None = None) -> dict[str, dict]:
    """Fetch PyPI profiles for pip modules, caching results to disk."""
    cache = cache or (config.CACHE_DIR / "pypi.json")
    cached: dict[str, dict] = {}
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cached = {}
    todo = [p for p in packages if p not in cached]
    LOG.info("pypi: %d cached, fetching %d pip modules", len(cached), len(todo))

    def _w(p: str) -> tuple[str, dict]:
        try:
            return p, fetch_profile(p)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("pypi %s failed: %s", p, exc)
            return p, {"pypi_name": p, "pypi_stale": False}

    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for p, prof in ex.map(_w, todo):
            cached[p] = prof

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(cached, ensure_ascii=False, indent=2))
    return cached
