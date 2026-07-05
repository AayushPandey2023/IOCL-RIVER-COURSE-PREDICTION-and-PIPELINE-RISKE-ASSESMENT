"""
07_scour_model.py  —  KRNPL Layer 3
=====================================
Computes total scour depth at the Najibabad pipeline crossing for
a range of discharge values, using:

  (A) GENERAL SCOUR  — Lacey's Regime Formula (IRC:5 / IS:7784)
      Gives the natural scour depth of the channel bed below HFL
      for a given discharge. This is the standard method used by
      Indian highway and railway bridge designers.

      d_s  = 1.34 * (q² / f)^(1/3)          [Lacey normal scour, m]
      D_s  = 1.27 * d_s                      [IRC:5 design scour, m]

      where:
        q  = discharge per unit width (m²/s) = Q / channel_width
        f  = Lacey's silt factor = 1.76 * sqrt(d50_mm)
        d50 = median bed sediment size (mm)

  (B) LOCAL SCOUR at PIPE  — Breusers et al. (1977) formula
      Once the pipeline is exposed, it acts as a bluff body and
      accelerates scour at its own location.

      d_local = 1.5 * D_pipe * tanh(h/D_pipe)

      where:
        D_pipe = pipe outer diameter (m)
        h      = approach flow depth (m) above the bed

  (C) TOTAL SCOUR = General Scour + Local Scour

  (D) CRITICAL DISCHARGE = Q at which total scour = burial depth
      This replaces the proxy value in Layer 2.

References:
  IRC:5-2015 Clause 703.2 — General scour
  Lacey G. (1930) — Stable channels in alluvium
  Breusers H.N.C., Nicollet G., Shen H.W. (1977) — Local scour
  IS:7784 Part 1 — Code of practice for design of cross drainage works

Outputs:
  outputs/scour_table.csv          ← full Q vs scour table
  outputs/layer3_critical_Q.txt    ← critical discharge to feed back to Layer 2
  outputs/layer3_scour_curve.png   ← chart for report

Run from project root:
    python scripts/07_scour_model.py
"""

import csv
import os
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

# ── Pipe parameters (from krnpl_details.xlsx) ────────────────────────────────
PIPE_OD_M       = 0.27305    # 273.05 mm outer diameter
PIPE_WT_M       = 0.00556    # 5.56 mm wall thickness
PIPE_ID_M       = PIPE_OD_M - 2 * PIPE_WT_M

# ── Burial depth ──────────────────────────────────────────────────────────────
# For open-trench river crossings in India, minimum cover per
# OISD-STD-214 and ASME B31.4 is 1.0 m in navigable rivers,
# 0.9 m in non-navigable. Najibabad is open-trench, non-HDD.
# Using 1.5 m as a conservative field estimate pending ILI data.
# UPDATE THIS VALUE when IOCL provides the ILI depth-of-cover log.
BURIAL_DEPTH_M  = 1.5        # m — TOP of pipe below original riverbed

# ── Channel parameters (from MERIT Hydro via script 04) ──────────────────────
# Replace with actual values from your catchment_summary.csv
CHANNEL_WIDTH_M = 85         # m — from MERIT Hydro wth band (update from CSV)

# ── Sediment parameters ───────────────────────────────────────────────────────
# Najibabad area: Shivalik foothills river — fine to medium sand
# d50 = 0.3 mm is typical for this river class in Uttarakhand
# (Reference: CPCB river sediment survey, Ganga basin tributaries)
# Update when soil/sediment data is provided by IOCL.
D50_MM          = 0.3        # median grain size (mm)
SILT_FACTOR_F   = 1.76 * math.sqrt(D50_MM)   # Lacey's silt factor

# ── Discharge range to model ──────────────────────────────────────────────────
# Layer 2 showed catchment < 100 km² with 5+ exceedance years.
# Model Q from 10 to 800 m³/s to find the real critical threshold.
Q_RANGE = list(range(10, 810, 10))   # m³/s

OUT_DIR = "outputs"

# ── Colours ───────────────────────────────────────────────────────────────────
RED, NAVY, BLUE, GOLD, LGRY = "#C0202E", "#1A2A4A", "#2E5A8E", "#F0A500", "#F4F6F9"
GRN = "#2E7D32"

# ─────────────────────────────────────────────────────────────────────────────
def lacey_scour(Q_m3s, width_m=CHANNEL_WIDTH_M, f=SILT_FACTOR_F):
    """
    Lacey's regime formula — general scour depth.

    Returns:
      d_normal : Lacey normal scour depth (m)
      d_design : IRC:5 design scour depth (m) = 1.27 * d_normal
      q_unit   : discharge per unit width (m²/s)
    """
    q_unit   = Q_m3s / width_m
    d_normal = 1.34 * ((q_unit ** 2) / f) ** (1/3)
    d_design = 1.27 * d_normal
    return d_normal, d_design, q_unit

def flow_depth(Q_m3s, width_m=CHANNEL_WIDTH_M, d_normal_m=None):
    """
    Estimate flow depth using Manning's equation (simplified).
    Assumes wide rectangular channel, Manning's n = 0.035
    (natural river with sand bed — Chow 1959 Table 5-6).
    Used to compute approach depth for Breusers local scour.
    """
    n       = 0.035
    S_slope = 0.002    # approximate bed slope for Shivalik foothill rivers
    # From Manning: Q = (1/n) * A * R^(2/3) * S^(1/2)
    # For wide channel: R ≈ depth h
    # Q/width = (1/n) * h^(5/3) * S^(1/2)
    # h = ((Q/width * n) / S^0.5)^(3/5)
    q_unit  = Q_m3s / width_m
    h       = ((q_unit * n) / (S_slope ** 0.5)) ** (3/5)
    return h

def breusers_local_scour(pipe_od_m, flow_depth_m):
    """
    Breusers et al. (1977) local scour at a circular cylinder (pipe).

    d_local = 1.5 * D * tanh(h / D)

    where:
      D = pipe outer diameter (m)
      h = approach flow depth (m)

    This formula gives the equilibrium scour depth below the pipe
    invert once the pipe is exposed to flow.

    Note: local scour only develops AFTER general scour has exposed
    the pipe. We compute it here to establish the full risk envelope.
    """
    D = pipe_od_m
    h = flow_depth_m
    d_local = 1.5 * D * math.tanh(h / D)
    return d_local

# ─────────────────────────────────────────────────────────────────────────────
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # Try to read channel width from catchment_summary.csv
    csv_path = os.path.join(OUT_DIR, "catchment_summary.csv")
    channel_width = CHANNEL_WIDTH_M
    if os.path.exists(csv_path):
        with open(csv_path) as f:
            for row in csv.DictReader(f):
                if row["metric"] == "channel_width_at_crossing":
                    try:
                        w = float(row["value"])
                        if w and w > 0:
                            channel_width = w
                            print(f"Channel width loaded from catchment_summary.csv: {w} m")
                    except (ValueError, TypeError):
                        pass

    print(f"\nScour model parameters:")
    print(f"  Pipe OD           : {PIPE_OD_M*1000:.1f} mm")
    print(f"  Burial depth      : {BURIAL_DEPTH_M} m  (estimate — update from ILI data)")
    print(f"  Channel width     : {channel_width} m")
    print(f"  d50 (bed sediment): {D50_MM} mm")
    print(f"  Lacey silt factor : {SILT_FACTOR_F:.3f}")
    print(f"  Discharge range   : {Q_RANGE[0]}–{Q_RANGE[-1]} m³/s\n")

    # ── Build scour table ─────────────────────────────────────────────────────
    results = []
    critical_Q = None
    warning_Q  = None
    alert_Q    = None

    for Q in Q_RANGE:
        d_normal, d_design, q_unit = lacey_scour(Q, channel_width, SILT_FACTOR_F)
        h_flow   = flow_depth(Q, channel_width)
        d_local  = breusers_local_scour(PIPE_OD_M, h_flow)
        d_total  = d_design + d_local
        cover    = BURIAL_DEPTH_M - d_design   # cover above top of pipe
        cover_total = BURIAL_DEPTH_M - d_total  # after local scour too

        results.append({
            "discharge_m3s":          Q,
            "q_unit_m2s":             round(q_unit, 3),
            "flow_depth_m":           round(h_flow, 2),
            "lacey_normal_scour_m":   round(d_normal, 3),
            "lacey_design_scour_m":   round(d_design, 3),
            "breusers_local_scour_m": round(d_local, 3),
            "total_scour_m":          round(d_total, 3),
            "cover_above_pipe_m":     round(cover, 3),
            "cover_total_m":          round(cover_total, 3),
        })

        # Find thresholds
        if warning_Q is None and d_design >= BURIAL_DEPTH_M * 0.50:
            warning_Q = Q
        if alert_Q is None and d_design >= BURIAL_DEPTH_M * 0.80:
            alert_Q = Q
        if critical_Q is None and d_design >= BURIAL_DEPTH_M:
            critical_Q = Q

    # ── Print threshold summary ───────────────────────────────────────────────
    print("=" * 58)
    print("LAYER 3 — SCOUR-BASED DISCHARGE THRESHOLDS")
    print("=" * 58)
    print(f"  WARNING  (50% burial consumed) : Q > {warning_Q:>5} m³/s")
    print(f"  ALERT    (80% burial consumed) : Q > {alert_Q:>5} m³/s")
    print(f"  CRITICAL (pipe top exposed)    : Q > {critical_Q:>5} m³/s")
    print(f"\n  ► Replace PROXY_CRITICAL_DISCHARGE_M3S = {critical_Q}")
    print(f"    in scripts/05_rainfall_discharge.py")
    print("=" * 58)

    # ── Save CSV ──────────────────────────────────────────────────────────────
    csv_out = os.path.join(OUT_DIR, "scour_table.csv")
    with open(csv_out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print(f"\nScour table saved: {csv_out}")

    # ── Save critical Q for Layer 2 feedback ─────────────────────────────────
    thresh_text = f"""KRNPL LAYER 3 — CRITICAL DISCHARGE THRESHOLDS
Najibabad Crossing  |  Ch. ~144.1 km
{'='*50}

SCOUR MODEL
  Method (general) : Lacey's Regime Formula (IRC:5 Clause 703.2)
  Method (local)   : Breusers et al. (1977)
  Channel width    : {channel_width} m
  Bed sediment d50 : {D50_MM} mm
  Lacey silt factor: {SILT_FACTOR_F:.3f}
  Pipe OD          : {PIPE_OD_M*1000:.1f} mm
  Burial depth     : {BURIAL_DEPTH_M} m (ESTIMATE — update from ILI data)

THRESHOLDS (scour-based — replace proxy in Layer 2)
  WARNING_Q_M3S  = {warning_Q}    (general scour reaches 50% of burial)
  ALERT_Q_M3S    = {alert_Q}    (general scour reaches 80% of burial)
  CRITICAL_Q_M3S = {critical_Q}   (general scour reaches pipe top)

ACTION
  Update PROXY_CRITICAL_DISCHARGE_M3S in 05_rainfall_discharge.py
  with CRITICAL_Q_M3S = {critical_Q} m³/s

ASSUMPTIONS TO FLAG FOR GUIDE
  1. Burial depth {BURIAL_DEPTH_M} m is estimated — update from ILI depth-of-cover log
  2. Channel width {channel_width} m from MERIT Hydro — measure from NDWI imagery
  3. d50 = {D50_MM} mm assumed (medium-fine sand) — confirm from site sediment sample
  4. Manning's n = 0.035 assumed for sand-bed river
  5. Local scour (Breusers) applies only AFTER pipe is exposed by general scour
"""
    thresh_path = os.path.join(OUT_DIR, "layer3_critical_Q.txt")
    with open(thresh_path, "w") as f:
        f.write(thresh_text)
    print(f"Critical Q file saved: {thresh_path}")

    # ── Plot ──────────────────────────────────────────────────────────────────
    Q_vals        = [r["discharge_m3s"]          for r in results]
    scour_general = [r["lacey_design_scour_m"]   for r in results]
    scour_local   = [r["breusers_local_scour_m"] for r in results]
    scour_total   = [r["total_scour_m"]          for r in results]
    cover_vals    = [r["cover_above_pipe_m"]     for r in results]
    depth_vals    = [r["flow_depth_m"]           for r in results]

    fig = plt.figure(figsize=(15, 9), facecolor=LGRY)
    fig.suptitle(
        "KRNPL — Layer 3: Hydraulic Scour Model\n"
        f"Najibabad Crossing | Ch. ~144.1 km | "
        f"Lacey (IRC:5) + Breusers Local Scour | d50={D50_MM}mm | W={channel_width}m",
        fontsize=12, fontweight="bold", color=NAVY, y=0.98
    )
    gs = GridSpec(2, 3, figure=fig, hspace=0.42, wspace=0.32,
                  left=0.07, right=0.97, top=0.91, bottom=0.09)

    # Panel A — General vs Local scour
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("white")
    ax1.plot(Q_vals, scour_general, color=BLUE, lw=2, label="Lacey general scour (IRC:5)")
    ax1.plot(Q_vals, scour_local,   color=GOLD, lw=1.5, ls="--", label="Breusers local scour")
    ax1.plot(Q_vals, scour_total,   color=RED,  lw=2.5, label="Total scour")
    ax1.axhline(BURIAL_DEPTH_M, color=NAVY, lw=2, ls=":",
                label=f"Burial depth ({BURIAL_DEPTH_M} m)")
    if warning_Q:  ax1.axvline(warning_Q,  color=GOLD,     lw=1.2, ls="--")
    if alert_Q:    ax1.axvline(alert_Q,    color="#E65100", lw=1.2, ls="--")
    if critical_Q: ax1.axvline(critical_Q, color=RED,      lw=1.5, ls="-")
    ax1.set_xlabel("Discharge Q (m³/s)", color=NAVY, fontsize=9)
    ax1.set_ylabel("Scour depth (m)", color=NAVY, fontsize=9)
    ax1.set_title("A.  Scour Depth vs Discharge", fontweight="bold", color=NAVY, fontsize=9)
    ax1.legend(fontsize=7); ax1.grid(alpha=0.2)
    for sp in ax1.spines.values(): sp.set_edgecolor("#CCCCCC")

    # Panel B — Cover remaining above pipe
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor("white")
    ax2.plot(Q_vals, cover_vals, color=BLUE, lw=2)
    ax2.fill_between(Q_vals, cover_vals, 0,
                     where=[c > 0 for c in cover_vals],
                     alpha=0.12, color=GRN, label="Cover intact")
    ax2.fill_between(Q_vals, cover_vals, 0,
                     where=[c <= 0 for c in cover_vals],
                     alpha=0.15, color=RED, label="Pipe exposed")
    ax2.axhline(0, color=RED, lw=2, label="Pipe top (exposure level)")
    ax2.axhline(-PIPE_OD_M, color="#880000", lw=1.5, ls="--",
                label=f"Pipe bottom ({PIPE_OD_M*1000:.0f}mm below)")
    if warning_Q:  ax2.axvline(warning_Q,  color=GOLD,     lw=1.2, ls="--", label=f"WARNING {warning_Q} m³/s")
    if alert_Q:    ax2.axvline(alert_Q,    color="#E65100", lw=1.2, ls="--", label=f"ALERT {alert_Q} m³/s")
    if critical_Q: ax2.axvline(critical_Q, color=RED,      lw=1.5, ls="-",  label=f"CRITICAL {critical_Q} m³/s")
    ax2.set_xlabel("Discharge Q (m³/s)", color=NAVY, fontsize=9)
    ax2.set_ylabel("Cover above pipe top (m)", color=NAVY, fontsize=9)
    ax2.set_title("B.  Remaining Burial Cover vs Discharge", fontweight="bold", color=NAVY, fontsize=9)
    ax2.legend(fontsize=6.5); ax2.grid(alpha=0.2)
    for sp in ax2.spines.values(): sp.set_edgecolor("#CCCCCC")

    # Panel C — Flow depth vs discharge
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.set_facecolor("white")
    ax3.plot(Q_vals, depth_vals, color=BLUE, lw=2)
    ax3.set_xlabel("Discharge Q (m³/s)", color=NAVY, fontsize=9)
    ax3.set_ylabel("Flow depth h (m)", color=NAVY, fontsize=9)
    ax3.set_title("C.  Flow Depth (Manning's Equation)\nn=0.035, S=0.002",
                  fontweight="bold", color=NAVY, fontsize=9)
    ax3.grid(alpha=0.2)
    for sp in ax3.spines.values(): sp.set_edgecolor("#CCCCCC")

    # Panel D — Scour breakdown at critical Q
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.set_facecolor("white")
    if critical_Q:
        crit_row = next(r for r in results if r["discharge_m3s"] == critical_Q)
        components = ["General\nScour\n(Lacey)", "Local\nScour\n(Breusers)", "Total\nScour", "Burial\nDepth"]
        values     = [crit_row["lacey_design_scour_m"],
                      crit_row["breusers_local_scour_m"],
                      crit_row["total_scour_m"],
                      BURIAL_DEPTH_M]
        bar_colors = [BLUE, GOLD, RED, NAVY]
        bars = ax4.bar(components, values, color=bar_colors, alpha=0.85)
        ax4.axhline(BURIAL_DEPTH_M, color=NAVY, lw=1.5, ls=":", alpha=0.6)
        for bar, val in zip(bars, values):
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                     f"{val:.2f}m", ha="center", va="bottom", fontsize=8.5,
                     fontweight="bold", color=NAVY)
        ax4.set_ylabel("Depth (m)", color=NAVY, fontsize=9)
        ax4.set_title(f"D.  Scour Breakdown at Critical Q\n({critical_Q} m³/s)",
                      fontweight="bold", color=NAVY, fontsize=9)
    ax4.grid(alpha=0.2, axis="y")
    for sp in ax4.spines.values(): sp.set_edgecolor("#CCCCCC")

    # Panel E — Threshold summary card
    ax5 = fig.add_subplot(gs[1, 1:])
    ax5.set_facecolor("white")
    ax5.set_xlim(0, 1); ax5.set_ylim(0, 1); ax5.axis("off")

    ax5.text(0.5, 0.95, "E.  Layer 3 Threshold Summary", ha="center",
             fontsize=11, fontweight="bold", color=NAVY, va="top")
    ax5.text(0.5, 0.87, "These values replace the proxy threshold in Layer 2",
             ha="center", fontsize=8.5, color="gray", va="top")

    thresh_rows = [
        (GOLD,      "WARNING",  warning_Q,  "50% of burial cover consumed by general scour",
         "Increase monitoring. Review 48-hr IMD forecast."),
        ("#E65100", "ALERT",    alert_Q,    "80% of burial cover consumed by general scour",
         "Deploy drone to Ch.141-146 km. Alert field team."),
        (RED,       "CRITICAL", critical_Q, "Pipe top reached by Lacey design scour",
         "SHUT VALVES: Mundakhera RCP + Najibabad. Emergency response."),
    ]

    y = 0.74
    for color, level, Q_val, desc, action in thresh_rows:
        # Level badge
        ax5.add_patch(plt.Rectangle((0.02, y-0.045), 0.13, 0.075,
                      facecolor=color, alpha=0.85, transform=ax5.transAxes))
        ax5.text(0.085, y, level, ha="center", va="center",
                 fontsize=8, fontweight="bold", color="white")
        # Q value
        ax5.text(0.20, y+0.01, f"Q > {Q_val} m³/s", ha="left", va="center",
                 fontsize=10, fontweight="bold", color=NAVY)
        # Description
        ax5.text(0.20, y-0.02, desc, ha="left", va="center",
                 fontsize=7.5, color="#555555")
        # Action
        ax5.text(0.20, y-0.043, f"→ {action}", ha="left", va="center",
                 fontsize=7, color=color, fontstyle="italic")
        ax5.axhline(y - 0.065, xmin=0.02, xmax=0.98, color="#EEEEEE", lw=0.8)
        y -= 0.20

    ax5.text(0.5, 0.06,
             f"Assumptions: burial={BURIAL_DEPTH_M}m (est.) | width={channel_width}m | "
             f"d50={D50_MM}mm | Manning n=0.035 | S=0.002",
             ha="center", fontsize=7, color="gray", style="italic")
    ax5.text(0.5, 0.01,
             "Update burial depth from ILI data and channel width from NDWI imagery measurement.",
             ha="center", fontsize=7, color=RED, style="italic")

    plot_path = os.path.join(OUT_DIR, "layer3_scour_curve.png")
    plt.savefig(plot_path, dpi=150, bbox_inches="tight", facecolor=LGRY)
    plt.close()
    print(f"Chart saved: {plot_path}")
    print("\n✓ Layer 3 Step 1 complete.")
    print("  Next: run scripts/08_layer3_feedback.py to update Layer 2 thresholds.")


if __name__ == "__main__":
    main()
