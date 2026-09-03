"""A–D activity grading from a rolling 12-month activity series.

Design: docs/scoring-v2.md D1–D3. Pipeline:

1. normalise each monthly bucket into a per-month composite value
   (commits + 1.5·prs + 0.5·issues),
2. apply an exponential recency decay and take a weighted mean over the
   1/3/6/12-month rolling windows,
3. map the composite through a *log* scale (`log1p`) — distro repos are
   healthy at 0.5–2 monthly units (version syncs + CVE patches), a linear
   scale graded them all D,
4. apply event floors: a repo with a recent last-commit is alive regardless
   of volume (Debian MIA / Fedora responsiveness logic),
5. map the index into the A/B/C/D bands from the rules.

When no measured monthly series exists the grade falls back to a
data-driven proxy from point-in-time signals (last commit / open backlog)
and is labelled ``estimated`` so the UI is never ambiguous about provenance.
"""

from __future__ import annotations

import datetime as dt
import math

from app.engine.rules_loader import rules
from app.models import RepoSignals


def _month_value(bucket: dict) -> float:
    """Weighted per-month activity from a month bucket."""
    commits = bucket.get("commits", 0)
    prs = bucket.get("prs", 0)
    issues = bucket.get("issues", 0)
    # Commits and merged-PRs are strong signals; issue creation weaker
    # (it reflects user traffic, not maintainer response).
    return commits + prs * 1.5 + issues * 0.5


def _activity_index(monthly: dict[str, dict]) -> float:
    """Compute a normalised activity index in [0,1] on a log scale."""
    if not monthly:
        return 0.0
    cfg = rules().get("activity_weights", {})
    decay = float(cfg.get("month_decay", 0.92))
    windows = cfg.get("rolling_windows", {"1": 0.4, "3": 0.3, "6": 0.2, "12": 0.1})
    ref_high = float(cfg.get("ref_high", 12))
    denom = math.log1p(ref_high)

    now = dt.date.today()
    # Build a map of month string, with deltas from "now".
    by_month: dict[dt.date, float] = {}
    for key, bucket in monthly.items():
        try:
            y, m = (int(p) for p in key.split("-"))
            by_month[dt.date(y, m, 1)] = _month_value(bucket)
        except ValueError:
            continue

    def month_start(delta: int) -> dt.date:
        """Return the date of the first day of `delta` months before now."""
        y, m = now.year, now.month
        total = (y * 12 + m - 1) - delta
        ny, nm = divmod(total, 12)
        return dt.date(ny, nm + 1, 1)

    def window_score(months: int) -> float:
        total_w = 0.0
        acc = 0.0
        for delta in range(months):  # delta=0 is the current month (most recent)
            w = decay**delta
            acc += w * by_month.get(month_start(delta), 0.0)
            total_w += w
        return acc / (total_w or 1.0)

    composite = sum(float(w) * math.log1p(min(window_score(int(m)), ref_high)) / denom for m, w in windows.items())
    return min(1.0, max(0.0, composite))


def _fallback_index(signals: RepoSignals) -> float:
    """Produce a plausible index from point-in-time signals (no monthly series)."""
    idx = 0.0
    if signals.last_commit:
        last = dt.date.fromisoformat(signals.last_commit)
        days = (dt.date.today() - last).days
        # Recency: <30d active, <180d moderate, else decaying.
        idx += max(0.0, 1.0 - days / 365) * 0.6
    idx += min(1.0, (signals.closed_prs + signals.closed_issues) / 200) * 0.25
    idx += min(1.0, (signals.open_prs + signals.open_issues) / 100) * 0.15
    return min(1.0, idx)


def _event_floor(signals: RepoSignals, bands: dict[str, float]) -> float | None:
    """Index floor from last-commit recency (docs/scoring-v2.md D2)."""
    if not signals.last_commit:
        return None
    from app.utils import days_since

    days = days_since(signals.last_commit)
    if days is None:
        return None
    floors = rules().get("activity_event_floors", {"b_days": 180, "c_days": 365})
    if days <= int(floors.get("b_days", 180)):
        return float(bands.get("B", 0.30))
    if days <= int(floors.get("c_days", 365)):
        return float(bands.get("C", 0.15))
    return None


def grade(signals: RepoSignals) -> tuple[str, float | None, dict]:
    """Return (letter_grade, index, scores)."""
    bands = rules().get("activity_grade_bands", {"A": 0.45, "B": 0.30, "C": 0.15, "D": 0.0})
    scores: dict[str, object] = {}

    # Only fully measured sources get a grade; a bare last-push is displayed in
    # the table but must not be conflated with real activity health.
    if signals.source != "measured":
        scores = {"index": None, "source": "estimated", "composite": None}
        return "N/A", None, scores

    has_any_signal = bool(signals.monthly or signals.last_commit or signals.closed_prs or signals.closed_issues)
    if not has_any_signal:
        scores = {"index": None, "source": "estimated", "composite": None}
        return "N/A", None, scores

    # Point-in-time proxies are not measured monthly series: label them so the
    # "已测活跃度" filter stays honest (docs/scoring-v2.md D3).
    idx = _activity_index(signals.monthly) if signals.monthly else _fallback_index(signals)
    source = "measured" if signals.monthly else "estimated"

    # Event floors (D2): recent commits prove the package is alive.
    floor = _event_floor(signals, bands)
    if floor is not None:
        idx = max(idx, floor)

    letter = "D"
    for g, threshold in bands.items():
        if idx >= threshold:
            letter = g
            break
    scores = {"index": round(idx, 3), "source": source, "composite": round(idx, 3)}
    return letter, idx, scores
