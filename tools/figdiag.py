# -*- coding: utf-8 -*-
# تشخيص: أي شكل بالضبط فيه النص المقطوع، وبأي قياسات
import os, re
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from streamlit.testing.v1 import AppTest
from matplotlib.backends.backend_agg import FigureCanvasAgg
APP = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")

FIG = []
_o = plt.subplots
def spy(*a, **kw):
    f, ax = _o(*a, **kw); FIG.append(f); return f, ax
plt.subplots = spy

at = AppTest.from_file(APP, default_timeout=600); at.run()
[b for b in at.sidebar.button if b.key == "sb_hhs"][0].click().run()
FIG.clear()
[b for b in at.button if b.key and b.key.endswith("g_rd")][0].click().run()

for i, f in enumerate(FIG, 1):
    c = FigureCanvasAgg(f); c.draw(); r = c.get_renderer(); fb = f.bbox
    kind = ("barh" if any(len(gg.get_yticklabels()) for gg in f.axes) and
            any(len(t.get_yticks()) and len(t.get_yticklabels()) > 2 for t in f.axes) else "?")
    out = []
    for j, ax in enumerate(f.axes):
        for t in ax.get_xticklabels() + ax.get_yticklabels():
            if not t.get_text().strip(): continue
            bb = t.get_window_extent(r)
            if bb.x0 < fb.x0 - 1 or bb.x1 > fb.x1 + 1:
                out.append("ax%d %r x0=%.0f x1=%.0f fig=%.0f..%.0f fs=%.1f"
                           % (j, t.get_text()[:26], bb.x0, bb.x1, fb.x0, fb.x1,
                              t.get_fontsize()))
    print("fig%-2d inches=%.2fx%.2f px=%.0fx%.0f pos=%s"
          % (i, f.get_size_inches()[0], f.get_size_inches()[1],
             f.bbox.width, f.bbox.height, kind))
    for o in out[:4]: print("        CLIP", o)