"""Turn two period composites into candidate change polygons with features."""

from __future__ import annotations

import logging
import math

import geopandas as gpd
import numpy as np
from odc.geo.geobox import GeoBox
from rasterio.features import rasterize, shapes
from scipy import ndimage as ndi
from shapely.geometry import shape
from shapely.ops import unary_union

from .ancillary import BUILT, CROPLAND
from .config import Period

log = logging.getLogger(__name__)

EIGHT = np.ones((3, 3), bool)


def candidate_mask(before: dict, after: dict, aoi_mask: np.ndarray, cfg: dict) -> np.ndarray:
    """Pixels that became persistently bare (or a pit) and lost peak greenness."""
    d = cfg["detection"]
    with np.errstate(invalid="ignore"):
        m = (
            aoi_mask
            & (before["n_clear"] >= d["min_clear_obs"])
            & (after["n_clear"] >= d["min_clear_obs"])
            & (after["disturbed_freq"] >= d["after_disturbed_min"])
            & (after["disturbed_freq"] - before["disturbed_freq"] >= d["disturbed_increase_min"])
            & (before["ndvi_p90"] - after["ndvi_p90"] >= d["ndvi_p90_drop_min"])
        )
    # drop speckle and 1-px slivers, then knit nearby fragments of one site
    m = ndi.binary_opening(m, structure=ndi.generate_binary_structure(2, 1))
    m = ndi.binary_closing(m, structure=EIGHT)
    return ndi.binary_fill_holes(m)


def label_sites(mask: np.ndarray, min_px: int) -> np.ndarray:
    labels, _ = ndi.label(mask, structure=EIGHT)
    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_px
    keep[0] = False
    remap = np.zeros(len(sizes), dtype="int32")
    remap[keep] = np.arange(1, keep.sum() + 1)
    return remap[labels]


def detect(before: dict, after: dict, anc: dict, aoi_mask: np.ndarray, gbox: GeoBox,
           p0: Period, p1: Period, cfg: dict) -> gpd.GeoDataFrame:
    res = abs(gbox.resolution.x)
    px_ha = res * res / 1e4
    mask = candidate_mask(before, after, aoi_mask, cfg)
    labels = label_sites(mask, math.ceil(cfg["detection"]["min_area_ha"] / px_ha))
    n = int(labels.max())
    log.info("%s -> %s: %d candidate px, %d sites", p0.name, p1.name, int(mask.sum()), n)
    if n == 0:
        return gpd.GeoDataFrame(geometry=[], crs=gbox.crs.wkt)

    idx = np.arange(1, n + 1)

    def mean(arr):
        return ndi.mean(np.nan_to_num(arr), labels, idx)

    count = ndi.sum(np.ones_like(labels), labels, idx)

    # "expansion" if the site is within 2 px of ground already disturbed before
    with np.errstate(invalid="ignore"):
        existing = before["disturbed_freq"] >= cfg["detection"]["after_disturbed_min"]
    touches = ndi.sum(ndi.binary_dilation(existing, EIGHT, iterations=2), labels, idx) > 0

    wc = anc["worldcover"]
    feats = {
        "pixels": count,
        "area_ha": count * px_ha,
        "disturbed_before": mean(before["disturbed_freq"]),
        "disturbed_after": mean(after["disturbed_freq"]),
        "ndvi_p90_before": mean(before["ndvi_p90"]),
        "ndvi_p90_after": mean(after["ndvi_p90"]),
        "bsi_before": mean(before["bsi_median"]),
        "bsi_after": mean(after["bsi_median"]),
        "n_clear_before": mean(before["n_clear"]),
        "n_clear_after": mean(after["n_clear"]),
        "cropland_frac": ndi.mean(wc == CROPLAND, labels, idx),
        "built_frac": ndi.mean(wc == BUILT, labels, idx),
        "slope_mean": mean(anc["slope"]),
        "kind": np.where(touches, "expansion", "new site"),
    }

    geoms = [[] for _ in idx]
    for g, v in shapes(labels, mask=labels > 0, transform=gbox.transform, connectivity=8):
        geoms[int(v) - 1].append(shape(g))
    polys = [unary_union(g).simplify(res / 2) for g in geoms]

    gdf = gpd.GeoDataFrame(feats, geometry=polys, crs=f"EPSG:{gbox.crs.epsg}")
    # the true edge can sit anywhere within half a pixel of the mapped one
    band_ha = gdf.length * res / 2 / 1e4
    gdf["area_ha_low"] = (gdf["area_ha"] - band_ha).clip(lower=0)
    gdf["area_ha_high"] = gdf["area_ha"] + band_ha
    gdf["label"] = idx
    gdf["period_before"] = p0.name
    gdf["period_after"] = p1.name
    gdf["period_after_key"] = p1.key
    return gdf


def sites_mask(cases: gpd.GeoDataFrame, gbox: GeoBox) -> np.ndarray:
    """Union of all case polygons as a mask (to keep them out of control rings)."""
    if cases.empty:
        return np.zeros(gbox.shape, bool)
    return rasterize(cases.geometry, out_shape=gbox.shape, transform=gbox.transform).astype(bool)
