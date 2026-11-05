"""Command line: python -m sentinel config/nuh.yaml"""

from __future__ import annotations

import argparse
import logging
import warnings

from . import config, pipeline


def _bbox(s: str) -> tuple[float, float, float, float]:
    parts = tuple(float(v) for v in s.split(","))
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("expected LON0,LAT0,LON1,LAT1")
    return parts


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m sentinel",
                                 description="Detect unauthorised change in a district and write case files.")
    ap.add_argument("config", help="YAML run configuration, e.g. config/nuh.yaml")
    ap.add_argument("--subset", type=_bbox, metavar="LON0,LAT0,LON1,LAT1",
                    help="only process this box inside the district (quick tests)")
    ap.add_argument("--top", type=int, help="number of case files to build (default from config)")
    ap.add_argument("--force", action="store_true", help="re-search scenes and recompute cached composites")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("rasterio").setLevel(logging.WARNING)
    warnings.filterwarnings("ignore", message="Could not parse bucket")  # pystac storage-extension noise
    cfg = config.load(args.config)
    if args.top:
        cfg["cases"]["top_n"] = args.top
    pipeline.run(cfg, subset=args.subset, force=args.force)


if __name__ == "__main__":
    main()
