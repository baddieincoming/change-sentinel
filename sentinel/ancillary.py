"""Static context layers on the analysis grid: land cover and slope."""

from __future__ import annotations

import logging
import math

import numpy as np
import odc.stac
import rasterio
from odc.geo.geobox import GeoBox
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

log = logging.getLogger(__name__)

WORLDCOVER = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
              "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif")
CROPLAND, BUILT = 40, 50


def _worldcover_tiles(bounds) -> list[str]:
    lon0, lat0, lon1, lat1 = bounds
    tiles = []
    for lat in range(math.floor(lat0 / 3) * 3, math.ceil(lat1 / 3) * 3, 3):
        for lon in range(math.floor(lon0 / 3) * 3, math.ceil(lon1 / 3) * 3, 3):
            tiles.append(f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}")
    return tiles


def worldcover(gbox: GeoBox) -> np.ndarray:
    """ESA WorldCover 2021 classes (0 where no tile)."""
    out = np.zeros(gbox.shape, dtype="uint8")
    for tile in _worldcover_tiles(gbox.geographic_extent.boundingbox):
        with rasterio.open(WORLDCOVER.format(tile=tile)) as src, WarpedVRT(
            src, crs=gbox.crs.wkt, transform=gbox.transform, width=gbox.shape[1],
            height=gbox.shape[0], resampling=Resampling.mode,
        ) as vrt:
            arr = vrt.read(1)
        out = np.where(arr > 0, arr, out)
    return out


def slope(gbox: GeoBox, stac_url: str) -> np.ndarray:
    """Slope in degrees from Copernicus DEM GLO-30."""
    items = Client.open(stac_url).search(
        collections=["cop-dem-glo-30"], bbox=gbox.geographic_extent.boundingbox
    ).item_collection()
    dem = odc.stac.load(items, bands=["data"], geobox=gbox, resampling="bilinear")["data"].isel(time=0).values
    res = abs(gbox.resolution.x)
    gy, gx = np.gradient(dem.astype("float64"), res)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")


def build(gbox: GeoBox, cfg: dict) -> dict[str, np.ndarray]:
    log.info("loading land cover and terrain")
    return {"worldcover": worldcover(gbox).astype("float32"), "slope": slope(gbox, cfg["stac"]["url"])}
