"""
Step 6 — Layer 2, Part B — Rainfall-to-discharge monitoring for the
Najibabad crossing using NASA GPM IMERG (half-hourly precipitation).

Method (report section 7.2 — Rational Method):
    Q = C * I * A / 360
    Q = peak discharge (m3/s)
    C = runoff coefficient (dimensionless, catchment-dependent)
    I = peak rainfall intensity (mm/hr)
    A = catchment area (km2, from 04_catchment_delineation.py)

This script pulls one monsoon season at a time (2016-2024, matching
the Layer 1 window), finds the peak sustained rainfall intensity over
the crossing catchment, converts it to discharge, and compares it
against a PROXY critical threshold.

IMPORTANT: the true critical discharge — the flow at which scour depth
equals pipe burial depth — is produced by Layer 3 (HEC-RAS + Lacey's
regime + Breusers/Raudkivi scour). PROXY_CRITICAL_DISCHARGE_M3S below
is a placeholder so the Layer 2 alert logic can be built and tested
end-to-end now; replace it once Layer 3 delivers the real number.

Run from the project root:
    python scripts/05_rainfall_discharge.py
"""

import ee
import csv
import os

GEE_PROJECT = "vaulted-journal-500312-m1"
ROI_BOUNDS = [78.087585, 29.628245, 78.133742, 29.668558]

CATCHMENT_CSV = "outputs/catchment_summary.csv"
OUT_DIR = "outputs"
OUT_CSV = os.path.join(OUT_DIR, "rainfall_discharge.csv")

YEARS = list(range(2016, 2025))
MONSOON_START = "06-01"   # 1 June
MONSOON_END = "09-30"     # 30 Sept

# Runoff coefficient — ASSUMPTION pending soil/land-cover survey.
# 0.35 is a typical mixed cultivated/scrub foothill value
# (IRC:SP:42 gives 0.30-0.50 for this class of terrain).
# Update once Layer 3 soil/sediment data is available.
RUNOFF_COEFF = 0.35

# Proxy critical discharge — PLACEHOLDER until Layer 3 delivers the
# scour-based threshold from HEC-RAS + Lacey's regime formula.
PROXY_CRITICAL_DISCHARGE_M3S = 150.0

IMERG_BAND = "precipitation"  # mm/hr (V07 band name; V06 used "precipitationCal")


def load_catchment_area():
    with open(CATCHMENT_CSV) as f:
        for row in csv.DictReader(f):
            if row["metric"] == "catchment_area":
                return float(row["value"])
    raise RuntimeError(
        f"Could not find catchment_area in {CATCHMENT_CSV} — "
        "run 04_catchment_delineation.py first."
    )


def main():
    ee.Authenticate()
    ee.Initialize(project=GEE_PROJECT)

    catchment_area_km2 = load_catchment_area()
    print(f"Using catchment area: {catchment_area_km2:.2f} km²  (C={RUNOFF_COEFF})")
    print(f"Proxy critical discharge: {PROXY_CRITICAL_DISCHARGE_M3S} m³/s\n")

    roi = ee.Geometry.Rectangle(ROI_BOUNDS)
    os.makedirs(OUT_DIR, exist_ok=True)

    results = []
    for year in YEARS:
        date_start = f"{year}-{MONSOON_START}"
        date_end = f"{year}-{MONSOON_END}"

        imerg = (
            ee.ImageCollection("NASA/GPM_L3/IMERG_V07")
            .filterBounds(roi)
            .filterDate(date_start, date_end)
            .select(IMERG_BAND)
        )

        count = imerg.size().getInfo()
        if count == 0:
            print(f"  {year}  no IMERG scenes found — skipped")
            results.append({"year": year, "peak_intensity_mmhr": None,
                             "peak_discharge_m3s": None, "exceeds_threshold": None})
            continue

        # Peak half-hourly rainfall rate anywhere over the ROI in the
        # whole monsoon window — used as the design storm intensity.
        # IMERG pixels are ~11 km across; the crossing ROI itself is
        # only ~5 km, so we buffer it to guarantee we always land
        # inside at least one full pixel instead of on a pixel edge.
        sample_area = roi.buffer(15000)
        max_img = imerg.max()
        stat = max_img.reduceRegion(
            reducer=ee.Reducer.max(),
            geometry=sample_area,
            scale=11132,          # native IMERG pixel size (0.1 deg at equator)
            bestEffort=True,
            maxPixels=1e9,
        ).getInfo()
        peak_intensity = stat.get(IMERG_BAND)

        if peak_intensity is None:
            print(f"  {year}  WARNING: reduceRegion returned no data — skipped")
            results.append({"year": year, "peak_intensity_mmhr": None,
                             "peak_discharge_m3s": None, "exceeds_threshold": None})
            continue

        discharge = (RUNOFF_COEFF * peak_intensity * catchment_area_km2) / 360.0
        exceeds = discharge >= PROXY_CRITICAL_DISCHARGE_M3S

        flag = "  >>> EXCEEDS PROXY THRESHOLD" if exceeds else ""
        print(f"  {year}  peak intensity {peak_intensity:6.2f} mm/hr  →  "
              f"Q = {discharge:7.2f} m³/s{flag}")

        results.append({
            "year": year,
            "peak_intensity_mmhr": round(peak_intensity, 2),
            "peak_discharge_m3s": round(discharge, 2),
            "exceeds_threshold": exceeds,
        })

    fields = ["year", "peak_intensity_mmhr", "peak_discharge_m3s", "exceeds_threshold"]
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nSaved: {OUT_CSV}")
    print("Next: run scripts/06_flood_alert_plot.py")


if __name__ == "__main__":
    main()