"""Node.js / npm package governance.

System repos should only keep npm modules forced in by critical packages;
everything else is a development tool that developers install via
npm/pnpm/bun themselves. The toolchain (node runtime + package managers) is
what the system repo must actively maintain.
"""

from __future__ import annotations

from app.engine.rules_loader import rules
from app.models import Package

_DEFAULT_TOOLCHAIN = ["nodejs", "node", "npm", "pnpm", "yarn", "corepack", "bun"]


def is_node_module(name: str) -> bool:
    return name.startswith("nodejs-")


def _toolchain() -> set[str]:
    return set(rules().get("node_toolchain", _DEFAULT_TOOLCHAIN))


def _fmt(names: list[str]) -> str:
    shown = ", ".join(names[:5])
    return shown + ("…" if len(names) > 5 else "")


def apply_nodejs(
    pkg: Package, system_set: set[str], npm_profiles: dict[str, dict] | None = None
) -> Package:
    """Apply the npm-module disposal policy to a package."""
    name = pkg.name
    gov = pkg.governance
    if name in _toolchain():
        if gov.disposal == "sunset":
            gov.disposal = "maintain"
            gov.sunset_candidate = False
        gov.maintenance_notes.append(
            "Node.js 运行时/包管理器：开发者生态入口，系统源需重点维护并保持跟进上游。"
        )
        return pkg
    if not is_node_module(name):
        return pkg

    prof = (npm_profiles or {}).get(name, {}) or {}
    note = []
    if prof.get("npm_deprecated"):
        note.append(
            f"npm 上游 [{prof.get('npm_name', '')}] 已被官方标记 deprecated"
            f"（最新 {prof.get('npm_latest', '')}）。"
        )
    if prof.get("npm_stale"):
        note.append(
            f"npm 上游 [{prof.get('npm_name', '')}] 已超过 2 年未发布"
            f"（最新 {prof.get('npm_latest', '')}，"
            f"发布于 {prof.get('npm_last_release', '') or '—'}）。"
        )
    elif prof.get("npm_latest"):
        note.append(f"npm 上游最新 {prof.get('npm_latest', '')}。")
    pkg.npm = {
        "kind": "npm_module",
        "npm_name": prof.get("npm_name", name),
        "npm_latest": prof.get("npm_latest", ""),
        "npm_last_release": prof.get("npm_last_release", ""),
        "npm_stale": bool(prof.get("npm_stale", False)),
        "npm_deprecated": bool(prof.get("npm_deprecated", False)),
        "notes": note,
    }

    sys_deps = [d for d in gov.dependents if d in system_set]
    other_deps = [d for d in gov.dependents if d not in system_set]
    if sys_deps:
        gov.maintenance_notes.append(
            f"npm 模块被关键包 [{_fmt(sys_deps)}] 强制依赖：保留在系统源维护。"
        )
        if prof.get("npm_stale") or prof.get("npm_deprecated"):
            gov.maintenance_notes.append(
                "npm 模块：上游停更/已废弃，但仍被关键包依赖，需维持并评估替代。"
            )
    elif other_deps:
        gov.maintenance_notes.append(
            f"npm 模块仅被非关键包 [{_fmt(other_deps)}] 依赖：属开发工具，"
            "通告并敦促依赖方维护者转向 bundle 方式（npm bundle、pkg、Electron 自带运行时等），"
            "过渡期后退出系统源。"
        )
    else:
        gov.disposal = "sunset"
        gov.sunset_candidate = True
        reason = "无关键包依赖的 npm 模块属开发工具，应由 npm/pnpm/bun 生态承接"
        if prof.get("npm_deprecated"):
            reason += "；npm 上游已标记废弃"
        elif prof.get("npm_stale"):
            reason += "；npm 上游亦已停更"
        gov.maintenance_notes.append(reason + "，建议日落。")
    gov.maintenance_notes.extend(note)
    return pkg
