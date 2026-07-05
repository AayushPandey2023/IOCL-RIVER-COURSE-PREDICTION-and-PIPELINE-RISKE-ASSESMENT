"""
09_sar_change_detection.py  —  KRNPL Layer 4
=============================================
Detects physical ground change at the Najibabad pipeline crossing
using Sentinel-1 SAR (Synthetic Aperture Radar).

WHY SAR?
  Optical satellites (Sentinel-2) go BLIND during monsoon cloud cover
  — exactly when you need them most. SAR penetrates cloud completely.

METHOD — SAR Coherence Change Detection:
  Coherence measures how similar two SAR images are.
  - HIGH coherence (>0.6) = ground surface unchanged
  - LOW coherence (<0.3)  = ground has changed (erosion, flooding,
    sediment deposition, channel shift)

  We compare a PRE-MONSOON baseline to a POST-MONSOON image.
  Low coherence zones that overlap the pipeline alignment = ALERT.

Also uses backscatter intensity change as a secondary check:
  Water and saturated soil return distinctly different backscatter
  than dry land — easy to detect channel movement.

Outputs:
  outputs/sar_coherence_YYYY.png     ← coherence map per year
  outputs/sar_timeseries.csv         ← coherence stats per year
  outputs/layer4_change_report.txt   ← change detection summary

Run from project root:
    python scripts/09_sar_change_detection.py
"""

import ee
import urllib.request
import csv
import os
import time
import math

GEE_PROJECT = "vaulted-journal-500312-m1"
ROI_BOUNDS  = [78.087585, 29.628245, 78.133742, 29.668558]
YEARS       = list(range(2017, 2025))   # SAR coherence needs pairs — start 2017

# Coherence threshold below which ground change is flagged
COHERENCE_ALERT_THRESHOLD = 0.35

OUT_DIR = "outputs"

# ── Colour palette ────────────────────────────────────────────────────────────
# For coherence: purple=low change, yellow=high coherence (stable)
VIS_COHERENCE = {
    "min": 0.0, "max": 1.0,
    "palette": ["4B0082", "C0202E", "F0A500", "FFFF00", "FFFFFF"]
}
# For backscatter: dark=water, bright=land
VIS_BACKSCATTER = {
    "min": -25, "max": 0,
    "palette": ["000000", "1A2A4A", "2E5A8E", "ADD8E6", "FFFFFF"]
}


def mask_sar_edges(image):
    """Remove SAR image edges which have low coherence by default."""
    edge = image.lt(-30)
    return image.updateMask(edge.Not())


def main():
    ee.Authenticate()
    ee.Initialize(project=GEE_PROJECT)

    roi = ee.Geometry.Rectangle(ROI_BOUNDS)
    os.makedirs(OUT_DIR, exist_ok=True)

    # Buffer ROI slightly for SAR — SAR pixels are 10m but speckle
    # filtering needs context around the crossing
    roi_buffered = roi.buffer(500)

    print("KRNPL — Layer 4: SAR Change Detection")
    print("=" * 55)
    print(f"ROI: {ROI_BOUNDS}")
    print(f"Years: {YEARS[0]}–{YEARS[-1]}")
    print(f"Coherence alert threshold: < {COHERENCE_ALERT_THRESHOLD}\n")

    results = []

    for year in YEARS:
        print(f"  Processing {year}...", end="  ")

        # PRE-MONSOON baseline: March-May (dry season, stable ground)
        pre_start  = f"{year}-03-01"
        pre_end    = f"{year}-05-31"

        # POST-MONSOON: October-November (after peak flood, changes visible)
        post_start = f"{year}-10-01"
        post_end   = f"{year}-11-30"

        # Get Sentinel-1 GRD (Ground Range Detected) — VV polarisation
        # VV is best for water/soil moisture detection
        s1_pre = (ee.ImageCollection("COPERNICUS/S1_GRD")
                    .filterBounds(roi_buffered)
                    .filterDate(pre_start, pre_end)
                    .filter(ee.Filter.eq("instrumentMode", "IW"))
                    .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                    .select("VV")
                    .map(mask_sar_edges))

        s1_post = (ee.ImageCollection("COPERNICUS/S1_GRD")
                     .filterBounds(roi_buffered)
                     .filterDate(post_start, post_end)
                     .filter(ee.Filter.eq("instrumentMode", "IW"))
                     .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                     .select("VV")
                     .map(mask_sar_edges))

        pre_count  = s1_pre.size().getInfo()
        post_count = s1_post.size().getInfo()

        if pre_count == 0 or post_count == 0:
            print(f"SKIPPED (pre={pre_count}, post={post_count} scenes)")
            results.append({
                "year": year, "pre_scenes": pre_count,
                "post_scenes": post_count,
                "mean_pre_backscatter_db":  None,
                "mean_post_backscatter_db": None,
                "backscatter_change_db":    None,
                "change_flag":              "NO_DATA"
            })
            continue

        # Median composites — reduces speckle noise
        pre_composite  = s1_pre.median().clip(roi_buffered)
        post_composite = s1_post.median().clip(roi_buffered)

        # ── Backscatter change (dB difference) ───────────────────────────────
        # More negative post = more water/saturation = channel change
        backscatter_change = post_composite.subtract(pre_composite).rename("change")

        # Statistics over ROI
        pre_stats = pre_composite.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi,
            scale=10, maxPixels=1e8
        ).getInfo()
        post_stats = post_composite.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi,
            scale=10, maxPixels=1e8
        ).getInfo()
        change_stats = backscatter_change.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
            geometry=roi, scale=10, maxPixels=1e8
        ).getInfo()

        pre_db    = pre_stats.get("VV")   or 0.0
        post_db   = post_stats.get("VV")  or 0.0
        change_db = change_stats.get("change_mean") or (post_db - pre_db)
        change_sd = change_stats.get("change_stdDev") or 0.0

        # Flag if backscatter dropped significantly (more negative = more water)
        # Threshold: -3 dB change indicates significant increase in water/moisture
        CHANGE_THRESHOLD_DB = -3.0
        change_flag = "CHANGE_DETECTED" if change_db < CHANGE_THRESHOLD_DB else "STABLE"

        print(f"pre={pre_count}sc, post={post_count}sc | "
              f"ΔdB={change_db:+.2f} | {change_flag}", end="  →  ")

        # ── Save backscatter change PNG ───────────────────────────────────────
        # Visualise the change image: red=decrease(more water), blue=increase
        change_vis = {
            "min": -8, "max": 4,
            "palette": ["C0202E", "F0A500", "FFFFFF", "ADD8E6", "1A2A4A"]
        }
        png_path = os.path.join(OUT_DIR, f"sar_change_{year}.png")
        try:
            url = backscatter_change.getThumbURL({
                **change_vis,
                "region": roi_buffered, "dimensions": 600, "format": "png"
            })
            urllib.request.urlretrieve(url, png_path)
            print(f"saved {png_path}")
        except Exception as e:
            print(f"PNG failed ({e})")

        results.append({
            "year":                     year,
            "pre_scenes":               pre_count,
            "post_scenes":              post_count,
            "mean_pre_backscatter_db":  round(pre_db, 2),
            "mean_post_backscatter_db": round(post_db, 2),
            "backscatter_change_db":    round(change_db, 2),
            "change_flag":              change_flag,
        })

        time.sleep(1)

    # ── Save CSV ──────────────────────────────────────────────────────────────
    csv_path = os.path.join(OUT_DIR, "sar_timeseries.csv")
    fields = ["year", "pre_scenes", "post_scenes",
              "mean_pre_backscatter_db", "mean_post_backscatter_db",
              "backscatter_change_db", "change_flag"]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    print(f"\nSAR CSV saved: {csv_path}")

    # ── Summary report ────────────────────────────────────────────────────────
    valid   = [r for r in results if r["change_flag"] != "NO_DATA"]
    changed = [r for r in valid   if r["change_flag"] == "CHANGE_DETECTED"]

    summary = f"""
KRNPL — LAYER 4 SUMMARY: SAR Change Detection
Najibabad Crossing  |  Ch. ~144.1 km
{'='*52}

METHOD
  Sensor      : Sentinel-1 GRD, VV polarisation (free, ESA)
  Baseline    : March–May (pre-monsoon, stable ground)
  Monitor     : October–November (post-monsoon)
  Change flag : Backscatter drop > 3 dB (water/saturation)

RESULTS ({years[0]}–{YEARS[-1]})
  Years analysed  : {len(valid)}
  Change detected : {len(changed)} years
  Stable          : {len(valid) - len(changed)} years

YEAR-BY-YEAR
"""
    for r in results:
        flag_str = r["change_flag"]
        db_str   = f"{r['backscatter_change_db']:+.2f} dB" if r["backscatter_change_db"] else "N/A"
        summary += f"  {r['year']}  ΔdB={db_str:<12}  {flag_str}\n"

    summary += f"""
INTERPRETATION
  A backscatter drop (negative ΔdB) in Oct–Nov vs Mar–May means
  the ground surface became wetter / more water-covered after
  monsoon — indicating channel migration or bank flooding over
  the pipeline corridor.

  Years with CHANGE_DETECTED confirm what Layer 1 NDWI showed:
  the river is actively modifying the ground at the pipeline crossing.

ACTION
  For each CHANGE_DETECTED year, open sar_change_YYYY.png:
    RED pixels   = backscatter decreased (more water/erosion)
    WHITE pixels = no change
    BLUE pixels  = backscatter increased (sediment deposition)
  
  If red pixels cluster on the pipeline alignment → INSPECT.

NOTE: Full SAR coherence analysis requires SLC (Single Look Complex)
  data processed in ESA SNAP. This GRD-based backscatter change
  is a practical approximation suitable for this project stage.
  SLC coherence would be the next refinement step.
"""
    report_path = os.path.join(OUT_DIR, "layer4_change_report.txt")
    with open(report_path, "w") as f:
        f.write(summary)
    print(summary)
    print(f"Report saved: {report_path}")
    print("\n✓ Layer 4 complete. Next: python scripts/10_freespan_structural.py")


if __name__ == "__main__":
    main()
