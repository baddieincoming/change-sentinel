"""Write the ranked index, per-case pages, and machine-readable outputs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import geopandas as gpd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from matplotlib.figure import Figure

from .evidence import AXIS, INK_2, MUTED, SURFACE

TEMPLATES = Path(__file__).parent / "templates"
# status palette (dataviz skill), always paired with a label
TIER_COLOURS = {"Inspect": "#d03b3b", "Review": "#ec835a", "Low": "#898781"}


def overview_map(cases: gpd.GeoDataFrame, district: gpd.GeoDataFrame, admin: dict, top_n: int, path: Path) -> None:
    crs = cases.crs if not cases.empty else district.estimate_utm_crs()
    fig = Figure(figsize=(6.5, 6.5), dpi=150, facecolor=SURFACE)
    ax = fig.subplots()
    if "ADM3" in admin:
        admin["ADM3"].to_crs(crs).boundary.plot(ax=ax, color=AXIS, lw=0.5)
    district.to_crs(crs).boundary.plot(ax=ax, color=INK_2, lw=1.2)
    if not cases.empty:
        pts = cases.copy()
        pts["geometry"] = pts.representative_point()
        rest = pts[pts["rank"] > top_n]
        if not rest.empty:
            rest.plot(ax=ax, color=MUTED, markersize=6)
        for tier, colour in TIER_COLOURS.items():
            sel = pts[(pts["rank"] <= top_n) & (pts["tier"] == tier)]
            if not sel.empty:
                sel.plot(ax=ax, color=colour, markersize=40, edgecolor="white", linewidth=0.8,
                         label=f"{tier} (top {top_n})")
                for r in sel.itertuples():
                    ax.annotate(str(r.rank), (r.geometry.x, r.geometry.y), xytext=(5, 4),
                                textcoords="offset points", fontsize=7, color=INK_2)
        ax.legend(loc="lower left", fontsize=7, labelcolor=INK_2, facecolor=SURFACE, edgecolor=AXIS,
                  framealpha=1)
    xmin, ymin, xmax, ymax = district.to_crs(crs).total_bounds
    pad = 0.04 * max(xmax - xmin, ymax - ymin)
    ax.set_xlim(xmin - pad, xmax + pad)
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_axis_off()
    fig.subplots_adjust(0.01, 0.01, 0.99, 0.99)
    fig.savefig(path, facecolor=SURFACE)


def write(cases: gpd.GeoDataFrame, run: dict, district, admin, out: Path, cfg: dict) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape())
    env.globals["zip"] = zip
    shutil.copy(TEMPLATES / "style.css", out / "style.css")
    top_n = cfg["cases"]["top_n"]
    levels = [lv["label"] for lv in cfg["jurisdiction"]["levels"]]

    overview_map(cases, district, admin, top_n, out / "overview.png")
    if not cases.empty:
        flat = cases.to_crs(4326).drop(columns=["evidence"])
        flat["reasons"] = flat["reasons"].map(" | ".join)
        flat["context"] = flat["context"].map(", ".join)
        flat.to_file(out / "cases.geojson", driver="GeoJSON")
        flat.drop(columns=["geometry"]).to_csv(out / "cases.csv", index=False)

    rows = cases.head(top_n).to_dict("records")
    for r in rows:
        case_dir = out / "cases" / r["case_id"]
        r["href"] = f"cases/{r['case_id']}/case.html"
        r["place"] = ", ".join(dict.fromkeys(r[lv] for lv in reversed(levels)))
        evidence = {k: v for k, v in r.items() if k not in ("geometry",)}
        evidence["geometry_wgs84"] = gpd.GeoSeries([r["geometry"]], crs=cases.crs).to_crs(4326).iloc[0].wkt
        (case_dir / "evidence.json").write_text(json.dumps(evidence, indent=2, default=str))
        html = env.get_template("case.html.j2").render(c=r, run=run, levels=levels, cfg=cfg,
                                                       tier_colour=TIER_COLOURS[r["tier"]])
        (case_dir / "case.html").write_text(html)

    counts = cases["tier"].value_counts().to_dict() if not cases.empty else {}
    html = env.get_template("index.html.j2").render(rows=rows, run=run, cfg=cfg, levels=levels,
                                                    counts=counts, total=len(cases), colours=TIER_COLOURS)
    (out / "index.html").write_text(html)
    return out / "index.html"
