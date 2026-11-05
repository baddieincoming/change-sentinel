# The Change Sentinel

Watches one district in free Sentinel-2 imagery, finds **new open-cast quarries**, and writes a ranked list of case files, each with before/after images, area, confidence, the date window, and the village, block, tehsil and district it falls in.

The default run covers **Nuh district, Haryana**, on a laptop.

## Why quarrying, and why Nuh

**One change class, chosen because it can be called "unauthorised" without guessing.** A detection is only actionable if the system can tell an officer *why it shouldn't be there*. For quarrying the legal reference is geometric: a site is either inside a lease polygon or it isn't. In Nuh there is not even a lease layer to fetch. The Supreme Court suspended all mining in the Aravalli hills of Faridabad, Gurugram and Nuh (then Mewat) on 8 May 2009, and the ban was still reported in force in 2024. A new pit in Nuh's hills is presumptively illegal, and illegal mining there has continued for years.

**Quarries are easy to separate from seasonal noise.** Crops go bare for a few months and green up again. A working quarry is bare rock, or a flooded pit, in nearly every clear view all year. That persistence is the signal the detector keys on.

**The existing system's failure mode is the design target.** The Indian Bureau of Mines' Mining Surveillance System has flagged changes near leases since 2016. An RTI response found states acted on about half the alerts and only 14% confirmed illegal mining. Alerts without evidence and ranking get ignored, so every case here ships with its evidence and a plain-language reason for its rank.

## Quick start

```bash
python3 -m venv .venv            # or: uv venv --python 3.12
.venv/bin/pip install -r requirements.txt

# quick test on part of the district (~250 km²)
.venv/bin/python -m sentinel config/nuh.yaml --subset 76.86,27.70,77.00,27.86 --top 8

# the whole district
.venv/bin/python -m sentinel config/nuh.yaml
open output/nuh/index.html
```

Offline tests of the detection, dating and download-failure rules: `.venv/bin/pip install pytest && .venv/bin/python -m pytest tests`.

No accounts or API keys are needed. Imagery streams from public cloud-optimised GeoTIFFs. Composites are cached in `data/`, so re-running with different detection, confidence or priority settings takes seconds. Changing the cloud mask or index thresholds rebuilds them.

## How it works

| Brief asks for | What the pipeline does | Code |
|---|---|---|
| Free imagery, one district | Sentinel-2 L2A Collection 1 from Element 84 Earth Search (STAC), 20 m grid in UTM over the district plus a 1 km border buffer | `imagery.py`, `aoi.py` |
| Cloud and shadow handling | Scene classification mask (cloud, cirrus, cloud shadow, terrain shadow), grown by 40 m. Peak greenness uses the 90th percentile, which leftover cloud can only pull down, never up | `imagery.py`, `composites.py` |
| Seasonal normalisation | Each pixel is summarised over a **full 12-month window**, so every season appears once on both sides of the comparison. The detector compares *how often* a pixel is bare across the year, not a single date | `composites.py` |
| One change class | A pixel is flagged when it went from rarely bare to bare-or-pit in ≥75% of clear views, its bare share rose by ≥30 points, and its peak NDVI fell by ≥0.10. Speckle is removed, sites under 0.5 ha are dropped, and each site is tagged "new" or "expansion" | `detect.py` |
| Case file | Clearest recent image and a same-season image one year earlier, rendered with an identical stretch. Area with a boundary-uncertainty range, confidence, change date window, village → state, coordinates, scene IDs and SHA-256 of each image | `evidence.py`, `report.py` |
| Prioritisation | Grouped by confidence tier (Inspect, Review, Low), then ordered by `confidence × log₂(1 + area)`, scaled down inside authorised areas or outside the district. Every rank comes with a written list of reasons | `prioritise.py` |

**Monthly NDVI trajectory.** Each case also gets a chart of monthly NDVI inside the site against a 300 m ring around it. The ring experiences the same monsoon and crop calendar, so seasonal swings move both lines together, while a quarry pulls the site line down and keeps it there. It shows the seasonal normalisation in a way an officer can read without trusting the algorithm.

**Confidence** is a logistic score over six features: bare share after, increase in bare share, NDVI drop, observation count, slope (quarries in Nuh are in the hills, fields are flat), and the ESA WorldCover cropland share as a penalty against fallow fields. The weights in `config.py` are hand-set priors. See *Calibrating confidence* below.

## Outputs

```
output/nuh/
  index.html              ranked list: tier, case, village, area, confidence, change window, thumbnail
  overview.png            district map with numbered cases
  cases.geojson / .csv    every site, all attributes (for QGIS or a spreadsheet)
  cases/<CASE-ID>/
    case.html             printable case file
    before.png, after.png same-season pair, same stretch, outline of the detected area
    trajectory.png        monthly NDVI, site vs surroundings
    evidence.json         machine-readable record: geometry, scene IDs, STAC links, hashes
```

Case IDs are stable: the same site in the same period always gets the same ID, so a re-run doesn't renumber what an officer already has.

**Sample results** from the test-area run are included in `output/nuh-subset/`. Open `output/nuh-subset/index.html` in a browser, no install needed.

## Compute budget

The bottleneck is **bytes downloaded**, not CPU. Measured on a MacBook (8 GB RAM) over home broadband in India:

| | Test area (~250 km²) | Whole of Nuh (1,848 km² incl. 1 km border buffer) |
|---|---|---|
| Image dates read | 33 + 35 | ~33 + 35 |
| Download | ~0.5 GB (estimate) | ~6 GB (estimate, scaled from the test area) |
| Peak memory | < 1 GB | ~1.5 GB |
| CPU time | ~1 min | a few minutes |
| Wall time | ~20 min on a congested link (measured); case files 2–5 min | ~10 min at 80 Mbps; 1 h+ at 10 Mbps (estimate) |

How the cost is kept down:

- **Each COG block is downloaded once.** Each acquisition date is read for the whole district in one call, rather than in tiles that would each fetch shared 10 km blocks again. Tiling cost 4× the bytes in testing.
- **Only the clearest 3 dates per month** are used. Monthly spread matters more for seasonal statistics than scene count.
- **10 m bands are read from their 20 m overviews.** Detection runs at 20 m. Only the evidence chips use 10 m.
- **Per-date values are kept as 1-byte quantised NDVI and bare-soil stacks**, so a year of observations for the district fits in under 1 GB.
- **Composites are cached.** Re-running with new detection, confidence or priority settings takes seconds and downloads nothing except chips.

The imagery lives in AWS `us-west-2`. From a slow or congested link, run the composites on a free cloud notebook (Google Colab or GitHub Codespaces, both well connected to AWS), then copy back `data/nuh/`, about 200 MB.

## Another district or change class

Copy `config/nuh.yaml` and change:

- `district.name` / `state`: the geoBoundaries ADM2 name. Older names are used in places, as with Mewat for Nuh.
- `periods`: two or more windows. Keep them the same calendar length.
- `authorised_areas`: lease polygons from PARIVESH or the state mining department (KML, GeoJSON or GPKG). Sites inside a lease are ranked down. Sites within `lease_buffer_m` are flagged as possible overreach.
- `context_layers`: protected areas, water bodies, forest boundaries and similar, each with a priority multiplier.
- `detection` / `indices` thresholds. For **lake infill**, invert the rule: water share falls and bare or built share rises. JRC Global Surface Water gives the historical baseline.

## Calibrating confidence

The confidence formula is the same logistic form you would fit from labelled data:

1. Run the district and open `cases.csv`.
2. Label ~100 sites as quarry / not quarry from the before/after pairs (or field visits). Collect Earth Online works well for this.
3. Fit `sklearn.linear_model.LogisticRegression` on the six features in `prioritise.features()` and paste the coefficients into `confidence.weights`.
4. Report precision at the "Inspect" threshold, and estimate total disturbed area with stratified sampling (Olofsson et al. 2014) rather than summing polygons.

## Known limitations

- **Fallow fields and brick kilns** can look like quarries for a whole year. The cropland and slope features push them down the list, but they are not removed.
- **Monsoon gaps.** Optical imagery is thin from July to September. Sentinel-1 or NISAR L-band radar would fill this, and NISAR has been public on ASF since July 2026. That is the main next step.
- **20 m detection grid.** Pits narrower than ~40 m, or sites under 0.5 ha, are missed. Evidence chips are at 10 m.
- **Boundaries** come from geoBoundaries (ODbL; LGD and Census 2011 sources). Village polygons are simplified Census 2011 shapes. This is not an official Survey of India map. Confirm the khasra on Bhunaksha.
- **Legal status.** The authorisation note in `config/nuh.yaml` reflects the 2009 Supreme Court order as reported up to 2024. Verify the current position before acting.

## Data and licences

| Data | Source | Licence |
|---|---|---|
| Sentinel-2 L2A Collection 1 | Copernicus, via Element 84 Earth Search | Copernicus free and open |
| Copernicus DEM GLO-30 | ESA, via Earth Search | Copernicus DEM licence (free) |
| ESA WorldCover 2021 | ESA, public S3 | CC BY 4.0 |
| Admin boundaries ADM1–ADM5 | geoBoundaries (LGD, Census 2011) | ODbL 1.0 / CC BY 2.5 IN (ADM1) |

See `RESOURCES.md` for the wider landscape of open tools and data.
