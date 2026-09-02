"""Parse an RPM repo's ``primary.xml`` into source-package records.

The openEuler mirror exposes the standard dnf repository metadata:
``repodata/repomd.xml`` points to a (zstd or gzip) ``*primary.xml``. That file
contains one ``<package>`` element per *binary* RPM: name, epoch/version/release,
arch, summary, license, vendor, group, source RPM, build time, and the provides/
requires sets. From it we derive:

* the set of source packages and their build versions per release stream,
* the software-provides graph used for reverse-dependency (“how many packages
  rely on me”) importance scoring.
"""

from __future__ import annotations

import gzip
import io
import re
import subprocess
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree as ET

from app.utils import LOG, version_compare

RPM_NS = "http://linux.duke.edu/metadata/rpm"


def download(url: str, dest: Path, *, timeout: float = 120) -> Path:
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    LOG.info("downloading %s", url)
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    fh.write(chunk)
    return dest


def decompress(path: Path) -> bytes:
    if path.read_bytes()[:2] == b"\x1f\x8b":
        with gzip.open(path, "rb") as fh:
            return fh.read()
    if path.read_bytes()[:4] == b"\x28\xb5\x2f\xfd":  # zstd magic
        out = subprocess.run(
            ["zstdcat", "-T0", str(path)], capture_output=True, check=True
        )
        return out.stdout
    # Possibly plain XML (very unusual) — let ElementTree tell us later.
    return path.read_bytes()


def primary_path_from_repomd(repomd: bytes) -> str | None:
    root = ET.fromstring(repomd)
    # repomd declares a default namespace; use a wildcard lookup to be robust to
    # both namespaced and plain-XML variants.
    for data in root.iter():
        if _local(data.tag) != "data":
            continue
        if data.get("type") == "primary":
            for child in data:
                if _local(child.tag) == "location":
                    return child.get("href")
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(obj) -> list:
    return list(obj) if obj is not None else []


def _find(obj, local: str):
    """Return the first child element whose local tag equals `local`."""
    if obj is None:
        return None
    for child in obj:
        if _local(child.tag) == local:
            return child
    return None


def _text(obj, tag: str, ns: str = "") -> str:
    el = _find(obj, tag)
    return (el.text or "").strip() if el is not None else ""


def _version(ver_el) -> str:
    """Build epoch:version-release string from an rpm:version element."""
    if ver_el is None:
        return ""
    epoch = ver_el.get("epoch") or "0"
    version = ver_el.get("ver") or "0"
    release = ver_el.get("rel") or ""
    return f"{epoch}:{version}-{release}" if release else f"{epoch}:{version}"


def iter_packages(xml_bytes: bytes) -> Iterator[ET.Element]:
    """Yield each ``<package>`` element with minimal parser reset."""
    # We strip the heavy inner text only where needed; use iterparse to stream.
    for event, elem in ET.iterparse(io.BytesIO(xml_bytes), events=("end",)):
        if _local(elem.tag) == "package":
            yield elem
            elem.clear()


def parse_primary(xml_bytes: bytes) -> list[dict]:
    """Return one record per *binary* RPM (compact, hashable)."""
    records: list[dict] = []
    for pkg in iter_packages(xml_bytes):
        name = _text(pkg, "name")
        arch = _text(pkg, "arch")
        version = _version(_find(pkg, "version"))
        source = ""
        summary = _text(pkg, "summary")
        buildtime = _text(pkg, "time")  # this is always present w/ build attr?

        frmt = _find(pkg, "format")
        license_ = _text(frmt, "license")
        group = _text(frmt, "group")
        vendor = _text(frmt, "vendor")
        sourcerpm_el = frmt.find(f"{{{RPM_NS}}}sourcerpm") if frmt is not None else None
        if sourcerpm_el is not None and sourcerpm_el.text:
            source = sourcerpm_el.text.strip()
            # "glibc-2.28-1.src.rpm" -> source = "glibc-2.28-1" -> name "glibc"

        provides: list[str] = []
        requires: list[str] = []
        if frmt is not None:
            for prov_container in frmt.findall(f"{{{RPM_NS}}}provides"):
                for entry in prov_container:
                    pn = (entry.get("name") or "").strip()
                    if pn:
                        provides.append(pn)
            for req_container in frmt.findall(f"{{{RPM_NS}}}requires"):
                for entry in req_container:
                    rn = (entry.get("name") or "").strip()
                    if rn:
                        requires.append(rn)

        records.append(
            {
                "name": name,
                "arch": arch,
                "version": version,
                "source": source,
                "license": license_,
                "summary": summary,
                "group": group,
                "vendor": vendor,
                "provides": provides,
                "requires": requires,
                "buildtime": buildtime,
            }
        )
    return records


def source_name_from_rpm(src_rpm: str) -> str:
    """`python3-libs-3.9.16-1.oe2403.src.rpm` -> `python3-libs`."""
    if not src_rpm:
        return ""
    base = src_rpm.split("/")[-1]
    base = re.sub(r"\.src\.rpm$", "", base)
    # The source RPM filename is "<name>-<version>-<release>". Source names often
    # contain hyphens themselves (e.g. 389-ds-base), so we only strip the final
    # two hyphen-separated fields, which are version and release.
    parts = base.rsplit("-", 2)
    if len(parts) == 3:
        # Release starts with a digit or has a digit-dot (e.g. 1.oe2609).
        if re.match(r"^[0-9]", parts[-1]) or re.match(r"^[0-9]", parts[-2]):
            return parts[0]
    # Fallback: the name is whatever precedes the last "-".
    return base.rsplit("-", 1)[0]


def build_source_records(records: list[dict]) -> dict[str, dict]:
    """Aggregate binary records into source-package records.

    Returns {source_name: {version, arches, groups, summary, license, provides,
    provides_set, requires_set, binaries, reverse}}.
    """
    src: dict[str, dict] = {}
    reverse: dict[str, int] = defaultdict(int)

    for rec in records:
        sname = source_name_from_rpm(rec["source"]) or rec["name"]
        sname = sname.rstrip()
        entry = src.setdefault(
            sname,
            {
                "name": sname,
                "version": rec["version"],
                "arches": [],
                "groups": [],
                "summary": rec["summary"],
                "license": rec["license"],
                "provides": [],
                "requires": [],
                "provides_set": set(),
                "binaries": [],
                "reverse": 0,
            },
        )
        # update repos can carry several versions of one source; keep the newest
        if version_compare(rec["version"], entry["version"]) > 0:
            entry["version"] = rec["version"]
        if rec["arch"] not in entry["arches"]:
            entry["arches"].append(rec["arch"])
        if rec["group"] and rec["group"] not in entry["groups"]:
            entry["groups"].append(rec["group"])
        if not entry["summary"] and rec["summary"]:
            entry["summary"] = rec["summary"]
        if rec["license"] and not entry["license"]:
            entry["license"] = rec["license"]
        entry["binaries"].append(rec["name"])
        entry["provides"].extend(rec["provides"])
        entry["requires"].extend(rec["requires"])
        for prov in rec["provides"]:
            entry["provides_set"].add(prov)

        # Reverse-dependency: a binary `requires` a provides-name of another pkg.

    # Second pass: count reverse deps using a global provides -> source map.
    provide_to_src: dict[str, set[str]] = defaultdict(set)
    for sname, entry in src.items():
        for prov in entry["provides_set"]:
            # Normalise provides like "libc.so.6()(64bit)" -> keep the name part.
            key = prov.split("(")[0]
            provide_to_src[key].add(sname)

    for sname, entry in src.items():
        reverse_sources: set[str] = set()
        for req in entry["requires"]:
            key = req.split("(")[0]
            for dep_src in provide_to_src.get(key, ()):
                if dep_src != sname:
                    reverse_sources.add(dep_src)
        src[sname]["reverse"] = len(reverse_sources)

    for entry in src.values():
        entry["provides"] = list(dict.fromkeys(entry["provides"]))
        entry["provides_set"] = list(entry["provides_set"])

    return src


def collect_release(
    repomd_url: str,
    cache_dir: Path,
    arch_field: str = "x86_64",
    *,
    light: bool = False,
) -> dict[str, dict]:
    """Fetch and parse a whole release from its repomd URL.

    `repomd_url` points at ``.../{release}/{target}/{arch}/repodata/repomd.xml``.
    """
    import hashlib
    import tempfile

    key = hashlib.sha256(repomd_url.encode()).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    repomd_path = cache_dir / f"{key}_repomd.xml"
    dl = download(repomd_url, repomd_path)
    repomd = dl.read_bytes()
    href = primary_path_from_repomd(repomd)
    if not href:
        raise ValueError(f"no primary entry in {repomd_url}")

    # The location href (e.g. "repodata/<sha>-primary.xml.zst") is relative to
    # the repository root (the directory that contains the repodata folder).
    repo_base = repomd_url.rsplit("/repodata/", 1)[0]
    primary_url = f"{repo_base}/{href}"
    primary_name = href.split("/")[-1]
    primary_path = cache_dir / primary_name
    if not primary_path.exists() or primary_path.stat().st_size == 0:
        download(primary_url, primary_path)
    LOG.info("parsing %s (%d bytes)", primary_name, primary_path.stat().st_size)
    data = decompress(primary_path)
    if light:
        # Fast path: versions/summary only (no provides/requires/reverse graph).
        result: dict[str, dict] = {}
        for rec in parse_primary(data):
            sname = source_name_from_rpm(rec["source"]) or rec["name"]
            entry = result.setdefault(
                sname,
                {"version": rec["version"], "arches": [], "summary": rec["summary"], "license": rec["license"]},
            )
            if version_compare(rec["version"], entry["version"]) > 0:
                entry["version"] = rec["version"]
            if rec["arch"] not in entry["arches"]:
                entry["arches"].append(rec["arch"])
            if not entry["summary"] and rec["summary"]:
                entry["summary"] = rec["summary"]
        LOG.info("release %s -> %d source packages (light)", repo_base, len(result))
        return result
    records = parse_primary(data)
    src = build_source_records(records)
    LOG.info("release %s -> %d source packages", repo_base, len(src))
    return src
