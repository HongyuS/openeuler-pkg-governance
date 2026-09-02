"""Optional openSUSE / SLE baseline adapter (off by default).

The plan compares openEuler against SUSE (Tumbleweed innovation + Leap/SLE
long-term) as a second reference. openSUSE publishes the same dnf repository
metadata (repodata/primary.xml.zst) under ``download.opensuse.org``, so the
reuse of ``app.collectors.repodata_parser`` is the intended implementation.

Enable by adding a "suse_leap"/"suse_tumbleweed" entry to ``baselines`` in
``scripts/build.py`` and pointing ``OPENSUSE_BASE`` at the distribution repo.
"""

from __future__ import annotations

from app import config
from app.collectors import repodata_parser
from app.utils import LOG


def collect(_baselines: tuple[str, str] | None = None) -> dict[str, dict]:
    """Return ``{suse_leap: {source: version}, suse_tumbleweed: {source: version}}``."""
    LOG.warning("SUSE adapter is a stub: enable OPENSUSE_BASE & stream mapping to use it.")
    return {}


def gather_release(project_url: str) -> dict[str, dict]:
    """Collect a single openSUSE release from its repo root URL."""
    base = config.OPENSUSE_BASE
    url = f"{base}/{project_url}/repodata/repomd.xml"
    return repodata_parser.collect_release(url, config.REPO_META_CACHE / "suse")
