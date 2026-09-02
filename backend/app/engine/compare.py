"""Version-lag detection: openEuler vs. downstream baselines.

For each package the *upstream* portion of the openEuler version (LTS and
innovation streams) is compared against the newest Ubuntu (and optional SUSE)
baseline. A package is flagged as **outdated** when the newest downstream
baseline carries a strictly newer upstream version.
"""

from __future__ import annotations

from app.engine.rules_loader import rules
from app.models import Comparison, VersionRow
from app.utils import compare_upstream


def _row(distro: str, stream: str, version: str, *, date: str = "", source: str = "") -> VersionRow:
    return VersionRow(
        distro=distro,
        stream=stream,
        version=version,
        release_date=date,
        present=bool(version),
        source=source,
    )


def build_comparison(
    name: str,
    open_euler_versions: dict[str, str],
    baselines: dict[str, dict],
    *,
    special_latest: str = "",
) -> Comparison:
    """Assemble the baseline version rows for one package."""
    comp = Comparison()
    rows: list[VersionRow] = []

    for stream in ("openEuler_LTS", "openEuler_innovation"):
        v = open_euler_versions.get(stream, "")
        rows.append(_row("openEuler", stream, v, source="repo"))

    for stream in ("ubuntu_LTS", "ubuntu_interim"):
        rec = baselines.get(stream, {}) or {}
        v = rec.get(name, "") if isinstance(rec, dict) else ""
        if not v:
            # Cross-distro source renames (e.g. openEuler "kernel" == Ubuntu "linux").
            aliases = rules().get("source_aliases", {})
            for alias in (aliases.get(name, ""),):
                if alias and isinstance(rec, dict):
                    v = rec.get(alias, "")
                    if v:
                        break
        rows.append(_row("ubuntu", stream, v, source="ubuntu_archive"))

    for stream in ("suse_leap", "suse_tumbleweed"):
        rec = baselines.get(stream, {}) or {}
        if rec:
            v = rec.get("versions", {}).get(name, "")
            rows.append(_row("suse", stream, v, source="opensuse"))

    if special_latest:
        rows.append(_row("upstream", "special", special_latest, source="network"))

    comp.baselines = rows
    return _compute_lag(comp)


def _newer(a: VersionRow, b: VersionRow) -> VersionRow:
    return a if compare_upstream(a.version, b.version) > 0 else b


def _compute_lag(comp: Comparison) -> Comparison:
    present = [r for r in comp.baselines if r.version]
    if not present:
        return comp

    oe_rows = [r for r in present if r.distro == "openEuler"]
    external = [r for r in present if r.distro not in ("openEuler", "upstream")]

    oe_best = (
        max(oe_rows, key=lambda r: compare_upstream(r.version, r.version) or 0) if oe_rows else None
    )
    if oe_rows:
        oe_best = oe_rows[0]
        for r in oe_rows[1:]:
            oe_best = _newer(r, oe_best)

    if external:
        newest_ext = external[0]
        for r in external[1:]:
            newest_ext = _newer(r, newest_ext)

        if oe_best and compare_upstream(newest_ext.version, oe_best.version) > 0:
            comp.lagging = True
            comp.latest_upstream = newest_ext.version
            comp.latest_upstream_source = f"{newest_ext.distro} {newest_ext.stream}"
            comp.lag_notes.append(
                f"{newest_ext.distro} {newest_ext.stream} carries {newest_ext.version} "
                f"vs openEuler {oe_best.version}."
            )

    ubuntu_lts = next((r for r in present if r.stream == "ubuntu_LTS" and r.version), None)
    ubuntu_interim = next((r for r in present if r.stream == "ubuntu_interim" and r.version), None)
    oe_lts = next((r for r in present if r.stream == "openEuler_LTS" and r.version), None)

    if ubuntu_lts and oe_lts:
        comp.lag_behind_ubuntu_lts = compare_upstream(ubuntu_lts.version, oe_lts.version) > 0
    if ubuntu_interim and oe_best:
        comp.lag_behind_ubuntu_interim = (
            compare_upstream(ubuntu_interim.version, oe_best.version) > 0
        )

    return comp
