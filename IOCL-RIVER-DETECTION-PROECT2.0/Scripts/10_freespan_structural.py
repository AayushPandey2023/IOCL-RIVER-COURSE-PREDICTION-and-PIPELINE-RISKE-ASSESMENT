"""
10_freespan_structural.py  —  KRNPL Layer 5
============================================
Computes the maximum allowable free span for the KRNPL pipeline
and determines the structural risk level based on estimated or
measured exposed pipe length.

WHAT IS FREE SPAN?
  When the riverbed scours away beneath the pipeline, the pipe
  hangs unsupported — like a beam. Beyond a critical length,
  the pipe bends under its own weight + internal pressure and
  eventually yields (permanent deformation) or fractures.

METHOD — DNV-RP-F105 simplified (free span analysis):
  The allowable free span is governed by two failure modes:
  (A) STATIC OVERSTRESS — pipe sags under gravity + pressure
  (B) VORTEX-INDUCED VIBRATION (VIV) — flowing water causes
      oscillation that fatigues the pipe wall

  For this project we compute the static case (primary) and
  flag VIV as a secondary check.

  Static allowable span:
    L_allow = (π/4) * sqrt(σ_allow * D * t / (w_eff))   [simplified beam]

  where:
    σ_allow = allowable bending stress = 0.72 * SMYS * DF
    D       = pipe outer diameter (m)
    t       = wall thickness (m)
    w_eff   = effective submerged weight per unit length (N/m)
    DF      = design factor = 0.72 (ASME B31.4 / OISD-STD-214)

Reference:
  DNV-RP-F105 (2021) — Free spanning pipelines
  ASME B31.4 — Pipeline Transportation Systems
  OISD-STD-214 — Oil Industry Safety Directorate

Outputs:
  outputs/layer5_freespan.png        ← structural chart
  outputs/layer5_structural.txt      ← structural risk summary

Run from project root:
    python scripts/10_freespan_structural.py
"""

import csv
import os
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import matplotlib.patches as mpatches

OUT_DIR = "outputs"

# ── Pipe parameters (KRNPL — from krnpl_details.xlsx) ────────────────────────
PIPE_OD_M    = 0.27305     # 273.05 mm OD
PIPE_WT_M    = 0.00556     # 5.56 mm wall thickness
SMYS_PA      = 46000 * 6894.76   # API 5L X46 SMYS: 46,000 psi → Pa
MOP_PA       = 65 * 1e5    # 65 barg → Pa
DESIGN_FACTOR= 0.72        # ASME B31.4 / OISD-214

# ── Contents & coating ────────────────────────────────────────────────────────
PRODUCT_DENSITY_KG_M3 = 750    # Motor spirit (petrol) density
STEEL_DENSITY_KG_M3   = 7850   # Carbon steel
COATING_THICKNESS_M   = 0.003  # 3mm FBE coating (typical IOCL spec)
COATING_DENSITY_KG_M3 = 1300   # Fusion bonded epoxy

# ── River flow parameters ─────────────────────────────────────────────────────
FLOW_VELOCITY_MS  = 2.5    # m/s — typical flood velocity for this river class
WATER_DENSITY     = 1000   # kg/m³

# ── Span exposure scenarios ───────────────────────────────────────────────────
# The Najibabad incident had ~100 m exposed. We model 0–120 m.
SPAN_RANGE_M = list(range(0, 125, 5))

# colours
RED, NAVY, BLUE, GOLD, LGRY = "#C0202E", "#1A2A4A", "#2E5A8E", "#F0A500", "#F4F6F9"
GRN = "#2E7D32"

# ─────────────────────────────────────────────────────────────────────────────
def pipe_weights():
    """Compute weight components per unit length (N/m)."""
    # Steel wall cross-section area
    r_outer = PIPE_OD_M / 2
    r_inner = r_outer - PIPE_WT_M
    A_steel = math.pi * (r_outer**2 - r_inner**2)
    w_steel = A_steel * STEEL_DENSITY_KG_M3 * 9.81   # N/m

    # Product inside pipe
    A_bore  = math.pi * r_inner**2
    w_prod  = A_bore * PRODUCT_DENSITY_KG_M3 * 9.81  # N/m

    # Coating
    r_coat  = r_outer + COATING_THICKNESS_M
    A_coat  = math.pi * (r_coat**2 - r_outer**2)
    w_coat  = A_coat * COATING_DENSITY_KG_M3 * 9.81  # N/m

    # Buoyancy (submerged in water)
    A_disp  = math.pi * r_coat**2
    w_buoy  = A_disp * WATER_DENSITY * 9.81           # N/m (upward)

    w_total_air   = w_steel + w_prod + w_coat
    w_submerged   = w_total_air - w_buoy

    return w_steel, w_prod, w_coat, w_buoy, w_total_air, w_submerged

def allowable_stress():
    """Allowable bending stress (Pa) — ASME B31.4."""
    return DESIGN_FACTOR * SMYS_PA * 0.72   # hoop stress allowable for bending

def static_allowable_span(w_eff_N_m, sigma_allow_Pa):
    """
    Allowable free span from static beam bending.
    Pipe treated as simply supported beam under UDL (uniform distributed load).
    
    Max bending moment: M = w * L² / 8
    Section modulus:    Z = π/32 * (OD⁴ - ID⁴) / OD
    Stress:             σ = M / Z  ≤  σ_allow
    
    Solving for L:      L = sqrt(8 * σ_allow * Z / w)
    """
    OD = PIPE_OD_M
    ID = OD - 2 * PIPE_WT_M
    # Section modulus for hollow circle
    Z = (math.pi / 32) * (OD**4 - ID**4) / OD   # m³
    if w_eff_N_m <= 0:
        w_eff_N_m = 1.0   # avoid division by zero if buoyancy > weight
    L_allow = math.sqrt(8 * sigma_allow_Pa * Z / w_eff_N_m)
    return L_allow, Z

def viv_critical_velocity(L_span_m):
    """
    Vortex-Induced Vibration — critical flow velocity for resonance.
    
    Natural frequency of simply supported span:
      f_n = (π/2L²) * sqrt(EI/m)
    
    VIV onset when Strouhal number St ≈ 0.2:
      U_critical = f_n * D / St
    
    If actual flow velocity > U_critical → VIV risk.
    """
    E  = 207e9          # Young's modulus for steel (Pa)
    OD = PIPE_OD_M
    ID = OD - 2 * PIPE_WT_M
    I  = math.pi / 64 * (OD**4 - ID**4)   # Second moment of area (m⁴)

    # Mass per unit length (steel + product, no buoyancy for VIV in air gap)
    w_steel, w_prod, w_coat, _, _, _ = pipe_weights()
    m = (w_steel + w_prod + w_coat) / 9.81   # kg/m

    if L_span_m <= 0:
        return 999.0

    EI   = E * I
    f_n  = (math.pi / (2 * L_span_m**2)) * math.sqrt(EI / m)   # Hz
    St   = 0.2
    U_cr = f_n * OD / St   # m/s
    return U_cr

def bending_stress_at_span(L_m, w_eff_N_m):
    """Actual bending stress for a given span length (Pa)."""
    OD = PIPE_OD_M
    ID = OD - 2 * PIPE_WT_M
    Z  = (math.pi / 32) * (OD**4 - ID**4) / OD
    M  = w_eff_N_m * L_m**2 / 8
    return M / Z   # Pa

# ─────────────────────────────────────────────────────────────────────────────
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    w_steel, w_prod, w_coat, w_buoy, w_air, w_sub = pipe_weights()
    sigma_allow = allowable_stress()
    L_allow_sub, Z = static_allowable_span(w_sub, sigma_allow)
    L_allow_air, _ = static_allowable_span(w_air, sigma_allow)

    # Use submerged weight (conservative — pipe is in river)
    L_allow = L_allow_sub

    # Thresholds
    L_warning  = L_allow * 0.50
    L_alert    = L_allow * 0.75
    L_critical = L_allow * 0.90

    print("=" * 58)
    print("LAYER 5 — FREE SPAN STRUCTURAL ASSESSMENT")
    print("KRNPL | Najibabad Crossing | Ch. ~144.1 km")
    print("=" * 58)
    print(f"\nPIPE PARAMETERS")
    print(f"  OD / WT          : {PIPE_OD_M*1000:.1f} mm / {PIPE_WT_M*1000:.1f} mm")
    print(f"  Grade            : API 5L X46  (SMYS = {SMYS_PA/1e6:.0f} MPa)")
    print(f"  MOP              : {MOP_PA/1e5:.0f} barg")
    print(f"\nWEIGHT COMPONENTS (N/m)")
    print(f"  Steel pipe       : {w_steel:.1f}")
    print(f"  Product (MS)     : {w_prod:.1f}")
    print(f"  Coating (FBE)    : {w_coat:.1f}")
    print(f"  Buoyancy         : -{w_buoy:.1f}")
    print(f"  Net submerged    : {w_sub:.1f}")
    print(f"\nSTRUCTURAL RESULTS")
    print(f"  Allowable stress : {sigma_allow/1e6:.1f} MPa")
    print(f"  Section modulus Z: {Z*1e6:.2f} cm³")
    print(f"  Max allowable span (submerged): {L_allow:.1f} m")
    print(f"  Max allowable span (in air)   : {L_allow_air:.1f} m")
    print(f"\nSPAN THRESHOLDS")
    print(f"  WARNING  (50% allowable) : > {L_warning:.1f} m")
    print(f"  ALERT    (75% allowable) : > {L_alert:.1f} m")
    print(f"  CRITICAL (90% allowable) : > {L_critical:.1f} m")
    print(f"\nNAJIBABAD INCIDENT CONTEXT")
    print(f"  Reported exposed span    : ~100 m")
    print(f"  This is {100/L_allow*100:.0f}% of allowable span — well into FAILURE zone")

    # ── Build span analysis table ─────────────────────────────────────────────
    rows = []
    for L in SPAN_RANGE_M:
        if L == 0:
            rows.append({
                "span_m": 0, "bending_stress_mpa": 0,
                "stress_ratio": 0, "viv_critical_velocity_ms": 999,
                "viv_risk": False, "status": "SAFE"
            })
            continue
        sigma = bending_stress_at_span(L, w_sub)
        ratio = sigma / sigma_allow
        u_viv = viv_critical_velocity(L)
        viv   = FLOW_VELOCITY_MS > u_viv

        if L >= L_critical:   status = "CRITICAL"
        elif L >= L_alert:    status = "ALERT"
        elif L >= L_warning:  status = "WARNING"
        else:                 status = "SAFE"

        rows.append({
            "span_m":                    L,
            "bending_stress_mpa":        round(sigma/1e6, 2),
            "stress_ratio":              round(ratio, 3),
            "viv_critical_velocity_ms":  round(u_viv, 2),
            "viv_risk":                  viv,
            "status":                    status,
        })

    # Save CSV
    csv_path = os.path.join(OUT_DIR, "freespan_table.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nFree span table saved: {csv_path}")

    # ── Plot ──────────────────────────────────────────────────────────────────
    spans   = [r["span_m"]               for r in rows]
    stress  = [r["bending_stress_mpa"]   for r in rows]
    ratio   = [r["stress_ratio"]         for r in rows]
    u_viv_v = [r["viv_critical_velocity_ms"] for r in rows[1:]]  # skip 0
    spans_v = spans[1:]

    fig = plt.figure(figsize=(15, 9), facecolor=LGRY)
    fig.suptitle(
        "KRNPL — Layer 5: Free Span Structural Assessment\n"
        f"Najibabad Crossing | Ch. ~144.1 km | "
        f"DNV-RP-F105 / ASME B31.4 | API 5L X46 | OD={PIPE_OD_M*1000:.0f}mm",
        fontsize=12, fontweight="bold", color=NAVY, y=0.98
    )
    gs = GridSpec(2, 3, figure=fig, hspace=0.42, wspace=0.35,
                  left=0.07, right=0.97, top=0.91, bottom=0.09)

    # Panel A — Bending stress vs span
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("white")
    stress_colors = []
    for r in rows:
        if r["status"] == "CRITICAL": stress_colors.append(RED)
        elif r["status"] == "ALERT":  stress_colors.append("#E65100")
        elif r["status"] == "WARNING":stress_colors.append(GOLD)
        else:                         stress_colors.append(GRN)
    ax1.plot(spans, stress, color=BLUE, lw=2.5, zorder=3)
    ax1.axhline(sigma_allow/1e6, color=RED,  lw=2, ls="-",
                label=f"Allowable stress ({sigma_allow/1e6:.0f} MPa)")
    ax1.axhline(sigma_allow/1e6*0.75, color="#E65100", lw=1.5, ls="--", label="75% allowable")
    ax1.axhline(sigma_allow/1e6*0.50, color=GOLD, lw=1.5, ls="--", label="50% allowable")
    ax1.axvline(100, color=RED, lw=2, ls=":", label="Najibabad incident (~100m)")
    ax1.fill_between(spans, stress, sigma_allow/1e6,
                     where=[s < sigma_allow/1e6 for s in stress],
                     alpha=0.08, color=GRN)
    ax1.fill_between(spans, stress, sigma_allow/1e6,
                     where=[s >= sigma_allow/1e6 for s in stress],
                     alpha=0.15, color=RED)
    ax1.set_xlabel("Free span length (m)", color=NAVY, fontsize=9)
    ax1.set_ylabel("Bending stress (MPa)", color=NAVY, fontsize=9)
    ax1.set_title("A.  Bending Stress vs Free Span Length",
                  fontweight="bold", color=NAVY, fontsize=9)
    ax1.legend(fontsize=7); ax1.grid(alpha=0.2)
    for sp in ax1.spines.values(): sp.set_edgecolor("#CCCCCC")

    # Panel B — Stress ratio
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor("white")
    ax2.plot(spans, ratio, color=BLUE, lw=2.5)
    ax2.axhline(1.0,  color=RED,      lw=2,   ls="-",  label="Failure (ratio=1.0)")
    ax2.axhline(0.90, color=RED,      lw=1.5, ls="--", label="CRITICAL (90%)")
    ax2.axhline(0.75, color="#E65100",lw=1.5, ls="--", label="ALERT (75%)")
    ax2.axhline(0.50, color=GOLD,     lw=1.5, ls="--", label="WARNING (50%)")
    ax2.axvline(100,  color=RED,      lw=2,   ls=":",  label="Najibabad ~100m")
    ax2.fill_between(spans, ratio, 1.0,
                     where=[r < 1.0 for r in ratio], alpha=0.08, color=GRN)
    ax2.fill_between(spans, ratio, 1.0,
                     where=[r >= 1.0 for r in ratio], alpha=0.15, color=RED)
    ax2.set_xlabel("Free span length (m)", color=NAVY, fontsize=9)
    ax2.set_ylabel("Stress utilisation ratio (σ/σ_allow)", color=NAVY, fontsize=9)
    ax2.set_title("B.  Stress Utilisation Ratio",
                  fontweight="bold", color=NAVY, fontsize=9)
    ax2.legend(fontsize=7); ax2.grid(alpha=0.2)
    for sp in ax2.spines.values(): sp.set_edgecolor("#CCCCCC")

    # Panel C — VIV critical velocity vs span
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.set_facecolor("white")
    ax3.plot(spans_v, u_viv_v, color=BLUE, lw=2.5, label="VIV critical velocity")
    ax3.axhline(FLOW_VELOCITY_MS, color=RED, lw=2, ls="--",
                label=f"Design flow velocity ({FLOW_VELOCITY_MS} m/s)")
    viv_cross = next((spans_v[i] for i, u in enumerate(u_viv_v)
                      if u < FLOW_VELOCITY_MS), None)
    if viv_cross:
        ax3.axvline(viv_cross, color=RED, lw=1.5, ls=":",
                    label=f"VIV onset at {viv_cross:.0f}m")
    ax3.fill_between(spans_v, u_viv_v, FLOW_VELOCITY_MS,
                     where=[u > FLOW_VELOCITY_MS for u in u_viv_v],
                     alpha=0.08, color=GRN, label="VIV safe zone")
    ax3.fill_between(spans_v, u_viv_v, FLOW_VELOCITY_MS,
                     where=[u <= FLOW_VELOCITY_MS for u in u_viv_v],
                     alpha=0.15, color=RED, label="VIV risk zone")
    ax3.set_xlabel("Free span length (m)", color=NAVY, fontsize=9)
    ax3.set_ylabel("Critical flow velocity (m/s)", color=NAVY, fontsize=9)
    ax3.set_title("C.  Vortex-Induced Vibration Risk\n(St=0.2, DNV-RP-F105)",
                  fontweight="bold", color=NAVY, fontsize=9)
    ax3.legend(fontsize=7); ax3.grid(alpha=0.2)
    for sp in ax3.spines.values(): sp.set_edgecolor("#CCCCCC")

    # Panel D — Weight breakdown bar
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.set_facecolor("white")
    labels  = ["Steel\npipe", "Product\n(MS)", "Coating\n(FBE)", "Buoyancy\n(upward)", "Net\nsubmerged"]
    weights = [w_steel, w_prod, w_coat, -w_buoy, w_sub]
    bcolors = [NAVY, BLUE, GOLD, "#2E7D32", RED]
    bars = ax4.bar(labels, weights, color=bcolors, alpha=0.85)
    for bar, val in zip(bars, weights):
        ax4.text(bar.get_x() + bar.get_width()/2,
                 bar.get_height() + (2 if val >= 0 else -12),
                 f"{val:.0f}", ha="center", fontsize=8, fontweight="bold", color=NAVY)
    ax4.axhline(0, color=NAVY, lw=0.8)
    ax4.set_ylabel("Weight per unit length (N/m)", color=NAVY, fontsize=9)
    ax4.set_title("D.  Pipe Weight Components\n(Submerged condition)",
                  fontweight="bold", color=NAVY, fontsize=9)
    ax4.grid(alpha=0.2, axis="y")
    for sp in ax4.spines.values(): sp.set_edgecolor("#CCCCCC")

    # Panel E — Summary card
    ax5 = fig.add_subplot(gs[1, 1:])
    ax5.set_facecolor("white")
    ax5.set_xlim(0, 1); ax5.set_ylim(0, 1); ax5.axis("off")

    ax5.text(0.5, 0.97, "E.  Layer 5 Structural Threshold Summary",
             ha="center", fontsize=11, fontweight="bold", color=NAVY, va="top")

    thresh_rows = [
        (GRN,      "SAFE",     f"< {L_warning:.0f} m",
         "Stress < 50% allowable. No action.",
         "Continue routine monitoring."),
        (GOLD,     "WARNING",  f"{L_warning:.0f}–{L_alert:.0f} m",
         "Stress 50–75% allowable.",
         "Increase patrol frequency. Review scour model."),
        ("#E65100","ALERT",    f"{L_alert:.0f}–{L_critical:.0f} m",
         "Stress 75–90% allowable. VIV risk developing.",
         "Deploy drone. Pre-position emergency team."),
        (RED,      "CRITICAL", f"> {L_critical:.0f} m",
         "Stress > 90% allowable. Imminent failure risk.",
         "SHUT VALVES IMMEDIATELY. Emergency excavation."),
    ]

    y = 0.80
    for color, level, span_range, desc, action in thresh_rows:
        ax5.add_patch(mpatches.FancyBboxPatch(
            (0.01, y-0.05), 0.13, 0.09, boxstyle="round,pad=0.01",
            facecolor=color, alpha=0.85, edgecolor="none"))
        ax5.text(0.075, y, level, ha="center", va="center",
                 fontsize=8, fontweight="bold", color="white")
        ax5.text(0.17, y+0.02, f"Span {span_range}",
                 ha="left", va="center", fontsize=9.5, fontweight="bold", color=NAVY)
        ax5.text(0.17, y-0.01, desc,
                 ha="left", va="center", fontsize=7.5, color="#555555")
        ax5.text(0.17, y-0.04, f"→ {action}",
                 ha="left", va="center", fontsize=7, color=color, fontstyle="italic")
        ax5.axhline(y-0.07, xmin=0.01, xmax=0.99, color="#EEEEEE", lw=0.7)
        y -= 0.175

    # Najibabad callout
    ax5.add_patch(mpatches.FancyBboxPatch(
        (0.01, 0.04), 0.98, 0.07, boxstyle="round,pad=0.01",
        facecolor="#FDECEA", edgecolor=RED, linewidth=0.8))
    ax5.text(0.5, 0.075,
             f"Najibabad 2021: ~100m exposed = {100/L_allow*100:.0f}% of allowable span "
             f"({L_allow:.1f}m) — well into FAILURE zone. "
             f"System must alert at >{L_warning:.0f}m.",
             ha="center", va="center", fontsize=8, color=RED, fontweight="bold")

    plot_path = os.path.join(OUT_DIR, "layer5_freespan.png")
    plt.savefig(plot_path, dpi=150, bbox_inches="tight", facecolor=LGRY)
    plt.close()
    print(f"Chart saved: {plot_path}")

    # ── Text summary ──────────────────────────────────────────────────────────
    summary = f"""
KRNPL — LAYER 5 STRUCTURAL ASSESSMENT
Najibabad Crossing  |  Ch. ~144.1 km
{'='*52}

PIPE PARAMETERS
  OD / WT       : {PIPE_OD_M*1000:.1f} mm / {PIPE_WT_M*1000:.1f} mm
  Grade         : API 5L X46  (SMYS = {SMYS_PA/1e6:.0f} MPa)
  MOP           : {MOP_PA/1e5:.0f} barg
  Design factor : {DESIGN_FACTOR}  (ASME B31.4 / OISD-STD-214)

STRUCTURAL RESULTS
  Net submerged weight  : {w_sub:.1f} N/m
  Allowable bending σ   : {sigma_allow/1e6:.1f} MPa
  Max allowable span    : {L_allow:.1f} m  (submerged, simply supported)

SPAN THRESHOLDS — USE THESE IN ALERT SYSTEM
  SAFE     : exposed span < {L_warning:.0f} m
  WARNING  : exposed span {L_warning:.0f}–{L_alert:.0f} m
  ALERT    : exposed span {L_alert:.0f}–{L_critical:.0f} m
  CRITICAL : exposed span > {L_critical:.0f} m  → SHUT VALVES

VIV ANALYSIS
  Design flow velocity  : {FLOW_VELOCITY_MS} m/s
  VIV onset span        : {viv_cross if viv_cross else 'beyond model range'} m
  (Vortex-induced vibration risk above this span)

NAJIBABAD INCIDENT VALIDATION
  Reported exposed span : ~100 m
  Allowable span        : {L_allow:.1f} m
  Ratio                 : {100/L_allow:.1f}x allowable → FAILURE confirmed by model

FREESPAN_ALLOW_M = {L_allow:.1f}
WARNING_SPAN_M   = {L_warning:.1f}
ALERT_SPAN_M     = {L_alert:.1f}
CRITICAL_SPAN_M  = {L_critical:.1f}
"""
    txt_path = os.path.join(OUT_DIR, "layer5_structural.txt")
    with open(txt_path, "w") as f:
        f.write(summary)
    print(summary)
    print(f"Summary saved: {txt_path}")
    print("\n✓ Layer 5 complete.")
    print("  Next: python scripts/11_alert_dashboard.py")


if __name__ == "__main__":
    main()
