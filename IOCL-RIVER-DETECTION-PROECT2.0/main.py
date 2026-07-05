"""
Step 4 — Pull one year of Sentinel-2 NDWI over the KRNPL river crossing.
"""

import ee
import urllib.request
import os

GEE_PROJECT = "vaulted-journal-500312-m1"

ROI_BOUNDS = [78.087585, 29.628245, 78.133742, 29.668558]

YEAR = 2024
OUT_PNG = f"outputs/ndwi_{YEAR}_test.png"


def mask_clouds(img):
    scl = img.select("SCL")
    mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return img.updateMask(mask)


def compute_ndwi(img):
    ndwi = img.normalizedDifference(["B3", "B8"]).rename("NDWI")
    return img.addBands(ndwi)


def main():
    ee.Authenticate()
    ee.Initialize(project=GEE_PROJECT)

    roi = ee.Geometry.Rectangle(ROI_BOUNDS)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(roi)
        .filterDate(f"{YEAR}-01-01", f"{YEAR}-03-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .map(mask_clouds)
        .map(compute_ndwi)
    )

    count = collection.size().getInfo()
    print(f"Found {count} Sentinel-2 scenes for {YEAR} dry season over the ROI.")
    if count == 0:
        print("No scenes found — widen the date range or check ROI coordinates.")
        return

    composite = collection.select("NDWI").median().clip(roi)

    vis_params = {
        "min": -0.3,
        "max": 0.4,
        "palette": ["8B4513", "D2B48C", "F0E68C", "ADD8E6", "0000FF"],
    }

    url = composite.getThumbURL(
        {**vis_params, "region": roi, "dimensions": 800, "format": "png"}
    )

    os.makedirs("outputs", exist_ok=True)
    urllib.request.urlretrieve(url, OUT_PNG)
    print(f"Saved NDWI thumbnail: {OUT_PNG}")
    print("Open it and check: does the river channel show clearly in blue?")


if __name__ == "__main__":
    main()