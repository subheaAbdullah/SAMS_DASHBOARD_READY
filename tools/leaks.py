# -*- coding: utf-8 -*-
# فحص تسرّب النصوص العربية بالإنجليزية (عامة + شاشة المؤشرات)
import os, re, time
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
import matplotlib; matplotlib.use("Agg")
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","auto_tr.json")
AR = re.compile(r"[\u0600-\u06FF]")

def scan(at, tag):
    bad = []
    for i, m in enumerate(at.markdown):
        v = m.value or ""
        if AR.search(v) and "data:image" not in v and "<style>" not in v:
            bad.append(("md", " ".join(re.sub(r"<[^>]+>", " ", v).split())[:75]))
    for b in at.button:
        if AR.search(b.label or ""): bad.append(("btn", b.label[:60]))
    for c in at.caption:
        if AR.search(c.value or ""): bad.append(("cap", c.value[:60]))
    for w in at.warning:
        if AR.search(w.value or ""): bad.append(("warn", w.value[:60]))
    for x in at.selectbox:
        if AR.search(str(x.label or "")): bad.append(("sel", str(x.label)))
        for o in (x.options or []):
            if AR.search(str(o)): bad.append(("selopt", str(o)[:50]))
    for x in at.text_input:
        if AR.search(str(x.label or "")): bad.append(("tin", str(x.label)[:60]))
    for x in at.checkbox:
        if AR.search(str(x.label or "")): bad.append(("chk", str(x.label)[:60]))
    for x in at.expander:
        if AR.search(str(x.label or "")): bad.append(("exp", str(x.label)[:60]))
    print(f"  [{tag}] ARABIC LEAKS: {len(bad)}")
    seen = set()
    for t in bad:
        if t[1] in seen: continue
        seen.add(t[1]); print("     -", t[0], "|", t[1])
    return len(bad)

t0 = time.time()
at = AppTest.from_file(APP, default_timeout=2400); at.run()
print("run1 %.1fs | lang=%s | exceptions=%s" % (time.time()-t0, at.session_state.get("lang"),
                                                 [e.value for e in at.exception] or "NONE"))
n1 = scan(at, "dashboard/en")

# شاشة المؤشرات (form)
at.session_state["view"] = "form"; at.session_state["phase"] = "setup"; at.run()
print("indicators exceptions:", [e.value for e in at.exception] or "NONE")
n2 = scan(at, "indicators/en")

# زر اللغة -> عربي
[b for b in at.sidebar.button if b.key == "lang_toggle"][0].click().run()
print("after toggle lang:", at.session_state.get("lang"),
      "| exceptions:", [e.value for e in at.exception] or "NONE")

print("cache file exists:", os.path.isfile(CACHE),
      "| entries:", (len(open(CACHE, encoding="utf-8").read()) if os.path.isfile(CACHE) else 0), "bytes")
print("TOTAL LEAKS:", n1 + n2)