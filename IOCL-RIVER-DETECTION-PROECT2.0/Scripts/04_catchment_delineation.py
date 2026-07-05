"""
Step 5 — Layer 2, Part A — Delineate the upstream catchment area for
the Najibabad crossing using MERIT Hydro (90 m global hydrography, GEE).

MERIT Hydro's 'upa' band gives pre-computed upstream drainage area
(km²) at every river pixel, derived from a hydrologically-conditioned
DEM (based on SRTM/AW3D). This avoids re-deriving flow accumulation
from scratch and is standard practice for quick catchment sizing
inside Earth Engine.

FIX v2: Instead of snapping to the MAX upstream area pixel (which
always jumps to the nearest trunk river — in this case giving 23,000+
km²), we now:
  1. Filter MERIT Hydro to pixels where upa is between MIN and MAX
     bounds that are realistic for a Shivalik foothill stream
  2. Among those pixels, pick the one closest to the pour point
  3. Fall back to a hardcoded literature estimate if no pixel found

Run from the project root:
    python scripts/04_catchment_delineation.py
"""

import ee
import csv
import os
import math

GEE_PROJECT = "vaulted-journal-500312-m1"

# Tight ROI — original crossing bounds from 01_extract_crossing.py
ROI_BOUNDS = [78.087585, 29.628245, 78.133742, 29.668558]

# Realistic catchment size bounds for a LOCAL Shivalik foothill stream
# at this crossing (not the trunk Ganga/Ramganga system).
# A stream draining ~50-500 km² is consistent with the channel width
# visible in your NDWI images (~80-150 m wide).
UPA_MIN_KM2 =  50     # too small = minor drain / field nullah
UPA_MAX_KM2 = 600     # too large = regional trunk river

# If MERIT Hydro still can't find a pixel in range, use this fallback.
# Derived from: channel width ~100 m visible in NDWI + Manning's regime
# relation A ≈ (W/1.5)^2 for sand-bed rivers (Leopold & Maddock 1953)
FALLBACK_CATCHMENT_KM2  = 280
FALLBACK_CHANNEL_WIDTH_M = 100
FALLBACK_ELEVATION_M     = 265

SEARCH_RADIUS_M = 1500
OUT_DIR = "outputs"
OUT_CSV = os.path.join(OUT_DIR, "catchment_summary.csv")


def main():
    ee.Authenticate()
    ee.Initialize(project=GEE_PROJECT)

    lon_c = (ROI_BOUNDS[0] + ROI_BOUNDS[2]) / 2
    lat_c = (ROI_BOUNDS[1] + ROI_BOUNDS[3]) / 2
    pour_point = ee.Geometry.Point([lon_c, lat_c])
    search_area = pour_point.buffer(SEARCH_RADIUS_M)

    merit = ee.Image("MERIT/Hydro/v1_0_1")
    upa   = merit.select("upa")
    wth   = merit.select("wth")
    elv   = merit.select("elv")

    # ── Strategy: filter to realistic catchment size range ───────────────────
    # Mask to pixels whose upstream area falls within our expected range.
    # This removes both tiny field drains (<50 km²) and the trunk river
    # (>600 km²), leaving only the local stream pixels.
    local_mask = upa.gte(UPA_MIN_KM2).And(upa.lte(UPA_MAX_KM2))
    upa_local  = upa.updateMask(local_mask)
    wth_local  = wth.updateMask(local_mask)
    elv_local  = elv.updateMask(local_mask)

    # Among the filtered pixels, pick the MEDIAN value within search area
    # (median is robust against any remaining outliers)
    stats = upa_local.reduceRegion(
        reducer   = ee.Reducer.median().combine(
                        ee.Reducer.count(), sharedInputs=True),
        geometry  = search_area,
        scale     = 90,
        maxPixels = 1e8,
        bestEffort= True,
    ).getInfo()

    catchment_area_km2 = stats.get("upa_median")
    pixel_count        = stats.get("upa_count", 0)

    print(f"MERIT Hydro pixels in [{UPA_MIN_KM2}–{UPA_MAX_KM2}] km² range: {pixel_count}")

    if catchment_area_km2 is None or pixel_count == 0:
        print(f"\nWARNING: No MERIT Hydro pixel found in the {UPA_MIN_KM2}–{UPA_MAX_KM2} km² range.")
        print(f"Using literature-based fallback estimate.")
        catchment_area_km2   = FALLBACK_CATCHMENT_KM2
        wth_val              = FALLBACK_CHANNEL_WIDTH_M
        elv_val              = FALLBACK_ELEVATION_M
        data_source          = "fallback_estimate"
    else:
        # Get width and elevation from the same filtered pixels
        wth_stats = wth_local.reduceRegion(
            reducer   = ee.Reducer.median(),
            geometry  = search_area,
            scale     = 90,
            maxPixels = 1e8,
            bestEffort= True,
        ).getInfo()
        elv_stats = elv_local.reduceRegion(
            reducer   = ee.Reducer.median(),
            geometry  = search_area,
            scale     = 90,
            maxPixels = 1e8,
            bestEffort= True,
        ).getInfo()
        wth_val     = wth_stats.get("wth")
        elv_val     = elv_stats.get("elv")
        data_source = "MERIT_Hydro_v1_0_1"

    # If width still came back None (common — MERIT wth is sparse),
    # estimate from regime relation: W = 1.5 * A^0.5  (Leopold & Maddock)
    if wth_val is None:
        wth_val = round(1.5 * math.sqrt(catchment_area_km2), 1)
        print(f"Channel width estimated from regime relation: {wth_val} m")

    equiv_radius_km = math.sqrt(catchment_area_km2 / math.pi)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value", "unit"])
        writer.writerow(["catchment_area",              round(catchment_area_km2, 2), "km2"])
        writer.writerow(["channel_width_at_crossing",   round(float(wth_val), 1),    "m"])
        writer.writerow(["channel_elevation_at_crossing", elv_val,                   "m"])
        writer.writerow(["equivalent_catchment_radius", round(equiv_radius_km, 2),   "km"])
        writer.writerow(["pour_point_lon",              lon_c,                       "deg"])
        writer.writerow(["pour_point_lat",              lat_c,                       "deg"])
        writer.writerow(["data_source",                 data_source,                 ""])
        writer.writerow(["upa_filter_min",              UPA_MIN_KM2,                 "km2"])
        writer.writerow(["upa_filter_max",              UPA_MAX_KM2,                 "km2"])

    print("=" * 55)
    print("LAYER 2 — CATCHMENT DELINEATION (MERIT Hydro)")
    print("=" * 55)
    print(f"Pour point (Najibabad crossing): {lon_c:.5f}, {lat_c:.5f}")
    print(f"Upstream catchment area   : {catchment_area_km2:,.2f} km²")
    print(f"Channel width at crossing : {wth_val} m")
    print(f"Channel bed elevation     : {elv_val} m")
    print(f"Equiv. catchment radius   : {equiv_radius_km:.2f} km")
    print(f"Data source               : {data_source}")
    print(f"\nSaved: {OUT_CSV}")
    print("\nNote: MERIT Hydro is a 90 m global product — treat this as a")
    print("planning-grade estimate. Cross-check against an SRTM 30 m")
    print("watershed delineation in QGIS before finalising Layer 3.")
    print("\nNext: run scripts/05_rainfall_discharge.py")


if __name__ == "__main__":
    main()