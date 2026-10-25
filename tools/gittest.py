# -*- coding: utf-8 -*-
import os, re
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
import matplotlib; matplotlib.use("Agg")
from streamlit.testing.v1 import AppTest
import pandas as pd

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")

for lang in ("ar", "en"):
    at = AppTest.from_file(APP, default_timeout=900); at.run()
    at.session_state["lang"] = lang; at.run()
    [b for b in at.sidebar.button if b.key == "sb_hhs"][0].click().run()
    [b for b in at.button if b.key == "hhs_general_g_gi"][0].click().run()
    print(f"\n########## lang={lang} ##########")
    print("exceptions:", [e.value for e in at.exception] or "NONE")
    for e in at.exception:
        for fr in (e.stack_trace or [])[-4:]: print("   ", fr)
    for m in at.markdown:
        if "onebig" in (m.value or "") and "--c" in (m.value or ""):
            t = " ".join(re.sub(r"<[^>]+>", " ", m.value).split())
            print("  ONEBOX:", t)
    for m in at.markdown:
        t = " ".join(re.sub(r"<[^>]+>", " ", m.value or "").split())
        if re.match(r"^[①②③④⑤⑥]", t) and len(t) < 90: print("   ", t[:80])
    secs = [ " ".join(re.sub(r"<[^>]+>"," ",m.value or "").split())
            for m in at.markdown if 'class="ct"' in (m.value or "") ]
    print("  section bars:", len(secs))
    for s in secs[:12]: print("     -", s[:60])
    print("  dataframes:", len(at.dataframe))
    for i, df in enumerate(at.dataframe):
        print(f"   df{i}: shape={df.value.shape} cols={list(df.value.columns)}")
        if df.value.shape[0] <= 6:
            print(df.value.to_string(index=False)[:600])
    # تأكيد الأرقام
    d = pd.read_excel(os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","Basic and Final Update june 2026.xlsx"), sheet_name="Commulative Semi 2022")
    d.columns = [str(c).strip() for c in d.columns]
    g = d.groupby(d["Facility Name"].astype(str))["Total Gi Scope"].sum().astype(float)
    print("  SOURCE total:", f"{g.sum():,.0f}", "| facilities:", len(g), "| zeros:", int((g == 0).sum()))