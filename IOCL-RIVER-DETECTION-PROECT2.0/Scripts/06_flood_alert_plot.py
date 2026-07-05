"""
06_flood_alert_plot.py  —  KRNPL Layer 2
==========================================
Reads rainfall_discharge.csv (from 05_rainfall_discharge.py) and
catchment_summary.csv (from 04_catchment_delineation.py), and produces:
  • outputs/layer2_trend.png    — chart for your report
  • outputs/layer2_summary.txt  — text risk summary for your guide

Run from the project root:
    python scripts/06_flood_alert_plot.py
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

# ── Config ────────────────────────────────────────────────────────────────────
DISCHARGE_CSV = "outputs/rainfall_discharge.csv"
CATCHMENT_CSV = "outputs/catchment_summary.csv"
OUT_DIR = "outputs"

RED, NAVY, BLUE, GOLD, LGRY = "#C0202E", "#1A2A4A", "#2E5A8E", "#F0A500", "#F4F6F9"

PROXY_CRITICAL_DISCHARGE_M3S = 150.0  # keep in sync with 05_rainfall_discharge.py


def linregress(xs, ys):
    n = len(xs)
    xm, ym = sum(xs) / n, sum(ys) / n
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


# ── Load data ─────────────────────────────────────────────────────────────────
rows = []
with open(DISCHARGE_CSV, newline="") as f:
    for row in csv.DictReader(f):
        if row["peak_discharge_m3s"] and row["peak_discharge_m3s"] != "None":
            rows.append({
                "year": int(row["year"]),
                "intensity": float(row["peak_intensity_mmhr"]),
                "discharge": float(row["peak_discharge_m3s"]),
                "exceeds": row["exceeds_threshold"] == "True",
            })

if len(rows) < 3:
    print("Not enough data rows to plot trend. Check rainfall_discharge.csv.")
    exit(1)

catchment_area_km2 = None
with open(CATCHMENT_CSV) as f:
    for row in csv.DictReader(f):
        if row["metric"] == "catchment_area":
            catchment_area_km2 = float(row["value"])

years = [r["year"] for r in rows]
intensity = [r["intensity"] for r in rows]
discharge = [r["discharge"] for r in rows]

slope_i, intercept_i, r2_i = linregress(years, intensity)
slope_q, intercept_q, r2_q = linregress(years, discharge)
trend_q = [slope_q * y + intercept_q for y in years]

n_exceed = sum(1 for r in rows if r["exceeds"])
latest = rows[-1]
peak_year = years[discharge.index(max(discharge))]

# ── Risk scoring (0-100), mirrors Layer 1 structure ─────────────────────────
score = 0

# Factor 1 — exceedance frequency (0-35)
exceed_frac = n_exceed / len(rows)
if exceed_frac >= 0.4:   s1, l1 = 35, "Frequent exceedance"
elif exceed_frac >= 0.2: s1, l1 = 25, "Occasional exceedance"
elif exceed_frac > 0:    s1, l1 = 12, "Rare exceedance"
else:                    s1, l1 = 0,  "No exceedance on record"
score += s1

# Factor 2 — latest year vs threshold (0-30)
latest_ratio = latest["discharge"] / PROXY_CRITICAL_DISCHARGE_M3S
if latest_ratio >= 1.0:   s2, l2 = 30, "Latest year exceeds threshold"
elif latest_ratio >= 0.75: s2, l2 = 20, "Latest year near threshold (>=75%)"
elif latest_ratio >= 0.5:  s2, l2 = 10, "Latest year moderate (>=50%)"
else:                       s2, l2 = 5,  "Latest year well below threshold"
score += s2

# Factor 3 — discharge trend confidence (0-20)
s3 = int(r2_q * 20)
l3 = f"R²={r2_q:.2f}, trend {slope_q:+.1f} m³/s/yr"
score += s3

# Factor 4 — known incident site (always 15, consistent with Layer 1)
s4, l4 = 15, "Known washout incident site"
score += s4

if score >= 70:   risk_cat, risk_col = "CRITICAL", RED
elif score >= 50: risk_cat, risk_col = "HIGH", "#E65100"
elif score >= 30: risk_cat, risk_col = "MEDIUM", GOLD
else:             risk_cat, risk_col = "LOW", "#2E7D32"

# ── PLOT ──────────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(14, 9), facecolor=LGRY)
fig.suptitle(
    "KRNPL — Layer 2: Rainfall & Flood Threshold Monitoring\n"
    "Najibabad Incident Zone  |  Ch. ~144.1 km  |  GPM IMERG Monsoon Peaks (Rational Method)",
    fontsize=13, fontweight="bold", color=NAVY, y=0.98
)

gs = GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.32,
              left=0.08, right=0.96, top=0.91, bottom=0.09)

# Panel A — peak rainfall intensity per monsoon
ax1 = fig.add_subplot(gs[0, 0])
ax1.set_facecolor("white")
ax1.bar(years, intensity, color=BLUE, alpha=0.7, zorder=2, label="Peak intensity (mm/hr)")
ax1.set_xlabel("Year", color=NAVY, fontsize=9)
ax1.set_ylabel("Peak rainfall intensity (mm/hr)", color=NAVY, fontsize=9)
ax1.set_title("A.  Peak Monsoon Rainfall Intensity (GPM IMERG)", fontweight="bold",
              color=NAVY, fontsize=10)
ax1.legend(fontsize=7.5)
for sp in ax1.spines.values(): sp.set_edgecolor("#CCCCCC")

# Panel B — discharge vs critical threshold
ax2 = fig.add_subplot(gs[0, 1])
ax2.set_facecolor("white")
colors_b = [RED if r["exceeds"] else BLUE for r in rows]
ax2.bar(years, discharge, color=colors_b, alpha=0.8, zorder=2)
ax2.plot(years, trend_q, "--", color=NAVY, lw=1.5, zorder=3,
         label=f"Trend: {slope_q:+.1f} m³/s/yr")
ax2.axhline(PROXY_CRITICAL_DISCHARGE_M3S, color=RED, lw=1.5, ls=":",
            label=f"Proxy critical Q ({PROXY_CRITICAL_DISCHARGE_M3S:.0f} m³/s)")
ax2.set_xlabel("Year", color=NAVY, fontsize=9)
ax2.set_ylabel("Peak discharge (m³/s)", color=NAVY, fontsize=9)
ax2.set_title("B.  Rational-Method Peak Discharge vs Threshold", fontweight="bold",
              color=NAVY, fontsize=10)
ax2.legend(fontsize=7.5)
for sp in ax2.spines.values(): sp.set_edgecolor("#CCCCCC")

# Panel C — exceedance timeline
ax3 = fig.add_subplot(gs[1, 0])
ax3.set_facecolor("white")
ax3.set_xlim(years[0] - 0.5, years[-1] + 0.5)
ax3.set_ylim(0, 1)
for y, r in zip(years, rows):
    c = RED if r["exceeds"] else "#2E7D32"
    ax3.add_patch(mpatches.Circle((y, 0.5), 0.3, color=c, alpha=0.85, zorder=2))
    ax3.text(y, 0.5, "!" if r["exceeds"] else "ok", ha="center", va="center",
              fontsize=7, color="white", fontweight="bold")
ax3.set_yticks([])
ax3.set_xlabel("Year", color=NAVY, fontsize=9)
ax3.set_title(f"C.  Threshold Exceedance Timeline  ({n_exceed}/{len(rows)} years)",
              fontweight="bold", color=NAVY, fontsize=10)
red_p = mpatches.Patch(color=RED, alpha=0.85, label="Exceeded proxy threshold")
grn_p = mpatches.Patch(color="#2E7D32", alpha=0.85, label="Within threshold")
ax3.legend(handles=[red_p, grn_p], fontsize=7.5, loc="upper center")
for sp in ax3.spines.values(): sp.set_edgecolor("#CCCCCC")

# Panel D — risk summary card
ax4 = fig.add_subplot(gs[1, 1])
ax4.set_facecolor("white")
ax4.set_xlim(0, 1); ax4.set_ylim(0, 1); ax4.axis("off")
ax4.text(0.5, 0.96, "D.  Flood Risk Assessment", ha="center", fontsize=11,
         fontweight="bold", color=NAVY, va="top")
ax4.text(0.5, 0.88, "Najibabad Crossing  |  Ch. 144.1 km", ha="center",
         fontsize=8.5, color="gray", va="top")

ax4.add_patch(mpatches.FancyBboxPatch(
    (0.05, 0.72), 0.90, 0.10, boxstyle="round,pad=0.01",
    facecolor="#EEEEEE", edgecolor="#CCCCCC", zorder=2))
fill_w = 0.90 * min(score, 100) / 100
ax4.add_patch(mpatches.FancyBboxPatch(
    (0.05, 0.72), fill_w, 0.10, boxstyle="round,pad=0.01",
    facecolor=risk_col, edgecolor="none", alpha=0.85, zorder=3))
ax4.text(0.5, 0.77, f"{score}/100", ha="center", va="center",
         fontsize=12, fontweight="bold", color="white", zorder=4)
ax4.text(0.5, 0.64, risk_cat, ha="center", fontsize=24, fontweight="bold", color=risk_col)

factor_rows = [
    (f"{n_exceed}/{len(rows)} yrs", f"Exceedance frequency  → {s1}/35  [{l1}]"),
    (f"{latest_ratio*100:.0f}%",    f"Latest yr vs threshold  → {s2}/30  [{l2}]"),
    (f"{r2_q:.2f}",                 f"Trend confidence (R²)  → {s3}/20  [{l3}]"),
    ("Yes",                        f"Known incident site  → {s4}/15  [{l4}]"),
]
y_pos = 0.54
for val, label in factor_rows:
    ax4.text(0.07, y_pos, label, fontsize=7.2, color="#444444", va="center")
    ax4.text(0.93, y_pos, val, fontsize=8, color=NAVY, va="center",
             ha="right", fontweight="bold")
    y_pos -= 0.10

ax4.axhline(0.06, xmin=0.05, xmax=0.95, color="#EEEEEE", lw=0.8)
ax4.text(0.5, 0.03,
         "Note: threshold is a PROXY — replace with Layer 3 scour-based value.",
         ha="center", fontsize=7, color="gray", style="italic")

os.makedirs(OUT_DIR, exist_ok=True)
plot_path = os.path.join(OUT_DIR, "layer2_trend.png")
plt.savefig(plot_path, dpi=150, bbox_inches="tight", facecolor=LGRY)
plt.close()
print(f"Chart saved: {plot_path}")

# ── Text summary ──────────────────────────────────────────────────────────────
summary = f"""
KRNPL — LAYER 2 RISK SUMMARY
Najibabad Incident Zone  |  Ch. ~144.1 km
{'='*50}

DATA SOURCE
  Rainfall  : NASA GPM IMERG V07 (half-hourly, 0.1°)
  Catchment : MERIT Hydro (90 m), area = {catchment_area_km2:.2f} km²
  Window    : June-Sept monsoon, {years[0]}-{years[-1]} ({len(rows)} usable years)
  Method    : Rational Method  Q = C x I x A / 360

ASSUMPTIONS (flag for review with IOCL guide)
  Runoff coefficient C  : 0.35 (typical cultivated/scrub foothill terrain)
  Critical discharge    : {PROXY_CRITICAL_DISCHARGE_M3S:.0f} m³/s — PROXY VALUE,
                           pending Layer 3 HEC-RAS + scour model output

DISCHARGE TREND
  Change rate : {slope_q:+.2f} m³/s per year
  Trend R²    : {r2_q:.3f}
  Peak year   : {peak_year}  ({max(discharge):.1f} m³/s)
  Latest      : {years[-1]}  ({latest['discharge']:.1f} m³/s, {latest_ratio*100:.0f}% of threshold)
  Years exceeding proxy threshold: {n_exceed} / {len(rows)}

RISK SCORE BREAKDOWN
  Exceedance frequency   {s1:>3}/35   {l1}
  Latest yr vs threshold {s2:>3}/30   {l2}
  Trend confidence       {s3:>3}/20   {l3}
  Known incident site    {s4:>3}/15   {l4}
  ─────────────────────────────────
  TOTAL SCORE          {score:>4}/100  →  {risk_cat}

IMMEDIATE NEXT STEPS
  1. Replace PROXY_CRITICAL_DISCHARGE_M3S with the real scour-based
     threshold once Layer 3 (HEC-RAS + Lacey's regime formula) is built.
  2. Cross-check IMERG peak intensities against IMD gridded rainfall
     and, if available, CWC gauge discharge for the same events.
  3. Refine runoff coefficient C using actual soil/land-cover data
     for the catchment (currently an assumed value).
  4. Wire this script's exceedance flag into an alert (email/SMS)
     once thresholds are finalised.
  5. Proceed to Layer 3 — Hydraulic Scour Modelling.
"""
txt_path = os.path.join(OUT_DIR, "layer2_summary.txt")
with open(txt_path, "w", encoding="utf-8") as f:
    f.write(summary)

print(summary)
print(f"Text summary saved: {txt_path}")
print("\n✓ Layer 2 complete.")