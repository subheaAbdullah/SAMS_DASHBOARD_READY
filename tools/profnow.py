# -*- coding: utf-8 -*-
import os, cProfile, pstats, io as _io
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
import matplotlib; matplotlib.use("Agg")
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")
at = AppTest.from_file(APP, default_timeout=2400); at.run()
at.session_state["view"] = "hhs"; at.session_state["_hhs_key"] = "g_cb"; at.run()

pr = cProfile.Profile(); pr.enable()
at.run()
pr.disable()
s = _io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
ps.print_stats(38)
out = s.getvalue()
print("\n".join(out.split("\n")[:60]))