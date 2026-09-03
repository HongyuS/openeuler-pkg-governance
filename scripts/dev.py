"""Dev-server launcher with instance discovery and port-conflict management.

Usage (via make or directly with the project venv):

    python scripts/dev.py [--port 8000] [--host 127.0.0.1]
    python scripts/dev.py --status        # show running instances
    python scripts/dev.py --stop          # gracefully stop running instances
    python scripts/dev.py --restart       # stop, then start again
    python scripts/dev.py --any-port      # shift to the next free port on conflict

Instance discovery combines two signals:
* who is LISTENing on the port        (``lsof`` / socket bind probe),
* which processes are our server      (``pgrep -f`` on the uvicorn target).

Starting is idempotent: if our own server already listens on the port, the
script health-checks it and exits 0 instead of spawning a duplicate.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
VENV_PY = ROOT / ".venv" / "bin" / "python"
SERVER_TARGET = "app.server:app"
DEFAULT_PORT = int(os.getenv("PORT", "8000"))
DEFAULT_HOST = os.getenv("HOST", "127.0.0.1")


# ---------------------------------------------------------------------------
# discovery helpers
# ---------------------------------------------------------------------------
def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def listening_pids(port: int) -> list[int]:
    """PIDs of processes LISTENing on TCP port (lsof; empty if unknown)."""
    out = _run(["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"])
    return [int(p) for p in out.split() if p.isdigit()]


def server_pids() -> list[int]:
    """All pids whose command line runs our uvicorn target (any port)."""
    out = _run(["pgrep", "-f", f"uvicorn {SERVER_TARGET}"])
    me = os.getpid()
    return [int(p) for p in out.split() if p.isdigit() and int(p) != me]


def port_free(port: int) -> bool:
    """True if no one is bound to the TCP port (bind-probe, works everywhere)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
        else:
            return True


def describe_pids(pids: list[int]) -> str:
    """Return ps command lines for the given pids, or a placeholder if unavailable."""
    rows = _run(["ps", "-o", "pid=,command=", "-p", ",".join(map(str, pids))])
    return rows or "(process detail unavailable)"


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------
def stop(pids: list[int], timeout: float = 5.0) -> None:
    """SIGTERM the given pids, wait up to timeout, then SIGKILL any survivors."""
    if not pids:
        print("no running dev-server instance")
        return
    for pid in pids:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not server_pids():
            break
        time.sleep(0.2)
    for pid in server_pids():  # anything left gets SIGKILL
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"force-killed pid {pid}")
        except ProcessLookupError:
            pass
    print("stopped: " + ", ".join(map(str, pids)))


def health(url: str, timeout: float = 30.0) -> bool:
    """Poll /api/health until it answers 200 or the deadline passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def ensure_ui() -> None:
    """Build the frontend with pnpm unless frontend/dist already exists."""
    if (ROOT / "frontend" / "dist").is_dir():
        return
    print("frontend/dist missing — building UI (pnpm)…")
    subprocess.run(["pnpm", "install"], cwd=ROOT / "frontend", check=True)
    subprocess.run(["pnpm", "build"], cwd=ROOT / "frontend", check=True)


def start(host: str, port: int, *, any_port: bool) -> int:
    """Launch the dev server on host:port, handling port conflicts and idempotent start."""
    bound = listening_pids(port)
    ours = server_pids()
    if bound:
        if all(pid in ours for pid in bound):
            url = f"http://127.0.0.1:{port}"
            pids = ",".join(map(str, bound))
            print(f"dev-server already running on {url} (pid {pids})")
            return 0
        if not any_port:
            print(
                f"ERROR: port {port} is taken by another process:\n{describe_pids(bound)}\n"
                "  use --restart to replace our instance, --any-port to shift,"
                " or --stop first"
            )
            return 1
        while not port_free(port):
            port += 1
        print(f"port busy — shifted to {port}")
    elif ours:
        print(f"note: another instance runs elsewhere (pids {ours})")

    ensure_ui()
    env = {**os.environ, "HOST": host, "PORT": str(port), "PYTHONPATH": str(BACKEND)}
    cmd = [
        str(VENV_PY if VENV_PY.exists() else sys.executable),
        "-m",
        "uvicorn",
        SERVER_TARGET,
        "--host",
        host,
        "--port",
        str(port),
    ]
    display = f"http://127.0.0.1:{port}" if host in ("0.0.0.0", "::") else f"http://{host}:{port}"  # ruff: ignore[hardcoded-bind-all-interfaces] — 仅展示分支判断，非实际绑定
    print(f"starting {SERVER_TARGET}  ->  {display}")
    proc = subprocess.Popen(cmd, cwd=BACKEND, env=env)
    try:
        if not health(display.rstrip("/") + "/api/health"):
            print("WARNING: server did not report healthy within 30s; logs above may explain")
            proc.terminate()
            return 1
        print("healthy. Ctrl-C to stop.")
        return proc.wait()
    except KeyboardInterrupt:
        print("\nstopping…")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 0


def status() -> int:
    """Print running dev-server instances, or a not-running notice."""
    ours = server_pids()
    if not ours:
        print("dev-server: not running")
        return 0
    print("dev-server running (pids " + ", ".join(map(str, ours)) + "):")
    print(describe_pids(ours))
    return 0


def main() -> int:
    """Parse CLI arguments and dispatch to status, stop, or start."""
    ap = argparse.ArgumentParser(description="pkg-governance dev server launcher")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--status", action="store_true", help="show running instances")
    ap.add_argument("--stop", action="store_true", help="stop running instances")
    ap.add_argument("--restart", action="store_true", help="stop then start")
    ap.add_argument(
        "--any-port",
        action="store_true",
        help="if the requested port is taken by a foreign process, use the next free port",
    )
    args = ap.parse_args()

    if args.status:
        return status()
    if args.stop:
        stop(server_pids())
        return 0
    if args.restart:
        stop(server_pids())
    return start(args.host, args.port, any_port=args.any_port)


if __name__ == "__main__":
    raise SystemExit(main())
