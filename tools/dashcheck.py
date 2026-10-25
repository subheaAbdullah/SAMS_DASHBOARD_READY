# -*- coding: utf-8 -*-
# فحص كل الداشبوردات بعد التوحيد: يفتح كل زر فعليًا ويتأكد إنه يرسم شيئًا
import os, re, sys, hashlib
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
import matplotlib; matplotlib.use("Agg")
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")

at = AppTest.from_file(APP, default_timeout=2400); at.run()
[b for b in at.sidebar.button if b.key == "sb_hhs"][0].click().run()
keys = [b.key for b in at.button if b.key and b.key.startswith("hhs_")]
print("section buttons:", len(keys))
for k in keys: print("   ", k)

def strip(v): return " ".join(re.sub(r"<[^>]+>", " ", v or "").split())

print("\n=== per-dashboard render check ===")
sigs = {}
bad = 0


def to_sections():
    """ارجع لصفحة الأقسام (فيها الأزرار)"""
    for k in ("dash_back", "hhs_back"):
        b = [x for x in at.button if x.key == k]
        if b:
            b[0].click().run()
            return True
    return False


for k in keys:
    if k == "hhs_back":
        continue
    if not any(x.key == k for x in at.button):
        to_sections()
    b = [x for x in at.button if x.key == k]
    if not b:
        print("  %-24s BUTTON NOT FOUND" % k); bad += 1; continue
    try:
        b[0].click().run()
    except Exception as e:
        print("  %-24s CLICK FAILED %s" % (k, e)); bad += 1; continue
    ex = [e.value for e in at.exception]
    body = [m.value for m in at.markdown if m.value and "wallcard" not in m.value]
    secs = [m.value for m in at.markdown if 'class="ct"' in (m.value or "")]
    rheads = [m.value for m in at.markdown if "sect-h" in (m.value or "") or "rhead" in (m.value or "")]
    dfs = len(at.dataframe)
    sig = hashlib.md5("\n".join(body).encode()).hexdigest()[:8]
    sigs.setdefault(sig, []).append(k)
    if ex: bad += 1
    print("  %-24s md=%3d secbars=%2d rheads=%2d df=%d sig=%s exc=%s"
          % (k, len(body), len(secs), len(rheads), dfs, sig, ex or "NONE"))

print("\ndistinct renderings:", len(sigs), "/", len(keys) - 1)
print("with exceptions:", bad)