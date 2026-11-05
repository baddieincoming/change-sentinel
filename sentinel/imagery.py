"""Sentinel-2 search, date thinning, and cloud-masked reflectance loading."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import odc.stac
import pystac
import xarray as xr
from odc.geo.geobox import GeoBox
from pystac_client import Client
from rasterio.errors import RasterioIOError
from scipy import ndimage as ndi
from shapely.geometry import box, mapping, shape

from .config import Period

log = logging.getLogger(__name__)

BANDS = ["blue", "green", "red", "nir", "swir16"]


def search(cfg: dict, geom_4326, period: Period, cache: Path) -> pystac.ItemCollection:
    """All scenes for a period (cached so evidence can be traced to exact items)."""
    if cache.exists():
        return pystac.ItemCollection.from_file(str(cache))
    st = cfg["stac"]
    items = Client.open(st["url"]).search(
        collections=[st["collection"]],
        intersects=mapping(geom_4326),
        datetime=period.stac_range,
        query={"eo:cloud_cover": {"lt": st["max_scene_cloud"]}},
    ).item_collection()
    items.save_object(str(cache))
    return items


def by_day(items) -> dict:
    days = defaultdict(list)
    for it in items:
        days[it.datetime.date()].append(it)
    return dict(days)


def thin(items, per_month: int) -> list[pystac.Item]:
    """Keep the clearest `per_month` acquisition days per month.

    Spreading dates across months matters more for the seasonal statistics
    than total scene count, and caps the bytes read in clear months.
    """
    days = by_day(items)
    months = defaultdict(list)
    for day, its in days.items():
        months[(day.year, day.month)].append((np.mean([i.properties["eo:cloud_cover"] for i in its]), day))
    keep = {day for ranked in months.values() for _, day in sorted(ranked)[:per_month]}
    return [it for day in sorted(keep) for it in days[day]]


def scale_offset(items, band: str) -> tuple[float, float]:
    pairs = set()
    for it in items:
        rb = (it.assets[band].extra_fields.get("raster:bands") or [{}])[0]
        pairs.add((rb.get("scale", 1.0), rb.get("offset", 0.0)))
    if len(pairs) != 1:
        raise ValueError(f"{band}: mixed scale/offset {pairs}; use a single-baseline collection")
    return pairs.pop()


def clear_mask(scl: np.ndarray, cfg: dict) -> np.ndarray:
    """True where the pixel is usable, with clouds and shadows grown by a margin."""
    bad = np.isin(scl, cfg["cloud_mask"]["scl_classes"])
    k = 2 * cfg["cloud_mask"]["dilate_px"] + 1
    if k > 1:
        bad = ndi.binary_dilation(bad, structure=np.ones((k, k), bool))
    return ~bad


def overlapping(items, gbox: GeoBox) -> list[pystac.Item]:
    area = box(*gbox.geographic_extent.boundingbox)
    return [it for it in items if shape(it.geometry).intersects(area)]


def load_day(items, gbox: GeoBox, cfg: dict, tries: int = 5) -> xr.Dataset | None:
    """Cloud-masked surface reflectance for one acquisition day (NaN = not clear).

    The whole grid is read in one call, so each COG block is downloaded once;
    on a slow link the bytes moved, not the CPU, set the run time.

    A failed read is retried with backoff, then raised. Skipping it would turn
    a network outage into "cloudy" pixels and silently bias the statistics.
    """
    items = overlapping(items, gbox)
    if not items:
        return None
    for attempt in range(tries):
        try:
            ds = odc.stac.load(
                items,
                bands=BANDS + ["scl"],
                geobox=gbox,
                groupby="solar_day",
                resampling={"scl": "nearest", "*": "average"},
                pool=cfg["io_threads"],
            ).isel(time=0)
            break
        except RasterioIOError as e:
            if attempt == tries - 1:
                raise
            wait = 15 * 2 ** attempt
            log.warning("read failed (%s); retrying in %d s", str(e).splitlines()[0], wait)
            time.sleep(wait)
    clear = clear_mask(ds["scl"].values, cfg)
    out = {}
    for b in BANDS:
        scale, offset = scale_offset(items, b)
        v = ds[b]
        out[b] = (v.astype("float32") * scale + offset).where((v != 0) & clear)
    return xr.Dataset(out)


def load_chip(items, gbox: GeoBox, cfg: dict) -> tuple[np.ndarray, float]:
    """True-colour reflectance (3, y, x) for one day, and its clear fraction."""
    ds = odc.stac.load(items, bands=["red", "green", "blue", "scl"], geobox=gbox, groupby="solar_day",
                       resampling={"scl": "nearest", "*": "bilinear"}, pool=cfg["io_threads"])
    ds = ds.isel(time=0)
    clear = ~np.isin(ds["scl"].values, cfg["cloud_mask"]["scl_classes"])
    rgb = []
    for b in ["red", "green", "blue"]:
        scale, offset = scale_offset(items, b)
        v = ds[b].values.astype("float32")
        rgb.append(np.where(v == 0, np.nan, v * scale + offset))
    return np.stack(rgb), float(clear.mean())
