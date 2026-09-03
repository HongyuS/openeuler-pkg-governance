"""Package -> SIG ownership map from the openEuler community repo.

The community repository (atomgit.com/openeuler/community, mirrored on GitCode)
keeps one ``sig/<SIG>/sig-info.yaml`` per SIG that lists every repository the
SIG owns under ``repositories[].repo`` (entries like ``src-openeuler/<pkg>``).
Scanning those ~100 small YAML files therefore yields the complete
package->SIG mapping for the whole distribution (~7000 source repos) with a
couple of hundred requests — no per-package repo enumeration needed.

Per-SIG metadata (description, mailing list, maturity level) is returned as
well so the UI can show the owning SIG as first-class information.
"""

from __future__ import annotations

import base64
from pathlib import Path

import yaml

from app import config
from app.utils import LOG, http_get

API_BASE = "https://api.gitcode.com/api/v5/repos/openeuler/community"
FILE_CACHE = config.CACHE_DIR / "sig"
REF = "master"
SRC_PREFIX = "src-openeuler/"  # source-package repos, vs openeuler/<docs-repos>


def sig_names() -> list[str]:
    """SIG directory names in the community repo."""
    try:
        resp = http_get(f"{API_BASE}/contents/sig", params={"ref": REF}, timeout=20)
        data = resp.json() if resp.status_code == 200 else []
        dirs = [e.get("name", "") for e in data if isinstance(e, dict) and e.get("type") == "dir"]
        return sorted(dirs)
    except Exception:  # ruff: ignore[blind-except]
        return []


def _fetch_info(name: str) -> bytes:
    """Fetch one SIG's sig-info.yaml via the GitCode contents API, cached on disk."""
    dest: Path = FILE_CACHE / f"{name}.yaml"
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    try:
        resp = http_get(f"{API_BASE}/contents/sig/{name}/sig-info.yaml", params={"ref": REF}, timeout=30)
        if resp.status_code != 200:
            LOG.info("sig: %s has no sig-info.yaml (HTTP %s)", name, resp.status_code)
            return b""
        content = base64.b64decode(resp.json().get("content", ""))
    except Exception:  # ruff: ignore[blind-except]
        return b""
    if content:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    return content


def parse_info(data: bytes) -> dict:
    """Parse a sig-info.yaml into {name, description, mailing_list, mature_level, packages}."""
    try:
        doc = yaml.safe_load(data.decode("utf-8", "replace")) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(doc, dict):
        return {}
    packages: list[str] = []
    for group in doc.get("repositories") or []:
        if not isinstance(group, dict):
            continue
        repos = group.get("repo") or []
        if isinstance(repos, str):
            repos = [repos]
        for entry in repos:
            if isinstance(entry, str) and entry.startswith(SRC_PREFIX):
                pkg = entry[len(SRC_PREFIX) :]
                if pkg and pkg not in packages:
                    packages.append(pkg)
    return {
        "name": doc.get("name") or "",
        "description": doc.get("description") or "",
        "mailing_list": doc.get("mailing_list") or "",
        "mature_level": doc.get("mature_level") or "",
        "packages": packages,
    }


def collect() -> dict:
    """Build the package->SIG map and per-SIG metadata.

    Returns ``{"pkg_sig": {package: [sig, ...]}, "sigs": {sig: {description,
    mailing_list, mature_level, package_count}}}``. A package owned by several
    SIGs keeps every owner (rare; usually a transferred package), the pipeline
    stores the first one.
    """
    pkg_sig: dict[str, list[str]] = {}
    sigs: dict[str, dict] = {}
    names = sig_names()
    for name in names:
        info = parse_info(_fetch_info(name))
        if not info:
            continue
        for pkg in info.pop("packages"):
            owners = pkg_sig.setdefault(pkg, [])
            if name not in owners:
                owners.append(name)
        sigs[info.get("name") or name] = info
    multi = [p for p, s in pkg_sig.items() if len(s) > 1]
    if multi:
        LOG.info("sig: %d packages owned by multiple SIGs (first wins)", len(multi))
    LOG.info("sig: %d SIGs cover %d source packages", len(sigs), len(pkg_sig))
    return {"pkg_sig": pkg_sig, "sigs": sigs}
