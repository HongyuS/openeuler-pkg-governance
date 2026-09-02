"""Collect Ubuntu source-package versions for the LTS & interim baselines.

Ubuntu publishes the canonical source-package version inventory in the per-arch
``Packages`` index of each release's archive. We auto-detect the latest LTS
(even ``YY.04``) and the latest interim (non-LTS) release from ``dists/``, then
read the ``Source``/``Version`` fields so that openEuler can be compared against
real upstream activity.
"""

from __future__ import annotations

import re
import zlib
from pathlib import Path

from app import config
from app.utils import LOG, http_get

CODEPAT = re.compile(r'href="(?P<codename>[a-z]{3,})/"')


def _release_meta(codename: str) -> dict:
    resp = http_get(f"{config.UBUNTU_ARCHIVE}/dists/{codename}/Release", timeout=30)
    out: dict[str, str] = {}
    if resp.status_code != 200:
        return out
    for line in resp.text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _is_lts(meta: dict) -> bool:
    version = meta.get("Version", "")
    m = re.match(r"^(\d{2})\.(\d{2})$", version)
    if not m:
        return False
    year, minor = int(m.group(1)), int(m.group(2))
    # Ubuntu LTS releases are even-year YY.04.
    return year % 2 == 0 and minor == 4


def _ver_key(meta: dict) -> tuple:
    m = re.match(r"^(\d{2})\.(\d{2})$", meta.get("Version", ""))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def discover_baselines() -> tuple[str, str]:
    resp = http_get(config.UBUNTU_ARCHIVE + "/dists/", timeout=30)
    codenames = {m.group("codename") for m in CODEPAT.finditer(resp.text)}
    lts: list[tuple[str, tuple]] = []
    interim: list[tuple[str, tuple]] = []
    for cn in sorted(codenames):
        meta = _release_meta(cn)
        if not meta:
            continue
        key = _ver_key(meta)
        if key == (0, 0):
            continue
        if _is_lts(meta):
            lts.append((cn, key))
        else:
            interim.append((cn, key))
    lts.sort(key=lambda x: x[1])
    interim.sort(key=lambda x: x[1])
    return (lts[-1][0] if lts else ""), (interim[-1][0] if interim else "")


def _packages_url(codename: str, component: str) -> str:
    return (
        f"{config.UBUNTU_ARCHIVE}/dists/{codename}/{component}/"
        f"binary-{config.UBUNTU_ARCH}/Packages.gz"
    )


def _iter_packages(codename: str) -> dict[str, dict]:
    """Return {source_name: {version, package, section}} for main+universe."""
    result: dict[str, dict] = {}
    for component in config.UBUNTU_COMPONENTS:
        url = _packages_url(codename, component)
        resp = http_get(url, timeout=60)
        if resp.status_code != 200:
            LOG.warning("no Packages for %s/%s (%s)", codename, component, resp.status_code)
            continue
        try:
            text = zlib.decompress(resp.content, 16 + zlib.MAX_WBITS).decode("utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001
            LOG.warning("could not decompress %s: %s", url, exc)
            continue
        for block in re.split(r"\n\n", text):
            fields: dict[str, str] = {}
            for line in block.splitlines():
                if line.startswith(" ") or not line:
                    continue
                if ":" in line:
                    k, v = line.split(":", 1)
                    fields[k.strip()] = v.strip()
            src = fields.get("Source", "")
            if " " in src:
                src = src.split(" ")[0]
            src = src or fields.get("Package", "")
            if not src:
                continue
            rec = result.setdefault(
                src,
                {"version": fields.get("Version", ""), "arch": fields.get("Architecture", "")},
            )
            rec["version"] = fields.get("Version", rec["version"])
    return result


def collect(baselines: tuple[str, str] | None = None) -> dict[str, dict]:
    """Return {stream: {source_name: version}} and the {stream: codename} map."""
    import json

    if config.UBUNTU_CACHE.exists() and baselines is None:
        try:
            return json.loads(config.UBUNTU_CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass

    if not baselines:
        baselines = discover_baselines()
    lts_codename, interim_codename = baselines
    LOG.info("ubuntu baselines: LTS=%s interim=%s", lts_codename, interim_codename)

    versions: dict[str, dict[str, str]] = {}
    meta: dict[str, str] = {"ubuntu_LTS": lts_codename, "ubuntu_interim": interim_codename}

    for stream, codename in (("ubuntu_LTS", lts_codename), ("ubuntu_interim", interim_codename)):
        if not codename:
            versions[stream] = {}
            continue
        pkgs = _iter_packages(codename)
        versions[stream] = {name: rec["version"] for name, rec in pkgs.items()}
        LOG.info("ubuntu %s (%s): %d source packages", stream, codename, len(versions[stream]))

    result = {"versions": versions, "meta": meta}
    try:
        config.UBUNTU_CACHE.parent.mkdir(parents=True, exist_ok=True)
        config.UBUNTU_CACHE.write_text(json.dumps(result, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass
    return result
