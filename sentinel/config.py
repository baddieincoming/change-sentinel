"""Run configuration: YAML file merged over defaults."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BOUNDARY_DIR = ROOT / "data" / "boundaries"

DEFAULTS: dict = {
    "country": "IND",
    "change_class": "Open-cast quarrying",
    "field_checks": [],
    "aoi_buffer_m": 0,
    "resolution_m": 20,
    "io_threads": 8,
    "stac": {
        "url": "https://earth-search.aws.element84.com/v1",
        # Collection 1 is reprocessed with a single processing baseline, so the
        # 2022 radiometric offset change does not show up as fake change.
        "collection": "sentinel-2-c1-l2a",
        "max_scene_cloud": 60,
        "max_dates_per_month": 3,
    },
    "cloud_mask": {
        # SCL: 0 nodata, 1 defective, 2 dark/terrain shadow, 3 cloud shadow,
        # 8/9 cloud, 10 cirrus, 11 snow
        "scl_classes": [0, 1, 2, 3, 8, 9, 10, 11],
        "dilate_px": 2,
    },
    "indices": {
        "exposed_ndvi_max": 0.20,
        "exposed_bsi_min": 0.05,
        "water_mndwi_min": 0.10,
    },
    "detection": {
        "min_clear_obs": 8,
        "after_disturbed_min": 0.75,
        "disturbed_increase_min": 0.30,
        "ndvi_p90_drop_min": 0.10,
        "min_area_ha": 0.5,
    },
    "confidence": {
        # Hand-set priors in the same logistic form you would fit with
        # labelled cases (see README, "Calibrating confidence").
        "bias": -6.0,
        "weights": {
            "after_disturbed": 3.0,
            "disturbed_increase": 3.0,
            "ndvi_p90_drop": 4.0,
            "obs_support": 1.5,
            "cropland_frac": -3.0,
            "slope_support": 1.5,
        },
    },
    "priority": {
        "inside_authorised": 0.1,
        "outside_district": 0.5,
        "tiers": {"inspect": 0.7, "review": 0.4},
    },
    "jurisdiction": {
        "levels": [
            {"level": "ADM1", "label": "State"},
            {"level": "ADM2", "label": "District"},
            {"level": "ADM3", "label": "Tehsil"},
            {"level": "ADM4", "label": "Block"},
        ],
        "aliases": {},
    },
    "authorised_areas": None,
    "authorisation_note": "",
    "lease_buffer_m": 500,
    "context_layers": [],
    "cases": {
        "top_n": 25,
        "chip_min_m": 800,
        "chip_margin_m": 250,
        "min_chip_clear": 0.97,
        "max_chip_tries": 10,
        "ring_m": 300,
    },
}


@dataclass(frozen=True)
class Period:
    name: str
    start: dt.date
    end: dt.date

    @property
    def key(self) -> str:
        return f"{self.start:%Y%m%d}-{self.end:%Y%m%d}"

    @property
    def stac_range(self) -> str:
        return f"{self.start.isoformat()}/{self.end.isoformat()}"


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "aliases":
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str | Path) -> dict:
    raw = yaml.safe_load(Path(path).read_text())
    cfg = _merge(DEFAULTS, raw)
    cfg["periods"] = [
        Period(p["name"], _date(p["start"]), _date(p["end"])) for p in raw["periods"]
    ]
    if len(cfg["periods"]) < 2:
        raise SystemExit("config needs at least two periods to compare")
    cfg["hash"] = hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return cfg


def _date(v) -> dt.date:
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))
