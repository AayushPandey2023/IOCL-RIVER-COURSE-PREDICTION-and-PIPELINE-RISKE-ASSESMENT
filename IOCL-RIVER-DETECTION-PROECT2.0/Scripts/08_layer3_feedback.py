"""
08_layer3_feedback.py  —  KRNPL Layer 3
=========================================
Reads the critical discharge from Layer 3 (layer3_critical_Q.txt)
and the historical discharge from Layer 2 (rainfall_discharge.csv),
then:

  1. Re-evaluates which years actually exceeded the REAL threshold
     (not the proxy 150 m³/s used before)
  2. Computes cover remaining for each historical peak discharge year
  3. Produces a combined Layer 2+3 risk chart
  4. Writes the final Layer 3 summary for your report

Run from project root:
    python scripts/08_layer3_feedback.py
"""

import csv
import os
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import matplotlib.patches as mpatches

OUT_DIR          = "outputs"
DISCHARGE_CSV    = os.path.join(OUT_DIR, "rainfall_discharge.csv")
SCOUR_CSV        = os.path.join(OUT_DIR, "scour_table.csv")
CRITICAL_Q_FILE  = os.path.join(OUT_DIR, "layer3_critical_Q.txt")

RED, NAVY, BLUE, GOLD, LGRY = "#C0202E", "#1A2A4A", "#2E5A8E", "#F0A500", "#F4F6F9"
GRN = "#2E7D32"

PIPE_OD_M      = 0.27305
BURIAL_DEPTH_M = 1.5

# ── Load scour table ──────────────────────────────────────────────────────────
def load_scour_table():
    rows = []
    with open(SCOUR_CSV, newline="") as f:
        for row in csv.DictReader(f):
            rows.append({k: float(v) for k, v in row.items()})
    return rows

def scour_at_Q(Q, scour_table):
    """Interpolate scour table to get values at any discharge Q."""
    for i in range(len(scour_table) - 1):
        q0 = scour_table[i]["discharge_m3s"]
        q1 = scour_table[i+1]["discharge_m3s"]
        if q0 <= Q <= q1:
            frac = (Q - q0) / (q1 - q0)
            return {
                k: scour_table[i][k] + frac * (scour_table[i+1][k] - scour_table[i][k])
                for k in scour_table[i]
            }
    # Beyond range — extrapolate last row
    return scour_table[-1]

def load_thresholds():
    """Parse critical Q values from layer3_critical_Q.txt."""
    thresholds = {}
    with open(CRITICAL_Q_FILE) as f:
        for line in f:
            for key in ["WARNING_Q_M3S", "ALERT_Q_M3S", "CRITICAL_Q_M3S"]:
                if key in line:
                    try:
                        thresholds[key] = float(line.split("=")[1].strip().split()[0])
                    except (IndexError, ValueError):
                        pass
    return thresholds

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Load all data
    scour_table = load_scour_table()
    thresholds  = load_thresholds()

    warning_Q  = thresholds.get("WARNING_Q_M3S",  50)
    alert_Q    = thresholds.get("ALERT_Q_M3S",    80)
    critical_Q = thresholds.get("CRITICAL_Q_M3S", 120)

    print("=" * 58)
    print("LAYER 3 FEEDBACK — Applying Real Thresholds to Layer 2")
    print("=" * 58)
    print(f"  WARNING  Q > {warning_Q}  m³/s")
    print(f"  ALERT    Q > {alert_Q}  m³/s")
    print(f"  CRITICAL Q > {critical_Q} m³/s\n")

    # Load Layer 2 historical discharge
    discharge_rows = []
    with open(DISCHARGE_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if row["peak_discharge_m3s"] and row["peak_discharge_m3s"] != "None":
                discharge_rows.append({
                    "year":      int(row["year"]),
                    "intensity": float(row["peak_intensity_mmhr"]),
                    "discharge": float(row["peak_discharge_m3s"]),
                })

    # ── Re-evaluate each year with real scour model ───────────────────────────
    print(f"{'Year':<6} {'Q (m³/s)':<12} {'Gen Scour':<12} {'Cover Left':<12} {'Status'}")
    print("-" * 60)

    enriched = []
    for r in discharge_rows:
        Q    = r["discharge"]
        sc   = scour_at_Q(Q, scour_table)
        cover = BURIAL_DEPTH_M - sc["lacey_design_scour_m"]

        if Q >= critical_Q:   status = "CRITICAL"
        elif Q >= alert_Q:    status = "ALERT"
        elif Q >= warning_Q:  status = "WARNING"
        else:                 status = "NORMAL"

        print(f"{r['year']:<6} {Q:<12.1f} {sc['lacey_design_scour_m']:<12.3f} "
              f"{cover:<12.3f} {status}")

        enriched.append({**r,
            "lacey_scour_m":   sc["lacey_design_scour_m"],
            "total_scour_m":   sc["total_scour_m"],
            "cover_left_m":    cover,
            "status":          status,
        })

    n_critical = sum(1 for r in enriched if r["status"] == "CRITICAL")
    n_alert    = sum(1 for r in enriched if r["status"] == "ALERT")
    n_warning  = sum(1 for r in enriched if r["status"] == "WARNING")
    n_normal   = sum(1 for r in enriched if r["status"] == "NORMAL")

    print(f"\n  NORMAL: {n_normal}  |  WARNING: {n_warning}  |  "
          f"ALERT: {n_alert}  |  CRITICAL: {n_critical}")

    # ── Save enriched CSV ─────────────────────────────────────────────────────
    out_csv = os.path.join(OUT_DIR, "layer3_historical_risk.csv")
    fields  = ["year", "intensity", "discharge", "lacey_scour_m",
               "total_scour_m", "cover_left_m", "status"]
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(enriched)
    print(f"\n  Enriched CSV saved: {out_csv}")

    # ── Plot ──────────────────────────────────────────────────────────────────
    years    = [r["year"]        for r in enriched]
    Q_vals   = [r["discharge"]   for r in enriched]
    scours   = [r["lacey_scour_m"] for r in enriched]
    covers   = [r["cover_left_m"]  for r in enriched]
    statuses = [r["status"]        for r in enriched]

    status_colors = {
        "NORMAL": GRN, "WARNING": GOLD, "ALERT": "#E65100", "CRITICAL": RED
    }
    bar_colors = [status_colors[s] for s in statuses]

    fig = plt.figure(figsize=(14, 9), facecolor=LGRY)
    fig.suptitle(
        "KRNPL — Layer 2+3 Combined: Historical Flood Risk Assessment\n"
        "Najibabad Crossing | Ch. ~144.1 km | Real Scour Thresholds Applied",
        fontsize=12, fontweight="bold", color=NAVY, y=0.98
    )
    gs = GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.32,
                  left=0.08, right=0.96, top=0.91, bottom=0.09)

    # Panel A — Discharge coloured by alert level
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("white")
    ax1.bar(years, Q_vals, color=bar_colors, alpha=0.85, zorder=2)
    ax1.axhline(warning_Q,  color=GOLD,     lw=1.2, ls="--", label=f"WARNING {warning_Q:.0f} m³/s")
    ax1.axhline(alert_Q,    color="#E65100", lw=1.2, ls="--", label=f"ALERT {alert_Q:.0f} m³/s")
    ax1.axhline(critical_Q, color=RED,      lw=2,   ls="-",  label=f"CRITICAL {critical_Q:.0f} m³/s")
    ax1.set_xlabel("Year", color=NAVY, fontsize=9)
    ax1.set_ylabel("Peak Discharge (m³/s)", color=NAVY, fontsize=9)
    ax1.set_title("A.  Historical Peak Discharge\n(Coloured by Alert Level)",
                  fontweight="bold", color=NAVY, fontsize=9)
    ax1.legend(fontsize=7.5); ax1.grid(alpha=0.2, axis="y")
    for sp in ax1.spines.values(): sp.set_edgecolor("#CCCCCC")

    # Panel B — Cover remaining each year
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor("white")
    ax2.bar(years, covers, color=bar_colors, alpha=0.85, zorder=2)
    ax2.axhline(0, color=RED, lw=2, label="Pipe exposure level")
    ax2.axhline(BURIAL_DEPTH_M * 0.5, color=GOLD,     lw=1.2, ls="--", label="50% cover (WARNING)")
    ax2.axhline(BURIAL_DEPTH_M * 0.2, color="#E65100", lw=1.2, ls="--", label="20% cover (ALERT)")
    ax2.set_xlabel("Year", color=NAVY, fontsize=9)
    ax2.set_ylabel("Remaining burial cover (m)", color=NAVY, fontsize=9)
    ax2.set_title("B.  Remaining Cover Above Pipe Top\n(Each Monsoon Season)",
                  fontweight="bold", color=NAVY, fontsize=9)
    ax2.legend(fontsize=7.5); ax2.grid(alpha=0.2, axis="y")
    for sp in ax2.spines.values(): sp.set_edgecolor("#CCCCCC")

    # Panel C — Scour depth each year
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor("white")
    ax3.bar(years, scours, color=bar_colors, alpha=0.85, zorder=2)
    ax3.axhline(BURIAL_DEPTH_M, color=NAVY, lw=2, ls=":",
                label=f"Burial depth ({BURIAL_DEPTH_M} m)")
    ax3.axhline(BURIAL_DEPTH_M * 0.5, color=GOLD, lw=1.2, ls="--")
    ax3.axhline(BURIAL_DEPTH_M * 0.8, color="#E65100", lw=1.2, ls="--")
    ax3.set_xlabel("Year", color=NAVY, fontsize=9)
    ax3.set_ylabel("Lacey design scour depth (m)", color=NAVY, fontsize=9)
    ax3.set_title("C.  Computed Scour Depth Each Monsoon\n(Lacey IRC:5)",
                  fontweight="bold", color=NAVY, fontsize=9)
    ax3.legend(fontsize=7.5); ax3.grid(alpha=0.2, axis="y")
    for sp in ax3.spines.values(): sp.set_edgecolor("#CCCCCC")

    # Panel D — Summary status card
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor("white")
    ax4.set_xlim(0, 1); ax4.set_ylim(0, 1); ax4.axis("off")

    ax4.text(0.5, 0.96, "D.  Combined Layer 2+3 Risk Summary",
             ha="center", fontsize=10, fontweight="bold", color=NAVY, va="top")

    # Year count boxes
    boxes = [
        (GRN,     "NORMAL",   n_normal,   "years within\nnormal range"),
        (GOLD,    "WARNING",  n_warning,  "years at\nWARNING level"),
        ("#E65100","ALERT",   n_alert,    "years at\nALERT level"),
        (RED,     "CRITICAL", n_critical, "years at\nCRITICAL level"),
    ]
    x_pos = [0.06, 0.30, 0.55, 0.76]
    for (col, label, count, desc), x in zip(boxes, x_pos):
        ax4.add_patch(mpatches.FancyBboxPatch(
            (x, 0.62), 0.19, 0.24, boxstyle="round,pad=0.01",
            facecolor=col, alpha=0.85, edgecolor="none"))
        ax4.text(x + 0.095, 0.80, str(count), ha="center", va="center",
                 fontsize=20, fontweight="bold", color="white")
        ax4.text(x + 0.095, 0.67, desc, ha="center", va="center",
                 fontsize=6.5, color="white")
        ax4.text(x + 0.095, 0.59, label, ha="center", va="top",
                 fontsize=7, fontweight="bold",
                 color=col if col != GRN else "#1B5E20")

    # Key finding
    worst = max(enriched, key=lambda r: r["discharge"])
    ax4.text(0.5, 0.50,
             f"Worst year: {worst['year']}  "
             f"(Q={worst['discharge']:.0f} m³/s, scour={worst['lacey_scour_m']:.2f}m, "
             f"cover={worst['cover_left_m']:.2f}m)",
             ha="center", fontsize=8, color=NAVY, fontweight="bold")

    # Threshold table
    trows = [
        ("WARNING",  f"{warning_Q:.0f}",  "Scour > 50% burial"),
        ("ALERT",    f"{alert_Q:.0f}",    "Scour > 80% burial"),
        ("CRITICAL", f"{critical_Q:.0f}", "Scour = burial depth"),
    ]
    y = 0.40
    ax4.text(0.05, y+0.04, "Level", fontsize=8, fontweight="bold", color=NAVY)
    ax4.text(0.38, y+0.04, "Q threshold (m³/s)", fontsize=8, fontweight="bold", color=NAVY)
    ax4.text(0.72, y+0.04, "Meaning", fontsize=8, fontweight="bold", color=NAVY)
    ax4.axhline(y+0.02, xmin=0.04, xmax=0.97, color="#CCCCCC", lw=0.8)
    for level, q_t, meaning in trows:
        col = status_colors[level]
        ax4.text(0.05, y-0.04, level,   fontsize=8, color=col, fontweight="bold")
        ax4.text(0.38, y-0.04, q_t,     fontsize=8, color=NAVY)
        ax4.text(0.72, y-0.04, meaning, fontsize=7.5, color="#555555")
        y -= 0.10

    ax4.text(0.5, 0.02,
             f"Burial depth {BURIAL_DEPTH_M}m assumed — update from ILI depth-of-cover log",
             ha="center", fontsize=7, color=RED, style="italic")

    plot_path = os.path.join(OUT_DIR, "layer3_combined_risk.png")
    plt.savefig(plot_path, dpi=150, bbox_inches="tight", facecolor=LGRY)
    plt.close()
    print(f"  Combined risk chart saved: {plot_path}")

    # ── Text summary ──────────────────────────────────────────────────────────
    summary = f"""
KRNPL — LAYER 3 COMPLETE: SCOUR-BASED RISK ASSESSMENT
Najibabad Crossing  |  Ch. ~144.1 km
{'='*55}

SCOUR MODEL (07_scour_model.py)
  General scour : Lacey's Regime Formula (IRC:5 Clause 703.2)
  Local scour   : Breusers et al. (1977)
  Burial depth  : {BURIAL_DEPTH_M} m  (estimated — update from ILI data)

REAL DISCHARGE THRESHOLDS (replacing Layer 2 proxy of 150 m³/s)
  WARNING  : Q > {warning_Q:.0f} m³/s   (50% burial consumed)
  ALERT    : Q > {alert_Q:.0f} m³/s   (80% burial consumed)
  CRITICAL : Q > {critical_Q:.0f} m³/s  (pipe top exposed)

HISTORICAL RISK CLASSIFICATION (2016–{years[-1]})
  NORMAL   : {n_normal} years
  WARNING  : {n_warning} years
  ALERT    : {n_alert} years
  CRITICAL : {n_critical} years

  Worst event : {worst['year']}
    Q          = {worst['discharge']:.1f} m³/s
    Scour      = {worst['lacey_scour_m']:.3f} m
    Cover left = {worst['cover_left_m']:.3f} m

ACTION REQUIRED FROM IOCL
  1. Provide ILI depth-of-cover log for Ch. 141-146 km
     → This is the single most important input to refine all thresholds
  2. Provide bed sediment d50 from site survey
     → Changes Lacey silt factor and all scour values
  3. Confirm channel width at crossing from recent survey
     → Currently using MERIT Hydro estimate

NEXT STEPS
  → Proceed to Layer 4 (SAR change detection)
  → Update 05_rainfall_discharge.py: PROXY_CRITICAL_DISCHARGE_M3S = {critical_Q:.0f}
"""
    txt_path = os.path.join(OUT_DIR, "layer3_summary.txt")
    with open(txt_path, "w") as f:
        f.write(summary)
    print(summary)
    print(f"  Summary saved: {txt_path}")
    print("\n✓ Layer 3 complete.")


if __name__ == "__main__":
    main()
