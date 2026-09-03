"""Maintenance effort estimation (person-days / person-years per package).

The plan models per-package annual effort as::

    effort = upgrade(people-days per bump × annual bump count)
           + CVE(people-days per fix × annual CVE count)
           + routine maintenance

and gives a capacity reference by importance tier (core 0.5–1 py, important
0.1–0.3 py, ordinary 0.05–0.1 py).
"""

from __future__ import annotations

from app.engine.rules_loader import rules
from app.models import Governance


def estimate(gov: Governance) -> Governance:
    """Estimate annual maintenance effort (person-days / person-years) for a package."""
    cfg = rules().get("effort", {})
    up_min = cfg.get("upgrade_person_days_min", 3)
    up_max = cfg.get("upgrade_person_days_max", 10)
    cve_min = cfg.get("cve_person_days_min", 0.5)
    cve_max = cfg.get("cve_person_days_max", 2.0)
    routine = cfg.get("routine_person_days", 2)
    upgrades_per_year = cfg.get("upgrades_per_year", {}).get(gov.importance, 1)

    # Upgrade cost scales with complexity (reverse deps, criticality).
    complexity = 1.0 + min(1.0, gov.reverse_deps / 50.0)
    if gov.critical_term:
        complexity = max(complexity, 1.8)
    upgrade_pd = (up_min + up_max) / 2.0 * complexity

    # Annual CVE volume heuristic, weighted by importance/reverse pressure.
    cve_count = {"core": 6, "important": 3, "ordinary": 1}.get(gov.importance, 1)
    cve_pd = (cve_min + cve_max) / 2.0 * cve_count

    total_pd = round(upgrades_per_year * upgrade_pd + cve_pd + routine, 2)
    gov.effort_person_days = total_pd
    gov.effort_person_years = round(total_pd / 240.0, 3)
    return gov
