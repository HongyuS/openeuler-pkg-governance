"""Collect per-package activity/backlog from the public GitCode API.

openEuler source repositories live under ``src-openeuler/<pkg>`` (the spec and
patch repos). We use the public ``api.gitcode.com/api/v5`` endpoints that do not
require authentication for public repositories:

* ``/repos/{org}/{repo}/commits`` — commit dates (author time),
* ``/repos/{org}/{repo}/pulls``  — merged/closed PR backlog,
* ``/repos/{org}/{repo}/issues`` — issue backlog,

Every call is bounded and rate-limit aware so a full-repo sweep stays polite.
The resulting ``RepoSignals`` feeds the A–D activity grader.
"""

from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import time
from collections.abc import Callable
from pathlib import Path

from app import config
from app.models import RepoSignals
from app.utils import LOG, http_get, json_or_none, parse_date


def _headers() -> dict:
    h = {"Accept": "application/json"}
    if config.ACTIVITY_TOKEN:
        h["private-token"] = config.ACTIVITY_TOKEN
        h["Authorization"] = f"Bearer {config.ACTIVITY_TOKEN}"
    return h


def _get(path: str, **params) -> list | dict | None:
    url = f"{config.ACTIVITY_API_BASE}/{path}"
    for attempt in range(3):
        resp = http_get(url, headers=_headers(), params=params, timeout=config.ACTIVITY_TIMEOUT)
        if resp.status_code == 429:
            time.sleep(2 + attempt * 2)
            continue
        if resp.status_code in (401, 403, 404):
            return None
        if resp.status_code >= 500:
            time.sleep(1 + attempt)
            continue
        return json_or_none(resp)
    return None


def _month_key(iso: str) -> str:
    d = parse_date(iso)
    return d.strftime("%Y-%m") if d else ""


def _fetch_commits(org: str, repo: str) -> list[dict]:
    """Return the bounded recent commit list (≤2 pages) for speed.

    Busy repos (kernel, glibc) are almost entirely recent, so their monthly
    distribution from the first pages still captures the recency signal used for
    A–D grading. Quiet repos return a complete ≤12-month series.

    No ``since`` filter is applied on purpose: a repo whose latest commit is
    older than the 12-month grading window is *dormant* (grade D), not missing —
    filtering would return an empty list that is indistinguishable from a 404.
    Keeping stale commits also yields the true last-commit date.
    """
    commits: list[dict] = []
    page = 1
    while page <= 2:
        data = _get(f"repos/{org}/{repo}/commits", per_page=100, page=page)
        if not isinstance(data, list) or not data:
            break
        commits.extend(data)
        if len(data) < 100:
            break
        page += 1
        time.sleep(0.05)
    return commits


def _backlog_and_buckets(org: str, repo: str, kind: str) -> tuple[int, int, dict[str, int]]:
    """Return (open_count, closed_count, monthly_counts) from a state=all page."""
    data = _get(f"repos/{org}/{repo}/{kind}", state="all", per_page=100, page=1)
    if not isinstance(data, list) or not data:
        return 0, 0, {}
    open_ = sum(1 for item in data if item.get("state") not in ("closed", "merged"))
    closed = len(data) - open_
    monthly: dict[str, int] = {}
    for item in data:
        mk = _month_key(item.get("created_at", ""))
        if mk:
            monthly[mk] = monthly.get(mk, 0) + 1
    # If the page was full, the totals are at least 100 each side, but for a
    # bounded estimate we keep the observed values (closure is a heuristic).
    return open_, closed, monthly


def fetch_activity(pkg: str, *, org: str | None = None, repo: str | None = None) -> RepoSignals:
    """Fetch activity signals for one source package.

    ``repo`` overrides the GitCode repo name for packages whose source repo is
    named differently (resolved from the org listing by the caller). Tries
    ``src-openeuler`` then ``openeuler``. Returns a fully populated
    ``RepoSignals``, with ``source`` reflecting data quality. PR/issue backlog
    is only fetched for repos with commits in the last 12 months — dormant
    repos skip the extra calls (their grade is D regardless).
    """
    org = org or config.ACTIVITY_ORG
    repo = repo or pkg
    signals = RepoSignals()

    commits = _fetch_commits(org, repo)
    if not commits:
        alt_org = "openeuler" if org != "openeuler" else "src-openeuler"
        alt_commits = _fetch_commits(alt_org, repo)
        if alt_commits:
            org = alt_org
            commits = alt_commits
        else:
            signals.source = "none"
            return signals

    signals.repo = f"{org}/{repo}"
    signals.source = "measured"
    monthly: dict[str, dict[str, int]] = {}
    commit_dates: list[dt.date] = []
    for c in commits:
        committed = c.get("commit", {}).get("author", {}).get("date", "")
        d = parse_date(committed)
        if not d:
            continue
        commit_dates.append(d)
        m = monthly.setdefault(d.strftime("%Y-%m"), {"commits": 0, "prs": 0, "issues": 0})
        m["commits"] += 1
    signals.monthly = monthly
    if commit_dates:
        signals.last_commit = max(commit_dates).isoformat()

    active_cutoff = dt.date.today() - dt.timedelta(days=365)
    if not any(d >= active_cutoff for d in commit_dates):
        return signals

    try:
        open_prs, closed_prs, prs_monthly = _backlog_and_buckets(org, repo, "pulls")
        signals.closed_prs = closed_prs
        signals.open_prs = open_prs
        for mk, n in prs_monthly.items():
            m = monthly.setdefault(mk, {"commits": 0, "prs": 0, "issues": 0})
            m["prs"] += n
    except Exception:  # ruff: ignore[blind-except]
        pass
    try:
        open_issues, closed_issues, iss_monthly = _backlog_and_buckets(org, repo, "issues")
        signals.closed_issues = closed_issues
        signals.open_issues = open_issues
        for mk, n in iss_monthly.items():
            m = monthly.setdefault(mk, {"commits": 0, "prs": 0, "issues": 0})
            m["issues"] += n
    except Exception:  # ruff: ignore[blind-except]
        pass
    signals.monthly = monthly
    return signals


def collect_many(
    packages: list[str],
    *,
    limit: int = 0,
    cache: Path | None = None,
    resolve: Callable[[str], str | None] | None = None,
) -> dict[str, RepoSignals]:
    """Collect activity for many packages with bounded concurrency + cache.

    ``resolve`` maps a package name to its GitCode repo name when the two
    differ (see :func:`app.collectors.repos.build_resolver`); packages the
    resolver cannot map fall back to using their own name.
    """
    cache = cache or (config.CACHE_DIR / "activity.json")
    cached: dict[str, RepoSignals] = {}
    if cache.exists():
        try:
            raw = json.loads(cache.read_text())
            for name, sig in raw.items():
                # Treat transient "no data" entries as not cached so they can be
                # retried on the next run.
                if sig.get("source") != "none" or sig.get("monthly") or sig.get("last_commit"):
                    cached[name] = RepoSignals(**sig)
        except Exception:  # ruff: ignore[blind-except]
            cached = {}

    todo = [p for p in packages if p not in cached]
    if limit:
        todo = todo[:limit]
    LOG.info("activity: %d cached, collecting %d packages", len(cached), len(todo))

    results: dict[str, RepoSignals] = {}
    done = 0

    def _worker(pkg: str) -> tuple[str, RepoSignals]:
        try:
            repo = resolve(pkg) if resolve else None
            return pkg, fetch_activity(pkg, repo=repo)
        except Exception as exc:  # ruff: ignore[blind-except]
            LOG.warning("activity failed for %s: %s", pkg, exc)
            return pkg, RepoSignals(source="none")

    with cf.ThreadPoolExecutor(max_workers=max(1, config.ACTIVITY_CONCURRENCY)) as ex:
        futures = {ex.submit(_worker, p): p for p in todo}
        for fut in cf.as_completed(futures):
            name, sig = fut.result()
            results[name] = sig
            cached[name] = sig
            done += 1
            if done % 200 == 0:
                _write_cache(cache, cached)
                LOG.info("activity: %d/%d done", done, len(todo))
            elif len(cached) % 25 == 0:
                _write_cache(cache, cached)

    _write_cache(cache, cached)
    return {name: cached[name] for name in packages if name in cached}


def _write_cache(cache: Path, data: dict) -> None:
    cache.parent.mkdir(parents=True, exist_ok=True)
    serialisable = {k: dict(v.__dict__.items()) for k, v in data.items()}
    cache.write_text(json.dumps(serialisable, ensure_ascii=False, indent=2), encoding="utf-8")
