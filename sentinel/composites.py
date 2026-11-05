"""Per-period statistics that cancel out clouds and seasons.

Each pixel is summarised over a whole period, using every clear observation:

- disturbed_freq: share of clear views where the ground is exposed (low NDVI,
  high bare-soil index) or open water. Crops are bare for part of the year;
  a working quarry is bare (or a flooded pit) nearly all the time.
- ndvi_p90: peak greenness. Residual clouds only ever lower NDVI, so a high
  percentile is robust to the clouds the mask missed.
- bsi_median, n_clear: supporting evidence and observation count.

Monthly NDVI medians are kept as well, for the per-case trajectory chart.
"""

from __future__ import annotations

import logging
import time
import warnings

import numpy as np
import pandas as pd
import xarray as xr
from odc.geo.geobox import GeoBox

from . import imagery
from .config import Period

log = logging.getLogger(__name__)

def indices(ds: xr.Dataset):
    ndvi = (ds.nir - ds.red) / (ds.nir + ds.red)
    bsi = ((ds.swir16 + ds.red) - (ds.nir + ds.blue)) / ((ds.swir16 + ds.red) + (ds.nir + ds.blue))
    mndwi = (ds.green - ds.swir16) / (ds.green + ds.swir16)
    return ndvi, bsi, mndwi


def _quantise(x: np.ndarray) -> np.ndarray:
    """Index in [-1, 1] to uint8 (step 0.008), 255 = no data. Keeps a year of
    per-date values for the whole district in well under a gigabyte."""
    q = np.round((np.clip(np.nan_to_num(x), -1, 1) + 1) * 127).astype("uint8")
    q[~np.isfinite(x)] = 255
    return q


def _reduce(q: np.ndarray, fn, rows: int = 256) -> np.ndarray:
    """Apply a nan-aware reduction over time, a band of rows at a time."""
    out = np.full(q.shape[1:], np.nan, "float32")
    for y in range(0, q.shape[1], rows):
        v = q[:, y:y + rows].astype("float32") / 127 - 1
        v[q[:, y:y + rows] == 255] = np.nan
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # never-clear pixels
            out[y:y + rows] = fn(v, axis=0)
    return out


def compute_period(items, gbox: GeoBox, mask: np.ndarray, period: Period, cfg: dict) -> tuple[dict, dict]:
    """Period statistics over the AOI, streaming one acquisition day at a time."""
    t = cfg["indices"]
    days = imagery.by_day(items)
    dates = sorted(days)
    q_ndvi = np.full((len(dates), *gbox.shape), 255, "uint8")
    q_bsi = np.full_like(q_ndvi, 255)
    n_clear = np.zeros(gbox.shape, "uint16")
    n_dist = np.zeros(gbox.shape, "uint16")
    t0 = time.time()
    for i, day in enumerate(dates):
        ds = imagery.load_day(days[day], gbox, cfg)
        if ds is not None:
            ndvi, bsi, mndwi = (v.values for v in indices(ds))
            with np.errstate(invalid="ignore"):
                clear = np.isfinite(ndvi) & mask
                exposed = (ndvi < t["exposed_ndvi_max"]) & (bsi > t["exposed_bsi_min"])
                disturbed = (exposed | (mndwi > t["water_mndwi_min"])) & clear
            n_clear += clear
            n_dist += disturbed
            q_ndvi[i] = _quantise(np.where(clear, ndvi, np.nan))
            q_bsi[i] = _quantise(np.where(clear, bsi, np.nan))
            share = clear.sum() / mask.sum()
        else:
            share = 0.0
        eta = (time.time() - t0) / (i + 1) * (len(dates) - i - 1)
        log.info("%s: %s (%d/%d), %.0f%% clear, ~%.0f min left", period.name, day, i + 1, len(dates),
                 100 * share, eta / 60)

    with np.errstate(invalid="ignore", divide="ignore"):
        freq = np.where(n_clear > 0, n_dist / n_clear, np.nan)
    stats = {
        "n_clear": np.where(mask, n_clear, np.nan).astype("float32"),
        "disturbed_freq": np.where(mask, freq, np.nan).astype("float32"),
        "ndvi_p90": _reduce(q_ndvi, lambda v, axis: np.nanpercentile(v, 90, axis=axis)),
        "bsi_median": _reduce(q_bsi, np.nanmedian),
    }
    monthly = {}
    for m in pd.date_range(period.start, period.end, freq="MS"):
        idx = [i for i, d in enumerate(dates) if (d.year, d.month) == (m.year, m.month)]
        monthly[f"{m:%Y-%m}"] = (_reduce(q_ndvi[idx], np.nanmedian) if idx
                                 else np.full(gbox.shape, np.nan, "float32"))
    return stats, monthly
