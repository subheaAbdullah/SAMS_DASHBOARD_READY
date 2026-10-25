# -*- coding: utf-8 -*-
# فحص شامل للـ23 داشبورد: استثناءات + ألوان زرقاء فقط + عرض الرسومات + قطع النص
import os, re
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS","true")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS","false")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from streamlit.testing.v1 import AppTest
from matplotlib.backends.backend_agg import FigureCanvasAgg
APP = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")
KEYS = ["g_cb","g_rh","g_sg","g_chw","g_de","g_tr","g_ho","g_rf","g_lr","g_gi",
        "g_rd","g_da","f_inf","s_mh","s_bb","s_icu","s_dl","s_on","s_pt",
        "m_mb","o_pop","o_ca","o_er"]
FIG = {}
_o = plt.subplots
def spy(*a, **kw):
    f, ax = _o(*a, **kw)
    FIG["cur"].append(f)
    return f, ax
plt.subplots = spy

def is_blue(hx):
    hx = hx.lstrip("#")
    r, g, b = (int(hx[i:i+2], 16) for i in (0, 2, 4))
    return b > r and b > g

def audit_color(c, where, bad):
    if isinstance(c, str):
        if c.startswith("#") and not is_blue(c): bad.add((c.lower(), where))
        return
    try: seq = list(c)
    except TypeError: return
    if seq and not isinstance(seq[0], (int, float)):
        for x in seq: audit_color(x, where, bad)
        return
    if len(seq) >= 4 and seq[3] == 0: return
    if len(seq) < 3: return
    hx = "#%02x%02x%02x" % tuple(int(round(max(0, min(1, v)) * 255)) for v in seq[:3])
    if not is_blue(hx): bad.add((hx, where))

def clip_of(f):
    out = []
    c = FigureCanvasAgg(f); c.draw(); r = c.get_renderer()
    fb = f.bbox
    for ax in f.axes:
        for t in ax.get_xticklabels() + ax.get_yticklabels():
            if not t.get_text().strip(): continue
            bb = t.get_window_extent(r)
            if bb.x0 < fb.x0-1 or bb.x1 > fb.x1+1 or bb.y0 < fb.y0-1 or bb.y1 > fb.y1+1:
                out.append(t.get_text()[:22])
        lg = ax.get_legend()
        if lg is not None:
            for t in lg.get_texts():
                bb = t.get_window_extent(r)
                if bb.x1 > fb.x1+1 or bb.x0 < fb.x0-1 or bb.y1 > fb.y1+1 or bb.y0 < fb.y0-1:
                    out.append("leg:" + t.get_text()[:20])
    return out

print(f"{'unit':<7}{'figs':<6}{'full':<6}{'tiles':<7}{'exc':<6}{'nonblue':<9}{'clip'}")
print("-"*72)
bad_units = []
for k in KEYS:
    FIG["cur"] = []
    at = AppTest.from_file(APP, default_timeout=400)
    at.run()
    [b for b in at.sidebar.button if b.key == "sb_hhs"][0].click().run()
    FIG["cur"] = []                      # نلتقط رسوم هذا الداشبورد فقط
    [b for b in at.button if b.key and b.key.endswith(k)][0].click().run()
    ex = [e.value for e in at.exception]
    fs = FIG["cur"]
    nb = set()
    for i, f in enumerate(fs, 1):
        for ax in f.axes:
            for coll in list(ax.collections) + list(ax.patches):
                try: audit_color(coll.get_facecolor(), f"f{i}", nb)
                except Exception: pass
                try: audit_color(coll.get_edgecolor(), f"f{i}", nb)
                except Exception: pass
            for ln in list(ax.lines):
                try: audit_color(ln.get_color(), f"f{i}", ln_tag := f"f{i}", nb)
                except Exception: pass
    cl = []
    for i, f in enumerate(fs, 1):
        c = clip_of(f)
        if c: cl += [f"f{i}:{x}" for x in c[:3]]
    full = sum(1 for f in fs if f.get_size_inches()[0] > 13.45)
    tile = sum(1 for f in fs if f.get_size_inches()[0] < 5)
    print(f"{k:<7}{len(fs):<6}{full:<6}{tile:<7}{(ex[0][:5] if ex else '-'):<6}"
          f"{(str(sorted(nb)[:2]) if nb else '0'):<9}{(str(cl[:3]) if cl else '0')}")
    if ex or nb or cl: bad_units.append(k)
print()
print("UNITS WITH ISSUES:", bad_units or "NONE")
