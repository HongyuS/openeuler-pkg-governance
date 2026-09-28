"""Importance & update-wave classification (P0/P1/P2, core/important/ordinary).

Mirrors the plan:

* **P0** — minimal critical set: kernel, glibc, openssl, systemd, python and its
  dependency closure. Align to the latest release first.
* **P1** — secondary base packages: network / storage / toolchain.
* **P2** — upper-layer applications: desktop & terminal software, updated last.

Two dependency graphs feed the classification, kept deliberately separate:

* **runtime** — binary ``Requires`` (shared libraries, ``python3dist(…)``, …);
* **build-only** — spec-level ``BuildRequires`` from the source repositories,
  with the runtime capabilities already subtracted by the collector.

A package can be pulled out of obscurity by either graph (``make`` has 17 runtime
dependents but ~800 build dependents), so the P1 percentile band uses the larger
of the two. The P0 ``core`` promotion stays runtime-only: build fan-in says
"many specs need this to compile", not "the installed system depends on it".
"""

from __future__ import annotations

from collections import deque

from app.engine.rules_loader import rules
from app.utils import cap_key

# Kept as a module-level alias: the historical private name is referenced by the
# repo's AGENTS.md and by out-of-tree scripts.
_cap_key = cap_key


def build_provide_map(inventory: dict[str, dict]) -> dict[str, set[str]]:
    """Map each provided capability to the set of source packages providing it."""
    pmap: dict[str, set[str]] = {}
    for name, rec in inventory.items():
        for prov in rec.get("provides", []):
            pmap.setdefault(_cap_key(prov), set()).add(name)
    return pmap


def build_require_graph(inventory: dict[str, dict], provide_map: dict[str, set[str]]) -> dict[str, set[str]]:
    """Build the package -> {runtime dependent sources} reverse graph."""
    reverse: dict[str, set[str]] = {}
    for name, rec in inventory.items():
        for req in rec.get("requires", []):
            for src in provide_map.get(_cap_key(req), ()):
                if src != name:
                    reverse.setdefault(src, set()).add(name)
    return reverse


def build_build_graph(inventory: dict[str, dict], provide_map: dict[str, set[str]]) -> dict[str, set[str]]:
    """Build the package -> {sources that BuildRequire it} reverse graph.

    ``build_requires`` holds the spec-level ``BuildRequires`` capabilities that
    remain *after* the collector subtracted the source package's runtime
    capabilities, so this graph is disjoint from the runtime one and the two can
    simply be unioned for protection decisions (e.g. sunset).
    """
    reverse: dict[str, set[str]] = {}
    for name, rec in inventory.items():
        for req in rec.get("build_requires", []):
            for src in provide_map.get(_cap_key(req), ()):
                if src != name:
                    reverse.setdefault(src, set()).add(name)
    return reverse


def _is_python_edge(key: str) -> bool:
    """Only follow Python-namespaced capabilities.

    Otherwise the closure BFS
    spills into half the distro via real but irrelevant edges
    (python3 -> libm -> glibc -> kernel -> llvm -> numpy; bash -> info -> texlive -> R).
    """
    return key.startswith(("python", "/usr/bin/python", "/usr/lib/python"))


def python_closure(inventory: dict[str, dict], provide_map: dict[str, set[str]] | None = None) -> set[str]:
    """BFS the Python dependency closure from the seed packages."""
    provide_map = provide_map or build_provide_map(inventory)
    seeds = rules().get("python_closure_seeds", [])
    closure: set[str] = set()
    queue = deque(seeds)
    while queue:
        name = queue.popleft()
        if name in closure:
            continue
        if name not in inventory:
            continue
        closure.add(name)
        for req in inventory[name].get("requires", []):
            key = _cap_key(req)
            if not _is_python_edge(key):
                continue
            for src in provide_map.get(key, ()):
                if src not in closure:
                    queue.append(src)
    return closure


def _percentiles(values: list[int]) -> dict[str, int]:
    if not values:
        return {"p95": 0, "p75": 0}
    v = sorted(values, reverse=True)
    n = len(v)
    return {
        "p95": v[int(n * 0.05)] if n >= 20 else v[-1],
        "p75": v[int(n * 0.25)] if n >= 20 else v[0],
    }


def classify(
    inventory: dict[str, dict],
    *,
    closure: set[str] | None = None,
    iso_baseline: set[str] | None = None,
) -> dict[str, dict]:
    """Return per-package classification metadata.

    ``iso_baseline`` (packages selected by the base-install ISO comps groups)
    unions the curated ``P1_base`` list: the ISO membership *is* the "what
    ships" definition, mirroring Ubuntu seeds / Fedora comps (D8).
    """
    cfg = rules()
    p0 = set(cfg.get("P0_critical", []))
    p1 = set(cfg.get("P1_base", []))
    iso_base = iso_baseline or set()
    py_seeds = set(cfg.get("python_closure_seeds", []))
    provide_map = build_provide_map(inventory)
    reverse = build_require_graph(inventory, provide_map)
    build_reverse = build_build_graph(inventory, provide_map)
    closure = closure if closure is not None else python_closure(inventory, provide_map)

    rd = {name: len(reverse.get(name, ())) for name in inventory}
    brd = {name: len(build_reverse.get(name, ())) for name in inventory}
    # Percentile bands follow the *stronger* of the two graphs: a build-only
    # dependency is just as much of a reason to keep a package as a runtime one
    # (a removed BuildRequires breaks the whole buildroot, not just one binary).
    pct = _percentiles([max(rd[name], brd[name]) for name in inventory])
    p95, p75 = pct["p95"], pct["p75"]
    # "Key" packages: the curated critical set plus the explicit Python runtime
    # seeds. The *closure* is tracked separately (in_python_closure) but should
    # not promote every python-* subpackage to P0.
    py_runtime = set(py_seeds)

    result: dict[str, dict] = {}
    for name in inventory:
        reverse_deps = rd.get(name, 0)
        build_reverse_deps = brd.get(name, 0)
        pressure = max(reverse_deps, build_reverse_deps)
        is_critical = name in p0 or name in py_runtime
        is_base = name in p1 or name in iso_base

        if is_critical:
            p_level = "P0"
        elif is_base or pressure >= p75:
            p_level = "P1"
        else:
            p_level = "P2"

        if is_critical or (reverse_deps >= p95 and is_base):
            importance = "core"
        elif is_base or pressure >= p75:
            importance = "important"
        else:
            importance = "ordinary"

        result[name] = {
            "importance": importance,
            "p_level": p_level,
            "is_key_package": is_critical or name in py_seeds,
            "critical_term": name in ("kernel", "glibc", "openssl", "systemd"),
            "reverse_deps": reverse_deps,
            "dependents": sorted(reverse.get(name, ()))[:60],
            "build_reverse_deps": build_reverse_deps,
            "build_dependents": sorted(build_reverse.get(name, ()))[:60],
            "in_python_closure": name in closure,
            "bands": pct,
        }
    return result
