# -*- coding: utf-8 -*-
# قياس البطء: وين يروح الوقت فعليًا
import os, time, cProfile, pstats, io as _io
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
import matplotlib; matplotlib.use("Agg")
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")

def phase(tag, sess=None):
    if sess:
        for k, v in sess.items():
            pass
    t = time.time()
    return t

# --- 1) زمن التحميل الكامل ---
t0 = time.time()
at = AppTest.from_file(APP, default_timeout=2400)
at.run()
print("FULL RUN (cold cache)      : %.2fs" % (time.time() - t0))

# --- 2) زمن إعادة التشغيل بدون أي تغيير (typing simulé) ---
t0 = time.time(); at.run()
print("RERUN no change            : %.2fs" % (time.time() - t0))

# --- 3) rerun بعد تغيير فلاتر ---
t0 = time.time()
at.session_state["flt_Governorate"] = "Aleppo"; at.run()
print("RERUN after filter change  : %.2fs" % (time.time() - t0))
at.session_state["flt_Governorate"] = "All"; at.run()

# --- 4) كل داشبورد لحاله ---
KEYS = ["g_cb","g_rh","g_sg","g_chw","g_de","g_tr","g_ho","g_rf","g_lr","g_gi","g_rd","g_da"]
print("\n--- per-dashboard (rerun time) ---")
for k in KEYS:
    at.session_state["view"] = "hhs"
    at.session_state["_hhs_key"] = k
    at.run()
    t0 = time.time(); at.run()
    ex = [e.value for e in at.exception] or "NONE"
    print("  %-7s %6.2fs   exceptions=%s" % (k, time.time() - t0, ex))