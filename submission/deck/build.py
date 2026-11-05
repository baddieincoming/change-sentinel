"""Render the submission deck from a run's outputs: deck.html -> PDF and slide PNGs.

    .venv/bin/python submission/deck/build.py [output/nuh-subset]
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TIERS = [("Inspect", "#d03b3b"), ("Review", "#ec835a"), ("Low", "#898781")]


def chrome(*args):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--virtual-time-budget=8000", *args], check=True, capture_output=True)


def screenshot(page: Path, out: Path, width: int, height: int, scale: float = 2):
    chrome(f"--screenshot={out}", f"--window-size={width},{height}", f"--force-device-scale-factor={scale}",
           page.as_uri())


def chip_image(png: Path) -> Image.Image:
    """The square image area of an evidence chip, without its title and caption."""
    im = Image.open(png)
    w, h = im.size  # 600 x 660: Figure(4, 4.4) at 150 dpi, axes 3%-97% x 8%-92%
    side = round(0.84 * h)
    top = round(0.08 * h)
    left = (w - side) // 2
    return im.crop((left, top, left + side, top + side))


def main(run_dir: Path):
    img = HERE / "img"
    img.mkdir(exist_ok=True)
    run = json.loads((run_dir / "run.json").read_text())
    cases = pd.read_csv(run_dir / "cases.csv")
    have = [c for c in cases.itertuples() if (run_dir / "cases" / c.case_id / "after.png").exists()]

    # featured case: best-ranked in-district Inspect/Review case with images, else the top case
    pick = [c for c in have if c.in_district_share >= 0.5 and c.tier in ("Inspect", "Review")] or have
    f = pick[0]
    (HERE / "featured.txt").write_text(f.case_id)  # the video shows the same case
    cdir = run_dir / "cases" / f.case_id
    ev = json.loads((cdir / "evidence.json").read_text())["evidence"]
    for name in ("before", "after", "trajectory"):
        Image.open(cdir / f"{name}.png").save(img / f"{name}.png")
    chip_image(cdir / "after.png").resize((940, 940), Image.LANCZOS).save(img / "hero.png")

    # ranked list: crop the table from a render of the real index page
    screenshot(run_dir / "index.html", img / "index_full.png", 1280, 1400)
    Image.open(img / "index_full.png").crop((200, 500, 2360, 1636)).save(img / "index.png")  # header + 4 rows
    ov = Image.open(run_dir / "overview.png")
    w, h = ov.size
    ov.crop((round(0.12 * w), round(0.50 * h), round(0.80 * w), h)).save(img / "overview.png")

    counts = cases["tier"].value_counts()
    outside = cases[cases.in_district_share < 0.5]
    crop_low = cases[(cases.tier == "Low") & (cases.cropland_frac >= 0.5)]
    notes = []
    if len(outside):
        notes.append(f"{len(outside)} site{'s' if len(outside) > 1 else ''} just across the Rajasthan border, in an "
                     "active quarry cluster, are kept and marked \"refer to the neighbouring administration\".")
    if len(crop_low):
        notes.append(f"{len(crop_low)} on mapped cropland, likely fallow fields, are kept but ranked last.")
    notes.append("Caught in testing: a network drop silently blanked six months of imagery. Downloads now retry, "
                 "then stop the run rather than cache bad data.")
    notes.append("The whole district (~6 GB of imagery) has not been run yet: the link to the imagery servers "
                 "is the limit, not the code.")
    inspect = int(counts.get("Inspect", 0))
    res = {
        "headline": f"Test run: {len(cases)} sites in {run['area_km2']:.0f} km², {inspect} worth sending someone to",
        "area": f"{run['area_km2']:.0f}", "dates": sum(run["dates_used"]), "sites": len(cases),
        "tiers": [{"name": n, "colour": c, "n": int(counts.get(n, 0))} for n, c in TIERS if counts.get(n, 0)],
        "notes": notes,
    }
    window = f"{ev['before']['date']} to {ev['after']['date']}"
    if ev.get("onset_month"):
        window += f", onset {ev['onset_month']}"
    feat = {"case_id": f.case_id, "village": f.Village, "tehsil": f.Tehsil, "district": f.District,
            "area": f"{f.area_ha:.1f}", "area_lo": f"{f.area_ha_low:.1f}", "area_hi": f"{f.area_ha_high:.1f}",
            "conf": round(100 * f.confidence), "tier": f.tier, "window": window}
    hero = {"caption": f"{f.case_id}, {f.Village}, {f.Tehsil}. Sentinel-2 true colour, "
                       f"{pd.Timestamp(ev['after']['date']):%d %b %Y}; outline is the detected change."}
    traj = {"caption": f"{f.case_id}: monthly NDVI inside the site against a 300 m ring. Seasons move both lines; "
                       "the quarry pulls the site line down and keeps it there."}

    html = Environment(loader=FileSystemLoader(HERE)).get_template("deck.html.j2").render(
        res=res, feat=feat, hero=hero, traj=traj)
    page = HERE / "deck.html"
    page.write_text(html)

    out = ROOT / "submission" / "ChangeSentinel_Deck.pdf"
    chrome(f"--print-to-pdf={out}", "--no-pdf-header-footer", "--print-to-pdf-no-header", page.as_uri())
    n = html.count('<section class="slide')
    screenshot(page, img / "deck_full.png", 1280, 720 * n, scale=1.5)
    full = Image.open(img / "deck_full.png")
    slides = HERE / "slides"
    slides.mkdir(exist_ok=True)
    for i in range(n):
        full.crop((0, i * 1080, 1920, (i + 1) * 1080)).save(slides / f"slide-{i + 1:02d}.png")
    print(out, f"{out.stat().st_size / 1e6:.1f} MB,", n, "slides; featured", f.case_id)


if __name__ == "__main__":
    main(ROOT / (sys.argv[1] if len(sys.argv) > 1 else "output/nuh-subset"))
