import os
# -*- coding: utf-8 -*-
# توحيد الخطوط والأحجام داخل الرسوم البيانية (كل الداشبوردات)
import io, re, sys

P = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")
src = io.open(P, encoding="utf-8").read()
L = src.split("\n")

defs = [(i + 1, re.match(r'\s*def (\w+)', l).group(1))
        for i, l in enumerate(L) if re.match(r'\s*def \w+\(', l) and not l.startswith(' ')]
idx = {}
for k, (ln, nm) in enumerate(defs):
    idx[nm] = (ln, defs[k + 1][0] - 1 if k + 1 < len(defs) else len(L))

rows = []
for n in [x for x in idx if x.startswith("dash_g_")]:
    a, b = idx[n]
    rows += list(range(a - 1, b))

APPLY = "--apply" in sys.argv

def tier_fs(v):
    v = float(v)
    if v <= 10:   return "DP_FS_SM"
    if v <= 12:   return "DP_FS"
    return "DP_FS_LG"

RULES = [
    (re.compile(r'\bfontsize=([0-9.]+)'), lambda m: 'fontsize=' + tier_fs(m.group(1)), "fontsize"),
    (re.compile(r'\blabelsize=([0-9.]+)'), lambda m: 'labelsize=' + tier_fs(m.group(1)), "labelsize"),
    (re.compile(r'\bmarkersize=([0-9.]+)'), lambda m: 'markersize=DP_MS', "markersize"),
    (re.compile(r'\blinewidth=([0-9.]+)'), lambda m: 'linewidth=DP_LW', "linewidth"),
]

counts = {}
out = list(L)
for i in rows:
    for rx, fn, tag in RULES:
        new = rx.sub(fn, out[i])
        if new != out[i]:
            counts[tag] = counts.get(tag, 0) + 1
            if APPLY:
                out[i] = new

print("changes:", counts, "total:", sum(counts.values()))
if APPLY:
    io.open(P, "w", encoding="utf-8", newline="").write("\n".join(out))
    print("APPLIED")
else:
    print("(dry run)")