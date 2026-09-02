"""Python / pip package governance.

Third-party Python modules arrive as ``python-<name>`` source packages. Whether
they should be sunset depends on upstream-maintenance (PyPI release cadence),
Python-version compatibility, and reverse-dependency pressure. We keep the
system Python runtime untouched and apply a *conservative* sunset rule to pip
modules only.
"""

from __future__ import annotations

import re

from app.collectors import pypi as pypi_collect
from app.models import Package
from app.utils import compare_upstream

_RANG = re.compile(
    r"(?P<op>>=|<=|==|!=|~=|>|<)?\s*(?P<ver>\d+(?:\.\d+){0,2}(?:\.\*)?)"
)


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
            ">": cur > target, ">=": cur >= target,
            "<": cur < target, "<=": cur <= target,
            "==": cur[: len(target)] == target,
            "!=": cur[: len(target)] != target,
            "~=": target <= cur < (target[0], target[1] + 1) if len(target) >= 2 else cur >= target,
        }.get(op, True)
        if hasattr(ok, "__call__"):
            ok = cur >= target
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
) -> Package:
    """Attach a python profile + conservative sunset adjustment to a package."""
    name = pkg.name
    if not pypi_collect.is_pip_module(name):
        return pkg

    prof = pypi_profiles.get(name, {}) or {}
    sys_major_minor = ".".join(str(v) for v in _num(sys_python)[:2]) if sys_python else ""
    compat_ok = _pep440_satisfied(prof.get("pypi_requires_python", ""), sys_major_minor or sys_python)

    note = []
    if prof.get("pypi_stale"):
        note.append(
            f"PyPI 上游 [{prof.get('pypi_name','')}] 已超过 2 年未发布（最新 {prof.get('pypi_latest','')}，"
            f"发布于 {prof.get('pypi_last_release','') or '—'}）。"
        )
    elif prof.get("pypi_latest"):
        note.append(
            f"PyPI 上游最新 {prof.get('pypi_latest','')}（Requires-Python {prof.get('pypi_requires_python','') or '不限'}）。"
        )
    if prof.get("pypi_requires_python") and not compat_ok and sys_major_minor:
        note.append(
            f"PyPI 新版本要求 Python {prof.get('pypi_requires_python','')}，当前系统 Python {sys_major_minor} 不满足："
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

    # Conservative sunset: PyPI stale + no meaningful reverse pressure + not core.
    if prof.get("pypi_stale") and pkg.governance.reverse_deps == 0 and pkg.governance.importance != "core":
        pkg.governance.disposal = "sunset"
        pkg.governance.sunset_candidate = True
        pkg.governance.maintenance_notes.append(
            "Python/pip 模块：PyPI 上游已停更且无反向依赖、非核心，建议日落。"
        )
    elif prof.get("pypi_stale"):
        pkg.governance.maintenance_notes.append(
            "Python/pip 模块：PyPI 上游停更，但仍被依赖，需维持并评估替代。"
        )
    pkg.governance.maintenance_notes.extend(note)
    return pkg
