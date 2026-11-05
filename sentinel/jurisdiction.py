"""Who is responsible for each site, and is it inside an authorised area."""

from __future__ import annotations

import unicodedata

import geopandas as gpd
import numpy as np


def plain(name: str) -> str:
    """'Haryāna' -> 'Haryana': geoBoundaries state names carry IAST diacritics."""
    return "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))


def assign_admin(cases: gpd.GeoDataFrame, admin: dict[str, gpd.GeoDataFrame], cfg: dict) -> gpd.GeoDataFrame:
    """Containing unit at each admin level, by largest overlap; flags sites that straddle a boundary."""
    aliases = {plain(k): v for k, v in cfg["jurisdiction"]["aliases"].items()}
    cases = cases.copy()
    spans = [[] for _ in range(len(cases))]
    for lv in cfg["jurisdiction"]["levels"]:
        units = admin[lv["level"]].to_crs(cases.crs)
        units["name"] = units["name"].map(plain)
        inter = gpd.overlay(cases[["case_id", "geometry"]], units, how="intersection", keep_geom_type=True)
        inter["share"] = inter.area / inter["case_id"].map(cases.set_index("case_id").area)
        best = inter.sort_values("share", ascending=False).drop_duplicates("case_id").set_index("case_id")
        names = best["name"].map(lambda n: aliases.get(n, n))
        cases[lv["label"]] = cases["case_id"].map(names).fillna("unknown")
        for i, cid in enumerate(cases["case_id"]):
            if cid in best.index and best.at[cid, "share"] < 0.95:
                others = inter[(inter.case_id == cid) & (inter.share >= 0.05)]["name"].map(lambda n: aliases.get(n, n))
                spans[i].append(f"{lv['label']}: {' / '.join(others)}")
    cases["spans_boundary"] = ["; ".join(s) for s in spans]
    return cases


def in_district_share(cases: gpd.GeoDataFrame, district: gpd.GeoDataFrame) -> np.ndarray:
    d = district.to_crs(cases.crs).union_all()
    return (cases.intersection(d).area / cases.area).to_numpy()


def authorisation(cases: gpd.GeoDataFrame, cfg: dict) -> list[str]:
    buf = cfg["lease_buffer_m"]
    if not cfg["authorised_areas"]:
        return ["no authorised areas on file"] * len(cases)
    leases = gpd.read_file(cfg["authorised_areas"]).to_crs(cases.crs).union_all()
    inside = (cases.intersection(leases).area / cases.area).to_numpy()
    dist = cases.distance(leases).to_numpy()
    return np.select(
        [inside >= 0.9, dist <= buf],
        ["inside an authorised area", f"within {buf} m of an authorised area (possible overreach)"],
        f"no authorised area within {buf} m",
    ).tolist()


def context_flags(cases: gpd.GeoDataFrame, cfg: dict) -> tuple[list[list[str]], np.ndarray]:
    """Sensitive layers near each site (e.g. protected areas, water bodies) and their priority multiplier."""
    labels = [[] for _ in range(len(cases))]
    mult = np.ones(len(cases))
    for layer in cfg["context_layers"]:
        g = gpd.read_file(layer["path"]).to_crs(cases.crs).union_all()
        hit = (cases.distance(g) <= layer.get("buffer_m", 0)).to_numpy()
        for i in np.flatnonzero(hit):
            labels[i].append(layer["label"])
        mult = np.where(hit, mult * layer.get("multiplier", 1.5), mult)
    return labels, mult
