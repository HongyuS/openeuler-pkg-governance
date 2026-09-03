"""Disposal / obsolescence recommendations.

The plan's four actions are: **upgrade** (default, upgrade-first), **maintain**,
**merge**, **sunset**. Sunset is restricted to D-grade packages with no reverse
dependencies and no critical/key-package status. Long-unmaintained packages that
cannot yet be sunset because they still have dependents are held at *maintain*
with an explicit note, so the platform surfaces the sunset pipeline rather than
guessing destructively.
"""

from __future__ import annotations

from app.models import Governance


def recommend(
    gov: Governance,
    *,
    grade: str,
    activity_source: str,
    last_commit: str = "",
    open_issues: int = 0,
    open_prs: int = 0,
) -> Governance:
    """Compute disposal + sunset/unmaintained flags on a Governance object."""
    if grade == "N/A" or activity_source == "none":
        gov.disposal = "upgrade"
        gov.maintenance_notes.append("活跃度数据待采集；未参与日落判定。")
        return gov

    sunset_eligible = (
        grade == "D"
        and gov.reverse_deps == 0
        and not gov.critical_term
        and not gov.is_key_package
        and gov.importance != "core"
    )

    if sunset_eligible:
        gov.disposal = "sunset"
        gov.sunset_candidate = True
        gov.maintenance_notes.append("D 级活跃度 + 无反向依赖 + 非关键：建议日落（先确认无下游消费）。")
    elif grade == "D":
        gov.disposal = "maintain"
        gov.maintenance_notes.append("D 级但仍有关键性/依赖：暂不日落，需维持并上报无人维护风险。")
    else:
        gov.disposal = "upgrade"

    # Long-unupdated & unmaintained signal.
    if last_commit:
        from app.utils import days_since

        idle = days_since(last_commit) or 0
        if idle > 180 and (open_issues or open_prs):
            gov.maintenance_notes.append(
                f"最近提交 {idle} 天前，且存在 {open_issues + open_prs} 个未闭环 Issue/PR：疑似长期未更新/无人维护。"
            )
        elif idle > 365:
            gov.maintenance_notes.append(f"超过 {idle} 天无提交，未更新风险高。")

    return gov
