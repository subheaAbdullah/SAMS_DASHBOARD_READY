# -*- coding: utf-8 -*-
# القائمة تفتح بالضغط وتحط الداتا تحتها — ما في أي تراكب (absolute/fixed)
import os, re, html
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
import matplotlib; matplotlib.use("Agg")
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")
at = AppTest.from_file(APP, default_timeout=900)
at.run()
[b for b in at.sidebar.button if b.key == "sb_hhs"][0].click().run()

bad = []
details = 0
for m in at.markdown:
    v = m.value or ""
    details += v.count('<details class="hovlist"')
    for t in re.findall(r'<details class="hovlist">.*?</details>', v, re.S):
        n = len(re.findall(r'<div>', t))
        if n < 1: bad.append(t[:70])

print("exceptions        :", [e.value for e in at.exception] or "NONE")
print("click-to-open lists:", details)
print("empty lists       :", len(bad))

# تأكد إنو ما في أي عنصر overlay Absolute/fixed بقى
src = open(APP, encoding="utf-8").read()
for tok in ("position:absolute", "position: fixed", "position:fixed",
            ".hov:hover::after", "data-tip="):
    print(f"  {tok:<22} occurrences: {src.count(tok)}")

# عدّ الأسماء بأكبر قائمة
at2 = AppTest.from_file(APP, default_timeout=900)
at2.run()
[b for b in at2.sidebar.button if b.key == "sb_hhs"][0].click().run()
[b for b in at2.button if b.key == "hhs_general_g_cb"][0].click().run()
mx = 0
for m in at2.markdown:
    for t in re.findall(r'<details class="hovlist">.*?</details>', m.value or "", re.S):
        mx = max(mx, len(re.findall(r'<div>', t)))
print("largest list (names):", mx, "of 67 ->", "ALL SHOWN" if mx >= 67 else "truncated")