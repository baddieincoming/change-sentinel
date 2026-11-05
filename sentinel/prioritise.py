"""Confidence, priority and the plain-language reasons behind each rank."""

from __future__ import annotations

import geopandas as gpd
import numpy as np


def features(cases: gpd.GeoDataFrame) -> dict[str, np.ndarray]:
    return {
        "after_disturbed": cases["disturbed_after"].to_numpy(),
        "disturbed_increase": (cases["disturbed_after"] - cases["disturbed_before"]).to_numpy(),
        "ndvi_p90_drop": (cases["ndvi_p90_before"] - cases["ndvi_p90_after"]).to_numpy(),
        "obs_support": np.clip(np.minimum(cases["n_clear_before"], cases["n_clear_after"]) / 20, 0, 1).to_numpy(),
        "cropland_frac": cases["cropland_frac"].to_numpy(),
        "slope_support": np.clip(cases["slope_mean"] / 10, 0, 1).to_numpy(),
    }


def confidence(cases: gpd.GeoDataFrame, cfg: dict) -> np.ndarray:
    c = cfg["confidence"]
    f = features(cases)
    z = c["bias"] + sum(w * f[k] for k, w in c["weights"].items())
    return 1 / (1 + np.exp(-z))


def rank(cases: gpd.GeoDataFrame, cfg: dict) -> gpd.GeoDataFrame:
    p = cfg["priority"]
    cases = cases.copy()
    cases["confidence"] = confidence(cases, cfg)
    mult = cases["context_multiplier"].to_numpy().copy()
    mult *= np.where(cases["authorisation"].str.startswith("inside"), p["inside_authorised"], 1.0)
    mult *= np.where(cases["in_district_share"] < 0.5, p["outside_district"], 1.0)
    cases["priority"] = cases["confidence"] * np.log2(1 + cases["area_ha"]) * mult
    t = p["tiers"]
    cases["tier"] = np.select([cases["confidence"] >= t["inspect"], cases["confidence"] >= t["review"]],
                              ["Inspect", "Review"], "Low")
    cases["reasons"] = [reasons(r) for r in cases.itertuples()]
    # confident cases first: a big maybe-fallow field must not outrank a likely quarry
    order = cases["tier"].map({"Inspect": 0, "Review": 1, "Low": 2})
    cases = cases.assign(_o=order).sort_values(["_o", "priority"], ascending=[True, False])
    cases = cases.drop(columns="_o").reset_index(drop=True)
    cases["rank"] = np.arange(1, len(cases) + 1)
    return cases


def reasons(r) -> list[str]:
    out = [
        f"{r.area_ha:.1f} ha newly disturbed (boundary range {r.area_ha_low:.1f}–{r.area_ha_high:.1f} ha)",
        f"bare ground or open pit in {r.disturbed_after:.0%} of clear views in {r.period_after}, "
        f"vs {r.disturbed_before:.0%} in {r.period_before}",
        f"peak greenness (NDVI p90) fell from {r.ndvi_p90_before:.2f} to {r.ndvi_p90_after:.2f}",
        "grows out of ground that was already disturbed" if r.kind == "expansion"
        else "new site: nothing disturbed next to it in the earlier period",
    ]
    if r.slope_mean >= 5:
        out.append(f"on hill terrain (mean slope {r.slope_mean:.0f}°)")
    if r.cropland_frac >= 0.3:
        out.append(f"caution: {r.cropland_frac:.0%} mapped as cropland in ESA WorldCover 2021, could be a fallow field")
    if r.built_frac >= 0.3:
        out.append(f"caution: {r.built_frac:.0%} mapped as built-up, could be construction")
    if min(r.n_clear_before, r.n_clear_after) < 12:
        out.append(f"only {min(r.n_clear_before, r.n_clear_after):.0f} clear views in one period, so lower confidence")
    out.append(r.authorisation)
    if r.in_district_share < 0.5:
        out.append("mostly outside the district: refer to the neighbouring administration")
    if r.spans_boundary:
        out.append(f"straddles a boundary ({r.spans_boundary})")
    for label in r.context:
        out.append(f"near {label}")
    return out
