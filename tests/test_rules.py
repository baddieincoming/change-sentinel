"""Offline checks of the detection and dating rules on synthetic data."""

import datetime as dt

import numpy as np
import pystac
import pytest
from odc.geo.geobox import GeoBox
from rasterio.errors import RasterioIOError
from shapely.geometry import box, mapping

from sentinel import config, detect, evidence, imagery

CFG = config.load(config.ROOT / "config" / "nuh.yaml")
P0 = config.Period("before", dt.date(2024, 10, 1), dt.date(2025, 9, 30))
P1 = config.Period("after", dt.date(2025, 10, 1), dt.date(2026, 9, 30))


def _stats(disturbed, ndvi_p90, n=30.0, shape=(60, 60)):
    return {
        "n_clear": np.full(shape, n, "float32"),
        "disturbed_freq": disturbed.astype("float32"),
        "ndvi_p90": ndvi_p90.astype("float32"),
        "bsi_median": np.zeros(shape, "float32"),
    }


def _scene():
    """Scrub everywhere; a 10x10 px quarry appears; a 10x10 px field is bare part of each year."""
    shape = (60, 60)
    before = _stats(np.full(shape, 0.2), np.full(shape, 0.45))
    after = _stats(np.full(shape, 0.2), np.full(shape, 0.45))
    quarry, field = np.s_[10:20, 10:20], np.s_[35:45, 35:45]
    after["disturbed_freq"][quarry], after["ndvi_p90"][quarry] = 0.95, 0.12
    before["disturbed_freq"][field], after["disturbed_freq"][field] = 0.45, 0.55
    before["ndvi_p90"][field], after["ndvi_p90"][field] = 0.75, 0.7
    return before, after, quarry, field


def test_quarry_flagged_crop_cycle_ignored():
    before, after, quarry, field = _scene()
    m = detect.candidate_mask(before, after, np.ones((60, 60), bool), CFG)
    assert m[quarry].mean() > 0.9
    assert not m[field].any()


def test_detect_returns_one_site_with_area():
    before, after, _, _ = _scene()
    gbox = GeoBox.from_bbox((700000, 3070000, 701200, 3071200), crs="EPSG:32643", resolution=20)
    anc = {"worldcover": np.full((60, 60), 20, "float32"), "slope": np.full((60, 60), 8, "float32")}
    sites = detect.detect(before, after, anc, np.ones((60, 60), bool), gbox, P0, P1, CFG)
    assert len(sites) == 1
    assert abs(sites.area_ha.iloc[0] - 4.0) < 0.5  # 10x10 px at 20 m
    assert sites.area_ha_low.iloc[0] < sites.area_ha.iloc[0] < sites.area_ha_high.iloc[0]
    assert sites.kind.iloc[0] == "new site"


def test_onset_cancels_season():
    months = [f"{y}-{m:02d}" for y, m in [(2024, 10), (2024, 11), (2024, 12)] + [(2025, m) for m in range(1, 13)]
              + [(2026, m) for m in range(1, 10)]]
    season = 0.3 + 0.15 * np.cos(np.arange(len(months)) * 2 * np.pi / 12)  # scrub: 0.15 dry, 0.45 monsoon
    ring = season.copy()
    site = season.copy()
    drop_from = months.index("2026-02")
    site[drop_from:] = 0.08  # quarried in Feb 2026; ring keeps its seasonal swing
    assert evidence.onset(months, site, ring) == drop_from
    assert evidence.onset(months, season.copy(), ring) is None


def test_failed_download_raises_instead_of_reading_as_cloud(monkeypatch):
    gbox = GeoBox.from_bbox((76.9, 27.7, 77.0, 27.8), crs="EPSG:4326", resolution=0.01)
    item = pystac.Item("S2_test", mapping(box(76.8, 27.6, 77.1, 27.9)), None, dt.datetime(2026, 5, 1), {})
    calls = []

    def offline(*args, **kwargs):
        calls.append(1)
        raise RasterioIOError("CURL error: Could not resolve host")

    monkeypatch.setattr(imagery.odc.stac, "load", offline)
    monkeypatch.setattr(imagery.time, "sleep", lambda s: None)
    with pytest.raises(RasterioIOError):
        imagery.load_day([item], gbox, CFG, tries=3)
    assert len(calls) == 3
