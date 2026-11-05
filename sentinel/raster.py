"""Small GeoTIFF helpers for cached rasters on the analysis grid."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from odc.geo.geobox import GeoBox


def write(path: Path, bands: dict[str, np.ndarray], gbox: GeoBox, dtype="float32", nodata=np.nan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part.tif")
    profile = dict(driver="GTiff", height=gbox.shape[0], width=gbox.shape[1], count=len(bands),
                   dtype=dtype, crs=gbox.crs.wkt, transform=gbox.transform, nodata=nodata,
                   compress="deflate", predictor=3 if dtype.startswith("float") else 2,
                   tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(tmp, "w", **profile) as dst:
        for i, (name, arr) in enumerate(bands.items(), start=1):
            dst.write(arr.astype(dtype), i)
            dst.set_band_description(i, name)
    tmp.rename(path)


def read(path: Path) -> dict[str, np.ndarray]:
    with rasterio.open(path) as src:
        out = {}
        for i, name in enumerate(src.descriptions, start=1):
            arr = src.read(i)
            if src.nodata is not None and not np.isnan(src.nodata):
                arr = np.where(arr == src.nodata, np.nan, arr.astype("float32"))
            out[name] = arr
        return out
