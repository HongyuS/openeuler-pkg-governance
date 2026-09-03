"""Shared helpers: version handling, HTTP, date parsing."""

from __future__ import annotations

import datetime as dt
import functools
import logging
import re
from typing import Any

import requests

LOG = logging.getLogger("pkg.gov")


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging with a timestamped console format."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


@functools.lru_cache(maxsize=512)
def parse_version(version: str) -> tuple:
    """Split an RPM/Epoch version into a sortable tuple.

    Handles `epoch:version-release` and strips common source suffixes so that
    e.g. `1.2.3.oe2403` and `1.2.3.oe2503` compare correctly on the upstream
    portion. Kept deliberately conservative (never raises).
    """
    if not version:
        return (0, (), ())
    v = str(version).strip()
    epoch = 0
    rest = v
    if ":" in v:
        maybe_epoch, rest = v.split(":", 1)
        try:
            epoch = int(maybe_epoch)
        except ValueError:
            rest = v

    match = re.match(r"^(?P<ver>[\w.~+\-]+?)(?:-(?P<rel>[\w.~+\-]+))?$", rest)
    if match:
        ver = match.group("ver")
        rel = match.group("rel") or ""
    else:
        ver, rel = rest, ""

    def _tok(part: str) -> tuple:
        # Split into numeric and alpha tokens; numeric compare numerically.
        tokens = re.split(r"([0-9]+|[A-Za-z]+)", part)
        out: list[tuple[int, str | int]] = []
        for t in tokens:
            if not t:
                continue
            if t.isdigit():
                out.append((0, int(t)))
            else:
                # tilde sorts before any real token
                out.append((1, t.lower()))
        return tuple(out)

    return (epoch, _tok(ver), _tok(rel))


def version_compare(a: str, b: str) -> int:
    """Return -1/0/1 if a is <, ==, > b (never raises)."""
    try:
        pa, pb = parse_version(a), parse_version(b)
    except Exception:  # ruff: ignore[blind-except]
        return (a > b) - (a < b)
    return (pa > pb) - (pa < pb)


def compare_versions_str(a: str, b: str) -> int:
    """Alias used by external callers (returns -1/0/1)."""
    return version_compare(a, b)


def upstream_version(version: str) -> str:
    """Return only the epoch:version portion (upstream).

    Dropping the distro release suffix so cross-distribution comparisons are meaningful.
    """
    if not version:
        return ""
    text = str(version).strip()
    if ":" in text:
        epoch, rest = text.split(":", 1)
    else:
        epoch, rest = "0", text
    # Drop the release (everything after the last '-' in the upstream portion).
    upstream = rest.split("-")[0] if "-" in rest else rest
    return f"{epoch}:{upstream}"


def compare_upstream(a: str, b: str) -> int:
    """Cross-distribution upstream compare (-1/0/1)."""
    if not a and not b:
        return 0
    if not a:
        return -1
    if not b:
        return 1
    try:
        pa = parse_version(upstream_version(a))
        pb = parse_version(upstream_version(b))
    except Exception:  # ruff: ignore[blind-except]
        return (a > b) - (a < b)
    return (pa[:2] > pb[:2]) - (pa[:2] < pb[:2])


def strip_source_suffix(version: str) -> str:
    """Return the upstream version before the last `.oe*` / distro suffix."""
    if not version:
        return ""
    return re.sub(r"(\.oe[0-9]+.*|\.el[0-9]+.*|\.fc[0-9]+.*)$", "", version)


def iso_today() -> str:
    """Return today's date as an ISO-8601 string."""
    return dt.date.today().isoformat()


def parse_date(value: str) -> dt.date | None:
    """Parse a variety of date formats into a date, or None."""
    if not value:
        return None
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    text = text.replace("Z", "").split("T")[0]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y.%m.%d", "%Y-%m", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()  # ruff: ignore[call-datetime-strptime-without-zone] — 刻意取 naive date，日期粒度无时区语义
        except ValueError:
            continue
    return None


def days_between(later: str, earlier: str) -> int | None:
    """Return the day difference between two parseable dates, or None."""
    a, b = parse_date(later), parse_date(earlier)
    if a and b:
        return (a - b).days
    return None


def days_since(value: str, ref: str | None = None) -> int | None:
    """Return days elapsed since ``value`` up to ``ref`` (default today), or None."""
    ref = ref or iso_today()
    return days_between(ref, value)


def http_get(
    url: str, *, headers: dict | None = None, timeout: float = 20, params: dict | None = None
) -> requests.Response:
    """GET with retry-once and a small backoff for transient 429/5xx."""
    hdrs = {"User-Agent": "pkg-governance/1.0", **(headers or {})}
    last_exc: Exception | None = None
    for attempt in (0, 1):
        try:
            resp = requests.get(url, headers=hdrs, timeout=timeout, params=params)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                import time

                time.sleep(1.0 + attempt)
                continue
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == 0:
                import time

                time.sleep(0.5)
                continue
        else:
            return resp
    if last_exc:
        raise last_exc
    return requests.Response()


def json_or_none(resp: requests.Response, *, limit: int = 0) -> Any:
    """Return the response JSON (lists trimmed to ``limit``), or None on parse failure."""
    try:
        data = resp.json()
    except Exception:  # ruff: ignore[blind-except]
        return None
    if limit and isinstance(data, list):
        return data[:limit]
    return data
