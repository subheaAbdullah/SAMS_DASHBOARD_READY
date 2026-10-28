# -*- coding: utf-8 -*-
# =============================================================================
# SAMS — وحدة متابعة المشاريع (MEAL) + التقارير + الصلاحيات
# -----------------------------------------------------------------------------
# كل الملفات الحسّاسة (البيانات، المستخدمون، الإنجاز الشهري) تُخزَّن داخل
# مجلد خاص اسمه .sams_private/ — وهو مستثنى في .gitignore ولا يُرفع على GitHub.
#
# المحتوى:
#   1) تخزين خاص + إدارة المستخدمين والأدوار (Users / Roles)
#   2) إدخال الإنجاز الشهري (st.data_editor) وحفظه في monthly_actuals.csv
#   3) المتابعة والتقارير + فلترة (مشروع/مانح/مستوى) + تصدير Excel
#   4) تصدير التقارير PDF و Word لكل المستخدمين
#   5) تقرير شهري للأدمن على شكل صور + أرقام (PNG / ZIP / PDF / Word)
# =============================================================================
import io
import os
import re
import json
import glob
import math
import zipfile
import hashlib
import datetime

import numpy as np
import pandas as pd
import streamlit as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# =============================================================================
# ===== مسارات التخزين الخاص (خارج Git) =====
# =============================================================================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
# يمكن تغيير مكان التخزين الخاص عبر متغير البيئة SAMS_PRIVATE_DIR
PRIVATE_DIR = os.environ.get("SAMS_PRIVATE_DIR") or os.path.join(APP_DIR, ".sams_private")
os.makedirs(PRIVATE_DIR, exist_ok=True)

USERS_FILE = os.path.join(PRIVATE_DIR, "users.json")
MONTHLY_FILE = os.path.join(PRIVATE_DIR, "monthly_actuals.csv")
DATA_PRIVATE = os.path.join(PRIVATE_DIR, "data.xlsx")
DATA_UPLOADS_DIR = os.path.join(PRIVATE_DIR, "uploads")
os.makedirs(DATA_UPLOADS_DIR, exist_ok=True)

_LEGACY_USERS = os.path.join(APP_DIR, "users.json")
_LEGACY_MONTHLY = os.path.join(APP_DIR, "monthly_actuals.csv")

# =============================================================================
# ===== أدوات عامة =====
# =============================================================================
def _L(lang, ar, en):
    """نص ثنائي اللغة حسب لغة الواجهة."""
    return ar if str(lang or "ar").lower().startswith("ar") else en


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_name(txt, default="report"):
    s = re.sub(r"[^\w\u0600-\u06FF\- ]+", "_", str(txt or "")).strip(" _")
    return (s or default)[:80]


def _df_key(d):
    """بصمة سريعة وثابتة للـ DataFrame لعمل كاش آمن (بدون تجزئة كل الخلايا عند التغيير)."""
    if d is None:
        return "none"
    # نتذكر البصمة حسب هوية الكائن: تُحسب مرة واحدة لكل DataFrame في كل rerun
    try:
        hit = _DF_KEY_MEMO.get(id(d))
        if hit is not None and hit[0] is d:
            return hit[1]
    except Exception:
        pass
    try:
        cols = tuple(map(str, d.columns))
        h = hashlib.md5(pd.util.hash_pandas_object(d, index=False).values.tobytes()).hexdigest()[:16]
        key = (len(d), len(cols), h)
    except Exception:
        key = (len(d), len(getattr(d, "columns", [])), id(d))
    try:
        if len(_DF_KEY_MEMO) > 8:
            _DF_KEY_MEMO.clear()
        _DF_KEY_MEMO[id(d)] = (d, key)
    except Exception:
        pass
    return key


_DF_KEY_MEMO = {}


def _auth():
    return st.session_state.get("auth") or {}


def is_admin():
    return (_auth().get("role") == "admin")


def _current_name():
    a = _auth()
    return a.get("name") or a.get("email") or "—"


# =============================================================================
# ===== 1) المستخدمون والصلاحيات =====
# =============================================================================
def _pw_hash(pw, salt=""):
    return hashlib.sha256((str(salt) + str(pw)).encode("utf-8")).hexdigest()


def _migrate_legacy():
    """نقل users.json / monthly_actuals.csv القديمة إلى المجلد الخاص مرة واحدة."""
    try:
        if os.path.isfile(_LEGACY_USERS) and not os.path.isfile(USERS_FILE):
            with open(_LEGACY_USERS, "rb") as f:
                data = f.read()
            with open(USERS_FILE, "wb") as f:
                f.write(data)
        if os.path.isfile(_LEGACY_MONTHLY) and not os.path.isfile(MONTHLY_FILE):
            with open(_LEGACY_MONTHLY, "rb") as f:
                data = f.read()
            with open(MONTHLY_FILE, "wb") as f:
                f.write(data)
    except Exception:
        pass


def load_users():
    _migrate_legacy()
    try:
        if os.path.isfile(USERS_FILE):
            with io.open(USERS_FILE, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                # تأكيد أن الدور موجود وصحيح
                for k, v in list(d.items()):
                    if not isinstance(v, dict):
                        d.pop(k, None)
                        continue
                    if v.get("role") not in ("admin", "viewer"):
                        v["role"] = "viewer"
                return d
    except Exception:
        pass
    return {}


def save_users(d):
    try:
        tmp = USERS_FILE + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, USERS_FILE)
        return True
    except Exception:
        return False


def add_user(email, name, password, role="viewer"):
    email = (email or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return False, _L(st.session_state.get("lang", "ar"), "أدخل إيميلاً صحيحاً.", "Enter a valid email.")
    if len(password or "") < 4:
        return False, _L(st.session_state.get("lang", "ar"), "كلمة المرور ٤ أحرف على الأقل.", "Password must be at least 4 characters.")
    d = load_users()
    if email in d:
        return False, _L(st.session_state.get("lang", "ar"), "هذا الإيميل موجود مسبقاً.", "This email already exists.")
    salt = os.urandom(8).hex()
    d[email] = {"name": (name or "").strip() or email.split("@")[0],
                "pw": _pw_hash(password, salt), "salt": salt,
                "role": role if role in ("admin", "viewer") else "viewer",
                "created": _now(), "updated": _now()}
    if save_users(d):
        return True, _L(st.session_state.get("lang", "ar"), "تمت إضافة المستخدم.", "User added.")
    return False, _L(st.session_state.get("lang", "ar"), "تعذّر الحفظ — تحقّق من صلاحيات المجلد.", "Could not save — check folder permissions.")


def update_user(email, name=None, role=None, password=None):
    d = load_users()
    email = (email or "").strip().lower()
    if email not in d:
        return False
    if name is not None:
        d[email]["name"] = (name or "").strip() or email.split("@")[0]
    if role in ("admin", "viewer"):
        d[email]["role"] = role
    if password:
        salt = os.urandom(8).hex()
        d[email]["salt"] = salt
        d[email]["pw"] = _pw_hash(password, salt)
    d[email]["updated"] = _now()
    return save_users(d)


def delete_user(email):
    d = load_users()
    email = (email or "").strip().lower()
    if email in d:
        d.pop(email, None)
        return save_users(d)
    return False


# =============================================================================
# ===== 2) الإنجاز الشهري (monthly_actuals.csv) =====
# =============================================================================
MEAL_COLS = ["month", "project", "donor", "level", "indicator",
             "target", "actual", "note", "updated_by", "updated_at"]
DIM_COLS = ["month", "project", "donor", "level", "indicator", "note"]


@st.cache_data(show_spinner=False)
def _load_monthly_cached(path, mtime, size):
    try:
        d = pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame(columns=MEAL_COLS)
    return _normalize_monthly(d)


def _normalize_monthly(d):
    if d is None:
        d = pd.DataFrame(columns=MEAL_COLS)
    d = d.copy()
    for c in MEAL_COLS:
        if c not in d.columns:
            d[c] = ""
    d = d[MEAL_COLS]
    for c in DIM_COLS:
        d[c] = d[c].fillna("").astype(str).str.strip()
    for c in ("target", "actual"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0).astype(float)
    # حذف الصفوف الفارغة تماماً
    key = d[["month", "project", "donor", "level", "indicator"]].astype(str).agg("|".join, axis=1)
    empty = (key.str.replace("|", "", regex=False).str.strip() == "")
    d = d[~empty].reset_index(drop=True)
    d["achievement_pct"] = d.apply(
        lambda r: (r["actual"] / r["target"] * 100.0) if r["target"] > 0 else 0.0, axis=1)
    return d


def load_monthly():
    _migrate_legacy()
    try:
        mt = os.path.getmtime(MONTHLY_FILE)
        sz = os.path.getsize(MONTHLY_FILE)
    except Exception:
        return pd.DataFrame(columns=MEAL_COLS + ["achievement_pct"])
    return _load_monthly_cached(MONTHLY_FILE, mt, sz).copy()


def save_monthly(d):
    out = _normalize_monthly(d)
    out = out.drop(columns=["achievement_pct"], errors="ignore")
    out.to_csv(MONTHLY_FILE, index=False, encoding="utf-8-sig")
    _load_monthly_cached.clear()
    return MONTHLY_FILE


# =============================================================================
# ===== 3) خيارات الفلاتر من البيانات الرئيسية =====
# =============================================================================
def _uniq(fdata, col):
    if fdata is None or col not in getattr(fdata, "columns", []):
        return []
    try:
        vals = fdata[col].dropna().astype(str).str.strip()
        return sorted({v for v in vals if v and v.lower() not in ("nan", "none")})
    except Exception:
        return []


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: _df_key})
def _data_options_cached(fdata, monthly):
    months = set()
    try:
        if fdata is not None and "Date" in fdata.columns:
            per = pd.to_datetime(fdata["Date"], errors="coerce").dropna().dt.to_period("M").astype(str)
            months |= set(per.unique())
    except Exception:
        pass
    if isinstance(monthly, pd.DataFrame) and len(monthly):
        months |= set(monthly["month"].dropna().astype(str))
    months = sorted({m for m in months if re.match(r"^\d{4}-\d{2}$", str(m))})
    projects = _uniq(fdata, "Project ID")
    donors = _uniq(fdata, "Program")
    levels = _uniq(fdata, "Governorate")
    return months, projects, donors, levels


def data_options(fdata, monthly=None):
    if monthly is None:
        monthly = load_monthly()
    return _data_options_cached(fdata, monthly)


# =============================================================================
# ===== 4) التجميعات =====
# =============================================================================
def _pick_col(df, names):
    if df is None:
        return None
    for n in names:
        if n in df.columns:
            return n
    return None


GENERAL_METRICS = [
    ("services", ["Total services", "Number of given services",
                  "Consultations / Visits Total", "Consultations / Visits", "Total services "],
     "الخدمات المقدّمة", "Services provided"),
    ("beneficiaries", ["Total Benefeciaries all", "Uniqe Beneficiaries",
                       "Unique Beneficiaries", "New Benefeciaries"],
     "المستفيدون", "Beneficiaries"),
    ("consultations", ["Consultations / Visits Total", "Consultations / Visits",
                       "Number of outpatient Curative consultations"],
     "الاستشارات", "Consultations"),
]


def _sum_col(df, col):
    if df is None or col is None or col not in df.columns or len(df) == 0:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def meal_summary(mdf):
    """ملخّص الإنجاز الشهري: أهداف/إنجاز/نسبة + تجميعات."""
    out = {"target": 0.0, "actual": 0.0, "pct": 0.0, "rows": 0,
           "projects": 0, "donors": 0, "indicators": 0, "ahead": 0, "behind": 0,
           "by_project": pd.DataFrame(), "by_donor": pd.DataFrame(),
           "by_level": pd.DataFrame(), "by_indicator": pd.DataFrame()}
    if mdf is None or len(mdf) == 0:
        return out
    out["target"] = float(mdf["target"].sum())
    out["actual"] = float(mdf["actual"].sum())
    out["pct"] = (out["actual"] / out["target"] * 100.0) if out["target"] > 0 else 0.0
    out["rows"] = len(mdf)
    out["projects"] = int(mdf["project"].replace("", np.nan).nunique())
    out["donors"] = int(mdf["donor"].replace("", np.nan).nunique())
    out["indicators"] = int(mdf["indicator"].replace("", np.nan).nunique())
    _rowpct = mdf.apply(lambda r: (r["actual"] / r["target"] * 100.0) if r["target"] > 0 else 0.0, axis=1)
    out["ahead"] = int((_rowpct >= 100).sum())
    out["behind"] = int(((_rowpct > 0) & (_rowpct < 100)).sum())

    def _grp(col, label):
        if col not in mdf.columns:
            return pd.DataFrame()
        d = (mdf.groupby(col, dropna=False)[["target", "actual"]].sum()
             .reset_index().rename(columns={col: label}))
        d["achievement_pct"] = d.apply(
            lambda r: (r["actual"] / r["target"] * 100.0) if r["target"] > 0 else 0.0, axis=1)
        return d.sort_values("actual", ascending=False).reset_index(drop=True)

    out["by_project"] = _grp("project", _L(st.session_state.get("lang", "ar"), "المشروع", "Project"))
    out["by_donor"] = _grp("donor", _L(st.session_state.get("lang", "ar"), "المانح", "Donor"))
    out["by_level"] = _grp("level", _L(st.session_state.get("lang", "ar"), "المستوى", "Level"))
    out["by_indicator"] = _grp("indicator", _L(st.session_state.get("lang", "ar"), "المؤشر", "Indicator"))
    return out


def general_month(fdata, month):
    """النتائج العامة للشهر من قاعدة البيانات الرئيسية."""
    out = {"rows": 0, "facilities": 0, "governorates": 0, "programs": 0,
           "services": 0.0, "beneficiaries": 0.0, "consultations": 0.0,
           "by_gov": pd.DataFrame(), "trend": pd.DataFrame(),
           "metric_label": "", "available": False}
    if fdata is None or len(fdata) == 0 or "Date" not in getattr(fdata, "columns", []):
        return out
    try:
        d = fdata.copy()
        d["_m"] = pd.to_datetime(d["Date"], errors="coerce").dt.to_period("M").astype(str)
        sub = d[d["_m"] == str(month)]
        if len(sub) == 0:
            return out
        out["available"] = True
        out["rows"] = len(sub)
        for k, names, ar, en in GENERAL_METRICS:
            col = _pick_col(sub, names)
            if col is not None:
                out[k] = _sum_col(sub, col)
                if k == "services" and not out["metric_label"]:
                    out["metric_label"] = ar if str(st.session_state.get("lang", "ar")).startswith("ar") else en
        out["facilities"] = int(sub["Facility Name"].replace("", np.nan).nunique()) if "Facility Name" in sub.columns else 0
        out["governorates"] = int(sub["Governorate"].replace("", np.nan).nunique()) if "Governorate" in sub.columns else 0
        out["programs"] = int(sub["Program"].replace("", np.nan).nunique()) if "Program" in sub.columns else 0
        # حسب المحافظة
        if "Governorate" in sub.columns:
            mcol = _pick_col(sub, GENERAL_METRICS[0][1]) or _pick_col(sub, GENERAL_METRICS[1][1])
            if mcol:
                g = (sub.assign(_v=pd.to_numeric(sub[mcol], errors="coerce").fillna(0))
                     .groupby("Governorate")["_v"].sum().reset_index()
                     .rename(columns={"Governorate": "المحافظة", "_v": "القيمة"}))
                out["by_gov"] = g.sort_values("القيمة", ascending=False).head(10).reset_index(drop=True)
        # الاتجاه الشهري (آخر 18 شهر)
        trend = None
        for k, names, ar, en in GENERAL_METRICS:
            col = _pick_col(d, names)
            if col is not None and k == "services":
                trend = (d.assign(_v=pd.to_numeric(d[col], errors="coerce").fillna(0))
                         .groupby("_m")["_v"].sum().reset_index().rename(columns={"_m": "month", "_v": "value"}))
                break
        if trend is None:
            col = _pick_col(d, GENERAL_METRICS[1][1])
            if col:
                trend = (d.assign(_v=pd.to_numeric(d[col], errors="coerce").fillna(0))
                         .groupby("_m")["_v"].sum().reset_index().rename(columns={"_m": "month", "_v": "value"}))
        if trend is not None and len(trend):
            out["trend"] = trend.sort_values("month").tail(18).reset_index(drop=True)
    except Exception:
        pass
    return out


# =============================================================================
# ===== 5) الرسوم (صور PNG) =====
# =============================================================================
_FONT_READY = [False]


def _arabic_font_path():
    cands = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    try:
        cands.append(os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf"))
    except Exception:
        pass
    for p in cands:
        if p and os.path.isfile(p):
            return p
    return None


def _ensure_font():
    if _FONT_READY[0]:
        return
    try:
        import matplotlib.font_manager as fm
        p = _arabic_font_path()
        if p:
            fm.fontManager.addfont(p)
            name = fm.FontProperties(fname=p).get_name()
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass
    _FONT_READY[0] = True


def _shape(txt):
    """تشكيل الحروف العربية + اتجاه RTL لرسومات matplotlib/reportlab."""
    s = str(txt if txt is not None else "")
    if not re.search(r"[\u0600-\u06FF]", s):
        return s
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def _fig(w=7.4, h=3.4):
    _ensure_font()
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor("#151f38")
    ax.set_facecolor("#1c2846")
    for sp in ax.spines.values():
        sp.set_color("#2b3f66")
    ax.tick_params(colors="#c7d5ea", labelsize=8)
    ax.yaxis.label.set_color("#c7d5ea")
    ax.xaxis.label.set_color("#c7d5ea")
    return fig, ax


def _fig_save(fig):
    bio = io.BytesIO()
    fig.savefig(bio, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return bio.getvalue()


def _txt(lang, ar, en):
    return _shape(_L(lang, ar, en))


def fig_meal_projects(mdf, lang="ar", month=""):
    s = meal_summary(mdf)
    d = s["by_project"]
    if d is None or len(d) == 0:
        return None
    d = d.head(10).iloc[::-1]
    fig, ax = _fig(7.6, max(2.8, 0.42 * len(d) + 1.2))
    y = np.arange(len(d))
    ax.barh(y + 0.2, d["target"], height=0.38, color="#7c5cff", label=_txt(lang, "الهدف", "Target"))
    ax.barh(y - 0.2, d["actual"], height=0.38, color="#00d4ff", label=_txt(lang, "الإنجاز", "Actual"))
    ax.set_yticks(y)
    ax.set_yticklabels([str(x)[:28] for x in d.iloc[:, 0]], color="#c7d5ea", fontsize=8)
    ax.set_title(_txt(lang, "الهدف مقابل الإنجاز حسب المشروع", "Target vs actual by project"),
                 color="#e6edf7", fontsize=11, pad=10)
    ax.grid(axis="x", color="#2b3f66", alpha=0.5, linewidth=0.6)
    ax.legend(facecolor="#151f38", edgecolor="#2b3f66", labelcolor="#c7d5ea", fontsize=8)
    ax.ticklabel_format(style="plain", axis="x")
    return _fig_save(fig)


def fig_meal_donor(mdf, lang="ar"):
    s = meal_summary(mdf)
    d = s["by_donor"]
    if d is None or len(d) == 0:
        return None
    d = d[d["actual"] > 0].head(8)
    if len(d) == 0:
        return None
    fig, ax = _fig(6.4, 3.4)
    colors = ["#00d4ff", "#7c5cff", "#4ade80", "#fbbf24", "#f472b6", "#38bdf8", "#ff7a59", "#a78bfa"]
    ax.pie(d["actual"], labels=[str(x)[:18] for x in d.iloc[:, 0]], autopct="%1.0f%%",
           colors=colors[:len(d)], textprops={"color": "#c7d5ea", "fontsize": 8},
           wedgeprops={"edgecolor": "#151f38", "linewidth": 1.4})
    ax.set_title(_txt(lang, "توزيع الإنجاز حسب المانح", "Actual distribution by donor"),
                 color="#e6edf7", fontsize=11)
    return _fig_save(fig)


def fig_general_trend(trend, lang="ar"):
    if trend is None or len(trend) == 0:
        return None
    fig, ax = _fig(7.6, 3.2)
    ax.plot(trend["month"], trend["value"], color="#00d4ff", linewidth=2, marker="o", markersize=3)
    ax.fill_between(range(len(trend)), trend["value"], color="#00d4ff", alpha=0.12)
    ax.set_xticks(range(len(trend)))
    ax.set_xticklabels(trend["month"], rotation=45, ha="right", fontsize=7)
    ax.grid(color="#2b3f66", alpha=0.45, linewidth=0.6)
    ax.set_title(_txt(lang, "الاتجاه الشهري للخدمات", "Monthly services trend"),
                 color="#e6edf7", fontsize=11)
    return _fig_save(fig)


def fig_general_gov(by_gov, lang="ar"):
    if by_gov is None or len(by_gov) == 0:
        return None
    d = by_gov.head(10).iloc[::-1]
    fig, ax = _fig(7.6, max(2.8, 0.4 * len(d) + 1.2))
    ax.barh([str(x)[:22] for x in d.iloc[:, 0]], d.iloc[:, 1], color="#4ade80", height=0.55)
    ax.grid(axis="x", color="#2b3f66", alpha=0.45, linewidth=0.6)
    ax.set_title(_txt(lang, "النتائج حسب المحافظة (الشهر المحدد)", "Results by governorate (selected month)"),
                 color="#e6edf7", fontsize=11)
    ax.ticklabel_format(style="plain", axis="x")
    return _fig_save(fig)


# =============================================================================
# ===== 6) تصدير Excel =====
# =============================================================================
def excel_bytes(sheets, rtl=True):
    """تصدير عدة جداول إلى ملف Excel واحد."""
    bio = io.BytesIO()
    used = set()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        for name, df in (sheets or {}).items():
            if df is None:
                continue
            base = re.sub(r"[\\/*?:\[\]]", "_", str(name or "Sheet"))[:31] or "Sheet"
            nm = base
            i = 2
            while nm in used:
                suffix = f"_{i}"
                nm = base[:31 - len(suffix)] + suffix
                i += 1
            used.add(nm)
            df.to_excel(w, sheet_name=nm, index=False)
            try:
                w.sheets[nm].sheet_view.rightToLeft = bool(rtl)
                for col in w.sheets[nm].columns:
                    width = max(len(str(c.value or "")) for c in col[:200])
                    w.sheets[nm].column_dimensions[col[0].column_letter].width = min(46, max(10, width + 2))
            except Exception:
                pass
    return bio.getvalue()


# =============================================================================
# ===== 7) PDF (reportlab + تشكيل عربي) =====
# =============================================================================
_PDF_FONT = [None]


def _pdf_font():
    if _PDF_FONT[0]:
        return _PDF_FONT[0]
    name = "Helvetica"
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        p = _arabic_font_path()
        if p:
            pdfmetrics.registerFont(TTFont("SAMSAr", p))
            name = "SAMSAr"
    except Exception:
        name = "Helvetica"
    _PDF_FONT[0] = name
    return name


def _esc(txt):
    s = "" if txt is None else str(txt)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("\n", "<br/>"))


def pdf_bytes(payload, lang="ar"):
    """يبني تقرير PDF من payload: عنوان + KPIs + جداول + صور."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                        TableStyle, Image as RLImage, PageBreak)
        from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    except Exception:
        return None

    font = _pdf_font()
    bio = io.BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=A4, rightMargin=34, leftMargin=34,
                            topMargin=30, bottomMargin=28,
                            title=_L(lang, "تقرير SAMS", "SAMS report"))
    st_title = ParagraphStyle("t", fontName=font, fontSize=17, leading=22,
                              textColor=colors.HexColor("#0b2d5c"), alignment=TA_CENTER,
                              spaceAfter=4)
    st_sub = ParagraphStyle("s", fontName=font, fontSize=9.5, leading=13,
                            textColor=colors.HexColor("#55657a"), alignment=TA_CENTER,
                            spaceAfter=10)
    st_h = ParagraphStyle("h", fontName=font, fontSize=11.5, leading=15,
                          textColor=colors.HexColor("#0b2d5c"), alignment=TA_RIGHT,
                          spaceBefore=8, spaceAfter=5)
    st_p = ParagraphStyle("p", fontName=font, fontSize=8.6, leading=12,
                          textColor=colors.HexColor("#20303f"), alignment=TA_RIGHT)
    story = [Paragraph(_esc(_shape(payload.get("title", ""))), st_title),
             Paragraph(_esc(_shape(payload.get("subtitle", ""))), st_sub)]

    kpis = payload.get("kpis") or []
    if kpis:
        data = [[Paragraph(_esc(_shape(str(v))), st_p) for _, v in kpis],
                [Paragraph(_esc(_shape(str(k))), st_p) for k, _ in kpis]]
        n = len(kpis)
        tbl = Table(data, colWidths=[(A4[0] - 68) / max(1, n)] * n)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f2ff")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c3d3e6")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story += [tbl, Spacer(1, 8)]

    for cap, png in (payload.get("images") or []):
        try:
            im = ImageReader(io.BytesIO(png))
            iw, ih = im.getSize()
            width = A4[0] - 68
            height = width * ih / max(1, iw)
            maxh = 300
            if height > maxh:
                width = width * maxh / height
                height = maxh
            story += [Paragraph(_esc(_shape(cap)), st_h),
                      RLImage(io.BytesIO(png), width=width, height=height),
                      Spacer(1, 6)]
        except Exception:
            pass

    for name, df in (payload.get("tables") or []):
        if df is None or len(df) == 0:
            continue
        story.append(Paragraph(_esc(_shape(name)), st_h))
        show = df.head(40).copy()
        cols = list(show.columns)[:9]
        show = show[cols]
        head = [Paragraph(_esc(_shape(str(c))), st_p) for c in show.columns]
        body = []
        for _, row in show.iterrows():
            body.append([Paragraph(_esc(_shape(str(row[c]) if not isinstance(row[c], float)
                                           else f"{row[c]:,.1f}")), st_p) for c in show.columns])
        n = max(1, len(cols))
        tbl = Table([head] + body, colWidths=[(A4[0] - 68) / n] * n, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2d5c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c3d3e6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f8fd")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story += [tbl, Spacer(1, 8)]

    notes = payload.get("notes") or []
    if notes:
        story.append(Paragraph(_esc(_shape(_L(lang, "ملاحظات", "Notes"))), st_h))
        for n in notes:
            story.append(Paragraph("• " + _esc(_shape(n)), st_p))

    doc.build(story)
    return bio.getvalue()


# =============================================================================
# ===== 8) Word (python-docx) =====
# =============================================================================
def docx_bytes(payload, lang="ar"):
    try:
        from docx import Document
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
    except Exception:
        return None

    def _rtl(p):
        try:
            pPr = p._p.get_or_add_pPr()
            bidi = OxmlElement('w:bidi')
            pPr.append(bidi)
        except Exception:
            pass

    def _font(run, size=11, bold=False, color=None):
        run.font.name = "Arial"
        run.font.size = Pt(size)
        run.font.bold = bold
        if color:
            run.font.color.rgb = RGBColor(*color)
        try:
            rPr = run._element.get_or_add_rPr()
            rFonts = rPr.find(qn('w:rFonts'))
            if rFonts is None:
                rFonts = OxmlElement('w:rFonts')
                rPr.append(rFonts)
            rFonts.set(qn('w:cs'), "Arial")
            rFonts.set(qn('w:ascii'), "Arial")
            rFonts.set(qn('w:hAnsi'), "Arial")
        except Exception:
            pass

    def _para(doc, text, size=10, bold=False, align=WD_ALIGN_PARAGRAPH.RIGHT,
              color=None, space_after=4):
        p = doc.add_paragraph()
        p.alignment = align
        _rtl(p)
        r = p.add_run(str(text))
        _font(r, size, bold, color)
        p.paragraph_format.space_after = Pt(space_after)
        return p

    doc = Document()
    try:
        sec = doc.sections[0]
        sec.left_margin = Inches(0.55)
        sec.right_margin = Inches(0.55)
        sec.top_margin = Inches(0.55)
        sec.bottom_margin = Inches(0.55)
    except Exception:
        pass

    _para(doc, payload.get("title", ""), size=18, bold=True,
          align=WD_ALIGN_PARAGRAPH.CENTER, color=(0x0b, 0x2d, 0x5c), space_after=2)
    _para(doc, payload.get("subtitle", ""), size=9.5,
          align=WD_ALIGN_PARAGRAPH.CENTER, color=(0x55, 0x65, 0x7a), space_after=10)

    kpis = payload.get("kpis") or []
    if kpis:
        rows = math.ceil(len(kpis) / 4)
        tbl = doc.add_table(rows=rows * 2, cols=4)
        try:
            tbl.style = "Table Grid"
        except Exception:
            pass
        for i, (k, v) in enumerate(kpis):
            r = (i // 4) * 2
            c = i % 4
            cp = tbl.cell(r, c).paragraphs[0]
            cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _rtl(cp)
            _font(cp.add_run(str(v)), 13, True, (0x00, 0x6a, 0xa8))
            cp2 = tbl.cell(r + 1, c).paragraphs[0]
            cp2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _rtl(cp2)
            _font(cp2.add_run(str(k)), 8, False, (0x55, 0x65, 0x7a))
        doc.add_paragraph()

    for cap, png in (payload.get("images") or []):
        _para(doc, cap, size=11, bold=True, color=(0x0b, 0x2d, 0x5c), space_after=2)
        try:
            doc.add_picture(io.BytesIO(png), width=Inches(6.7))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception:
            pass

    for name, df in (payload.get("tables") or []):
        if df is None or len(df) == 0:
            continue
        _para(doc, name, size=11, bold=True, color=(0x0b, 0x2d, 0x5c), space_after=3)
        show = df.head(40).copy()
        cols = list(show.columns)[:9]
        show = show[cols]
        tbl = doc.add_table(rows=1, cols=len(cols))
        try:
            tbl.style = "Table Grid"
        except Exception:
            pass
        for j, c in enumerate(cols):
            p = tbl.rows[0].cells[j].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _rtl(p)
            _font(p.add_run(str(c)), 8, True, (0xff, 0xff, 0xff))
            try:
                tcPr = tbl.rows[0].cells[j]._tc.get_or_add_tcPr()
                shd = OxmlElement('w:shd')
                shd.set(qn('w:fill'), "0B2D5C")
                tcPr.append(shd)
            except Exception:
                pass
        for _, row in show.iterrows():
            cells = tbl.add_row().cells
            for j, c in enumerate(cols):
                p = cells[j].paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                _rtl(p)
                val = row[c]
                txt = f"{val:,.1f}" if isinstance(val, (float, np.floating)) else str(val)
                _font(p.add_run(txt), 8)
        doc.add_paragraph()

    notes = payload.get("notes") or []
    if notes:
        _para(doc, _L(lang, "ملاحظات", "Notes"), size=11, bold=True,
              color=(0x0b, 0x2d, 0x5c), space_after=3)
        for n in notes:
            _para(doc, "• " + str(n), size=9, space_after=2)

    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()


# =============================================================================
# ===== 9) بناء التقارير =====
# =============================================================================
def _fmt_num(v, dec=0):
    try:
        return f"{float(v):,.{dec}f}"
    except Exception:
        return str(v)


def _fmt_pct(v):
    try:
        return f"{float(v):,.1f}%"
    except Exception:
        return "—"


def followup_payload(mdf, lang="ar", subtitle=""):
    lang_ar = str(lang).startswith("ar")
    s = meal_summary(mdf)
    kpis = [
        (_L(lang, "عدد السجلات", "Records"), _fmt_num(s["rows"])),
        (_L(lang, "الهدف", "Target"), _fmt_num(s["target"])),
        (_L(lang, "الإنجاز", "Actual"), _fmt_num(s["actual"])),
        (_L(lang, "نسبة الإنجاز", "Achievement"), _fmt_pct(s["pct"])),
        (_L(lang, "المشاريع", "Projects"), _fmt_num(s["projects"])),
        (_L(lang, "المؤشرات", "Indicators"), _fmt_num(s["indicators"])),
    ]
    images = []
    png = fig_meal_projects(mdf, lang)
    if png:
        images.append((_L(lang, "الهدف مقابل الإنجاز حسب المشروع", "Target vs actual by project"), png))
    png = fig_meal_donor(mdf, lang)
    if png:
        images.append((_L(lang, "توزيع الإنجاز حسب المانح", "Actual by donor"), png))

    tables = []
    if len(s["by_project"]):
        tables.append((_L(lang, "التجميع حسب المشروع", "By project"), s["by_project"]))
    if len(s["by_donor"]):
        tables.append((_L(lang, "التجميع حسب المانح", "By donor"), s["by_donor"]))
    detail = mdf.copy()
    if len(detail):
        detail = detail[["month", "project", "donor", "level", "indicator", "target", "actual"]]
        detail["achievement_pct"] = detail.apply(
            lambda r: (r["actual"] / r["target"] * 100.0) if r["target"] > 0 else 0.0, axis=1)
        tables.append((_L(lang, "تفصيل السجلات", "Records detail"), detail))

    notes = [
        _L(lang, "نسبة الإنجاز = مجموع الإنجاز ÷ مجموع الأهداف.",
           "Achievement = total actual ÷ total target."),
    ]
    return {
        "title": _L(lang, "تقرير متابعة المشاريع (MEAL)", "MEAL Follow-up Report"),
        "subtitle": subtitle or _L(lang, "تقرير آلي من بيانات المتابعة", "Automated report from follow-up data"),
        "kpis": kpis,
        "images": images,
        "tables": tables,
        "notes": notes,
    }


def monthly_payload(mdf, general, month, lang="ar"):
    s = meal_summary(mdf)
    kpis = [
        (_L(lang, "الهدف الشهري", "Monthly target"), _fmt_num(s["target"])),
        (_L(lang, "الإنجاز الشهري", "Monthly actual"), _fmt_num(s["actual"])),
        (_L(lang, "نسبة الإنجاز", "Achievement"), _fmt_pct(s["pct"])),
        (_L(lang, "المشاريع", "Projects"), _fmt_num(s["projects"])),
        (_L(lang, "المؤشرات", "Indicators"), _fmt_num(s["indicators"])),
        (_L(lang, "مؤشرات متحققة", "Ahead"), _fmt_num(s["ahead"])),
    ]
    if general.get("available"):
        kpis += [
            (_L(lang, "الخدمات (النتائج العامة)", "Services (general)"), _fmt_num(general.get("services", 0))),
            (_L(lang, "المستفيدون (النتائج العامة)", "Beneficiaries (general)"), _fmt_num(general.get("beneficiaries", 0))),
            (_L(lang, "المنشآت", "Facilities"), _fmt_num(general.get("facilities", 0))),
            (_L(lang, "المحافظات", "Governorates"), _fmt_num(general.get("governorates", 0))),
        ]

    images = []
    png = fig_meal_projects(mdf, lang)
    if png:
        images.append((_L(lang, "الإنجاز حسب المشروع", "Actual by project"), png))
    png = fig_meal_donor(mdf, lang)
    if png:
        images.append((_L(lang, "الإنجاز حسب المانح", "Actual by donor"), png))
    png = fig_general_gov(general.get("by_gov"), lang)
    if png:
        images.append((_L(lang, "النتائج العامة حسب المحافظة", "General results by governorate"), png))
    png = fig_general_trend(general.get("trend"), lang)
    if png:
        images.append((_L(lang, "الاتجاه الشهري العام", "General monthly trend"), png))

    tables = []
    if len(s["by_project"]):
        tables.append((_L(lang, "الإنجاز حسب المشروع", "Actual by project"), s["by_project"]))
    if len(s["by_donor"]):
        tables.append((_L(lang, "الإنجاز حسب المانح", "Actual by donor"), s["by_donor"]))
    if general.get("available") and len(general.get("by_gov", [])):
        tables.append((_L(lang, "النتائج العامة حسب المحافظة", "General results by governorate"),
                       general["by_gov"]))

    notes = [
        _L(lang, f"الشهر: {month}", f"Month: {month}"),
        _L(lang, f"أُنشئ بواسطة: {_current_name()}", f"Generated by: {_current_name()}"),
        _L(lang, "التقرير أُنشئ محلياً — لا تُرفع البيانات على GitHub.",
           "Generated locally — data is never pushed to GitHub."),
    ]
    return {
        "title": _L(lang, "التقرير الشهري للمشاريع", "Monthly Projects Report"),
        "subtitle": f"{month} — {_L(lang, 'SAMS · متابعة المشاريع (MEAL)', 'SAMS · Projects Follow-up (MEAL)')}",
        "kpis": kpis,
        "images": images,
        "tables": tables,
        "notes": notes,
    }


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: _df_key})
def _cached_pdf(fdf, general_df, month, lang, kind):
    if kind == "monthly":
        payload = monthly_payload(fdf, general_df or {}, month, lang)
    else:
        payload = followup_payload(fdf, lang)
    return pdf_bytes(payload, lang)


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: _df_key})
def _cached_docx(fdf, general_df, month, lang, kind):
    if kind == "monthly":
        payload = monthly_payload(fdf, general_df or {}, month, lang)
    else:
        payload = followup_payload(fdf, lang)
    return docx_bytes(payload, lang)


def zip_images(images):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for i, (cap, png) in enumerate(images or [], 1):
            z.writestr(f"{i:02d}_{_safe_name(cap, 'image')}.png", png)
    return bio.getvalue()


# =============================================================================
# ===== 10) واجهة MEAL =====
# =============================================================================
def _kpi_cards(items):
    html = ('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));'
            'gap:10px;margin:10px 0 16px">')
    for lab, val in items:
        html += ('<div style="background:linear-gradient(180deg,#182341,#141e36);'
                 'border:1px solid #23324f;border-radius:14px;padding:12px 14px">'
                 f'<div style="color:#8aa0c0;font-size:12px;margin-bottom:2px">{lab}</div>'
                 f'<div style="color:#00d4ff;font-size:22px;font-weight:800">{val}</div></div>')
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _downloads(pdf, docx, excel=None, images=None, base="report", lang="ar", key="dl"):
    cols = st.columns(4)
    if pdf:
        cols[0].download_button("📄 PDF", pdf, file_name=f"{base}.pdf",
                                mime="application/pdf", use_container_width=True,
                                key=f"{key}_pdf")
    if docx:
        cols[1].download_button("📝 Word", docx, file_name=f"{base}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True, key=f"{key}_docx")
    if excel:
        cols[2].download_button("📊 Excel", excel, file_name=f"{base}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True, key=f"{key}_xlsx")
    if images:
        cols[3].download_button("🖼️ " + _L(lang, "صور ZIP", "Images ZIP"), zip_images(images),
                                file_name=f"{base}_images.zip", mime="application/zip",
                                use_container_width=True, key=f"{key}_zip")


def _filter_monthly(mdf, months_sel, project, donor, level):
    d = mdf.copy()
    if months_sel:
        d = d[d["month"].isin(months_sel)]
    if project:
        d = d[d["project"] == project]
    if donor:
        d = d[d["donor"] == donor]
    if level:
        d = d[d["level"] == level]
    return d.reset_index(drop=True)


def _tab_entry(fdata, lang, admin):
    st.markdown(f"#### 📝 {_L(lang, 'إدخال الإنجاز الشهري', 'Monthly actuals entry')}")
    st.caption(_L(lang,
                  "الجدول قابل للتعديل والإضافة. يُحفظ في ملف خاص: .sams_private/monthly_actuals.csv (غير مرفوع على Git).",
                  "Editable table. Saved privately to .sams_private/monthly_actuals.csv (never pushed to Git)."))
    months, projects, donors, levels = data_options(fdata)
    df = load_monthly()
    if not months:
        months = [datetime.date.today().strftime("%Y-%m")]
    # نضمّ القيم الموجودة أصلاً حتى ما تنمسح من الجدول
    proj_opts = sorted(set(projects) | set(df["project"].dropna().astype(str)) | {"أخرى"})
    donor_opts = sorted(set(donors) | set(df["donor"].dropna().astype(str)) | {"أخرى"})
    level_opts = sorted(set(levels) | set(df["level"].dropna().astype(str)) | {"أخرى"})
    month_opts = sorted(set(months) | set(df["month"].dropna().astype(str)))

    if admin:
        ver = st.session_state.get("_meal_ed_ver", 0)
        edited = st.data_editor(
            df.drop(columns=["achievement_pct"], errors="ignore"),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"meal_editor_{ver}",
            column_config={
                "month": st.column_config.SelectboxColumn(_L(lang, "الشهر", "Month"), options=month_opts, required=False),
                "project": st.column_config.SelectboxColumn(_L(lang, "المشروع", "Project"), options=[""] + proj_opts, required=False),
                "donor": st.column_config.SelectboxColumn(_L(lang, "المانح", "Donor"), options=[""] + donor_opts, required=False),
                "level": st.column_config.SelectboxColumn(_L(lang, "المستوى", "Level"), options=[""] + level_opts, required=False),
                "indicator": st.column_config.TextColumn(_L(lang, "المؤشر", "Indicator"), max_chars=200),
                "target": st.column_config.NumberColumn(_L(lang, "الهدف", "Target"), min_value=0.0, step=1.0, format="%.2f"),
                "actual": st.column_config.NumberColumn(_L(lang, "الإنجاز", "Actual"), min_value=0.0, step=1.0, format="%.2f"),
                "note": st.column_config.TextColumn(_L(lang, "ملاحظة", "Note"), max_chars=300),
                "updated_by": st.column_config.TextColumn(_L(lang, "آخر تعديل بواسطة", "Updated by"), disabled=True),
                "updated_at": st.column_config.TextColumn(_L(lang, "وقت التعديل", "Updated at"), disabled=True),
            },
        )
        c1, c2, c3 = st.columns([1, 1, 2])
        if c1.button("💾 " + _L(lang, "حفظ الإنجاز", "Save actuals"), type="primary",
                     use_container_width=True, key="meal_save"):
            out = edited.copy()
            out["updated_by"] = _current_name()
            out["updated_at"] = _now()
            try:
                save_monthly(out)
                st.session_state["_meal_ed_ver"] = ver + 1
                st.success(_L(lang, "تم الحفظ في monthly_actuals.csv", "Saved to monthly_actuals.csv"))
                st.rerun()
            except Exception as e:
                st.error(str(e))
        sample = pd.DataFrame([{"month": month_opts[-1], "project": (projects or ["Project 1"])[0],
                                "donor": (donors or ["Donor 1"])[0], "level": (levels or ["Level 1"])[0],
                                "indicator": "", "target": 0, "actual": 0, "note": "",
                                "updated_by": "", "updated_at": ""}])
        c2.download_button("⬇️ " + _L(lang, "نموذج CSV", "CSV template"),
                           sample.to_csv(index=False).encode("utf-8-sig"),
                           file_name="monthly_actuals_template.csv", mime="text/csv",
                           use_container_width=True, key="meal_tpl")
        mdf = load_monthly()
        if len(mdf):
            c3.caption(_L(lang, f"{len(mdf)} سجل محفوظ — آخر تعديل: {mdf['updated_at'].iloc[-1]}",
                          f"{len(mdf)} saved rows — last update: {mdf['updated_at'].iloc[-1]}"))
    else:
        st.info(_L(lang, "وضع المشاهدة: الإدخال والتعديل للأدمن فقط.",
                   "Viewer mode: entry and editing are admin-only."))
        st.dataframe(df.drop(columns=["achievement_pct"], errors="ignore"),
                     use_container_width=True, hide_index=True)


def _tab_followup(fdata, lang, admin):
    st.markdown(f"#### 📊 {_L(lang, 'المتابعة والتقارير', 'Follow-up & reports')}")
    df = load_monthly()
    months, projects, donors, levels = data_options(fdata, df)
    # نضمّ القيم الموجودة في ملف الإنجاز حتى لو ما إلها مقابل بالبيانات الرئيسية
    if len(df):
        projects = sorted(set(projects) | set(df["project"].dropna().astype(str)) - {""})
        donors = sorted(set(donors) | set(df["donor"].dropna().astype(str)) - {""})
        levels = sorted(set(levels) | set(df["level"].dropna().astype(str)) - {""})
    if len(df) == 0:
        st.warning(_L(lang, "لا يوجد إنجاز شهري محفوظ بعد — أضِفه من تبويب «إدخال الإنجاز الشهري».",
                      "No monthly actuals saved yet — add them in the entry tab."))
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        msel = st.multiselect(_L(lang, "الشهر", "Month"), months, default=[],
                              key="meal_f_months")
    with c2:
        psel = st.selectbox(_L(lang, "المشروع", "Project"), [""] + projects,
                            format_func=lambda x: x or _L(lang, "الكل", "All"),
                            key="meal_f_proj")
    with c3:
        dsel = st.selectbox(_L(lang, "المانح", "Donor"), [""] + donors,
                            format_func=lambda x: x or _L(lang, "الكل", "All"),
                            key="meal_f_donor")
    with c4:
        lsel = st.selectbox(_L(lang, "المستوى", "Level"), [""] + levels,
                            format_func=lambda x: x or _L(lang, "الكل", "All"),
                            key="meal_f_level")

    fdf = _filter_monthly(df, msel, psel, dsel, lsel)
    s = meal_summary(fdf)
    _kpi_cards([
        (_L(lang, "السجلات", "Records"), _fmt_num(s["rows"])),
        (_L(lang, "الهدف", "Target"), _fmt_num(s["target"])),
        (_L(lang, "الإنجاز", "Actual"), _fmt_num(s["actual"])),
        (_L(lang, "نسبة الإنجاز", "Achievement"), _fmt_pct(s["pct"])),
        (_L(lang, "المشاريع", "Projects"), _fmt_num(s["projects"])),
        (_L(lang, "المانحون", "Donors"), _fmt_num(s["donors"])),
    ])
    if len(s["by_project"]):
        png = fig_meal_projects(fdf, lang)
        if png:
            st.image(png, use_container_width=True)
    if len(s["by_donor"]):
        png = fig_meal_donor(fdf, lang)
        if png:
            st.image(png, use_container_width=True)

    show = fdf.copy()
    if len(show):
        show["achievement_pct"] = show.apply(
            lambda r: (r["actual"] / r["target"] * 100.0) if r["target"] > 0 else 0.0, axis=1)
        show = show.rename(columns={
            "month": _L(lang, "الشهر", "Month"), "project": _L(lang, "المشروع", "Project"),
            "donor": _L(lang, "المانح", "Donor"), "level": _L(lang, "المستوى", "Level"),
            "indicator": _L(lang, "المؤشر", "Indicator"), "target": _L(lang, "الهدف", "Target"),
            "actual": _L(lang, "الإنجاز", "Actual"), "note": _L(lang, "ملاحظة", "Note"),
            "achievement_pct": _L(lang, "نسبة الإنجاز %", "Achievement %"),
            "updated_by": _L(lang, "بواسطة", "By"), "updated_at": _L(lang, "التاريخ", "Date"),
        })
    st.dataframe(show, use_container_width=True, hide_index=True)

    # ===== تصدير Excel (متاح للجميع) =====
    if len(fdf):
        sheets = {
            _L(lang, "المتابعة", "Follow-up"): fdf.drop(columns=["achievement_pct"], errors="ignore"),
        }
        if len(s["by_project"]):
            sheets[_L(lang, "حسب المشروع", "By project")] = s["by_project"]
        if len(s["by_donor"]):
            sheets[_L(lang, "حسب المانح", "By donor")] = s["by_donor"]
        if len(s["by_level"]):
            sheets[_L(lang, "حسب المستوى", "By level")] = s["by_level"]
        if len(s["by_indicator"]):
            sheets[_L(lang, "حسب المؤشر", "By indicator")] = s["by_indicator"]
        xb = excel_bytes(sheets)
    else:
        xb = None

    # ===== تقارير PDF / Word لكل المستخدمين =====
    base = "MEAL_followup_" + datetime.datetime.now().strftime("%Y%m%d_%H%M")
    pdf = _cached_pdf(fdf, None, "", lang, "followup") if len(fdf) else None
    docx = _cached_docx(fdf, None, "", lang, "followup") if len(fdf) else None
    st.markdown(f"##### ⬇️ {_L(lang, 'تنزيل التقرير', 'Download report')}")
    _downloads(pdf, docx, xb, None, base=base, lang=lang, key="meal_fu")


def _tab_monthly_report(fdata, lang):
    st.markdown(f"#### 🗓️ {_L(lang, 'التقرير الشهري (أدمن)', 'Monthly report (admin)')}")
    st.caption(_L(lang,
                  "تقرير شهري على شكل صور + أرقام للنتائج العامة، مع تصدير PDF / Word / Excel / صور ZIP.",
                  "Monthly report with images + numbers for overall results, exportable to PDF / Word / Excel / images ZIP."))
    df = load_monthly()
    months, _, _, _ = data_options(fdata, df)
    if not months:
        months = [datetime.date.today().strftime("%Y-%m")]
    default_idx = len(months) - 1
    month = st.selectbox(_L(lang, "اختر الشهر", "Select month"), months,
                         index=default_idx, key="meal_rep_month")
    mdf = df[df["month"] == month].copy() if len(df) else df.copy()
    general = general_month(fdata, month)

    if len(mdf) == 0:
        st.warning(_L(lang,
                      f"لا يوجد إنجاز شهري مُدخل للشهر {month}. سيتم عرض النتائج العامة من قاعدة البيانات إن توفّرت.",
                      f"No monthly actuals for {month}. General results from the main database will be shown if available."))
    if not general.get("available"):
        st.info(_L(lang, "لا توجد بيانات رئيسية لهذا الشهر أيضاً.",
                   "No main-database rows for this month either."))

    s = meal_summary(mdf)
    cards = [
        (_L(lang, "الهدف الشهري", "Monthly target"), _fmt_num(s["target"])),
        (_L(lang, "الإنجاز الشهري", "Monthly actual"), _fmt_num(s["actual"])),
        (_L(lang, "نسبة الإنجاز", "Achievement"), _fmt_pct(s["pct"])),
    ]
    if general.get("available"):
        cards += [
            (_L(lang, "الخدمات العامة", "General services"), _fmt_num(general.get("services", 0))),
            (_L(lang, "المستفيدون", "Beneficiaries"), _fmt_num(general.get("beneficiaries", 0))),
            (_L(lang, "المنشآت", "Facilities"), _fmt_num(general.get("facilities", 0))),
            (_L(lang, "المحافظات", "Governorates"), _fmt_num(general.get("governorates", 0))),
            (_L(lang, "البرامج", "Programs"), _fmt_num(general.get("programs", 0))),
        ]
    _kpi_cards(cards)

    images = []
    png = fig_meal_projects(mdf, lang)
    if png:
        images.append((_L(lang, "الإنجاز حسب المشروع", "Actual by project"), png))
        st.markdown(f"**{_L(lang, 'الإنجاز حسب المشروع', 'Actual by project')}**")
        st.image(png, use_container_width=True)
    png = fig_meal_donor(mdf, lang)
    if png:
        images.append((_L(lang, "الإنجاز حسب المانح", "Actual by donor"), png))
        st.markdown(f"**{_L(lang, 'الإنجاز حسب المانح', 'Actual by donor')}**")
        st.image(png, use_container_width=True)
    png = fig_general_gov(general.get("by_gov"), lang)
    if png:
        images.append((_L(lang, "النتائج حسب المحافظة", "Results by governorate"), png))
        st.markdown(f"**{_L(lang, 'النتائج العامة حسب المحافظة', 'General results by governorate')}**")
        st.image(png, use_container_width=True)
    png = fig_general_trend(general.get("trend"), lang)
    if png:
        images.append((_L(lang, "الاتجاه الشهري", "Monthly trend"), png))
        st.markdown(f"**{_L(lang, 'الاتجاه الشهري العام', 'General monthly trend')}**")
        st.image(png, use_container_width=True)

    # ===== الأرقام التفصيلية =====
    if len(s["by_project"]):
        st.markdown(f"**{_L(lang, 'التجميع حسب المشروع', 'By project')}**")
        st.dataframe(s["by_project"], use_container_width=True, hide_index=True)
    if general.get("available") and len(general.get("by_gov", [])):
        st.markdown(f"**{_L(lang, 'النتائج العامة حسب المحافظة', 'General results by governorate')}**")
        st.dataframe(general["by_gov"], use_container_width=True, hide_index=True)

    payload = monthly_payload(mdf, general, month, lang)
    pdf = pdf_bytes(payload, lang)
    docx = docx_bytes(payload, lang)
    sheets = {_L(lang, "ملخص", "Summary"): pd.DataFrame(payload["kpis"], columns=[_L(lang, "المؤشر", "KPI"), _L(lang, "القيمة", "Value")])}
    if len(s["by_project"]):
        sheets[_L(lang, "حسب المشروع", "By project")] = s["by_project"]
    if general.get("available") and len(general.get("by_gov", [])):
        sheets[_L(lang, "حسب المحافظة", "By governorate")] = general["by_gov"]
    xb = excel_bytes(sheets)

    st.markdown(f"##### ⬇️ {_L(lang, 'تنزيل التقرير الشهري', 'Download monthly report')}")
    _downloads(pdf, docx, xb, images, base=f"MEAL_monthly_{month}", lang=lang, key="meal_rep")


def _tab_users(lang, admin):
    st.markdown(f"#### 🔐 {_L(lang, 'الصلاحيات (Users / Roles)', 'Permissions (Users / Roles)')}")
    st.caption(_L(lang,
                  "الحساب الأدمن الأساسي: SAMSAD. يمكن للأدمن إضافة مستخدمين وتحديد الدور (أدمن / مشاهد). تُحفظ الحسابات في .sams_private/users.json.",
                  "Main admin account: SAMSAD. Admin can add users and set roles (admin / viewer). Accounts are stored in .sams_private/users.json."))
    users = load_users()
    if not admin:
        st.info(_L(lang, "وضع المشاهدة: إدارة المستخدمين للأدمن فقط.",
                   "Viewer mode: user management is admin-only."))
        rows = [{"name": v.get("name", "") or "—", "role": v.get("role", "viewer"),
                 "created": v.get("created", "")} for _, v in sorted(users.items())]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        return

    with st.expander("➕ " + _L(lang, "إضافة مستخدم جديد", "Add new user"), expanded=False):
        with st.form("meal_add_user", clear_on_submit=True):
            c1, c2 = st.columns(2)
            name = c1.text_input(_L(lang, "الاسم", "Name"), key="meal_u_name")
            email = c2.text_input(_L(lang, "الإيميل", "Email"), key="meal_u_email")
            c3, c4 = st.columns(2)
            pw = c3.text_input(_L(lang, "كلمة المرور", "Password"), type="password", key="meal_u_pw")
            role = c4.selectbox(_L(lang, "الدور", "Role"), ["viewer", "admin"],
                                format_func=lambda x: _L(lang, "مشاهد", "Viewer") if x == "viewer" else _L(lang, "أدمن", "Admin"),
                                key="meal_u_role")
            ok = st.form_submit_button("➕ " + _L(lang, "إضافة", "Add"), type="primary",
                                       use_container_width=True)
        if ok:
            good, msg = add_user(email, name, pw, role)
            if good:
                st.success(msg); st.rerun()
            else:
                st.error(msg)

    if not users:
        st.info(_L(lang, "لا يوجد مستخدمون مسجّلون بعد.", "No registered users yet."))
        return

    st.markdown(f"##### 👥 {_L(lang, 'المستخدمون الحاليون', 'Current users')}")
    labels = {k: f"{v.get('name') or k} — {k} ({v.get('role', 'viewer')})" for k, v in users.items()}
    sel = st.selectbox(_L(lang, "اختر مستخدماً للتعديل", "Select a user to edit"),
                       list(users.keys()), format_func=lambda x: labels.get(x, x),
                       key="meal_u_sel")
    u = users[sel]
    e1, e2 = st.columns(2)
    new_name = e1.text_input(_L(lang, "الاسم", "Name"), value=u.get("name", ""), key="meal_u_edit_name")
    new_role = e2.selectbox(_L(lang, "الدور", "Role"), ["viewer", "admin"],
                            index=0 if u.get("role", "viewer") == "viewer" else 1,
                            format_func=lambda x: _L(lang, "مشاهد", "Viewer") if x == "viewer" else _L(lang, "أدمن", "Admin"),
                            key="meal_u_edit_role")
    new_pw = st.text_input(_L(lang, "كلمة مرور جديدة (اتركها فارغة للإبقاء على القديمة)",
                              "New password (leave blank to keep current)"),
                           type="password", key="meal_u_edit_pw")
    b1, b2, b3 = st.columns(3)
    if b1.button("💾 " + _L(lang, "حفظ التعديلات", "Save changes"), type="primary",
                 use_container_width=True, key="meal_u_save"):
        if update_user(sel, new_name, new_role, new_pw or None):
            st.success(_L(lang, "تم التحديث.", "Updated.")); st.rerun()
        else:
            st.error(_L(lang, "تعذّر التحديث.", "Could not update."))
    if b2.button("🔑 " + _L(lang, "تصفير كلمة المرور", "Reset password"),
                 use_container_width=True, key="meal_u_reset", disabled=not bool(new_pw)):
        if update_user(sel, password=new_pw):
            st.success(_L(lang, "تم تغيير كلمة المرور.", "Password changed.")); st.rerun()
    if b3.button("🗑 " + _L(lang, "حذف المستخدم", "Delete user"), use_container_width=True,
                 key="meal_u_del"):
        if delete_user(sel):
            st.success(_L(lang, "تم الحذف.", "Deleted.")); st.rerun()

    rows = [{"email": k, "name": v.get("name", ""), "role": v.get("role", "viewer"),
             "created": v.get("created", ""), "updated": v.get("updated", "")}
            for k, v in sorted(users.items())]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _admin_data_tools(alldata, lang):
    """أدوات الأدمن: تنزيل قاعدة البيانات الكاملة (Excel/CSV) — لا تظهر للمشاهد."""
    if not is_admin():
        return
    with st.expander("🔐 " + _L(lang, "أدوات البيانات (أدمن فقط)", "Data tools (admin only)"), expanded=False):
        st.caption(_L(lang,
                      f"التخزين الخاص: `{PRIVATE_DIR}`  \n"
                      "هذا المجلد مستثنى في .gitignore — لا تُرفع البيانات على GitHub.",
                      f"Private storage: `{PRIVATE_DIR}`  \n"
                      "This folder is excluded in .gitignore — data is never pushed to GitHub."))
        if alldata is not None and len(alldata):
            file_base = "SAMS_data_" + datetime.datetime.now().strftime("%Y%m%d_%H%M")
            c1, c2, c3 = st.columns(3)
            c1.download_button("📊 " + _L(lang, "تنزيل البيانات (Excel)", "Download data (Excel)"),
                               _full_excel(alldata), file_name=f"{file_base}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True, key="meal_dl_full_xlsx")
            c2.download_button("📄 " + _L(lang, "تنزيل البيانات (CSV)", "Download data (CSV)"),
                               alldata.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"{file_base}.csv", mime="text/csv",
                               use_container_width=True, key="meal_dl_full_csv")
            mdf = load_monthly()
            if len(mdf):
                c3.download_button("📝 " + _L(lang, "تنزيل الإنجاز الشهري", "Download monthly actuals"),
                                   mdf.drop(columns=["achievement_pct"], errors="ignore")
                                   .to_csv(index=False).encode("utf-8-sig"),
                                   file_name="monthly_actuals.csv", mime="text/csv",
                                   use_container_width=True, key="meal_dl_monthly")
            if os.path.isfile(DATA_PRIVATE):
                st.markdown("---")
                st.caption(_L(lang, "في نسخة دائمة محفوظة داخل التخزين الخاص.",
                              "A permanent copy is saved in private storage."))
                if st.button("🗑 " + _L(lang, "حذف الملف الدائم والعودة للملف الافتراضي",
                                       "Delete permanent file and use default"),
                             key="meal_del_private_data", use_container_width=True):
                    try:
                        os.remove(DATA_PRIVATE)
                        st.cache_data.clear()
                        st.success(_L(lang, "تم الحذف.", "Deleted."))
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        st.caption(_L(lang,
                      "لحفظ ملف بيانات جديد بشكل دائم: ارفعه من «مصدر البيانات» في الشريط الجانبي ثم اضغط «حفظ للاستخدام الدائم».",
                      "To persist a new data file: upload it from Data Source in the sidebar, then press 'Save permanently'."))


@st.cache_data(show_spinner=False, hash_funcs={pd.DataFrame: _df_key})
def _full_excel(d):
    return excel_bytes({_L(st.session_state.get("lang", "ar"), "البيانات", "Data"): d})


def render_meal_section(fdata, alldata, lang="ar", admin=None):
    """قسم متابعة المشاريع (MEAL) داخل الصفحة الرئيسية — 3 تبويبات + تقرير شهري للأدمن."""
    if admin is None:
        admin = is_admin()
    _admin_data_tools(alldata, lang)
    lbl = [
        "📝 " + _L(lang, "إدخال الإنجاز الشهري", "Monthly actuals entry"),
        "📊 " + _L(lang, "المتابعة والتقارير", "Follow-up & reports"),
        "🔐 " + _L(lang, "الصلاحيات (Users / Roles)", "Permissions (Users / Roles)"),
    ]
    if admin:
        lbl.append("🗓️ " + _L(lang, "التقرير الشهري", "Monthly report"))
    tabs = st.tabs(lbl)
    with tabs[0]:
        _tab_entry(fdata, lang, admin)
    with tabs[1]:
        _tab_followup(fdata, lang, admin)
    with tabs[2]:
        _tab_users(lang, admin)
    if admin:
        with tabs[3]:
            _tab_monthly_report(fdata, lang)
