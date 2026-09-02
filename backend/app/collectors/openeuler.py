"""Discover, catalogue and collect openEuler release package metadata.

openEuler exposes a *stream catalogue*:

* **LTS** releases (and their service packs, e.g. ``24.03-LTS-SP4``) on the
  stable mirror (``repo.openeuler.org``),
* **innovation** releases (e.g. ``24.09``/``25.09``) on the stable mirror,
* the **DevStation** innovation series (``26.09-DevStation``) plus every
  pre-GA RC / daily build on ``dailybuild.openeuler.openatom.cn``.

Each stream resolves to a repository root that contains
``<target>/<arch>/repodata/repomd.xml``; ``collect_stream_versions`` pulls the
source-package inventory for a single stream, so the UI can switch freely.
"""

from __future__ import annotations

import re

from app import config
from app.collectors import repodata_parser
from app.utils import LOG, http_get, version_compare

LTS_RE = re.compile(r"^openEuler-(?P<ver>\d+\.\d+)-LTS(?:-SP(?P<sp>\d+))?$")
INNOV_RE = re.compile(r"^openEuler-(?P<ver>\d+\.\d+)(?:-DevStation)?$")
IGNORE = re.compile(r"(preview|Embedded|debug|source|RISC|loong|ARM64|X86)", re.I)


def _iter_releases() -> list[str]:
    resp = http_get(config.OPEN_EULER_MIRROR + "/", timeout=30)
    return sorted({m.group(1).strip("/") for m in re.finditer(r'href="(openEuler-[^"/]+)/?"', resp.text)})


def _ver_key(ver: str) -> tuple:
    a, b = ver.split(".")[:2]
    return (int(a), int(b))


# ---------------------------------------------------------------------------
# Mirror / daily-build listing helpers
# ---------------------------------------------------------------------------
def _mirror_lts_streams(family: str | None = None) -> list[str]:
    out = []
    for r in _iter_releases():
        m = LTS_RE.match(r)
        if not m:
            continue
        if family and not r.startswith(f"openEuler-{family}-LTS"):
            continue
        out.append(r)
    # Sort by version then SP, newest SP last.
    out.sort(key=lambda r: (_ver_key(LTS_RE.match(r).group("ver")), int(LTS_RE.match(r).group("sp") or 0)))
    return out


def _mirror_innovation_streams() -> list[str]:
    out = sorted(
        (r for r in _iter_releases() if INNOV_RE.match(r) and not IGNORE.search(r)),
        key=lambda r: _ver_key(INNOV_RE.match(r).group("ver")),
    )
    # Keep the current-generation innovation cycles only (the EOL 20.09–23.09
    # series are archived and not meaningful for a live compatibility view).
    return [r for r in out if _ver_key(INNOV_RE.match(r).group("ver")) >= (24, 9)]


def _iter_dailybuild_innovation() -> list[str]:
    """All EBS-openEuler-<ver>(-DevStation) releases on the daily-build host."""
    try:
        resp = http_get(config.OPEN_EULER_DAILYBUILD + "/", timeout=20)
        entries = {e for e in re.findall(r'href="(EBS-openEuler-[^"/]+)/"', resp.text)}
    except Exception:  # noqa: BLE001
        return []
    out = []
    for entry in entries:
        release = entry[len("EBS-"):] if entry.startswith("EBS-") else entry
        if INNOV_RE.match(release) and not IGNORE.search(entry):
            out.append(release)
    return sorted(out, key=lambda r: _ver_key(INNOV_RE.match(r).group("ver")))


def _iter_devstation_builds() -> list[dict]:
    """Every RC and dated daily build of the DevStation release."""
    release = _latest_devstation_release()
    if not release:
        return []
    idx_url = f"{config.OPEN_EULER_DAILYBUILD}/EBS-{release}/"
    try:
        resp = http_get(idx_url, timeout=30)
    except Exception:  # noqa: BLE001
        return []
    dirs = re.findall(r'href="([A-Za-z0-9_.-]+)/"', resp.text)
    builds: list[dict] = []
    for d in dirs:
        if re.match(r"^rc\d+_openeuler-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$", d):
            builds.append({"id": f"{release}-rc{d.split('_')[0][2:]}", "build": d, "label": f"{release} RC{d.split('_')[0][2:]}", "date": d.split("_")[1], "rc": True})
        elif re.match(r"^openeuler-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$", d):
            date = d.strip("openeuler-")
            builds.append({"id": f"{release}-daily-{date[:10].replace('-','')}", "build": d, "label": f"{release} 每日构建 {date[:10]}", "date": date, "rc": False})
    # Sort: RC builds first (by rc number), then daily (by date desc), keep only
    # the newest few dailies to avoid noise.
    rc = sorted((b for b in builds if b["rc"]), key=lambda b: int(b["id"].rsplit("rc", 1)[-1]))
    daily = sorted((b for b in builds if not b["rc"]), key=lambda b: b["date"], reverse=True)
    return rc + daily[: int(config.INCLUDE_DEVSTATION_DAILY) * 3]


def _latest_devstation_release() -> str:
    releases = _iter_dailybuild_innovation()
    dv = [r for r in releases if "-DevStation" in r]
    return dv[-1] if dv else ""


# ---------------------------------------------------------------------------
# Public catalogue
# ---------------------------------------------------------------------------
def stream_catalog(family: str | None = None) -> list[dict]:
    """Return every selectable openEuler stream descriptor."""
    fam = family or config.DEFAULT_LTS_FAMILY
    streams: list[dict] = []
    for release in _mirror_lts_streams(fam):
        m = LTS_RE.match(release)
        sp = m.group("sp")
        streams.append({
            "id": release,
            "label": f"openEuler {m.group('ver')} LTS" + (f" SP{sp}" if sp else ""),
            "kind": "LTS",
            "release": release,
            "base": f"{config.OPEN_EULER_MIRROR}/{release}",
            "source": "mirror",
            "date": "",
        })
    for release in _mirror_innovation_streams():
        m = INNOV_RE.match(release)
        streams.append({
            "id": release,
            "label": f"openEuler {m.group('ver')}" + (" DevStation" if "-DevStation" in release else ""),
            "kind": "innovation",
            "release": release,
            "base": f"{config.OPEN_EULER_MIRROR}/{release}",
            "source": "mirror",
            "date": "",
        })
    for b in _iter_devstation_builds():
        streams.append({
            "id": b["id"],
            "label": b["label"],
            "kind": "innovation",
            "release": b["id"],
            "base": f"{config.OPEN_EULER_DAILYBUILD}/EBS-{_latest_devstation_release()}/{b['build']}",
            "source": "dailybuild",
            "date": b["date"],
            "rc": b.get("rc", False),
        })
    return streams


def discover_latest() -> dict[str, str]:
    """Return {stream: release} for the latest LTS and innovation (defaults)."""
    catalog = stream_catalog()
    lts = [s for s in catalog if s["kind"] == "LTS"]
    innov = sorted(
        (s for s in catalog if s["kind"] == "innovation" and s["source"] == "mirror"),
        key=lambda s: _ver_key(s["release"].split("-")[1]),
    )
    devstation = [s for s in catalog if "DevStation" in s["id"] and s["source"] == "dailybuild"]
    # Latest innovation: mirror release first, else newest DevStation build.
    best_innov_id = innov[-1]["id"] if innov else ""
    if devstation:
        # Prefer the most recent RC, otherwise the newest daily build.
        rc = [s for s in devstation if s.get("rc")]
        best_innov_id = (rc[-1] if rc else sorted(devstation, key=lambda s: s["date"], reverse=True)[0])["id"]
    return {
        "openEuler_LTS": lts[-1]["id"] if lts else "",
        "openEuler_innovation": best_innov_id,
    }


# ---------------------------------------------------------------------------
# Per-stream resolution + collection
# ---------------------------------------------------------------------------
def _find_repomd(base: str) -> str | None:
    """Probe the common repo layouts to find a working primary repomd URL."""
    for spec in config.REPO_SOURCES:
        if spec["kind"] != "binary":
            continue
        url = _repomd_for(base, spec)
        if url:
            return url
    return None


def _prefixes(base: str) -> list[str]:
    """Candidate repo roots: the base, plus the kernel-variant nesting used by
    some DevStation daily/RC builds."""
    out = [base]
    for k in ("6.18", "6.6", "5.10"):
        out.append(f"{base}/26.09-with-kernel-{k}")
    return out


def _repomd_for(base: str, spec: dict, arch: str | None = None) -> str | None:
    """Return a working repomd.xml URL for a repo spec, or None."""
    arch = arch or config.OPEN_EULER_ARCH
    for prefix in _prefixes(base):
        path = spec["path"]
        if spec["kind"] in ("source",):
            url = f"{prefix}/{path}/repodata/repomd.xml"
        else:
            url = f"{prefix}/{path}/{arch}/repodata/repomd.xml"
        try:
            if http_get(url, timeout=12).status_code == 200:
                return url
        except Exception:  # noqa: BLE001
            continue
    return None


def resolve_stream(stream_id: str) -> dict | None:
    for s in stream_catalog():
        if s["id"] == stream_id:
            return s
    return None


def collect_stream_inventory(stream_id: str, *, full: bool = False) -> dict[str, dict]:
    """Aggregate every default repo of a stream into one source inventory.

    The binary version is the *newest* of OS / everything / EPOL / update; source
    availability comes from ``source``/``update/source``; debug info from
    ``debuginfo``. Returns ``{source: {version, repo, has_source, has_debug,
    in_epol, in_update, arches, summary, license, provides, requires, reverse}}``.
    """
    desc = resolve_stream(stream_id)
    if not desc:
        raise ValueError(f"unknown stream {stream_id}")
    merged: dict[str, dict] = {}
    src_cache = config.REPO_META_CACHE / stream_id.replace("/", "_")

    for spec in config.REPO_SOURCES:
        url = _repomd_for(desc["base"], spec)
        if not url:
            LOG.info("repo %s not present for %s", spec["name"], stream_id)
            continue
        try:
            # Binary repos carry the dependency graph (needed for importance);
            # source/debug repos only need presence + version, so parse lightly.
            parse_full = full and spec["kind"] == "binary"
            src = repodata_parser.collect_release(url, src_cache, light=not parse_full)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("repo %s failed for %s: %s", spec["name"], stream_id, exc)
            continue
        for name, rec in src.items():
            entry = merged.setdefault(
                name,
                {"name": name, "version": "", "latest_repo": "", "has_source": False,
                 "has_debug": False, "in_epol": False, "in_update": False,
                 "arches": [], "summary": rec.get("summary", ""), "license": rec.get("license", ""),
                 "provides": [], "requires": [], "reverse": 0},
            )
            # Newest binary version wins (full EVR, so update patches supersede).
            if spec["kind"] == "binary":
                cand = rec.get("version", "")
                if cand and version_compare(cand, entry["version"]) > 0:
                    entry["version"] = cand
                    entry["latest_repo"] = spec["name"]
                if spec["name"] == "update":
                    entry["in_update"] = True
                if spec["name"] == "EPOL":
                    entry["in_epol"] = True
            if spec["kind"] == "debug":
                entry["has_debug"] = True
            if spec["kind"] == "source":
                entry["has_source"] = True
                if not entry["version"]:
                    entry["version"] = rec.get("version", "")
            for a in rec.get("arches", []):
                if a not in entry["arches"]:
                    entry["arches"].append(a)
            if not entry["summary"] and rec.get("summary"):
                entry["summary"] = rec["summary"]
            if full:
                for p in rec.get("provides", []):
                    if p not in entry["provides"]:
                        entry["provides"].append(p)
                for rq in rec.get("requires", []):
                    if rq not in entry["requires"]:
                        entry["requires"].append(rq)
                entry["reverse"] = max(entry["reverse"], rec.get("reverse", 0))
    return merged


def collect_stream_versions(stream_id: str) -> dict[str, dict]:
    """Per-stream version + repo tags: {source: {version, latest_repo, in_epol,
    in_update, has_source, has_debug}} (aggregated, light)."""
    inv = collect_stream_inventory(stream_id, full=False)
    return {
        name: {
            "version": rec["version"],
            "latest_repo": rec["latest_repo"],
            "in_epol": rec["in_epol"],
            "in_update": rec["in_update"],
            "has_source": rec["has_source"],
            "has_debug": rec["has_debug"],
        }
        for name, rec in inv.items()
    }


def collect(streams: dict[str, str] | None = None) -> dict[str, dict]:
    """Collect full inventories (with dependency graph) for the default pair."""
    streams = streams or discover_latest()
    if config.OPEN_EULER_LTS_RELEASE:
        streams["openEuler_LTS"] = config.OPEN_EULER_LTS_RELEASE
    if config.OPEN_EULER_INNOVATION_RELEASE:
        streams["openEuler_innovation"] = config.OPEN_EULER_INNOVATION_RELEASE
    merged: dict[str, dict] = {}
    best: dict[str, str] = {}  # newest version seen per source, any stream
    for stream_name, stream_id in streams.items():
        try:
            src = collect_stream_inventory(stream_id, full=True)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("failed collecting %s (%s): %s", stream_name, stream_id, exc)
            continue
        for name, rec in src.items():
            entry = merged.setdefault(
                name,
                {"name": name, "versions": {}, "arches": [], "summary": rec.get("summary", ""),
                 "license": rec.get("license", ""), "reverse": rec.get("reverse", 0),
                 "provides": rec.get("provides", []), "requires": rec.get("requires", []),
                 "has_source": rec.get("has_source", False), "has_debug": rec.get("has_debug", False),
                 "in_epol": rec.get("in_epol", False), "in_update": rec.get("in_update", False),
                 "latest_repo": rec.get("latest_repo", "")},
            )
            entry["versions"][stream_name] = rec.get("version", "")
            # Repo tags follow whichever stream carries the newest version.
            ver = rec.get("version", "")
            if ver and version_compare(ver, best.get(name, "")) > 0:
                best[name] = ver
                for k in ("has_source", "has_debug", "in_epol", "in_update"):
                    entry[k] = rec.get(k, False)
                entry["latest_repo"] = rec.get("latest_repo", "")
            for a in rec.get("arches", []):
                if a not in entry["arches"]:
                    entry["arches"].append(a)
            if not entry["summary"] and rec.get("summary"):
                entry["summary"] = rec["summary"]
    return merged
