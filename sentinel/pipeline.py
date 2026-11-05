"""Run the whole chain: composites → detection → jurisdiction → ranking → case files."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import shutil
import time
from contextlib import contextmanager

import geopandas as gpd
import numpy as np
import pandas as pd

from . import __version__, aoi, ancillary, composites, detect, evidence, imagery, jurisdiction, prioritise, raster, report
from .config import ROOT

log = logging.getLogger(__name__)


@contextmanager
def timed(timings: dict, step: str):
    t = time.time()
    yield
    timings[step] = timings.get(step, 0) + time.time() - t


def case_ids(cases: gpd.GeoDataFrame, prefix: str) -> list[str]:
    """Stable IDs: the same site in the same period always gets the same ID."""
    out = []
    for r in cases.itertuples():
        c = r.geometry.representative_point()
        h = hashlib.sha1(f"{round(c.x, -2)}:{round(c.y, -2)}:{r.period_after_key}".encode()).hexdigest()[:6]
        out.append(f"{prefix}-{r.period_after_key[-6:-2]}-{h}")
    return out


def run(cfg: dict, subset: tuple | None = None, force: bool = False) -> None:
    t_start, timings = time.time(), {}
    name = cfg["name"] + ("-subset" if subset else "")
    work, out = ROOT / "data" / name, ROOT / "output" / name
    work.mkdir(parents=True, exist_ok=True)
    periods = cfg["periods"]

    with timed(timings, "boundaries"):
        district = aoi.load_district(cfg)
        admin = aoi.admin_layers(cfg, district, ROOT / "data" / cfg["name"] / "admin.gpkg")
        gbox, poly, mask = aoi.analysis_grid(cfg, district, subset)
        geom4326 = poly.to_crs("EPSG:4326").geom

    # composites depend on these settings; change one and they are rebuilt
    tag = hashlib.sha1(json.dumps([cfg[k] for k in ("stac", "cloud_mask", "indices", "resolution_m")],
                                  sort_keys=True).encode()).hexdigest()[:8]
    stats, monthly, items, dates_used = {}, {}, {}, []
    for p in periods:
        scenes = work / f"scenes_{p.key}.json"
        sp, mp = work / f"stats_{p.key}_{tag}.tif", work / f"ndvi_monthly_{p.key}_{tag}.tif"
        if force:
            for f in (scenes, sp, mp):
                f.unlink(missing_ok=True)
        with timed(timings, "search"):
            items[p.key] = imagery.search(cfg, geom4326, p, scenes)
        used = imagery.thin(items[p.key], cfg["stac"]["max_dates_per_month"])
        dates_used.append(len(imagery.by_day(used)))
        if not sp.exists():
            log.info("%s: %d scenes found, %d dates used", p.name, len(items[p.key]), dates_used[-1])
            with timed(timings, "composites"):
                bands, months = composites.compute_period(used, gbox, mask, p, cfg)
                raster.write(mp, months, gbox)
                raster.write(sp, bands, gbox)
        stats[p.key], monthly[p.key] = raster.read(sp), raster.read(mp)

    anc_path = work / f"ancillary_{cfg['resolution_m']}m.tif"
    with timed(timings, "context layers"):
        if not anc_path.exists():
            raster.write(anc_path, ancillary.build(gbox, cfg), gbox)
        anc = raster.read(anc_path)

    with timed(timings, "detection"):
        found = [detect.detect(stats[a.key], stats[b.key], anc, mask, gbox, a, b, cfg)
                 for a, b in zip(periods, periods[1:])]
        cases = gpd.GeoDataFrame(pd.concat(found, ignore_index=True), crs=found[0].crs)

    if not cases.empty:
        with timed(timings, "jurisdiction"):
            cases["case_id"] = case_ids(cases, cfg.get("case_prefix", cfg["name"].upper()))
            pts = cases.representative_point().to_crs(4326)
            cases["lon"], cases["lat"] = pts.x.round(5), pts.y.round(5)
            cases = jurisdiction.assign_admin(cases, admin, cfg)
            cases["in_district_share"] = jurisdiction.in_district_share(cases, district)
            cases["authorisation"] = jurisdiction.authorisation(cases, cfg)
            cases["context"], cases["context_multiplier"] = jurisdiction.context_flags(cases, cfg)
            cases = prioritise.rank(cases, cfg)

        with timed(timings, "case files"):
            by_period = {p.key: p for p in periods}
            prev = {b.key: a for a, b in zip(periods, periods[1:])}
            sites = detect.sites_mask(cases, gbox)
            shutil.rmtree(out / "cases", ignore_errors=True)  # drop folders of cases no longer found
            ev = [{} for _ in range(len(cases))]
            for i, r in cases.head(cfg["cases"]["top_n"]).iterrows():
                p1 = by_period[r.period_after_key]
                p0 = prev[p1.key]
                log.info("case %d/%d %s", i + 1, min(len(cases), cfg["cases"]["top_n"]), r.case_id)
                ev[i] = evidence.build(r, r.geometry, gbox.crs.epsg, items, p0, p1,
                                       {**monthly[p0.key], **monthly[p1.key]}, sites, gbox, cfg,
                                       out / "cases" / r.case_id)
            cases["evidence"] = ev
    else:
        for col in ("rank", "tier", "evidence"):
            cases[col] = []

    timings["total"] = time.time() - t_start
    run_info = {
        "district": cfg["jurisdiction"]["aliases"].get(cfg["district"]["name"], cfg["district"]["name"]),
        "state": cfg["district"].get("state", ""),
        "periods": [p.name for p in periods],
        "dates_used": dates_used,
        "area_km2": float(mask.sum()) * abs(gbox.resolution.x) ** 2 / 1e6,
        "grid": f"{gbox.shape[1]} × {gbox.shape[0]} px at {cfg['resolution_m']} m, EPSG:{gbox.crs.epsg}",
        "timings": {k: round(v) for k, v in timings.items()},
        "minutes": f"{timings['total'] / 60:.0f}",
        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "version": __version__,
    }
    index = report.write(cases, run_info, district, admin, out, cfg)
    (out / "run.json").write_text(json.dumps(run_info, indent=2))
    tiers = cases["tier"].value_counts().to_dict() if not cases.empty else {}
    log.info("%d sites (%s); report: %s", len(cases), tiers, index)
    if not cases.empty:
        log.info("top case: %s, %.1f ha, confidence %.0f%%", cases.case_id.iloc[0],
                 cases.area_ha.iloc[0], 100 * np.asarray(cases.confidence)[0])
