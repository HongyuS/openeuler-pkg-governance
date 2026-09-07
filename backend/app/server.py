"""FastAPI application exposing the package-governance REST API.

The platform reads a self-contained ``packages.json`` cache (produced either by
the live collectors or by the seed script), serves an aggregated ``/api/digest``
payload for the interactive single-page dashboard, and mounts the static SPA.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.engine import compare
from app.models import VersionRow
from app.utils import LOG, setup_logging

setup_logging()

app = FastAPI(title="openEuler Package Governance", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Dataset state
# ---------------------------------------------------------------------------
STATE: dict[str, Any] = {
    "packages": [],
    "meta": {},
    "stream_versions": {},
    "loaded_mtime": 0.0,
}


def _load_cache(force: bool = False) -> None:
    path = config.PACKAGES_CACHE
    if not path.exists():
        return
    mtime = path.stat().st_mtime
    if not force and mtime == STATE["loaded_mtime"] and STATE["packages"]:
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        STATE["packages"] = data.get("packages", [])
        STATE["meta"] = data.get("meta", {})
        STATE["loaded_mtime"] = mtime
        LOG.info("loaded %d packages from %s", len(STATE["packages"]), path)
    except Exception as exc:  # ruff: ignore[blind-except]
        LOG.warning("could not load %s: %s", path, exc)
    if config.STREAM_VERSIONS_CACHE.exists():
        try:
            STATE["stream_versions"] = json.loads(config.STREAM_VERSIONS_CACHE.read_text(encoding="utf-8"))
        except Exception as exc:  # ruff: ignore[blind-except]
            LOG.warning("could not load stream versions: %s", exc)


@app.on_event("startup")
def _startup() -> None:
    _load_cache(force=True)


def _default_pair() -> dict[str, str]:
    return STATE["meta"].get("default", {"openEuler_LTS": "", "openEuler_innovation": ""})


def _stream_ids(lts: str | None, innov: str | None) -> tuple[str, str]:
    d = _default_pair()
    return (lts or d.get("openEuler_LTS", ""), innov or d.get("openEuler_innovation", ""))


def _ubuntu_baselines() -> dict[str, dict]:
    m = STATE["meta"]
    return {"ubuntu_LTS": m.get("ubuntu_lts", {}), "ubuntu_interim": m.get("ubuntu_interim", {})}


def _sv_rec(stream: str, name: str | None) -> dict:
    """One package's stream_versions entry.

    Tolerates the legacy ``{name: "version"}`` format (only the version is usable then).
    """
    if not name:
        return {}
    rec = STATE["stream_versions"].get(stream, {}).get(name)
    if isinstance(rec, str):
        return {"version": rec}
    return rec or {}


def _registry_fallback(p: dict) -> Any:
    """PyPI/npm registry latest as a fallback baseline row (None if inapplicable).

    Used only when the package has no Ubuntu counterpart: pip/npm modules whose
    latest version lives on the registry, not in any distro archive.
    """
    py = p.get("python") or {}
    if py.get("kind") == "pip_module" and py.get("pypi_latest"):
        return VersionRow(distro="pypi", stream="PyPI", version=str(py["pypi_latest"]), source="pypi")
    npm = p.get("npm") or {}
    if npm.get("kind") == "npm_module" and npm.get("npm_latest"):
        return VersionRow(distro="npm", stream="npm", version=str(npm["npm_latest"]), source="npm")
    return None


def _apply_stream(p: dict, lts: str, innov: str) -> dict[str, Any]:
    """Recompute the openEuler version columns, lag and repo tags.

    For a selected stream pair. Tags follow the LTS stream, falling back to the
    innovation stream, then to the build-time snapshot in packages.json.
    """
    name = str(p.get("name") or "")
    lts_rec = _sv_rec(lts, name)
    innov_rec = _sv_rec(innov, name)
    oe = {
        "openEuler_LTS": lts_rec.get("version", ""),
        "openEuler_innovation": innov_rec.get("version", ""),
    }
    comp = compare.build_comparison(name, oe, _ubuntu_baselines(), fallback=_registry_fallback(p))
    sv_rec = lts_rec or innov_rec
    return {
        "versions": {r.stream: r.version for r in comp.baselines},
        "baselines": [vars(r) for r in comp.baselines],
        "lagging": comp.lagging,
        "lag_behind_ubuntu_lts": comp.lag_behind_ubuntu_lts,
        "lag_behind_ubuntu_interim": comp.lag_behind_ubuntu_interim,
        "latest_upstream": comp.latest_upstream,
        "latest_upstream_source": comp.latest_upstream_source,
        "lag_degree": comp.lag_degree,
        "lag_notes": comp.lag_notes,
        **{
            k: sv_rec.get(k, p.get(k, default))
            for k, default in (
                ("in_epol", False),
                ("in_update", False),
                ("latest_repo", ""),
                ("has_source", False),
                ("has_debug", False),
                ("in_iso", False),
                ("iso_baseline", False),
                ("iso_excluded", False),
                ("iso_desktop", False),
                ("iso_edge", False),
            )
        },
    }


def _summary(lts: str | None = None, innov: str | None = None) -> dict[str, Any]:
    lts, innov = _stream_ids(lts, innov)
    pkgs = STATE["packages"]
    rows = [_apply_stream(p, lts, innov) for p in pkgs]
    dist = {
        "total": len(pkgs),
        "p_level": _count(pkgs, "p_level"),
        "importance": _count(pkgs, "importance"),
        "activity_grade": _count(pkgs, "activity_grade"),
        "disposal": _count(pkgs, "disposal"),
        "outdated": sum(1 for r in rows if r["lagging"]),
        "sunset_candidate": sum(1 for p in pkgs if p.get("governance", {}).get("sunset_candidate")),
        "unmaintained_risk": sum(
            1 for p in pkgs if "长期未更新" in " ".join(p.get("governance", {}).get("maintenance_notes", []))
        ),
        "special": sum(1 for p in pkgs if p.get("special")),
    }
    effort_pd = round(sum(p.get("governance", {}).get("effort_person_days", 0) for p in pkgs), 1)
    effort_py = round(sum(p.get("governance", {}).get("effort_person_years", 0) for p in pkgs), 3)
    effort_note = _effort_note(effort_py)
    lag_map = {p.get("name"): r for p, r in zip(pkgs, rows, strict=False)}
    top_lagging = sorted(
        (p for p in pkgs if lag_map.get(p.get("name"), {}).get("lagging")),
        key=lambda p: p.get("governance", {}).get("score", 0),
        reverse=True,
    )[:10]
    sunset = sorted(
        (p for p in pkgs if p.get("governance", {}).get("sunset_candidate")),
        key=lambda p: p.get("governance", {}).get("score", 0),
        reverse=True,
    )[:10]
    return {
        "distributions": dist,
        "effort": {"person_days": effort_pd, "person_years": effort_py, "note": effort_note},
        "top_lagging": [_light(p, lag_map.get(p.get("name"), {})) for p in top_lagging],
        "top_sunset": [_light(p, lag_map.get(p.get("name"), {})) for p in sunset],
        "streams": STATE["meta"].get("streams", []),
        "baselines": STATE["meta"].get("baselines", {}),
        "data_date": STATE["meta"].get("data_date", ""),
        "selected": {"openEuler_LTS": lts, "openEuler_innovation": innov},
    }


def _effort_note(py: float) -> str:
    # Rough narrative equivalent of the plan's capacity reference.
    return f"≈{py:.1f} 人年/年（按 240 人日/人年折算）"


def _count(pkgs: list, key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in pkgs:
        value = p.get("governance", {}).get(key)
        if value:
            out[value] = out.get(value, 0) + 1
    return out


def _light(p: dict, stream_row: dict | None = None) -> dict[str, Any]:
    gov = p.get("governance", {})
    comp = p.get("comparison", {})
    versions = stream_row.get("versions") if stream_row else None
    if versions is None:
        versions = {r["stream"]: r["version"] for r in comp.get("baselines", [])}
    lagging = stream_row.get("lagging") if stream_row else comp.get("lagging")
    return {
        "name": p.get("name"),
        "p_level": gov.get("p_level"),
        "grade": gov.get("activity_grade"),
        "importance": gov.get("importance"),
        "disposal": gov.get("disposal"),
        "score": gov.get("score"),
        "lagging": lagging,
        "versions": versions,
    }


@app.get("/api/health")
def health() -> dict:
    """Report service health and the loaded package count."""
    return {"status": "ok", "packages": len(STATE["packages"])}


@app.get("/api/meta")
def meta() -> dict:
    """Return the dataset metadata."""
    return {"meta": STATE["meta"], "config": {"version": "1.0"}}


@app.get("/api/streams")
def streams() -> dict:
    """Return the available streams and the default stream pair."""
    _load_cache()
    return {
        "streams": STATE["meta"].get("streams", []),
        "default": _default_pair(),
    }


@app.get("/api/summary")
def summary(lts: str = Query(""), innov: str = Query("")) -> dict:
    """Return governance summary counts for the selected stream pair."""
    _load_cache()
    return _summary(lts or None, innov or None)


@app.get("/api/digest")
def digest(lts: str = Query(""), innov: str = Query("")) -> dict:
    """Return the full digest: metadata, summary and per-package rows."""
    _load_cache()
    pkgs = STATE["packages"]
    lts, innov = _stream_ids(lts or None, innov or None)
    rows = [_apply_stream(p, lts, innov) for p in pkgs]
    return {
        "meta": STATE["meta"],
        "summary": {
            "distributions": dict(
                {
                    "total": len(pkgs),
                    "p_level": _count(pkgs, "p_level"),
                    "importance": _count(pkgs, "importance"),
                    "activity_grade": _count(pkgs, "activity_grade"),
                    "disposal": _count(pkgs, "disposal"),
                    "outdated": sum(1 for r in rows if r["lagging"]),
                    "sunset_candidate": sum(1 for p in pkgs if p.get("governance", {}).get("sunset_candidate")),
                    "special": sum(1 for p in pkgs if p.get("special")),
                }.items()
            ),
            "selected": {"openEuler_LTS": lts, "openEuler_innovation": innov},
        },
        "packages": [
            {
                "name": p.get("name"),
                "summary": p.get("summary", "")[:220],
                "p_level": p.get("governance", {}).get("p_level"),
                "grade": p.get("governance", {}).get("activity_grade"),
                "importance": p.get("governance", {}).get("importance"),
                "disposal": p.get("governance", {}).get("disposal"),
                "lagging": r["lagging"],
                "lag_behind_ubuntu_lts": r["lag_behind_ubuntu_lts"],
                "lag_behind_ubuntu_interim": r["lag_behind_ubuntu_interim"],
                "sunset_candidate": p.get("governance", {}).get("sunset_candidate"),
                "special": p.get("special"),
                "sig": p.get("sig", ""),
                "reverse_deps": p.get("governance", {}).get("reverse_deps"),
                "score": p.get("governance", {}).get("score"),
                "effort_pd": p.get("governance", {}).get("effort_person_days"),
                "effort_py": p.get("governance", {}).get("effort_person_years"),
                "has_source": r["has_source"],
                "has_debug": r["has_debug"],
                "in_epol": r["in_epol"],
                "in_update": r["in_update"],
                "latest_repo": r["latest_repo"],
                "in_iso": r["in_iso"],
                "iso_baseline": r["iso_baseline"],
                "iso_excluded": r["iso_excluded"],
                "iso_desktop": r["iso_desktop"],
                "iso_edge": r["iso_edge"],
                "python": {
                    k: p.get("python", {}).get(k, "")
                    for k in (
                        "kind",
                        "pypi_name",
                        "pypi_latest",
                        "pypi_stale",
                        "compat_ok",
                        "system_python",
                    )
                },
                "npm": {
                    k: p.get("npm", {}).get(k, "")
                    for k in ("kind", "npm_name", "npm_latest", "npm_stale", "npm_deprecated")
                },
                "versions": r["versions"],
                "last_commit": p.get("activity", {}).get("last_commit", ""),
                "open_backlog": (
                    p.get("activity", {}).get("open_issues", 0) + p.get("activity", {}).get("open_prs", 0)
                ),
            }
            for p, r in zip(pkgs, rows, strict=False)
        ],
    }


@app.get("/api/packages")
def list_packages(
    q: str = Query(""),
    p_level: str = Query(""),
    grade: str = Query(""),
    importance: str = Query(""),
    disposal: str = Query(""),
    lagging: bool | None = Query(None),
    sunset: bool | None = Query(None),
    pmin: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=1000),
    sort: str = Query("score"),
    order: str = Query("desc"),
    lts: str = Query(""),
    innov: str = Query(""),
) -> JSONResponse:
    """Return a filtered, sorted and paginated package list."""
    _load_cache()
    items = _filter(
        STATE["packages"],
        q=q,
        p_level=p_level,
        grade=grade,
        importance=importance,
        disposal=disposal,
        lagging=lagging,
        sunset=sunset,
    )
    items = _sort(items, sort, order)
    total = len(items)
    start = (pmin - 1) * per_page
    page = items[start : start + per_page]
    lts, innov = _stream_ids(lts or None, innov or None)
    rows = {p.get("name"): _apply_stream(p, lts, innov) for p in page}
    return JSONResponse(
        {
            "total": total,
            "page": pmin,
            "per_page": per_page,
            "items": [_light(p, rows.get(p.get("name"))) for p in page],
        }
    )


@app.get("/api/packages/{name}")
def get_package(name: str, lts: str = Query(""), innov: str = Query("")) -> dict:
    """Return one package's full record with recomputed stream columns."""
    _load_cache()
    for p in STATE["packages"]:
        if p.get("name") == name:
            out = dict(p)
            lts, innov = _stream_ids(lts or None, innov or None)
            row = _apply_stream(p, lts, innov)
            for k in (
                "has_source",
                "has_debug",
                "in_epol",
                "in_update",
                "latest_repo",
                "in_iso",
                "iso_baseline",
                "iso_excluded",
                "iso_desktop",
                "iso_edge",
            ):
                out[k] = row[k]
            out["open_euler"] = dict(
                {
                    "openEuler_LTS": row["versions"].get("openEuler_LTS", ""),
                    "openEuler_innovation": row["versions"].get("openEuler_innovation", ""),
                }.items()
            )
            out["versions"] = row["baselines"]
            comp = dict(out.get("comparison", {}))
            comp["baselines"] = row["baselines"]
            comp["lagging"] = row["lagging"]
            comp["lag_behind_ubuntu_lts"] = row["lag_behind_ubuntu_lts"]
            comp["lag_behind_ubuntu_interim"] = row["lag_behind_ubuntu_interim"]
            comp["latest_upstream"] = row["latest_upstream"]
            comp["latest_upstream_source"] = row["latest_upstream_source"]
            comp["lag_degree"] = row["lag_degree"]
            comp["lag_notes"] = row["lag_notes"]
            out["comparison"] = comp
            return out
    raise HTTPException(status_code=404, detail=f"package {name} not found")


@app.get("/api/packages/{name}/activity")
def activity_series(name: str) -> dict:
    """Return a package's activity signals, 404 if the package is unknown."""
    _load_cache()
    for p in STATE["packages"]:
        if p.get("name") == name:
            sig = p.get("activity", {})
            return {
                "name": name,
                "monthly": sig.get("monthly", {}),
                "last_commit": sig.get("last_commit", ""),
                "open_issues": sig.get("open_issues", 0),
                "open_prs": sig.get("open_prs", 0),
                "closed_prs": sig.get("closed_prs", 0),
                "closed_issues": sig.get("closed_issues", 0),
                "source": sig.get("source", "none"),
            }
    raise HTTPException(status_code=404, detail=f"package {name} not found")


@app.get("/api/reload")
def reload_data() -> dict:
    """Force-reload the dataset cache and report the loaded package count."""
    _load_cache(force=True)
    return {"loaded": len(STATE["packages"])}


def _filter(pkgs, *, q, p_level, grade, importance, disposal, lagging, sunset) -> list:
    q = q.strip().lower()
    out = []
    for p in pkgs:
        gov = p.get("governance", {})
        comp = p.get("comparison", {})
        if q and q not in p.get("name", "").lower() and q not in p.get("summary", "").lower():
            continue
        if p_level and gov.get("p_level") != p_level:
            continue
        if grade and gov.get("activity_grade") != grade:
            continue
        if importance and gov.get("importance") != importance:
            continue
        if disposal and gov.get("disposal") != disposal:
            continue
        if lagging is not None and bool(comp.get("lagging")) != lagging:
            continue
        if sunset is not None and bool(gov.get("sunset_candidate")) != sunset:
            continue
        out.append(p)
    return out


def _sort(pkgs, sort, order) -> list:
    rev = order != "asc"

    def keyfn(p):
        gov = p.get("governance", {})
        if sort == "name":
            return p.get("name", "")
        if sort == "effort":
            return gov.get("effort_person_days", 0)
        if sort == "reverse":
            return gov.get("reverse_deps", 0)
        if sort == "grade":
            return _grade_order(gov.get("activity_grade"))
        if sort == "p_level":
            return _p_level_order(gov.get("p_level"))
        return gov.get("score", 0)

    return sorted(pkgs, key=keyfn, reverse=rev)


def _grade_order(g):
    return {"A": 4, "B": 3, "C": 2, "D": 1, "N/A": 0}.get(g, 0)


def _p_level_order(p):
    return {"P0": 3, "P1": 2, "P2": 1}.get(p, 0)


# Static frontend (served at the root).
if config.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")


def run() -> None:
    """Run the API server with uvicorn."""
    import uvicorn

    uvicorn.run("app.server:app", host=config.HOST, port=config.PORT, reload=False)


if __name__ == "__main__":
    run()
