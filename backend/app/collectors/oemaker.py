"""Official ISO package lists from the oemaker repo (GitCode mirror).

The oemaker project (atomgit.com/src-openeuler/oemaker, mirrored on GitCode)
maintains, per release branch, the comps group XMLs used to compose the
standard ISO, an rpmlist of packages explicitly excluded from it, and the
DevStation ISO rpmlist. Those lists use binary-RPM names, so they are mapped
back to source packages through the stream's OS-repo binary->source index.

Exposes three tags per source package:

* ``baseline``   - selected by the oemaker comps groups (mandatory/default),
* ``excluded``   - explicitly excluded from the ISO by the oemaker rpmlist,
* ``devstation`` - inside the DevStation ISO rpmlist.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from app import config
from app.collectors import openeuler, repodata_parser
from app.utils import LOG, http_get

API_BASE = "https://api.gitcode.com/api/v5/repos/src-openeuler/oemaker"
FILE_CACHE = config.CACHE_DIR / "oemaker"
COMPS_ARCHES = ("x86_64", "aarch64")

_STREAM_PREFIX = re.compile(r"^(openEuler-\d+\.\d+)")


def branches() -> set[str]:
    """Branch names of the oemaker repo."""
    try:
        resp = http_get(f"{API_BASE}/branches", params={"per_page": 100}, timeout=20)
        data = resp.json() if resp.status_code == 200 else []
        return {b.get("name", "") for b in data if isinstance(b, dict)} - {""}
    except Exception:  # ruff: ignore[blind-except]
        return set()


def resolve_branch(stream_id: str, known: set[str] | None = None) -> str:
    """Map a stream id onto the oemaker branch holding its ISO lists.

    Exact ids match directly (``openEuler-24.03-LTS-SP4``); DevStation build
    ids collapse onto the ``*-DevStation`` branch; anything else falls back to
    the ``openEuler-<major.minor>`` prefix.
    """
    known = known if known is not None else branches()
    if stream_id in known:
        return stream_id
    if "-DevStation" in stream_id:
        cand = stream_id.split("-DevStation", 1)[0] + "-DevStation"
        if cand in known:
            return cand
    m = _STREAM_PREFIX.match(stream_id)
    if m and m.group(1) in known:
        return m.group(1)
    return ""


def _fetch_file(branch: str, path: str) -> bytes:
    """Fetch one repo file via the GitCode contents API, cached on disk."""
    dest: Path = FILE_CACHE / branch / path
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    try:
        resp = http_get(f"{API_BASE}/contents/{path}", params={"ref": branch}, timeout=30)
        if resp.status_code != 200:
            LOG.info("oemaker: %s not in branch %s (HTTP %s)", path, branch, resp.status_code)
            return b""
        content = base64.b64decode(resp.json().get("content", ""))
    except Exception:  # ruff: ignore[blind-except]
        return b""
    if content:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    return content


def parse_comps(xml_bytes: bytes) -> list[str]:
    """Binary RPM names in the mandatory/default comps groups (ISO-selected)."""
    if not xml_bytes:
        return []
    out: list[str] = []
    for el in ET.fromstring(xml_bytes).iter():
        if el.tag.rsplit("}", 1)[-1] != "packagereq":
            continue
        if (el.get("type") or "mandatory") not in ("mandatory", "default"):
            continue
        name = (el.text or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def parse_rpmlist(xml_bytes: bytes) -> list[str]:
    """Binary RPM names explicitly excluded from / conflicting with the ISO."""
    if not xml_bytes:
        return []
    out: list[str] = []
    for pl in ET.fromstring(xml_bytes).iter():
        if pl.tag.rsplit("}", 1)[-1] != "packagelist":
            continue
        if (pl.get("type") or "") not in ("exclude", "conflict"):
            continue
        for el in pl:
            if el.tag.rsplit("}", 1)[-1] != "packagereq":
                continue
            name = (el.text or "").strip()
            if name and name not in out:
                out.append(name)
    return out


def parse_plain_list(data: bytes) -> list[str]:
    """One binary RPM name per line (DevStation rpmlist)."""
    out: list[str] = []
    for line in data.decode("utf-8", "replace").splitlines():
        name = line.strip()
        if name and not name.startswith("#") and name not in out:
            out.append(name)
    return out


def binary_source_map(stream_id: str) -> dict[str, str]:
    """Binary RPM name -> source package name, from the stream's OS repo."""
    desc = openeuler.resolve_stream(stream_id)
    if not desc:
        return {}
    spec = next((s for s in config.REPO_SOURCES if s["name"] == "OS"), None)
    if not spec:
        return {}
    url = openeuler.repomd_for(desc["base"], spec)
    if not url:
        return {}
    try:
        src = repodata_parser.collect_release(url, config.REPO_META_CACHE / stream_id.replace("/", "_"), light=False)
    except Exception as exc:  # ruff: ignore[blind-except]
        LOG.warning("oemaker: OS repo parse failed for %s: %s", stream_id, exc)
        return {}
    return {b: sname for sname, rec in src.items() for b in rec.get("binaries", [])}


def collect(streams: dict[str, str]) -> dict:
    """Collect ISO composition tags for the default streams.

    Returns ``{"streams": {stream_name: {...counts...}}, "tags": {source: {
    baseline/excluded/devstation: True}}}``. Binary names without a known
    source mapping fall back to their own name (most are source == binary).
    """
    known = branches()
    tags: dict[str, dict] = {}
    report: dict[str, dict] = {}
    for stream_name, stream_id in streams.items():
        branch = resolve_branch(stream_id, known)
        if not branch:
            LOG.info("oemaker: no branch matches stream %s", stream_id)
            continue
        baseline_bin = parse_comps(_fetch_file(branch, "normal_x86_64.xml")) + list(
            parse_comps(_fetch_file(branch, "normal_aarch64.xml"))
        )
        excluded_bin = parse_rpmlist(_fetch_file(branch, "rpmlist.xml"))
        devstation_bin: list[str] = []
        if "-DevStation" in stream_id:
            devstation_bin = parse_plain_list(_fetch_file(branch, "devstation_x86_64_rpmlist")) + parse_plain_list(
                _fetch_file(branch, "devstation_aarch64_rpmlist")
            )
        b2s = binary_source_map(stream_id)
        baseline_src = {b2s.get(n, n) for n in baseline_bin}
        excluded_src = {b2s.get(n, n) for n in excluded_bin}
        devstation_src = {b2s.get(n, n) for n in devstation_bin}
        for sname in baseline_src:
            tags.setdefault(sname, {})["baseline"] = True
        for sname in excluded_src:
            tags.setdefault(sname, {})["excluded"] = True
        for sname in devstation_src:
            tags.setdefault(sname, {})["devstation"] = True
        report[stream_name] = {
            "branch": branch,
            "baseline_binaries": len(set(baseline_bin)),
            "excluded_binaries": len(set(excluded_bin)),
            "devstation_binaries": len(set(devstation_bin)),
            "baseline_sources": len(baseline_src),
            "excluded_sources": len(excluded_src),
            "devstation_sources": len(devstation_src),
        }
        LOG.info("oemaker: ISO tags for %s (branch %s): %s", stream_id, branch, report[stream_name])
    return {"streams": report, "tags": tags}
