"""Domain model for a governed openEuler source package.

Every record in the platform is a *source* package portrait assembled from three
independent sources:

* openEuler release metadata (package inventory + version per release),
* activity / backlog signals (GitCode/AtomGit public API),
* downstream-distribution baselines (Ubuntu LTS and interim, optionally SUSE).

The engine then derives the governance dimensions described in the business plan:
activity grade (A-D), importance (Core/Important/Ordinary), update wave (P0/P1/P2),
version-lag vs. baselines, disposal recommendation, and maintenance effort.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RepoSignals:
    """Raw activity/backlog signals collected from the source repo API."""

    repo: str = ""
    last_commit: str = ""  # ISO date of most recent commit
    last_release: str = ""  # ISO date of most recent release/tag
    open_issues: int = 0
    open_prs: int = 0
    closed_issues: int = 0
    closed_prs: int = 0
    contributors: int = 0
    monthly: dict[str, dict[str, int]] = field(
        default_factory=dict
    )  # {YYYY-MM: {commits,prs,issues}}
    source: str = "estimated"  # "measured" | "estimated" | "none"


@dataclass
class VersionRow:
    """One distribution's version for a package (or a sentinel for absent)."""

    distro: str
    stream: str  # e.g. "openEuler_LTS", "openEuler_innovation", "ubuntu_LTS", "ubuntu_interim"
    version: str
    release_date: str = ""  # ISO date if known
    present: bool = True
    source: str = ""  # where the version was read


@dataclass
class Comparison:
    """Version-lag result against every configured baseline."""

    baselines: list[VersionRow] = field(default_factory=list)
    lagging: bool = False  # behind newest baseline
    lag_behind_ubuntu_lts: bool = False
    lag_behind_ubuntu_interim: bool = False
    latest_upstream: str = ""
    latest_upstream_source: str = ""  # which stream holds the newest version
    lag_notes: list[str] = field(default_factory=list)


@dataclass
class Governance:
    """Derived governance decisions for a package."""

    importance: str = "ordinary"  # core | important | ordinary
    p_level: str = "P2"  # P0 | P1 | P2
    is_key_package: bool = False  # in the python/essential closure
    critical_term: bool = False  # kernel/glibc/openssl/systemd type
    activity_grade: str = "N/A"  # A | B | C | D | N/A
    activity_scores: dict[str, float] = field(default_factory=dict)
    activity_source: str = "estimated"
    disposal: str = "upgrade"  # upgrade | maintain | merge | sunset
    sunset_candidate: bool = False
    reverse_deps: int = 0
    dependents: list[str] = field(default_factory=list)
    effort_person_days: float = 0.0
    effort_person_years: float = 0.0
    maintenance_notes: list[str] = field(default_factory=list)
    score: float = 0.0  # composite governance priority score


@dataclass
class Package:
    """Full portrait of one source package."""

    name: str
    summary: str = ""
    license: str = ""
    upstream: str = ""
    versions: list[VersionRow] = field(default_factory=list)
    open_euler: dict[str, str] = field(default_factory=dict)  # stream -> version
    arches: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    release_versions: list[str] = field(default_factory=list)
    # Availability across the default openEuler repositories.
    has_source: bool = False  # present in source / update-source
    has_debug: bool = False  # present in debuginfo
    in_epol: bool = False  # present in EPOL (extra packages)
    in_update: bool = False  # present in update (newest patch repo)
    latest_repo: str = ""  # repo holding the newest version
    # Official ISO composition tags.
    in_iso: bool = False  # inside the base-installation ISO (OS repo / DevStation list)
    iso_baseline: bool = False  # explicitly selected by the oemaker comps groups
    iso_excluded: bool = False  # explicitly excluded from the ISO by oemaker rpmlist
    # Python/pip assessment for pip-module source packages (python-*).
    python: dict[str, Any] = field(default_factory=dict)
    # Node.js/npm assessment for npm-module source packages (nodejs-*).
    npm: dict[str, Any] = field(default_factory=dict)
    activity: RepoSignals = field(default_factory=RepoSignals)
    comparison: Comparison = field(default_factory=Comparison)
    governance: Governance = field(default_factory=Governance)
    special: bool = False
    special_note: str = ""
    tags: list[str] = field(default_factory=list)
    data_date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "RepoSignals",
    "VersionRow",
    "Comparison",
    "Governance",
    "Package",
]
