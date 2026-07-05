"""
11_alert_dashboard.py  —  KRNPL Pipeline Risk Alert System
===========================================================
Full integrated dashboard — takes user inputs, runs live
computations, and displays all layer charts + results in
one unified GUI window.

Run from project root:
    python scripts/11_alert_dashboard.py
"""

import os, csv, math, datetime, tkinter as tk
from tkinter import simpledialog, messagebox, ttk
from PIL import Image, ImageTk   # pip install Pillow

OUT_DIR = "outputs"

# ── Colour helpers ────────────────────────────────────────────────────────────
def level_color(level):
    return {"CRITICAL":"#C0202E","ALERT":"#E65100",
            "WARNING":"#F0A500","NORMAL":"#2E7D32"}.get(level,"#1A2A4A")
def level_emoji(level):
    return {"CRITICAL":"🔴","ALERT":"🟠",
            "WARNING":"🟡","NORMAL":"🟢"}.get(level,"⚪")
def risk_level(val, warn, alert, crit):
    if val>=crit:    return "CRITICAL"
    elif val>=alert: return "ALERT"
    elif val>=warn:  return "WARNING"
    else:            return "NORMAL"

# ── Data loaders ──────────────────────────────────────────────────────────────
def load_layer3_thresholds():
    path = os.path.join(OUT_DIR,"layer3_critical_Q.txt")
    t = {"WARNING_Q_M3S":50.0,"ALERT_Q_M3S":80.0,"CRITICAL_Q_M3S":120.0}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                for key in t:
                    if key in line and "=" in line:
                        try: t[key]=float(line.split("=")[1].strip().split()[0])
                        except: pass
    return t

def load_layer5_thresholds():
    path = os.path.join(OUT_DIR,"layer5_structural.txt")
    t = {"FREESPAN_ALLOW_M":25.0,"WARNING_SPAN_M":12.5,
         "ALERT_SPAN_M":18.8,"CRITICAL_SPAN_M":22.5}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                for key in t:
                    if key in line and "=" in line:
                        try: t[key]=float(line.split("=")[1].strip())
                        except: pass
    return t

def load_ndwi_series():
    path = os.path.join(OUT_DIR,"ndwi_timeseries.csv")
    rows = []
    if not os.path.exists(path): return rows
    with open(path,newline="") as f:
        for row in csv.DictReader(f):
            if row.get("water_pct") and row["water_pct"]!="None":
                rows.append({"year":int(row["year"]),
                             "water_pct":float(row["water_pct"]),
                             "mean_ndwi":float(row.get("mean_ndwi") or 0)})
    return rows

def load_discharge_series():
    path = os.path.join(OUT_DIR,"rainfall_discharge.csv")
    rows = []
    if not os.path.exists(path): return rows
    with open(path,newline="") as f:
        for row in csv.DictReader(f):
            if row.get("peak_discharge_m3s") and row["peak_discharge_m3s"]!="None":
                rows.append({"year":int(row["year"]),
                             "discharge":float(row["peak_discharge_m3s"]),
                             "intensity":float(row.get("peak_intensity_mmhr") or 0)})
    return rows

def load_scour_table():
    path = os.path.join(OUT_DIR,"scour_table.csv")
    rows = []
    if not os.path.exists(path): return rows
    with open(path,newline="") as f:
        for row in csv.DictReader(f):
            rows.append({k:float(v) for k,v in row.items()})
    return rows

def load_sar_series():
    path = os.path.join(OUT_DIR,"sar_timeseries.csv")
    rows = []
    if not os.path.exists(path): return rows
    with open(path,newline="") as f:
        for row in csv.DictReader(f):
            if row.get("change_flag") and row["change_flag"]!="NO_DATA":
                rows.append(row)
    return rows

def load_freespan_table():
    path = os.path.join(OUT_DIR,"freespan_table.csv")
    rows = []
    if not os.path.exists(path): return rows
    with open(path,newline="") as f:
        for row in csv.DictReader(f):
            rows.append({k:float(v) if k!="status" and k!="viv_risk"
                         else v for k,v in row.items()})
    return rows

# ── Physics ───────────────────────────────────────────────────────────────────
def compute_scour(Q, width=100, d50=0.3, burial=1.5):
    if Q<=0: return 0.0,0.0,burial
    f = 1.76*math.sqrt(d50)
    q_unit = Q/width
    d_n = 1.34*((q_unit**2)/f)**(1/3)
    d_d = 1.27*d_n
    return d_n, d_d, burial-d_d

def linregress(xs, ys):
    n=len(xs); xm=sum(xs)/n; ym=sum(ys)/n
    ss_xy=sum((x-xm)*(y-ym) for x,y in zip(xs,ys))
    ss_xx=sum((x-xm)**2 for x in xs)
    if ss_xx==0: return 0.0,ym,0.0
    slope=ss_xy/ss_xx; intercept=ym-slope*xm
    ss_tot=sum((y-ym)**2 for y in ys)
    ss_res=sum((y-(slope*x+intercept))**2 for x,y in zip(xs,ys))
    r2=1-ss_res/ss_tot if ss_tot>0 else 0.0
    return slope,intercept,r2

# ── PNG loader helper ─────────────────────────────────────────────────────────
def load_png(path, max_w=540, max_h=280):
    """Load a PNG and return a PhotoImage scaled to fit max dimensions."""
    try:
        img = Image.open(path)
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        return None

# ── Main result window ────────────────────────────────────────────────────────
def show_result_window(inputs, results, data, overall, timestamp):
    lon,lat,span_m,discharge,burial,channel_w = inputs
    L1,L2,L3,L4,L5 = results
    ndwi_rows,disc_rows,scour_tbl,sar_rows,fspan_rows = data

    win = tk.Toplevel()
    win.title("KRNPL Pipeline Risk Assessment")
    win.configure(bg="#1A2A4A")
    win.geometry("640x780")
    win.resizable(True,True)

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = tk.Frame(win, bg="#1A2A4A", pady=8)
    hdr.pack(fill="x")
    tk.Label(hdr,text="KRNPL PIPELINE RISK ALERT SYSTEM",
             font=("Helvetica",14,"bold"),fg="white",bg="#1A2A4A").pack()
    tk.Label(hdr,text="Indian Oil Corporation Limited  |  Pipelines Division",
             font=("Helvetica",9),fg="#ADD8E6",bg="#1A2A4A").pack()
    tk.Label(hdr,text=f"Assessment: {timestamp}",
             font=("Helvetica",8),fg="#888888",bg="#1A2A4A").pack()
    tk.Frame(win,bg="#C0202E",height=3).pack(fill="x")

    # ── Overall banner ────────────────────────────────────────────────────────
    ov_col = level_color(overall)
    ov_frm = tk.Frame(win,bg=ov_col,pady=10)
    ov_frm.pack(fill="x")
    tk.Label(ov_frm,
             text=f"{level_emoji(overall)}   OVERALL STATUS: {overall}",
             font=("Helvetica",15,"bold"),fg="white",bg=ov_col).pack()

    # ── Notebook (tabbed) ─────────────────────────────────────────────────────
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TNotebook",background="#1A2A4A",borderwidth=0)
    style.configure("TNotebook.Tab",background="#2E5A8E",foreground="white",
                    font=("Helvetica",9,"bold"),padding=[10,4])
    style.map("TNotebook.Tab",background=[("selected","#C0202E")])

    nb = ttk.Notebook(win)
    nb.pack(fill="both",expand=True,padx=0,pady=0)

    def make_scroll_tab(title):
        outer = tk.Frame(nb, bg="#F4F6F9")
        canvas = tk.Canvas(outer,bg="#F4F6F9",highlightthickness=0)
        sb = ttk.Scrollbar(outer,orient="vertical",command=canvas.yview)
        inner = tk.Frame(canvas,bg="#F4F6F9")
        inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0),window=inner,anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left",fill="both",expand=True)
        sb.pack(side="right",fill="y")
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)),"units"))
        nb.add(outer, text=title)
        return inner

    def sec(parent, title, color="#2E5A8E"):
        frm = tk.Frame(parent,bg="white",bd=1,relief="solid")
        frm.pack(fill="x",padx=10,pady=5)
        tk.Frame(frm,bg=color,height=4).pack(fill="x")
        tk.Label(frm,text=title,font=("Helvetica",10,"bold"),
                 fg=color,bg="white",anchor="w",padx=10,pady=3).pack(fill="x")
        return frm

    def drow(parent, label, value, color="#333333"):
        row=tk.Frame(parent,bg="white"); row.pack(fill="x",padx=10,pady=1)
        tk.Label(row,text=label,font=("Helvetica",9),fg="#666666",
                 bg="white",width=30,anchor="w").pack(side="left")
        tk.Label(row,text=value,font=("Helvetica",9,"bold"),
                 fg=color,bg="white",anchor="w").pack(side="left")

    def arow(parent, level, msg, action):
        col=level_color(level)
        af=tk.Frame(parent,bg=col,pady=5); af.pack(fill="x",padx=10,pady=(3,8))
        tk.Label(af,text=f"{level_emoji(level)}  {level}: {msg}",
                 font=("Helvetica",9,"bold"),fg="white",bg=col,
                 wraplength=500,justify="left",padx=8).pack(anchor="w")
        tk.Label(af,text=f"-> {action}",
                 font=("Helvetica",8,"italic"),fg="white",bg=col,
                 wraplength=500,justify="left",padx=8).pack(anchor="w")

    def add_chart(parent, png_path, caption=""):
        photo = load_png(png_path)
        if photo:
            lbl = tk.Label(parent,image=photo,bg="#F4F6F9")
            lbl.image = photo   # keep reference
            lbl.pack(padx=10,pady=(6,2))
            if caption:
                tk.Label(parent,text=caption,font=("Helvetica",8,"italic"),
                         fg="#666666",bg="#F4F6F9").pack()
        else:
            tk.Label(parent,
                     text=f"Chart not found: {os.path.basename(png_path)}\n"
                          f"Run the corresponding script first.",
                     font=("Helvetica",9),fg="#888888",bg="#F4F6F9",
                     pady=8).pack()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 0 — Summary
    # ══════════════════════════════════════════════════════════════════════════
    t0 = make_scroll_tab("  Summary  ")

    sf = sec(t0,"Site Inputs","#1A2A4A")
    drow(sf,"Longitude / Latitude", f"{lon:.5f} E  ,  {lat:.5f} N")
    drow(sf,"Pipe burial depth",    f"{burial:.1f} m")
    drow(sf,"Channel width",        f"{channel_w:.0f} m")
    drow(sf,"Observed exposed span",f"{span_m:.1f} m")
    drow(sf,"Input discharge",      f"{discharge:.1f} m3/s")

    # Layer status badges
    sf2 = sec(t0,"All-Layer Status Summary","#1A2A4A")
    lnames = ["L1  Channel Migration (Sentinel-2)",
              "L2  Flood Threshold (GPM IMERG)",
              "L3  Scour Depth Model (Lacey IRC:5)",
              "L4  SAR Change Detection (Sentinel-1)",
              "L5  Structural Free Span (DNV-RP-F105)"]
    lstats = [L1[0],L2[0],L3[0],L4[0],L5[0]]
    for nm,st in zip(lnames,lstats):
        col=level_color(st)
        row=tk.Frame(sf2,bg="white"); row.pack(fill="x",padx=10,pady=3)
        tk.Label(row,text=nm,font=("Helvetica",9),fg="#333333",
                 bg="white",width=36,anchor="w").pack(side="left")
        tk.Label(row,text=f" {level_emoji(st)} {st} ",
                 font=("Helvetica",9,"bold"),fg="white",bg=col,
                 padx=6,pady=2).pack(side="left",padx=4)

    # Required action
    actions = {
        "CRITICAL":("1. SHUT valves: Mundakhera RCP (Ch.133.7km) + Najibabad (Ch.167.3km)\n"
                    "2. Call IOCL Emergency Response immediately\n"
                    "3. Deploy field team to Ch.141-146 km\n"
                    "4. Isolate product flow. Prepare spill containment."),
        "ALERT":   ("1. Deploy drone survey to Ch.141-146 km within 24 hours\n"
                    "2. Pre-position emergency response team\n"
                    "3. Prepare valve isolation plan\n"
                    "4. Increase monitoring to every 6 hours"),
        "WARNING": ("1. Review 48-hr IMD rainfall forecast for the catchment\n"
                    "2. Alert field patrol team for Ch.141-146 km\n"
                    "3. Confirm valve operability at Mundakhera RCP\n"
                    "4. Schedule drone survey within 1 week"),
        "NORMAL":  ("Continue routine monitoring schedule.\n"
                    "Next inspection: per IOCL maintenance calendar."),
    }
    ov_col=level_color(overall)
    af=tk.Frame(t0,bg=ov_col,pady=10); af.pack(fill="x",padx=10,pady=8)
    tk.Label(af,text=f"{level_emoji(overall)}  REQUIRED ACTION — {overall}",
             font=("Helvetica",11,"bold"),fg="white",bg=ov_col).pack(anchor="w",padx=10)
    tk.Label(af,text=actions.get(overall,""),
             font=("Helvetica",9),fg="white",bg=ov_col,
             justify="left",wraplength=550).pack(anchor="w",padx=20,pady=4)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — Layer 1
    # ══════════════════════════════════════════════════════════════════════════
    t1 = make_scroll_tab("  Layer 1  ")
    l1_status,l1_slope,l1_pct,l1_yr = L1

    hf = sec(t1,"Layer 1 — Channel Migration (Sentinel-2 NDWI)","#2E5A8E")
    if l1_slope is not None:
        drow(hf,"Analysis period","2016 – 2024  (Oct–Nov post-monsoon composites)")
        drow(hf,"Water coverage trend",f"{l1_slope:+.2f} %/year",level_color(l1_status))
        drow(hf,"Latest water coverage",f"{l1_pct:.1f}%  (year {l1_yr})")
        drow(hf,"Layer 1 status",l1_status,level_color(l1_status))

        # Year-by-year table
        if ndwi_rows:
            tf = sec(t1,"Year-by-Year NDWI Data","#2E5A8E")
            hrow=tk.Frame(tf,bg="#2E5A8E"); hrow.pack(fill="x",padx=10,pady=(2,0))
            for h,w in [("Year",6),("Water %",10),("Mean NDWI",12),("Trend",8)]:
                tk.Label(hrow,text=h,font=("Helvetica",8,"bold"),fg="white",
                         bg="#2E5A8E",width=w,anchor="w").pack(side="left",padx=2)
            avg = sum(r["water_pct"] for r in ndwi_rows)/len(ndwi_rows)
            for i,r in enumerate(ndwi_rows):
                bg="#EBF2FA" if i%2==0 else "white"
                row=tk.Frame(tf,bg=bg); row.pack(fill="x",padx=10)
                trend = "▲" if i>0 and r["water_pct"]>ndwi_rows[i-1]["water_pct"] else "▼"
                tc = "#C0202E" if trend=="▲" else "#2E7D32"
                for val,w in [(str(r["year"]),6),(f"{r['water_pct']:.1f}%",10),
                              (f"{r['mean_ndwi']:.4f}",12),(trend,8)]:
                    col = tc if val in ["▲","▼"] else "#333333"
                    tk.Label(row,text=val,font=("Helvetica",8),fg=col,
                             bg=bg,width=w,anchor="w").pack(side="left",padx=2)
        arow(hf,l1_status,
             "Channel expanding rapidly toward pipeline." if l1_status=="CRITICAL" else
             "Channel slowly expanding near pipeline." if l1_status in ["ALERT","WARNING"] else
             "Channel position stable in 2016-2024 record.",
             "Prioritise drone survey and burial depth check." if l1_status in ["CRITICAL","ALERT"] else
             "Monitor monthly during monsoon." if l1_status=="WARNING" else
             "Continue quarterly monitoring.")
    else:
        tk.Label(t1,text="No NDWI data found.\nRun: python scripts/02_ndwi_timeseries.py",
                 font=("Helvetica",10),fg="#888888",bg="#F4F6F9",pady=20).pack()

    # Chart
    cf = sec(t1,"Layer 1 Chart — Water Coverage Trend","#2E5A8E")
    add_chart(cf, os.path.join(OUT_DIR,"layer1_trend.png"),
              "Fig 1: Sentinel-2 NDWI water coverage trend 2016-2024")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — Layer 2
    # ══════════════════════════════════════════════════════════════════════════
    t2 = make_scroll_tab("  Layer 2  ")
    l2_status,q_checked,warn_Q,alert_Q,crit_Q,l2_peak = L2

    h2 = sec(t2,"Layer 2 — Flood Threshold Monitoring (GPM IMERG)","#2E5A8E")
    drow(h2,"Discharge assessed",     f"{q_checked:.1f} m3/s",level_color(l2_status))
    drow(h2,"WARNING  threshold",     f"{warn_Q:.0f} m3/s")
    drow(h2,"ALERT    threshold",     f"{alert_Q:.0f} m3/s")
    drow(h2,"CRITICAL threshold",     f"{crit_Q:.0f} m3/s")
    if l2_peak:
        drow(h2,"Historical peak discharge",f"{l2_peak:.1f} m3/s")
    drow(h2,"Layer 2 status",l2_status,level_color(l2_status))

    if disc_rows:
        tf2 = sec(t2,"Year-by-Year Monsoon Discharge","#2E5A8E")
        hrow=tk.Frame(tf2,bg="#2E5A8E"); hrow.pack(fill="x",padx=10,pady=(2,0))
        for h,w in [("Year",6),("Intensity mm/hr",16),("Q m3/s",10),("vs Threshold",14)]:
            tk.Label(hrow,text=h,font=("Helvetica",8,"bold"),fg="white",
                     bg="#2E5A8E",width=w,anchor="w").pack(side="left",padx=2)
        for i,r in enumerate(disc_rows):
            bg="#EBF2FA" if i%2==0 else "white"
            row=tk.Frame(tf2,bg=bg); row.pack(fill="x",padx=10)
            lvl = risk_level(r["discharge"],warn_Q,alert_Q,crit_Q)
            col = level_color(lvl)
            for val,w in [(str(r["year"]),6),(f"{r['intensity']:.1f}",16),
                          (f"{r['discharge']:.1f}",10),(lvl,14)]:
                tk.Label(row,text=val,font=("Helvetica",8),
                         fg=col if val==lvl else "#333333",
                         bg=bg,width=w,anchor="w").pack(side="left",padx=2)

    arow(h2,l2_status,
         f"Discharge {q_checked:.0f} m3/s exceeds critical threshold {crit_Q:.0f} m3/s." if l2_status=="CRITICAL" else
         f"Discharge {q_checked:.0f} m3/s near critical threshold." if l2_status=="ALERT" else
         f"Discharge {q_checked:.0f} m3/s at warning level." if l2_status=="WARNING" else
         f"Discharge {q_checked:.0f} m3/s within safe limits.",
         "SHUT Mundakhera RCP + Najibabad valves. Emergency response." if l2_status=="CRITICAL" else
         "Deploy drone. Pre-position emergency team." if l2_status=="ALERT" else
         "Increase monitoring. Check 48-hr IMD forecast." if l2_status=="WARNING" else
         "No action required.")

    cf2 = sec(t2,"Layer 2 Chart — Peak Discharge Trend","#2E5A8E")
    add_chart(cf2, os.path.join(OUT_DIR,"layer2_trend.png"),
              "Fig 2: GPM IMERG monsoon peak discharge 2016-2024")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — Layer 3
    # ══════════════════════════════════════════════════════════════════════════
    t3 = make_scroll_tab("  Layer 3  ")
    l3_status,d_normal,d_design,cover = L3

    h3 = sec(t3,"Layer 3 — Scour Depth Model  (Lacey IRC:5 + Breusers)","#2E5A8E")
    drow(h3,"Input discharge",        f"{discharge:.1f} m3/s")
    drow(h3,"Channel width",          f"{channel_w:.0f} m")
    drow(h3,"d50 (bed sediment)",     "0.30 mm  (medium-fine sand, Shivalik rivers)")
    drow(h3,"Lacey silt factor f",    f"{1.76*math.sqrt(0.3):.3f}")
    drow(h3,"Lacey NORMAL scour",     f"{d_normal:.3f} m")
    drow(h3,"Lacey DESIGN scour",     f"{d_design:.3f} m  (IRC:5 = 1.27 x normal)")
    drow(h3,"Pipe burial depth",      f"{burial:.2f} m  (input)")
    drow(h3,"Cover remaining",        f"{cover:.3f} m",level_color(l3_status))
    drow(h3,"Layer 3 status",         l3_status,level_color(l3_status))

    # Live scour table for nearby Q values
    if scour_tbl:
        tf3 = sec(t3,"Scour Reference Table (from pre-computed model)","#2E5A8E")
        # Show 5 rows near the user's input discharge
        nearest = sorted(scour_tbl,key=lambda r: abs(r["discharge_m3s"]-discharge))[:8]
        nearest = sorted(nearest,key=lambda r: r["discharge_m3s"])
        hrow=tk.Frame(tf3,bg="#2E5A8E"); hrow.pack(fill="x",padx=10,pady=(2,0))
        for h,w in [("Q m3/s",8),("Gen Scour m",12),("Local Scour m",13),
                    ("Total Scour m",13),("Cover Left m",12)]:
            tk.Label(hrow,text=h,font=("Helvetica",8,"bold"),fg="white",
                     bg="#2E5A8E",width=w,anchor="w").pack(side="left",padx=2)
        for i,r in enumerate(nearest):
            bg="#FDECEA" if abs(r["discharge_m3s"]-discharge)<6 else \
               "#EBF2FA" if i%2==0 else "white"
            row=tk.Frame(tf3,bg=bg); row.pack(fill="x",padx=10)
            cl = r["discharge_m3s"]-burial
            for val,w in [(f"{r['discharge_m3s']:.0f}",8),
                          (f"{r['lacey_design_scour_m']:.3f}",12),
                          (f"{r['breusers_local_scour_m']:.3f}",13),
                          (f"{r['total_scour_m']:.3f}",13),
                          (f"{burial-r['lacey_design_scour_m']:.3f}",12)]:
                tk.Label(row,text=val,font=("Helvetica",8),fg="#333333",
                         bg=bg,width=w,anchor="w").pack(side="left",padx=2)
        tk.Label(tf3,text="  Highlighted row = closest to your input discharge",
                 font=("Helvetica",7,"italic"),fg="#C0202E",
                 bg="#F4F6F9",anchor="w").pack(fill="x",padx=10,pady=2)

    arow(h3,l3_status,
         f"Scour reached pipe level. Cover: {cover:.3f}m." if l3_status=="CRITICAL" else
         f"Only {cover:.3f}m cover remaining above pipe top." if l3_status=="ALERT" else
         f"{cover:.3f}m cover remaining — less than 50% of burial depth." if l3_status=="WARNING" else
         f"{cover:.3f}m cover remaining — pipe safely buried.",
         "EMERGENCY: Shut isolation valves. Pipe exposure imminent." if l3_status=="CRITICAL" else
         "Deploy inspection team to Ch.141-146 km immediately." if l3_status=="ALERT" else
         "Increase scour monitoring frequency." if l3_status=="WARNING" else
         "Continue routine monitoring.")

    cf3 = sec(t3,"Layer 3 Chart — Scour vs Discharge Curve","#2E5A8E")
    add_chart(cf3, os.path.join(OUT_DIR,"layer3_scour_curve.png"),
              "Fig 3: Lacey + Breusers scour model — discharge vs scour depth")

    cf3b = sec(t3,"Layer 2+3 Combined — Historical Risk","#2E5A8E")
    add_chart(cf3b, os.path.join(OUT_DIR,"layer3_combined_risk.png"),
              "Fig 4: Historical discharge classified by real scour thresholds")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — Layer 4
    # ══════════════════════════════════════════════════════════════════════════
    t4 = make_scroll_tab("  Layer 4  ")
    l4_status,l4_flag,l4_n = L4

    h4 = sec(t4,"Layer 4 — SAR Ground Change Detection (Sentinel-1)","#2E5A8E")
    drow(h4,"Method","Backscatter intensity change (VV polarisation)")
    drow(h4,"Baseline","March–May (pre-monsoon, stable ground)")
    drow(h4,"Monitor window","October–November (post-monsoon)")
    drow(h4,"Change threshold","-3 dB drop = significant water/erosion")
    if l4_flag is not None:
        drow(h4,"Latest season result",l4_flag,level_color(l4_status))
        drow(h4,"Years with change detected",f"{l4_n} of {len(sar_rows)} years")
    drow(h4,"Layer 4 status",l4_status,level_color(l4_status))

    if sar_rows:
        tf4 = sec(t4,"Year-by-Year SAR Change Results","#2E5A8E")
        hrow=tk.Frame(tf4,bg="#2E5A8E"); hrow.pack(fill="x",padx=10,pady=(2,0))
        for h,w in [("Year",6),("Pre dB",10),("Post dB",10),
                    ("Change dB",12),("Result",18)]:
            tk.Label(hrow,text=h,font=("Helvetica",8,"bold"),fg="white",
                     bg="#2E5A8E",width=w,anchor="w").pack(side="left",padx=2)
        for i,r in enumerate(sar_rows):
            bg="#FDECEA" if r["change_flag"]=="CHANGE_DETECTED" else \
               "#EBF2FA" if i%2==0 else "white"
            row=tk.Frame(tf4,bg=bg); row.pack(fill="x",padx=10)
            col="#C0202E" if r["change_flag"]=="CHANGE_DETECTED" else "#2E7D32"
            pre  = r.get("mean_pre_backscatter_db","N/A")
            post = r.get("mean_post_backscatter_db","N/A")
            chg  = r.get("backscatter_change_db","N/A")
            for val,w in [(r["year"],6),(f"{float(pre):.1f}" if pre!="N/A" else "N/A",10),
                          (f"{float(post):.1f}" if post!="N/A" else "N/A",10),
                          (f"{float(chg):+.2f}" if chg!="N/A" else "N/A",12),
                          (r["change_flag"],18)]:
                tk.Label(row,text=str(val),font=("Helvetica",8),
                         fg=col if str(val)==r["change_flag"] else "#333333",
                         bg=bg,width=w,anchor="w").pack(side="left",padx=2)

    arow(h4,l4_status,
         "SAR confirms physical ground change at pipeline corridor last season." if l4_status=="ALERT" else
         "No significant SAR ground change detected in latest season.",
         "Open sar_change_YYYY.png — red pixels = erosion on pipeline alignment." if l4_status=="ALERT" else
         "Continue monitoring. Check after next monsoon season.")

    # Show most recent SAR change PNG
    cf4 = sec(t4,"Latest SAR Change Map","#2E5A8E")
    latest_sar_yr = sar_rows[-1]["year"] if sar_rows else 2024
    add_chart(cf4,
              os.path.join(OUT_DIR,f"sar_change_{latest_sar_yr}.png"),
              f"Fig 5: SAR backscatter change map {latest_sar_yr}  "
              f"(RED=more water/erosion, BLUE=deposition)")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 5 — Layer 5
    # ══════════════════════════════════════════════════════════════════════════
    t5 = make_scroll_tab("  Layer 5  ")
    l5_status,allow_span,warn_sp,alert_sp,crit_sp,stress_ratio = L5

    h5 = sec(t5,"Layer 5 — Structural Free Span Assessment (DNV-RP-F105)","#2E5A8E")
    drow(h5,"Pipe OD / Wall thickness","273.05 mm / 5.56 mm")
    drow(h5,"Grade / SMYS","API 5L X46  /  317 MPa")
    drow(h5,"Operating pressure","65 barg")
    drow(h5,"Max allowable free span",f"{allow_span:.1f} m  (submerged, simply supported)")
    drow(h5,"Observed exposed span",  f"{span_m:.1f} m",level_color(l5_status))
    if span_m>0:
        drow(h5,"Stress utilisation", f"{min(stress_ratio,9.99):.2f}x allowable",
             level_color(l5_status))
    drow(h5,"WARNING  threshold",     f"{warn_sp:.1f} m  (50% allowable)")
    drow(h5,"ALERT    threshold",     f"{alert_sp:.1f} m  (75% allowable)")
    drow(h5,"CRITICAL threshold",     f"{crit_sp:.1f} m  (90% allowable)")
    drow(h5,"Layer 5 status",         l5_status,level_color(l5_status))

    # Najibabad context
    nj_ratio = 100/allow_span if allow_span>0 else 0
    nc = sec(t5,"Najibabad Incident Validation","#C0202E")
    drow(nc,"Reported exposed span (2021)","~100 m")
    drow(nc,"Allowable span",              f"{allow_span:.1f} m")
    drow(nc,"Ratio",                       f"{nj_ratio:.1f}x allowable — FAILURE confirmed",
         "#C0202E")

    # Freespan table near user input span
    if fspan_rows:
        tf5 = sec(t5,"Free Span Reference Table","#2E5A8E")
        nearby = sorted(fspan_rows, key=lambda r: abs(float(r["span_m"])-span_m))[:8]
        nearby = sorted(nearby, key=lambda r: float(r["span_m"]))
        hrow=tk.Frame(tf5,bg="#2E5A8E"); hrow.pack(fill="x",padx=10,pady=(2,0))
        for h,w in [("Span m",8),("Stress MPa",12),
                    ("Ratio",8),("VIV U_cr m/s",14),("Status",12)]:
            tk.Label(hrow,text=h,font=("Helvetica",8,"bold"),fg="white",
                     bg="#2E5A8E",width=w,anchor="w").pack(side="left",padx=2)
        for i,r in enumerate(nearby):
            sp_val = float(r["span_m"])
            st_val = str(r.get("status",""))
            col    = level_color(st_val)
            bg     = "#FDECEA" if abs(sp_val-span_m)<3 else \
                     "#EBF2FA" if i%2==0 else "white"
            row    = tk.Frame(tf5,bg=bg); row.pack(fill="x",padx=10)
            for val,w in [(f"{sp_val:.0f}",8),
                          (f"{float(r['bending_stress_mpa']):.1f}",12),
                          (f"{float(r['stress_ratio']):.3f}",8),
                          (f"{float(r['viv_critical_velocity_ms']):.2f}",14),
                          (st_val,12)]:
                tk.Label(row,text=val,font=("Helvetica",8),
                         fg=col if val==st_val else "#333333",
                         bg=bg,width=w,anchor="w").pack(side="left",padx=2)
        tk.Label(tf5,
                 text="  Highlighted row = closest to your input span",
                 font=("Helvetica",7,"italic"),fg="#C0202E",
                 bg="#F4F6F9",anchor="w").pack(fill="x",padx=10,pady=2)

    arow(h5,l5_status,
         f"Span {span_m:.0f}m exceeds 90% of allowable {allow_span:.0f}m. IMMINENT FAILURE." if l5_status=="CRITICAL" else
         f"Span {span_m:.0f}m at 75-90% of allowable. VIV fatigue developing." if l5_status=="ALERT" else
         f"Span {span_m:.0f}m at 50-75% of allowable. Margin reducing." if l5_status=="WARNING" else
         "Span within safe structural limits.",
         "SHUT VALVES. Emergency excavation. IOCL Emergency Response." if l5_status=="CRITICAL" else
         "Deploy emergency team. Prepare valve shutdown." if l5_status=="ALERT" else
         "Increase patrol. Prepare valve isolation plan." if l5_status=="WARNING" else
         "Continue routine monitoring.")

    cf5 = sec(t5,"Layer 5 Chart — Free Span Structural Assessment","#2E5A8E")
    add_chart(cf5, os.path.join(OUT_DIR,"layer5_freespan.png"),
              "Fig 6: Bending stress, stress ratio, and VIV analysis vs free span length")

    # ══════════════════════════════════════════════════════════════════════════
    # Bottom buttons
    # ══════════════════════════════════════════════════════════════════════════
    btn = tk.Frame(win,bg="#1A2A4A",pady=6)
    btn.pack(fill="x")

    def save_report():
        os.makedirs(OUT_DIR,exist_ok=True)
        fname = f"alert_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path  = os.path.join(OUT_DIR,fname)
        with open(path,"w") as f:
            f.write(f"KRNPL PIPELINE RISK ALERT REPORT\n")
            f.write(f"Generated : {timestamp}\n{'='*55}\n\n")
            f.write(f"SITE INPUTS\n")
            f.write(f"  Lon/Lat        : {lon:.5f} E , {lat:.5f} N\n")
            f.write(f"  Burial depth   : {burial:.1f} m\n")
            f.write(f"  Channel width  : {channel_w:.0f} m\n")
            f.write(f"  Exposed span   : {span_m:.1f} m\n")
            f.write(f"  Discharge      : {discharge:.1f} m3/s\n\n")
            f.write(f"LAYER RESULTS\n")
            for nm,st in zip(lnames,lstats):
                f.write(f"  {nm:<42} {st}\n")
            f.write(f"\nOVERALL STATUS : {overall}\n\n")
            f.write(f"LAYER 3 SCOUR\n")
            f.write(f"  Normal scour   : {d_normal:.3f} m\n")
            f.write(f"  Design scour   : {d_design:.3f} m\n")
            f.write(f"  Cover left     : {cover:.3f} m\n\n")
            f.write(f"REQUIRED ACTION\n{actions.get(overall,'')}\n")
        messagebox.showinfo("Report Saved",f"Saved to:\n{path}")

    tk.Button(btn,text="Save Full Report",command=save_report,
              bg="#2E5A8E",fg="white",font=("Helvetica",10,"bold"),
              relief="flat",padx=14,pady=5).pack(side="left",padx=10)
    tk.Button(btn,text="New Assessment",
              command=lambda:(win.destroy(), main()),
              bg="#F0A500",fg="white",font=("Helvetica",10,"bold"),
              relief="flat",padx=14,pady=5).pack(side="left",padx=4)
    tk.Button(btn,text="Close",command=win.destroy,
              bg="#C0202E",fg="white",font=("Helvetica",10,"bold"),
              relief="flat",padx=14,pady=5).pack(side="right",padx=10)

    win.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    root = tk.Tk(); root.withdraw()

    # Check Pillow
    try:
        from PIL import Image, ImageTk
    except ImportError:
        messagebox.showerror("Missing Library",
            "Please install Pillow first:\n\npip install Pillow\n\nThen run again.")
        root.destroy(); return

    L3t = load_layer3_thresholds()
    L5t = load_layer5_thresholds()

    messagebox.showinfo("KRNPL Risk Alert System",
        "KRNPL Pipeline Risk Alert System\n\n"
        "Indian Oil Corporation Limited\nPipelines Division\n\n"
        "You will be asked to enter 6 site parameters.\n"
        "Press OK to begin.")

    def ask(prompt, title, default):
        val = simpledialog.askstring(title, f"{prompt}\n(Default: {default})")
        if val is None: return None
        try:    return float(val)
        except: return float(default)

    lon       = ask("Crossing LONGITUDE (degrees East)\nExample: 78.1106",
                    "Step 1/6 — Coordinates", 78.1106)
    if lon is None: root.destroy(); return
    lat       = ask("Crossing LATITUDE (degrees North)\nExample: 29.6484",
                    "Step 2/6 — Coordinates", 29.6484)
    if lat is None: root.destroy(); return
    span_m    = ask("Observed EXPOSED SPAN (metres)\nEnter 0 if pipe is not exposed",
                    "Step 3/6 — Structural", 0.0)
    if span_m is None: root.destroy(); return
    discharge = ask("Current / forecast DISCHARGE Q (m3/s)\nEnter 0 if unknown",
                    "Step 4/6 — Hydraulic", 0.0)
    if discharge is None: root.destroy(); return
    burial    = ask("Pipe BURIAL DEPTH at crossing (metres)\n1.5 m = estimated open-trench",
                    "Step 5/6 — Pipe Parameters", 1.5)
    if burial is None: root.destroy(); return
    channel_w = ask("CHANNEL WIDTH at crossing (metres)\n100 m = MERIT Hydro estimate",
                    "Step 6/6 — Channel", 100.0)
    if channel_w is None: root.destroy(); return

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Load all data series
    ndwi_rows  = load_ndwi_series()
    disc_rows  = load_discharge_series()
    scour_tbl  = load_scour_table()
    sar_rows   = load_sar_series()
    fspan_rows = load_freespan_table()

    # Compute layer results
    warn_Q = L3t["WARNING_Q_M3S"]
    alert_Q= L3t["ALERT_Q_M3S"]
    crit_Q = L3t["CRITICAL_Q_M3S"]

    # L1
    if ndwi_rows and len(ndwi_rows)>=2:
        yrs=[r["year"] for r in ndwi_rows]
        wpc=[r["water_pct"] for r in ndwi_rows]
        sl,_,_ = linregress(yrs,wpc)
        l1_status = risk_level(sl,0.5,2.0,3.0)
        L1=(l1_status,sl,wpc[-1],yrs[-1])
    else:
        L1=("NO DATA",None,None,None)

    # L2
    q_checked = discharge if discharge>0 else (disc_rows[-1]["discharge"] if disc_rows else 0)
    l2_status = risk_level(q_checked,warn_Q,alert_Q,crit_Q)
    l2_peak   = max((r["discharge"] for r in disc_rows),default=None) if disc_rows else None
    L2=(l2_status,q_checked,warn_Q,alert_Q,crit_Q,l2_peak)

    # L3
    d_n,d_d,cov = compute_scour(discharge,channel_w,0.3,burial)
    if cov<=0:           l3s="CRITICAL"
    elif cov<burial*0.2: l3s="ALERT"
    elif cov<burial*0.5: l3s="WARNING"
    else:                l3s="NORMAL"
    L3=(l3s,d_n,d_d,cov)

    # L4
    if sar_rows:
        lf=sar_rows[-1]["change_flag"]
        nc=sum(1 for r in sar_rows if r["change_flag"]=="CHANGE_DETECTED")
        l4s="ALERT" if lf=="CHANGE_DETECTED" else "NORMAL"
        L4=(l4s,lf,nc)
    else:
        L4=("NO DATA",None,0)

    # L5
    al=L5t["FREESPAN_ALLOW_M"]; ws=L5t["WARNING_SPAN_M"]
    als=L5t["ALERT_SPAN_M"];    cs=L5t["CRITICAL_SPAN_M"]
    l5s=risk_level(span_m,ws,als,cs)
    sr=(span_m/al)**2 if al>0 and span_m>0 else 0
    L5=(l5s,al,ws,als,cs,sr)

    order={"NORMAL":0,"WARNING":1,"ALERT":2,"CRITICAL":3,"NO DATA":-1}
    overall=max((s for s in [L1[0],L2[0],L3[0],L4[0],L5[0]] if s!="NO DATA"),
                key=lambda s:order.get(s,0),default="NORMAL")

    root.destroy()
    show_result_window(
        (lon,lat,span_m,discharge,burial,channel_w),
        [L1,L2,L3,L4,L5],
        (ndwi_rows,disc_rows,scour_tbl,sar_rows,fspan_rows),
        overall, timestamp
    )

if __name__=="__main__":
    main()