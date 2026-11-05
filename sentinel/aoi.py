"""District boundary, admin layers for jurisdiction, and the analysis grid."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import requests
from odc.geo.geobox import GeoBox
from odc.geo.geom import Geometry
from rasterio.features import rasterize
from shapely.geometry import box

from .config import BOUNDARY_DIR

log = logging.getLogger(__name__)

GB_API = "https://www.geoboundaries.org/api/current/gbOpen/{iso}/{level}/"


def boundary_file(country: str, level: str, simplified: bool = False) -> Path:
    """Path to a national geoBoundaries layer, downloading it once."""
    suffix = "_simplified" if simplified else ""
    path = BOUNDARY_DIR / f"{country}-{level}{suffix}.geojson"
    if path.exists():
        return path
    meta = requests.get(GB_API.format(iso=country, level=level), timeout=60).json()
    url = meta["simplifiedGeometryGeoJSON" if simplified else "gjDownloadURL"]
    log.info("downloading %s %s boundaries from %s", country, level, url)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.rename(path)
    return path


def load_district(cfg: dict) -> gpd.GeoDataFrame:
    d = cfg["district"]
    gdf = gpd.read_file(boundary_file(cfg["country"], d.get("level", "ADM2")))
    hit = gdf[gdf["shapeName"].str.casefold() == d["name"].casefold()]
    if len(hit) > 1 and d.get("state"):
        states = gpd.read_file(boundary_file(cfg["country"], "ADM1"))
        state = states[states["shapeName"].str.casefold() == d["state"].casefold()]
        hit = hit[hit.representative_point().within(state.union_all())]
    if len(hit) != 1:
        raise SystemExit(f"expected one {d.get('level', 'ADM2')} named {d['name']!r}, found {len(hit)}")
    return hit[["shapeName", "geometry"]].to_crs(4326).reset_index(drop=True)


def admin_layers(cfg: dict, district: gpd.GeoDataFrame, cache: Path) -> dict[str, gpd.GeoDataFrame]:
    """Admin units around the district, clipped from the national layers and cached."""
    levels = cfg["jurisdiction"]["levels"]
    if cache.exists():
        return {lv["level"]: gpd.read_file(cache, layer=lv["level"]) for lv in levels}
    utm = district.estimate_utm_crs()
    bbox = tuple(district.to_crs(utm).buffer(cfg["aoi_buffer_m"] + 5000).to_crs(4326).total_bounds)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".part.gpkg")
    tmp.unlink(missing_ok=True)
    out = {}
    for lv in levels:
        path = boundary_file(cfg["country"], lv["level"], lv.get("simplified", False))
        log.info("clipping %s to the district", path.name)
        g = gpd.read_file(path, bbox=bbox, columns=["shapeName"])
        g = g.rename(columns={"shapeName": "name"})[["name", "geometry"]].to_crs(4326)
        g.to_file(tmp, layer=lv["level"], driver="GPKG")
        out[lv["level"]] = g
    tmp.rename(cache)
    return out


def utm_epsg(lon: float, lat: float) -> int:
    return (32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1


def analysis_grid(cfg: dict, district: gpd.GeoDataFrame, subset: tuple | None):
    """UTM grid over the (buffered) district, plus the AOI as a raster mask."""
    geom = district.geometry.iloc[0]
    if subset:
        geom = geom.intersection(box(*subset))
        if geom.is_empty:
            raise SystemExit("--subset does not overlap the district")
    c = geom.centroid
    epsg = utm_epsg(c.x, c.y)
    poly = Geometry(geom, crs="EPSG:4326").to_crs(f"EPSG:{epsg}")
    if cfg["aoi_buffer_m"]:
        poly = poly.buffer(cfg["aoi_buffer_m"])
    gbox = GeoBox.from_geopolygon(poly, resolution=cfg["resolution_m"], crs=poly.crs)
    mask = rasterize([poly.geom], out_shape=gbox.shape, transform=gbox.transform).astype(bool)
    log.info("grid %s x %s px at %s m (%.0f km2 in AOI)", *gbox.shape, cfg["resolution_m"],
             mask.sum() * cfg["resolution_m"] ** 2 / 1e6)
    return gbox, poly, mask


def district_mask(district: gpd.GeoDataFrame, gbox: GeoBox) -> np.ndarray:
    geom = district.to_crs(gbox.crs.epsg).geometry.iloc[0]
    return rasterize([geom], out_shape=gbox.shape, transform=gbox.transform).astype(bool)
