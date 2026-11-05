"""The Change Sentinel: watch a district from orbit and produce case files."""

import odc.stac

__version__ = "0.1.0"

# Public buckets only (the DEM is served as s3:// URLs), so never sign requests.
# Retry generously: slow links drop range requests under load.
odc.stac.configure_rio(cloud_defaults=True, aws={"aws_unsigned": True},
                       GDAL_HTTP_MAX_RETRY=5, GDAL_HTTP_RETRY_DELAY=2, GDAL_HTTP_TIMEOUT=120)
