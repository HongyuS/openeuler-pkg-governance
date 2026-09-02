"""Assemble source-package portraits from collectors + classifiers."""

from __future__ import annotations

from app.engine import compare, disposal, effort, grading, importance, nodejs_gov, python_gov
from app.models import Governance, Package, RepoSignals
from app.utils import iso_today


def _priority_score(gov: Governance, lagging: bool) -> float:
    base = {"P0": 4.0, "P1": 2.5, "P2": 1.0}.get(gov.p_level, 1.0)
    score = base
    if lagging:
        score += 2.0
    if gov.activity_grade == "D":
        score += 1.5
    elif gov.activity_grade == "C":
        score += 0.75
    if gov.sunset_candidate:
        score += 1.0
    return round(min(10.0, score), 2)


def build_packages(
    inventory: dict[str, dict],
    baselines: dict[str, dict],
    activity: dict[str, RepoSignals],
    *,
    special: dict[str, str] | None = None,
    data_date: str = "",
    pypi_profiles: dict[str, dict] | None = None,
    npm_profiles: dict[str, dict] | None = None,
) -> list[Package]:
    """Produce the full list of Package portraits (already governance-scored)."""
    special = special or {}
    pypi_profiles = pypi_profiles or {}
    npm_profiles = npm_profiles or {}
    data_date = data_date or iso_today()
    sys_python = python_gov.system_python_version(inventory)

    classifications = importance.classify(inventory)
    # Packages whose dependency forces a language module to stay in the system
    # repo: core/key packages plus the system Python runtime closure.
    system_set = {
        name
        for name, cls in classifications.items()
        if cls["importance"] == "core" or cls["is_key_package"] or cls.get("in_python_closure")
    }
    packages: list[Package] = []
    for name, rec in inventory.items():
        cls = classifications.get(
            name,
            {
                "importance": "ordinary",
                "p_level": "P2",
                "is_key_package": False,
                "critical_term": False,
                "reverse_deps": 0,
                "dependents": [],
            },
        )
        signals = activity.get(name, RepoSignals(source="none"))
        comp = compare.build_comparison(name, rec.get("versions", {}), baselines)
        letter, idx, scores = grading.grade(signals)

        gov = Governance(
            importance=cls["importance"],
            p_level=cls["p_level"],
            is_key_package=cls["is_key_package"],
            critical_term=cls["critical_term"],
            reverse_deps=cls["reverse_deps"],
            dependents=cls["dependents"],
            activity_grade=letter,
            activity_scores=scores,
            activity_source=scores.get("source", "estimated"),
        )
        # Sunset logic.
        gov = disposal.recommend(
            gov,
            grade=letter,
            activity_source=gov.activity_source,
            lagging=comp.lagging,
            last_commit=signals.last_commit,
            open_issues=signals.open_issues,
            open_prs=signals.open_prs,
        )
        # Effort.
        gov = effort.estimate(gov)
        gov.score = _priority_score(gov, comp.lagging)

        special_note = special.get(name, "")
        pkg = Package(
            name=name,
            summary=rec.get("summary", ""),
            license=rec.get("license", ""),
            upstream=rec.get("upstream", ""),
            versions=comp.baselines,
            open_euler=rec.get("versions", {}),
            arches=rec.get("arches", []),
            groups=rec.get("groups", []),
            has_source=rec.get("has_source", False),
            has_debug=rec.get("has_debug", False),
            in_epol=rec.get("in_epol", False),
            in_update=rec.get("in_update", False),
            latest_repo=rec.get("latest_repo", ""),
            activity=signals,
            comparison=comp,
            governance=gov,
            special=bool(special_note),
            special_note=special_note,
            data_date=data_date,
        )
        pkg = python_gov.apply_python(pkg, inventory, pypi_profiles, sys_python, system_set)
        pkg = nodejs_gov.apply_nodejs(pkg, system_set, npm_profiles)
        packages.append(pkg)
    return packages
