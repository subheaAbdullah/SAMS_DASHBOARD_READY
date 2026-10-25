import os
# -*- coding: utf-8 -*-
# توحيد شكل كل الداشبوردات على نمط «Consultations and BEN»
# dry-run: يعرض كل تغيير قبل تنفيذه
import io, re, sys

P = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ss_dash.py")
src = io.open(P, encoding="utf-8").read()
L = src.split("\n")

defs = [(i + 1, re.match(r'\s*def (\w+)', l).group(1))
        for i, l in enumerate(L) if re.match(r'\s*def \w+\(', l) and not l.startswith(' ')]
idx = {}
for k, (ln, nm) in enumerate(defs):
    idx[nm] = (ln, defs[k + 1][0] - 1 if k + 1 < len(defs) else len(L))

dash = [n for n in idx if n.startswith("dash_g_")]
ranges = []
for n in dash:
    a, b = idx[n]
    for i in range(a - 1, b):
        ranges.append((i, n))

APPLY = "--apply" in sys.argv

RULES = [
    # 1) صفوف السلايدين: نفس عرض سلايد الثلاثية + توسيط، مع تحديث فكّ التغليف
    (re.compile(r'^(\s*)(\w+),(\w+)=st\.columns\(\[1,1\],gap="medium"\)'),
     r'\1\2,\3,__pad=st.columns([0.5,1,1,0.5],gap="medium")', "row2-unpack"),
    (re.compile(r'st\.columns\(\[1,1\],gap="medium"\)'),
     'st.columns([0.5,1,1,0.5],gap="medium")', "row2"),
    (re.compile(r'st\.columns\(\[1,1\.6,1\.2\],gap="medium"\)'),
     'st.columns(3,gap="medium")', "row3-odd"),
    (re.compile(r'st\.columns\(3\)'), 'st.columns(3,gap="medium")', "gap"),
    # 2) توحيد المقاسات
    (re.compile(r'\bw=HALF_W\*[0-9.]+'), 'w=DP_W', "donut-w*"),
    (re.compile(r'\bw=HALF_W\b'), 'w=DP_W', "donut-w"),
    (re.compile(r'_dark_fig\(HALF_W,'), '_dark_fig(DP_W,', "fig-w"),
    (re.compile(r'\btsize=[0-9.]+'), 'tsize=DP_TSIZE', "tsize"),
    (re.compile(r'\blfont=[0-9.]+'), 'lfont=DP_LFONT', "lfont"),
    (re.compile(r'\blmax=[0-9.]+'), 'lmax=DP_LMAX', "lmax"),
    (re.compile(r'\bkey_below=(True|False)'), 'key_below=DP_KEYBELOW', "key_below"),
    (re.compile(r',h=[0-9.]+\)'), ')', "h-end"),
    (re.compile(r',h=[0-9.]+,'), ',', "h-mid"),
]

counts = {}
out = list(L)
for i, nm in ranges:
    for rx, rep, tag in RULES:
        new = rx.sub(rep, out[i])
        if new != out[i]:
            counts[tag] = counts.get(tag, 0) + 1
            if APPLY:
                out[i] = new

print("changes by rule:")
for k, v in sorted(counts.items(), key=lambda x: -x[1]):
    print("   %-12s %d" % (k, v))
print("total:", sum(counts.values()))

if APPLY:
    io.open(P, "w", encoding="utf-8", newline="").write("\n".join(out))
    print("APPLIED")
else:
    print("(dry run — pass --apply to write)")