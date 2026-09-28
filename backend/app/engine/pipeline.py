"""Assemble source-package portraits from collectors + classifiers."""

from __future__ import annotations

from app.engine import compare, disposal, effort, grading, importance, nodejs_gov, python_gov
from app.engine.rules_loader import rules
from app.models import Governance, Package, RepoSignals
from app.utils import iso_today


def _priority_score(gov: Governance, *, lag_degree: str, backport: bool) -> float:
    """Composite governance priority score (docs/scoring-v2.md D4–D6).

    P-level base (P0=4/P1=2.5/P2=1) + lag bonus graded by ``lag_degree``
    (halved when the package is actively backported via update/EPOL) +
    maintenance risk (activity D/C). Sunset candidates already imply a D
    grade, so their extra term is a small overlap (+0.5), not a full sum.
    """
    base = {"P0": 4.0, "P1": 2.5, "P2": 1.0}.get(gov.p_level, 1.0)
    cfg = rules().get("lag_bonus", {})
    lag = float(cfg.get(lag_degree, 0.0)) if lag_degree else 0.0
    if lag and backport:
        lag *= float(cfg.get("backport_relief", 0.5))
    risk = 1.5 if gov.activity_grade == "D" else 0.75 if gov.activity_grade == "C" else 0.0
    if gov.sunset_candidate:
        risk += 0.5
    return round(min(10.0, base + lag + risk), 2)


def build_packages(
    inventory: dict[str, dict],
    baselines: dict[str, dict],
    activity: dict[str, RepoSignals],
    *,
    special: dict[str, str] | None = None,
    data_date: str = "",
    pypi_profiles: dict[str, dict] | None = None,
    npm_profiles: dict[str, dict] | None = None,
    iso_tags: dict[str, dict] | None = None,
    iso_protection: bool = False,
    sig_map: dict[str, list[str]] | None = None,
) -> list[Package]:
    """Produce the full list of Package portraits (already governance-scored).

    ``iso_tags`` maps source name -> {"baseline"/"excluded"/"devstation": bool}
    from the oemaker ISO composition lists. ``iso_protection`` keeps ISO
    packages out of the sunset recommendation (they must exit via the official
    release-management branch process instead). ``sig_map`` maps source name ->
    owning SIG name(s) from the community repo; the first SIG wins.
    """
    special = special or {}
    pypi_profiles = pypi_profiles or {}
    npm_profiles = npm_profiles or {}
    iso_tags = iso_tags or {}
    sig_map = sig_map or {}
    data_date = data_date or iso_today()
    sys_python = python_gov.system_python_version(inventory)

    # Base-ISO comps membership feeds the P1 derivation (docs/scoring-v2.md D8).
    iso_baseline = {name for name, tags in iso_tags.items() if tags.get("baseline")}
    classifications = importance.classify(inventory, iso_baseline=iso_baseline)
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
                "build_reverse_deps": 0,
                "build_dependents": [],
            },
        )
        signals = activity.get(name, RepoSignals(source="none"))
        comp = compare.build_comparison(name, rec.get("versions", {}), baselines)
        letter, _idx, scores = grading.grade(signals)

        gov = Governance(
            importance=cls["importance"],
            p_level=cls["p_level"],
            is_key_package=cls["is_key_package"],
            critical_term=cls["critical_term"],
            reverse_deps=cls["reverse_deps"],
            dependents=cls["dependents"],
            build_reverse_deps=cls.get("build_reverse_deps", 0),
            build_dependents=cls.get("build_dependents", []),
            activity_grade=letter,
            activity_scores=scores,
            activity_source=scores.get("source", "estimated"),
        )
        # Sunset logic.
        gov = disposal.recommend(
            gov,
            grade=letter,
            activity_source=gov.activity_source,
            last_commit=signals.last_commit,
            open_issues=signals.open_issues,
            open_prs=signals.open_prs,
        )
        # Effort.
        gov = effort.estimate(gov)
        # Actively backported = carries updates in the update/EPOL repos
        # (backport model, docs/scoring-v2.md D5).
        backport = bool(rec.get("in_update") or rec.get("in_epol"))
        gov.score = _priority_score(gov, lag_degree=comp.lag_degree, backport=backport)

        special_note = special.get(name, "")
        tags = iso_tags.get(name, {})
        owners = sig_map.get(name, [])
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
            build_requires=rec.get("build_requires", []),
            in_epol=rec.get("in_epol", False),
            in_update=rec.get("in_update", False),
            latest_repo=rec.get("latest_repo", ""),
            sig=owners[0] if owners else "",
            in_iso=bool(rec.get("in_os", False)) or bool(tags.get("devstation", False)),
            iso_baseline=bool(tags.get("baseline", False)),
            iso_excluded=bool(tags.get("excluded", False)),
            iso_desktop=bool(tags.get("desktop", False)),
            iso_edge=bool(tags.get("edge", False)),
            activity=signals,
            comparison=comp,
            governance=gov,
            special=bool(special_note),
            special_note=special_note,
            data_date=data_date,
        )
        pkg = python_gov.apply_python(pkg, pypi_profiles, sys_python, system_set)
        pkg = nodejs_gov.apply_nodejs(pkg, system_set, npm_profiles)
        # ISO protection overrides any sunset recommendation (structural, pip
        # or npm module): base-ISO components are officially delivered, so
        # their removal must go through release-management, not auto-sunset.
        if iso_protection and pkg.in_iso and pkg.governance.sunset_candidate:
            gov = pkg.governance
            gov.disposal = "maintain"
            gov.sunset_candidate = False
            gov.maintenance_notes.append(
                "Offline Standard ISO（基础安装 ISO）内置：官方交付组件，保留；"
                "退出需走 release-management 版本分支变更流程。"
            )
            gov.score = _priority_score(gov, lag_degree=comp.lag_degree, backport=backport)
        packages.append(pkg)
    return packages
