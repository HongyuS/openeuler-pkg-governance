"""Importance & update-wave classification (P0/P1/P2, core/important/ordinary).

Mirrors the plan:

* **P0** — minimal critical set: kernel, glibc, openssl, systemd, python and its
  dependency closure. Align to the latest release first.
* **P1** — secondary base packages: network / storage / toolchain.
* **P2** — upper-layer applications: desktop & terminal software, updated last.

The reverse-dependency count is a strong importance signal but must not swallow
the histogram (base libraries are required by everything). We therefore combine
curated rules with *percentile* bands of reverse-dependency pressure.
"""

from __future__ import annotations

from collections import deque

from app.engine.rules_loader import rules


def build_provide_map(inventory: dict[str, dict]) -> dict[str, set[str]]:
    """Map each provided capability to the set of source packages providing it."""
    pmap: dict[str, set[str]] = {}
    for name, rec in inventory.items():
        for prov in rec.get("provides", []):
            key = prov.split("(")[0]
            pmap.setdefault(key, set()).add(name)
    return pmap


def build_require_graph(inventory: dict[str, dict], provide_map: dict[str, set[str]]) -> dict[str, set[str]]:
    """Build the package -> {dependent sources} reverse graph."""
    reverse: dict[str, set[str]] = {}
    for name, rec in inventory.items():
        for req in rec.get("requires", []):
            key = req.split("(")[0]
            for src in provide_map.get(key, ()):
                if src != name:
                    reverse.setdefault(src, set()).add(name)
    return reverse


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
            for src in provide_map.get(req.split("(")[0], ()):
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


def classify(inventory: dict[str, dict], *, closure: set[str] | None = None) -> dict[str, dict]:
    """Return per-package classification metadata."""
    cfg = rules()
    p0 = set(cfg.get("P0_critical", []))
    p1 = set(cfg.get("P1_base", []))
    py_seeds = set(cfg.get("python_closure_seeds", []))
    provide_map = build_provide_map(inventory)
    reverse = build_require_graph(inventory, provide_map)
    closure = closure if closure is not None else python_closure(inventory, provide_map)

    rd = {name: len(reverse.get(name, ())) for name in inventory}
    pct = _percentiles(list(rd.values()))
    p95, p75 = pct["p95"], pct["p75"]
    # "Key" packages: the curated critical set plus the explicit Python runtime
    # seeds. The *closure* is tracked separately (in_python_closure) but should
    # not promote every python-* subpackage to P0.
    py_runtime = set(py_seeds)

    result: dict[str, dict] = {}
    for name, rec in inventory.items():
        reverse_deps = rd.get(name, 0)
        is_critical = name in p0 or name in py_runtime
        is_base = name in p1

        if is_critical:
            p_level = "P0"
        elif is_base or reverse_deps >= p75:
            p_level = "P1"
        else:
            p_level = "P2"

        if is_critical or (reverse_deps >= p95 and is_base):
            importance = "core"
        elif is_base or reverse_deps >= p75:
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
            "in_python_closure": name in closure,
            "bands": pct,
        }
    return result
