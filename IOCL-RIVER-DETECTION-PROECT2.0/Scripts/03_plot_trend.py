"""
03_plot_trend.py  —  KRNPL Layer 1
====================================
Reads the ndwi_timeseries.csv produced by 02_ndwi_timeseries.py
and produces two outputs:
  • outputs/layer1_trend.png    — chart for your report
  • outputs/layer1_summary.txt  — text risk summary for your guide

Run from the project root:
    python scripts/03_plot_trend.py
"""

import csv
import math
import os

# We only use the stdlib + matplotlib — no scipy needed
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

# ── Config ────────────────────────────────────────────────────────────────────
CSV_PATH = "outputs/ndwi_timeseries.csv"
OUT_DIR  = "outputs"

# IOCL colour palette
RED  = "#C0202E"
NAVY = "#1A2A4A"
BLUE = "#2E5A8E"
GOLD = "#F0A500"
LGRY = "#F4F6F9"

# ── Helpers ───────────────────────────────────────────────────────────────────
def linregress(xs, ys):
    """Simple linear regression — returns (slope, intercept, r_squared)."""
    n = len(xs)
    xm = sum(xs) / n
    ym = sum(ys) / n
    ss_xy = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    ss_xx = sum((x - xm) ** 2 for x in xs)
    if ss_xx == 0:
        return 0.0, ym, 0.0
    slope = ss_xy / ss_xx
    intercept = ym - slope * xm
    ss_tot = sum((y - ym) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, intercept, r2

# ── Load CSV ──────────────────────────────────────────────────────────────────
rows = []
with open(CSV_PATH, newline="") as f:
    for row in csv.DictReader(f):
        if row["water_pct"] and row["water_pct"] != "None":
            rows.append({
                "year":      int(row["year"]),
                "water_pct": float(row["water_pct"]),
                "mean_ndwi": float(row["mean_ndwi"]),
                "max_ndwi":  float(row["max_ndwi"]),
            })

if len(rows) < 3:
    print("Not enough data rows to plot trend. Check ndwi_timeseries.csv.")
    exit(1)

years     = [r["year"]      for r in rows]
water_pct = [r["water_pct"] for r in rows]
mean_ndwi = [r["mean_ndwi"] for r in rows]

# ── Regression on water coverage % ───────────────────────────────────────────
slope_w, intercept_w, r2_w = linregress(years, water_pct)
trend_w = [slope_w * y + intercept_w for y in years]

# Project 4 years forward
future_years = [years[-1] + i for i in range(1, 5)]
projected_w  = [slope_w * y + intercept_w for y in future_years]

# Regression on mean NDWI
slope_n, intercept_n, r2_n = linregress(years, mean_ndwi)
trend_n = [slope_n * y + intercept_n for y in years]

# ── Risk scoring ──────────────────────────────────────────────────────────────
# How fast is water coverage growing?
pct_per_yr = slope_w          # % points per year
peak_water  = max(water_pct)
latest_water = water_pct[-1]

# Risk score (0–100)
score = 0

# Factor 1 — expansion trend (0–35)
if pct_per_yr > 2.0:    s1, l1 = 35, "Rapid expansion"
elif pct_per_yr > 0.5:  s1, l1 = 25, "Moderate expansion"
elif pct_per_yr > 0:    s1, l1 = 12, "Slow expansion"
elif pct_per_yr > -0.5: s1, l1 =  5, "Stable"
else:                   s1, l1 =  0, "Contracting"
score += s1

# Factor 2 — current water coverage (0–30)
if latest_water > 20:   s2, l2 = 30, "Very high current coverage"
elif latest_water > 10: s2, l2 = 20, "High current coverage"
elif latest_water > 5:  s2, l2 = 10, "Moderate coverage"
else:                   s2, l2 =  5, "Low coverage"
score += s2

# Factor 3 — trend confidence (0–20)
s3 = int(r2_w * 20)
l3 = f"R²={r2_w:.2f}"
score += s3

# Factor 4 — known incident site (always 15 for Najibabad)
s4, l4 = 15, "Known washout incident site"
score += s4

if score >= 70:   risk_cat, risk_col = "CRITICAL", RED
elif score >= 50: risk_cat, risk_col = "HIGH",     "#E65100"
elif score >= 30: risk_cat, risk_col = "MEDIUM",   GOLD
else:             risk_cat, risk_col = "LOW",      "#2E7D32"

# ── PLOT ──────────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(14, 9), facecolor=LGRY)
fig.suptitle(
    "KRNPL — Layer 1: Channel Migration Analysis\n"
    "Najibabad Incident Zone  |  Ch. ~144.1 km  |  Sentinel-2 Oct–Nov Composites",
    fontsize=13, fontweight="bold", color=NAVY, y=0.98
)

gs = GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.32,
              left=0.08, right=0.96, top=0.91, bottom=0.09)

# ── Panel A: Water coverage % over time ──────────────────────────────────────
ax1 = fig.add_subplot(gs[0, 0])
ax1.set_facecolor("white")
bars = ax1.bar(years, water_pct, color=BLUE, alpha=0.7, zorder=2, label="Water coverage (%)")
ax1.plot(years, trend_w, color=RED, lw=2, ls="--", zorder=3,
         label=f"Trend: {slope_w:+.2f}%/yr  (R²={r2_w:.2f})")
ax1.plot(future_years, projected_w, color=GOLD, lw=1.5, ls=":", zorder=3, label="Projected")

# Highlight bars that are above-average
avg_w = sum(water_pct) / len(water_pct)
ax1.axhline(avg_w, color=NAVY, lw=0.8, ls=":", alpha=0.5, label=f"Average ({avg_w:.1f}%)")

ax1.set_xlabel("Year", color=NAVY, fontsize=9)
ax1.set_ylabel("Water coverage (% of ROI)", color=NAVY, fontsize=9)
ax1.set_title("A.  Water Body Coverage — Oct/Nov Each Year", fontweight="bold",
              color=NAVY, fontsize=10)
ax1.legend(fontsize=7.5)
ax1.set_xlim(2015, future_years[-1] + 0.5)
for sp in ax1.spines.values(): sp.set_edgecolor("#CCCCCC")

# ── Panel B: Mean NDWI trend ──────────────────────────────────────────────────
ax2 = fig.add_subplot(gs[0, 1])
ax2.set_facecolor("white")
ax2.plot(years, mean_ndwi, "o-", color=BLUE, lw=2, ms=6, zorder=3, label="Mean NDWI")
ax2.plot(years, trend_n, "--", color=RED, lw=1.5, zorder=3,
         label=f"Trend: {slope_n:+.4f}/yr")
ax2.fill_between(years, mean_ndwi, 0,
                 where=[v > 0 for v in mean_ndwi],
                 alpha=0.12, color=BLUE, label="NDWI > 0 (water)")
ax2.axhline(0, color="gray", lw=0.8, ls=":")
ax2.set_xlabel("Year", color=NAVY, fontsize=9)
ax2.set_ylabel("Mean NDWI", color=NAVY, fontsize=9)
ax2.set_title("B.  Mean NDWI Intensity Trend", fontweight="bold", color=NAVY, fontsize=10)
ax2.legend(fontsize=7.5)
for sp in ax2.spines.values(): sp.set_edgecolor("#CCCCCC")

# ── Panel C: Year-on-year change (delta) ─────────────────────────────────────
ax3 = fig.add_subplot(gs[1, 0])
ax3.set_facecolor("white")
deltas = [water_pct[i] - water_pct[i-1] for i in range(1, len(water_pct))]
delta_years = years[1:]
colors_d = [RED if d > 0 else "#2E7D32" for d in deltas]
ax3.bar(delta_years, deltas, color=colors_d, alpha=0.8, zorder=2)
ax3.axhline(0, color=NAVY, lw=0.8)
ax3.set_xlabel("Year", color=NAVY, fontsize=9)
ax3.set_ylabel("Change in water coverage (% pts)", color=NAVY, fontsize=9)
ax3.set_title("C.  Year-on-Year Change in Water Coverage", fontweight="bold",
              color=NAVY, fontsize=10)
red_p  = mpatches.Patch(color=RED,       alpha=0.8, label="Expansion (channel growing)")
grn_p  = mpatches.Patch(color="#2E7D32", alpha=0.8, label="Contraction")
ax3.legend(handles=[red_p, grn_p], fontsize=7.5)
for sp in ax3.spines.values(): sp.set_edgecolor("#CCCCCC")

# ── Panel D: Risk summary card ────────────────────────────────────────────────
ax4 = fig.add_subplot(gs[1, 1])
ax4.set_facecolor("white")
ax4.set_xlim(0, 1); ax4.set_ylim(0, 1); ax4.axis("off")

ax4.text(0.5, 0.96, "D.  Risk Assessment", ha="center", fontsize=11,
         fontweight="bold", color=NAVY, va="top")
ax4.text(0.5, 0.88, "Najibabad Crossing  |  Ch. 144.1 km", ha="center",
         fontsize=8.5, color="gray", va="top")

# Score bar background
ax4.add_patch(mpatches.FancyBboxPatch(
    (0.05, 0.72), 0.90, 0.10, boxstyle="round,pad=0.01",
    facecolor="#EEEEEE", edgecolor="#CCCCCC", zorder=2))
# Score bar fill
fill_w = 0.90 * min(score, 100) / 100
ax4.add_patch(mpatches.FancyBboxPatch(
    (0.05, 0.72), fill_w, 0.10, boxstyle="round,pad=0.01",
    facecolor=risk_col, edgecolor="none", alpha=0.85, zorder=3))
ax4.text(0.5, 0.77, f"{score}/100", ha="center", va="center",
         fontsize=12, fontweight="bold", color="white", zorder=4)

ax4.text(0.5, 0.64, risk_cat, ha="center", fontsize=24,
         fontweight="bold", color=risk_col)

# Score breakdown table
factor_rows = [
    (f"{slope_w:+.2f}%/yr", f"Expansion trend  → {s1}/35  [{l1}]"),
    (f"{latest_water:.1f}%",  f"Current water coverage  → {s2}/30  [{l2}]"),
    (f"{r2_w:.2f}",           f"Trend confidence (R²)  → {s3}/20  [{l3}]"),
    ("Yes",                   f"Known incident site  → {s4}/15  [{l4}]"),
]
y_pos = 0.54
for val, label in factor_rows:
    ax4.text(0.07, y_pos, label,  fontsize=7.5, color="#444444", va="center")
    ax4.text(0.93, y_pos, val,    fontsize=8,   color=NAVY, va="center",
             ha="right", fontweight="bold")
    y_pos -= 0.10

ax4.axhline(0.06, xmin=0.05, xmax=0.95, color="#EEEEEE", lw=0.8)
ax4.text(0.5, 0.03,
         "Note: distance measurement pending — verify GeoTIFF in QGIS.",
         ha="center", fontsize=7, color="gray", style="italic")

# Save
os.makedirs(OUT_DIR, exist_ok=True)
plot_path = os.path.join(OUT_DIR, "layer1_trend.png")
plt.savefig(plot_path, dpi=150, bbox_inches="tight", facecolor=LGRY)
plt.close()
print(f"Chart saved: {plot_path}")

# ── Text summary ──────────────────────────────────────────────────────────────
summary = f"""
KRNPL — LAYER 1 RISK SUMMARY
Najibabad Incident Zone  |  Ch. ~144.1 km
{'='*50}

DATA SOURCE
  Sentinel-2 Level-2A  (Google Earth Engine)
  Window : October–November (post-monsoon)
  Years  : {years[0]}–{years[-1]}  ({len(rows)} usable years)

WATER COVERAGE TREND
  Change rate : {slope_w:+.2f} % per year
  Trend R²    : {r2_w:.3f}
  Peak year   : {years[water_pct.index(peak_water)]}  ({peak_water:.1f}% of ROI)
  Latest      : {years[-1]}  ({latest_water:.1f}% of ROI)

RISK SCORE BREAKDOWN
  Expansion trend       {s1:>3}/35   {l1}
  Current coverage      {s2:>3}/30   {l2}
  Trend confidence      {s3:>3}/20   {l3}
  Known incident site   {s4:>3}/15   {l4}
  ─────────────────────────────────
  TOTAL SCORE         {score:>4}/100  →  {risk_cat}

IMMEDIATE NEXT STEPS
  1. Open each ndwi_YYYY.png in sequence and visually confirm
     the channel is moving toward the pipeline alignment.
  2. Measure exact pixel distance from channel edge to pipeline
     in QGIS (load ndwi_2024.png + pipeline_crossing_segment.csv).
  3. Update CURRENT_DISTANCE_M in this script with measured value.
  4. Proceed to Layer 2 — Rainfall & Flood Threshold Modelling.
"""
txt_path = os.path.join(OUT_DIR, "layer1_summary.txt")
with open(txt_path, "w") as f:
    f.write(summary)

print(summary)
print(f"Text summary saved: {txt_path}")
print("\n✓ Layer 1 complete.")