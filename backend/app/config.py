"""Central configuration for the openEuler package-governance service."""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]          # pkg-governance/
BACKEND_DIR = PROJECT_ROOT / "backend"
DATA_DIR = BACKEND_DIR / "data"
RULES_DIR = DATA_DIR / "rules"
CACHE_DIR = DATA_DIR / "cache"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
# Serve the Vite production build when present, else the (dev) source dir.
_built = FRONTEND_DIR / "dist"
if _built.exists():
    FRONTEND_DIR = _built

# Ensure runtime directories exist.
for _d in (DATA_DIR, RULES_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# openEuler upstream (public package-repository metadata)
# ---------------------------------------------------------------------------
OPEN_EULER_MIRROR = os.getenv("OPEN_EULER_MIRROR", "https://repo.openeuler.org")
# Canonical daily-build / RC host for pre-GA innovation streams.
OPEN_EULER_DAILYBUILD = os.getenv(
    "OPEN_EULER_DAILYBUILD", "https://dailybuild.openeuler.openatom.cn/dailybuild"
)
OPEN_EULER_ARCH = os.getenv("OPEN_EULER_ARCH", "x86_64")
# Repo + arch variant inside a release ("everything", "standard", "baseos"...).
OPEN_EULER_TARGETS = os.getenv("OPEN_EULER_TARGETS", "everything").split(",")
# Repositories that together define a release's package set. A source package's
# binary version is the newest among the "binary" repos; "source" repos confirm
# source availability; "debuginfo" confirms debug-info availability.
REPO_SOURCES = [
    {"name": "OS", "path": "OS", "kind": "binary"},
    {"name": "everything", "path": "everything", "kind": "binary"},
    {"name": "EPOL", "path": "EPOL/main", "kind": "binary"},
    {"name": "update", "path": "update", "kind": "binary"},
    {"name": "debuginfo", "path": "debuginfo", "kind": "debug"},
    {"name": "source", "path": "source", "kind": "source"},
    {"name": "update-source", "path": "update/source", "kind": "source"},
]
# Explicit overrides: stream -> release/repo root. If set, these take precedence
# over auto-discovery (useful to pin a pre-GA innovation release).
OPEN_EULER_LTS_RELEASE = os.getenv("OPEN_EULER_LTS_RELEASE", "")
OPEN_EULER_INNOVATION_RELEASE = os.getenv("OPEN_EULER_INNOVATION_RELEASE", "")
# Which LTS family to expose in the stream switcher (e.g. "24.03").
DEFAULT_LTS_FAMILY = os.getenv("DEFAULT_LTS_FAMILY", "24.03")
# Include dated daily builds for DevStation, or only stable RC builds.
INCLUDE_DEVSTATION_DAILY = os.getenv("INCLUDE_DEVSTATION_DAILY", "1") == "1"

# ---------------------------------------------------------------------------
# activity source (GitCode / AtomGit public API)
# ---------------------------------------------------------------------------
ACTIVITY_API_BASE = os.getenv("ACTIVITY_API_BASE", "https://api.gitcode.com/api/v5")
ACTIVITY_TOKEN = os.getenv("ACTIVITY_TOKEN", "")  # optional; raises rate limits
ACTIVITY_ORG = os.getenv("ACTIVITY_ORG", "src-openeuler")  # package source repos
ACTIVITY_CONCURRENCY = int(os.getenv("ACTIVITY_CONCURRENCY", "4"))
ACTIVITY_TIMEOUT = float(os.getenv("ACTIVITY_TIMEOUT", "20"))

# ---------------------------------------------------------------------------
# Ubuntu baseline (public archive metadata)
# ---------------------------------------------------------------------------
UBUNTU_ARCHIVE = os.getenv("UBUNTU_ARCHIVE", "https://archive.ubuntu.com/ubuntu")
UBUNTU_ARCH = os.getenv("UBUNTU_ARCH", "amd64")
UBUNTU_COMPONENTS = os.getenv("UBUNTU_COMPONENTS", "main,universe").split(",")

# ---------------------------------------------------------------------------
# SUSE baseline (optional; used only when a comparator adapter is enabled)
# ---------------------------------------------------------------------------
OPENSUSE_BASE = os.getenv("OPENSUSE_BASE", "https://download.opensuse.org")

# ---------------------------------------------------------------------------
# Runtime knobs
# ---------------------------------------------------------------------------
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "1") == "1"
# How many package-level activity collections to attempt during a live run
# before stopping (0 = every package; the activity cache makes reruns
# incremental so a full sweep resumes where it left off).
ACTIVITY_SAMPLE_LIMIT = int(os.getenv("ACTIVITY_SAMPLE_LIMIT", "0"))

# Relative (name) or absolute path to the generated cache JSON.
PACKAGES_CACHE = CACHE_DIR / "packages.json"
REPO_META_CACHE = CACHE_DIR / "repo_metadata"
UBUNTU_CACHE = CACHE_DIR / "ubuntu.json"
STREAM_VERSIONS_CACHE = CACHE_DIR / "stream_versions.json"
ACTIVITY_CACHE = CACHE_DIR / "activity.json"

# Cache-control header value so the SPA does not stale the single digest payload.
HTTP_CACHE_SECONDS = int(os.getenv("HTTP_CACHE_SECONDS", "60"))
