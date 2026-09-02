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


def apply_nodejs(pkg: Package, system_set: set[str]) -> Package:
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

    sys_deps = [d for d in gov.dependents if d in system_set]
    other_deps = [d for d in gov.dependents if d not in system_set]
    if sys_deps:
        gov.maintenance_notes.append(
            f"npm 模块被关键包 [{_fmt(sys_deps)}] 强制依赖：保留在系统源维护。"
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
        gov.maintenance_notes.append(
            "无关键包依赖的 npm 模块属开发工具，应由 npm/pnpm/bun 生态承接，建议日落。"
        )
    return pkg
