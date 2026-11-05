# The Change Sentinel — open resources

Free and open-source building blocks for each stage of the pipeline. Anything free but **not open** (or with a restrictive licence) is marked. Checked October 2026.

## 1. Imagery

### Optical
- **Sentinel-2 L2A** (10 m, ~5-day revisit) — the default. Access via:
  - [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu) — STAC, openEO (10,000 free credits/month), Copernicus Browser
  - Element 84 Earth Search on AWS — `https://earth-search.aws.element84.com/v1`, COGs, no account (used by this pipeline)
  - Microsoft Planetary Computer STAC — the hosted Hub is retired, the STAC API and data still work
- **HLS (Harmonized Landsat Sentinel-2, NASA)** — Landsat 8/9 + Sentinel-2 on one 30 m grid, 2–3-day revisit, Fmask included
- **Landsat 5/7/8/9 Collection 2** (USGS) — 30 m back to 1984, for long baselines
- **Resourcesat-2/2A LISS-III / LISS-IV / AWiFS** on [Bhoonidhi (NRSC)](https://bhoonidhi.nrsc.gov.in) — under Space Policy 2023, data at 5 m and coarser is open; finer data is free only to government bodies
- **Planet NICFI basemaps** (4.77 m monthly/biannual) — free for non-commercial use with sign-up, *not open*; check your district is inside the tropical coverage
- **Declassified Corona imagery** (1960s–70s, USGS EarthExplorer) — historical baseline ("this used to be a lake")

### Radar (sees through monsoon cloud)
- **Sentinel-1** (C-band, 10 m) — CDSE, ASF, Planetary Computer (incl. terrain-corrected RTC)
- **NISAR** (NASA-ISRO, L+S band) — calibrated L-band [public since 20 July 2026](https://asf.alaska.edu/notices/nisar-l-band-data-now-publicly-available/) via ASF Vertex / `asf_search`; full first-year record expected by end-2026. L-band sees through vegetation and picks up soil disturbance far better than C-band
- **EOS-04 (RISAT-1A)** — analysis-ready products free on Bhoonidhi
- **ASF HyP3** — free on-demand RTC and InSAR processing

### Elevation
Copernicus DEM GLO-30 (on Earth Search as `cop-dem-glo-30`), CartoDEM (Bhuvan), SRTM — terrain shadow, slope, pit depth.

## 2. Ready-made layers (baselines, masks, priors)
- **Dynamic World** (Google, 10 m per-scene land-cover probabilities, in Earth Engine) — crop/built probabilities as seasonal masks
- **ESA WorldCover** 2020/2021 (10 m) — public COGs on AWS (used by this pipeline)
- **JRC Global Surface Water** (1984–present) — water occurrence/seasonality/transitions; baseline for lake infill
- **NASA OPERA** — DSWx (surface water from HLS and Sentinel-1), DIST-ALERT (30 m land disturbance)
- **Forest**: Hansen Global Forest Change, GLAD alerts, Global Forest Watch integrated alerts
- **NASA FIRMS** — active fire, to explain away burn scars
- **Buildings**: Google Open Buildings (incl. 2.5D temporal 2016–2023), Microsoft building footprints, GHSL, WSF
- **Global mining polygons** (training labels for quarries):
  - [Maus et al. 2022 v2](https://pure.iiasa.ac.at/18508) — 44,929 polygons, CC BY-SA, PANGAEA
  - [Tang & Werner 2023](https://gee-community-catalog.org/projects/global-mining/) — CC BY, Zenodo + Earth Engine asset
- **Embeddings** (cheap year-over-year change score):
  - [Google Satellite Embedding / AlphaEarth](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_SATELLITE_EMBEDDING_V1_ANNUAL) — annual 10 m, 2017–2025, CC BY 4.0
  - [TESSERA](https://geotessera-readme.static.hf.space/README.md) (Cambridge) — annual 10 m from S1+S2; weights CC0, `geotessera` MIT
- **[GEE Community Catalog](https://gee-community-catalog.org)** — hundreds of community datasets, many India-specific

### India-specific
- **Bhuvan thematic layers** — LULC 1:50k, wasteland atlas (incl. mining wastelands), National Wetland Decadal Change Atlas; mostly view-only WMS
- **VEDAS** (SAC/ISRO), **India-WRIS** (water bodies, rivers, basins)
- **[Water Bodies Census](https://indiawaterportal.org/articles/indias-first-census-all-water-bodies)** (Jal Shakti, 2023) — ~2.4M water bodies with encroachment recorded; national/state PDFs only, no village-level geometry found
- **PARIVESH** — environment/forest clearance applications include project-boundary KMLs; lease coordinates appear in clearance documents. This is how you define "authorised"
- **State Dept. of Mines & Geology portals** — many publish lease lists with coordinates (varies by state)
- **Protected Planet (WDPA)**, MoEFCC eco-sensitive zone notifications

## 3. Administrative boundaries (jurisdiction)
- **[Survey of India Online Maps](https://onlinemaps.surveyofindia.gov.in)** — official; village boundary database listed at ₹0; 1:50k Open Series maps free as PDF (vector is paid)
- **LGD (Local Government Directory)** — official codes state → village/panchayat; tabular only, join to geometry yourself
- **[SHRUG open polygons](https://devdatalab.medium.com/open-access-geospatial-data-for-india-b9dceb7196bb)** (Development Data Lab) — ~600k villages + 8k towns with Census 2011 IDs; 0–1 km boundary error
- **[DataMeet maps](https://projects.datameet.org/maps/)** — community district/sub-district boundaries, CC BY 2.5 India; some states pre-delimitation
- **Bharat Maps** (NIC) WMS, **geoBoundaries** (open), **GADM** (*non-commercial only*), OSM admin boundaries
- **Bhunaksha** — state cadastral maps; view-only in most states, but it's what an officer will check
- For official use, India's external boundary must follow Survey of India; GADM/geoBoundaries depict disputed areas differently

## 4. Data access & processing (open source)
- STAC: `pystac-client`, `odc-stac`, `stackstac`, `planetary-computer`
- Core: GDAL, rasterio, rioxarray, xarray, dask, geopandas, shapely, DuckDB spatial, GeoParquet
- openEO Python client (CDSE free credits), `eodag`, `cdsetool`
- **FORCE** — full Landsat/S2 pipeline (correction, cloud mask, composites, time-series features) on one machine
- **Open Data Cube**, Digital Earth Australia and Digital Earth Africa notebooks
- **eo-learn** (Sinergise) — includes a water-level monitoring example
- Google Earth Engine + `geemap`, `xee`, `eemont` — *free for non-commercial use, not open source*
- Radar: ESA SNAP + `esa_snappy`, `pyroSAR`, `sarsen`, ISCE3 (NISAR processor)
- QGIS + Semi-Automatic Classification Plugin, Orfeo ToolBox

## 5. Clouds & shadows
- Sentinel-2 **SCL** band — baseline, misses thin cloud and shadow (used by this pipeline)
- **Cloud Score+** (Earth Engine) — best S2 mask if you're on Earth Engine
- **[OmniCloudMask](https://omnicloudmask.readthedocs.io/)** — `pip install omnicloudmask`; clear / thick / thin / shadow; S2, Landsat, PlanetScope
- **s2cloudless** — also precomputed in Earth Engine
- Fmask 4.x / `python-fmask`, CloudSEN12 dataset + models, SEnSeIv2, KappaMask, MAJA (CNES, multi-date)
- Terrain shadow: hillshade from DEM with the acquisition sun angle
- Compositing: per-pixel median, geomedian (`odc-algo`, `hdstats`), best-available-pixel

## 6. Seasonal normalisation & time-series change
- **[nrt (EC JRC)](https://github.com/ec-jrc/nrt)** — EWMA, CuSum, MoSum, CCDC, IQR under one API; fits a harmonic model on a stable history, flags breaks after N consecutive anomalies
- **CCDC** (Earth Engine built-in), `pycold` / S-CCD, `pyccd` (USGS LCMAP)
- **BFAST / bfastmonitor** (R) and a GPU-capable Python port
- **LandTrendr** (LT-GEE)
- **sits** (R, INPE) — Brazil's deforestation monitoring toolchain
- **SEPAL** (FAO) — free hosted platform with BFAST, CCDC and time-series recipes

## 7. Change detection
### Classical
- Index differencing — BSI (bare soil), NDVI, NDBI, MNDWI/AWEI (water) with Otsu thresholds
- Change vector analysis; iMAD (Mort Canty's Python code)
- SAR log-ratio; sequential omnibus test — [eesarseq](https://developers.google.com/earth-engine/tutorials/community/detecting-changes-in-sentinel-1-imagery-pt-4)

### Deep learning toolboxes
- **[open-cd](https://github.com/likyoo/open-cd)** (OpenMMLab, Apache-2.0) — ChangeFormer, BIT, SNUNet, STANet, ChangeStar, CGNet …
- **torchange** (pytorch-change-models) — Changen2, ChangeStar, AnyChange (zero-shot)
- **ChangeMamba**
- **TorchGeo** — datasets (OSCD), samplers, pretrained Sentinel-2 weights
- **segment-geospatial (samgeo)** — Segment Anything for clean pit/fill polygons

### Foundation models (fine-tune with a few hundred labels)
- **Prithvi-EO-2.0** (NASA/IBM; 300M/600M; HLS, multi-date) + **TerraTorch** for fine-tuning
- **TerraMind** (IBM/ESA; S1/S2/DEM/LULC)
- **[OlmoEarth](https://allenai.org/blog/olmoearth-models)** (Ai2, Nov 2025; Nano ~1.4M → Large ~300M params)
- Clay v1.5, Galileo, Presto (tiny pixel time-series model, CPU-friendly), SSL4EO-S12, DOFA, Copernicus-FM, SatlasPretrain

### Training data
OSCD (S2 bitemporal), DynamicEarthNet, LEVIR-CD / S2Looking (high-res), the mining polygons above, CloudSEN12.

## 8. Area, confidence, validation
- **Olofsson et al. 2014**, "Good practices for estimating area and assessing accuracy" — stratified sampling → area with a confidence interval
- AREA2 (Earth Engine), SEPAL area estimation, `mapaccuracy` (Python), Collect Earth Online for labelling points
- Compute area in UTM, never EPSG:4326; calibrate scores (scikit-learn isotonic/Platt) so 0.8 means ~80%

## 9. Case files, evidence, field checks
- **rio-tiler / TiTiler** — before/after chips straight from COGs
- **geemap timelapse**, **leafmap** — animations, interactive maps
- Jinja2 + WeasyPrint / Quarto / Typst — HTML → PDF case files
- **PMTiles + MapLibre GL** — static, serverless map of all cases
- A **STAC record per case** — exact scene IDs, timestamps, processing versions
- **CoMapeo, ODK, KoboToolbox** — offline field verification with geotagged photos

## 10. Prior art worth copying
- **[Amazon Mining Watch](https://source.coop/earthgenome/amazon-mining-watch)** (Earth Genome) — MIT code, CC-BY data; Sentinel-2 CNN ensemble on 480 m patches, Earth Engine only, quarterly since mid-2025. Closest template for quarry detection
- **[Sand Mining Watch](https://ost.ecosyste.ms/projects/307075)** (Berkeley, GPL-3.0) — S1+S2 sand-mine detection, piloting in India with India Sand Watch and Veditum
- **[MapBiomas Alerta](https://alerta.mapbiomas.org/en/metodo-mapbiomas-alerta/)** — each alert ships before/after high-res images cross-checked against property, protected-area and enforcement records. The best model of a "case file"
- **Indian Bureau of Mines' Mining Surveillance System** (2016, not open) — flags changes within 500 m of major-mineral leases. [Per an RTI response](https://thewire.in/political-economy/a-system-to-identify-illegal-mining-raises-hundreds-of-alerts-governments-sleep-on-half-of-them), states acted on 51% of alerts and 14% confirmed illegal mining — alerts without prioritisation get ignored
- **DEA Waterbodies**, **Global Forest Watch**, **Digital Earth Africa** notebooks

## 11. Curated lists
- [awesome-remote-sensing-change-detection](https://www.sourcepulse.org/projects/16291861) (wenhwu, updated 2026)
- satellite-image-deep-learning/techniques
- awesome-gee-community-datasets

## Pitfalls
- **Sentinel-2 offset**: from January 2022 (processing baseline 04.00), L2A reflectance carries a −1000 offset. Use harmonised collections or apply the offset, or you get a fake change at January 2022
- **Monsoon**: June–September optical is mostly cloud. Use Sentinel-1/NISAR then, or compare only full-year or same-season windows
- **Licences**: GADM is non-commercial; DataMeet is CC BY 2.5 IN; Maus 2022 is share-alike
