"""
Step 3 — Parse KRNPL.kml and extract the river-crossing segment.
Run from the project root:
    python scripts/01_extract_crossing.py
"""

import re
import math
import csv
import os

KML_PATH = "data/KRNPL.kml"
OUT_FULL = "outputs/pipeline_chainage_full.csv"
OUT_CROSSING = "outputs/pipeline_crossing_segment.csv"

CHAINAGE_MIN = 140_000
CHAINAGE_MAX = 147_000


def haversine(lon1, lat1, lon2, lat2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    with open(KML_PATH, "r") as f:
        content = f.read()

    match = re.search(r"<coordinates>\s*(.*?)\s*</coordinates>", content, re.S)
    if not match:
        raise ValueError("Could not find <coordinates> block in KML — check the file.")

    raw_lines = [l.strip() for l in match.group(1).split("\n") if l.strip()]

    rows = []
    cum = 0.0
    prev = None
    for line in raw_lines:
        lon, lat, elev = map(float, line.split(","))
        if prev is not None:
            cum += haversine(prev[0], prev[1], lon, lat)
        rows.append({"chainage_m": round(cum, 1), "lon": lon, "lat": lat, "elev_m": elev})
        prev = (lon, lat)

    os.makedirs("outputs", exist_ok=True)

    with open(OUT_FULL, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["chainage_m", "lon", "lat", "elev_m"])
        writer.writeheader()
        writer.writerows(rows)

    crossing = [r for r in rows if CHAINAGE_MIN <= r["chainage_m"] <= CHAINAGE_MAX]
    with open(OUT_CROSSING, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["chainage_m", "lon", "lat", "elev_m"])
        writer.writeheader()
        writer.writerows(crossing)

    total_length = rows[-1]["chainage_m"]
    lons = [r["lon"] for r in crossing]
    lats = [r["lat"] for r in crossing]

    print(f"Total pipeline length:      {total_length:,.1f} m  ({total_length/1000:.2f} km)")
    print(f"Total vertices parsed:      {len(rows):,}")
    print(f"Crossing-segment vertices:  {len(crossing):,}")
    print()
    print(f"Crossing ROI bounding box (use this for Earth Engine):")
    print(f"  lon: {min(lons):.6f} to {max(lons):.6f}")
    print(f"  lat: {min(lats):.6f} to {max(lats):.6f}")
    print()
    print(f"Saved: {OUT_FULL}")
    print(f"Saved: {OUT_CROSSING}")


if __name__ == "__main__":
    main()