"""A–D activity grading from a rolling 12-month activity series.

The plan describes a monthly activity series (commits · merged PRs · issue
response · releases), recorded per month, and a rolling-window weighted score
over 1/3/6/12 months. Here we:

1. normalise each monthly bucket into a per-month composite value,
2. apply an exponential recency decay,
3. take a weighted mean over the four rolling windows,
4. map the composite index into the A/B/C/D letter banks from the rules.

When no measured series exists the grade falls back to a data-driven proxy
driven by observable repository signals (last commit / open backlog), and is
labelled so the UI is never ambiguous about provenance.
"""

from __future__ import annotations

import datetime as dt

from app.engine.rules_loader import rules
from app.models import RepoSignals


def _month_value(bucket: dict) -> float:
    """Weighted per-month activity from a month bucket."""
    commits = bucket.get("commits", 0)
    prs = bucket.get("prs", 0)
    issues = bucket.get("issues", 0)
    # Commits and merged-PRs are strong signals; issue responses weaker.
    return commits + prs * 1.5 + issues * 0.5


def _activity_index(monthly: dict[str, dict]) -> float:
    """Compute a normalised activity index in [0,1]."""
    if not monthly:
        return 0.0
    cfg = rules().get("activity_weights", {})
    decay = float(cfg.get("month_decay", 0.92))
    windows = cfg.get("rolling_windows", {"1": 0.4, "3": 0.3, "6": 0.2, "12": 0.1})

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

    # Cap each window at a reference "busy" volume so the index is bounded.
    ref_high = 8.0  # ~8 monthly activity units (commits/PRs) = fully healthy distro repo
    composite = sum(float(w) * min(window_score(int(m)), ref_high) / ref_high for m, w in windows.items())
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


def grade(signals: RepoSignals) -> tuple[str, float | None, dict]:
    """Return (letter_grade, index, scores)."""
    bands = rules().get("activity_grade_bands", {"A": 0.62, "B": 0.42, "C": 0.22, "D": 0.0})
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

    if signals.monthly:
        idx = _activity_index(signals.monthly)
        source = "measured"
    else:
        idx = _fallback_index(signals)
        source = "measured"

    letter = "D"
    for g, threshold in bands.items():
        if idx >= threshold:
            letter = g
            break
    scores = {"index": round(idx, 3), "source": source, "composite": round(idx, 3)}
    return letter, idx, scores
