# -*- coding: utf-8 -*-
# داشبورد المختبر والأشعة: 4 أرقام + خريطة + خطين جنب بعض
import os, re
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
import matplotlib; matplotlib.use("Agg")
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")

for lang in ("ar", "en"):
    at = AppTest.from_file(APP, default_timeout=900); at.run()
    at.session_state["lang"] = lang; at.run()
    [b for b in at.sidebar.button if b.key == "sb_hhs"][0].click().run()
    [b for b in at.button if b.key == "hhs_general_g_lr"][0].click().run()
    print(f"\n########## lang={lang} ##########")
    print("exceptions:", [e.value for e in at.exception] or "NONE")
    for e in at.exception:
        for fr in (e.stack_trace or [])[-3:]: print("   ", fr)
    box = 0
    for m in at.markdown:
        v = m.value or ""
        if 'class="tbox' in v:
            box += 1
            print(f"  ① numbers: {re.findall(r'<div class=.vl.>([^<]+)</div>', v)}")
            print(f"  ① labels : {re.findall(r'<div class=.lb.>([^<]+)</div>', v)}")
    print("  number boxes:", box)
    for m in at.markdown:
        t = " ".join(re.sub(r"<[^>]+>", " ", m.value or "").split())
        if re.match(r"^[①②③]", t): print("   ", t[:80])