"""Bulk source-repo metadata from the public GitCode org listing.

Most openEuler source packages map 1:1 to a repo in the ``src-openeuler`` org
(``src-openeuler/<source>``). Paginating ``/orgs/{org}/repos`` is far cheaper
than one ``/commits`` call per package and yields the full repo-name inventory
used to resolve packages whose repo is named differently (``java-17-openjdk`` →
``openjdk-17``, ``rust-afterburn`` → ``afterburn``, case drift, …).

``pushed_at`` from the listing is *not* used as a last-commit proxy: during the
Gitee→GitCode migration ~80% of repos were bulk-pushed on a handful of dates,
so it reflects migration events, not real activity.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from app import config
from app.utils import LOG, http_get, json_or_none


def collect_org_push(org: str = "src-openeuler", *, max_pages: int = 120, cache: Path | None = None) -> dict[str, str]:
    """Return {repo_name: pushed_at} for a GitCode org (paginated, cached)."""
    cache = cache or (config.CACHE_DIR / f"repo_push_{org}.json")
    result: dict[str, str] = {}
    if cache.exists():
        try:
            result = json.loads(cache.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            result = {}
    if result:
        LOG.info("org %s: %d repos in listing cache", org, len(result))
        return result
    page = 1
    while page <= max_pages:
        data = json_or_none(http_get(
            f"{config.ACTIVITY_API_BASE}/orgs/{org}/repos",
            params={"per_page": 100, "page": page},
            timeout=25,
        ))
        if not isinstance(data, list) or not data:
            break
        for r in data:
            name = r.get("name") or r.get("path")
            pushed = r.get("pushed_at") or ""
            if name and pushed:
                result[name] = pushed[:10]
        if len(data) < 100:
            break
        page += 1
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, ensure_ascii=False))
    LOG.info("org %s: %d repos with pushed_at", org, len(result))
    return result


def build_resolver(packages: list[str]) -> Callable[[str], str | None]:
    """Return resolver(pkg) -> repo name for packages whose GitCode repo name
    differs from the source-package name.

    Resolution chain (first hit wins):
      1. exact name,
      2. case-insensitive name (repodata vs. repo casing drift),
      3. known renames: ``java-X-openjdk`` → ``openjdk-X``, ``c++`` → ``cpp``,
         ``rust-`` prefix strip, ``python-`` prefix strip, ``_`` → ``-``.

    Rule-based candidates are only accepted when the candidate repo is not the
    name of another inventory package (that repo belongs to the exact match).
    Unresolved packages return ``None`` and fall back to their own name.
    """
    src_org = collect_org_push("src-openeuler")
    oe_org = collect_org_push("openeuler")
    repos = {**oe_org, **src_org}  # src-openeuler wins on collision
    lower_repos = {k.lower(): k for k in repos}
    pkg_names = set(packages)
    pkg_lower = {p.lower() for p in packages}
    memo: dict[str, str | None] = {}

    def _candidate(pkg: str) -> str | None:
        if pkg in repos:
            return pkg
        cased = lower_repos.get(pkg.lower())
        if cased:
            return cased
        m = re.match(r"^java-(.+)-openjdk$", pkg)
        candidates = []
        if m:
            candidates.append(f"openjdk-{m.group(1)}")
        if "c++" in pkg:
            candidates.append(pkg.replace("c++", "cpp"))
        if pkg.startswith("rust-"):
            candidates.append(pkg[5:])
        if pkg.startswith("python-"):
            candidates.append(pkg[7:])
        if "_" in pkg:
            candidates.append(pkg.replace("_", "-"))
        for cand in candidates:
            if cand in repos and cand not in pkg_names and cand.lower() not in pkg_lower:
                return cand
        return None

    def resolve(pkg: str) -> str | None:
        if pkg not in memo:
            memo[pkg] = _candidate(pkg)
            if memo[pkg] and memo[pkg] != pkg:
                LOG.info("repo resolved: %s -> %s", pkg, memo[pkg])
        return memo[pkg]

    return resolve
