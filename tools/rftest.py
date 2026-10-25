# -*- coding: utf-8 -*-
# داشبورد الإحالات: 6 عناصر + كل الأعمدة مربوطة صح
import os, re
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
import matplotlib; matplotlib.use("Agg")
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")

for lang in ("ar", "en"):
    at = AppTest.from_file(APP, default_timeout=900); at.run()
    at.session_state["lang"] = lang; at.run()
    [b for b in at.sidebar.button if b.key == "sb_hhs"][0].click().run()
    [b for b in at.button if b.key == "hhs_general_g_rf"][0].click().run()
    print(f"\n########## lang={lang} ##########")
    print("exceptions:", [e.value for e in at.exception] or "NONE")
    for e in at.exception:
        for fr in (e.stack_trace or [])[-4:]: print("   ", fr)
    for m in at.markdown:
        v = m.value or ""
        if 'class="tbox' in v:
            print("  ① numbers:", re.findall(r'<div class="vl">([^<]+)</div>', v))
            print("  ① labels :", re.findall(r'<div class="lb">([^<]+)</div>', v))
        t = " ".join(re.sub(r"<[^>]+>", " ", v).split())
        if re.match(r"^[①②③④⑤⑥]", t): print("   ", t[:86])
    print("  charts:", len(at.get("arrow_vega_lite_chart")))