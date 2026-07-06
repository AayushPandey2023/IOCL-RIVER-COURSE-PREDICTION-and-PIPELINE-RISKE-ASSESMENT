"""
11_alert_dashboard.py  —  KRNPL Pipeline Risk Alert System
===========================================================
INTERACTIVE ALERT TOOL — ties all 5 layers together.

The user inputs site coordinates and pipeline parameters.
The system queries all available data and outputs a full
colour-coded risk assessment on screen.

Can be run in two modes:
  1. INTERACTIVE — prompts user for inputs
  2. QUICK CHECK — pass coordinates as command-line arguments

Usage:
  python scripts/11_alert_dashboard.py
  python scripts/11_alert_dashboard.py --lon 78.11 --lat 29.65 --span 0 --discharge 0

Run from project root.
"""

import os
import csv
import math
import sys
import argparse
import datetime

OUT_DIR = "outputs"

# ── ANSI colour codes for terminal output ─────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    ORANGE = "\033[38;5;208m"
    YELLOW = "\033[93m"
    GREEN  = "\033[92m"
    BLUE   = "\033[94m"
    NAVY   = "\033[38;5;17m"
    WHITE  = "\033[97m"
    GREY   = "\033[90m"
    BG_RED = "\033[41m"
    BG_YEL = "\033[43m"
    BG_GRN = "\033[42m"
    BG_BLU = "\033[44m"

# ── Load thresholds from Layer 3 output ──────────────────────────────────────
def load_layer3_thresholds():
    path = os.path.join(OUT_DIR, "layer3_critical_Q.txt")
    thresholds = {"WARNING_Q_M3S": 50, "ALERT_Q_M3S": 80, "CRITICAL_Q_M3S": 120}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                for key in thresholds:
                    if key in line and "=" in line:
                        try:
                            thresholds[key] = float(line.split("=")[1].strip().split()[0])
                        except:
                            pass
    return thresholds

# ── Load Layer 5 span thresholds ─────────────────────────────────────────────
def load_layer5_thresholds():
    path = os.path.join(OUT_DIR, "layer5_structural.txt")
    thresholds = {
        "FREESPAN_ALLOW_M": 25.0,
        "WARNING_SPAN_M":   12.5,
        "ALERT_SPAN_M":     18.8,
        "CRITICAL_SPAN_M":  22.5,
    }
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                for key in thresholds:
                    if key in line and "=" in line:
                        try:
                            thresholds[key] = float(line.split("=")[1].strip())
                        except:
                            pass
    return thresholds

# ── Load Layer 1 NDWI trend ───────────────────────────────────────────────────
def load_layer1_trend():
    path = os.path.join(OUT_DIR, "ndwi_timeseries.csv")
    if not os.path.exists(path):
        return None, None, None
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("water_pct") and row["water_pct"] != "None":
                rows.append({
                    "year": int(row["year"]),
                    "water_pct": float(row["water_pct"])
                })
    if len(rows) < 2:
        return None, None, None
    years = [r["year"] for r in rows]
    wpct  = [r["water_pct"] for r in rows]
    n  = len(years)
    xm = sum(years) / n
    ym = sum(wpct)  / n
    ss_xy = sum((x-xm)*(y-ym) for x,y in zip(years,wpct))
    ss_xx = sum((x-xm)**2 for x in years)
    slope = ss_xy / ss_xx if ss_xx else 0
    latest_pct = wpct[-1]
    latest_yr  = years[-1]
    return slope, latest_pct, latest_yr

# ── Load Layer 2 historical discharge ────────────────────────────────────────
def load_layer2_discharge():
    path = os.path.join(OUT_DIR, "rainfall_discharge.csv")
    if not os.path.exists(path):
        return None, None
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("peak_discharge_m3s") and row["peak_discharge_m3s"] != "None":
                rows.append({
                    "year": int(row["year"]),
                    "discharge": float(row["peak_discharge_m3s"])
                })
    if not rows:
        return None, None
    latest = rows[-1]
    peak   = max(rows, key=lambda r: r["discharge"])
    return latest["discharge"], peak["discharge"]

# ── Load Layer 4 SAR change ───────────────────────────────────────────────────
def load_layer4_sar():
    path = os.path.join(OUT_DIR, "sar_timeseries.csv")
    if not os.path.exists(path):
        return None, None
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("change_flag") and row["change_flag"] != "NO_DATA":
                rows.append(row)
    if not rows:
        return None, None
    latest = rows[-1]
    n_changed = sum(1 for r in rows if r["change_flag"] == "CHANGE_DETECTED")
    return latest["change_flag"], n_changed

# ── Scour model (from Layer 3 physics) ───────────────────────────────────────
def compute_scour(Q_m3s, channel_width=100, d50_mm=0.3, burial_depth=1.5):
    if Q_m3s <= 0:
        return 0, 0, burial_depth
    f = 1.76 * math.sqrt(d50_mm)
    q_unit   = Q_m3s / channel_width
    d_normal = 1.34 * ((q_unit**2) / f) ** (1/3)
    d_design = 1.27 * d_normal
    cover    = burial_depth - d_design
    return d_normal, d_design, cover

# ── Risk level helper ─────────────────────────────────────────────────────────
def risk_level(value, warn, alert, crit, higher_is_worse=True):
    if higher_is_worse:
        if value >= crit:   return "CRITICAL", C.RED
        elif value >= alert: return "ALERT",   C.ORANGE
        elif value >= warn:  return "WARNING",  C.YELLOW
        else:               return "NORMAL",   C.GREEN
    else:
        if value <= crit:   return "CRITICAL", C.RED
        elif value <= alert: return "ALERT",   C.ORANGE
        elif value <= warn:  return "WARNING",  C.YELLOW
        else:               return "NORMAL",   C.GREEN

# ── Print helpers ─────────────────────────────────────────────────────────────
def banner(text, color=C.NAVY):
    w = 62
    print(f"\n{color}{C.BOLD}{'═'*w}{C.RESET}")
    print(f"{color}{C.BOLD}  {text}{C.RESET}")
    print(f"{color}{C.BOLD}{'═'*w}{C.RESET}")

def section(text):
    print(f"\n{C.BLUE}{C.BOLD}  ▶  {text}{C.RESET}")
    print(f"  {'─'*55}")

def row_print(label, value, unit="", level=None, color=None):
    col = color or (level[1] if level else C.WHITE)
    lv  = f"  [{level[0]}]" if level else ""
    print(f"  {C.GREY}{label:<32}{C.RESET}{col}{C.BOLD}{value} {unit}{lv}{C.RESET}")

def alert_box(level, message, action):
    colors = {
        "CRITICAL": (C.BG_RED,  C.RED,    "🔴"),
        "ALERT":    (C.BG_YEL,  C.ORANGE, "🟠"),
        "WARNING":  (C.BG_YEL,  C.YELLOW, "🟡"),
        "NORMAL":   (C.BG_GRN,  C.GREEN,  "🟢"),
    }
    bg, fg, emoji = colors.get(level, (C.BG_GRN, C.GREEN, "🟢"))
    w = 60
    print(f"\n  {fg}{C.BOLD}{'─'*w}{C.RESET}")
    print(f"  {fg}{C.BOLD}{emoji}  STATUS: {level}{C.RESET}")
    print(f"  {fg}{message}{C.RESET}")
    print(f"  {fg}{C.BOLD}ACTION: {action}{C.RESET}")
    print(f"  {fg}{C.BOLD}{'─'*w}{C.RESET}")

# ─────────────────────────────────────────────────────────────────────────────
def get_inputs(args):
    """Get user inputs either from args or interactive prompts."""

    print(f"\n{C.BLUE}{C.BOLD}")
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║     KRNPL PIPELINE RISK ALERT SYSTEM                ║")
    print("  ║     Indian Oil Corporation Limited                   ║")
    print("  ║     Developed for Najibabad Crossing Assessment      ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print(f"{C.RESET}")

    if args.lon and args.lat:
        lon          = float(args.lon)
        lat          = float(args.lat)
        span_m       = float(args.span)
        discharge    = float(args.discharge)
        burial_depth = float(args.burial) if args.burial else 1.5
        channel_w    = float(args.width)  if args.width  else 100.0
    else:
        print(f"  {C.GREY}Enter site details below. Press Enter to use default values.{C.RESET}\n")

        def ask(prompt, default):
            val = input(f"  {C.BOLD}{prompt}{C.RESET} [{default}]: ").strip()
            return float(val) if val else default

        lon          = ask("Pipeline crossing longitude (°E)",   78.1106)
        lat          = ask("Pipeline crossing latitude  (°N)",   29.6484)
        span_m       = ask("Current observed exposed span (m)  [0 if unknown]", 0.0)
        discharge    = ask("Current / forecast discharge Q (m³/s) [0 if unknown]", 0.0)
        burial_depth = ask("Pipe burial depth at crossing (m)",  1.5)
        channel_w    = ask("Channel width at crossing (m)",      100.0)

    return lon, lat, span_m, discharge, burial_depth, channel_w


def main():
    parser = argparse.ArgumentParser(description="KRNPL Pipeline Risk Alert System")
    parser.add_argument("--lon",      type=float, help="Crossing longitude")
    parser.add_argument("--lat",      type=float, help="Crossing latitude")
    parser.add_argument("--span",     type=float, default=0, help="Observed exposed span (m)")
    parser.add_argument("--discharge",type=float, default=0, help="Current discharge Q (m³/s)")
    parser.add_argument("--burial",   type=float, default=1.5, help="Burial depth (m)")
    parser.add_argument("--width",    type=float, default=100.0, help="Channel width (m)")
    args = parser.parse_args()

    # ── Get inputs ────────────────────────────────────────────────────────────
    lon, lat, span_m, discharge, burial_depth, channel_w = get_inputs(args)

    # ── Load all layer thresholds ─────────────────────────────────────────────
    L3 = load_layer3_thresholds()
    L5 = load_layer5_thresholds()

    warn_Q  = L3["WARNING_Q_M3S"]
    alert_Q = L3["ALERT_Q_M3S"]
    crit_Q  = L3["CRITICAL_Q_M3S"]

    warn_span  = L5["WARNING_SPAN_M"]
    alert_span = L5["ALERT_SPAN_M"]
    crit_span  = L5["CRITICAL_SPAN_M"]

    # ── Load historical layer data ────────────────────────────────────────────
    l1_slope, l1_latest_pct, l1_yr = load_layer1_trend()
    l2_latest_Q, l2_peak_Q         = load_layer2_discharge()
    l4_latest_flag, l4_n_changed   = load_layer4_sar()

    # ── Compute scour ─────────────────────────────────────────────────────────
    d_normal, d_design, cover_left = compute_scour(
        discharge, channel_w, d50_mm=0.3, burial_depth=burial_depth
    )

    # ── Assess each layer ─────────────────────────────────────────────────────
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    banner(f"PIPELINE RISK ASSESSMENT  —  {timestamp}")

    # Site info
    section("SITE INFORMATION")
    row_print("Longitude",            f"{lon:.5f}", "°E")
    row_print("Latitude",             f"{lat:.5f}", "°N")
    row_print("Pipe burial depth",    f"{burial_depth:.1f}", "m")
    row_print("Channel width",        f"{channel_w:.0f}", "m")
    row_print("Observed exposed span",f"{span_m:.1f}", "m")
    row_print("Input discharge",      f"{discharge:.1f}", "m³/s")

    # ── LAYER 1 ───────────────────────────────────────────────────────────────
    section("LAYER 1 — Channel Migration (Satellite NDWI)")
    if l1_slope is not None:
        l1_lv = risk_level(l1_slope, 0.5, 2.0, 3.0)
        row_print("Water coverage trend", f"{l1_slope:+.2f}", "%/year", l1_lv)
        row_print("Latest water coverage",f"{l1_latest_pct:.1f}", f"% (year {l1_yr})")
        if l1_slope > 2.0:
            alert_box("CRITICAL",
                "Channel expanding rapidly toward pipeline alignment.",
                "Prioritise drone survey and scour depth measurement.")
        elif l1_slope > 0.5:
            alert_box("WARNING",
                "Channel slowly expanding near pipeline.",
                "Monitor monthly during monsoon season.")
        else:
            alert_box("NORMAL",
                "Channel position stable in historical record.",
                "Continue routine quarterly monitoring.")
    else:
        print(f"  {C.GREY}  No NDWI data found — run 02_ndwi_timeseries.py first.{C.RESET}")

    # ── LAYER 2 ───────────────────────────────────────────────────────────────
    section("LAYER 2 — Flood Threshold (Rainfall → Discharge)")
    q_to_check = discharge if discharge > 0 else (l2_latest_Q or 0)
    l2_lv = risk_level(q_to_check, warn_Q, alert_Q, crit_Q)
    row_print("Discharge being assessed",  f"{q_to_check:.1f}", "m³/s")
    row_print("WARNING  threshold",        f"{warn_Q:.0f}",     "m³/s")
    row_print("ALERT    threshold",        f"{alert_Q:.0f}",    "m³/s")
    row_print("CRITICAL threshold",        f"{crit_Q:.0f}",     "m³/s")
    row_print("Layer 2 assessment",        l2_lv[0], "", l2_lv)
    if l2_latest_Q:
        row_print("Historical peak discharge", f"{l2_peak_Q:.1f}", "m³/s")

    if l2_lv[0] == "CRITICAL":
        alert_box("CRITICAL",
            f"Discharge {q_to_check:.0f} m³/s exceeds critical threshold {crit_Q:.0f} m³/s.",
            "SHUT Mundakhera RCP + Najibabad valves. Deploy emergency team.")
    elif l2_lv[0] == "ALERT":
        alert_box("ALERT",
            f"Discharge {q_to_check:.0f} m³/s near critical threshold.",
            "Deploy drone to Ch.141-146 km. Pre-position emergency response.")
    elif l2_lv[0] == "WARNING":
        alert_box("WARNING",
            f"Discharge {q_to_check:.0f} m³/s at warning level.",
            "Increase monitoring frequency. Review 48-hr IMD rainfall forecast.")
    else:
        alert_box("NORMAL",
            f"Discharge {q_to_check:.0f} m³/s within safe limits.",
            "No action required.")

    # ── LAYER 3 ───────────────────────────────────────────────────────────────
    section("LAYER 3 — Scour Depth Model (Lacey IRC:5)")
    row_print("Lacey normal scour",   f"{d_normal:.3f}", "m")
    row_print("Lacey design scour",   f"{d_design:.3f}", "m  (IRC:5 = 1.27 × normal)")
    row_print("Pipe burial depth",    f"{burial_depth:.2f}", "m")
    cover_color = C.GREEN if cover_left > burial_depth * 0.5 else \
                  C.YELLOW if cover_left > 0 else C.RED
    row_print("Cover remaining",      f"{cover_left:.3f}", "m", color=cover_color)

    if cover_left <= 0:
        alert_box("CRITICAL",
            f"Scour has reached pipe level. Cover remaining: {cover_left:.2f}m.",
            "EMERGENCY: Shut isolation valves. Pipe exposure imminent.")
    elif cover_left < burial_depth * 0.2:
        alert_box("ALERT",
            f"Only {cover_left:.2f}m cover remaining above pipe top.",
            "Deploy inspection team immediately to Ch.141-146 km.")
    elif cover_left < burial_depth * 0.5:
        alert_box("WARNING",
            f"{cover_left:.2f}m cover remaining (< 50% of burial depth).",
            "Increase scour monitoring frequency.")
    else:
        alert_box("NORMAL",
            f"{cover_left:.2f}m cover remaining — pipe buried adequately.",
            "Continue routine monitoring.")

    # ── LAYER 4 ───────────────────────────────────────────────────────────────
    section("LAYER 4 — SAR Ground Change Detection")
    if l4_latest_flag is not None:
        l4_color = C.RED if l4_latest_flag == "CHANGE_DETECTED" else C.GREEN
        row_print("Latest season SAR status", l4_latest_flag, "", color=l4_color)
        row_print("Years with change detected", f"{l4_n_changed}", "of 8 years")
        if l4_latest_flag == "CHANGE_DETECTED":
            alert_box("ALERT",
                "SAR confirms physical ground change at pipeline corridor last season.",
                "Open sar_change_YYYY.png to locate affected zone. Inspect alignment.")
        else:
            alert_box("NORMAL",
                "No significant SAR ground change detected in latest season.",
                "Continue monitoring.")
    else:
        print(f"  {C.GREY}  No SAR data — run 09_sar_change_detection.py first.{C.RESET}")

    # ── LAYER 5 ───────────────────────────────────────────────────────────────
    section("LAYER 5 — Structural Free Span Assessment (DNV-RP-F105)")
    row_print("Observed exposed span",    f"{span_m:.1f}", "m")
    row_print("Max allowable span",       f"{L5['FREESPAN_ALLOW_M']:.1f}", "m")
    row_print("WARNING  threshold",       f"{warn_span:.1f}", "m")
    row_print("ALERT    threshold",       f"{alert_span:.1f}", "m")
    row_print("CRITICAL threshold",       f"{crit_span:.1f}", "m")

    l5_lv = risk_level(span_m, warn_span, alert_span, crit_span)
    row_print("Structural assessment",    l5_lv[0], "", l5_lv)

    if span_m > 0:
        stress_ratio = (span_m / L5["FREESPAN_ALLOW_M"]) ** 2
        row_print("Estimated stress ratio",f"{min(stress_ratio, 9.99):.2f}",
                  "× allowable")

    if l5_lv[0] == "CRITICAL":
        alert_box("CRITICAL",
            f"Span {span_m:.0f}m exceeds 90% of allowable {L5['FREESPAN_ALLOW_M']:.0f}m. IMMINENT FAILURE.",
            "SHUT VALVES. Emergency excavation and support. Contact IOCL Emergency Response.")
    elif l5_lv[0] == "ALERT":
        alert_box("ALERT",
            f"Span {span_m:.0f}m at 75-90% of allowable. VIV fatigue developing.",
            "Deploy emergency team. Prepare for valve shutdown. Engineer inspection.")
    elif l5_lv[0] == "WARNING":
        alert_box("WARNING",
            f"Span {span_m:.0f}m at 50-75% of allowable. Structural margin reducing.",
            "Increase patrol. Prepare valve isolation plan.")
    else:
        if span_m == 0:
            alert_box("NORMAL", "No exposed span reported.", "Continue routine monitoring.")
        else:
            alert_box("NORMAL",
                f"Span {span_m:.0f}m within safe structural limits.",
                "Continue monitoring.")

    # ── OVERALL RISK ──────────────────────────────────────────────────────────
    banner("OVERALL PIPELINE RISK SUMMARY")

    # Compute overall level (worst of all layers)
    levels_order = {"NORMAL": 0, "WARNING": 1, "ALERT": 2, "CRITICAL": 3}
    layer_levels = []
    if l1_slope is not None:
        layer_levels.append(risk_level(l1_slope, 0.5, 2.0, 3.0)[0])
    layer_levels.append(l2_lv[0])
    if cover_left <= 0:           layer_levels.append("CRITICAL")
    elif cover_left < burial_depth * 0.2: layer_levels.append("ALERT")
    elif cover_left < burial_depth * 0.5: layer_levels.append("WARNING")
    else:                         layer_levels.append("NORMAL")
    if l4_latest_flag == "CHANGE_DETECTED": layer_levels.append("ALERT")
    else: layer_levels.append("NORMAL")
    layer_levels.append(l5_lv[0])

    overall = max(layer_levels, key=lambda l: levels_order.get(l, 0))

    layer_names = ["L1 Migration", "L2 Flood", "L3 Scour", "L4 SAR", "L5 Structural"]
    print(f"\n  {'Layer':<20} {'Status'}")
    print(f"  {'─'*35}")
    for name, lv in zip(layer_names, layer_levels):
        col = {
            "CRITICAL": C.RED, "ALERT": C.ORANGE,
            "WARNING": C.YELLOW, "NORMAL": C.GREEN
        }.get(lv, C.WHITE)
        print(f"  {name:<20} {col}{C.BOLD}{lv}{C.RESET}")

    overall_actions = {
        "CRITICAL": (
            "CRITICAL — IMMEDIATE ACTION REQUIRED",
            "1. SHUT isolation valves: Mundakhera RCP (Ch.133.7km) + Najibabad (Ch.167.3km)\n"
            "  2. Call IOCL Emergency Response immediately\n"
            "  3. Deploy field team to Ch.141-146 km\n"
            "  4. Isolate product flow. Prepare spill containment."
        ),
        "ALERT": (
            "ALERT — URGENT ATTENTION REQUIRED",
            "1. Deploy drone survey to Ch.141-146 km within 24 hours\n"
            "  2. Pre-position emergency response team\n"
            "  3. Prepare valve isolation plan\n"
            "  4. Increase monitoring to every 6 hours"
        ),
        "WARNING": (
            "WARNING — ELEVATED RISK",
            "1. Review 48-hour IMD rainfall forecast for the catchment\n"
            "  2. Alert field patrol team for Ch.141-146 km\n"
            "  3. Confirm valve operability at Mundakhera RCP\n"
            "  4. Schedule drone survey within 1 week"
        ),
        "NORMAL": (
            "NORMAL — NO IMMEDIATE ACTION REQUIRED",
            "Continue routine monitoring schedule.\n"
            "  Next scheduled inspection: per IOCL maintenance calendar."
        ),
    }

    title, action = overall_actions[overall]
    print(f"\n  {'═'*58}")
    col = {
        "CRITICAL": C.RED, "ALERT": C.ORANGE,
        "WARNING": C.YELLOW, "NORMAL": C.GREEN
    }.get(overall, C.WHITE)
    print(f"  {col}{C.BOLD}  OVERALL: {title}{C.RESET}")
    print(f"  {'─'*58}")
    print(f"  {col}  {action}{C.RESET}")
    print(f"  {'═'*58}")

    # ── Save text report ──────────────────────────────────────────────────────
    report_path = os.path.join(OUT_DIR, f"alert_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(report_path, "w") as f:
        f.write(f"KRNPL PIPELINE RISK ALERT REPORT\n")
        f.write(f"Generated: {timestamp}\n")
        f.write(f"{'='*55}\n\n")
        f.write(f"INPUTS\n")
        f.write(f"  Longitude        : {lon:.5f} E\n")
        f.write(f"  Latitude         : {lat:.5f} N\n")
        f.write(f"  Burial depth     : {burial_depth:.1f} m\n")
        f.write(f"  Channel width    : {channel_w:.0f} m\n")
        f.write(f"  Exposed span     : {span_m:.1f} m\n")
        f.write(f"  Discharge        : {discharge:.1f} m³/s\n\n")
        f.write(f"LAYER RESULTS\n")
        for name, lv in zip(layer_names, layer_levels):
            f.write(f"  {name:<20} {lv}\n")
        f.write(f"\nOVERALL STATUS: {overall}\n")
        f.write(f"ACTION REQUIRED:\n  {action}\n")

    print(f"\n  {C.GREY}Report saved: {report_path}{C.RESET}\n")


if __name__ == "__main__":
    main()
