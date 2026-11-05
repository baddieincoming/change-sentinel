"""Evidence for each case: before/after chips, NDVI trajectory, provenance."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import warnings
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.patheffects as pe
import numpy as np
from matplotlib.figure import Figure
from odc.geo.geobox import GeoBox
from rasterio.errors import RasterioIOError
from rasterio.features import rasterize

from .config import Period
from .imagery import by_day, load_chip, overlapping

log = logging.getLogger(__name__)

# reference palette (dataviz skill): categorical slots 1-2, chart chrome and ink
SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SITE, SURROUND = "#eb6834", "#2a78d6"
HALO = [pe.withStroke(linewidth=3.5, foreground="black")]


def chip_geobox(geom, epsg: int, cfg: dict) -> GeoBox:
    c = cfg["cases"]
    minx, miny, maxx, maxy = geom.bounds
    side = max(maxx - minx, maxy - miny, c["chip_min_m"] - 2 * c["chip_margin_m"]) + 2 * c["chip_margin_m"]
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    return GeoBox.from_bbox((cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2),
                            crs=f"EPSG:{epsg}", resolution=10)


def _ordered(days: dict, key) -> list[dt.date]:
    """Low-cloud days first, each group in order of preference."""
    def cloud(d):
        return min(it.properties["eo:cloud_cover"] for it in days[d])
    return sorted(days, key=lambda d: (cloud(d) > 20, key(d)))


def clearest(days: dict, order: list[dt.date], gbox: GeoBox, cfg: dict):
    best = None
    for day in order[: cfg["cases"]["max_chip_tries"]]:
        try:
            rgb, frac = load_chip(days[day], gbox, cfg)
        except RasterioIOError as e:  # dropped connection: try the next day, don't lose the run
            log.warning("chip for %s failed: %s", day, str(e).splitlines()[0])
            continue
        if best is None or frac > best["clear"]:
            best = {"day": day, "rgb": rgb, "clear": frac, "items": days[day]}
        if frac >= cfg["cases"]["min_chip_clear"]:
            break
    return best


def pick_views(items_before, items_after, gbox: GeoBox, cfg: dict, began_in_later: bool):
    """Most recent clear view in the later period, plus a 'before' view.

    If the change began inside the later period, the before view is the clear
    day nearest one year before the after view (same season, so crops match).
    If it was already under way when the later period started, the before
    view comes from as early as possible in the earlier period.
    """
    after_days = by_day(overlapping(items_after, gbox))
    after = clearest(after_days, _ordered(after_days, lambda d: -d.toordinal()), gbox, cfg)
    before_days = by_day(overlapping(items_before, gbox))
    if after and began_in_later:
        target = after["day"] - dt.timedelta(days=365)
        order = _ordered(before_days, lambda d: abs((d - target).days))
    else:
        order = _ordered(before_days, lambda d: d.toordinal())
    return clearest(before_days, order, gbox, cfg), after


def _stretch(a: np.ndarray, b: np.ndarray):
    """One shared 2–98% stretch so both images are rendered identically."""
    both = np.concatenate([a.reshape(3, -1), b.reshape(3, -1)], axis=1)
    lo = np.nanpercentile(both, 2, axis=1)[:, None, None]
    hi = np.nanpercentile(both, 98, axis=1)[:, None, None]

    def f(x):
        return np.nan_to_num(np.clip((x - lo) / (hi - lo), 0, 1)).transpose(1, 2, 0)
    return f(a), f(b)


def _outline(ax, geom):
    lines = [geom.boundary] if geom.boundary.geom_type == "LineString" else list(geom.boundary.geoms)
    for ln in lines:
        x, y = ln.xy
        ax.plot(x, y, color="white", lw=1.6, path_effects=HALO)


def _scalebar(ax, gbox: GeoBox):
    minx, miny, maxx, maxy = gbox.extent.boundingbox
    side = maxx - minx
    length = max(v for v in (50, 100, 200, 250, 500, 1000, 2000, 5000) if v <= side / 4)
    x0, y0 = minx + side * 0.05, miny + side * 0.06
    ax.plot([x0, x0 + length], [y0, y0], color="white", lw=2.5, solid_capstyle="butt", path_effects=HALO)
    label = f"{length / 1000:g} km" if length >= 1000 else f"{length} m"
    ax.text(x0, y0 + side * 0.025, label, color="white", fontsize=8, path_effects=HALO)


def save_chip(img, gbox: GeoBox, geom, title: str, caption: str, path: Path) -> str:
    minx, miny, maxx, maxy = gbox.extent.boundingbox
    fig = Figure(figsize=(4, 4.4), dpi=150, facecolor=SURFACE)
    ax = fig.subplots()
    ax.imshow(img, extent=(minx, maxx, miny, maxy), interpolation="nearest")
    _outline(ax, geom)
    _scalebar(ax, gbox)
    ax.set_axis_off()
    ax.set_title(title, loc="left", fontsize=10, color=INK, fontweight="bold")
    fig.text(0.04, 0.02, caption, fontsize=6, color=INK_2, wrap=True)
    fig.subplots_adjust(left=0.03, right=0.97, top=0.92, bottom=0.08)
    fig.savefig(path, facecolor=SURFACE)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def site_series(geom, sites: np.ndarray, monthly: dict[str, np.ndarray], gbox: GeoBox, ring_m: int):
    """Monthly mean NDVI inside the site and in a ring around it (other sites excluded)."""
    def mask(g):
        return rasterize([g], out_shape=gbox.shape, transform=gbox.transform).astype(bool)

    inside = mask(geom)
    ring = mask(geom.buffer(ring_m)) & ~mask(geom.buffer(40)) & ~sites
    months = sorted(monthly)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN months (monsoon cloud)
        s_in = np.array([np.nanmean(monthly[m][inside]) for m in months])
        s_ring = np.array([np.nanmean(monthly[m][ring]) for m in months])
    return months, s_in, s_ring


def onset(months: list[str], s_in: np.ndarray, s_ring: np.ndarray, drop: float = 0.08) -> int | None:
    """First month from which the site stays below where it was a year earlier.

    Each month is compared with the same month last year, relative to the
    surrounding ring (a difference-in-differences), so both the season and any
    district-wide wet or dry year cancel out. Needs a matching month a year
    back, so it can only date changes inside the later period.
    """
    pos = {m: i for i, m in enumerate(months)}
    did = np.full(len(months), np.nan)
    for i, m in enumerate(months):
        j = pos.get(f"{int(m[:4]) - 1}{m[4:]}")
        if j is not None:
            did[i] = (s_in[i] - s_in[j]) - (s_ring[i] - s_ring[j])
    seen = np.isfinite(did)
    low = did < -drop
    for i in np.flatnonzero(seen & low):
        later = low[i:][seen[i:]]
        if later.mean() >= 0.8:
            return int(i)
    return None


def trajectory(months: list[str], s_in: np.ndarray, s_ring: np.ndarray, start: int | None,
               p0: Period, p1: Period, ring_m: int, path: Path) -> None:
    """Chart of monthly NDVI, site vs surroundings.

    The ring sees the same monsoon and crop calendar, so a seasonal swing moves
    both lines together; a quarry makes the site line drop and stay down.
    """
    x = [dt.date.fromisoformat(m + "-01") for m in months]

    fig = Figure(figsize=(7.2, 2.8), dpi=150, facecolor=SURFACE)
    ax = fig.subplots()
    ax.set_facecolor(SURFACE)
    ax.plot(x, s_ring, color=SURROUND, lw=1.5, marker="o", ms=3.5, label=f"Surroundings ({ring_m} m ring)")
    ax.plot(x, s_in, color=SITE, lw=1.5, marker="o", ms=3.5, label="This site")
    for ys, txt in ((s_in, "This site"), (s_ring, "Surroundings")):
        last = max((i for i, v in enumerate(ys) if np.isfinite(v)), default=None)
        if last is not None:
            ax.annotate(txt, (x[last], ys[last]), xytext=(6, 0), textcoords="offset points",
                        va="center", fontsize=7.5, color=INK_2)
    if start is not None:  # label sits under both lines, clear of the end labels
        ax.annotate(f"below last year from {x[start]:%b %Y}", (x[start], s_in[start]),
                    xytext=(x[start] + dt.timedelta(days=8), 0.04), textcoords=("data", "axes fraction"),
                    ha="left", fontsize=7, color=INK_2,
                    arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.8})
    lo = np.nanmin(np.concatenate([s_in, s_ring]))
    ax.set_ylim(bottom=lo - (0.15 if start is not None else 0.08))
    ax.axvline(p1.start, color=AXIS, lw=1, ls="--")
    ax.text(p0.start, 1.02, p0.name, transform=ax.get_xaxis_transform(), fontsize=7.5, color=MUTED)
    ax.text(p1.start, 1.02, "  " + p1.name, transform=ax.get_xaxis_transform(), fontsize=7.5, color=MUTED)
    ax.set_ylabel("Monthly median NDVI", fontsize=8, color=INK_2)
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.tick_params(colors=MUTED, labelsize=7, length=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.legend(loc="upper right", fontsize=7, frameon=False, labelcolor=INK_2, ncols=2,
              bbox_to_anchor=(1, 1.16))
    ax.set_xlim(x[0] - dt.timedelta(days=10), x[-1] + dt.timedelta(days=75))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)


def build(case, geom, epsg: int, items: dict, p0: Period, p1: Period, monthly: dict,
          sites: np.ndarray, grid: GeoBox, cfg: dict, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    ring_m = cfg["cases"]["ring_m"]
    months, s_in, s_ring = site_series(geom, sites, monthly, grid, ring_m)
    start = onset(months, s_in, s_ring)
    first_later = min(i for i, m in enumerate(months) if dt.date.fromisoformat(m + "-01") >= p1.start)
    began_in_later = start is not None and start > first_later
    trajectory(months, s_in, s_ring, start, p0, p1, ring_m, out / "trajectory.png")

    gbox = chip_geobox(geom, epsg, cfg)
    before, after = pick_views(items[p0.key], items[p1.key], gbox, cfg, began_in_later)
    ev = {"chip_bbox_utm": list(gbox.extent.boundingbox), "crs": f"EPSG:{epsg}",
          "onset_month": f"{dt.date.fromisoformat(months[start] + '-01'):%b %Y}" if start is not None else None,
          "began_in_later_period": began_in_later}
    if before and after:
        img_b, img_a = _stretch(before["rgb"], after["rgb"])
        for name, view, img in (("before", before, img_b), ("after", after, img_a)):
            ids = [it.id for it in view["items"]]
            sha = save_chip(img, gbox, geom, f"{name.title()}  ·  {view['day']:%d %b %Y}",
                            f"Sentinel-2 L2A true colour, 10 m, {view['clear']:.0%} clear. {', '.join(ids)}",
                            out / f"{name}.png")
            ev[name] = {"date": view["day"].isoformat(), "items": ids,
                        "stac": [it.get_self_href() for it in view["items"]],
                        "clear_fraction": round(view["clear"], 3), "png_sha256": sha}
    else:
        log.warning("case %s: no usable imagery for chips", case.case_id)
    return ev
