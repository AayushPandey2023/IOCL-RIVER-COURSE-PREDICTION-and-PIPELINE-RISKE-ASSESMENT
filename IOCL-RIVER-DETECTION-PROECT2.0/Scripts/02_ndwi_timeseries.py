"""
02_ndwi_timeseries.py  —  KRNPL Layer 1
========================================
Loops 2016–2024, pulls a POST-MONSOON (Oct–Nov) Sentinel-2 NDWI
composite for each year over the Najibabad crossing ROI, and:
  • saves a colour PNG per year  (outputs/ndwi_YYYY.png)
  • measures water-pixel count and mean NDWI inside the ROI
  • writes a summary CSV         (outputs/ndwi_timeseries.csv)

WHY OCT–NOV instead of Jan–Mar like main.py used?
  Jan–Mar is dry season — the river is at its smallest.
  Oct–Nov is POST-MONSOON — the channel is at peak extent,
  so we can see exactly how much of the floodplain was active
  that year.  Comparing Oct–Nov across years shows migration.

Run from the project root:
    python scripts/02_ndwi_timeseries.py
"""

import ee
import urllib.request
import csv
import os
import time

# ── Config ────────────────────────────────────────────────────────────────────
GEE_PROJECT = "vaulted-journal-500312-m1"   # your existing project ID

# Same ROI bounding box your 01_extract_crossing.py printed
# [lon_min, lat_min, lon_max, lat_max]
ROI_BOUNDS = [78.087585, 29.628245, 78.133742, 29.668558]

YEARS = list(range(2016, 2025))   # 2016 → 2024  (Sentinel-2 launched Apr 2015)

# Post-monsoon window — consistent across all years for fair comparison
MONTH_START = "10-01"   # 1 Oct
MONTH_END   = "11-30"   # 30 Nov

OUT_DIR = "outputs"

# Colour palette — same brown→blue you already have in main.py
VIS = {
    "min": -0.3,
    "max":  0.4,
    "palette": ["8B4513", "D2B48C", "F0E68C", "ADD8E6", "0000FF"],
}

# ── Cloud mask (identical to main.py) ────────────────────────────────────────
def mask_clouds(img):
    scl = img.select("SCL")
    mask = (scl.neq(3).And(scl.neq(8))
               .And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11)))
    return img.updateMask(mask)

# ── NDWI (identical to main.py) ───────────────────────────────────────────────
def compute_ndwi(img):
    ndwi = img.normalizedDifference(["B3", "B8"]).rename("NDWI")
    return img.addBands(ndwi)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ee.Authenticate()
    ee.Initialize(project=GEE_PROJECT)

    roi = ee.Geometry.Rectangle(ROI_BOUNDS)
    os.makedirs(OUT_DIR, exist_ok=True)

    # Total ROI pixel count — needed to convert water_pixels → percentage
    # At 10 m resolution: pixel area = 100 m²
    roi_area_m2 = roi.area().getInfo()
    total_pixels_in_roi = roi_area_m2 / 100          # 10 m × 10 m pixels
    print(f"ROI area: {roi_area_m2/1e6:.3f} km²  ({int(total_pixels_in_roi):,} pixels at 10 m)")
    print(f"Processing {len(YEARS)} years — Oct–Nov window\n")

    results = []

    for year in YEARS:
        date_start = f"{year}-{MONTH_START}"
        date_end   = f"{year}-{MONTH_END}"

        print(f"  {year}  ({date_start} → {date_end})", end="  ")

        collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(roi)
            .filterDate(date_start, date_end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))  # slightly relaxed for monsoon tail
            .map(mask_clouds)
            .map(compute_ndwi)
        )

        count = collection.size().getInfo()
        print(f"{count} scenes", end="  →  ")

        if count == 0:
            print("SKIPPED (no cloud-free scenes)")
            results.append({
                "year": year, "scenes": 0,
                "water_pixels": None, "water_pct": None,
                "mean_ndwi": None, "max_ndwi": None,
                "png_saved": False
            })
            continue

        # Median composite over all scenes in the window
        composite = collection.select("NDWI").median().clip(roi)

        # ── Statistics ────────────────────────────────────────────────────────
        # Mean and max NDWI across the ROI
        stats = composite.reduceRegion(
            reducer   = ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
            geometry  = roi,
            scale     = 10,
            maxPixels = 1e8
        ).getInfo()

        mean_ndwi = stats.get("NDWI_mean") or 0.0
        max_ndwi  = stats.get("NDWI_max")  or 0.0

        # Count pixels where NDWI > 0  (water pixels)
        water_mask = composite.gt(0.0)
        water_count = water_mask.reduceRegion(
            reducer   = ee.Reducer.sum(),
            geometry  = roi,
            scale     = 10,
            maxPixels = 1e8
        ).getInfo().get("NDWI", 0) or 0

        water_pct = (water_count / total_pixels_in_roi) * 100 if total_pixels_in_roi else 0

        print(f"water {water_pct:.1f}%  mean NDWI {mean_ndwi:.3f}", end="  →  ")

        # ── Save PNG ──────────────────────────────────────────────────────────
        png_path = os.path.join(OUT_DIR, f"ndwi_{year}.png")
        url = composite.getThumbURL({
            **VIS,
            "region":     roi,
            "dimensions": 800,
            "format":     "png"
        })
        urllib.request.urlretrieve(url, png_path)
        print(f"saved {png_path}")

        results.append({
            "year":         year,
            "scenes":       count,
            "water_pixels": int(water_count),
            "water_pct":    round(water_pct, 2),
            "mean_ndwi":    round(mean_ndwi, 4),
            "max_ndwi":     round(max_ndwi, 4),
            "png_saved":    True
        })

        time.sleep(1)   # polite pause between GEE calls

    # ── Save CSV ──────────────────────────────────────────────────────────────
    csv_path = os.path.join(OUT_DIR, "ndwi_timeseries.csv")
    fields = ["year", "scenes", "water_pixels", "water_pct", "mean_ndwi", "max_ndwi", "png_saved"]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n{'='*55}")
    print(f"CSV saved: {csv_path}")
    print(f"\nYear-by-year summary:")
    print(f"{'Year':<6} {'Scenes':<8} {'Water%':<10} {'MeanNDWI':<12} {'MaxNDWI'}")
    print("-" * 50)
    for r in results:
        if r["water_pct"] is not None:
            trend = "▲" if results.index(r) > 0 and results[results.index(r)-1]["water_pct"] and \
                           r["water_pct"] > results[results.index(r)-1]["water_pct"] else "▼"
            print(f"{r['year']:<6} {r['scenes']:<8} {r['water_pct']:<10.1f} "
                  f"{r['mean_ndwi']:<12.4f} {r['max_ndwi']:.4f}  {trend}")
        else:
            print(f"{r['year']:<6} {'—':<8} {'NO DATA'}")

    print(f"\n✓ Done. Next step: run  scripts/03_plot_trend.py")


if __name__ == "__main__":
    main()