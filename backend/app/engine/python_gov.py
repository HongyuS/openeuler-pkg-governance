"""Python / pip package governance.

Third-party Python modules arrive as ``python-<name>`` source packages. Normal
Python projects should build their own venv rather than rely on the system
site-packages, so the system repo keeps only pip modules that serve other
system packages: modules depended on by critical/key packages stay, modules
depended on only by non-critical packages get a migration notice (venv /
bundling such as PyInstaller, shiv, pex), and modules with no dependents are
sunset. PyPI upstream staleness and Requires-Python compatibility remain as
risk notes.
"""

from __future__ import annotations

import re

from app.collectors import pypi as pypi_collect
from app.models import Package

_RANG = re.compile(r"(?P<op>>=|<=|==|!=|~=|>|<)?\s*(?P<ver>\d+(?:\.\d+){0,2}(?:\.\*)?)")


def _clean(ver: str) -> str:
    """Strip epoch and release: '0:3.11.6-39.oe2403' -> '3.11.6'."""
    v = ver.split(":", 1)[-1] if ":" in ver else ver
    return v.split("-", 1)[0].strip() if "-" in v else v.strip()


def _num(ver: str) -> tuple:
    parts = re.findall(r"\d+", _clean(ver))
    return tuple(int(p) for p in parts[:3])


def _pep440_satisfied(requires_python: str, current: str) -> bool:
    """Best-effort check of a PEP 440 ``Requires-Python`` against ``current``."""
    cur = _num(current)
    if not requires_python:
        return True
    clauses = [c.strip() for c in requires_python.split(",") if c.strip()]
    for clause in clauses:
        m = _RANG.match(clause)
        if not m:
            continue
        op = m.group("op") or "=="
        target = _num(m.group("ver").rstrip(".*"))
        ok = {
            ">": cur > target,
            ">=": cur >= target,
            "<": cur < target,
            "<=": cur <= target,
            "==": cur[: len(target)] == target,
            "!=": cur[: len(target)] != target,
            "~=": target <= cur < (target[0], target[1] + 1) if len(target) >= 2 else cur >= target,
        }.get(op, True)
        if not ok:
            return False
    return True


def system_python_version(inventory: dict[str, dict]) -> str:
    py3 = inventory.get("python3", {})
    # Canonical inventory stores versions keyed by stream (openEuler_LTS/innovation).
    versions = py3.get("versions", {})
    for key in ("openEuler_LTS", "openEuler_innovation"):
        if versions.get(key):
            return _clean(versions[key])
    if py3.get("version"):
        return _clean(py3["version"])
    return next((_clean(v) for v in versions.values() if v), "")


def apply_python(
    pkg: Package,
    inventory: dict[str, dict],
    pypi_profiles: dict[str, dict],
    sys_python: str,
    system_set: set[str] | None = None,
) -> Package:
    """Attach a python profile + dependency-driven disposal to a package."""
    name = pkg.name
    if not pypi_collect.is_pip_module(name):
        return pkg

    prof = pypi_profiles.get(name, {}) or {}
    sys_major_minor = ".".join(str(v) for v in _num(sys_python)[:2]) if sys_python else ""
    compat_ok = _pep440_satisfied(
        prof.get("pypi_requires_python", ""), sys_major_minor or sys_python
    )

    note = []
    if prof.get("pypi_stale"):
        note.append(
            f"PyPI 上游 [{prof.get('pypi_name', '')}] 已超过 2 年未发布"
            f"（最新 {prof.get('pypi_latest', '')}，"
            f"发布于 {prof.get('pypi_last_release', '') or '—'}）。"
        )
    elif prof.get("pypi_latest"):
        note.append(
            f"PyPI 上游最新 {prof.get('pypi_latest', '')}"
            f"（Requires-Python {prof.get('pypi_requires_python', '') or '不限'}）。"
        )
    if prof.get("pypi_requires_python") and not compat_ok and sys_major_minor:
        note.append(
            f"PyPI 新版本要求 Python {prof.get('pypi_requires_python', '')}，"
            f"当前系统 Python {sys_major_minor} 不满足："
            "存在 Python 版本兼容屏障，不能盲目升级。"
        )

    pkg.python = {
        "kind": "pip_module",
        "pypi_name": prof.get("pypi_name", name),
        "pypi_latest": prof.get("pypi_latest", ""),
        "pypi_last_release": prof.get("pypi_last_release", ""),
        "pypi_stale": bool(prof.get("pypi_stale", False)),
        "pypi_requires_python": prof.get("pypi_requires_python", ""),
        "compat_ok": compat_ok,
        "system_python": sys_major_minor,
        "notes": note,
    }

    # Dependency-driven disposal: system Python packages exist to serve other
    # system packages; everything else belongs to venv/pip or bundling.
    gov = pkg.governance
    system_set = system_set or set()
    sys_deps = [d for d in gov.dependents if d in system_set]
    other_deps = [d for d in gov.dependents if d not in system_set]

    def _fmt(names: list[str]) -> str:
        shown = ", ".join(names[:5])
        return shown + ("…" if len(names) > 5 else "")

    if sys_deps:
        gov.maintenance_notes.append(
            f"被系统/关键包 [{_fmt(sys_deps)}] 依赖：保留在系统源并优先对齐上游。"
        )
        if prof.get("pypi_stale"):
            gov.maintenance_notes.append(
                "Python/pip 模块：PyPI 上游停更，但仍被系统包依赖，需维持并评估替代。"
            )
    elif other_deps:
        gov.maintenance_notes.append(
            f"仅被非关键包 [{_fmt(other_deps)}] 依赖：通告并敦促依赖方维护者转向 "
            "venv/bundle 方式（PyInstaller、shiv、pex、打包 venv、容器镜像等，AI 类软件尤应如此），"
            "过渡期后退出系统源。"
        )
        if prof.get("pypi_stale"):
            gov.maintenance_notes.append(
                "Python/pip 模块：PyPI 上游停更，但仍被依赖，需维持并评估替代。"
            )
    else:
        gov.disposal = "sunset"
        gov.sunset_candidate = True
        reason = "无系统包依赖的 pip 模块应退出系统源，由 pip/venv 生态承接"
        if prof.get("pypi_stale"):
            reason += "；PyPI 上游亦已停更"
        gov.maintenance_notes.append(reason + "，建议日落。")
    pkg.governance.maintenance_notes.extend(note)
    return pkg
