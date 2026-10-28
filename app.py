# -*- coding: utf-8 -*-
# =============================================================================
# SAMS — لوحة متابعة المشاريع الإنسانية (Grant Monitoring Dashboard)
# تطبيق Streamlit لإنشاء المنح ومتابعة مؤشراتها بأسلوب Power BI (سمة داكنة).
# دورة العمل: جدار المنح (wall) ← إعداد المنحة والمؤشرات (setup / form) ← اللوحة (dashboard)
# الحفظ: ملفات pkl داخل مجلد saves/ + حفظ تلقائي للحظة في ملف _auto.pkl.
# ملاحظة: هذه النسخة معاد بناؤها بالتطابق مع كود بايت الأصلي مع إعادة كتابة
# التعليقات بالعربية (لأن ملف الـ pyc كان مجردًا من التعليقات).
# =============================================================================
import io,itertools,datetime,calendar,pickle,math,os,glob,re,unicodedata,hashlib,inspect,json
import pandas as pd
import numpy as np
import streamlit as st
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import FuncFormatter, MaxNLocator
import statistics as stt
import streamlit.components.v1 as components
# وحدة MEAL: التخزين الخاص + الإنجاز الشهري + التقارير PDF/Word + إدارة المستخدمين
import sams_meal as meal

# إعداد صفحة التطبيق: العنوان، عرض عريض، وإخفاء الشريط الجانبي افتراضيًا
st.set_page_config(page_title="SAMS - Grant Monitoring",layout="wide",initial_sidebar_state="collapsed")

# مجلد الحفظ (بجانب الكود) — داخله توضع ملفات المنح؛ الملفات الداخليّة تبدأ بـ _
SAVES_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)),"saves")
os.makedirs(SAVES_DIR,exist_ok=True)
AUTO=os.path.join(SAVES_DIR,"_auto.pkl")

# =============================================================================
# ===== ترجمة تلقائية: عربي ⇄ إنجليزي لكل النصوص المكتوبة مباشرة في الكود =====
# بعض النصوص (خصوصًا إعدادات المؤشرات) كانت مكتوبة بالعربية مباشرة داخل st.*.
# بدل ترجمتها كلمة كلمة، بنستدعي مترجم Google المجاني مرة واحدة لكل نص،
# وبنخزّن النتيجة في ملف auto_tr.json عشان بعدها كلشي محفوظ Offline وفوري.
# =============================================================================
AUTO_TR_FILE=os.path.join(os.path.dirname(os.path.abspath(__file__)),"auto_tr.json")
_AR_RE=re.compile(r"[\u0600-\u06FF]")
_AUTO_TR={}          # ar -> en  (مخبّأ في الذاكرة)
_AUTO_TR_DONE=set()  # النصوص اللي فشل ترجمتها (حتى ما نجرب كل مرة)
_AUTO_TR_ON=True     # تقدر تطفّيها من هنا
_A2E_SAVE_NOW=[False]   # هل في ترجمات جديدة لازم تنحفظ؟

# ===== اسم المنظمة: ثابت بكل الصفحات، ما بينترجم تلقائيًا =====
ORG_EN="Syrian American Medical Society"
ORG_AR="الجمعية السورية الأمريكية الطبية"
ORG_SHORT="SAMS"
ORG_DASH_AR="لوحة متابعة المشاريع الإنسانية"
ORG_DASH_EN="Grant Monitoring Dashboard"
# شعار SAMS: الصورة نفسها بتحوي الاسم كامل، فما مناخد اختصار
ORG_LOGO=os.path.join(os.path.dirname(os.path.abspath(__file__)),"1.png")
_ORG_LOGO_URI=[None]
def _org_logo():
    """صورة 1.png كـ data URI حتى تطلع جوّا HTML مع الحفاظ على حجمها
    الطبيعي (1163×258) بدون تصغير أو قص."""
    if _ORG_LOGO_URI[0] is None:
        _ORG_LOGO_URI[0]=""
        try:
            import base64
            with open(ORG_LOGO,"rb") as _f:
                _ORG_LOGO_URI[0]="data:image/png;base64,"+base64.b64encode(_f.read()).decode("ascii")
        except Exception:
            pass
    return _ORG_LOGO_URI[0]

def _pin_org_names():
    """اسم المنظمة ما بينترجم تلقائيًا — بينثبّت على حالو"""
    for k in (ORG_EN,ORG_AR,ORG_SHORT,ORG_DASH_AR,ORG_DASH_EN):
        _AUTO_TR[k]=k
        _AUTO_TR_DONE.add(k)

def _auto_tr_load():
    global _AUTO_TR
    try:
        if os.path.isfile(AUTO_TR_FILE):
            with io.open(AUTO_TR_FILE,encoding="utf-8") as _f:
                _AUTO_TR=json.load(_f) or {}
    except Exception:
        _AUTO_TR={}

def _auto_tr_save():
    try:
        with io.open(AUTO_TR_FILE,"w",encoding="utf-8") as _f:
            json.dump(_AUTO_TR,_f,ensure_ascii=False,indent=0)
    except Exception:
        pass

def _auto_tr_call(batch):
    """يترجم قائمة نصوص ar -> en دفعة وحدة. يرجّع dict {ar: en}."""
    out={}
    try:
        import requests
        _p=[("client","dict-chrome-ex"),("sl","ar"),("tl","en"),("dt","t")]
        for _q in batch: _p.append(("q",_q))
        _r=requests.get("https://clients5.google.com/translate_a/t",params=_p,timeout=25)
        _r.raise_for_status()
        _j=_r.json()
        # شكل الرد: نص واحد -> [[ [نص,...] ]]  |  عدة نصوص -> [نص, نص, ...]
        if isinstance(_j,list) and _j and all(isinstance(x,str) for x in _j):
            _items=_j                      # نص واحد أو عدة نصوص: قائمة نصوص مباشرة
        elif isinstance(_j,list) and _j and isinstance(_j[0],list):
            _items=[]                     # شكل قديم متداخل
            for _it in _j:
                try: _items.append(_it[0][0][0])
                except Exception: _items.append(None)
        else:
            _items=[]
        if len(_items)!=len(batch): return out
        for _src,_txt in zip(batch,_items):
            if isinstance(_txt,str) and _txt.strip(): out[_src]=_txt
    except Exception:
        pass
    return out

def A2E(text):
    """ترجمة نص عربي واحد -> إنجليزي (مع كاش)."""
    if not _AUTO_TR_ON: return text
    if not isinstance(text,str) or not _AR_RE.search(text): return text
    # ===== أشياء ما بنترجمها =====
    # 1) كتل CSS: فيها تعليقات عربي بس ما بتظهر للمستخدم + فيها صورة base64 ضخمة
    # 2) أي نص فيه data:image  (حجمه ضخم وبيرسل عبر النت كل مرة)
    # 3) النصوص الطويلة جدًا (>4000 حرف) — غالبًا HTML مدمج، وما يستاهل
    if "<style" in text or "</style" in text or "data:image" in text: return text
    if len(text)>4000: return text
    if text in _AUTO_TR: return _AUTO_TR[text]
    if text in _AUTO_TR_DONE: return text
    _got=_auto_tr_call([text])
    if text in _got:
        _AUTO_TR[text]=_got[text]; _A2E_SAVE_NOW[0]=True
        return _got[text]
    _AUTO_TR_DONE.add(text)
    return text

def A2E_MANY(texts):
    """ترجمة قائمة نصوص دفعة وحدة (أسرع بكثير من واحد واحد)."""
    if not _AUTO_TR_ON: return texts
    todo=[t for t in dict.fromkeys(texts)
          if isinstance(t,str) and _AR_RE.search(t)
          and t not in _AUTO_TR and t not in _AUTO_TR_DONE]
    if todo:
        for _i in range(0,len(todo),40):   # 40 نص per request
            _batch=todo[_i:_i+40]
            _got=_auto_tr_call(_batch)
            for _src in _batch:
                if _src in _got: _AUTO_TR[_src]=_got[_src]
                else: _AUTO_TR_DONE.add(_src)
            _A2E_SAVE_NOW[0]=True
    return [(_AUTO_TR.get(t) if isinstance(t,str) and _AUTO_TR.get(t) else t) for t in texts]

# ===== تركيب الترجمة التلقائية على كل دوال streamlit التي تعرض نصوصًا =====
# بهالطريقة كل نص عربي مكتوب مباشرة (indicators / setup / dashboard) بينترجم
# لحاله وقت التشغيل بدون ما نعدّل كل سطر يدوي.
_A2E_KW=("body","text","label","caption","help","placeholder","subtitle","value_msg","delta_msg")
# ملاحظة مهمة: ما بنترجم options ولا القيم — هي أسماء أعمدة من فايgls المستخدم أو
# مفاتيح مخزّنة (يومي/شهري/مجموع...)، وترجمتها بكسرت المطابقة بين الUI والداتا.
_A2E_NO_LIST=True
def _a2e_patch():
    import functools
    from streamlit.delta_generator import DeltaGenerator as _DG
    def _disp(_x):
        return A2E(_x) if isinstance(_x,str) else _x
    def _wrap(fn):
        @functools.wraps(fn)
        def _w(*a,**kw):
            if st.session_state.get("lang","en")=="en":
                # لو كانت دالة على DeltaGenerator فـ self هو أول وسيط
                _i=1 if a and isinstance(a[0],_DG) else 0
                if len(a)>_i and isinstance(a[_i],str) and _AR_RE.search(a[_i]):
                    a=list(a); a[_i]=A2E(a[_i]); a=tuple(a)
                for _k in _A2E_KW:
                    if _k in kw and isinstance(kw[_k],str) and _AR_RE.search(kw[_k]):
                        kw[_k]=A2E(kw[_k])
                _ff=kw.get("format_func")
                # خيارات القوائم: نترجم المعروض فقط عبر format_func، والقيمة
                # الأصلية ترجع زي ما هي (أسماء أعمدة الفايزل ومفاتيح محفوظة)
                _op=kw.get("options")
                if _op is None and len(a)>_i+1 and isinstance(a[_i+1],(list,tuple)):
                    _op=a[_i+1]
                if isinstance(_op,(list,tuple)) and any(isinstance(x,str) and _AR_RE.search(x) for x in _op):
                    if callable(_ff):
                        _prev=_ff
                        def _chain(_x,_p=_prev): return _disp(_p(_x))
                        kw["format_func"]=_chain
                    else:
                        kw["format_func"]=_disp
                elif callable(_ff):
                    _prev=_ff
                    @functools.wraps(_prev)
                    def _ffw(_x,_p=_prev): return _disp(_p(_x))
                    kw["format_func"]=_ffw
            return fn(*a,**kw)
        return _w
    # نترجم على مستوى DeltaGenerator أيضًا (st.columns / st.sidebar ... كلهم بيستخدموه)
    _targets=[st]
    try:
        from streamlit.delta_generator import DeltaGenerator
        _targets.append(DeltaGenerator)
    except Exception:
        pass
    for _mod in _targets:
        for _name in ("markdown","caption","info","warning","error","success",
                      "subheader","header","title","text","write","divider","toast",
                      "button","checkbox","radio","selectbox","multiselect",
                      "text_input","text_area","number_input","date_input","file_uploader",
                      "download_button","expander","form","toggle","popover","dialog"):
            _fn=getattr(_mod,_name,None)
            if callable(_fn):
                try: setattr(_mod,_name,_wrap(_fn))
                except Exception: pass

def _auto_tr_flush():
    """يحفظ الكاش على القرص (بينادى بعد كل rerun إذا في جديد)."""
    try:
        if _A2E_SAVE_NOW[0]:
            _auto_tr_save(); _A2E_SAVE_NOW[0]=False
    except Exception:
        pass

_auto_tr_load()
_pin_org_names()
_a2e_patch()

# =============================================================================
# ===== نظام اللغة (English أساسي ⇄ عربي) =====
# اللغة الأساسية للموقع إنجليزية. زر اللغة في السايدبار يقلب الموقع كله فورًا.
# النصوص مرتبة في قاموس UI لكل لغة، والدالة T(key) ترجّع النص حسب اللغة الحالية.
# لإضافة نص جديد: أضف المفتاح في اللغتين معًا وإلا سيظهر المفتاح نفسه كبديل.
# =============================================================================
# تهيئة اللغة الافتراضية (إنجليزية) مرة واحدة لكل جلسة
if "lang" not in st.session_state:
    st.session_state["lang"]="en"

UI={
 "ar":{
  # --- القوائم الجديدة ---
  "btn_hhs":"🏥 لوحة خدمات الصحة",
  "hhs_title":"لوحة خدمات الصحة",
  "hhs_sub":"اختر القسم الذي تريد الدخول إليه",
  "sec_general":"تحليل عام",
  "sec_flashcards":"بطاقات معلومات",
  "sec_specialized":"خدمات متخصصة",
  "sec_morbidity":"الأمراض والوفيات",
  "sec_other":"أخرى",
  "btn_back":"⬅ رجوع",
  "btn_home":"🏠 الرئيسية",
  "btn_lang":"🌐 English",
  "coming_soon":"قريبًا",
  "no_items":"لا توجد عناصر بعد — أضِفها من SECTIONS في الكود",
  # ===== تحليل عام (12 قسمًا) =====
  "g_cb":"الاستشارات والمنافع",
  "g_rh":"الصحة الإنجابية",
  "g_sg":"العمليات الجراحية",
  "g_chw":"الرعاية الصحية المنزلية",
  "g_de":"خدمات الأسنان",
  "g_tr":"الجروح",
  "g_ho":"الإقامة في المستشفى",
  "g_rf":"الإحالات",
  "g_lr":"المختبر والأشعة",
  "g_gi":"تنظير الجهاز الهضمي",
  "g_rd":"الإعاقات المبلّغ عنها",
  "g_da":"توفر الأدوية",
  # ===== بطاقات معلومات =====
  "f_inf":"معلومات (INF)",
  # ===== خدمات متخصصة (6 أزرار) =====
  "s_mh":"الصحة النفسية",
  "s_bb":"بنك الدم",
  "s_icu":"العناية المركزة والحاضنات",
  "s_dl":"غسيل الكلى",
  "s_on":"الأورام",
  "s_pt":"العلاج الطبيعي",
  # ===== الأمراض والوفيات =====
  "m_mb":"الأمراض (Morbidities)",
  # ===== أخرى (3 أزرار) =====
  "o_pop":"عدد السكان",
  "o_ca":"منطقة الخدمة",
  "o_er":"تقرير الطوارئ 2026",
  # ===== صفحة البيانات =====
  "data_title":"بيانات: ",
  "upload_label":"📂 ارفع ملف Excel هنا",
  "upload_help":"الملفات المدعومة: xlsx / xls / csv",
  "no_file":"لم يتم رفع أي ملف بعد",
  "rows_label":"الصفوف",
  # ===== الجروح / war related =====
  "tr_trauma":"استشارات الجروح",
  "tr_war":"مرتبطة بالحرب",
  "tr_nonwar":"غير مرتبطة بالحرب",
  "tr_male":"ذكور",
  "tr_female":"إناث",
  "tr_age_gender":"الإناث والذكور حسب الفئة العمرية",
  "tr_war_pct":"نسبة war-related من الجروح",
  "tr_by_time":"استشارات الجروح و war-related شهرياً",
  "f_month":"حسب الشهر",
  # ===== تنظير الجهاز الهضمي =====
  "gi_total":"إجمالي التنظير",
  "gi_ages":"الفئات العمرية",
  "gi_upper_lower":"علوي مقابل سفلي",
  "gi_upper":"تنظير علوي",
  "gi_lower":"تنظير سفلي",
  "gi_by_fac":"التنظير حسب المنشأة",
  "gi_section":"القسم",
  "gi_totals":"مجاميع التنظير حسب القسم",
  "gi_total_all":"المجموع الكلي",
  "gi_by_time":"التنظير عبر الأشهر",
  # ===== المختبر والأشعة =====
  "lr_lab":"فحوص المختبر",
  "lr_rad":"فحوص الأشعة",
  "lr_ref_lab":"إحالة بسبب المختبر",
  "lr_ref_rad":"إحالة بسبب الأشعة",
  "lr_rad_parts":"أقسام الأشعة",
  "lr_echo":"أيكو (Echo)",
  "lr_xray":"أشعة سينية (X-Ray)",
  "lr_ct":"أشعة مقطعية (CT)",
  "lr_other":"أشعة أخرى",
  "lr_mamo":"ماموغرام",
  "lr_mamo_time":"الماموغرام عبر الأشهر",
  "lr_ct_time":"الأشعة المقطعية عبر الأشهر",
  # ===== الإحالات =====
  "rf_total":"إجمالي الإحالات",
  "rf_received":"الإحالات المستلمة",
  "rf_referrals":"الإحالات",
  "rf_consultations":"الاستشارات",
  "rf_vs_con":"الفرق بين الإحالات والاستشارات",
  "rf_gender_share":"توزيع الإحالات حسب الجنس",
  "rf_boys":"صبيان",
  "rf_girls":"بنات",
  "rf_causes":"أسباب الإحالة",
  "rf_dest":"وجهة الإحالة",
  "rf_beds":"بدون غرف",
  "rf_equip":"بدون معدات",
  "rf_spec":"بدون تخصص",
  "rf_lab":"بدون مختبر",
  "rf_patient":"قرار المريض",
  "rf_rad":"بدون أشعة",
  "rf_d_hosp_sy":"مستشفى بسوريا",
  "rf_d_clinic_sy":"عيادة بسوريا",
  "rf_d_turkey":"تركيا",
  "rf_by_time":"الإحالات المستلمة وأسباب الإحالة شهرياً",
  # ===== قسم الإقامة في المستشفى =====
  "ho_hosp":"عدد حالات الإقامة",
  "ho_icu":"العناية Intensive (ICU)",
  "ho_incub":"الحاضنات",
  "ho_by_age_gender":"أعداد الذكور والإناث حسب الفئة العمرية",
  "ho_gender_split":"نسبة الذكور إلى الإناث",
  "ho_causes":"أسباب الدخول إلى المستشفى",
  "ho_by_time":"حالات الإقامة عبر الزمن",
  "mo_safe_deliveries":"الولادات الآمنة",
  "mo_respiratory":"أمراض الجهاز التنفسي",
  "mo_metabolic":"الأمراض الأيضية",
  "mo_neonatal":"رعاية حديثي الولادة",
  "mo_gi":"أمراض الجهاز الهضمي",
  "mo_wounds":"الجروح والصدمات",
  "mo_genito":"أمراض الجهاز البولي والتناسلي",
  "mo_blood":"الأمراض المتعلقة بالدم",
  "mo_derm":"الأمراض الجلدية",
  # ===== تفصيل أنواع المنشآت =====
  "fac_kinds_title":"تفصيل المنشآت حسب النوع",
  "fac_kinds_sub":"حسب الفلترة الحالية",
  "fac_kind_share":"النسبة",
  "fac_no_data":"بلا بيانات بهذا المجال",
  "f_from_month":"من شهر",
  "f_to_month":"إلى شهر",
  "f_period":"الفترة",
  "cols_label":"الأعمدة",
  "loaded_ok":"تم تحميل الملف بنجاح",
  "no_cols":"الملف ما فيه أعمدة",
  "close":"✖ إغلاق",
  # ===== الفلاتر الستة الرئيسية =====
  "fl_title":"الفلاتر الرئيسية",
  "all":"الكل",
  "f_program":"المنحة",
  "f_governorate":"المحافظة",
  "f_district":"المديرية",
  "f_sub_district":"المنطقة",
  "f_facility_name":"المنشأة",
  "f_date":"الفترة (من تاريخ إلى تاريخ)",
  # ===== نصوص الداشبورد =====
  "pick_a_button":"👆 اختر قسمًا من الأعلى لعرض داشبورده",
  "grand_total":"الإجمالي",
  "matched_cols":"عمود مطابق",
  "all_rows":"كل السجلات",
  "top_groups":"أكبر 15 قياس",
  "over_time":"التقدّم عبر الزمن",
  "top_facilities":"أعلى 10 منشآت",
  "all_cols":"كل الأعمدة",
  "no_values":"لا توجد قيم في الفلتر الحالي",
  "no_rows_match":"لا توجد سجلات تطابق الفلاتر المختارة — وسّع الفترة أو اختر «الكل»",
  # ===== مصدر الداتا =====
  "data_source":"💾 مصدر الداتا",
  "src_upload":"📂 ارفع ملف Excel / CSV (بدّل الداتا يلي كل الداشبوردات بتستعملها)",
  "src_default":"الملف الافتراضي",
  "src_active":"مصدر الداتا الحالي",
  "src_sheet":"الورقة (Sheet)",
  "src_back_default":"رجوع للملف الافتراضي",
  "src_need_cols":"الملف ناقصه الأعمدة التالية، والفلاتر ما رح تشتغل",
  "src_ok":"الأعمدة الستة جاهزة ✅",
  "src_bad":"تعذّر قراءة الملف — تأكد إنه Excel/CSV سليم",
  # ===== داشبورد الاستشارات والمنافع =====
  "k_services":"الخدمات",
  "k_consultations":"الاستشارات",
  "k_beneficiaries":"المنافع",
  "k_curative":"الاستشارات العلاجية",
  "k_new_ben":"المنافع الجديدة",
  "k_avg_serv_ben":"متوسط خدمات/منفعة",
  "bx_by_age_gender":"التقسيم حسب العمر والجنس",
  "bx_cons_age":"الاستشارات — 10 أقسام (5 صبيان + 5 بنات)",
  "bx_ben_age":"المنافع — 10 أقسام (5 صبيان + 5 بنات)",
  "lbl_boys":"صبيان",
  "lbl_girls":"بنات",
  "age_0_4":"0-4",
  "age_5_14":"5-14",
  "age_15_18":"15-18",
  "age_19_49":"19-49",
  "age_50p":"50+",
  "lbl_row_total":"مجموع الصف",
  "lbl_share_note":"النسبة داخل كل خانة = نسبتها من مجموع صفها (ذكور أو إناث)",
 "warn_band_mismatch":"⚠️ عدم تطابق في البيانات: مجموع الشرائح العمرية لا يطابق عمود «الإجمالي» التالي → {x}. الأرقام الإجمالية معروضة من عمود «الإجمالي» الرسمي، ولم يتم تعديل أي تفصيل.",
  "u18":"تحت 18",
  "o18":"فوق 18",
  "f_age":"حسب العمر",
  "rh_consult":"استشارات الصحة الإنجابية",
  "rh_anc":"متابعة الحامل (ANC)",
  "rh_anc2":"ANC 2+",
  "rh_anc4":"ANC 4+",
  "rh_deliv":"الولادات",
  "rh_csect":"قيصرية",
  "rh_normal":"ولادة طبيعية",
  "rh_by_doc":"بإشراف طبيب",
  "rh_by_mwf":"بإشراف قابلة",
  "rh_mda":"وفيات أمومية مُنقاة",
  "rh_pnc_m":"متابعة ما بعد الولادة (الأم)",
  "rh_pnc_u24":"أقل من 24 ساعة",
  "rh_pnc_24p":"24 ساعة فأكثر",
  "rh_pnc_n":"المواليد الجدد",
  "rh_boys":"ذكور",
  "rh_fp":"تنظيم الأسرة",
  "rh_dead":"المواليد الميتة",
  "bx_stls":"الأمراض المنقولة جنسياً (STIs)",
  "ch_deliv_trend":"الولادات شهرياً: طبيعية مقابل قيصرية",
  "ch_anc_trend":"متابعة الحوامل شهرياً",
  "t_total_normal":"إجمالي الولادات الطبيعية",
  "t_total_csec":"إجمالي القيصرية",
  "t_total_anc":"إجمالي ANC",
  "t_anc4":"ANC 4 فأكثر",
  "s_syph":"الزهري",
  "s_chlam":"الكلاميديا",
  "s_aids":"الإيدز",
  "s_gono":"السيلان",
  "s_trich":"التريكومونيايز",
  "s_unspec":"غير محدد",
  "s_stls18p":"STLs فوق 18",
  "s_stls18m":"STLs تحت 18",
  "other_val":"أخرى",
  "by_group":"توزيع المجموعات",
  "by_col":"توزيع الأعمدة",
  "main_group":"المجموعة الرئيسية",
  "top_fac_main":"أعلى المنشآت",
  "g_cols_n":"عمود",
  "sg_minor":"عمليات صغرى",
  "sg_major":"عمليات كبرى",
  "sg_war":"حربية",
  "sg_nowar":"غير حربية",
   "sg_warpct":"نسبةWAR-RELATED",
   # ===== لوحة خدمات الأسنان (g_de) =====
   "de_consultations":"عدد الاستشارات",
   "de_procedures":"عدد الإجراءات",
   "de_svc":"الاستشارات والإجراءات",
   "de_ben_gender":"Dental Beneficiaries · مستفيدو الأسنان حسب الجنس",
   "de_ben_age":"Dental Beneficiaries · مستفيدو الأسنان حسب الجنس والفئة العمرية",
   "de_ben_time":"Dental Ben by Time · مستفيدو الأسنان شهرياً",
   "de_male":"ذكور",
   "de_female":"إناث",
   "de_services_title":"",
  "sg_warpctsub":"من إجمالي العمليات",
  "sg_age_dist":"توزيع الأعمار (الحربية)",
  "sg_age_sub":"ملاحظة: بيانات الأعمار تخص الحالات الحربية",
  "sg_by_gender":"التوزيع حسب الفئة",
  "sg_by_gender_sub":"غير حربية + حربية × ذكور/إناث/أولاد/بنات",
  "sg_monthly":"العمليات شهرياً",
  "sg_4q":"مربع رباعي: حربية / غير حربية × صغرى / كبرى",
  "sg_under5":"أقل من 5 سنوات",
  "sg_5_14":"5 - 14 سنة",
  "sg_15_18":"15 - 18 سنة",
  "sg_19_49":"19 - 49 سنة",
  "sg_50p":"50 سنة فأكثر",
  "sg_male":"ذكور",
  "sg_female":"إناث",
  "sg_boys":"أولاد",
  "sg_girls":"بنات",
  "chw_hh":"زيارات المنازل",
  "chw_hhben":"المستفيدون من الزيارات",
  "chw_reach":"المستفيدون من رسائل التثقيف الصحي",
  "chw_reach4":"مقسّم إلى أربع فئات: ذكور / إناث / أولاد / بنات",
  "chw_iycf":"مستفيدو رسائل IYCF",
  "chw_iycf4":"مقسّم إلى أربع فئات: ذكور / إناث / أولاد / بنات",
  "chw_screen":"الفحص المجتمعي لسوء التغذية",
  "chw_cu5m":"CU5 ذكور",
  "chw_cu5f":"CU5 إناث",
  "chw_plws":"الحوامل والمرضعات PLWS",
  "chw_cu5n":"عدد المفحوصين CU5",
  "chw_sammam":"نسبة SAM و MAM",
  "chw_case_ratio":"نسبة حالات سوء التغذية إلى المفحوصين",
  "chw_ref":"عدد التحويلات (Referrals) من العامل الصحي",
  "chw_reach_t":"المستفيدون من التثقيف الصحي عبر الزمن",
  "chw_sam_t":"حالات SAM و MAM عبر الزمن",
  "hhs_status":"حالة التنفيذ",
  "hhs_custom":"مخصّص",
  "hhs_generic":"عام",
  "hhs_has_data":"به داتا",
  "hhs_no_data":"بدون داتا",
  "s_sam":"SAM (شديد)",
  "s_mam":"MAM (متوسط)",
  "s_ok":"سليم / بدون سوء تغذية",
  "ch_gender":"التوزيع حسب الجنس",
  "ch_host_idp":"التوزيع حسب المضيف والنازح",
  "p_host":"المضيف (Host)",
  "p_idp":"النازحون (IDP)",
  "bx_pwd":"الأشخاص ذوو الإعاقة",
  "pwd_boys":"ذكور الأطفال",
  "pwd_men":"ذكور البالغين",
  "pwd_girls":"إناث الأطفال",
  "pwd_women":"إناث البالغات",
  "bx_amput":"بتر الأطراف",
  "amput_lower":"بتر الأطراف السفلية",
  "amput_upper":"بتر الأطراف العلوية",
  "ch_timeline":"التطوّر الشهري: الاستشارات مقابل عدد المنشآت",
  "lbl_fac_count":"عدد المنشآت",
  "btn_back_sections":"رجوع للأقسام",
  "switch_dash":"بدّل الداشبورد",
  # --- العناوين والأزرار الرئيسية ---
  "saved_grants":"المنح المحفوظة",
  "btn_new_grant":"➕ منحة جديدة",
  # --- CRM ---
  "btn_crm":"🤝 CRM",
  "crm_title":"🤝 CRM — قاعدة بيانات قابلة للتعديل",
  "crm_hint":"اختر جدول محفوظ، أو ارفع ملف، أو ابدأ جدول جديد. عدّل الخانات مباشرة واحفظ — التعديلات بتضل محفوظة مع الوقت.",
  "crm_saved":"الجداول المحفوظة",
  "crm_tables":"جدول",
  "crm_load":"📂 فتح",
  "crm_newbtn":"➕ جدول جديد",
  "crm_del":"🗑 حذف",
  "crm_del_ok":"تم حذف الجدول: {x}",
  "crm_upload":"ارفع ملف (xlsx / csv) لإنشاء أو استبدال جدول",
  "crm_upsave":"اسم الجدول المحفوظ",
  "crm_upsave_ph":"مثال: crm_contacts",
  "crm_import":"⬆️ استيراد للمحرّر",
  "crm_name":"اسم الجدول",
  "crm_name_ph":"مثال: crm_contacts",
  "crm_cols":"أعمدة الجدول (افصل بفاصلة)",
  "crm_cols_ph":"الاسم، الجوال، المنطقة، الملاحظات",
  "crm_create":"إنشاء الجدول",
  "crm_editor":"المحرّر",
  "crm_rows":"عدد الصفوف",
  "crm_save":"💾 حفظ التغييرات",
  "crm_saved_ok":"تم الحفظ في: {x}.csv",
  "crm_export":"⬇️ تنزيل Excel",
  "crm_empty":"لا يوجد جدول محرّر — افتح جدول محفوظ أو أنشئ جدول جديد.",
  "crm_need_name":"اكتب اسم الجدول.",
  "crm_need_cols":"حدّد عمود واحد على الأقل.",
  "crm_loaded":"تم فتح الجدول: {x}",
  "crm_addcol":"➕ عمود",
  "crm_tab_edit":"المحرّر",
  "crm_tab_dash":"الداشبورد",
  "crm_view":"العرض",
  "crm_imported":"تم استيراد الملف",
  "crm_dash_cur":"الجدول الحالي",
  "crm_dash_norows":"الجدول فارغ — أضف صفوفاً من تبويب «المحرّر» ثم احفظ.",
  "crm_dash_cols_tbl":"نظرة على الأعمدة",
  "crm_col":"العمود",
  "crm_type":"النوع",
  "crm_num":"رقمي",
  "crm_txt":"نصي",
  "crm_nonempty":"قيم غير فارغة",
  "crm_unique":"قيم فريدة",
  "crm_topval":"القيمة الأكثر تكراراً",
  "crm_topcount":"عددها",
  "crm_preview":"معاينة البيانات",
  "crm_channel":"قناة استقبال الشكوى",
  "crm_priority":"الأولوية",
  "crm_status":"الحالة الحالية",
  "crm_category":"تصنيف الشكوى",
  "crm_gov":"المحافظة",
  "crm_gov_out":"خارج سوريا",
  "crm_res15":"الحل خلال 15 يوم",
  "crm_gender":"الجنس",
  "crm_complainer":"نوع المُشتكي",
  "crm_avg_filter":"حسب المعدّل",
  "crm_avg_all":"كل الأيام",
  "crm_avg_above":"أعلى من المعدّل",
  "crm_avg_equal":"يساوي",
  "crm_avg_below":"أقل من المعدّل",
  "crm_days":"عدد الأيام",
  "crm_count":"العدد",
  "crm_with_dates":"مع تاريخ حل",
  "crm_period":"الفترة الزمنية",
  "crm_filter":"فلترة",
  "crm_filter_id":"رقم الشكوى (ID)",
  "crm_filter_id_ph":"مثال: 4543",
  "crm_filter_id_from":"من رقم الشكوى (ID)",
  "crm_filter_id_to":"إلى رقم الشكوى (ID)",
  "crm_filter_from":"من تاريخ",
  "crm_filter_to":"إلى تاريخ",
  "crm_filter_gantt":"فلترة الرسم الزمني (غانت)",
  "crm_no_match":"لا توجد نتائج مطابقة للفلتر.",
  "crm_dash_distr_hdr":"توزيع القيم حسب الأعمدة",
  "crm_need_data":"لا يوجد جدول — افتح جدولاً أو أنشئ واحداً أولاً.",
  "crm_dash_kpi":"ملخّص الجدول",
  "crm_dash_rows":"عدد الصفوف",
  "crm_dash_cols":"عدد الأعمدة",
  "crm_dash_filled":"نسبة التعبئة",
  "crm_dash_numcol":"أعمدة رقمية",
  "crm_dash_numeric":"ملخّص الأعمدة الرقمية",
  "crm_dash_numeric_n":"مجموع · متوسط · أعلى",
  "crm_dash_nonum":"لا توجد أعمدة رقمية في هذا الجدول.",
  "crm_dash_reset":"إعادة ضبط",
  "crm_dash_dist":"توزيع القيم —",
  "crm_dash_by":"حسب",
  "crm_sum":"المجموع",
  "crm_avg":"المتوسط",
  "crm_max":"الأعلى",
  "crm_min":"الأدنى",
  "crm_kpi_title":"مؤشرات أساسية",
  "crm_kpi_note":"متوسط · أدنى · أعلى",
  "crm_days_left":"متوسط الأيام المتبقية لإغلاق الشكوى",
  "crm_days_unit":"يوم",
  "crm_satisfaction":"الرضا عن استجابة SAMS",
  "crm_not_specified":"غير محدّد",
  "btn_resume":"▶️ متابعة آخر عمل",
  "btn_clear":"🗑 مسح وتجاهل",
  "btn_add_ind":"➕ إضافة مؤشر",
  "btn_edit":"🔄 عدّل الإعداد",
  "btn_save":"💾 حفظ",
  "btn_home2":"🏠 الرئيسية",
  "last_work":"آخر عمل مفتوح",
  "status_done":"مكتمل",
  "status_draft":"مسودة",
  "ach_ratio":"نسبة الإنجاز",
  "can_continue":"يمكنك متابعة آخر عمل محفوظ — بحفظ تلقائي",
  "value_lbl":"القيمة",
  "n_ind":"عدد المؤشرات",
  "monitor":"متابعة المؤشرات",
  "filter_before":"فلترة البيانات (قبل العرض):",
  "target_mode":"نوع الهدف والنسبة المحققة",
  "pct_mode_pct":"نسبة مئوية %",
  "pct_mode_num":"رقم (الهدف هو الأصل 100)",
 },
"en":{
   "tr_trauma":"Trauma consultations",
   "tr_war":"War related",
   "tr_nonwar":"Non-war related",
   "tr_male":"Male",
   "tr_female":"Female",
   "tr_age_gender":"Females and males by age group",
   "tr_war_pct":"War-related share of trauma consultations",
   "tr_by_time":"Trauma consultations and war related, monthly",
   "f_month":"By month",
   # ===== GI Scope =====
   "gi_total":"Total GI scope",
   "gi_ages":"Age groups",
   "gi_upper_lower":"Upper vs lower",
   "gi_upper":"Upper GI scope",
   "gi_lower":"Lower GI scope",
   "gi_by_fac":"GI scope by facility",
   "gi_section":"Section",
   "gi_totals":"GI scope totals by section",
   "gi_total_all":"Grand total",
   "gi_by_time":"GI scope by time",
   # ===== Lab & Radiology =====
   "lr_lab":"Total lab tests",
   "lr_rad":"Total radiology",
   "lr_ref_lab":"Referrals caused by lab",
   "lr_ref_rad":"Referrals caused by radiology",
   "lr_rad_parts":"Radiology sections",
   "lr_echo":"Echo",
   "lr_xray":"X-Ray",
   "lr_ct":"CT scan",
   "lr_other":"Other radiology",
   "lr_mamo":"Mammography",
   "lr_mamo_time":"Mammography by time",
   "lr_ct_time":"CT scan by time",
   # ===== Referrals =====
   "rf_total":"Total referrals",
   "rf_received":"Received referrals",
   "rf_referrals":"Referrals",
   "rf_consultations":"Consultations",
   "rf_vs_con":"Referrals compared with consultations",
   "rf_gender_share":"Referrals by gender",
   "rf_boys":"Boys",
   "rf_girls":"Girls",
   "rf_causes":"Cause of referral",
   "rf_dest":"Referral destination",
   "rf_beds":"No beds",
   "rf_equip":"No equipment",
   "rf_spec":"No speciality",
   "rf_lab":"No lab",
   "rf_patient":"Patient decision",
   "rf_rad":"No radiology",
   "rf_d_hosp_sy":"Hospital in Syria",
   "rf_d_clinic_sy":"Clinic in Syria",
   "rf_d_turkey":"Turkey",
   "rf_by_time":"Received referrals and causes of referral, monthly",
   # ===== قسم الإقامة في المستشفى =====
   "ho_hosp":"Hospitalizations",
   "ho_icu":"ICU",
   "ho_incub":"Incubators",
   "ho_by_age_gender":"Male and female by age group",
   "ho_gender_split":"Male vs female share",
   "ho_causes":"Admission causes",
   "ho_by_time":"Hospitalizations over time",
   "mo_safe_deliveries":"Safe deliveries",
   "mo_respiratory":"Respiratory diseases",
   "mo_metabolic":"Metabolic diseases",
   "mo_neonatal":"Neonatal care",
   "mo_gi":"GI diseases",
   "mo_wounds":"Wounds and traumas",
   "mo_genito":"Genitourinary tract diseases",
   "mo_blood":"Blood related diseases",
   "mo_derm":"Dermatologic diseases",
   "btn_hhs":"🏥 Health Services Dashboard",
  "hhs_title":"Health Services Dashboard",
  "hhs_sub":"Choose the section you want to open",
  "sec_general":"General Analysis",
  "sec_flashcards":"Information Flashcards",
  "sec_specialized":"Specialized Services",
  "sec_morbidity":"Morbidities and Mortalities",
  "sec_other":"Other",
  "btn_back":"⬅ Back",
  "btn_home":"🏠 Home",
  "btn_lang":"🌐 العربية",
  "coming_soon":"Coming soon",
  "no_items":"No items yet — add them in SECTIONS in the code",
  # ===== General Analysis (12 sections) =====
  "g_cb":"Consultations and BEN",
  "g_rh":"Reproductive Health",
  "g_sg":"Surgeries",
  "g_chw":"Community Health Workers",
  "g_de":"Dental Services",
  "g_tr":"Traumas",
  "g_ho":"Hospitalization",
  "g_rf":"Referrals",
  "g_lr":"Lab and Radiology",
  "g_gi":"GI Scope",
  "g_rd":"Reported Disabilities",
  "g_da":"Drugs Availability",
  # ===== Information Flashcards =====
  "f_inf":"Information (INF)",
  # ===== Specialized Services (6 buttons) =====
  "s_mh":"Mental Health",
  "s_bb":"Blood Bank",
  "s_icu":"ICU & Incubators",
  "s_dl":"Dialysis",
  "s_on":"Oncology",
  "s_pt":"Physiotherapy",
  # ===== Morbidities and Mortalities =====
  "m_mb":"Morbidities",
  # ===== Other (3 buttons) =====
  "o_pop":"Population",
  "o_ca":"Catchment Area",
  "o_er":"ER Report 2026",
  # ===== Data page =====
  "data_title":"Data: ",
  "upload_label":"📂 Upload your Excel file here",
  "upload_help":"Supported files: xlsx / xls / csv",
  "no_file":"No file uploaded yet",
  "rows_label":"Rows",
  # ===== Facility type breakdown =====
  "fac_kinds_title":"Facilities by type",
  "fac_kinds_sub":"Based on current filter",
  "fac_kind_share":"Share",
  "fac_no_data":"No data in this domain",
  "f_from_month":"From month",
  "f_to_month":"To month",
  "f_period":"Period",
  "cols_label":"Columns",
  "loaded_ok":"File loaded successfully",
  "no_cols":"The file has no columns",
  "close":"✖ Close",
  # ===== The six main filters =====
  "fl_title":"Main Filters",
  "all":"All",
  "f_program":"Grant",
  "f_governorate":"Governorate",
  "f_district":"District",
  "f_sub_district":"Sub-district",
  "f_facility_name":"Facility Name",
  "f_date":"Period (from date to date)",
  # ===== Dashboard labels =====
  "pick_a_button":"👆 Pick a section above to see its dashboard",
  "grand_total":"Grand Total",
  "matched_cols":"Matched columns",
  "all_rows":"All rows",
  "top_groups":"Top 15 measures",
  "over_time":"Progress over time",
  "top_facilities":"Top 10 facilities",
  "all_cols":"All columns",
  "no_values":"No values in the current filter",
  "no_rows_match":"No rows match the selected filters — widen the period or choose \"All\"",
  # ===== Data source =====
  "data_source":"💾 Data Source",
  "src_upload":"📂 Upload an Excel / CSV file (replaces the data every dashboard uses)",
  "src_default":"Default file",
  "src_active":"Active data source",
  "src_sheet":"Sheet",
  "src_back_default":"Back to default file",
  "src_need_cols":"The file is missing these columns, so the filters will not work",
  "src_ok":"The six required columns are present ✅",
  "src_bad":"Could not read the file — make sure it is a valid Excel/CSV",
  # ===== Consultations & Beneficiaries dashboard =====
  "k_services":"Services",
  "k_consultations":"Consultations",
  "k_beneficiaries":"Beneficiaries",
  "k_curative":"Curative consultations",
  "k_new_ben":"New beneficiaries",
  "k_avg_serv_ben":"Average of services / beneficiaries",
  "bx_by_age_gender":"Breakdown by age and gender",
  "bx_cons_age":"Consultations — 10 groups (5 boys + 5 girls)",
  "bx_ben_age":"Beneficiaries — 10 groups (5 boys + 5 girls)",
  "lbl_boys":"Boys",
  "lbl_girls":"Girls",
  "age_0_4":"0-4",
  "age_5_14":"5-14",
  "age_15_18":"15-18",
  "age_19_49":"19-49",
  "age_50p":"50+",
  "lbl_row_total":"Row total",
  "lbl_share_note":"Each cell % = its share of its own row total (boys or girls)",
 "warn_band_mismatch":"⚠️ Source data mismatch: the age-band detail does not add up to the official Total column → {x}. Totals shown come from the official Total column; no detail was altered.",
  "u18":"Under 18",
  "o18":"Over 18",
  "f_age":"By age",
  "rh_consult":"RH consultations",
  "rh_anc":"Antenatal care (ANC)",
  "rh_anc2":"ANC 2+",
  "rh_anc4":"ANC 4+",
  "rh_deliv":"Deliveries",
  "rh_csect":"C-sections",
  "rh_normal":"Normal delivery",
  "rh_by_doc":"By doctor",
  "rh_by_mwf":"By midwife",
  "rh_mda":"Maternal deaths averted",
  "rh_pnc_m":"Postnatal care (mothers)",
  "rh_pnc_u24":"Under 24 hours",
  "rh_pnc_24p":"24 hours and above",
  "rh_pnc_n":"Newborns",
  "rh_boys":"Boys",
  "rh_fp":"Family planning",
  "rh_dead":"Dead births",
  "bx_stls":"Sexually transmitted infections (STIs)",
  "ch_deliv_trend":"Deliveries by month: normal vs C-sections",
  "ch_anc_trend":"Antenatal care by month",
  "t_total_normal":"Total normal deliveries",
  "t_total_csec":"Total C-sections",
  "t_total_anc":"Total ANCs",
  "t_anc4":"ANC 4 and above",
  "s_syph":"Syphilis",
  "s_chlam":"Chlamydia",
  "s_aids":"AIDS",
  "s_gono":"Gonococcal",
  "s_trich":"Trichomoniasis",
  "s_unspec":"Unspecified",
  "s_stls18p":"STLs over 18",
  "s_stls18m":"STLs under 18",
  "other_val":"Other",
  "by_group":"Distribution by group",
  "by_col":"Distribution by column",
  "main_group":"Main group",
  "top_fac_main":"Top facilities",
  "g_cols_n":"columns",
  "sg_minor":"Minor surgeries",
  "sg_major":"Major surgeries",
  "sg_war":"War related",
  "sg_nowar":"Non-war related",
   "sg_warpct":"WAR-RELATED SHARE",
   # ===== Dental Services dashboard (g_de) =====
   "de_consultations":"Dental Consultations",
   "de_procedures":"Dental Procedures",
   "de_svc":"Consultations & Procedures",
   "de_ben_gender":"Dental Beneficiaries \u00b7 by Gender",
   "de_ben_age":"Dental Beneficiaries \u00b7 by Gender & Age Group",
   "de_ben_time":"Dental Ben by Time \u00b7 Monthly",
   "de_male":"Males",
   "de_female":"Females",
   "de_services_title":"",
  "sg_warpctsub":"of total surgeries",
  "sg_age_dist":"Age distribution (war related)",
  "sg_age_sub":"Note: age data covers war-related cases",
  "sg_by_gender":"Distribution by group",
  "sg_by_gender_sub":"Non-war + war related x men / women / boys / girls",
  "sg_monthly":"Surgeries per month",
  "sg_4q":"Four-way split: war / non-war x minor / major",
  "sg_under5":"Under 5 years",
  "sg_5_14":"5 - 14 years",
  "sg_15_18":"15 - 18 years",
  "sg_19_49":"19 - 49 years",
  "sg_50p":"50 years and above",
  "sg_male":"Men",
  "sg_female":"Women",
  "sg_boys":"Boys",
  "sg_girls":"Girls",
  "chw_hh":"Household visits",
  "chw_hhben":"Beneficiaries from visits",
  "chw_reach":"People reached through health education messages",
  "chw_reach4":"Split into four groups: men / women / boys / girls",
  "chw_iycf":"People reached through IYCF messages",
  "chw_iycf4":"Split into four groups: men / women / boys / girls",
  "chw_screen":"Community screening for malnutrition",
  "chw_cu5m":"CU5 Male",
  "chw_cu5f":"CU5 Female",
  "chw_plws":"Pregnant and lactating women (PLWS)",
  "chw_cu5n":"Total CU5 screened",
  "chw_sammam":"SAM and MAM share",
  "chw_case_ratio":"Malnutrition cases / screened",
  "chw_ref":"Referrals by community health worker",
  "chw_reach_t":"People reached over time",
  "chw_sam_t":"SAM and MAM cases over time",
  "hhs_status":"Status",
  "hhs_custom":"Custom",
  "hhs_generic":"Generic",
  "hhs_has_data":"Has data",
  "hhs_no_data":"No data",
  "s_sam":"SAM (severe)",
  "s_mam":"MAM (moderate)",
  "s_ok":"Normal / not malnourished",
  "ch_gender":"Distribution by gender",
  "ch_host_idp":"Distribution by host and IDP",
  "p_host":"Host",
  "p_idp":"IDPs",
  "bx_pwd":"People with disabilities",
  "pwd_boys":"Boys",
  "pwd_men":"Men",
  "pwd_girls":"Girls",
  "pwd_women":"Women",
  "bx_amput":"Limb amputations",
  "amput_lower":"Lower limb amputations",
  "amput_upper":"Upper limb amputations",
  "ch_timeline":"Monthly trend: consultations vs number of facilities",
  "lbl_fac_count":"Number of facilities",
  "btn_back_sections":"Back to sections",
  "switch_dash":"Switch dashboard",
  "saved_grants":"Saved Grants",
  "btn_new_grant":"➕ New Grant",
  # --- CRM ---
  "btn_crm":"🤝 CRM",
  "crm_title":"🤝 CRM — Editable database",
  "crm_hint":"Pick a saved table, upload a file, or start a new table. Edit cells directly and save — changes persist over time.",
  "crm_saved":"Saved tables",
  "crm_tables":"table(s)",
  "crm_load":"📂 Open",
  "crm_newbtn":"➕ New table",
  "crm_del":"🗑 Delete",
  "crm_del_ok":"Deleted table: {x}",
  "crm_upload":"Upload a file (xlsx / csv) to create or replace a table",
  "crm_upsave":"Saved table name",
  "crm_upsave_ph":"e.g. crm_contacts",
  "crm_import":"⬆️ Import to editor",
  "crm_name":"Table name",
  "crm_name_ph":"e.g. crm_contacts",
  "crm_cols":"Table columns (comma-separated)",
  "crm_cols_ph":"name, phone, area, notes",
  "crm_create":"Create table",
  "crm_editor":"Editor",
  "crm_rows":"rows",
  "crm_save":"💾 Save changes",
  "crm_saved_ok":"Saved to: {x}.csv",
  "crm_export":"⬇️ Download Excel",
  "crm_empty":"No table in the editor — open a saved table or create a new one.",
  "crm_need_name":"Enter the table name.",
  "crm_need_cols":"Define at least one column.",
  "crm_loaded":"Opened table: {x}",
  "crm_addcol":"➕ Column",
  "crm_tab_edit":"Editor",
  "crm_tab_dash":"Dashboard",
  "crm_view":"View",
  "crm_imported":"File imported",
  "crm_dash_cur":"Current table",
  "crm_dash_norows":"Table is empty — add rows in the Editor tab, then save.",
  "crm_dash_cols_tbl":"Columns overview",
  "crm_col":"Column",
  "crm_type":"Type",
  "crm_num":"Numeric",
  "crm_txt":"Text",
  "crm_nonempty":"Non-empty",
  "crm_unique":"Unique",
  "crm_topval":"Top value",
  "crm_topcount":"Count",
  "crm_preview":"Data preview",
  "crm_channel":"Complaint input channel",
  "crm_priority":"Priority",
  "crm_status":"Current Status",
  "crm_category":"Complaint Category",
  "crm_gov":"Governorate",
  "crm_gov_out":"Outside Syria",
  "crm_res15":"Resolved within 15 days",
  "crm_gender":"Gender",
  "crm_complainer":"Complainer Type",
  "crm_avg_filter":"By average",
  "crm_avg_all":"All days",
  "crm_avg_above":"Above average",
  "crm_avg_equal":"Equals",
  "crm_avg_below":"Below average",
  "crm_days":"Days",
  "crm_count":"Count",
  "crm_with_dates":"with resolution date",
  "crm_period":"Time period",
  "crm_filter":"Filter",
  "crm_filter_id":"Complaint ID",
  "crm_filter_id_ph":"e.g. 4543",
  "crm_filter_id_from":"From ID",
  "crm_filter_id_to":"To ID",
  "crm_filter_from":"From date",
  "crm_filter_to":"To date",
  "crm_filter_gantt":"Gantt filter",
  "crm_no_match":"No rows match the filter.",
  "crm_dash_distr_hdr":"Value distribution by column",
  "crm_need_data":"No table — open or create one first.",
  "crm_dash_kpi":"Table summary",
  "crm_dash_rows":"Rows",
  "crm_dash_cols":"Columns",
  "crm_dash_filled":"Filled",
  "crm_dash_numcol":"Numeric columns",
  "crm_dash_numeric":"Numeric columns summary",
  "crm_dash_numeric_n":"Sum · Average · Max",
  "crm_dash_nonum":"No numeric columns in this table.",
  "crm_dash_reset":"Reset",
  "crm_dash_dist":"Value distribution —",
  "crm_dash_by":"by",
  "crm_sum":"Sum",
  "crm_avg":"Avg",
  "crm_max":"Max",
  "crm_min":"Min",
  "crm_kpi_title":"Key indicators",
  "crm_kpi_note":"Average · Min · Max",
  "crm_days_left":"Average of days left to close the complaint",
  "crm_days_unit":"days",
  "crm_satisfaction":"Satisfaction about SAMS response",
  "crm_not_specified":"Not specified",
  "btn_resume":"▶️ Resume Last Work",
  "btn_clear":"🗑 Clear and Ignore",
  "btn_add_ind":"➕ Add Indicator",
  "btn_edit":"🔄 Edit Setup",
  "btn_save":"💾 Save",
  "btn_home2":"🏠 Home",
  "last_work":"Last Open Work",
  "status_done":"Complete",
  "status_draft":"Draft",
  "ach_ratio":"Achievement",
  "can_continue":"You can continue your last saved work — autosaved",
  "value_lbl":"Value",
  "n_ind":"Indicators",
  "monitor":"Indicator Tracking",
  "filter_before":"Filter data (before display):",
  "target_mode":"Target type and achieved ratio",
  "pct_mode_pct":"Percentage %",
  "pct_mode_num":"Number (target is the base 100)",
 },
}

# اللغة الحالية (تُضبط من زر التبديل) — نحفظها في session_state فقط
if "lang" not in st.session_state: st.session_state["lang"]="ar"

def T(key):
    # ترجمة مفتاح حسب اللغة الحالية؛ اللغة الأساسية إنجليزية.
    # إذا المفتاح ناقص بلغة الشاشات بنرجّعه من الإنجليزية، وبعدها من العربية، وبعدها المفتاح نفسه.
    lang=st.session_state.get("lang","en")
    _d=UI.get(lang,{})
    if key in _d: return _d[key]
    return UI.get("en",{}).get(key, UI.get("ar",{}).get(key,key))

def _L(ar,en):
    """نص مباشر بلغتين بدون قاموس UI — للعناصر الجديدة (الدخول، الصفحة الرئيسية)."""
    return ar if st.session_state.get("lang","en")=="ar" else en

# =============================================================================
# ===== أقسام «لوحة خدمات الصحة» =====
# كل قسم: (المفتاح، الأيقونة، عنوانه). وكل زر داخله: (المفتاح، الأيقونة).
# الضغط على أي زر ينقله إلى صفحة البيانات (hhs) مع اسم القسم في العنوان.
# لإضافة زر: سطر واحد هنا + نصّه في القاموس UI (عربي وإنجليزي).
# =============================================================================
SECTIONS=[
 ("general","📊","sec_general",[
   ("g_cb","🩺"),   # consultations and ben
   ("g_rh","🤰"),   # reproductive health
   ("g_sg","🔪"),   # surgeries
   ("g_chw","🏠"),  # chw
   ("g_de","🦷"),   # dental services
   ("g_tr","🩹"),   # traumas
   ("g_ho","🏥"),   # hospitalization
   ("g_rf","↪️"),   # referrals
   ("g_lr","🧪"),   # lab and rad
   ("g_gi","🔎"),   # gi scope
   ("g_rd","♿"),    # reported disabilities
   ("g_da","💊"),   # drugs availability
 ]),
 ("flashcards","🗂️","sec_flashcards",[
   ("f_inf","ℹ️"),  # inf — like the other buttons
 ]),
 ("specialized","🧰","sec_specialized",[
   ("s_mh","🧠"),   # mental health
   ("s_bb","🩸"),   # blood bank
   ("s_icu","🏥"),  # icu & incubators
   ("s_dl","🫘"),   # dialysis
   ("s_on","🎗️"),  # oncology
   ("s_pt","🏋️"),  # physiotherapy
 ]),
 ("morbidity","🩺","sec_morbidity",[
   ("m_mb","📋"),   # morbidities
 ]),
 ("other","📦","sec_other",[
   ("o_pop","👥"),  # population
   ("o_ca","🗺️"),  # catchment area
   ("o_er","🚨"),   # er 2026
 ]),
]

# =============================================================================
# ===== مصدر البيانات المشترك: ملف واحد يغذّي كل الداشبوردات =====
# الملف: 972 سجل × 509 عمود. أول 8 أعمدة أبعاد (Date, Project ID, Program,
# Governorate, District, Sub-district, Community, Facility Name) والباقي 501 مقياس.
# ملاحظة مهمة: 68 اسم عمود فيه مسافات زائدة، لذلك ننظّف الأسماء عند القراءة.
# =============================================================================
# الملف صار جوّه مجلد المشروع (SAMS DASHBOARD) حتى يكون كل شيء بمكان واحد
# ومحمول: يشتغل من أي جهاز بدون أي مسار خاص بالمستخدم.
_APP_DIR=os.path.dirname(os.path.abspath(__file__))
# ===== التخزين الخاص: البيانات الحسّاسة داخل .sams_private/ (مستثنى من Git) =====
# الأولوية: ملف الأدمن المحفوظ محلياً ← الملف الافتراضي بجذر المشروع.
# الملف الافتراضي أيضاً مستثنى في .gitignore، فلا تُرفع أي بيانات على GitHub.
_PRIV_DIR=meal.PRIVATE_DIR
_PRIV_DATA=meal.DATA_PRIVATE
DATA_FILE=_PRIV_DATA if os.path.exists(_PRIV_DATA) else os.path.join(_APP_DIR,"Basic and Final Update june 2026.xlsx")
if not os.path.exists(DATA_FILE):   # احتياط: أول ملف xlsx جوّه المجلد (غير جداول CRM)
    for _f in sorted(os.listdir(_APP_DIR)):
        if _f.lower().endswith((".xlsx",".xls")) and "crm" not in _f.lower():
            DATA_FILE=os.path.join(_APP_DIR,_f); break
DATA_SHEET="Commulative Semi 2022"
# ===== CRM: مجلد الجداول المحفوظة (ملفات CSV قابلة للتعديل مع الوقت) =====
CRM_DIR=os.path.join(_APP_DIR,"crm")
os.makedirs(CRM_DIR,exist_ok=True)
def _crm_safe(n):
    # اسم ملف آمن (بيسمح بالعربي) بدون رموز خطرة
    n=re.sub(r"[^\w\u0600-\u06FF\- ]+","",str(n or "")).strip()
    return n or "crm_table"
def _crm_path(n):
    return os.path.join(CRM_DIR,_crm_safe(n)+".csv")
def _crm_names():
    return sorted(os.path.splitext(os.path.basename(x))[0]
                  for x in glob.glob(os.path.join(CRM_DIR,"*.csv")))
def _crm_load(n):
    try:
        return pd.read_csv(_crm_path(n),dtype=str).fillna("")
    except Exception:
        return pd.DataFrame()
def _crm_save(n,d):
    d=d.fillna("").astype(str)
    d.to_csv(_crm_path(n),index=False,encoding="utf-8-sig")
    return _crm_safe(n)
# الأبعاد الخمسة للفلاتر النقطية + التاريخ = 6 فلاتر رئيسية لكل الداشبوردات
DIMS=["Program","Governorate","District","Sub-district","Facility Name"]
DIMS6=DIMS+["Date"]
# ===== السنة الافتراضية لفلتر «الفترة» في Main Filters =====
# مو ثابتة: بتتقرأ من الداتا نفسها. غيّر الرقم فقط لما تبغي سنة ثانية،
# وإذا ما موجودة بالسنة المختارة بيرجع تلقائيًا لكل المدة المتوفرة بالداتا.
DEFAULT_FILTER_YEAR=2026

# =============================================================================
# ===== توحيد أسماء الأبعاد: كل اسم 공식 موجود مرة واحدة فقط ================
# ملف المصدر كان فيه 17 اسم مختلفة لـ 14 محافظة سورية، مثل:
#   Idleb/Idelb · Ar-Raqqa/Raqaa/Raqqa · Al-Hasakeh/Hasakah/Hasaka
#   Lataakia/Latakia/Lattakia
# المديرية فيه تكرار أيضاً: Idleb/idleb/Idelb, Harem/Harim, Sa’sa’/Sa'sa# الحل: نوحّدهم على الاسم الرسمي الموحّد وقت تحميل أي ملف، فالفلتر
# بطلع 14 محافظة بدل 17، وكل صف بيتحسب ضمن محافظته/مديريته الصحيحة.
# ملاحظة: عم نطبّع الاسم ما بندمج أي اسم حقيقي بين محافظتين مختلفتين.
# =============================================================================
GOV_CANON={
    # ===== المكرر في الملف -> الاسم الرسمي =====
    "idelb":"Idleb","idlib":"Idleb","edleb":"Idleb","idleib":"Idleb",
    "raqaa":"Raqqa","ar raqqa":"Raqqa","al raqqa":"Raqqa","al ar raqqa":"Raqqa",
    "hasaka":"Hasakah","hasakeh":"Hasakah","hassakah":"Hasakah",
    "al hasakeh":"Hasakah","al hasakah":"Hasakah","al hassakah":"Hasakah",
    "lataakia":"Latakia","lattakia":"Latakia","al lattakia":"Latakia",
    # ===== باقي المحافظات الـ14 (لو ظهرت مستقبلاً) =====
    "aleppo":"Aleppo","alabppo":"Aleppo",
    "daraa":"Daraa","dara":"Daraa",
    "deir ezzor":"Deir Ezzor","deir al zor":"Deir Ezzor",
    "hama":"Hama","hamaa":"Hama",
    "sweida":"Sweida","as suwayda":"Sweida","suwayda":"Sweida",
    "rural damascus":"Rural Damascus","rif dimashq":"Rural Damascus",
    "damascus":"Damascus",
    "tartus":"Tartus","tartous":"Tartus",
    "quneitra":"Quneitra",
    "homs":"Homs",
    # ===== بالعربي (بعد توحيد الحروف: أ/إ/آ→ا ، ة→ه ، ى→ي) =====
    "حلب":"Aleppo","دمشق":"Damascus","ريف دمشق":"Rural Damascus","ريف دمشق":"Rural Damascus",
    "درعا":"Daraa","دير الزور":"Deir Ezzor","حماة":"Hama","حمص":"Homs",
    "الحسكة":"Hasakah","حسكة":"Hasakah","ادلب":"Idleb","لاذقيه":"Latakia","اللاذقية":"Latakia",
    "القنيطره":"Quneitra","رقه":"Raqqa","سويداء":"Sweida","طرطوس":"Tartus",
}

# المديرية: نفس منطق التوحيد (تم التحقق: ولا اسم مديرية حقيقي بين محافظتين)
DIST_CANON={
    "idelb":"Idleb","idlib":"Idleb","idleb":"Idleb",
    "lataakia":"Latakia","lattakia":"Latakia",
    "hasaka":"Hasakah","hasakeh":"Hasakah",
    "harem":"Harim","harm":"Harim",          # Harem/Harim/Harm = Directorate واحدة
    "al bab":"Al Bab","ras al ain":"Ras Al Ain","al ain":"Ras Al Ain",
    "al qalamoun":"Al-Qalamoun","qalamoun":"Al-Qalamoun",
    "maarret mesrin":"Maarret Mesrin","maarret al mesrin":"Maarret Mesrin",
    "deir ezzor":"Deir Ezzor","rural damascus":"Rural Damascus","aleppo":"Aleppo",
    "tal abied":"Tal- Abied","daraa":"Daraa","hama":"Hama","sweida":"Sweida","raqqa":"Raqqa",
}

# المنطقة (Sub-district)
SUB_CANON={
    "sasa":"Sa'sa","sa sa":"Sa'sa",               # Sa’sa’ / Sa'sa / sasa
    "idelb":"Idleb","idlib":"Idleb","idleb":"Idleb",
    "lataakia":"Latakia","lattakia":"Latakia","hasaka":"Hasakah","hasakeh":"Hasakah",
    "harem":"Harim","harm":"Harim","tal abied":"Tal- Abied",
    "al qalamoun":"Al-Qalamoun","maarret mesrin":"Maarret Mesrin","deir ezzor":"Deir Ezzor",
}

# البرنامج: الموحّد مع إبقاء أرقام المنح مختلفة (MOFA / MOFA 7 / MOFA 8)
PROG_CANON={
    "un unfpa":"UNFPA","unfpa":"UNFPA",
    "wv gffo":"WV-GFFO","wv gffo ii":"WV-GFFO-II","wv gffo 2":"WV-GFFO-II",
    "mofa":"MOFA","mofa 7":"MOFA 7","mofa 8":"MOFA 8",
    "prirvit fund":"Private Fund","gffo irc":"GFFO/IRC",
}

_AR_PREFIX=("al ","ar ","el ","ad ","as ","ash ")
_AR_SUFFIX=("governorate","muhafaza","muhafazat","directorate","sub district")

def _canon_key(v):
    """مفتاح موحّد للمقارنة: تشكيل وطويل وعلامات ترقيم وحروف عربية موحّدة"""
    s=unicodedata.normalize("NFKC",str(v))
    s=re.sub(r"[ً-ْٰـ]","",s)                     # تشكيل + تطويل
    for a,b in (("أ","ا"),("إ","ا"),("آ","ا"),("ٱ","ا"),("ى","ي"),("ة","ه"),("ؤ","و"),("ئ","ي")):
        s=s.replace(a,b)
    s=re.sub(r"[^0-9a-zء-ي]+"," ",s.lower()).strip()
    return re.sub(r"\s+"," ",s)

def _canon_val(v,mapping):
    """يرجّع الاسم الرسمي الموحّد، أو يحافظ على الاسم الأصلي إذا ما عرفناه"""
    if v is None: return None
    try:
        if pd.isna(v): return None
    except (TypeError,ValueError): pass
    s=str(v).strip()
    if not s: return None
    k=_canon_key(s)
    if not k: return s
    if k in mapping: return mapping[k]
    # 1) نشيل سابقة "Al/Ar/El" التعريف:  Al-Hasakeh → Hasakeh
    for pre in _AR_PREFIX:
        if k.startswith(pre):
            b=k[len(pre):].strip()
            if b in mapping: return mapping[b]
            if re.sub(r"(.)\1+",r"\1",b) in mapping: return mapping[re.sub(r"(.)\1+",r"\1",b)]
    # 2) نشيل لاحقة "Governorate/محافظة"
    for suf in _AR_SUFFIX:
        if k.endswith(" "+suf):
            b=k[:-(len(suf)+1)].strip()
            if b in mapping: return mapping[b]
    # 3) الحروف المكررة: Lataakia/Lattakia/Latakia → Latakia
    q=re.sub(r"(.)\1+",r"\1",k)
    if q in mapping: return mapping[q]
    for pre in _AR_PREFIX:
        if q.startswith(pre) and q[len(pre):].strip() in mapping:
            return mapping[q[len(pre):].strip()]
    # 4) زحزحة الحروف لقواعد البيانات: Alepo → Aleppo
    o=re.sub(r"(?<=[a-z])[aeiou](?=p)",lambda m:"e" if m.group()=="a" else m.group(),k)
    if o!=k and o in mapping: return mapping[o]
    return s

CANON_MAPS={"Governorate":GOV_CANON,"District":DIST_CANON,
            "Sub-district":SUB_CANON,"Program":PROG_CANON}

# =============================================================================
# ===== كل منشأة تنتمي لمحافظة واحدة فقط ================================
# الملف كان فيه 31 منشأة من 81 بتطلع تحت أكثر من محافظة بنفس الاسم
# (مثل: "AT-Tal Hospital" بحلب وريف دمشق مع بعض) — وهيدّي أرقام مغلوطة
# لأنه يجمع مرضى منشأة واحدة مع محافظات مختلفة.
# الحل: خريطة منظّمة من العميل تربط كل منشأة بمحافظةها الصحيحة.
# المفاتيح هي اسم المنشأة بعد التطبيع (_fac_key).
# =============================================================================
FAC_GOV={
    # ===== حلب =====
    "at tal hospital":"Aleppo",
    "alimarati hospital":"Aleppo",
    "alshifaa afrin hospital":"Aleppo",        # مكررتين مدمجين (بمسافة وبدون)
    "balsm center for oncology":"Aleppo",
    "jandaris freiriyeh phc":"Aleppo",
    "jarablus phc":"Aleppo",
    # ===== ادلب =====
    "alnafs almotmaenna mhpss":"Idleb",
    "cardiac comprehensive center":"Idleb",
    "salqin isolation hospital":"Idleb",
    "hazano mc":"Idleb",
    "maternity specialized hospital":"Idleb",
    "oncology and hematology center babsqua":"Idleb",
    "qah phc":"Idleb",
    "sams heart hospital":"Idleb",
    # ===== الرقة =====
    "ali bajliyah mc":"Raqqa",
    "koromaza phc":"Raqqa",
    "madaan phc":"Raqqa","madan phc":"Raqqa","maadan phcc":"Raqqa",
    # ===== الحسكة =====
    "mahtele mc1":"Hasakah",
    "mahtele mc2":"Hasakah",
    "qahtanya phcc":"Hasakah","al qahtanya phcc":"Hasakah",
    "shaddadi center":"Hasakah",
    # ===== درعا =====
    "daraa mobile clinic":"Daraa",
    "daraa oncology center":"Daraa",
    "museifreh mc":"Daraa",
    # ===== دير الزور =====
    "deir ezzor oncology center":"Deir Ezzor",
    # ===== السويداء =====
    "qasr mc":"Sweida",
    "sweida mc":"Sweida",
    "sura phc":"Sweida",
    # ===== اللاذقية =====
    "salma mc":"Latakia",
    # ===== ريف دمشق =====
    "sasa phc":"Rural Damascus",
}

# دمج المنشآت المكررة تحت اسم واحد موحّد
FAC_CANON={
    "alshifaa afrin hospital":"Alshifa'a (Afrin) Hospital",
    "sura phc":"Sura PHCC",
    "shaddadi center":"Shaddadi Center",
    "madan phc":"Mada'an PHCC","maadan phcc":"Mada'an PHCC",
    "al qahtanya phcc":"Qahtanya PHCC",
    # ===== تطبيع نفس الاسم بأكثر من كتابة =====
    # مستشفى المدينة في دير الزور: Madina / Maydin / Myadin كلها نفس المستشفى
    "al madina hospital":"Al Madina Hospital",
    "al maydin hospital":"Al Madina Hospital",
    "al myadin hospital":"Al Madina Hospital",
    # مركز DHPSS في دير الزور: Dez اختصار لـ Deir Ezzor
    "dez mhpss center":"Deir Ezzor MHPSS CENTER",
    # الاسم مكرّر: وحدة واحدة فقط باسم Ali Bajliyah
    "ali bachliya salma mc":"Ali Bajliyah MC",
    # العيادة المتنقلة باسم MC مثل باقي العيادات المتنقلة
    "daraa mobile clinic":"Daraa MC",
}

# منشآت بنفس الاسم موجودة فعلاً بأكثر من محافظة (مش تكرار بالإدخال):
# الاسم عام ما بيحدد مكان، فبنقسّمها ونسمي كل وحدة باسم محافظتها.
# الشكل: (مفتاح المنشأة) -> {المحافظة: الاسم الجديد}
FAC_SPLIT={
    "mhpss center":{
        "Deir Ezzor":"Deir Ezzor MHPSS CENTER",
        "Raqqa":"Raqqa MHPSS CENTER",
    },
}

def _fac_key(v):
    """مفتاح اسم المنشأة: يشيل التشكيل وكل أنواع الفواصل (’ ' ` ") والمسافات المكررة"""
    if v is None: return ""
    try:
        if pd.isna(v): return ""
    except (TypeError,ValueError): pass
    s=unicodedata.normalize("NFKC",str(v))
    s=re.sub(r"[ً-ْٰـ]","",s)                        # تشكيل + تطويل
    s=re.sub(r"[‘’ʼ'`\"”]","",s)                  # كل أنواع الفواصل
    s=re.sub(r"[^0-9a-zء-ي]+"," ",s.lower()).strip()
    return re.sub(r"\s+"," ",s)

# ===== استبعاد المنشآت اللي ما عندها أي بيانات =====
# منشأة عدد خدماتها 0 و عدد مستفيديها 0 (وباقي خاناتها أصفار/فاضية)
# معناها ما في عندنا أي معلومات عنها، فمش لازم تطلع بالفلتر.
# خلينا نحسبها تلقائياً من الداتا، فلما يتعبّى الرقم بتظهر لحالها.
DROP_DEAD_FACILITIES=True
SERVICE_COL="Consultations / Visits Total"
BENEF_COL="Total Benefeciaries all"

# ===== نقل صف منشأة لمكانها الصحيح =====
# بعض الصفوف مك governors.php(المحافظة/المديرية/المنطقة/المجتمع) كلها
# مكرّرة اسم المحافظة (بيانات افتراضية مو مكان حقيقي).
# الشكل: (مفتاح المنشأة) -> {المحافظة الغلط: (المحافظة, المديرية, المنطقة, المجتمع)}
FAC_MOVE={
    "ali bachliya salma mc":{"Deir Ezzor":("Raqqa","Tell Abiad","Tell Abiad","Amin")},
    "ali bajliyah mc":{"Deir Ezzor":("Raqqa","Tell Abiad","Tell Abiad","Amin")},
}
_MOVE_COLS=("Governorate","District","Sub-district","Community")

def _drop_dead_facilities(d):
    if not DROP_DEAD_FACILITIES or "Facility Name" not in d.columns: return d
    if SERVICE_COL not in d.columns or BENEF_COL not in d.columns: return d
    def _sum(col):
        return pd.to_numeric(d[col],errors="coerce").fillna(0).groupby(d["Facility Name"]).sum()
    tot=_sum(SERVICE_COL)+_sum(BENEF_COL)
    dead=tot.index[tot<=0]
    if len(dead)==0: return d
    is_dead=d["Facility Name"].isin(dead)
    if not is_dead.any(): return d
    return d[~is_dead]

def clean_df(d):
    # تنظيف موحّد لكل مصدر داتا: أسماء الأعمدة + قيم الأبعاد النصية + التاريخ
    d=d.copy()          # ما منعدّل الداتا الأصلية، نعمل على نسخة
    d.columns=[str(c).strip() for c in d.columns]
    for c in DIMS:
        if c in d.columns:
            # نشيل الفراغات بالبداية/النهاية والمسافات المكررة بالوسط
            d[c]=d[c].astype("string").str.strip().str.replace(r"\s+"," ",regex=True)
    # ===== توحيد أسماء المحافظات/المديريات/المناطق/البرامج =====
    for col,mapping in CANON_MAPS.items():
        if col in d.columns:
            d[col]=pd.Series([_canon_val(v,mapping) for v in d[col]],
                             index=d.index,dtype="string")
    # ===== دمج المنشآت المكررة ======
    if "Facility Name" in d.columns:
        _fk=[_fac_key(v) for v in d["Facility Name"]]
        _can=[FAC_CANON.get(k,None) for k in _fk]
        d["Facility Name"]=pd.Series(
            [c if c else d["Facility Name"].iloc[i]
             for i,c in enumerate(_can)],index=d.index,dtype="string")
        # ===== توحيد تسمية مراكز الصحة الأولية: PHC ← PHCC =====
        if "Facility Name" in d.columns:
            d["Facility Name"]=(d["Facility Name"].astype("string")
                               .str.replace(r"(?<![A-Za-z])PHC(?![A-Za-z])","PHCC",
                                            regex=True))
        # ===== كل منشأة بمحافظة واحدة (تفوق على أي محافظة مخزّنة مسبقاً) =====
        if "Governorate" in d.columns:
            _ov=[FAC_GOV.get(k,None) for k in _fk]
            if any(x is not None for x in _ov):
                d["Governorate"]=pd.Series(
                    [g if g else d["Governorate"].iloc[i]
                     for i,g in enumerate(_ov)],index=d.index,dtype="string")
        # ===== تقسيم المنشآت العامة الحقيقية لعدة وحدات باسم محافظة كل وحدة =====
        if FAC_SPLIT and "Governorate" in d.columns:
            _new=list(d["Facility Name"]); _hit=False
            for i,k in enumerate(_fk):
                _mp=FAC_SPLIT.get(k)
                if not _mp: continue
                _nn=_mp.get(d["Governorate"].iloc[i])
                if _nn: _new[i]=_nn; _hit=True
            if _hit:
                d["Facility Name"]=pd.Series(_new,index=d.index,dtype="string")
        # ===== نقل الصفوف اللي موقعها غلط لمكان المنشأة الحقيقي =====
        if FAC_MOVE and "Governorate" in d.columns:
            # بنحفظ المحافظة الأصلية قبل أي تعديل، لأن التعديل بيغيّرها
            # وباقي الأعمدة بتنlooked_up بالقيمة الأصلية مو بعد التعديل
            _gov0=list(d["Governorate"])
            for _col in _MOVE_COLS:
                if _col not in d.columns: continue
                _new=list(d[_col]); _hit=False
                for i,k in enumerate(_fk):
                    _mp=FAC_MOVE.get(k)
                    if not _mp: continue
                    _t=_mp.get(str(_gov0[i]))
                    if not _t: continue
                    _v=_t[_MOVE_COLS.index(_col)]
                    if _v is not None and _new[i]!=_v:
                        _new[i]=_v; _hit=True
                if _hit:
                    d[_col]=pd.Series(_new,index=d.index,dtype="string")
    if "Date" in d.columns:
        d["Date"]=pd.to_datetime(d["Date"],errors="coerce")
    d=_drop_dead_facilities(d)
    return d

# ===== بصمة قواعد التنظيف: تتغير تلقائياً إذا عدّلنا أي اسم محافظة/منشأة =====
# ليش؟ لأن Streamlit يخبّي الداتا المحمّلة بال-cache. قبل هي، عدّلنا الخريطة
# بس الكاش ما بيعرف، فيضل يعرض الداتا القديمة. البصمة بتخلي الكاش بينتهي لحاله.
def _clean_fingerprint():
    """بصمة قواعد التنظيف: أي تعديل على الخريطة أو على clean_df بينهي الكاش."""
    import inspect, hashlib
    try: src=inspect.getsource(clean_df)+inspect.getsource(_fac_key)
    except (OSError,TypeError): src=""
    maps=[GOV_CANON,DIST_CANON,SUB_CANON,PROG_CANON,FAC_GOV,FAC_CANON,FAC_SPLIT,FAC_MOVE]
    return hashlib.md5((repr(maps)+src).encode("utf-8")).hexdigest()[:10]

_CLEAN_VER=_clean_fingerprint()

@st.cache_data(show_spinner=False)
def load_base_data(path,sheet,_ver=_CLEAN_VER):
    # الملف الافتراضي المرفق مع المشروع
    return clean_df(pd.read_excel(path,sheet_name=sheet))

@st.cache_data(show_spinner=False)
def book_sheets(blob):
    # أسماء أوراق أي ملف xlsx/xls مرفوع
    return list(pd.ExcelFile(io.BytesIO(blob)).sheet_names)

@st.cache_data(show_spinner=False)
def load_uploaded(blob,name,sheet,_ver=_CLEAN_VER):
    # أي ملف مرفوع من المستخدم يمر بنفس تنظيف الملف الافتراضي
    b=io.BytesIO(blob)
    if name.lower().endswith(".csv"):
        return clean_df(pd.read_csv(b))
    return clean_df(pd.read_excel(b,sheet_name=sheet))

# ===== ربط كل زر بالأعمدة الخاصة به (بادئات أسماء الأعمدة) =====
# لو ضفت عمود جديد للملف، تكتب بادئة اسمه هون وينحسب تلقائيًا بالزر.
BTN_COLS={
 # ---------- تحليل عام (12) ----------
 "g_cb":["Consultations / Visits","Uniqe Beneficiaries","New Benefeciaries",
         "Number of outpatient Curative consultations"],
 "g_rh":["RH ","Total ANCs","Total PNCs","Total family planning","Total PNCs Newborn",
         "Total C sections","Total Normal delivery","STIs total","RH consultations",
         "Matrenatl death averted total","ANC1","ANC4/ANCs","ANC 2+/ANCs",
         "PNCs newborns within 3 days after delivery"],
 "g_sg":["War related surgeries","Non- war related surgeries","Total surgeries",
         "Total war surgeries","Total Non war Surgeries","Total major","Total minor",
         "% War surgeries","Total Major war","Total Major- Non War","Total Minor War",
         "Total Minor Non- War","Total surgeries2","Non War Percentage","Surgeries ",
         "Internal procedures","Non -War boys","Non War Men","Non-War Women","Non-War girls"],
 "g_chw":["CHW ","CHWs cummunity screening","IYCF Messages","AW sessions","Cohesion/",
          "scholarship"],
 "g_de":["Dental Beneficiaries","Total dental Ben","Dental consultations","Dental procedures"],
 "g_tr":["Trauma consultations","Wounds and traumas","War related Total War",
         "War related Male","War related Female","War Men","War Women","War boys","War girls"],
 "g_ho":["Number of Hospitalizations"],
 "g_rf":["Refferals ","Total referrals","Referrals/ consultations"],
 "g_lr":["Total lab tests","Radiolgy ","Total Radiology"],
 "g_gi":["GI Scope ","Total Gi Scope"],
 "g_rd":["Disabilities ","Total disabilities","Total Ambutation","Total Amputations",
         "Recived assisstive Devices","distributed hearing devices","distributed prosthetics",
         "cochlear","Assisstive / Ben"],
 "g_da":["Drugs (Only EMR facilities)","Vaccinations ","distributions BNFs"],
 # ---------- بطاقات معلومات (1) ----------
 "f_inf":["Total services","Daily services","Total Benefeciaries all","Dailiy Beneficiaries",
          "Service / Ben","Total IDP","Total Host","% war","Houshold Ben","Cases / Screened",
          "Men","Women","Boys","Girls","Number of given services","Number of prescribed services",
          "Services availibility"],
 # ---------- خدمات متخصصة (6) ----------
 "s_mh":["Mental health consultations","Total mental Ben","New Beneficiaries",
         "Morbidities Top Mental health Consultations","mhpss Sessions/","PSS group sessions",
         "Total ASD Sessions","Total Individ PSS sessions"],
 "s_bb":["Blood Bank ","Total Blood Bank Beneficiaries"],
 "s_icu":["Number of ICU patients received treatment","Ventilated","Incubators ",
          "Incubators Admissions","ICU Mortality %"],
 "s_dl":["Dialysis ","Total Dialysis Ben","Total Dialysis Sessions"],
 "s_on":["Oncology unit ","Daily oncology sessions"],
 "s_pt":["physiotherapy ","Physiotherapy ","PHYSIO SESSIONS / BEN","physio Consultations/ ben",
         "Speech thx sess"],
 # ---------- الأمراض والوفيات (1) ----------
 "m_mb":["Morbidities ","NCD Indicators ","CD indicators ","Diabetes Patients",
         "leishmaniasis ","Total Meningitis","Total Acute Bloody Diarrhea","Total Pneumonia",
         "Total leishmaniasis treated","Total leishmaniasis patients","Total Measles"],
 # ---------- أخرى (3) ----------
 "o_pop":["Total Benefeciaries all","Dailiy Beneficiaries","Total IDP","Total Host"],
 "o_ca":["Total services","Total Benefeciaries all","Daily services","Dailiy Beneficiaries",
         "Latitude","Longitude","Index"],
 "o_er":["Mortality","Mortality ","Total major","Total minor","Number of Hospitalizations",
         "Trauma consultations"],
}

# ===== لواحق الفئات العمرية/الجنس — تُستعمل لتجميع عمود القياس إلى «مجموعة» واحدة =====
_BREAKS=[" Male <5 years"," Male 5-14 years"," Male 15-18 years"," Male 19-49 years",
         " Male 50+ years"," Male Total Male"," Female <5 years"," Female 5-14 years",
         " Female 15-18 years"," Female 19-49 years"," Female 50+ years",
         " Female Total Female"," Male Male Total"," Female Female Total"," Total Total",
         " Total"," Male"," Female"]

def _group_of(col):
    # نرجّع اسم مجموعة المقياس بإزالة لاحقة الفئة؛ مثال: "X Male <5 years" -> "X"
    for b in sorted(_BREAKS,key=len,reverse=True):
        if col.endswith(b): return col[:-len(b)].strip()
    return col.strip()

# ===== كاش خفيف لأعمدة كل زر: يوفّر آلاف المقارنات في كل إعادة رسم =====
@st.cache_data(show_spinner=False)
def _match_cols_cached(cols,key):
    pats=BTN_COLS.get(key) or []
    skip=set(DIMS6)|{"Project ID","Community"}
    out=[]
    for c in cols:
        if c in skip: continue
        if any(c==p or c.startswith(p) for p in pats): out.append(c)
    return tuple(out)

def _match_cols(df,key):
    # كل الأعمدة الخاصة بزر معيّن (لا الأبعاد ولا التاريخ ولا Project ID ولا Community)
    return list(_match_cols_cached(tuple(map(str,df.columns)),key))

def _num(d,cols):
    # تحويل أعمدة القياس إلى أرقام (الملف فيه أعمدة نصية/فارغة) — يرجع DataFrame بنفس الشكل
    return d[cols].apply(pd.to_numeric,errors="coerce")

def render_data_source():
    # ===== خانة مصدر الداتا: ارفع ملفك أو ارجع للملف الافتراضي =====
    # كل داشبورد وكل فلتر بينحسبوا من الداتا يلي هي مفعّلة هون
    d=None; _name=""; _kind="default"
    with st.expander(T("data_source"),expanded=ss.get("src_open",False)):
        # مفتاح الـ uploader يتغيّر مع src_ver عشان نقدر نرجّع الملف الافتراضي
        # رفع ملف داتا جديد = تعديل على الداتا => للأدمن فقط (المشاهد بيشوف الملف الافتراضي)
        if is_admin():
            up=st.file_uploader(T("src_upload"),type=["xlsx","xls","csv"],
                                key=f"src_upload_{ss.get('src_ver',0)}",
                                help=T("upload_help"))
        else:
            up=None
            st.caption(_L("وضع المشاهدة: الملف الافتراضي فقط — رفع ملفات الداتا للأدمن.",
                          "Viewer mode: default data only — uploading data is admin-only."))
        if up is None:
            # ===== الملف الافتراضي =====
            if not os.path.isfile(DATA_FILE):
                st.warning(_L("لا توجد قاعدة بيانات محفوظة بعد — ارفع ملف Excel من الأعلى (للأدمن) ليبدأ العرض.",
                              "No saved database yet — upload an Excel file above (admin) to start."))
                return None,"",""
            d=load_base_data(DATA_FILE,DATA_SHEET)
            _name=os.path.basename(DATA_FILE); _kind="default"
            st.caption(f"📌 {T('src_default')}: **{_name}** — {T('src_sheet')}: `{DATA_SHEET}`")
        else:
            # ===== ملف المستخدم =====
            _blob=up.getvalue(); _fn=up.name
            if _fn.lower().endswith(".csv"):
                _sheet=None
            else:
                try: _sheets=book_sheets(_blob)
                except Exception as e:
                    st.error(f"{T('src_bad')}: {e}"); _sheets=[]
                if not _sheets:
                    st.error(T("src_bad")); return None,"",""
                _cur=ss.get("src_sheet")
                if _cur not in _sheets: _cur=_sheets[0]
                _sheet=st.selectbox(T("src_sheet"),_sheets,index=_sheets.index(_cur),key="src_sheet")
            try:
                d=load_uploaded(_blob,_fn,_sheet)
            except Exception as e:
                st.error(f"{T('src_bad')}: {e}"); return None,"",""
            _name=_fn; _kind="upload"
            st.success(f"✅ {T('src_active')}: **{_name}**"+(f" — {T('src_sheet')}: `{_sheet}`" if _sheet else ""))
            # حفظ نسخة دائمة من الملف داخل التخزين الخاص (خارج Git)
            if is_admin():
                if st.button("💾 "+_L("حفظ للاستخدام الدائم","Save permanently"),
                             key="src_persist",use_container_width=True):
                    try:
                        with open(meal.DATA_PRIVATE,"wb") as _pf:
                            _pf.write(_blob)
                        load_base_data.clear()
                        st.success(_L("تم الحفظ في .sams_private/data.xlsx","Saved to .sams_private/data.xlsx"))
                        st.rerun()
                    except Exception as _e:
                        st.error(f"{T('src_bad')}: {_e}")
        # ===== تحقق: الأبعاد الستة لازم موجودة وإلا الفلاتر ما رح تشتغل =====
        if d is not None:
            _miss=[c for c in DIMS6 if c not in d.columns]
            st.caption(f"{T('rows_label')}: **{len(d):,}** / {T('cols_label')}: **{len(d.columns):,}**")
            if _miss:
                st.error(f"{T('src_need_cols')}: {', '.join(_miss)}")
            else:
                st.success(T("src_ok"))
        if _kind=="upload" and is_admin() and st.button(f"🔄 {T('src_back_default')}",key="src_reset",use_container_width=True):
            ss["src_ver"]=ss.get("src_ver",0)+1
            st.rerun()
    return d,_name,_kind

def _crm_grid(figs,per_row=6):
    """يعرض الرسمات على شكل شبكة: 6 رسمات بكل سطر (تتمدّد مع عرض الشاشة)."""
    for _i in range(0,len(figs),per_row):
        _row=figs[_i:_i+per_row]
        _cs=st.columns(len(_row),gap="small")
        for _j,_f in enumerate(_row):
            with _cs[_j]:
                if _f.__class__.__module__.startswith("plotly"):
                    st.plotly_chart(_f,use_container_width=True,
                                    config={"displayModeBar":False})
                else:
                    st.pyplot(_f,use_container_width=True)
                    plt.close(_f)

_PIE_COLS=["#1d4ed8","#2563eb","#3b82f6","#60a5fa","#38bdf8","#7dd3fc","#0ea5e9","#93c5fd"]

# ===== ألوان الجنس الموحّدة لكل الرسوم (التمييز باللون والرمز) =====
# ذكر = أروق فاتح ♂ · أنثى = أحمر ♀ · غير محدّد/قيمة أخرى = رمادي ○
SEX_M="#86efac"   # أروق فاتح — ذكور
SEX_F="#ef4444"   # أحمر      — إناث
SEX_O="#9ca3af"   # رمادي     — غير محدّد / أعمدة غير جنسية
_SEX_M_AR=("ذكور","ذكر","صبيان","صبي","أولاد","ولاد","ذكور البالغين","ذكور الأطفال")
_SEX_F_AR=("إناث","اناث","أنثى","أنثاء","انثى","بنات","بنت","نساء","إناث البالغات","إناث الأطفال")

def sex_kind(x):
    """'m' = ذكر · 'f' = أنثى · 'o' = غير محدّد أو قيمة أخرى.
       كلمة «male» تظهر داخل «Female» أيضًا، لذلك الأنثى تُفحص أولًا
       (نفس منطق _is_male_col / _is_female_col تحت، مع دعم العربي)."""
    s=str(x).strip()
    if not s: return "o"
    for w in _SEX_F_AR:
        if w in s: return "f"
    for w in _SEX_M_AR:
        if w in s: return "m"
    if _is_female_col(s): return "f"
    if _is_male_col(s): return "m"
    return "o"

def sex_color(x):
    k=sex_kind(x)
    return SEX_M if k=="m" else SEX_F if k=="f" else SEX_O

def sex_colors(xs):
    return [sex_color(x) for x in xs]

def sex_sym(x):
    k=sex_kind(x)
    return "\u2642" if k=="m" else "\u2640" if k=="f" else "\u25cb"

def sex_lab(x):
    """اسم الفئة مع رمز الجنس — للشرائح المحدّدة جنسيًا فقط."""
    k=sex_kind(x)
    return (sex_sym(x)+" "+str(x)) if k in ("m","f") else str(x)

def sex_ink(x):
    """لون النص المناسب فوق لون الجنس: الأروق الفاتح يحتاج نصًا غامقًا."""
    return "#0f1626" if sex_kind(x)=="m" else "#ffffff"

def _sex_figs_html(counts):
    """رسم الجنس بشكل أشخاص: ذكر (أزرق) / أنثى (وردي) / شخص رمادي للي ما له تصنيف."""
    _m=_f=_u=0
    for _k,_v in dict(counts).items():
        _kind=sex_kind(_k)
        try: _n=int(_v)
        except Exception: _n=0
        if _kind=="m": _m+=_n
        elif _kind=="f": _f+=_n
        else: _u+=_n
    _tot=(_m+_f+_u) or 1
    def _card(ic,lab,val,cls):
        _p=val/_tot*100.0
        return (f'<div class="sexf {cls}"><div class="sexf-ic">{ic}</div>'
                f'<div class="sexf-v">{val:,}</div><div class="sexf-l">{lab}</div>'
                f'<div class="sexf-bar"><i style="width:{_p:.1f}%"></i></div>'
                f'<div class="sexf-p">{_p:.1f}%</div></div>')
    return ('<div class="sexfwrap">'
            +_card("👨",_L("ذكور","Male"),_m,"m")
            +_card("👩",_L("إناث","Female"),_f,"f")
            +_card("👤",_L("بدون تصنيف","Unspecified"),_u,"u")
            +'</div>')

def _cols_or(colors,n):
    """ألوان مُمرّرة من البَرّ، وإلا تدرّج الأزرق الموحّد — يقبل أي عدد شرائح."""
    _c=[str(c) for c in (colors or [])][:n]
    while len(_c)<n: _c.append(_PIE_COLS[len(_c)%len(_PIE_COLS)])
    return _c

def _wrap(s,n=12):
    """يكسر النص الطويل لعدّة أسطر قصيرة حتى ما يصغّر الدونت."""
    _w=str(s).split(); _out=[]; _cur=""
    for _x in _w:
        if _cur and len(_cur)+1+len(_x)>n:
            _out.append(_cur); _cur=_x
        else:
            _cur=(_cur+" "+_x).strip()
    if _cur: _out.append(_cur)
    return "<br>".join(_out) if _out else str(s)

def _pie_go(labels,values,title,height=470,colors=None):
    """دونات كبيرة + سهم (leader line) لكل قطعة يبيّن الاسم والعدد.
       colors=None => تدرّج الأزرق الافتراضي · وألوان الجنس تُمرَّر من بره."""
    import plotly.graph_objects as go
    _vals=[int(v) for v in values]; _tot=sum(_vals)
    _lab=[sex_lab(k) for k in labels]                    # ♂ ذكر · ♀ أنثى
    _txt=[f"{_wrap(k)}<br><b>{int(v):,}</b>" for k,v in zip(_lab,values)]
    _f=go.Figure(go.Pie(labels=_lab,values=_vals,hole=.42,sort=False,
        marker=dict(colors=_cols_or(colors,len(_vals)),
                    line=dict(color=DC_BG,width=2)),
        text=_txt,textinfo="text",textposition="outside",automargin=True,
        textfont=dict(color=DC_TXT,size=10.5),
        hovertemplate="<b>%{label}</b><br>"+T("crm_count")+": %{value:,} (%{percent})<extra></extra>"))
    _f.add_annotation(text=f"{_tot:,}",x=0.5,y=0.5,showarrow=False,
                      font=dict(color=DC_MUT,size=15))
    _f.update_layout(paper_bgcolor=DC_BG,plot_bgcolor=DC_BG,font=dict(color=DC_TXT),
        title=dict(text=title,x=0.5,xanchor="center",automargin=True,
                   font=dict(color=DC_TXT,size=13)),
        height=height,margin=dict(l=6,r=6,t=50,b=6),showlegend=False,
        hoverlabel=dict(bgcolor=DC_CARD,font=dict(color=DC_TXT)))
    return _f

def _gauge_go(value,vmax,title,height=340,vmin=0):
    """نصف دائرة (Gauge) من vmin إلى vmax مع مؤشّر عند المتوسط."""
    import plotly.graph_objects as go
    _mid=(vmax-vmin)/3.0
    _f=go.Figure(go.Indicator(
        mode="gauge+number",
        value=float(value),
        number=dict(font=dict(color=DC_TXT,size=30),valueformat=".1f",
                    suffix=f" <span style='font-size:14px'>{T('crm_days_unit')}</span>"),
        gauge=dict(
            axis=dict(range=[vmin,vmax],tickcolor=DC_MUT,
                      tickfont=dict(color=DC_MUT,size=10),nticks=6),
            bar=dict(color="#38bdf8",thickness=0.30),
            bgcolor="rgba(0,0,0,0)",borderwidth=0,
            steps=[dict(range=[vmin,vmin+_mid],color="rgba(37,99,235,0.30)"),
                   dict(range=[vmin+_mid,vmin+2*_mid],color="rgba(59,130,246,0.30)"),
                   dict(range=[vmin+2*_mid,vmax],color="rgba(147,197,253,0.28)")],
            threshold=dict(line=dict(color="#e6edf7",width=3),thickness=0.85,value=float(value)))))
    _f.update_layout(paper_bgcolor=DC_BG,plot_bgcolor=DC_BG,font=dict(color=DC_TXT,size=10),
        title=dict(text=title,x=0.5,xanchor="center",automargin=True,
                       font=dict(color=DC_TXT,size=13)),
        height=height,margin=dict(l=16,r=16,t=48,b=4))
    return _f

def _bar_go(labels,values,title,height=340,rot=0):
    """أعمدة رأسية بمشتقّات الأزرق فقط، مع العنوان والعدد فوق كل عمود."""
    import plotly.graph_objects as go
    _vals=[int(v) for v in values]
    _f=go.Figure(go.Bar(
        x=[str(x) for x in labels],y=_vals,
        marker=dict(color=[_PIE_COLS[i%len(_PIE_COLS)] for i in range(len(_vals))],
                    line=dict(color=DC_BG,width=1)),
        text=[f"{v:,}" for v in _vals],textposition="outside",
        textfont=dict(color=DC_TXT,size=12),
        hovertemplate="<b>%{x}</b><br>"+T("crm_count")+": %{y:,}<extra></extra>"))
    _f.update_layout(paper_bgcolor=DC_BG,plot_bgcolor=DC_BG,font=dict(color=DC_TXT,size=10),
        title=dict(text=title,x=0.5,xanchor="center",automargin=True,
                       font=dict(color=DC_TXT,size=13)),
        xaxis=dict(gridcolor="#ffffff11",tickfont=dict(size=10),tickangle=rot),
        yaxis=dict(gridcolor="#ffffff11",zeroline=False),
        height=height,margin=dict(l=8,r=8,t=46,b=8),
        hoverlabel=dict(bgcolor=DC_CARD,font=dict(color=DC_TXT)))
    return _f

def render_crm_dashboard(_df):
    """داشبورد الـCRM: ملخّص الأعمدة الرقمية فقط."""
    _nm=ss.get("crm_name_cur") or "crm_table"
    if _df is None or len(_df.columns)==0:
        st.info(T("crm_need_data")); return
    _df=_df.fillna("").astype(str)
    _did=_df.columns[0]
    _sd=None; _ed=None
    for _c in _df.columns:
        _k=_c.strip().lower()
        if _sd is None and ("date identified" in _k or _k in ("start date","start")):
            _sd=_c
        if _ed is None and ("final resolution date" in _k or _k in ("done date","end date","resolution date")):
            _ed=_c
    if ss.get("crm_dash_tbl")!=_nm:
        ss["crm_dash_tbl"]=_nm
        ss.pop("crm_dash_f",None); ss.pop("crm_dash_t",None)
    _gmin=_gmax=None
    if _sd:
        _gds=pd.to_datetime(_df[_sd],errors="coerce").dropna()
        if len(_gds): _gmin=_gds.min().date(); _gmax=_gds.max().date()
    if _gmin is not None:
        if "crm_dash_f" in ss and not (_gmin<=ss["crm_dash_f"]<=_gmax): ss["crm_dash_f"]=_gmin
        if "crm_dash_t" in ss and not (_gmin<=ss["crm_dash_t"]<=_gmax): ss["crm_dash_t"]=_gmax
        if "crm_dash_f" not in ss: ss["crm_dash_f"]=_gmin
        if "crm_dash_t" not in ss: ss["crm_dash_t"]=_gmax
        _fb=st.columns([1,1,0.8,2.2])
        _fb[0].date_input(T("crm_filter_from"),min_value=_gmin,max_value=_gmax,key="crm_dash_f")
        _fb[1].date_input(T("crm_filter_to"),min_value=_gmin,max_value=_gmax,key="crm_dash_t")
        if _fb[2].button(T("crm_dash_reset"),key="crm_dash_rst"):
            ss["crm_dash_f"]=_gmin; ss["crm_dash_t"]=_gmax; st.rerun()
        _gdd=pd.to_datetime(_df[_sd],errors="coerce").dt.date
        _df=_df[(_gdd>=ss["crm_dash_f"])&(_gdd<=ss["crm_dash_t"])].reset_index(drop=True)
    _rows=len(_df); _cols=len(_df.columns)
    _num={}
    for _c in _df.columns:
        _s=pd.to_numeric(_df[_c].str.replace(",","",regex=False).str.strip(),
                         errors="coerce")
        _nz=int(_s.notna().sum())
        if _rows and _nz>0 and _nz>=max(1,int(_rows*0.6)):
            _tk=set(re.split(r"[^a-z0-9]+",_c.strip().lower()))
            _uniq=int(_s.dropna().nunique())
            if "id" in _tk or "identifier" in _tk or _c.strip().lower().endswith("id"):
                continue
            if _nz>=10 and _uniq>=int(_nz*0.95):
                continue
            _num[_c]=_s
    st.caption(f"{T('crm_dash_cur')}: **{_nm}** \u00b7 {_rows:,} {T('crm_rows')} \u00b7 {_cols:,} {T('crm_dash_cols')}")
    if _rows==0:
        st.warning(T("crm_dash_norows")); return
    _rhead("①","\U0001F522",T("crm_kpi_title"),BL_M2,T("crm_kpi_note"))
    _k1,_k2,_k3=st.columns(3,gap="small")
    _dlc=None
    for _c in _df.columns:
        if "days left" in _c.strip().lower():
            _dlc=_c; break
    with _k1:
        _ds=(pd.to_numeric(_df[_dlc].str.replace(",","",regex=False).str.strip(),
             errors="coerce").dropna() if _dlc is not None else pd.Series(dtype=float))
        if len(_ds):
            st.plotly_chart(_gauge_go(_ds.mean(),max(1.0,float(_ds.max())),T("crm_days_left")),
                            use_container_width=True,config={"displayModeBar":False})
            st.caption(f"{T('crm_avg')} {_ds.mean():,.1f} \u00b7 {T('crm_min')} {_ds.min():,.0f}"
                       f" \u00b7 {T('crm_max')} {_ds.max():,.0f}")
        else:
            st.info(T("crm_dash_nonum"))
    with _k2:
        _cty=None
        for _c in _df.columns:
            if "complainer type" in _c.strip().lower():
                _cty=_c; break
        if _cty is not None:
            _tv=_df[_cty].str.strip(); _tv=_tv[_tv!=""]
            if len(_tv):
                _ttop=_tv.value_counts()
                st.plotly_chart(_bar_go(_ttop.index,_ttop.values,T("crm_complainer")),
                                use_container_width=True,config={"displayModeBar":False})
    with _k3:
        _satc=None
        for _c in _df.columns:
            if _c.strip().lower()=="satisfaction":
                _satc=_c; break
        if _satc is not None:
            _sv=_df[_satc].str.strip().replace("",T("crm_not_specified"))
            if len(_sv):
                _stop=_sv.value_counts()
                st.plotly_chart(_bar_go(_stop.index,_stop.values,T("crm_satisfaction")),
                                use_container_width=True,config={"displayModeBar":False})
    _f_chan=None
    _chan=None
    for _c in _df.columns:
        _cl=_c.strip().lower().replace(" ","")
        if "channel" in _cl or _cl in ("input/channel","inputchannel"):
            _chan=_c; break
    if _chan is not None:
        _cv=_df[_chan].str.strip(); _cv=_cv[_cv!=""]
        if len(_cv):
            _ctop=_cv.value_counts()
            _ylab=[str(x) for x in _ctop.index][::-1]
            _yval=list(_ctop.values)[::-1]
            import plotly.graph_objects as go
            _fchan=go.Figure(go.Bar(y=_ylab,x=_yval,orientation="h",
                marker=dict(color=[_PIE_COLS[i%len(_PIE_COLS)] for i in range(len(_yval))]),
                text=[f"{v:,}" for v in _yval],textposition="outside",
                textfont=dict(color=DC_TXT,size=12),
                hovertemplate="<b>%{y}</b><br>"+T("crm_count")+": %{x:,}<extra></extra>"))
            _fchan.update_layout(paper_bgcolor=DC_BG,plot_bgcolor=DC_BG,
                font=dict(color=DC_TXT,size=11),
                title=dict(text=T("crm_channel"),x=0.5,xanchor="center",automargin=True,
                           font=dict(color=DC_TXT,size=12)),
                xaxis=dict(gridcolor="#ffffff11"),yaxis=dict(gridcolor="#ffffff11"),
                height=470,margin=dict(l=6,r=44,t=48,b=8),
                hoverlabel=dict(bgcolor=DC_CARD,font=dict(color=DC_TXT)))
            _f_chan=_fchan
    _f_prio=None
    _prio=None
    for _c in _df.columns:
        if "priority" in _c.strip().lower():
            _prio=_c; break
    if _prio is not None:
        _pv=_df[_prio].str.strip(); _pv=_pv[_pv!=""]
        if 2<=_pv.nunique()<=5:
            _ptop=_pv.value_counts()
            _f_prio=_pie_go(_ptop.index,_ptop.values,T("crm_priority"))
    _f_status=None
    _stat=None
    for _c in _df.columns:
        if "current status" in _c.strip().lower():
            _stat=_c; break
    if _stat is not None:
        _sv=_df[_stat].str.strip(); _sv=_sv[_sv!=""]
        if 2<=_sv.nunique()<=6:
            _stop=_sv.value_counts()
            _f_status=_pie_go(_stop.index,_stop.values,T("crm_status"))
    _f_gender=None
    _gen=None; _gtop=None
    for _c in _df.columns:
        if _c.strip().lower() in ("gender","sex"):
            _gen=_c; break
    if _gen is not None:
        _gv=_df[_gen].str.strip(); _gv=_gv[_gv!=""]
        if len(_gv):
            _gtop=_gv.value_counts()
    _f_ctype=None
    _cty=None
    for _c in _df.columns:
        if "complainer type" in _c.strip().lower():
            _cty=_c; break
    if _cty is not None:
        _tv=_df[_cty].str.strip(); _tv=_tv[_tv!=""]
        if 2<=_tv.nunique()<=6:
            _ttop=_tv.value_counts()
            _f_ctype=_pie_go(_ttop.index,_ttop.values,T("crm_complainer"))
    _f_cat=None
    _ccol=None
    for _c in _df.columns:
        if "complaint categor" in _c.strip().lower():
            _ccol=_c; break
    if _ccol is not None:
        _cv=_df[_ccol].str.strip(); _cv=_cv[_cv!=""]
        if len(_cv):
            _ctop=_cv.value_counts()
            _ctot=int(_ctop.sum())
            import plotly.graph_objects as go
            _fc=go.Figure(go.Bar(
                x=[_abbrev(k) for k in _ctop.index],y=list(_ctop.values),
                marker=dict(color=[_PIE_COLS[i%len(_PIE_COLS)] for i in range(len(_ctop))]),
                customdata=[[str(k),int(v),v/_ctot*100] for k,v in _ctop.items()],
                hovertemplate="<b>%{customdata[0]}</b><br>"+T("crm_count")+
                              ": %{customdata[1]:,} (%{customdata[2]:.0f}%)<extra></extra>",
                text=[f"{v:,}" for v in _ctop.values],textposition="outside",
                textfont=dict(color=DC_TXT,size=11)))
            _fc.update_layout(margin=dict(l=6,r=6,t=42,b=10),
                paper_bgcolor=DC_BG,plot_bgcolor=DC_BG,font=dict(color=DC_TXT,size=10),
                title=dict(text=T("crm_category"),x=0.5,xanchor="center",automargin=True,
                           font=dict(color=DC_TXT,size=12)),
                xaxis=dict(tickfont=dict(size=10),gridcolor="#ffffff11"),
                yaxis=dict(gridcolor="#ffffff11",zeroline=False),
                height=470,hoverlabel=dict(bgcolor=DC_CARD,font=dict(color=DC_TXT)))
            _f_cat=_fc
    _cat=None
    for _c in _df.columns:
        _k=_c.strip().lower()
        if "complaint categor" in _k or _k in ("category","complaint classification","complaint type"):
            _cat=_c; break
    if _f_chan is not None or _f_prio is not None or _f_status is not None:
        _rhead("②","\U0001F4CA",T("crm_dash_distr_hdr"),BL_D2,"")
    _crm_grid([_f for _f in [_f_chan,_f_prio,_f_status,_f_ctype,_f_cat]
               if _f is not None])
    # ===== رسم الجنس بالأشخاص (ذكر/أنثى/رمادي للي ما له تصنيف) =====
    # (حُذف الخط الزمني للمدة بناءً على طلب المستخدم — هذا الرسم بيحل محل دونات الجنس)
    if _gtop is not None:
        st.markdown(f'<div class="sect">👥 {T("crm_gender")}</div>',unsafe_allow_html=True)
        st.markdown(_sex_figs_html(_gtop),unsafe_allow_html=True)
    _gcol=None
    for _c in _df.columns:
        if "govern" in _c.strip().lower():
            _gcol=_c; break
    if _gcol is not None:
        _gv=_df[_gcol].str.strip(); _gv=_gv[_gv!=""]
        if len(_gv):
            _gvc=_gv.value_counts()
            _rhead("③","\U0001F5FA",T("crm_gov"),BL_D2,"")
            _gc={}
            for _k,_v in _gvc.items():
                _id=_gov_id(_k)
                if _id: _gc[_id]=_gc.get(_id,0)+int(_v)
            _html=_syria_map_html(_gc)
            if _html:
                st.markdown(_html,unsafe_allow_html=True)
                _unm=[str(k) for k in _gvc.index if not _gov_id(k)]
                if _unm:
                    st.caption(f"{T('crm_gov_out')}: "+", ".join(f"{k} ({_gvc[k]:,})" for k in _unm))
            else:
                st.info(T("crm_no_match"))

# ===== CRM: صفحة جدول قابل للاختيار والتعديل والحفظ مع الوقت =====
def render_crm():
    # ===== وضع المشاهد أو فتح الداشبورد مباشرة: يعرض داشبورد CRM فقط (بدون أي تعديل) =====
    _open=ss.pop("crm_open",None)
    _cdf=_crm_ensure()
    if _open=="dash" or not is_admin():
        st.markdown('<div class="sect">🤝 CRM — Dashboard</div>',unsafe_allow_html=True)
        if _cdf is None:
            st.info(T("crm_empty"))
        else:
            render_crm_dashboard(_cdf)
        if not is_admin():
            st.caption(_L("وضع المشاهدة: بتقدر تفلتر وتشوف، بس التعديل على الداتا للأدمن فقط.",
                          "Viewer mode: you can filter and view; data editing is admin-only."))
        if st.button("⬅ "+_L("رجوع للرئيسية","Back to home"),key="crm_back_home",
                     use_container_width=True):
            ss["view"]="home"; st.rerun()
        return
    st.markdown('<div class="sect">🤝 CRM</div>',unsafe_allow_html=True)
    st.caption(T("crm_hint"))
    if "crm_ver" not in ss: ss["crm_ver"]=0
    _names=_crm_names()
    _ver=ss.get("crm_ver",0)

    if ss.get("crm_df") is None and _names:
        _first=ss.get("crm_pick") or _names[0]
        _ld=_crm_load(_first)
        if _ld is not None:
            ss["crm_df"]=_ld; ss["crm_name_cur"]=_first
            ss["crm_pick_loaded"]=_first

    # ===== مبدّل العرض في قلب الصفحة (المحرّر | الداشبورد) =====
    _lbl=[f'\u270F\uFE0F {T("crm_tab_edit")}',f'\U0001F4CA {T("crm_tab_dash")}']
    _lc,_cc,_rc=st.columns([1,1.4,1])
    with _cc:
        try:
            _sel=st.segmented_control(T("crm_view"),_lbl,default=_lbl[0],
                                      key="crm_seg",label_visibility="collapsed")
        except Exception:
            _sel=st.radio(T("crm_view"),_lbl,index=0,horizontal=True,
                          key="crm_rad",label_visibility="collapsed")
    if _sel==_lbl[1]:
        render_crm_dashboard(ss.get("crm_df")); return

    # ===== ① اختيار جدول محفوظ + فتح/حذف =====
    _rhead("①","\U0001F4C2",T("crm_saved"),BL_M,f"{len(_names)} {T('crm_tables')}")
    _c1,_c2,_c3=st.columns([1.6,1,1])
    with _c1:
        _pick=st.selectbox(T("crm_saved"),_names or ["\u2014"],index=0,
                           key="crm_pick",disabled=not _names)
    with _c2:
        if st.button(T("crm_load"),key="crm_load",type="primary",use_container_width=True,disabled=not _names):
            ss["crm_df"]=_crm_load(_pick); ss["crm_name_cur"]=_pick
            ss["crm_pick_loaded"]=_pick
            ss["crm_ver"]=_ver+1; st.rerun()
    with _c3:
        if st.button(T("crm_del"),key="crm_del",use_container_width=True,disabled=not _names):
            try: os.remove(_crm_path(_pick))
            except Exception: pass
            if ss.get("crm_name_cur")==_pick:
                ss["crm_df"]=None; ss["crm_name_cur"]=""
            ss.pop("crm_pick_loaded",None)
            ss["crm_ver"]=_ver+1
            st.success(T("crm_del_ok").format(x=_pick)); st.rerun()

    # ===== تحميل تلقائي عند اختيار جدول من القائمة =====
    if _names and _pick!=ss.get("crm_pick_loaded"):
        _ld=_crm_load(_pick)
        if _ld is not None:
            ss["crm_df"]=_ld; ss["crm_name_cur"]=_pick
            ss["crm_pick_loaded"]=_pick
            ss["crm_ver"]=_ver+1
            st.rerun()

    # ===== ② رفع ملف لإنشاء/استبدال جدول =====
    _rhead("②","\u2B06\uFE0F",T("crm_upload"),BL_M2,"")
    _u1,_u2=st.columns([1.6,1])
    with _u1:
        _up=st.file_uploader(T("crm_upload"),type=["xlsx","xls","csv"],
                             key=f"crm_up_{_ver}",label_visibility="collapsed")
    with _u2:
        _upname=st.text_input(T("crm_upsave"),value="",placeholder=T("crm_upsave_ph"),
                              key=f"crm_upname_{_ver}")
    if _up is not None:
        _sig=f"{_up.name}:{getattr(_up,'size',0)}"
        if ss.get("crm_up_sig")!=_sig:
            try:
                _df=(pd.read_csv(_up) if _up.name.lower().endswith(".csv")
                     else pd.read_excel(_up))
                _df=_df.fillna("").astype(str)
                _nm=(_upname or os.path.splitext(_up.name)[0]).strip()
                ss["crm_df"]=_df; ss["crm_name_cur"]=_nm; ss["crm_up_sig"]=_sig
                ss["crm_ver"]=_ver+1
                ss.pop("crm_seg",None)
                st.success(T("crm_loaded").format(x=_nm)); st.rerun()
            except Exception as e:
                st.error(f"⚠️ {e}")
        else:
            st.caption(f"✅ {T('crm_imported')}: {ss.get('crm_name_cur')}")

    # ===== ③ إنشاء جدول جديد فارغ =====
    _rhead("③","\u2795",T("crm_create"),BL_D2,"")
    _n1,_n2,_n3=st.columns([1,1.6,1])
    with _n1:
        _newname=st.text_input(T("crm_name"),value="",placeholder=T("crm_name_ph"),
                               key=f"crm_newname_{_ver}")
    with _n2:
        _newcols=st.text_input(T("crm_cols"),value="",placeholder=T("crm_cols_ph"),
                               key=f"crm_newcols_{_ver}")
    with _n3:
        if st.button(T("crm_newbtn"),key="crm_createbtn",use_container_width=True):
            if not (_newname or "").strip():
                st.warning(T("crm_need_name"))
            else:
                _cs=[c.strip() for c in (_newcols or "").replace("\n",",").split(",") if c.strip()] or ["Column 1"]
                ss["crm_df"]=pd.DataFrame(columns=_cs)
                ss["crm_name_cur"]=_newname.strip()
                ss["crm_ver"]=_ver+1
                st.success(T("crm_loaded").format(x=_newname.strip())); st.rerun()

    _df=ss.get("crm_df")
    if _df is None:
        st.info(T("crm_empty")); return
    _nm=ss.get("crm_name_cur") or "crm_table"
    with st.container():
        _rhead("④","\u270F\uFE0F",f'{T("crm_editor")} \u00b7 {_nm}',BL_D,
               f"{len(_df)} {T('crm_rows')}")
        _edited=st.data_editor(_df,num_rows="dynamic",use_container_width=True,
                               key=f"crm_editor_{_ver}")
        ss["crm_df"]=_edited
        _b1,_b2,_b3=st.columns([1,1,1])
        with _b1:
            _save_name=st.text_input(T("crm_name"),value=_nm,key=f"crm_save_name_{_ver}")
        with _b2:
            if st.button(T("crm_save"),key="crm_savebtn",type="primary",use_container_width=True):
                if not (_save_name or "").strip():
                    st.warning(T("crm_need_name"))
                else:
                    _saved=_crm_save(_save_name,ss["crm_df"])
                    ss["crm_name_cur"]=_saved
                    st.success(T("crm_saved_ok").format(x=_saved))
        with _b3:
            try:
                _buf=io.BytesIO()
                with pd.ExcelWriter(_buf,engine="openpyxl") as _w:
                    ss["crm_df"].to_excel(_w,index=False)
                st.download_button(T("crm_export"),data=_buf.getvalue(),
                                   file_name=f"{_crm_safe(_save_name or _nm)}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key="crm_dl",use_container_width=True)
            except Exception:
                pass
    st.markdown("<br>",unsafe_allow_html=True)
    if st.button("⬅ "+_L("رجوع للرئيسية","Back to home"),key="crm_back_home2",
                 use_container_width=True):
        ss["view"]="home"; st.rerun()

# ===== تصنيف المنشآت بنوعها (مشافي / مراكز صحة / MC / مراكز متخصصة ...) =====
# الترتيب مهم: أول قاعدة بتتطابق هي يلي بتطبّق.
# مثلاً «MC Hospital» فيها كلمة Hospital، فبتتصنّف مستشفى مو مركز MC.
# كل نوع له اسم بالعربي والإنجليزي، والعرض صار «عربي / English».
FAC_KINDS=(
    ("hospital",("hospital",),"مستشفيات","Hospitals","\U0001F3E5"),
    ("du",(r"\bdu\b",),"وحدات DU","DU Units","\U0001F3E8"),
    ("clinic",("clinic",),"عيادات","Clinics","\U0001F9FE"),
    ("phc",("phcc",),"مراكز الرعاية الصحية الأولية","Primary Health Care Centers","\U0001F3E7"),
    ("mc",(r"\bmc\d*\b",),"عيادات متنقلة (MC)","Mobile Clinics (MC)","\U0001F3E5"),
    ("spec",("oncology","cardiac","thalassemia","rehabilitation",
             "women care","maternity specialized"),"مراكز متخصصة","Specialized Centers","\U0001F9ED"),
    ("mhpss",("mhpss",),"مراكز دعم MHPSS","MHPSS Support Centers","\U0001F91D"),
    ("center",("center","centre",r"\bdh\b"),"مراكز أخرى","Other Centers","\U0001F3E2"),
    ("other",(),"أخرى","Other","\U0001F3E0"),
)
# أسماء منشآت تُصنَّف يدوياً لأن اسمها ما بيعبّر عن نوعها الحقيقي
# (المفتاح بعد _fac_key) -> النوع الصحيح
FAC_KIND_FIX={
    "al attareb center":"phc",            # مركز صحة أولية PHCC — مو «مركز أخرى»
    "shaddadi center":"phc",              # مركز صحة أولية PHCC — مو «مركز أخرى»
}
FAC_KIND_AR   ={k:a  for k,_,a,_,_ in FAC_KINDS}
FAC_KIND_EN   ={k:e  for k,_,_,e,_ in FAC_KINDS}
FAC_KIND_ORDER=[k for k,_,_,_,_ in FAC_KINDS if k!="other"]
FAC_KIND_ICON ={k:ic for k,_,_,_,ic in FAC_KINDS}
def _bi(ar,en,sep=" / "): return f"{ar}{sep}{en}"
def _kind_label(k):
    """اسم النوع حسب لغة الواجهة الحالية (زر عربي/English)."""
    return FAC_KIND_EN.get(k,k) if ss.get("lang","en")=="en" else FAC_KIND_AR.get(k,k)
_FAC_KIND_COMPILED=[(k,[(re.compile(p,re.I) if any(ch in p for ch in r"\b") else p.lower()) for p in pats])
                    for k,pats,_,_,_ in FAC_KINDS if pats]

def _fac_kind(name):
    """نوع المنشأة: أول قاعدة بتتطابق بالاسم (مع استثناءات يدوية)."""
    s=str(name or "")
    if not s.strip(): return "other"
    _fix=FAC_KIND_FIX.get(_fac_key(s))
    if _fix: return _fix
    for k,pats in _FAC_KIND_COMPILED:
        for p in pats:
            if p.search(s) if hasattr(p,"search") else (p in s.lower()):
                return k
    return "other"

# ===== بصمة خفيفة للداتا (تسمح بالكاش بدون تجزئة 509 عمود في كل رسم) =====
_SIG_MEMO={}
def _df_sig(df):
    # نتذكر البصمة حسب هوية الـ DataFrame نفسه: تُحسب مرة واحدة في كل rerun
    # بدل حسابها 30 مرة (مرة لكل كارت/رسم).
    try:
        _hit=_SIG_MEMO.get(id(df))
        if _hit is not None and _hit[0] is df:
            return _hit[1]
    except Exception:
        pass
    try:
        h=hashlib.md5(pd.util.hash_pandas_object(df,index=False).values.tobytes()).hexdigest()[:12]
        sig=(len(df),len(df.columns),h)
    except Exception:
        sig=(len(df),len(getattr(df,"columns",[])))
    try:
        if len(_SIG_MEMO)>8: _SIG_MEMO.clear()
        _SIG_MEMO[id(df)]=(df,sig)
    except Exception:
        pass
    return sig

@st.cache_data(show_spinner=False,hash_funcs={pd.DataFrame:_df_sig})
def _fac_kind_counts(df,col="Facility Name"):
    """عدد المنشآت الفريدة لكل نوع، مرتّبة بشكل مفهوم."""
    if df is None or len(df)==0 or col not in df.columns: return [],0
    _u=df[col].dropna().astype(str)
    _u=_u[_u.str.strip()!=""]
    if not len(_u): return [],0
    _g=pd.Series([_fac_kind(x) for x in _u.unique()]).value_counts()
    _rows=[]
    for k in FAC_KIND_ORDER:
        if k in _g.index: _rows.append((k,int(_g[k])))
    if "other" in _g.index: _rows.append(("other",int(_g["other"])))
    return _rows,len(_u.unique())

def render_fac_kind_panel(fdata,total_all):
    """تفصيل المنشآت بنوعها تحت الفلاتر — محسوب على الداتا المفلترة حالياً.
    كل الأسماء بتتبع زر اللغة (عربي / English)."""
    rows,total=_fac_kind_counts(fdata)
    if not rows: return
    st.markdown(f'<div class="ct" style="margin-top:.55rem">\U0001F3D7 '
                f'{T("fac_kinds_title")} — '
                f'<span style="color:#00d4ff">{total}</span> '
                f'{T("f_facility_name")}</div>',unsafe_allow_html=True)
    if total_all and total<total_all:
        st.caption(f"{T('fac_kinds_sub')}: **{total}** / {total_all:,}")
    st.markdown('<div class="hstack">'+_fac_kind_html(rows,total,fdata)+'</div>',
                unsafe_allow_html=True)

def _fac_kind_html(rows,total,fdata=None):
    out=[]
    _F="Facility Name"
    for k,n in rows:
        c=BL_M; share=(n/total*100) if total else 0
        _names=([x for x in fdata[_F].dropna()
                 if _fac_kind(x)==k] if fdata is not None and _F in getattr(fdata,"columns",[])
                 and _fac_kind_counts(fdata)[0] else [])
        _num=_hov(n,_names)
        out.append(f'<div class="qcell" style="--c:{c}">'
                   f'<div class="qh">{FAC_KIND_ICON.get(k,"\U0001F3E0")} {_kind_label(k)}'
                   f'{_num}</div>'
                   f'<div class="qv">{n}</div>'
                   f'{_pbar(share,c)}</div>')
    return "".join(out)

def render_global_filters(d):
    # ===== الفلاتر الستة الرئيسية داخل قسم قابل للطي، وتُطبَّق على كل داشبورد =====
    # 5 فلاتر نقطية (Program/Governorate/District/Sub-district/Facility) + فترة زمنية
    # ===== تصفية متقاطعة (Cross-filtering): أي فلتر بيضيّق باقي الفلاتر =====
    # يعني إذا اخترت المديرية، المحافظة والبرنامج والمنشأة كلهم بينضيقوا
    # حسب الداتا اللي بتطلع منها هالمديرية — والعكس صحيح بكل الاتجاهات.
    f=d  # آمن: لو القسم كان مطويًا ما ينكسر شيء (محتوى expander بينفّذ دايمًا)
    if d is None: return None,None
    with st.expander(T("fl_title"),expanded=ss.get("flt_open",True)):
        sel={}
        # ===== 1) الفترة الزمنية: بالشهر فقط (شهر + سنة) =====
        # ما بنحدد يوم ولا عدد أيام — بس «من شهر» و«إلى شهر».
        _mn=pd.Timestamp(d["Date"].min()); _mx=pd.Timestamp(d["Date"].max())
        _keys=[]
        _cur0=_mn.to_period("M"); _cur1=_mx.to_period("M")
        _p=_cur0
        while _p<=_cur1 and len(_keys)<600:
            _keys.append(str(_p))          # مثل "2026-06"
            _p=_p+1
        if not _keys: _keys=[str(_cur0)]
        # ===== الفترة الافتراضية: سنة DEFAULT_FILTER_YEAR لو موجودة، وإلا كل المدة =====
        _ys=[k for k in _keys if k[:4]==str(DEFAULT_FILTER_YEAR)]
        _d0,_d1=(_ys[0],_ys[-1]) if _ys else (_keys[0],_keys[-1])
        _fm=ss.get("flt_FromMonth"); _tm=ss.get("flt_ToMonth")
        if _fm not in _keys: _fm=_d0
        if _tm not in _keys: _tm=_d1
        if _fm>_tm: _fm,_tm=_tm,_fm
        _mfmt=lambda k:(f"{k[:4]}-{k[5:]}")
        _c1,_c2,_cl=st.columns([1,1,3],gap="medium")
        with _c1:
            _fv=st.selectbox(T("f_from_month"),_keys,index=_keys.index(_fm),
                             format_func=_mfmt,key="flt_FromMonth")
        with _c2:
            _tv=st.selectbox(T("f_to_month"),_keys,index=_keys.index(_tm),
                             format_func=_mfmt,key="flt_ToMonth")
        # لو بدّل المستخدم «من» بعد «إلى» نرتبهم تListenersئياً
        if _fv>_tv: _fv,_tv=_tv,_fv
        sel["Date"]=(pd.Period(_fv,"M").start_time,
                     pd.Period(_tv,"M").start_time+pd.offsets.MonthBegin(1))
        _dr_pool=d[(d["Date"]>=sel["Date"][0])&(d["Date"]<sel["Date"][1])]
        # ===== 2) الفلاتر النقطية: تصفية متقاطعة من كل الاتجاهات ============
        # كل فلتر خياراته بتتحسب من الداتا بعد ما نفلترها ببقية الفلاتر
        # (مو بس الفلاتر اللي قبله) — يعني إذا اخترت المديرية، المحافظة
        # والبرنامج والمنشأة كلهم بينضيقوا، والعكس صحيح.
        _ALL=T("all")
        _pre={dim:ss.get("flt_"+dim,_ALL) for dim in DIMS}
        for dim in DIMS:
            # الداتا = كاملة، minus الفلتر نفسه، minus باقي الفلاتر
            _s=_dr_pool
            for o in DIMS:
                if o==dim: continue
                _v=_pre[o]
                if _v and _v!=_ALL and o in _s.columns:
                    _s=_s[_s[o]==_v]
            if dim in d.columns:
                _vals=sorted([str(v) for v in _s[dim].dropna().unique()])
            else:
                _vals=[]
            _o=[_ALL]+_vals
            # لو الاختيار الحالي ما عاد موجود ضمن الخيارات الجديدة => ارجعله "الكل"
            _cur=_pre[dim]
            if _cur not in _o:
                _cur=_ALL
                ss["flt_"+dim]=_ALL          # تنظيف الاختيار القديم من ذاكرة الجلسة
            _c=st.selectbox(T("f_"+dim.lower().replace(" ","_").replace("-","_")),
                            _o,index=_o.index(_cur),key="flt_"+dim)
            sel[dim]=None if _c==_ALL else _c
        # ===== تطبيق الفلاتر الخمسة + الفترة على الداتا الكاملة =====
        f=d
        for dim in DIMS:
            if sel[dim] is not None: f=f[f[dim]==sel[dim]]
        a,b=sel["Date"]
        f=f[(f["Date"]>=a)&(f["Date"]<b)]
        # ===== ملخص سريع للاختيار الحالي =====
        st.caption(f"✅ {T('rows_label')}: **{len(f):,}** / {len(d):,}  |  {T('f_period')}: "
                   f"**{_mfmt(_fv)} → {_mfmt(_tv)}**")
        # ===== تفصيل المنشآت بنوعها: مشافي لحال، مراكز صحة لحال، MC لحال ... =====
        # بيتحسب على الداتا المفلترة حالياً، يعني بيتغيّر مع كل فلتر
        _ktot,_=(_fac_kind_counts(d)[1],0)
        render_fac_kind_panel(f,_ktot)
    return f,d

@st.cache_data(show_spinner=False,hash_funcs={pd.DataFrame:_df_sig})
def _hhs_has_data(df,key):
    # هل للوحدة داتا فعلاً؟ نفحص كل أعمدةها: إذا كلها صفر/فارغة => ماكو داتا
    cols=_match_cols(df,key)
    if not cols: return 0,0
    _n=df[cols].apply(pd.to_numeric,errors="coerce")
    _cols_with=int((_n.fillna(0).sum(axis=0)>0).sum())
    return _cols_with,len(cols)

def render_health_services(fdata,alldata,embedded=False):
    # ===== لوحة الخدمات الصحية: كروت موحّدة الشكل مع مؤشر حالة (بنمط Power BI) =====
    # embedded=True يعني إنها معروضة داخل الصفحة الرئيسية (بدون صندوق/زر رجوع).
    if embedded:
        st.markdown(f'<div class="sectband">🏥 {T("hhs_title")}<span class="sb-sub">{_L("الخدمات الصحية","Health Services")}</span></div>',unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="ibox"><div class="ibox-head"><span class="ibox-title">🏥 {T("hhs_title")}</span></div>',unsafe_allow_html=True)
    _sn=ss.get("_srcname") or ""
    st.caption(f"{T('data_source')}: **{_sn}**" if _sn else T("hhs_sub"))
    _cur=ss.get("_hhs_key")
    # الداشبوردات المخصّصة (ليها لوحة مصمّمة يدوياً) والباقي يعرض القالب العام
    _custom_keys={"g_cb","g_rh","g_sg","g_chw","g_de","g_tr","g_ho","g_rf","g_lr","g_gi"}
    for _sk,_ic,_tk,_items in SECTIONS:
        st.markdown(f'<div class="hhs-sec">{_ic} {T(_tk)}'
                    f'<span class="hs-n">{len(_items)}</span></div>',unsafe_allow_html=True)
        if not _items:
            st.caption(T("no_items")); st.markdown("<br>",unsafe_allow_html=True); continue
        # كل وحدة = كرت واحد حقيقي (حاوية بحدود) فيه سطر الحالة + زر واحد قابل للضغط.
        # الشبكة 4 أعمدة => كل الكروت بنفس الحجم والشكل مهما اختلف طول الاسم.
        _r=0
        while _r<len(_items):
            _row=_items[_r:_r+4]
            _cols=st.columns(len(_row),gap="small")
            for _ci,(_k,_ic2) in enumerate(_row):
                _n_ok,_n_all=_hhs_has_data(alldata,_k)
                _badge=('<span class="hhs-badge custom">★ '+T("hhs_custom")+'</span>'
                        if _k in _custom_keys
                        else '<span class="hhs-badge generic">'+T("hhs_generic")+'</span>')
                _dot=(f'<span class="hhs-dot has"><i></i>{_n_ok}/{_n_all} {T("hhs_has_data")}</span>'
                      if _n_ok>0 else '<span class="hhs-dot no"><i></i>'+T("hhs_no_data")+'</span>')
                with _cols[_ci]:
                    with st.container(border=True):
                        st.markdown(f'<div class="hhs-meta"><span class="hm-ic">{_ic2}</span>'
                                    f'{_badge}{_dot}</div>',unsafe_allow_html=True)
                        if st.button(T(_k),key=f"hhs_{_sk}_{_k}",use_container_width=True,
                                     type=("primary" if _cur==_k else "secondary")):
                            ss["_hhs_key"]=_k; ss["_hhs_sec"]=_tk
                            ss["view"]="dash"          # انتقال لواجهة الداشبورد لوحدها
                            ss.pop("dash_switch",None)  # نحدّث قائمة التبديل مع الزر الجديد
                            st.rerun()
            _r+=4
        st.markdown("<br>",unsafe_allow_html=True)
    st.markdown("<br>",unsafe_allow_html=True)
    st.caption(T("pick_a_button"))
    # زر الرجوع للرئيسية (يظهر بس لما الصفحة تكون مستقلة)
    if not embedded:
        if st.button(f"⬅ {T('btn_back')}",key="hhs_back",use_container_width=True):
            ss["view"]="home"; st.rerun()

# ===== ألوان الداشبورد (نفس هوية التطبيق) =====
DC_BG="#151f38"; DC_CARD="#1c2846"; DC_EDGE="#2b3f66"; DC_TXT="#e6edf7"; DC_MUT="#8aa0c0"
DC_PAL=["#00d4ff","#7c5cff","#4ade80","#fbbf24","#f472b6","#38bdf8","#ff7a59","#a78bfa"]
# ===== لوحة زرقاء بالكامل: مشتقات من الأزرق الفاتح والغامق فقط =====
# نستخدمها للأقسام التي يجب أن تكون بلون واحد (بلا أحمر/أخضر/برتقالي/بنفسجي)
BL_L="#7dd3fc"   # أزرق فاتح جداً
BL_M="#38bdf8"   # أزرق فاتح (لون الهوية)
BL_M2="#0ea5e9"  # أزرق متوسط
BL_D="#1e40af"   # أزرق غامق
BL_D2="#3b82f6"  # أزرق غامق متوسط
# ٤ درجات فاتحة (غير حربية) + ٤ درجات غامقة (حربية) — لتمييز المجموعتين
BL_NW=["#b3e5fc","#7dd3fc","#38bdf8","#0ea5e9"]
BL_W =["#60a5fa","#3b82f6","#2563eb","#1e40af"]
# تدرّج متسلسل للفئات العمرية (فاتح ⇄ غامق)
BL_SEQ=["#b3e5fc","#7dd3fc","#38bdf8","#2563eb","#1e3a8a"]
# ٨ درجات زرقاء كاملة (فاتح ⇄ غامق) — بديل DC_PAL داخل داشبوردات الخدمات الصحية
DB_PAL=["#b3e5fc","#7dd3fc","#38bdf8","#0ea5e9","#3b82f6","#2563eb","#1d4ed8","#1e40af"]

# ===== أحجام الرسومات: تأخذ عرض الداشبورد كامل وتتمدد مع الشاشة =====
# كل الرسومات تُعرض بـ use_container_width=True فتصبح بعرض الصفحة مهما كبرت الشاشة
PG_W=13.6      # العرض الكامل: رسم واحد بعرض الداشبورد
HALF_W=6.9     # نصف العرض: رسمان جنب بعض (شبكة المربعات)
TILE_W=4.45    # ثلث العرض: ثلاثة مربعات جنب بعض (سلايدات Power BI)
TILE_H=4.9     # ارتفاع المربع داخل شبكة الثلاث
DON_H=5.6      # ارتفاع الدونت بعرض الصفحة
HALF_H=4.6     # ارتفاع الدونت/الرسم داخل مربّع بنصف العرض
LINE_H=5.0     # ارتفاع الرسوم الخطية والأعمدة
# ===== هوية الداشبوردات الموحّدة (مأخوذة من داشبورد Consultations and BEN) =====
# كل داشبورد صار يستخدم نفس المقاسات بالضبط: نفس عرض السلايد، نفس خط
# الدونات والمفتاح، ونفس الارتفاع. قبل هي كانت كل داشبورد بمقاساتها.
DP_W       = TILE_W   # عرض كل سلايد (سلايد واحد بالنص = نفس عرض سلايد بثلاثة)
DP_TSIZE   = 14       # حجم رقم/عنوان الدونات في النص
DP_LFONT   = 10       # حجم خط مفتاح الشرائح
DP_LMAX    = 18       # أقصى طول لاسم الشريحة قبل القص
DP_KEYBELOW= True     # المفتاح تحت الدونات دايمًا (مو يمين)
DP_GAP     = "medium" # نفس المسافة بين كل السلايدات
# خطوط الرسوم البيانية: ٣ أحجام فقط بدل ١٠ أحجام مختلفة
DP_FS_SM = 10         # أرقام الشريط وأي تعليق صغير
DP_FS    = 12         # أسماء المحاور والتicks
DP_FS_LG = 13         # عناوين المحاور والمفاتيح
DP_MS    = 5          # حجم نقاط الخط
DP_LW    = 2.6        # سماكة الخط
# لوح الألوان الموحّد لكل الداشبوردات: تدرّج أزرق واحد (فاتح ⇄ غامق)
DP_PAL   = DB_PAL     # ٨ درجات — نفس لوحة هوية الموقع
def _don_fig(half=False):  return _dark_fig(HALF_W if half else PG_W,DON_H)
def _lin_fig(half=False):  return _dark_fig(HALF_W if half else PG_W,LINE_H)

def _dark_fig(w,h,**kw):
    # رسم بياني بنفس خلفية التطبيق وألوانه
    fig,ax=plt.subplots(figsize=(w,h),**kw)
    fig.patch.set_facecolor(DC_BG); ax.set_facecolor(DC_CARD)
    for sp in ax.spines.values(): sp.set_color(DC_EDGE)
    ax.tick_params(colors=DC_MUT,labelsize=9)
    ax.title.set_color(DC_TXT)
    try: ax.xaxis.label.set_color(DC_MUT); ax.yaxis.label.set_color(DC_MUT)
    except Exception: pass
    ax.grid(True,color="#ffffff",alpha=.07,linewidth=.8)
    ax.set_axisbelow(True)
    return fig,ax

_STOPWORDS={"for","or","of","no","the","and","a","an","to","with","on","in"}
def _abbrev(t,maxlen=9):
    t=str(t).strip()
    w=[x for x in re.split(r"[\s\-_\u2013\u2014/,\.]+",t) if x and x.lower() not in _STOPWORDS]
    if len(w)>=2:
        ab="".join(x[0].upper() for x in w if x[0].isalpha())
    else:
        ab=t
    ab=ab[:maxlen].strip()
    return ab or t[:maxlen]

_GOV_IDS={"idleb":"SYID","idlib":"SYID","aleppo":"SYHL","halab":"SYHL",
 "ar-raqqa":"SYRA","ar raqqa":"SYRA","raqqa":"SYRA","ar-raqqah":"SYRA",
 "al-hasakeh":"SYHA","al hasakeh":"SYHA","hasakeh":"SYHA","hasaka":"SYHA",
 "al-hasakah":"SYHA","damascus":"SYDI","rural damascus":"SYRD","rif dimashq":"SYRD",
 "homs":"SYHI","hims":"SYHI","hama":"SYHM","hamah":"SYHM",
 "lattakia":"SYLA","latakia":"SYLA","tartus":"SYTA","daraa":"SYDR","dar`a":"SYDR",
 "as-suwayda":"SYSU","suwayda":"SYSU","deir ez-zor":"SYDY","deir ezzor":"SYDY",
 "dayr az zawr":"SYDY","quneitra":"SYQU"}

def _gov_id(name):
    k=re.sub(r"\s+"," ",str(name).strip().lower())
    return _GOV_IDS.get(k)

def _hexmix(c1,c2,t):
    c1=c1.lstrip("#"); c2=c2.lstrip("#")
    a=[int(c1[i:i+2],16) for i in (0,2,4)]; b=[int(c2[i:i+2],16) for i in (0,2,4)]
    return "#%02x%02x%02x"%tuple(int(a[i]+(b[i]-a[i])*t) for i in range(3))

def _syria_map_html(counts):
    import os
    p=os.path.join(os.path.dirname(os.path.abspath(__file__)),"syria_gov.svg")
    try: svg=open(p,encoding="utf-8").read()
    except Exception: return None
    paths=re.findall(r'<path\s+d="([^"]+)"\s+id="(SY[A-Z]{2})"\s+name="([^"]+)"',svg)
    if not paths: return None
    mx=max(list(counts.values())+[1])
    out=['<svg viewBox="0 0 1000 918" width="100%" xmlns="http://www.w3.org/2000/svg" '
         'style="max-height:560px">']
    for d,i,nm in paths:
        c=int(counts.get(i,0))
        fill=_hexmix("#bcdcff","#1565c0",(c/mx)**0.45) if c else "#3f5c86"
        out.append(f'<path d="{d}" fill="{fill}" stroke="#0b1220" stroke-width="1.2">'
                   f'<title>{nm}: {c:,}</title></path>')
    out.append("</svg>")
    return "".join(out)

def _twobox(lb_a,vl_a,c_a,lb_b,vl_b,c_b):
    """مربع واحد فيه رقمان فقط (بدون أي سطر إضافي)."""
    st.markdown('<div class="tbox">'
                f'<div class="half" style="--c:{c_a}"><div class="lb">{lb_a}</div>'
                f'<div class="vl">{vl_a}</div></div>'
                f'<div class="sep"></div>'
                f'<div class="half" style="--c:{c_b}"><div class="lb">{lb_b}</div>'
                f'<div class="vl">{vl_b}</div></div>'
                '</div>',unsafe_allow_html=True)

def _quadbox(items):
    """صف واحد مرتّب من ٤ مربعات: كل مربع (اسم + رقم)."""
    h=['<div class="qbox4">']
    for lb,vl,c in items:
        h.append(f'<div class="q" style="--c:{c}"><div class="lb">{lb}</div>'
                 f'<div class="vl">{vl}</div></div>')
    h.append('</div>')
    st.markdown("".join(h),unsafe_allow_html=True)

def _twobox3(items):
    """مربع واحد فيه ٣ أرقام (بدون أي سطر إضافي)."""
    h=['<div class="tbox t3">']
    for _i,(lb,vl,c,sb) in enumerate(items):
        if _i: h.append('<div class="sep"></div>')
        h.append(f'<div class="half" style="--c:{c}"><div class="lb">{lb}</div>'
                 f'<div class="vl">{vl}</div>' + _sb_div(sb) + '</div>')
    h.append('</div>')
    st.markdown("".join(h),unsafe_allow_html=True)

def _kcards(items):
    # شريط بطاقات KPI: كل بطاقة = (أيقونة، عنوان، رقم، لون، سطر صغير)
    h=['<div class="kcards">']
    for ic,lb,vl,c,sb in items:
        h.append(f'<div class="kcard" style="--c:{c}"><div class="ic">{ic}</div>'
                 f'<div class="lb">{lb}</div><div class="vl">{vl}</div>'
                 + _sb_div(sb) + '</div>')
    h.append('</div>')
    st.markdown("".join(h),unsafe_allow_html=True)

_NUMS=["①","②","③","④","⑤","⑥","⑦","⑧","⑨","⑩","⑪","⑫","⑬","⑭","⑮","⑯","⑰","⑱","⑲","⑳"]
_ORG_CSS=(
    # ترويسة بلا إطار: ولا خلفية ولا حد ولا ظل — العنوان بنص الصفحة
    "<style>.orgbar{display:flex;align-items:center;justify-content:center;"
    "gap:18px;padding:6px 4px 16px 4px;margin:0 0 10px 0;flex-wrap:nowrap}"
    ".orglogo{height:74px;width:auto;max-width:46%;object-fit:contain;"
    "display:block;flex:0 1 auto}"
    ".orgsep{width:1px;height:56px;background:#c9d6ea;flex:0 0 1px}"
    ".orgmeta{display:flex;flex-direction:column;gap:4px;min-width:0;text-align:left}"
    ".org-en{font-size:19px;font-weight:800;color:#12233d;letter-spacing:.3px;line-height:1.2}"
    ".org-ar{font-size:17px;font-weight:700;color:#33507d;line-height:1.35}"
    ".org-tag{font-size:12px;font-weight:700;color:#5b7aad;letter-spacing:1.4px;"
    "text-transform:uppercase;margin-top:2px}"
    "</style>")

def _org_header():
    """ترويسة ثابتة أعلى **كل** صفحة: شعار 1.png بحجمه الطبيعي + الاسم
    الرسمي (إنجليزي ثم عربي)، كل شي بنص الصفحة وبلا إطار.
    الأسماء ما بينترجم تلقائيًا — مثبّتة على حالو بالترتيب المطلوب."""
    _lg=_org_logo()
    _logo=(f'<img class="orglogo" src="{_lg}" alt="{ORG_SHORT}">'
           if _lg else f'<div class="org-en">{ORG_EN}</div>')
    st.markdown(
        _ORG_CSS
        + '<div class="orgbar">'
        + _logo
        + '<div class="orgsep"></div>'
        + '<div class="orgmeta">'
        + f'<div class="org-en">{ORG_EN}</div>'
        + f'<div class="org-ar">{ORG_AR}</div>'
        + f'<div class="org-tag">{ORG_DASH_EN}</div>'
        + '</div></div>',
        unsafe_allow_html=True)

_SEC_N=[0]
# ===== حذف سطر النسبة المئوية تحت المربعات =====
# المستخدم طلب حذف النسبة المئوية الي كانت تحت المربعات، بس السطر الثاني
# المفيد (مثل: grouped screened: 120 أو war / total) بيضل ظاهر.
_PCT_ONLY=re.compile(r"^\s*[\d.,\s]*%\s*$|^\s*[\u2014\u2013-]\s*$")
_PCT_TOK=re.compile(r"[\d.,]+\s*%")
def _keep_sub(txt):
    """يحذف النسبة المئوية من السطر الثاني تحت المربعات، بس بيخلّي
    العنوان/الوصف شغّال (مثل: «Consultations 48.3%» => «Consultations»)،
    وإذا ما ضلّ شي مفيد بينحذف السطر كامل."""
    s=str(txt or "")
    if _PCT_ONLY.match(s): return ""
    if _PCT_TOK.search(s):
        s=_PCT_TOK.sub("",s)
        s=re.sub(r"\s*[\u00b7\u2022]\s*$","",s)
        s=re.sub(r"^\s*[\u00b7\u2022]\s*","",s)
        s=re.sub(r"\s*/\s*$","",s)
        s=re.sub(r"^\s*/\s*","",s)
        s=re.sub(r"\s{2,}"," ",s).strip(" \u00b7\u2022/-\u2014")
        return s
    return s
def _qs_div(txt):
    """سطر ثانوي تحت الرقم: يختفي تلقائياً إذا كان نسبة مئوية"""
    s=_keep_sub(txt)
    return f'<div class="qs">{s}</div>' if s else ""
def _sb_div(txt):
    s=_keep_sub(txt)
    return f'<div class="sb">{s}</div>' if s else ""

def _sechead(title,note="",icon="",color=None):
    """عنوان قسم legacy => يمرّ بنفس مكوّن _rhead الموحّد (ترقيم + لون)"""
    _SEC_N[0]+=1
    if not icon:
        icon=next((c for c in title if ord(c)>0x2000),"📌")
        if title.startswith(icon): title=title[len(icon):].lstrip()
    _rhead(_NUMS[min(_SEC_N[0],len(_NUMS))-1],icon,title,
           color or DC_PAL[(_SEC_N[0]-1)%len(DC_PAL)],note)

def _rhead_html(num,icon,title,color,note=""):
    """عنوان قسم موحّد لكل الداشبوردات — يُرجع HTML (للمربعات) أو يُطبع"""
    return (f'<div class="rhead" style="--c:{color}">'
            f'<span class="rn">{num}</span><span class="ri">{icon}</span>'
            f'<h4>{title}</h4><div class="n">{note}</div></div>')

def _rhead(num,icon,title,color,note=""):
    """عنوان قسم ملوّن بأيقونة ورقم — يجذب العين"""
    st.markdown(_rhead_html(num,icon,title,color,note),unsafe_allow_html=True)

def _donut_fig(data,colors,center_lab,hole=.42,explode=.05,tsize=30,w=None,lfont=19,
               key_below=False,lmax=None,h=None):
    """دونت: الدائرة يسار + المفتاح يمين (أو تحت إذا ضاق العرض)
       data=[(اسم,قيمة)] — العنوان يُرسم فوق الرسم في HTML وليس داخله
       lmax=قصّ اسم الشريحة في المفتاح (للسلايد الضيق)
       h=ارتفاع مخصّص (يتحكم بحجم الدونت بعد التمدّد للعرض)"""
    data=[(n,v) for n,v in data if v>0]
    if not data: return None
    # ===== الألوان: لو الداشبورد ما عطى لون لكل شريحة، نكمّل من اللوح الموحّد =====
    # (كذا كل الدونات بالموقع كله بتستخدم نفس تدرّج الأزرق)
    _cols=list(colors[:len(data)]) if colors else []
    if len(_cols)<len(data):
        _all=(list(DP_PAL)*4)
        _cols+= _all[len(_cols):len(data)]
    _w=w if w else PG_W
    # سلايد: نفس ارتفاع بقية السلايدات (TILE_H) — full: DON_H
    _h=h if h else (TILE_H if key_below else (DON_H if _w>=PG_W-0.1 else HALF_H))
    fig,ax=_dark_fig(_w,_h)
    _v=[v for _,v in data]; _tot=float(sum(_v))
    _ex=[explode]*len(_v) if explode else None
    w_,_t=ax.pie(_v,labels=None,startangle=90,counterclock=False,explode=_ex,
                 radius=1.0,colors=_cols,
                 wedgeprops=dict(width=hole,edgecolor=DC_BG,linewidth=2.4))
    ax.set_xlim(-1.06,1.06); ax.set_ylim(-1.06,1.06)   # الدائرة تملأ مساحتها
    ax.set_box_aspect(1)                                # دائرة مثالية (مو مضغوطة ولا ممدودة)
    ax.text(0,0.18,center_lab,ha="center",va="center",color=DC_TXT,
            fontsize=tsize,fontweight="900",transform=ax.transData)
    ax.text(0,-0.34,f"{_tot:,.0f}",ha="center",va="center",color=DC_MUT,
            fontsize=int(tsize*0.63),fontweight="700",transform=ax.transData)
    # أسماء الشرائح في المفتاح: مع رمز الجنس ♂/♀ للفئات المحدّدة جنسيًا فقط
    _nm=[sex_lab(n) if sex_kind(n) in ("m","f") else str(n) for n,v in data]
    _nm=[(n[:lmax-1]+"…" if lmax and len(str(n))>lmax else n) for n in _nm]
    lg=[f"{n}    {v:,.0f}    ({v/_tot*100:.1f}%)" for n,(_,v) in zip(_nm,data)]
    if key_below:
        # المفتاح تحت الدائرة: نختار عدد الأعمدة حسب طول النص حتى ما يقص
        _dpi=fig.get_size_inches()[1]*fig.dpi      # الارتفاع بالبكسل
        _wpx=_w*fig.dpi                            # العرض بالبكسل
        _est=max(len(x) for x in lg)*(lfont*0.62)  # تقدير عرض السطر
        _ncol=2 if (_est*2+60)<(_wpx*0.94) else 1
        ax.legend(w_,lg,loc="upper center",bbox_to_anchor=(0.5,-0.02),ncol=_ncol,
                  fontsize=lfont,labelcolor=DC_TXT,frameon=False,handlelength=1.0,
                  handletextpad=.5,columnspacing=.8,labelspacing=.5,borderpad=.2)
        _rows=int(-(-len(lg)//_ncol))              # عدد أسطر المفتاح
        _bot=min(0.46,0.10+_rows*(lfont*1.55)/_dpi)
        fig.subplots_adjust(left=0.03,right=0.97,top=1.0-_bot*0.42,bottom=_bot)
    else:               # عريض: الدائرة يسار والمفتاح يمين => العرض كله مستعمل
        ax.legend(w_,lg,loc="center left",bbox_to_anchor=(1.03,0.5),fontsize=lfont,
                 labelcolor=DC_TXT,frameon=False,handlelength=1.2,handletextpad=.9,
                 labelspacing=.9,borderpad=.5)
        fig.subplots_adjust(left=0.012,right=0.56,top=0.99,bottom=0.01)
    return fig

def _fig_tr(fig):
    """ترجمة كل النصوص الي *داخل الرسم* (محاور، مفتاح، عناوين، أرقام وسم)
    وقت العرض بالإنجليزية. قبل هي كانت تضلّع عربية لأن الترجمة كانت
    شغالة على مستوى st.markdown فقط، والنصوص الي جوّه matplotlib ما كان
    يوصلها ترجمة."""
    if st.session_state.get("lang","en")!="en": return
    try:
        from matplotlib.text import Text as _MText
    except Exception:
        return
    try:
        _all=list(fig.findobj(match=_MText))
    except Exception:
        return
    _ar=[t for t in _all if isinstance(t.get_text(),str) and _AR_RE.search(t.get_text())]
    if not _ar: return
    try:                                   # ترجمة دفعة وحدة (أسرع بكثير)
        _out=A2E_MANY([t.get_text() for t in _ar])
        for t,x in zip(_ar,_out):
            if isinstance(x,str) and x.strip() and x!=t.get_text():
                t.set_text(x)
    except Exception:
        pass

def _show(fig):
    """عرض أي رسم: يتمدّد لعرض الداشبورد/الشاشة كاملة"""
    if fig is not None:
        _fig_tr(fig)
        st.pyplot(fig,use_container_width=True); plt.close(fig)

def _pbar(share,color):
    """شريط نسبة رفيع يوضّح حجم الرقم بصرياً"""
    wpx=max(1.5,min(100.0,float(share)))
    return (f'<div class="pbar"><i style="width:{wpx:.1f}%;background:'
            f'linear-gradient(90deg,{color},#ffffff55)"></i></div>')

def _stack(parts):
    """شريط توزيع مركّب: أجزاء ملوّنة جنب بعضها بنسبة كل جزء"""
    tot=sum(v for _,v,_c in parts) or 1
    h=['<div class="stack">']
    for n,v,c in parts:
        if v<=0: continue
        h.append(f'<i style="width:{v/tot*100:.2f}%;background:{c}" title="{n}"></i>')
    h.append('</div>')
    return "".join(h)

def render_dash_page(fdata,alldata):
    # ===== واجهة الداشبورد: داشبورد واحد لحاله + تنقّل بين الأقسام =====
    _k=ss.get("_hhs_key")
    if not _k:
        ss["view"]="hhs"; st.rerun()
    # ===== شريط علوي: رجوع للأقسام + تبديل الداشبورد مباشرة =====
    top=st.columns([1,2.4])
    with top[0]:
        if st.button(f"⬅ {T('btn_back_sections')}",key="dash_back",use_container_width=True):
            ss["view"]="home"; st.rerun()
    with top[1]:
        _all=[(k,T(k)) for _,_,_,items in SECTIONS for k,_ in items]
        _labs=[n for _,n in _all]; _keys=[k for k,_ in _all]
        _i=_keys.index(_k) if _k in _keys else 0
        _pick=st.selectbox(T("switch_dash"),_labs,index=_i,key="dash_switch")
        if _pick!=T(_k):
            ss["_hhs_key"]=_keys[_labs.index(_pick)]; st.rerun()
    render_hhs_dashboard(fdata,alldata)
    st.markdown("<br>",unsafe_allow_html=True)
    b1,b2=st.columns(2)
    with b1:
        if st.button(f"⬅ {T('btn_back_sections')}",key="dash_back2",use_container_width=True):
            ss["view"]="home"; st.rerun()
    with b2:
        if st.button(f"🏠 {T('btn_home')}",key="dash_home",use_container_width=True):
            ss["view"]="home"; st.rerun()

def render_hhs_dashboard(fdata,alldata):
    # ===== داشبورد الزر المختار: لكل زر داشبورد مخصص، وإلا الداشبورد العام =====
    _k=ss.get("_hhs_key")
    if not _k:
        st.info(T("pick_a_button")); return
    _custom={"g_cb":dash_g_cb,"g_rh":dash_g_rh,"g_sg":dash_g_sg,"g_chw":dash_g_chw,
             "g_de":dash_g_de,"g_tr":dash_g_tr,"g_ho":dash_g_ho,"g_rf":dash_g_rf,"g_lr":dash_g_lr,"g_gi":dash_g_gi}
    if _k in _custom: _custom[_k](fdata,alldata)
    else: render_hhs_generic(fdata,alldata)

def dash_g_cb(fdata,alldata):
    # =========================================================================
    # ===== داشبورد «الاستشارات والمنافع» =====
    # هوية لونية: أزرق فقط (فاتح ⇄ غامق) — نفس داشبورد العمليات الجراحية
    # التخطيط: ٣ سلايدات جنب بعض + الخط بعرض الداشبورد كامل
    # =========================================================================
    if not len(fdata):
        _dash_head(T("g_cb"),fdata,ss.get("_srcname") or "","\U0001F4CA")
        st.info(T("no_rows_match"))
        _dash_foot(ss.get("_srcname") or "")
        return
    S=lambda c: float(_num(fdata,[c])[c].sum()) if c in fdata.columns else 0.0
    M=lambda c: float(_num(fdata,[c])[c].mean()) if c in fdata.columns else 0.0
    fmt=lambda v: f"{v:,.0f}"
    pct=lambda a,b: f"{(a/b*100):.1f}%" if b else "\u2014"
    _sn=ss.get("_srcname") or ""
    _dash_head(T("g_cb"),fdata,_sn,"\U0001F4CA")
    # ===== ① شريط الأرقام الأساسية (تدرّج أزرق) =====
    _sv=S("Total services"); _co=S("Consultations / Visits Total")
    _bn=S("Uniqe Beneficiaries Total")
    _cur=S("Number of outpatient Curative consultations Total Total")
    _nb=S("New Benefeciaries Total Total")
    _rhead("\u2460","\U0001F4CC",T("k_services"),BL_M,T("all_rows"))
    _kcards([
        ("\U0001FA7A",T("k_services"),fmt(_sv),BL_M,T("k_consultations")+f" {pct(_co,_sv)}"),
        ("\U0001F48A",T("k_consultations"),fmt(_co),BL_M2,T("k_curative")+f" {pct(_cur,_co)}"),
        ("\U0001F465",T("k_beneficiaries"),fmt(_bn),BL_NW[1],T("k_new_ben")+f" {pct(_nb,_bn)}"),
        ("\U0001F48A",T("k_curative"),fmt(_cur),BL_D2,T("k_beneficiaries")+f" {pct(_nb,_co)}"),
        ("\U0001F195",T("k_new_ben"),fmt(_nb),BL_D,T("k_beneficiaries")+f" {pct(_nb,_bn)}"),
        ("\u2696\uFE0F",T("k_avg_serv_ben"),f"{M('Service / Ben'):,.2f}",BL_NW[2],T("k_services")+"/"+T("k_beneficiaries")),
    ])
    # ===== ② و ③ جدولا العمر/الجنس: 10 أقسام لكل واحد =====
    AGES=[("<5 years","age_0_4"),("5-14 years","age_5_14"),("15-18 years","age_15_18"),
          ("19-49 years","age_19_49"),("50+ years","age_50p")]
    def age_grid(base,title):
        # المجموع المرجعي = عمود Total الرسمي (متسق مع Male+Female)،
        # مو مجموع الشرائح العمرية لأن الشرائح فيها صفوف ناقصة/مكررة
        _bt=S(f"{base} Male Total Male")
        _gt=S(f"{base} Female Total Female")
        _tot=_bt+_gt
        _rhead(title.split()[0],title.split(maxsplit=1)[1] if " " in title else title,BL_M2,
               f'{T("lbl_boys")} <b>{_bt:,.0f}</b> \u00b7 {T("lbl_girls")} <b>{_gt:,.0f}</b> \u00b7 {fmt(_tot)}')
        h=['<table class="agrid"><tr><th class="sex"></th>']
        for a,tk in AGES: h.append(f'<th>{T(tk)}</th>')
        h.append(f'<th class="totcol">{T("lbl_row_total")}</th></tr>')
        for sex,tk,cls,vcls in (("Male",T("lbl_boys"),"boyrow","bv"),("Female",T("lbl_girls"),"girlrow","gv")):
            vals=[S(f"{base} {sex} {a}") for a,_ in AGES]
            st_=S(f"{base} {sex} Total {sex}")   # مرجعي: عمود Total الرسمي
            h.append(f'<tr class="{cls}"><th class="sex">{sex_lab(tk)}</th>')
            for v in vals:
                h.append(f'<td class="{vcls}"><div class="v">{fmt(v)}</div>'
                         f'<div class="a">{pct(v,st_) if st_ else "\u2014"}</div></td>')
            h.append(f'<td class="totcol"><div class="v">{fmt(st_)}</div>'
                     f'<div class="a">100%</div></td></tr>')
        h.append(f'<tr class="grandrow"><th class="sex">{T("grand_total")}</th>')
        for a,_ in AGES:
            h.append(f'<td class="gc"><div class="v">{fmt(sum(S(f"{base} {sx} {a}") for sx in ("Male","Female")))}</div></td>')
        h.append(f'<td class="gc"><div class="v">{fmt(_tot)}</div></td></tr>')
        h.append('</table>')
        st.markdown("".join(h),unsafe_allow_html=True)
        # ===== تحذير صريح: صفوف ماbetنّسجم فيها الشرائح مع المجموع (الداتا ما بتتغير) =====
        def _c(c):
            return pd.to_numeric(fdata[c],errors="coerce").fillna(0) if c in fdata.columns else pd.Series(0.0,index=fdata.index)
        _w=[]
        for _sx,_lb in (("Male",T("lbl_boys")),("Female",T("lbl_girls"))):
            _d=_c(f"{base} {_sx} Total {_sx}")-sum(_c(f"{base} {_sx} {a}") for a,_ in AGES)
            _b=_d[_d!=0]
            if len(_b): _w.append((_lb,len(_b),int(_d.sum())))
        if _w: st.warning(T("warn_band_mismatch").format(x=" · ".join(f"{a}: {b} ({c:+,})" for a,b,c in _w)))
        st.caption(T("lbl_share_note"))
    age_grid("Consultations / Visits","\u2461 "+T("bx_cons_age"))
    age_grid("Uniqe Beneficiaries","\u2462 "+T("bx_ben_age"))
    # ===== ④ ثلاثة سلايدات: الجنس + المضيف/النازح + المعاقون =====
    _pw=[S("Disabilities Patients Boys"),S("Disabilities Patients Men"),
         S("Disabilities Patients Girls"),S("Disabilities Patients Women")]
    _rhead("\u2463","\U0001F4CA",T("bx_by_age_gender"),BL_D2,T("ch_host_idp"))
    _c1,_c2,_c3=st.columns(3,gap="medium")
    with _c1:
        st.markdown(f'<div class="ct">{T("ch_gender")}</div>',unsafe_allow_html=True)
        _gsex=[(T("pwd_men"),S("Men")),(T("pwd_women"),S("Women")),
               (T("lbl_boys"),S("Boys")),(T("lbl_girls"),S("Girls"))]
        _show(_donut_fig(_gsex,sex_colors([n for n,_ in _gsex]),T("grand_total"),
                         w=TILE_W,tsize=DP_TSIZE,lfont=DP_LFONT,key_below=DP_KEYBELOW,lmax=DP_LMAX))
    with _c2:
        st.markdown(f'<div class="ct">{T("ch_host_idp")}</div>',unsafe_allow_html=True)
        _show(_donut_fig([(T("p_host"),S("Total Host")),(T("p_idp"),S("Total IDP"))],
                         [BL_M,BL_D],T("grand_total"),
                         w=TILE_W,tsize=DP_TSIZE,lfont=DP_LFONT,key_below=DP_KEYBELOW,lmax=DP_LMAX,explode=.08))
    with _c3:
        st.markdown(f'<div class="ct">{T("bx_pwd")}</div>',unsafe_allow_html=True)
        _pwsx=[(T("pwd_boys"),_pw[0]),(T("pwd_men"),_pw[1]),
               (T("pwd_girls"),_pw[2]),(T("pwd_women"),_pw[3])]
        _show(_donut_fig(_pwsx,sex_colors([n for n,_ in _pwsx]),T("grand_total"),
                         w=TILE_W,tsize=DP_TSIZE,lfont=DP_LFONT,key_below=DP_KEYBELOW,lmax=DP_LMAX))
    # ===== ⑤ بتر الأطراف: قسمان — رقمان فقط =====
    _lo=S("Disabilities Lower limb amputations"); _up=S("Disabilities Upper limb amputation")
    _rhead("\u2464","\U0001F9B5",T("bx_amput"),BL_M,fmt(_lo+_up))
    st.markdown('<div class="mini2">'
                f'<div class="kcard" style="--c:{BL_NW[2]}"><div class="ic">\U0001F9BF</div>'
                f'<div class="lb">{T("amput_lower")}</div><div class="vl">{fmt(_lo)}</div>'
                f'</div>'
                f'<div class="kcard" style="--c:{BL_D}"><div class="ic">\U0001F9BE</div>'
                f'<div class="lb">{T("amput_upper")}</div><div class="vl">{fmt(_up)}</div>'
                f'</div></div>',unsafe_allow_html=True)
    # ===== ⑥ الرسم الكبير: خط زمني شهري بخطّين — بعرض الداشبورد كامل =====
    _rhead("\u2465","\U0001F4C8",T("ch_timeline"),BL_D,T("f_date"))
    if "Date" in fdata.columns and "Consultations / Visits Total" in fdata.columns:
        _g2=pd.DataFrame({"Date":fdata["Date"],
                         "c":pd.to_numeric(fdata["Consultations / Visits Total"],errors="coerce"),
                         "f":1.0 if "Facility Name" in fdata.columns else 0.0})
        _m=_g2.groupby(pd.Grouper(key="Date",freq="MS")).agg(c=("c","sum"),f=("f","sum"))
        _m=_m[_m.index.notna()]
        if _m["c"].sum()>0 or _m["f"].sum()>0:
            fig,ax=_lin_fig()
            ax2=ax.twinx()
            ax2.set_facecolor("none")
            for sp in ax2.spines.values(): sp.set_color(DC_EDGE)
            ax2.tick_params(colors=BL_D,labelsize=DP_FS)
            ax2.yaxis.label.set_color(BL_D)
            ax2.grid(False)
            ax2.yaxis.set_major_locator(MaxNLocator(nbins=5,prune="upper"))
            ax.plot(_m.index,_m["c"],color=BL_M,marker="o",markersize=DP_MS,linewidth=DP_LW,
                    label=T("k_consultations"),zorder=5,
                    markeredgecolor=DC_CARD,markeredgewidth=1)
            ax.fill_between(_m.index,_m["c"],alpha=.16,color=BL_M,zorder=1)
            ax.set_ylabel(T("k_consultations"),color=BL_M,fontsize=DP_FS_LG)
            ax.tick_params(axis="y",labelcolor=BL_M)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5,prune="upper"))
            ax2.plot(_m.index,_m["f"],color=BL_D,marker="s",markersize=DP_MS,linewidth=DP_LW,
                     linestyle="--",label=T("lbl_fac_count"),zorder=4,
                     markeredgecolor=DC_CARD,markeredgewidth=1)
            ax2.set_ylabel(T("lbl_fac_count"),color=BL_D,fontsize=DP_FS_LG)
            ax2.set_ylim(0,max(1.0,float(_m["f"].max())*1.35))
            ax.set_ylim(0,float(_m["c"].max())*1.28 if _m["c"].max()>0 else 1)
            ax.set_title("")
            ax.tick_params(colors=DC_MUT,labelsize=DP_FS)
            h1,l1=ax.get_legend_handles_labels(); h2,l2=ax2.get_legend_handles_labels()
            lg=ax.legend(h1+h2,l1+l2,loc="upper right",fontsize=DP_FS_LG,frameon=True,
                         facecolor=DC_CARD,edgecolor=DC_EDGE,labelcolor=DC_TXT)
            lg.get_frame().set_alpha(.95)
            fig.autofmt_xdate(rotation=25,ha="right")
            fig.subplots_adjust(left=0.075,right=0.93,top=0.965,bottom=0.19)
            _show(fig)
        else: st.info(T("no_values"))
    else: st.info(T("no_values"))
    _dash_foot(_sn)

def dash_g_sg(fdata,alldata):
    # =========================================================================
    # ===== داشبورد العمليات الجراحية (Surgeries) =====
    # هوية لونية: أزرق فقط (فاتح ⇄ غامق) — لا أحمر/أخضر/برتقالي/بنفسجي
    # التخطيط: ٣ مربعات جنب بعض (سلايدات) + الخط بعرض الداشبورد كامل
    # ① دونت صغرى/كبرى + مربع رباعي   ② دائرة أعمار
    # ③ 8 فئات (أعمدة)                ④ خطّان شهرياً
    # =========================================================================
    _k=ss.get("_hhs_key"); _sn=ss.get("_srcname") or ""
    _dash_head(T("g_sg"),fdata,_sn,"\U0001F52A")
    if not len(fdata):
        st.info(T("no_rows_match"))
        _dash_foot(_sn)
        return
    S=lambda c: float(_num(fdata,[c])[c].sum()) if c in fdata.columns else 0.0
    fmt=lambda v: f"{v:,.0f}"
    pct=lambda a,b: f"{(a/b*100):.1f}%" if b else "\u2014"
    def dcard(parts,colors):
        """دونت داخل سلايد: المفتاح تحت الدائرة بعمودين"""
        f=_donut_fig(parts,colors,T("grand_total"),w=TILE_W,tsize=DP_TSIZE,lfont=DP_LFONT,key_below=DP_KEYBELOW,lmax=DP_LMAX)
        if f is not None: _show(f)
        else: st.info(T("no_values"))
    def piecard(parts,colors,center_lab):
        """دائرة كاملة (بلا فراغ بالنص) — المفتاح تحت بعمودين"""
        parts=[(n,v) for n,v in parts if v>0]
        if not parts: st.info(T("no_values")); return
        _tot=float(sum(v for _,v in parts))
        fig,ax=_dark_fig(TILE_W,TILE_H)
        wdg,texts=ax.pie([v for _,v in parts],labels=None,startangle=90,counterclock=False,
                         radius=1.0,colors=colors[:len(parts)],
                         wedgeprops=dict(edgecolor=DC_BG,linewidth=DP_LW))
        ax.set_xlim(-1.06,1.06); ax.set_ylim(-1.06,1.06)
        ax.set_box_aspect(1)                          # دائرة مثالية مو ممدودة
        ax.text(0,0.18,center_lab,ha="center",va="center",color=DC_TXT,
                fontsize=DP_FS_LG,fontweight="900",transform=ax.transData)
        ax.text(0,-0.30,f"{_tot:,.0f}",ha="center",va="center",color=DC_MUT,
                fontsize=DP_FS,fontweight="700",transform=ax.transData)
        _nml=[(str(n)[:15]+"…" if len(str(n))>15 else str(n)) for n,v in parts]
        lg=[f"{n}  {v:,.0f}  ({v/_tot*100:.1f}%)" for n,(_,v) in zip(_nml,parts)]
        # عمود واحد إلا إذا اتسع السطران معاً بعرض السلايد
        _wpx=TILE_W*fig.dpi
        _est=max(len(x) for x in lg)*(10*0.62)
        _ncol=2 if (_est*2+60)<(_wpx*0.94) else 1
        ax.legend(wdg,lg,loc="upper center",bbox_to_anchor=(0.5,-0.02),ncol=_ncol,
                  fontsize=DP_FS_SM,labelcolor=DC_TXT,frameon=False,handlelength=1.0,
                  handletextpad=.5,columnspacing=1.0,labelspacing=.45,borderpad=.15)
        _rows=int(-(-len(lg)//_ncol))
        _bot=min(0.48,0.12+_rows*(10*1.6)/(TILE_H*fig.dpi))
        fig.subplots_adjust(left=0.02,right=0.98,top=1.0-_bot*0.40,bottom=_bot)
        ax.set_title("")
        _show(fig)
    def qcell(head,val,sub,color,share=None):
        return (f'<div class="qcell" style="--c:{color}"><div class="qh">{head}<b>{fmt(val)}</b></div>'
                f'<div class="qv">{fmt(val)}</div>' + _qs_div(sub)
                + f'{_pbar(share if share is not None else 0,color)}</div>')
    # ===== المؤشرات الأساسية =====
    _tot=S("Total surgeries"); _maj=S("Total major"); _min=S("Total minor")
    _war=S("Total war surgeries"); _nowar=S("Total Non war Surgeries")
    # مصدر الملف: مربع رباعي — حربية/غير حربية × صغرى/كبرى
    _mj_w=S("Total Major war");     _mj_n=S("Total Major- Non War")
    _mn_w=S("Total Minor War");     _mn_n=S("Total Minor Non- War")
    # ===== شريط ملخّص: كله بتدرّج أزرق =====
    _kcards([("\U0001F52A",T("grand_total"),fmt(_tot),BL_M,f'{T("rows_label")}: {len(fdata):,}'),
             ("\U0001FA7A",T("sg_major"),fmt(_maj),BL_M2,pct(_maj,_tot)),
             ("\U0001FA7B",T("sg_minor"),fmt(_min),BL_L,pct(_min,_tot)),
             ("\u2694\uFE0F",T("sg_war"),fmt(_war),BL_D,pct(_war,_tot)),
             ("\U0001F54A\uFE0F",T("sg_nowar"),fmt(_nowar),BL_D2,pct(_nowar,_tot))])
    # ===== بيانات الأعمار والفئات =====
    _bands=[(T("sg_under5"),["War related Male <5 years","War related Female <5 years"]),
            (T("sg_5_14"),["War related Male 5-14 years","War related Female 5-14 years"]),
            (T("sg_15_18"),["War related Male 15-18 years","War related Female 15-18 years"]),
            (T("sg_19_49"),["War related Male 19-49 years","War related Female 19-49 years"]),
            (T("sg_50p"),["War related Male 50+ years","War related Female 50+ years"])]
    _age=[(n,sum(S(c) for c in cs)) for n,cs in _bands]
    # الفئات: لون الجنس يحكم — ذكور = أروق فاتح · إناث = أحمر (والأعمدة غير الجنسية رمادي)
    _bars=[(f'{T("sg_nowar")} \u00b7 {T("sg_male")}',S("Non War Men")),
           (f'{T("sg_nowar")} \u00b7 {T("sg_female")}',S("Non-War Women")),
           (f'{T("sg_nowar")} \u00b7 {T("sg_boys")}',S("Non -War boys")),
           (f'{T("sg_nowar")} \u00b7 {T("sg_girls")}',S("Non-War girls")),
           (f'{T("sg_war")} \u00b7 {T("sg_male")}',S("War Men")),
           (f'{T("sg_war")} \u00b7 {T("sg_female")}',S("War Women")),
           (f'{T("sg_war")} \u00b7 {T("sg_boys")}',S("War boys")),
           (f'{T("sg_war")} \u00b7 {T("sg_girls")}',S("War girls"))]
    _bars=[(n,v,sex_color(n)) for n,v in _bars]
    _mt=max([v for _,v,_ in _bars]+[1])
    def mhead(n,icon,title,color,note=""):
        # نفس مكوّن العناوين المستعمل بكل الداشبوردات => هوية بصرية موحّدة
        return _rhead_html(n,icon,title,color,note)
    # ═══════════ سلايد ① : دونت صغرى/كبرى + مربع رباعي + نسبة war ═══════════
    c1,c2,c3=st.columns(3,gap="medium")
    with c1:
        st.markdown('<div class="mbox">'
                    +mhead("\u2460","\U0001F52A",T("sg_minor")+" \u00b7 "+T("sg_major"),BL_M,fmt(_tot))
                    +'</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="ct">{T("sg_minor")} / {T("sg_major")}</div>',unsafe_allow_html=True)
        dcard([(T("sg_minor"),_min),(T("sg_major"),_maj)],[BL_NW[3],BL_D])
        st.markdown('<div class="mbox">'
                    +'<div class="hbox2">'
                    +qcell(f'{T("sg_nowar")} \u00b7 {T("sg_minor")}',_mn_n,pct(_mn_n,_tot),BL_NW[2],
                           _mn_n/_tot*100 if _tot else 0)
                    +qcell(f'{T("sg_nowar")} \u00b7 {T("sg_major")}',_mj_n,pct(_mj_n,_tot),BL_NW[1],
                           _mj_n/_tot*100 if _tot else 0)
                    +qcell(f'{T("sg_war")} \u00b7 {T("sg_minor")}',_mn_w,pct(_mn_w,_tot),BL_W[1],
                           _mn_w/_tot*100 if _tot else 0)
                    +qcell(f'{T("sg_war")} \u00b7 {T("sg_major")}',_mj_w,pct(_mj_w,_tot),BL_D,
                           _mj_w/_tot*100 if _tot else 0)
                    +'</div>'
                    f'<div class="kcard" style="--c:{BL_D};margin-top:8px">'
                    f'<div class="ic">\u2694\uFE0F</div><div class="lb">{T("sg_warpct")}</div>'
                    f'<div class="vl">{pct(_war,_tot)}</div>'
                    f'<div class="sb">{fmt(_war)} / {fmt(_tot)}</div>'
                    f'{_pbar(_war/_tot*100 if _tot else 0,BL_D)}</div>'
                    '</div>',unsafe_allow_html=True)
    # ═══════════ سلايد ② : دائرة كاملة لتوزيع الأعمار ═══════════
    with c2:
        st.markdown('<div class="mbox">'
                    +mhead("\u2461","\U0001F382",T("sg_age_dist"),BL_M2,T("sg_age_sub"))
                    +'</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="ct">{T("sg_age_dist")}</div>',unsafe_allow_html=True)
        piecard(_age,BL_SEQ,T("sg_war"))
    # ═══════════ سلايد ③ : ثمانية أعمدة (تدرّج أزرق فاتح←غامق) ═══════════
    with c3:
        st.markdown('<div class="mbox">'
                    +mhead("\u2462","\U0001F4CA",T("sg_by_gender"),BL_D2,T("grand_total"))
                    +'</div>',unsafe_allow_html=True)
        fig,ax=_dark_fig(TILE_W,TILE_H)
        _x=list(range(len(_bars)))
        ax.bar(_x,[v for _,v,_ in _bars],color=[c for _,_,c in _bars],alpha=.92,width=.66)
        ax.set_xticks(_x)
        ax.set_xticklabels([_lbl(n,16) for n,_,_ in _bars],rotation=30,ha="right",fontsize=DP_FS_SM)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4,prune="upper"))
        ax.tick_params(labelsize=DP_FS_SM)
        ax.set_ylim(0,_mt*1.34)
        for i,(_,v,_) in enumerate(_bars):
            ax.text(i,v+_mt*0.025,fmt(v),ha="center",va="bottom",color=DC_TXT,
                    fontsize=DP_FS_SM,fontweight="700")
        ax.set_title("")
        fig.subplots_adjust(left=0.145,right=0.985,top=0.97,bottom=0.30)
        _show(fig)
    # ═══════════ الخط ④ : خطّان شهرياً — بعرض الداشبورد كامل ═══════════
    st.markdown('<div class="mbox">'
                +mhead("\u2463","\U0001F4C8",T("sg_monthly"),BL_M,T("rows_label"))
                +'</div>',unsafe_allow_html=True)
    _done=False
    if "Date" in fdata.columns and len(fdata):
        _g=pd.DataFrame({"Date":fdata["Date"],
                         "nw":pd.to_numeric(fdata["Total Non war Surgeries"],errors="coerce"),
                         "wr":pd.to_numeric(fdata["Total war surgeries"],errors="coerce")})
        _m=_g.groupby(pd.Grouper(key="Date",freq="MS"))[["nw","wr"]].sum()
        _m=_m[_m.index.notna()]
        if len(_m) and float(_m[["nw","wr"]].sum().sum())>0:
            fig,ax=_dark_fig(PG_W,LINE_H)
            ax.plot(_m.index,_m["nw"],color=BL_M,marker="o",markersize=DP_MS,linewidth=DP_LW,
                    label=T("sg_nowar"),markeredgecolor=DC_CARD,markeredgewidth=1)
            ax.plot(_m.index,_m["wr"],color=BL_D,marker="s",markersize=DP_MS,linewidth=DP_LW,
                    label=T("sg_war"),markeredgecolor=DC_CARD,markeredgewidth=1)
            ax.fill_between(_m.index,_m["nw"],alpha=.12,color=BL_M)
            ax.set_title("")
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5,prune="upper"))
            ax.tick_params(labelsize=DP_FS_SM)
            ax.set_ylim(0,max(1.0,float(_m["nw"].max()))*1.42)
            lg=ax.legend(loc="upper left",fontsize=DP_FS,frameon=True,facecolor=DC_CARD,
                         edgecolor=DC_EDGE,labelcolor=DC_TXT,ncol=2)
            lg.get_frame().set_alpha(.95)
            fig.autofmt_xdate(rotation=25,ha="right")
            fig.subplots_adjust(left=0.075,right=0.985,top=0.965,bottom=0.19)
            _show(fig); _done=True
    if not _done: st.info(T("no_values"))
    _dash_foot(_sn)

def dash_g_de(fdata,alldata):
    # =========================================================================
    # ===== داشبورد خدمات الأسنان (Dental Services) =====
    # هوية لونية: أزرق فقط (فاتح ⇄ غامق)
    # ① شريط مؤشرات: المستفيدون + الاستشارات + الإجراءات
    # ② ثلاثة سلايدات: استشارات/إجراءات · دونت الجنس · ٥ فئات عمرية
    # ③ خط شهري لمستفيدي الأسنان — بعرض الداشبورد كامل
    # =========================================================================
    _sn=ss.get("_srcname") or ""
    _dash_head(T("g_de"),fdata,_sn,"\U0001F9B7")
    if not len(fdata):
        st.info(T("no_rows_match"))
        _dash_foot(_sn)
        return
    S=lambda c: float(_num(fdata,[c])[c].sum()) if c in fdata.columns else 0.0
    fmt=lambda v: f"{v:,.0f}"
    pct=lambda a,b: f"{(a/b*100):.1f}%" if b else "\u2014"
    def mhead(n,icon,title,color,note=""):
        # نفس مكوّن العناوين المستعمل بكل الداشبوردات => هوية بصرية موحّدة
        return _rhead_html(n,icon,title,color,note)
    # ===== المؤشرات =====
    _ben=S("Total dental Ben")
    _con=S("Dental consultations")
    _pro=S("Dental procedures")
    _mal=S("Dental Beneficiaries Male Total Male")
    _fem=S("Dental Beneficiaries Female Total Female")
    # ═══════════ ① شريط المؤشرات — كله بتدرّج أزرق ═══════════
    _kcards([("\U0001F9B7",T("de_ben_gender").split("\u00b7")[0].strip() or "Dental Beneficiaries",
              fmt(_ben),BL_M,f'{T("rows_label")}: {len(fdata):,}'),
             ("\U0001F4CA",T("de_consultations"),fmt(_con),BL_M2,pct(_con,_ben)),
             ("\U0001FA7A",T("de_procedures"),fmt(_pro),BL_L,pct(_pro,_ben)),
             ("\u2642\uFE0F",T("de_male"),fmt(_mal),SEX_M,pct(_mal,_ben)),
             ("\u2640\uFE0F",T("de_female"),fmt(_fem),SEX_F,pct(_fem,_ben))])
    # ===== الفئات العمرية (٥ فئات) =====
    _bands=[(T("sg_under5"),"<5 years"),(T("sg_5_14"),"5-14 years"),
            (T("sg_15_18"),"15-18 years"),(T("sg_19_49"),"19-49 years"),
            (T("sg_50p"),"50+ years")]
    _age=[]
    for lab,suf in _bands:
        _age.append((lab,S(f"Dental Beneficiaries Male {suf}"),
                        S(f"Dental Beneficiaries Female {suf}")))
    _mt=max([max(m_,f_) for _,m_,f_ in _age]+[1.0])
    # ═══════════ ② ثلاثة سلايدات جنب بعض ═══════════
    c1,c2,c3=st.columns(3,gap="medium")
    # ── سلايد ① : الاستشارات مقابل الإجراءات ──
    with c1:
        st.markdown('<div class="mbox">'
                    +mhead("\u2460","\U0001F52A",T("de_svc"),BL_M,fmt(_con+_pro))
                    +'</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="ct">{T("de_svc")}</div>',unsafe_allow_html=True)
        f=_donut_fig([(T("de_consultations"),_con),(T("de_procedures"),_pro)],
                     [BL_L,BL_D],T("grand_total"),w=TILE_W,tsize=DP_TSIZE,lfont=DP_LFONT,
                     key_below=DP_KEYBELOW,lmax=DP_LMAX)
        if f is not None: _show(f)
        else: st.info(T("no_values"))
    # ── سلايد ② : دونت مستفيدي الأسنان حسب الجنس ──
    with c2:
        st.markdown('<div class="mbox">'
                    +mhead("\u2461","\U0001F9B7",T("de_ben_gender"),BL_M2,fmt(_ben))
                    +'</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="ct">{T("de_ben_gender")}</div>',unsafe_allow_html=True)
        _parts=[(T("de_male"),_mal),(T("de_female"),_fem)]
        _parts=[(n,v) for n,v in _parts if v>0]
        if not _parts:
            st.info(T("no_values"))
        else:
            _tp=float(sum(v for _,v in _parts))
            fig,ax=_dark_fig(TILE_W,TILE_H)
            wdg,texts=ax.pie([v for _,v in _parts],labels=None,startangle=90,
                             counterclock=False,radius=1.0,
                             colors=[sex_color(n) for n,_ in _parts],
                             wedgeprops=dict(edgecolor=DC_BG,linewidth=DP_LW))
            ax.set_xlim(-1.06,1.06); ax.set_ylim(-1.06,1.06)
            ax.set_box_aspect(1)                       # دائرة مثالية مو ممدودة
            ax.text(0,0.18,T("grand_total"),ha="center",va="center",color=DC_TXT,
                    fontsize=DP_FS_LG,fontweight="900",transform=ax.transData)
            ax.text(0,-0.30,f"{_tp:,.0f}",ha="center",va="center",color=DC_MUT,
                    fontsize=DP_FS,fontweight="700",transform=ax.transData)
            _lg=[f"{n}  {v:,.0f}  ({v/_tp*100:.1f}%)" for n,v in _parts]
            _wpx=TILE_W*fig.dpi
            _est=max(len(x) for x in _lg)*(10*0.62)
            _ncol=2 if (_est*2+60)<(_wpx*0.94) else 1
            ax.legend(wdg,_lg,loc="upper center",bbox_to_anchor=(0.5,-0.02),ncol=_ncol,
                      fontsize=DP_FS_SM,labelcolor=DC_TXT,frameon=False,handlelength=1.0,
                      handletextpad=.5,columnspacing=1.0,labelspacing=.45,borderpad=.15)
            _rws=int(-(-len(_lg)//_ncol))
            _bot=min(0.48,0.12+_rws*(10*1.6)/(TILE_H*fig.dpi))
            fig.subplots_adjust(left=0.02,right=0.98,top=1.0-_bot*0.40,bottom=_bot)
            ax.set_title("")
            _show(fig)
    # ── سلايد ③ : ٥ فئات عمرية × ذكر/أنثى (أعداد فقط) ──
    with c3:
        st.markdown('<div class="mbox">'
                    +mhead("\u2462","\U0001F4CA",T("de_ben_age"),BL_D2,fmt(_ben))
                    +'</div>',unsafe_allow_html=True)
        fig,ax=_dark_fig(TILE_W,TILE_H)
        _x=list(range(len(_age)))
        _w=0.38
        _mv=[v for _,m_,f_ in _age for v in (m_,f_)]
        _pk=max(_mv+[1.0])
        ax.bar([i-_w/2 for i in _x],[m_ for _,m_,_ in _age],width=_w,
               color=SEX_M,alpha=.95,label=sex_lab(T("de_male")))
        ax.bar([i+_w/2 for i in _x],[f_ for _,_,f_ in _age],width=_w,
               color=SEX_F,alpha=.95,label=sex_lab(T("de_female")))
        ax.set_xticks(_x)
        ax.set_xticklabels([_lbl(n,14) for n,_,_ in _age],rotation=28,ha="right",fontsize=DP_FS_SM)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4,prune="upper"))
        ax.tick_params(labelsize=DP_FS_SM)
        ax.set_ylim(0,_pk*1.30)
        for i,(_,m_,f_) in enumerate(_age):
            if m_: ax.text(i-_w/2,m_+_pk*0.025,fmt(m_),ha="center",va="bottom",
                           color=DC_TXT,fontsize=DP_FS_SM,fontweight="700")
            if f_: ax.text(i+_w/2,f_+_pk*0.025,fmt(f_),ha="center",va="bottom",
                           color=DC_TXT,fontsize=DP_FS_SM,fontweight="700")
        lg=ax.legend(loc="upper center",bbox_to_anchor=(0.5,-0.30),ncol=2,fontsize=DP_FS_SM,
                     frameon=False,labelcolor=DC_TXT,handlelength=1.0)
        ax.set_title("")
        fig.subplots_adjust(left=0.145,right=0.985,top=0.97,bottom=0.335)
        _show(fig)
    # ═══════════ ③ الخط : Dental Ben by Time — بعرض الداشبورد كامل ═══════════
    st.markdown('<div class="mbox">'
                +mhead("\u2463","\U0001F4C8",T("de_ben_time"),BL_M,T("rows_label"))
                +'</div>',unsafe_allow_html=True)
    _done=False
    if "Date" in fdata.columns and len(fdata):
        _g=pd.DataFrame({"Date":fdata["Date"],
                         "ben":pd.to_numeric(fdata["Total dental Ben"],errors="coerce"),
                         "con":pd.to_numeric(fdata["Dental consultations"],errors="coerce"),
                         "pro":pd.to_numeric(fdata["Dental procedures"],errors="coerce")})
        _m=_g.groupby(pd.Grouper(key="Date",freq="MS"))[["ben","con","pro"]].sum(min_count=1)
        _m=_m[_m.index.notna()]
        if len(_m) and float(_m[["ben","con","pro"]].sum().sum())>0:
            fig,ax=_dark_fig(PG_W,LINE_H)
            _style=[("ben",BL_M,"o",T("de_ben_gender").split("\u00b7")[0].strip()),
                    ("con",BL_M2,"s",T("de_consultations")),
                    ("pro",BL_D,"^",T("de_procedures"))]
            for k,c,mk,lb in _style:
                ax.plot(_m.index,_m[k],color=c,marker=mk,markersize=DP_MS,linewidth=DP_LW,
                        label=lb,markeredgecolor=DC_CARD,markeredgewidth=1)
                ax.fill_between(_m.index,_m[k],alpha=.10,color=c)
            ax.set_title("")
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5,prune="upper"))
            ax.tick_params(labelsize=DP_FS_SM)
            ax.set_ylim(0,max(1.0,float(_m.max().max()))*1.34)
            lg=ax.legend(loc="upper left",fontsize=DP_FS,frameon=True,facecolor=DC_CARD,
                         edgecolor=DC_EDGE,labelcolor=DC_TXT,ncol=3)
            lg.get_frame().set_alpha(.95)
            fig.autofmt_xdate(rotation=25,ha="right")
            fig.subplots_adjust(left=0.075,right=0.985,top=0.965,bottom=0.19)
            _show(fig); _done=True
    if not _done: st.info(T("no_values"))
    _dash_foot(_sn)

# ===== تدرّجات زرقاء للفنات العمرية: كل لون = عمر وجنس واحد =====
# الذكور أغمق شوي من الإناث، مع إنو كلهم أزرق (هوية الداشبورد)
# ألوان الفئات العمرية حسب الجنس: ذكور = تدرّج أروق فاتح · إناث = تدرّج أحمر
_TR_MALE=["#22c55e","#4ade80","#86efac","#a7f3d0","#bbf7d0"]
_TR_FEM =["#dc2626","#ef4444","#f87171","#fca5a5","#fecaca"]
# تدرّج أزرق بتباين واضح بين كل خطوة والتانية (بعيد كل ما يختلط)
BL_DIST=["#e0f2fe","#93c5fd","#4f9dfb","#1d7fe0","#2b5fd9","#1e40af","#16237d","#0d1550"]
# لون متباعد للمقطع رقم i: خطوتان بالتدرّج حتى ما يتشابهوا مع بعض
def _dist_color(i):
    return BL_DIST[(int(i)*2)%len(BL_DIST)]

def dash_g_tr(fdata,alldata):
    # =========================================================================
    # ===== داشبورد الجروح (Trauma & War Related) =====
    # هوية لونية: أزرق فقط (فاتح ⇄ غامق)
    # ① مربعان: استشارات الجروح + war related
    # ② مستطيل أفقي: إناث/ذكور حسب ٥ فئات عمرية (كل لون = عمر وجنس)
    #    + دونت: النسبة المئوية لـ war related
    # ③ خط شهري: استشارات الجروح و war related
    # =========================================================================
    _sn=ss.get("_srcname") or ""
    _dash_head(T("g_tr"),fdata,_sn,"\U0001FA7A")
    if not len(fdata):
        st.info(T("no_rows_match"))
        _dash_foot(_sn)
        return
    S=lambda c: float(_num(fdata,[c])[c].sum()) if c in fdata.columns else 0.0
    fmt=lambda v: f"{v:,.0f}"
    pct=lambda a,b: f"{(a/b*100):.1f}%" if b else "\u2014"
    def mhead(n,icon,title,color,note=""):
        return _rhead_html(n,icon,title,color,note)
    # ===== المؤشرات =====
    _tr=S("Trauma consultations Total")
    _war=S("War related Total War")
    # ═══════════ ① مربع واحد: رقمان — استشارات الجروح و war related ═══════════
    _twobox(T("tr_trauma"),fmt(_tr),BL_M,T("tr_war"),fmt(_war),BL_D)
    # ===== الفئات العمرية (٥) × جنس =====
    _bands=[(T("sg_under5"),"<5 years"),(T("sg_5_14"),"5-14 years"),
            (T("sg_15_18"),"15-18 years"),(T("sg_19_49"),"19-49 years"),
            (T("sg_50p"),"50+ years")]
    _bars=[]   # (نص, قيمة, لون)
    for _i,(_lab,_sfx) in enumerate(_bands):
        _bars.append((f'{T("tr_male")} · {_lab}',S(f"Trauma consultations Male {_sfx}"),_TR_MALE[_i]))
    for _i,(_lab,_sfx) in enumerate(_bands):
        _bars.append((f'{T("tr_female")} · {_lab}',S(f"Trauma consultations Female {_sfx}"),_TR_FEM[_i]))
    _bars=[(n,v,c) for n,v,c in _bars if v>0]
    _pk=max([v for _,v,_ in _bars]+[1.0])
    # ═══════════ ② + ③ جنب بعض: مستطيل الأعمار (يسار) + دونت war related (يمين) ═══════════
    _cA,_cB,__p1,__p2=st.columns([0.5,1,1,0.5],gap="medium")
    # ── ② مستطيل أفقي — إناث/ذكور حسب الفئة العمرية، كل لون = عمر وجنس ──
    with _cA:
        st.markdown('<div class="mbox">'
                    +mhead("\u2460","\U0001F4CA",T("tr_age_gender"),BL_M2,fmt(_tr))
                    +'</div>',unsafe_allow_html=True)
        if not _bars:
            st.info(T("no_values"))
        else:
            fig,ax=_dark_fig(DP_W,LINE_H)
            _y=list(range(len(_bars)))[::-1]
            ax.barh(_y,[v for _,v,_ in _bars],height=0.66,
                    color=[c for _,_,c in _bars],alpha=.96,edgecolor=DC_CARD,linewidth=DP_LW)
            ax.set_yticks(_y)
            ax.set_yticklabels([_lbl(n,12) for n,_,_ in _bars],fontsize=DP_FS_SM)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
            ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
            ax.tick_params(labelsize=DP_FS_SM)
            ax.set_xlim(0,_pk*1.16)
            _xt=[t for t in ax.get_xticks() if 0<=t<=_pk*1.16]   # لا ticks خارج المحور
            ax.set_xticks(_xt)
            ax.grid(color=DC_EDGE,alpha=.35,axis="x")
            ax.set_axisbelow(True)
            for _y0,(_,v,_) in zip(_y,_bars):
                ax.text(v+_pk*0.012,_y0,fmt(v),va="center",ha="left",
                        color=DC_TXT,fontsize=DP_FS_SM,fontweight="700")
            ax.set_title("")
            fig.subplots_adjust(left=0.315,right=0.965,top=0.975,bottom=0.135)
            _show(fig)
    # ── ③ دونت: النسبة المئوية لـ war related ──
    with _cB:
        st.markdown('<div class="mbox">'
                    +mhead("\u2461","\U0001F534",T("tr_war_pct"),BL_D2,fmt(_war))
                    +'</div>',unsafe_allow_html=True)
        # النسبة المئوية: war related من إجمالي استشارات الجروح
        _rest=max(0.0,_tr-_war)
        _parts=[]
        if _war>0: _parts.append((T("tr_war"),_war,BL_D))
        if _rest>0: _parts.append((T("tr_nonwar"),_rest,BL_L))
        if not _parts:
            st.info(T("no_values"))
        else:
            # الدونت على يسار العرض الكامل والمفتاح يمينه => ما بينقصّ أبداً
            _pc=f"{(_war/_tr*100):.1f}%" if _tr else "\u2014"
            f=_donut_fig([(n,v) for n,v,_ in _parts],[c for _,_,c in _parts],_pc,
                         hole=.42,explode=.05,tsize=DP_TSIZE,w=DP_W,lfont=DP_LFONT,
                         key_below=DP_KEYBELOW,lmax=DP_LMAX)
            if f is not None: _show(f)
    # ═══════════ ④ الخط الشهري — بعرض الداشبورد كامل ═══════════
    st.markdown('<div class="mbox">'
                +mhead("\u2462","\U0001F4C8",T("tr_by_time"),BL_M,T("f_month"))
                +'</div>',unsafe_allow_html=True)
    _done=False
    if "Date" in fdata.columns and len(fdata):
        _g=pd.DataFrame({"Date":fdata["Date"],
                         "tr":pd.to_numeric(fdata["Trauma consultations Total"],errors="coerce"),
                         "war":pd.to_numeric(fdata["War related Total War"],errors="coerce")})
        _m=_g.groupby(pd.Grouper(key="Date",freq="MS"))[["tr","war"]].sum(min_count=1)
        _m=_m[_m.index.notna()]
        if len(_m) and float(_m[["tr","war"]].sum().sum())>0:
            fig,ax=_dark_fig(PG_W,LINE_H)
            for k,c,mk,lb in (("tr",BL_M,"o",T("tr_trauma")),("war",BL_D,"s",T("tr_war"))):
                ax.plot(_m.index,_m[k],color=c,marker=mk,markersize=DP_MS,linewidth=DP_LW,
                        label=lb,markeredgecolor=DC_CARD,markeredgewidth=1)
                ax.fill_between(_m.index,_m[k],alpha=.10,color=c)
            ax.set_title("")
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5,prune="upper"))
            ax.tick_params(labelsize=DP_FS_SM)
            ax.set_ylim(0,max(1.0,float(_m.max().max()))*1.34)
            lg=ax.legend(loc="upper left",fontsize=DP_FS,frameon=True,facecolor=DC_CARD,
                         edgecolor=DC_EDGE,labelcolor=DC_TXT,ncol=2)
            lg.get_frame().set_alpha(.95)
            fig.autofmt_xdate(rotation=25,ha="right")
            fig.subplots_adjust(left=0.075,right=0.985,top=0.965,bottom=0.19)
            _show(fig); _done=True
    if not _done: st.info(T("no_values"))
    _dash_foot(_sn)

def dash_g_chw(fdata,alldata):
    # =========================================================================
    # ===== داشبورد العامل الصحي المجتمعي (CHW) =====
    # هوية لونية: أزرق فقط (فاتح ⇄ غامق) — نفس داشبورد العمليات الجراحية
    # الدونتات بسلايدات بثلث العرض، والخطوط الزمنية بعرض الداشبورد كامل
    # ① التثقيف الصحي  ② IYCF  ③ فحص سوء التغذية  ④ التحويلات
    # ⑤ SAM/MAM  ⑥ المستفيدون عبر الزمن  ⑦ SAM/MAM عبر الزمن
    # =========================================================================
    _k=ss.get("_hhs_key"); _sn=ss.get("_srcname") or ""
    _dash_head(T("g_chw"),fdata,_sn,"\U0001F3E0")
    if not len(fdata):
        st.info(T("no_rows_match"))
        _dash_foot(_sn)
        return
    # ===== مطابقة أسماء أعمدة CHW: مصدر الملف فيه مسافاتال طرفية و/MS ======
    _cols={re.sub(r"\s+"," ",str(c)).strip().lower():c for c in fdata.columns}
    def C(*names):
        """أول اسم عمود موجود (يطابق مع تجاهل المسافات)"""
        for n in names:
            _hit=_cols.get(re.sub(r"\s+"," ",str(n)).strip().lower())
            if _hit: return _hit
        return ""
    MS=C("CHWs messages ","CHW messages ","CHWs messages","CHW messages")
    def S(c):
        """مجموع عمود — بأمان إن كان الاسم غير موجود أو ناقص"""
        c=C(c) if c and str(c).strip() else ""
        if not c: return 0.0
        return float(_num(fdata,[c])[c].sum()) if c in fdata.columns else 0.0
    fmt=lambda v: f"{v:,.0f}"
    pct=lambda a,b: f"{(a/b*100):.1f}%" if b else "\u2014"
    def dcard(title,parts,colors):
        """دونت داخل سلايد: المفتاح تحت الدائرة"""
        st.markdown(f'<div class="ct">{title}</div>',unsafe_allow_html=True)
        f=_donut_fig(parts,colors,T("grand_total"),w=TILE_W,tsize=DP_TSIZE,lfont=DP_LFONT,key_below=DP_KEYBELOW,lmax=DP_LMAX)
        if f is not None: _show(f)
        else: st.info(T("no_values"))
    def piecard(title,parts,colors,center_lab):
        """دائرة كاملة داخل سلايد"""
        parts=[(n,v) for n,v in parts if v>0]
        st.markdown(f'<div class="ct">{title}</div>',unsafe_allow_html=True)
        if not parts: st.info(T("no_values")); return
        _tot=float(sum(v for _,v in parts))
        fig,ax=_dark_fig(TILE_W,TILE_H)
        wdg,_t=ax.pie([v for _,v in parts],labels=None,startangle=90,counterclock=False,
                      radius=1.0,colors=colors[:len(parts)],
                      wedgeprops=dict(edgecolor=DC_BG,linewidth=DP_LW))
        ax.set_xlim(-1.06,1.06); ax.set_ylim(-1.06,1.06)
        ax.set_box_aspect(1)                          # دائرة مثالية مو ممدودة
        ax.text(0,0.18,center_lab,ha="center",va="center",color=DC_TXT,
                fontsize=DP_FS_LG,fontweight="900",transform=ax.transData)
        ax.text(0,-0.30,f"{_tot:,.0f}",ha="center",va="center",color=DC_MUT,
                fontsize=DP_FS_SM,fontweight="700",transform=ax.transData)
        _nml=[(str(n)[:15]+"…" if len(str(n))>15 else str(n)) for n,v in parts]
        lg=[f"{n}  {v:,.0f}  ({v/_tot*100:.1f}%)" for n,(_,v) in zip(_nml,parts)]
        # عمود واحد إلا إذا اتسع السطران معاً بعرض السلايد (تقدير متحفّظ: الخط الفعلي + المقبض)
        _fs=DP_FS_SM
        _wpx=TILE_W*fig.dpi
        _est=max(len(x) for x in lg)*(_fs*0.66)+40
        _ncol=2 if (_est*2+70)<(_wpx*0.92) else 1
        ax.legend(wdg,lg,loc="upper center",bbox_to_anchor=(0.5,-0.02),ncol=_ncol,
                  fontsize=_fs,labelcolor=DC_TXT,frameon=False,handlelength=1.0,
                  handletextpad=.5,columnspacing=.9,labelspacing=.45,borderpad=.15)
        _rows=int(-(-len(lg)//_ncol))
        _bot=min(0.48,0.12+_rows*(_fs*1.7)/(TILE_H*fig.dpi))
        fig.subplots_adjust(left=0.02,right=0.98,top=1.0-_bot*0.40,bottom=_bot)
        ax.set_title(""); _show(fig)
    def qcell(head,val,sub,color,share=None):
        return (f'<div class="qcell" style="--c:{color}"><div class="qh">{head}<b>{fmt(val)}</b></div>'
                f'<div class="qv">{fmt(val)}</div>' + _qs_div(sub)
                + f'{_pbar(share if share is not None else 0,color)}</div>')
    def mhead(n,icon,title,color,note=""):
        # نفس مكوّن العناوين المستعمل بكل الداشبوردات => هوية بصرية موحّدة
        return _rhead_html(n,icon,title,color,note)
    # ===== المؤشرات =====
    _hh=S("CHW # Household visits ")
    _setA=[(T("pwd_men"),S(MS+"Men")),(T("pwd_women"),S(MS+"Women")),
           (T("lbl_boys"),S(MS+"Boy")),(T("lbl_girls"),S(MS+"Girls"))]
    _setB=[(T("pwd_men"),S(MS+"Men2")),(T("pwd_women"),S(MS+"Women3")),
           (T("lbl_boys"),S(MS+"Boy4")),(T("lbl_girls"),S(MS+"Girls5"))]
    _reachA=sum(v for _,v in _setA); _reachB=sum(v for _,v in _setB)
    _iycf=S("IYCF Messages")
    _cu5m=S("CHWs cummunity screening for Malnutrition <5 years Male")
    _cu5f=S("CHWs cummunity screening for Malnutrition <5 years Female")
    _plws=S("CHW PLWs ")
    _cu5=S("CHW screened CU5"); _screened=S("CHW Screened total")
    _sam=S("CHW SAM "); _mam=S("CHW MAM "); _cases=_sam+_mam
    _ref=S("CHW Refferals ")
    # ══════════ شريط المؤشرات (تدرّج أزرق) ══════════
    _kcards([("\U0001F3E0",T("chw_hh"),fmt(_hh),BL_M,T("rows_label")+f": {len(fdata):,}"),
             ("\U0001F4AC",T("chw_reach"),fmt(_reachA),BL_M2,T("chw_reach4")),
             ("\U0001F37C",T("chw_iycf"),fmt(_iycf),BL_NW[1],T("grand_total")),
             ("\U0001F9CA",T("chw_sammam"),fmt(_cases),BL_D2,pct(_cases,_cu5) if _cu5 else "\u2014"),
             ("\U0001F4E8",T("chw_ref"),fmt(_ref),BL_D,pct(_ref,_screened))])
    # ══════════ ① التثقيف الصحي  ② IYCF  ③ فحص سوء التغذية ══════════
    _rhead("\u2460","\U0001F4AC",T("chw_reach")+" \u00b7 "+T("chw_iycf")+" \u00b7 "+T("chw_screen"),
           BL_M2,f'{T("chw_reach")} {fmt(_reachA)} \u00b7 {T("chw_iycf")} {fmt(_iycf)}')
    _a1,_a2,_a3=st.columns(3,gap="medium")
    with _a1:
        st.markdown('<div class="mbox">'
                    +mhead("\u2460","\U0001F3E0",T("chw_hh"),BL_M,T("chw_hhben"))+'</div>',
                    unsafe_allow_html=True)
        dcard(T("chw_reach4"),_setA,sex_colors([n for n,_ in _setA]))
    with _a2:
        st.markdown('<div class="mbox">'
                    +mhead("\u2461","\U0001F37C",T("chw_iycf"),BL_D2,fmt(_iycf))+'</div>',
                    unsafe_allow_html=True)
        dcard(T("chw_iycf4"),_setB,sex_colors([n for n,_ in _setB]))
    with _a3:
        st.markdown('<div class="mbox">'
                    +mhead("\u2462","\U0001F9CA",T("chw_screen"),BL_D,T("chw_cu5n")+" "+fmt(_cu5))+'</div>',
                    unsafe_allow_html=True)
        dcard(T("chw_screen"),
              [(T("chw_cu5m"),_cu5m),(T("chw_cu5f"),_cu5f),(T("chw_plws"),_plws)],
              sex_colors([T("chw_cu5m"),T("chw_cu5f"),T("chw_plws")]))
    # ══════════ ④ التحويلات  ⑤ SAM/MAM  ⑥ نسبة الحالات ══════════
    _rhead("\u2463","\U0001F4E8",T("chw_ref")+" \u00b7 "+T("chw_sammam")+" \u00b7 "+T("chw_case_ratio"),
           BL_D,f'{T("chw_ref")} {fmt(_ref)} \u00b7 {T("s_sam")} {fmt(_sam)} \u00b7 {T("s_mam")} {fmt(_mam)}')
    _b1,_b2,_b3=st.columns(3,gap="medium")
    with _b1:
        st.markdown(f'<div class="ct">{T("chw_ref")}</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="kcard" style="--c:{BL_D}"><div class="ic">\U0001F4E8</div>'
                    f'<div class="lb">{T("chw_ref")}</div><div class="vl">{fmt(_ref)}</div>'
                    f'<div class="sb">{T("chw_screen")}: {fmt(_screened)}</div>'
                    f'{_pbar(_ref/max(1.0,_screened)*100,BL_D)}</div>',unsafe_allow_html=True)
    with _b2:
        piecard(T("chw_sammam"),[(T("s_sam"),_sam),(T("s_mam"),_mam)],[BL_D2,BL_M],T("chw_sammam"))
    with _b3:
        piecard(T("chw_case_ratio"),[(T("chw_sammam"),_cases),
                                     (T("s_ok"),max(0.0,_cu5-_cases))],
                [BL_D,BL_NW[1]],pct(_cases,_cu5) if _cu5 else "\u2014")
    st.markdown('<div class="hbox8">'
                +qcell(T("s_sam"),_sam,pct(_sam,_cases) if _cases else "\u2014",BL_D2,_sam/_cu5*100 if _cu5 else 0)
                +qcell(T("s_mam"),_mam,pct(_mam,_cases) if _cases else "\u2014",BL_M2,_mam/_cu5*100 if _cu5 else 0)
                +qcell(T("chw_case_ratio"),_cases,
                       f'{pct(_cases,_cu5)} \u00b7 {T("chw_cu5n")} {fmt(_cu5)}',
                       BL_D,_cases/_cu5*100 if _cu5 else 0)
                +qcell(T("chw_cu5n"),_cu5,f'{T("chw_screen")}: {fmt(_screened)}',
                       BL_NW[1],_cu5/_screened*100 if _screened else 0)
                +'</div>',unsafe_allow_html=True)
    # ══════════ ⑦ المستفيدون عبر الزمن  ⑧ SAM/MAM عبر الزمن — بعرض الداشبورد ══════════
    if "Date" in fdata.columns and len(fdata):
        def mser(names):
            _real=[C(x) for x in names]
            _real=[x for x in _real if x]
            if not _real: return pd.DataFrame()
            _g=pd.DataFrame({"Date":fdata["Date"]})
            for c in _real: _g[c]=pd.to_numeric(fdata[c],errors="coerce")
            _m=_g.groupby(pd.Grouper(key="Date",freq="MS"))[_real].sum()
            _m=_m[_m.index.notna()]
            _m.columns=[str(x).strip() for x in _m.columns]
            return _m
        _ra=mser([MS+"Men",MS+"Women",MS+"Boy",MS+"Girls"]); _ra["tot"]=_ra.sum(axis=1)
        _rb=mser([MS+"Men2",MS+"Women3",MS+"Boy4",MS+"Girls5"]); _rb["tot"]=_rb.sum(axis=1)
        _rs=mser(["CHW SAM ","CHW MAM "])
        # ⑦ المستفيدون: التثقيف الصحي مقابل IYCF
        _rhead("\u2464","\U0001F4C8",T("chw_reach_t"),T("chw_reach")+" \u00b7 "+T("chw_iycf"),BL_M2)
        if len(_ra) and float(_ra["tot"].sum())>0:
            st.markdown(f'<div class="ct">{T("chw_reach_t")}</div>',unsafe_allow_html=True)
            fig,ax=_lin_fig()
            ax.plot(_ra.index,_ra["tot"],color=BL_M,marker="o",markersize=DP_MS,linewidth=DP_LW,
                    label=T("chw_reach"),markeredgecolor=DC_CARD,markeredgewidth=1)
            if len(_rb) and float(_rb["tot"].sum())>0:
                ax.plot(_rb.index,_rb["tot"],color=BL_D,marker="s",markersize=DP_MS,linewidth=DP_LW,
                        linestyle="--",label=T("chw_iycf"),markeredgecolor=DC_CARD,markeredgewidth=1)
            ax.fill_between(_ra.index,_ra["tot"],alpha=.12,color=BL_M)
            ax.set_title("")
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5,prune="upper"))
            ax.tick_params(labelsize=DP_FS)
            ax.set_ylim(0,max(1.0,float(_ra["tot"].max()))*1.42)
            lg=ax.legend(loc="upper left",fontsize=DP_FS_LG,frameon=True,facecolor=DC_CARD,
                         edgecolor=DC_EDGE,labelcolor=DC_TXT)
            lg.get_frame().set_alpha(.95)
            fig.autofmt_xdate(rotation=25,ha="right")
            fig.subplots_adjust(left=0.075,right=0.985,top=0.965,bottom=0.19)
            _show(fig)
        else: st.info(T("no_values"))
        # ⑧ SAM و MAM عبر الزمن
        _rhead("\u2465","\U0001F95B",T("chw_sam_t"),T("s_sam")+" \u00b7 "+T("s_mam"),BL_D)
        _cs,_cm="CHW SAM","CHW MAM"
        if len(_rs) and float(_rs[[_cs,_cm]].sum().sum())>0:
            st.markdown(f'<div class="ct">{T("chw_sam_t")}</div>',unsafe_allow_html=True)
            fig,ax=_lin_fig()
            ax.plot(_rs.index,_rs[_cs],color=BL_D,marker="o",markersize=DP_MS,linewidth=DP_LW,
                    label=T("s_sam"),markeredgecolor=DC_CARD,markeredgewidth=1)
            ax.plot(_rs.index,_rs[_cm],color=BL_M,marker="s",markersize=DP_MS,linewidth=DP_LW,
                    label=T("s_mam"),markeredgecolor=DC_CARD,markeredgewidth=1)
            ax.fill_between(_rs.index,_rs[_cs],alpha=.12,color=BL_D)
            ax.set_title("")
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5,prune="upper"))
            ax.tick_params(labelsize=DP_FS)
            ax.set_ylim(0,max(1.0,float(_rs[[_cs,_cm]].max().max()))*1.42)
            lg=ax.legend(loc="upper left",fontsize=DP_FS_LG,frameon=True,facecolor=DC_CARD,
                         edgecolor=DC_EDGE,labelcolor=DC_TXT)
            lg.get_frame().set_alpha(.95)
            fig.autofmt_xdate(rotation=25,ha="right")
            fig.subplots_adjust(left=0.075,right=0.985,top=0.965,bottom=0.19)
            _show(fig)
        else: st.info(T("no_values"))
    _dash_foot(_sn)

def _tree_rects(sizes):
    """Treemap حقيقي: يقسّم المساحة لمربعات متقاربة (bruls algorithm).
       يرجّع [(x,y,w,h,index)] بإحداثيات نسبية 0..1."""
    _v=[(float(s),i) for i,s in enumerate(sizes) if s and float(s)>0]
    if not _v: return []
    _v.sort(key=lambda t:-t[0])
    _tot=sum(v for v,_ in _v) or 1.0
    _out=[]
    _norm=[(v/_tot,i) for v,i in _v]          # نسب المساحة

    def _worst(row,side):
        """أسوأ نسبة طول/عرض لصف عمودي على طول ضلعه."""
        if not row: return float("inf")
        s=sum(row); mx=max(row); mn=min(row)
        return max((side*side*mx)/(s*s),(s*s)/(side*side*mn))

    def _row(items,side):
        """أقصى صف يحسّن النسبة: يجمع رموزاً (قيمة،فهرس) حتى تتحسن."""
        row=[]; best=float("inf")
        for it in items:
            cand=row+[it]
            w=_worst([v for v,_ in cand],side)
            if w<=best or not row: row=cand; best=w
            else: break
        return row

    _x,_y,_w,_h=0.0,0.0,1.0,1.0
    _items=list(_norm)
    while _items:
        _side=min(_w,_h)
        _rowi=_row(_items,_side)
        _rest=_items[len(_rowi):]
        _sumrow=sum(v for v,_ in _rowi) or 1e-12
        if _w>=_h:                      # صف عمودي على اليسار
            _rw=_sumrow/_h
            _cur=_y
            for v,i in _rowi:
                _rh=v/_sumrow*_h
                _out.append((_x,_cur,_rw,_rh,i)); _cur+=_rh
            _x+=_rw; _w-=_rw
        else:                           # صف أفقي في الأعلى
            _rh=_sumrow/_w
            _cur=_x
            for v,i in _rowi:
                _rw=v/_sumrow*_w
                _out.append((_cur,_y,_rw,_rh,i)); _cur+=_rw
            _y+=_rh; _h-=_rh
        _items=_rest
        if _w<=1e-9 or _h<=1e-9: break
    return _out

def dash_g_rf(fdata,alldata):
    # =========================================================================
    # ===== داشبورد الإحالات (Referrals) =====
    # هوية لونية: أزرق فقط (فاتح ⇄ غامق)
    # ① رقمان: إجمالي الإحالات + الإحالات المستلمة
    # ② دونت: الفرق بين الإحالات والاستشارات
    # ③ خريطة شجرية: نسبة ذكور/إناث/بنات/صبيان
    # ④ دونت: أسباب الإحالة (بدون غرف/معدات/تخصص/مختبر/قرار المريض)
    # ⑤ دونت: وجهة الإحالة (مستشفى بسوريا/عيادة بسوريا/تركيا)
    # ⑥ خط شهري: الإحالات المستلمة + أسباب الإحالة
    # =========================================================================
    _sn=ss.get("_srcname") or ""
    _dash_head(T("g_rf"),fdata,_sn,"\U0001F4AA")
    if not len(fdata):
        st.info(T("no_rows_match"))
        _dash_foot(_sn)
        return
    S=lambda c: float(_num(fdata,[c])[c].sum()) if c in fdata.columns else 0.0
    fmt=lambda v: f"{v:,.0f}"
    def mhead(n,icon,title,color,note=""):
        return _rhead_html(n,icon,title,color,note)
    # ===== المؤشرات =====
    _tot=S("Total referrals")
    _rec=S("Refferals Referrals Received")
    _con=S("Referrals/ consultations")
    # ═══════════ ① رقمان: إجمالي الإحالات + المستلمة ═══════════
    _twobox(T("rf_total"),fmt(_tot),BL_M,T("rf_received"),fmt(_rec),BL_D)
    # ═══════════ ② + ③ جنب بعض: دونت الفروق (يسار) + خريطة الجنس (يمين) ═══════════
    _cA,_cB,__p1,__p2=st.columns([0.5,1,1,0.5],gap="medium")
    with _cA:
        st.markdown('<div class="mbox">'
                    +mhead("\u2460","\U0001F4CB",T("rf_vs_con"),BL_M2,fmt(_tot))
                    +'</div>',unsafe_allow_html=True)
        _p2=[]
        if _tot>0: _p2.append((T("rf_referrals"),_tot))
        if _con>0: _p2.append((T("rf_consultations"),_con))
        if not _p2:
            st.info(T("no_values"))
        else:
            _c2=f"{(_con/max(_tot,1.0)*100):.1f}%"
            f=_donut_fig(_p2,[BL_DIST[3],BL_DIST[7]],_c2,hole=.42,explode=.05,
                         tsize=DP_TSIZE,w=DP_W,lfont=DP_LFONT,key_below=DP_KEYBELOW,lmax=DP_LMAX)
            if f is not None: _show(f)
    with _cB:
        _gc=[(T("tr_male"),S("Refferals Men")),
             (T("tr_female"),S("Refferals Women")),
             (T("rf_boys"),S("Refferals Boys")),
             (T("rf_girls"),S("Refferals Girls"))]
        _gc=[(n,v) for n,v in _gc if v>0]
        _gct=sum(v for _,v in _gc)
        st.markdown('<div class="mbox">'
                    +mhead("\u2461","\U0001F5C2",T("rf_gender_share"),BL_M,fmt(_gct) if _gct else "")
                    +'</div>',unsafe_allow_html=True)
        if not _gc:
            st.info(T("no_values"))
        else:
            fig,ax=_dark_fig(DP_W,4.4)
            ax.axis("off"); ax.grid(False)
            ax.set_xlim(0,1); ax.set_ylim(0,1)
            ax.set_xticks([]); ax.set_yticks([])
            _rects=_tree_rects([v for _,v in _gc])
            for (_x,_y,_w,_h,_i) in _rects:
                ax.add_patch(mpatches.Rectangle((_x,_y),_w,_h,
                             facecolor=sex_color(_gc[_i][0]),edgecolor=DC_BG,
                             linewidth=DP_LW,alpha=.96))
                ax.text(_x+_w/2,_y+_h/2,f'{sex_lab(_gc[_i][0])}\n{fmt(_gc[_i][1])}\n{_gc[_i][1]/_gct*100:.1f}%',
                        ha="center",va="center",color=sex_ink(_gc[_i][0]),fontsize=DP_FS,
                        fontweight="700",linespacing=1.5)
            ax.set_facecolor(DC_BG); fig.patch.set_facecolor(DC_BG)
            fig.subplots_adjust(left=0,right=1,top=1,bottom=0)
            _show(fig)
    # ═══════════ ④ + ⑤ دونتان جنب بعض: الأسباب + الوجهة ═══════════
    _cA,_cB,__p1,__p2=st.columns([0.5,1,1,0.5],gap="medium")
    with _cA:
        _causes=[(T("rf_beds"),"Refferals Cause Unavailable Beds"),
                 (T("rf_equip"),"Refferals Cause Lack of equipment"),
                 (T("rf_spec"),"Refferals Cause Doctor Speciality unavailable"),
                 (T("rf_lab"),"Refferals Cause Lab"),
                 (T("rf_patient"),"Refferals Cause Patient decision"),
                 (T("rf_rad"),"Refferals Cause Rad")]
        _cv=[(n,S(c)) for n,c in _causes if S(c)>0]
        _ctot=sum(v for _,v in _cv)
        st.markdown('<div class="mbox">'
                    +mhead("\u2462","\U0001F5C2",T("rf_causes"),BL_M2,fmt(_ctot) if _ctot else "")
                    +'</div>',unsafe_allow_html=True)
        if not _cv:
            st.info(T("no_values"))
        else:
            _cd=[(n,v) for n,v in _cv]
            f=_donut_fig(_cd,BL_DIST[::2][:len(_cd)],f"{len(_cd)}",hole=.42,
                         explode=.05,tsize=DP_TSIZE,w=DP_W,lfont=DP_LFONT,key_below=DP_KEYBELOW,
                         lmax=DP_LMAX)
            if f is not None: _show(f)
    with _cB:
        _dest=[(T("rf_d_hosp_sy"),"Refferals Destinations Hospital in syria"),
               (T("rf_d_clinic_sy"),"Refferals Destinations Clinic in Syria"),
               (T("rf_d_turkey"),"Refferals Destinations Turkey")]
        _dv=[(n,S(c)) for n,c in _dest if S(c)>0]
        _dtot=sum(v for _,v in _dv)
        st.markdown('<div class="mbox">'
                    +mhead("\u2463","\U0001F5FA",T("rf_dest"),BL_D,fmt(_dtot) if _dtot else "")
                    +'</div>',unsafe_allow_html=True)
        if not _dv:
            st.info(T("no_values"))
        else:
            _dd=[(n,v) for n,v in _dv]
            f=_donut_fig(_dd,BL_DIST[::2][:len(_dd)],f"{len(_dd)}",hole=.42,
                         explode=.05,tsize=DP_TSIZE,w=DP_W,lfont=DP_LFONT,key_below=DP_KEYBELOW,
                         lmax=DP_LMAX)
            if f is not None: _show(f)
    # ═══════════ ⑥ الخط الشهري: المستلمة + أسباب الإحالة ═══════════
    st.markdown('<div class="mbox">'
                +mhead("\u2464","\U0001F4C8",T("rf_by_time"),BL_M,T("f_month"))
                +'</div>',unsafe_allow_html=True)
    _done=False
    if "Date" in fdata.columns and len(fdata):
        _cols=[("rec","Refferals Referrals Received",BL_DIST[7],"o",T("rf_received")),
               ("cause","Refferals Cause Unavailable Beds",BL_DIST[0],"s",T("rf_beds")),
               ("cause2","Refferals Cause Lack of equipment",BL_DIST[3],"^",T("rf_equip"))]
        _g=pd.DataFrame({"Date":fdata["Date"]})
        for _k,_c,*_ in _cols:
            _g[_k]=pd.to_numeric(fdata[_c],errors="coerce") if _c in fdata.columns else float("nan")
        _m=_g.groupby(pd.Grouper(key="Date",freq="MS"))[[k for k,_,_,_,_ in _cols]].sum(min_count=1)
        _m=_m[_m.index.notna()]
        _mk=[k for k,_,_,_,_ in _cols]
        if len(_m) and float(_m[_mk].sum().sum())>0:
            fig,ax=_dark_fig(PG_W,LINE_H)
            for _k,_c,_col,_mk2,_lb in _cols:
                ax.plot(_m.index,_m[_k].fillna(0),color=_col,marker=_mk2,markersize=DP_MS,
                        linewidth=DP_LW,label=_lb,markeredgecolor=DC_CARD,markeredgewidth=1)
                ax.fill_between(_m.index,_m[_k].fillna(0),alpha=.10,color=_col)
            ax.set_title("")
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5,prune="upper"))
            ax.tick_params(labelsize=DP_FS_SM)
            ax.set_ylim(0,max(1.0,float(_m[_mk].max().max()))*1.34)
            lg=ax.legend(loc="upper left",fontsize=DP_FS,frameon=True,facecolor=DC_CARD,
                         edgecolor=DC_EDGE,labelcolor=DC_TXT,ncol=3)
            lg.get_frame().set_alpha(.95)
            fig.autofmt_xdate(rotation=25,ha="right")
            fig.subplots_adjust(left=0.075,right=0.985,top=0.965,bottom=0.19)
            _show(fig); _done=True
    if not _done: st.info(T("no_values"))
    _dash_foot(_sn)

def dash_g_lr(fdata,alldata):
    # =========================================================================
    # ===== داشبورد المختبر والأشعة (Lab & Radiology) =====
    # هوية لونية: أزرق فقط (فاتح ⇄ غامق)
    # ① أربعة أرقام: فحوص المختبر + الأشعة + إحالة للمختبر + إحالة للأشعة
    # ② خريطة شجرية: أقسام الأشعة الخمسة
    # ③ + ④ خطّان جنب بعض: Mammography by time و CT by time
    # =========================================================================
    _sn=ss.get("_srcname") or ""
    _dash_head(T("g_lr"),fdata,_sn,"\U0001F52C")
    if not len(fdata):
        st.info(T("no_rows_match"))
        _dash_foot(_sn)
        return
    S=lambda c: float(_num(fdata,[c])[c].sum()) if c in fdata.columns else 0.0
    fmt=lambda v: f"{v:,.0f}"
    def mhead(n,icon,title,color,note=""):
        return _rhead_html(n,icon,title,color,note)
    # ===== المؤشرات =====
    _lab=S("Total lab tests")
    _rad=S("Total Radiology")
    _rlab=S("Refferals Cause Lab")
    _rrad=S("Refferals Cause Rad")
    # ═══════════ ① الأرقام الأربعة ═══════════
    _quadbox([(T("lr_lab"),fmt(_lab),BL_M),(T("lr_rad"),fmt(_rad),BL_D2),
              (T("lr_ref_lab"),fmt(_rlab),BL_M2),(T("lr_ref_rad"),fmt(_rrad),BL_D)])
    # ═══════════ ② خريطة شجرية: أقسام الأشعة ═══════════
    _parts=[(T("lr_echo"),"Radiolgy Echo"),(T("lr_xray"),"Radiolgy Xray"),
            (T("lr_ct"),"Radiolgy CT"),(T("lr_other"),"Radiolgy Other"),
            (T("lr_mamo"),"Radiolgy Mamo")]
    _cv=[(n,S(c)) for n,c in _parts if S(c)>0]
    _ctot=sum(v for _,v in _cv)
    st.markdown('<div class="mbox">'
                +mhead("\u2460","\U0001F5C2",T("lr_rad_parts"),BL_M2,
                       fmt(_rad) if _rad else "")
                +'</div>',unsafe_allow_html=True)
    if not _cv:
        st.info(T("no_values"))
    else:
        fig,ax=_dark_fig(PG_W,3.4)
        ax.axis("off"); ax.grid(False)
        ax.set_xlim(0,1); ax.set_ylim(0,1)
        ax.set_xticks([]); ax.set_yticks([])
        _rects=_tree_rects([v for _,v in _cv])
        for (_x,_y,_w,_h,_i) in _rects:
            ax.add_patch(mpatches.Rectangle((_x,_y),_w,_h,facecolor=_dist_color(_i),
                         edgecolor=DC_BG,linewidth=DP_LW,alpha=.96))
            ax.text(_x+_w/2,_y+_h/2,f'{_cv[_i][0]}\n{fmt(_cv[_i][1])}',
                    ha="center",va="center",color="#ffffff",fontsize=DP_FS,
                    fontweight="700",linespacing=1.45)
        ax.set_facecolor(DC_BG); fig.patch.set_facecolor(DC_BG)
        fig.subplots_adjust(left=0,right=1,top=1,bottom=0)
        _show(fig)
    # ═══════════ ③ + ④ خطّان جنب بعض: Mammography و CT عبر الأشهر ═══════════
    _cA,_cB,__p1,__p2=st.columns([0.5,1,1,0.5],gap="medium")
    def _timeseries(col,color,title,num):
        st.markdown('<div class="mbox">'
                    +mhead(num,"\U0001F4C8",title,color,T("f_month"))
                    +'</div>',unsafe_allow_html=True)
        if "Date" not in fdata.columns or col not in fdata.columns or not len(fdata):
            st.info(T("no_values")); return
        _g=pd.DataFrame({"Date":fdata["Date"],
                         "v":pd.to_numeric(fdata[col],errors="coerce")})
        _m=_g.groupby(pd.Grouper(key="Date",freq="MS"))["v"].sum(min_count=1)
        _m=_m[_m.index.notna()]
        if not len(_m) or float(_m.sum())<=0:
            st.info(T("no_values")); return
        fig,ax=_dark_fig(DP_W,4.6)
        ax.plot(_m.index,_m.values,color=color,marker="o",markersize=DP_MS,
                linewidth=DP_LW,markeredgecolor=DC_CARD,markeredgewidth=1)
        ax.fill_between(_m.index,_m.values,alpha=.14,color=color)
        ax.set_title("")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5,prune="upper"))
        ax.tick_params(labelsize=DP_FS_SM)
        ax.set_ylim(0,max(1.0,float(_m.max()))*1.28)
        fig.autofmt_xdate(rotation=25,ha="right")
        fig.subplots_adjust(left=0.115,right=0.975,top=0.965,bottom=0.215)
        _show(fig)
    with _cA:
        _timeseries("Radiolgy Mamo",BL_DIST[3],T("lr_mamo_time"),"\u2461")
    with _cB:
        _timeseries("Radiolgy CT",BL_DIST[1],T("lr_ct_time"),"\u2462")
    _dash_foot(_sn)

def dash_g_gi(fdata,alldata):
    # =========================================================================
    # ===== داشبورد تنظير الجهاز الهضمي (GI Scope) =====
    # ① رقم: إجمالي التنظير
    # ② خريطة شجرية: الفئات العمرية مصنّفة (رجال/نساء/صبيان/بنات)
    # ③ دونت: علوي مقابل سفلي
    # ④ جدول واحد: كل المنشآت مرتّبة مع نوعها (من الأصغر للأكبر)
    # ⑤ جدول: التنظير عبر الأشهر (GI scope by time)
    # =========================================================================
    _sn=ss.get("_srcname") or ""
    _dash_head(T("g_gi"),fdata,_sn,"\U0001F52E")
    if not len(fdata):
        st.info(T("no_rows_match"))
        _dash_foot(_sn)
        return
    S=lambda c: float(_num(fdata,[c])[c].sum()) if c in fdata.columns else 0.0
    fmt=lambda v: f"{v:,.0f}"
    _tot=S("Total Gi Scope")
    _up=S("GI Scope Upper"); _lo=S("GI Scope Lower")
    # ═══════════ ① + ② + ③ جنب بعض: رقم + شجرة + دونت ═══════════
    _c1,_c2,_c3=st.columns(3,gap="medium")
    with _c1:
        st.markdown('<div class="mbox">'
                    +_rhead_html("\u2460","\U0001F52E",T("gi_total"),BL_M,fmt(_tot))
                    +'</div>',unsafe_allow_html=True)
        st.markdown('<div class="onebig" style="--c:%s">'
                    '<div class="lb">%s</div><div class="vl">%s</div></div>'%(BL_M,T("gi_total"),fmt(_tot)),
                    unsafe_allow_html=True)
    with _c2:
        _gc=[(T("tr_male"),S("GI Scope Beneficiaries Men")),
             (T("tr_female"),S("GI Scope Beneficiaries Women")),
             (T("rf_boys"),S("GI Scope Beneficiaries Boys")),
             (T("rf_girls"),S("GI Scope Beneficiaries Girls"))]
        _gc=[(n,v) for n,v in _gc if v>0]
        _gct=sum(v for _,v in _gc)
        st.markdown('<div class="mbox">'
                    +_rhead_html("\u2461","\U0001F5C2",T("gi_ages"),BL_M2,fmt(_gct) if _gct else "")
                    +'</div>',unsafe_allow_html=True)
        if not _gc:
            st.info(T("no_values"))
        else:
            fig,ax=_dark_fig(DP_W,TILE_H)
            ax.axis("off"); ax.grid(False)
            ax.set_xlim(0,1); ax.set_ylim(0,1)
            ax.set_xticks([]); ax.set_yticks([])
            for (_x,_y,_w,_h,_i) in _tree_rects([v for _,v in _gc]):
                ax.add_patch(mpatches.Rectangle((_x,_y),_w,_h,facecolor=sex_color(_gc[_i][0]),
                             edgecolor=DC_BG,linewidth=DP_LW,alpha=.96))
                ax.text(_x+_w/2,_y+_h/2,f'{sex_lab(_gc[_i][0])}\n{fmt(_gc[_i][1])}\n{_gc[_i][1]/_gct*100:.1f}%',
                        ha="center",va="center",color=sex_ink(_gc[_i][0]),fontsize=DP_FS,
                        fontweight="700",linespacing=1.45)
            ax.set_facecolor(DC_BG); fig.patch.set_facecolor(DC_BG)
            fig.subplots_adjust(left=0,right=1,top=1,bottom=0)
            _show(fig)
    with _c3:
        st.markdown('<div class="mbox">'
                    +_rhead_html("\u2462","\U0001F4CB",T("gi_upper_lower"),BL_D,
                                 fmt(_up+_lo) if (_up+_lo) else "")
                    +'</div>',unsafe_allow_html=True)
        _sp=[]
        if _up>0: _sp.append((T("gi_upper"),_up))
        if _lo>0: _sp.append((T("gi_lower"),_lo))
        _spt=sum(v for _,v in _sp)
        if not _sp:
            st.info(T("no_values"))
        else:
            _sd=[(f'{n}  {v/_spt*100:.1f}%',v) for n,v in _sp]
            f=_donut_fig(_sd,[BL_DIST[1],BL_DIST[5]],f"{len(_sp)}",hole=.42,explode=.05,
                         tsize=DP_TSIZE,w=DP_W,lfont=DP_LFONT,key_below=DP_KEYBELOW,lmax=DP_LMAX)
            if f is not None: _show(f)
    # ═══════════ ④ جدول واحد: المنشآت اللي عندها تنظير فقط (من الأصغر للأكبر) ═══════════
    _fcol="Facility Name" if "Facility Name" in fdata.columns else None
    if _fcol is None:
        st.info(T("no_values"))
    else:
        _d=fdata[[_fcol]].copy()
        _d[_fcol]=_d[_fcol].fillna(T("unknown")).astype(str)
        _d[_fcol+"#k"]=_d[_fcol].map(_fac_key)
        _d["val"]=(pd.to_numeric(fdata["Total Gi Scope"],errors="coerce").fillna(0.0).values
                  if "Total Gi Scope" in fdata.columns else 0.0)
        _d=_d.groupby([_fcol+"#k",_fcol],as_index=False)["val"].sum()
        _d=_d[_d["val"]>0].reset_index(drop=True)
        _grand=float(_d["val"].sum())
        _rhead("④","\U0001F4CB",T("gi_by_fac"),BL_D,str(len(_d)))
        _kname={k:(ar_ if T("lang")=="ar" else en_) for k,_,ar_,en_,_ in FAC_KINDS}
        _tv=pd.DataFrame({"fac":_d[_fcol].tolist(),
                          "sec":[f"\U0001F3E5 {_kname.get(_fac_kind(x),T('fac_kind_other'))}" for x in _d[_fcol]],
                          "val":[float(v) for v in _d["val"].values]})
        _tv=_tv.sort_values(["val","fac"],ascending=[True,True]).reset_index(drop=True)
        _tv.loc[len(_tv)]={"fac":f'\U0001F535 {T("gi_total_all")}',"sec":"","val":_grand}
        _tv=_tv.rename(columns={"fac":T("f_facility_name"),
                                "sec":T("gi_section"),"val":T("gi_total")})
        st.dataframe(_tv,use_container_width=True,hide_index=True,
                     height=min(520,38+35*len(_tv)))
# ═══════════ ⑤ رسم بياني: التنظير عبر الأشهر ═══════════
    _rhead("⑤","\U0001F4C8",T("gi_by_time"),BL_D,T("f_month"))
    if "Date" not in fdata.columns or "Total Gi Scope" not in fdata.columns:
        st.info(T("no_values"))
    else:
        _g=pd.DataFrame({"Date":fdata["Date"],"v":pd.to_numeric(fdata["Total Gi Scope"],errors="coerce")})
        _m=_g.groupby(pd.Grouper(key="Date",freq="MS"))["v"].sum(min_count=1)
        _m=_m[_m.index.notna()]
        if not len(_m) or float(_m.sum())<=0:
            st.info(T("no_values"))
        else:
            fig,ax=_dark_fig(PG_W,LINE_H)
            ax.plot(_m.index,_m.values,color=BL_DIST[1],marker="o",markersize=DP_MS,
                    linewidth=DP_LW,markeredgecolor=DC_CARD,markeredgewidth=1.1)
            ax.fill_between(_m.index,_m.values,alpha=.15,color=BL_DIST[1])
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v:,.0f}"))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=6,prune="upper"))
            ax.tick_params(labelsize=DP_FS_SM)
            ax.set_ylim(0,max(1.0,float(_m.max()))*1.30)
            fig.autofmt_xdate(rotation=25,ha="right")
            fig.subplots_adjust(left=0.085,right=0.975,top=0.965,bottom=0.215)
            _show(fig)
    _dash_foot(_sn)

def dash_g_ho(fdata,alldata):
    # =========================================================================
    # ===== داشبورد الإقامة في المستشفى =====
    # هوية لونية: أزرق فقط (فاتح ⇄ غامق)
    # ① ثلاثة أرقام: الإقامة + ICU + الحاضنات
    # ② الذكور والإناث من كل الأعمار، مفصّلين حسب الفئة العمرية
    # ③ دونت: نسبة الذكور إلى الإناث
    # ④ خريطة شجرية: أسباب الدخول التسعة
    # ⑤ خط شهري: حالات الإقامة عبر الزمن
    # =========================================================================
    _sn=ss.get("_srcname") or ""
    _dash_head(T("g_ho"),fdata,_sn,"\U0001F3E5")
    if not len(fdata):
        st.info(T("no_rows_match"))
        _dash_foot(_sn)
        return
    S=lambda c: float(_num(fdata,[c])[c].sum()) if c in fdata.columns else 0.0
    fmt=lambda v: f"{v:,.0f}"
    def mhead(n,icon,title,color,note=""):
        return _rhead_html(n,icon,title,color,note)
    # ===== المؤشرات الثلاثة الرئيسية =====
    _hos=S("Number of Hospitalizations Total Total")
    _icu=S("Number of ICU patients received treatment Total")
    _inc=S("Incubators Admissions")
    _icm=S("Incubators Males")
    _icf=S("Incubators Females")
    _hm=S("Number of Hospitalizations Male Total Male")
    _hf=S("Number of Hospitalizations Female Total Female")
    _hos_pct=_hos/(_hos+_icu+_inc)*100 if (_hos+_icu+_inc) else 0.0
    _icu_pct=_icu/(_hos+_icu+_inc)*100 if (_hos+_icu+_inc) else 0.0
    _inc_pct=_inc/(_hos+_icu+_inc)*100 if (_hos+_icu+_inc) else 0.0
    # ═══════════ ① الأرقام الثلاثة الرئيسية ═══════════
    _twobox3([(T("ho_hosp"),fmt(_hos),BL_M,f'{T("tr_male")}: {fmt(_hm)}  ·  {T("tr_female")}: {fmt(_hf)}'),
              (T("ho_icu"),fmt(_icu),BL_D,f'{T("rows_label")}: {len(fdata):,}'),
              (T("ho_incub"),fmt(_inc),BL_M2,f'{T("tr_male")}: {fmt(_icm)}  ·  {T("tr_female")}: {fmt(_icf)}')])
    # ===== الفئات العمرية × الجنس =====
    _bands=[(T("sg_under5"),"<5 years"),(T("sg_5_14"),"5-14 years"),
            (T("sg_15_18"),"15-18 years"),(T("sg_19_49"),"19-49 years"),
            (T("sg_50p"),"50+ years")]
    _bars=[]
    for _i,(_lab,_sfx) in enumerate(_bands):
        _bars.append((f'{T("tr_male")} · {_lab}',S(f"Number of Hospitalizations Male {_sfx}"),_TR_MALE[_i]))
    for _i,(_lab,_sfx) in enumerate(_bands):
        _bars.append((f'{T("tr_female")} · {_lab}',S(f"Number of Hospitalizations Female {_sfx}"),_TR_FEM[_i]))
    _bars=[(n,v,c) for n,v,c in _bars if v>0]
    _pk=max([v for _,v,_ in _bars]+[1.0])
    # ═══════════ ② + ③ جنب بعض: الأعمار (يسار) + دونت الجنس (يمين) ═══════════
    _cA,_cB,__p1,__p2=st.columns([0.5,1,1,0.5],gap="medium")
    with _cA:
        st.markdown('<div class="mbox">'
                    +mhead("\u2460","\U0001F4CA",T("ho_by_age_gender"),BL_M2,fmt(_hos))
                    +'</div>',unsafe_allow_html=True)
        if not _bars:
            st.info(T("no_values"))
        else:
            fig,ax=_dark_fig(DP_W,LINE_H)
            _y=list(range(len(_bars)))[::-1]
            ax.barh(_y,[v for _,v,_ in _bars],height=0.66,
                    color=[c for _,_,c in _bars],alpha=.96,edgecolor=DC_CARD,linewidth=DP_LW)
            ax.set_yticks(_y)
            ax.set_yticklabels([_lbl(n,12) for n,_,_ in _bars],fontsize=DP_FS_SM)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
            ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
            ax.tick_params(labelsize=DP_FS_SM)
            ax.set_xlim(0,_pk*1.16)
            _xt=[t for t in ax.get_xticks() if 0<=t<=_pk*1.16]   # لا ticks خارج المحور
            ax.set_xticks(_xt)
            ax.grid(color=DC_EDGE,alpha=.35,axis="x")
            ax.set_axisbelow(True)
            for _y0,(_,v,_) in zip(_y,_bars):
                ax.text(v+_pk*0.012,_y0,fmt(v),va="center",ha="left",
                        color=DC_TXT,fontsize=DP_FS_SM,fontweight="700")
            ax.set_title("")
            fig.subplots_adjust(left=0.315,right=0.955,top=0.975,bottom=0.135)
            _show(fig)
    with _cB:
        st.markdown('<div class="mbox">'
                    +mhead("\u2461","\U0001F535",T("ho_gender_split"),BL_D2,fmt(_hos))
                    +'</div>',unsafe_allow_html=True)
        _parts=[]
        if _hm>0: _parts.append((T("tr_male"),_hm,SEX_M))
        if _hf>0: _parts.append((T("tr_female"),_hf,SEX_F))
        if not _parts:
            st.info(T("no_values"))
        else:
            _pc=f"{(T('tr_male'))}: {(_hm/(_hm+_hf)*100):.1f}%" if (_hm+_hf) else "\u2014"
            f=_donut_fig([(n,v) for n,v,_ in _parts],[c for _,_,c in _parts],_pc,
                         hole=.42,explode=.05,tsize=DP_TSIZE,w=DP_W,lfont=DP_LFONT,
                         key_below=DP_KEYBELOW,lmax=DP_LMAX)
            if f is not None: _show(f)
    # ═══════════ ④ خريطة شجرية: أسباب الدخول ═══════════
    _causes=[(T("mo_safe_deliveries"),"Morbidities Top Admission Causes Safe deliveries"),
             (T("mo_respiratory"),"Morbidities Top Admission Causes Respiratory diseases"),
             (T("mo_metabolic"),"Morbidities Top Admission Causes Metabolic diseases"),
             (T("mo_neonatal"),"Morbidities Top Admission Causes Neonatal care"),
             (T("mo_gi"),"Morbidities Top Admission Causes GI diseases"),
             (T("mo_wounds"),"Morbidities Top Admission Causes Wounds and traumas"),
             (T("mo_genito"),"Morbidities Top Admission Causes Genitourinary tract diseases"),
             (T("mo_blood"),"Morbidities Top Admission Causes Blood related diseases"),
             (T("mo_derm"),"Morbidities Top Admission Causes Dermatologic diseases")]
    _cv=[(n,S(c)) for n,c in _causes if S(c)>0]
    _ctot=sum(v for _,v in _cv)
    st.markdown('<div class="mbox">'
                +mhead("\u2462","\U0001F5C2",T("ho_causes"),BL_M,fmt(_ctot) if _ctot else "")
                +'</div>',unsafe_allow_html=True)
    if not _cv:
        st.info(T("no_values"))
    else:
        fig,ax=_dark_fig(PG_W,LINE_H)
        ax.axis("off"); ax.grid(False)
        ax.set_xlim(0,1); ax.set_ylim(0,1)
        ax.set_xticks([]); ax.set_yticks([])
        _sizes=[v for _,v in _cv]
        _rects=_tree_rects(_sizes)
        _seq=[BL_D,BL_D2,BL_M2,BL_M,BL_L,"#38bdf8","#60a5fa","#0ea5e9","#2563eb"]
        for (_x,_y,_w,_h,_i) in _rects:
            _ax0=ax.add_patch(mpatches.Rectangle((_x,_y),_w,_h,
                             facecolor=_seq[_i%len(_seq)],edgecolor=DC_BG,linewidth=DP_LW,alpha=.95))
            _lblw=min(len(_cv[_i][0]),int(_w*42))
            if _w>0.055 and _h>0.055:
                ax.text(_x+_w/2,_y+_h/2,f'{_cv[_i][0]}\n{fmt(_cv[_i][1])}',
                        ha="center",va="center",color="#ffffff",fontsize=DP_FS_SM,
                        fontweight="700",linespacing=1.45)
            elif _w>0.03 and _h>0.035:
                ax.text(_x+_w/2,_y+_h/2,fmt(_cv[_i][1]),ha="center",va="center",
                        color="#ffffff",fontsize=DP_FS_SM,fontweight="700")
        ax.set_xlim(0,1); ax.set_ylim(0,1)
        ax.set_facecolor(DC_BG); fig.patch.set_facecolor(DC_BG)
        fig.subplots_adjust(left=0,right=1,top=1,bottom=0)
        _show(fig)
    # ═══════════ ⑤ الخط الشهري: حالات الإقامة عبر الزمن ═══════════
    st.markdown('<div class="mbox">'
                +mhead("\u2463","\U0001F4C8",T("ho_by_time"),BL_M,T("f_month"))
                +'</div>',unsafe_allow_html=True)
    _done=False
    if "Date" in fdata.columns and len(fdata):
        _g=pd.DataFrame({"Date":fdata["Date"],
                         "hos":pd.to_numeric(fdata["Number of Hospitalizations Total Total"],errors="coerce")})
        _m=_g.groupby(pd.Grouper(key="Date",freq="MS"))["hos"].sum(min_count=1)
        _m=_m[_m.index.notna()]
        if len(_m) and float(_m.sum())>0:
            fig,ax=_dark_fig(PG_W,LINE_H)
            ax.plot(_m.index,_m.values,color=BL_M,marker="o",markersize=DP_MS,linewidth=DP_LW,
                    label=T("ho_hosp"),markeredgecolor=DC_CARD,markeredgewidth=1)
            ax.fill_between(_m.index,_m.values,alpha=.12,color=BL_M)
            ax.set_title("")
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5,prune="upper"))
            ax.tick_params(labelsize=DP_FS_SM)
            ax.set_ylim(0,max(1.0,float(_m.max()))*1.34)
            lg=ax.legend(loc="upper left",fontsize=DP_FS,frameon=True,facecolor=DC_CARD,
                         edgecolor=DC_EDGE,labelcolor=DC_TXT,ncol=2)
            lg.get_frame().set_alpha(.95)
            fig.autofmt_xdate(rotation=25,ha="right")
            fig.subplots_adjust(left=0.075,right=0.985,top=0.965,bottom=0.19)
            _show(fig); _done=True
    if not _done: st.info(T("no_values"))
    _dash_foot(_sn)


def dash_g_rh(fdata,alldata):
    # =========================================================================
    # ===== داشبورد «الصحة الإنجابية» =====
    # هوية لونية: أزرق فقط (فاتح ⇄ غامق) — نفس داشبورد العمليات الجراحية
    # الدونتات داخل سلايدات بثلث العرض، والخطوط بعرض الداشبورد كامل
    # =========================================================================
    _sn=ss.get("_srcname") or ""
    _dash_head(T("g_rh"),fdata,_sn,"\U0001F930")
    if not len(fdata):
        st.info(T("no_rows_match"))
        _dash_foot(_sn)
        return
    S=lambda c: float(_num(fdata,[c])[c].sum()) if c in fdata.columns else 0.0
    fmt=lambda v: f"{v:,.0f}"
    pct=lambda a,b: f"{(a/b*100):.1f}%" if b else "\u2014"
    def dcard(title,parts,colors):
        """دونت داخل سلايد: المفتاح تحت الدائرة"""
        st.markdown(f'<div class="ct">{title}</div>',unsafe_allow_html=True)
        f=_donut_fig(parts,colors,T("grand_total"),w=TILE_W,tsize=DP_TSIZE,lfont=DP_LFONT,key_below=DP_KEYBELOW,lmax=DP_LMAX)
        if f is not None: _show(f)
        else: st.info(T("no_values"))
    def qcell(head,val,sub,color,share=None):
        _b=_pbar(share if share is not None else 0,color)
        return (f'<div class="qcell" style="--c:{color}"><div class="qh">{head}<b>{fmt(val)}</b></div>'
                f'<div class="qv">{fmt(val)}</div>' + _qs_div(sub) + f'{_b}</div>')
    def hbar2(title,parts,colors):
        """مربع مقسوم نصين: طبيب / قابلة"""
        _t=sum(v for _,v in parts) or 1
        _h=['<div class="hbox2">']
        for (n,v),c in zip(parts,colors):
            _h.append(f'<div class="qcell" style="--c:{c}"><div class="qh">{n}<b>{pct(v,_t)}</b></div>'
                      f'<div class="qv">{fmt(v)}</div>'
                      f'<div class="qs">{T("grand_total")}: {fmt(_t)}</div>{_pbar(v/_t*100,c)}</div>')
        _h.append('</div>')
        st.markdown("".join(_h),unsafe_allow_html=True)
    def trend(cols,title,labels,colors):
        """خط زمني شهري — بعرض الداشبورد كامل"""
        if "Date" not in fdata.columns: return
        _ok=[c for c in cols if c in fdata.columns]
        if not _ok: return
        _g=pd.DataFrame({"Date":fdata["Date"]})
        for c in _ok: _g[c]=pd.to_numeric(fdata[c],errors="coerce")
        _m=_g.groupby(pd.Grouper(key="Date",freq="MS"))[_ok].sum()
        _m=_m[_m.index.notna()]
        if not len(_m) or float(_m.sum().sum())<=0: return
        fig,ax=_lin_fig()
        for c,lb,col,mk in zip(_ok,labels,colors,["o","s","^","D"]):
            ax.plot(_m.index,_m[c],color=col,marker=mk,markersize=DP_MS,linewidth=DP_LW,
                    label=lb,zorder=5,markeredgecolor=DC_CARD,markeredgewidth=1)
        ax.fill_between(_m.index,_m[_ok[0]],alpha=.10,color=colors[0],zorder=1)
        ax.set_title("")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5,prune="upper"))
        ax.set_ylim(0,float(_m[_ok].to_numpy().max())*1.42+1)
        ax.tick_params(colors=DC_MUT,labelsize=DP_FS)
        lg=ax.legend(loc="upper right",fontsize=DP_FS_LG,frameon=True,facecolor=DC_CARD,
                     edgecolor=DC_EDGE,labelcolor=DC_TXT,ncol=min(2,len(_ok)))
        lg.get_frame().set_alpha(.95)
        fig.autofmt_xdate(rotation=25,ha="right")
        fig.subplots_adjust(left=0.075,right=0.985,top=0.965,bottom=0.19)
        _show(fig)
    # ===== ① أرقام رئيسية: وفيات الأمهات + المواليد =====
    _dead=S("RH Dead births"); _mda=S("Matrenatl death averted total")
    _dv=S("RH Total deliveries"); _anc=S("Total ANCs")
    _rhead("\u2460","\U0001F4CC",T("grand_total"),BL_M,T("f_date"))
    _kcards([("\u26B0\uFE0F",T("rh_dead"),fmt(_dead),BL_D,f"{pct(_dead,_dv)} / {fmt(_dv)}"),
             ("\U0001F49A",T("rh_mda"),fmt(_mda),BL_NW[2],f"{pct(_mda,_anc)} / {fmt(_anc)}"),
             ("\U0001F476",T("rh_deliv"),fmt(_dv),BL_M,T("rh_normal")+" "+fmt(S("Total Normal delivery"))),
             ("\U0001F469",T("rh_anc"),fmt(_anc),BL_D2,f"{T('rh_anc4')} {fmt(S('RH ANC 4 and above'))}")])
    # ===== ② استشارات + ANC + ولادات: ٣ سلايدات =====
    _a2=S("RH ANC 2 and above"); _a4=S("RH ANC 4 and above")
    _cs=S("Total C sections"); _nv=S("Total Normal delivery")
    _rhead("\u2461","\U0001FA7A",T("rh_consult")+" \u00b7 "+T("rh_anc"),BL_M2,T("f_age"))
    _c1,_c2,_c3=st.columns(3,gap="medium")
    with _c1:
        dcard(T("rh_consult"),[(T("o18"),S("RH Total RH consultations 18>")),
                               (T("u18"),S("RH Total RH consultations 18<"))],[BL_M,BL_D])
    with _c2:
        dcard(T("rh_anc"),[(T("o18"),S("RH Total ANC visits 18>")),
                           (T("u18"),S("RH Total ANC visits 18<"))],[BL_M2,BL_D])
    with _c3:
        st.markdown(f'<div class="ct">{T("rh_deliv")}</div>',unsafe_allow_html=True)
        f=_donut_fig([(T("rh_csect"),_cs),(T("rh_normal"),_nv)],[BL_D2,BL_NW[1]],
                     T("grand_total"),w=TILE_W,tsize=DP_TSIZE,lfont=DP_LFONT,key_below=DP_KEYBELOW,lmax=DP_LMAX)
        if f is not None: _show(f)
        else: st.info(T("no_values"))
    # ===== ③ مربع ANC: ANC 2+ و ANC 4+ =====
    _rhead("\u2462","\U0001F930",T("rh_anc2")+" / "+T("rh_anc4"),BL_D2,fmt(_a2+_a4))
    st.markdown('<div class="hbox2">'
                f'<div class="qcell" style="--c:{BL_M}"><div class="qh">{T("rh_anc2")}<b>{pct(_a2,_anc)}</b></div>'
                f'<div class="qv">{fmt(_a2)}</div><div class="qs">{T("grand_total")}: {fmt(_anc)}</div>'
                f'{_pbar(_a2/_anc*100 if _anc else 0,BL_M)}</div>'
                f'<div class="qcell" style="--c:{BL_D2}"><div class="qh">{T("rh_anc4")}<b>{pct(_a4,_anc)}</b></div>'
                f'<div class="qv">{fmt(_a4)}</div><div class="qs">{T("grand_total")}: {fmt(_anc)}</div>'
                f'{_pbar(_a4/_anc*100 if _anc else 0,BL_D2)}</div></div>',unsafe_allow_html=True)
    # ===== ④ مربع مقسّم لأربع: تحت 18 / فوق 18 × نوع الولادة =====
    _csu=S("RH C sections 18>"); _csm=S("RH C sections 18<")
    _nvu=S("RH Normal Deliveries 18>"); _nvm=S("RH Normal Deliveries 18<")
    _rhead("\u2463","\U0001F476",T("rh_deliv")+" \u00b7 "+T("f_age"),BL_D,
           f'{T("u18")} {fmt(_csm+_nvm)} \u00b7 {T("o18")} {fmt(_csu+_nvu)}')
    st.markdown(_stack([(T("rh_csect"),_cs,BL_D),(T("rh_normal"),_nv,BL_NW[1])])
                +'<div class="legendrow">'
                f'<span><b style="background:{BL_D}"></b>{T("rh_csect")} {fmt(_cs)} \u00b7 {pct(_cs,_cs+_nv)}</span>'
                f'<span><b style="background:{BL_NW[1]}"></b>{T("rh_normal")} {fmt(_nv)} \u00b7 {pct(_nv,_cs+_nv)}</span>'
                '</div>'
                +'<div class="qbox">'
                +qcell(f'{T("u18")} \u00b7 {T("rh_csect")}',_csm,pct(_csm,_csm+_nvm),BL_D,_csm/(_csu+_nvu+_csm+_nvm)*100)
                +qcell(f'{T("u18")} \u00b7 {T("rh_normal")}',_nvm,pct(_nvm,_csm+_nvm),BL_NW[1],_nvm/(_csu+_nvu+_csm+_nvm)*100)
                +qcell(f'{T("o18")} \u00b7 {T("rh_csect")}',_csu,pct(_csu,_csu+_nvu),BL_D2,_csu/(_csu+_nvu+_csm+_nvm)*100)
                +qcell(f'{T("o18")} \u00b7 {T("rh_normal")}',_nvu,pct(_nvu,_csu+_nvu),BL_NW[2],_nvu/(_csu+_nvu+_csm+_nvm)*100)
                +'</div>',unsafe_allow_html=True)
    # ===== ⑤ إشراف الطبيب / القابلة + وفيات أمومية + متابعة الأم: ٣ سلايدات =====
    _doc=S("RH Deliveries by medical staff Doctor"); _mwf=S("RH Deliveries by medical staff Medwife")
    _rhead("\u2464","\U0001FA7A",T("rh_deliv")+" \u00b7 "+T("rh_mda")+" \u00b7 "+T("rh_pnc_m"),BL_M,
           f'{T("grand_total")} {fmt(_doc+_mwf)}')
    _d1,_d2,_d3=st.columns(3,gap="medium")
    with _d1:
        st.markdown(f'<div class="ct">{T("rh_deliv")}</div>',unsafe_allow_html=True)
        _t=(_doc+_mwf) or 1
        st.markdown('<div class="hstack">'
                    f'<div class="qcell" style="--c:{BL_M}"><div class="qh">{T("rh_by_doc")}<b>{pct(_doc,_t)}</b></div>'
                    f'<div class="qv">{fmt(_doc)}</div><div class="qs">{T("grand_total")}: {fmt(_t)}</div>'
                    f'{_pbar(_doc/_t*100,BL_M)}</div>'
                    f'<div class="qcell" style="--c:{BL_D2}"><div class="qh">{T("rh_by_mwf")}<b>{pct(_mwf,_t)}</b></div>'
                    f'<div class="qv">{fmt(_mwf)}</div><div class="qs">{T("grand_total")}: {fmt(_t)}</div>'
                    f'{_pbar(_mwf/_t*100,BL_D2)}</div></div>',unsafe_allow_html=True)
    with _d2:
        dcard(T("rh_mda"),[(T("o18"),S("RH Maternal death Averted 18>")),
                           (T("u18"),S("RH Maternal death Averted 18<"))],[BL_M2,BL_D])
    with _d3:
        dcard(T("rh_pnc_m"),[(T("o18"),S("RH Total PNCs mothers 18>")),
                             (T("u18"),S("RH Total PNCs mothers 18<"))],[BL_NW[1],BL_D])
    # ===== ⑥ متابعة الأم حسب التوقيت + المواليد + تنظيم الأسرة: ٣ سلايدات =====
    _u24=S("RH PNCs <24 hours"); _o24=S("RH PNCs 24 Hours and above")
    _rhead("\u2465","\u23F1\uFE0F",T("rh_pnc_m")+" \u00b7 "+T("rh_pnc_n")+" \u00b7 "+T("rh_fp"),BL_M2,
           f'{T("grand_total")} {fmt(_u24+_o24)}')
    _e1,_e2,_e3=st.columns(3,gap="medium")
    with _e1:
        st.markdown(f'<div class="ct">{T("rh_pnc_m")}</div>',unsafe_allow_html=True)
        st.markdown('<div class="hstack">'
                    +qcell(T("rh_pnc_u24"),_u24,pct(_u24,_u24+_o24),BL_M,_u24/(_u24+_o24)*100 if (_u24+_o24) else 0)
                    +qcell(T("rh_pnc_24p"),_o24,pct(_o24,_u24+_o24),BL_D2,_o24/(_u24+_o24)*100 if (_u24+_o24) else 0)
                    +'</div>',unsafe_allow_html=True)
    with _e2:
        dcard(T("rh_pnc_n"),[(T("rh_boys"),S("PNCs newborns within 3 days after delivery Male")),
                             (T("lbl_girls"),S("PNCs newborns within 3 days after delivery Female"))],
              sex_colors([T("rh_boys"),T("lbl_girls")]))
    with _e3:
        dcard(T("rh_fp"),[(T("o18"),S("RH Family Planning 18>")),
                          (T("u18"),S("RH Family Planning 18<"))],[BL_NW[1],BL_D])
    # ===== ⑦ STIs: ثمانية أقسام بتدرّج أزرق =====
    _sti=[(T("s_syph"),S("Morbidities STIs Syphilis"),DB_PAL[0]),
          (T("s_chlam"),S("Morbidities STIs Chlamidia"),DB_PAL[1]),
          (T("s_aids"),S("Morbidities STIs AIDS"),DB_PAL[3]),
          (T("s_gono"),S("Morbidities STIs Gonococcal infection"),DB_PAL[4]),
          (T("s_trich"),S("Morbidities STIs Trichomoniasis"),DB_PAL[2]),
          (T("s_unspec"),S("Morbidities STIs Other and unspecified"),DB_PAL[7]),
          (T("s_stls18p"),S("RH STIS 18>"),DB_PAL[5]),
          (T("s_stls18m"),S("RH STIS 18<"),DB_PAL[6])]
    _stit=sum(v for _,v,_ in _sti)
    _rhead("\u2466","\U0001F6E1\uFE0F",T("bx_stls"),BL_D,fmt(_stit))
    _h=['<div class="hbox8">']
    for n,v,c in _sti:
        _h.append(f'<div class="scell" style="--c:{c}"><div class="sh">{n}</div>'
                  f'<div class="sv">{fmt(v)}</div>'
                  f'<div class="sp">{pct(v,_stit)}</div>{_pbar(v/_stit*100 if _stit else 0,c)}</div>')
    _h.append('</div>')
    st.markdown("".join(_h),unsafe_allow_html=True)
    # ===== ⑧ ولادات شهرياً — بعرض الداشبورد كامل =====
    _rhead("\u2467","\U0001F4C8",T("ch_deliv_trend"),BL_M,T("f_date"))
    trend(["Total Normal delivery","Total C sections"],T("ch_deliv_trend"),
          [T("t_total_normal"),T("t_total_csec")],[BL_NW[1],BL_D])
    # ===== ⑨ متابعة الحوامل شهرياً — بعرض الداشبورد كامل =====
    _rhead("\u2468","\U0001F4C8",T("ch_anc_trend"),BL_D2,T("f_date"))
    trend(["Total ANCs","RH ANC 4 and above"],T("ch_anc_trend"),
          [T("t_total_anc"),T("t_anc4")],[BL_M,BL_D2])
    _dash_foot(_sn)

def _reporting_frame(fdata):
    """الصفوف إلها أرقام فعلاً: خدمات/مستفيدين > 0.
    المنشآت اللي ما في عندها أي إبلاغ ما منحسب ضمن العد."""
    if fdata is None or len(fdata)==0 or "Facility Name" not in fdata.columns:
        return fdata
    tot=pd.Series(0.0,index=fdata.index)
    for c in (SERVICE_COL,BENEF_COL):
        if c in fdata.columns:
            tot=tot+pd.to_numeric(fdata[c],errors="coerce").fillna(0)
    return fdata[tot>0]

# ===== فئات عمرية: هي تفصيل للمجموع، وممكن تناقض المجموع في الملف =====
# يعني منشأة ممكن إلها أرقام بفئات العمرية وبنفس الوقت «مجموع» = 0.
# هي المنشأة ما إلها الخدمة الحقيقية، فما منحسب ضمن عدّ الداشبورد.
_AGE_BAND_RE=re.compile(r"<\s*5|\b5-14\b|\b15-18\b|\b19-49\b|50\+|\b0-4\b|\b5-9\b|\b10-14\b"
                        r"|\b15-19\b|\b20-39\b|\b40-49\b",re.I)

def _is_age_band(col): return bool(_AGE_BAND_RE.search(str(col)))

def _count_cols(df,key):
    """الأعمدة يلي بنحسب فيها «المنشأة إلها بيانات» = المؤشرات الحقيقية،
    بدون أعمدة الفئات العمرية (تفصيل بس). وإذا كل الأعمدة فئات عمرية
    بنستخدمها كلها حتى ما نخسر داشبورد."""
    cols=[c for c in (_match_cols(df,key) or []) if c in df.columns]
    if not cols: return []
    prim=[c for c in cols if not _is_age_band(c)]
    return prim or cols

def _dashboard_rows(fdata,key):
    """صفوف إلها أرقام فعلاً بأعمدة هذا الداشبورد لحاله.
    مثلاً داشبورد الأسنان: منشأة إلها استشارات دون خدمات أسنان،
    ما منحسب ضمن العد — لأنه ما إلها بيانات لهذا الداشبورد."""
    if fdata is None or len(fdata)==0: return fdata
    try: cols=_count_cols(fdata,key)
    except Exception: cols=[]
    if not cols: return _reporting_frame(fdata)   # ما عرفنا الأعمدة => السلوك القديم
    num=fdata[cols].apply(pd.to_numeric,errors="coerce").fillna(0)
    has=(num!=0).any(axis=1)
    if not has.any(): return fdata.iloc[0:0]
    return fdata[has]

_NA_TOKENS={"nan","<na>","none","nat","null","n/a","-"}
def _clean_names(items):
    out=set()
    for x in items:
        if x is None: continue
        s=str(x).strip()
        if not s or s.lower() in _NA_TOKENS: continue
        out.add(s)
    return sorted(out)

def _hov(n,items,label=""):
    """رقم قابل للضغط: يفتح قائمة الأسماء تحت الترويسة (بدون ما يغطي أي شي)."""
    if n is None or n==0: return f"<b>{n if n is not None else 0}</b>"
    _names=_clean_names(items)
    if not _names: return f"<b>{n}</b>"
    _body="".join(f'<div>{_esc_html(x)}</div>' for x in _names)
    return (f'<details class="hovlist"><summary>{n}</summary>'
            f'<div class="hovbody">{_body}</div></details>')

def _esc_html(s):
    return (str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))

def _esc_attr(s): return _esc_html(s).replace('"',"&quot;")

def _dash_head(title,fdata,sn,icon="📊",extra=""):
    """ترويسة موحّدة لكل داشبوردات لوحة الخدمات الصحية"""
    _SEC_N[0]=0                       # ترقيم الأقسام يبدأ من ① بكل داشبورد
    # العدّ خاص بكل داشبورد: الصفوف/البرنامج/المحافظة/المنشأة
    # إلها أرقام بأعمدة هذا الزر بس (مو عدّ عام لكل الداتا)
    _rep=_dashboard_rows(fdata,ss.get("_hhs_key"))
    _pr=_rep["Program"].nunique() if "Program" in _rep.columns else 0
    _gv=_rep["Governorate"].nunique() if "Governorate" in _rep.columns else 0
    _fc=_rep["Facility Name"].nunique() if "Facility Name" in _rep.columns else 0
    # كم منشأة ما إلها بيانات بهذا المجال تحديداً (لهيك ما حسبناها)
    _all=_reporting_frame(fdata)
    _fc_all=_all["Facility Name"].nunique() if "Facility Name" in _all.columns else _fc
    _skip=(_fc_all-_fc) if _fc_all>_fc else 0
    _skip_html=(f' · {T("fac_no_data")}: <b>{_skip}</b>' if _skip else "")
    st.markdown(f'<div class="dashwrap"><div class="dashhead"><div>'
                f'<div class="t">{icon} {title}</div>'
                f'<div class="s">{T("rows_label")}: <b>{len(_rep):,}</b> · '
                f'{T("f_program")}: {_hov(_pr,_rep["Program"] if "Program" in _rep.columns else [],T("f_program"))} · '
                f'{T("f_governorate")}: {_hov(_gv,_rep["Governorate"] if "Governorate" in _rep.columns else [],T("f_governorate"))} · '
                f'{T("f_facility_name")}: {_hov(_fc,_rep["Facility Name"] if "Facility Name" in _rep.columns else [],T("f_facility_name"))}'
                f'{_skip_html}'
                f'{extra}</div></div><div class="badge">{(sn or "")[:34]}</div></div>',
                unsafe_allow_html=True)

def _dash_foot(sn):
    """تذييل موحّد: مصدر الداتا + تنبيه أن الفلتر يسبق الرقم"""
    st.markdown(f'<div class="foot-note">{T("src_active")}: <b>{sn}</b> · '
                f'{T("filter_before")}</div></div>',unsafe_allow_html=True)

def _lbl(x,maxlen=30):
    # ===== اسم مقروء للعمود: يختصر السن/الجنس ويقصّ من المنتصف (يحافظ على المميّز) =====
    s=re.sub(r"\s+"," ",str(x).strip()).replace("_"," ").replace("/"," ")
    s=re.sub(r"\s+"," ",s).strip()
    s=(s.replace("<5 years","<5y").replace("5-14 years","5-14y")
         .replace("15-18 years","15-18y").replace("19-49 years","19-49y")
         .replace("50+ years","50+").replace(" years","y"))
    # اختصار الجنس والفئات — بحدود كلمة حتى ما يأكل جزء من كلمة ثانية
    s=re.sub(r"\bFemales?\b","F",s); s=re.sub(r"\bMales?\b","M",s)
    s=re.sub(r"\bWomen\b","W",s);   s=re.sub(r"\bMen\b","M",s)
    s=re.sub(r"\bGirls\b","G",s);   s=re.sub(r"\bBoys\b","B",s)
    # بادئة الخدمة المكرّرة ما تضيف معلومة (Total نتركها لأنها تميّز صف المجموع)
    s=re.sub(r"^(CHWs?|SRV|Service)\s+","",s,flags=re.I)
    s=re.sub(r"\s+"," ",s).strip(" -–:#")
    if len(s)<=maxlen: return s or str(x)[:maxlen]
    # قصّ من المنتصف: نحافظ على أول كلمتين وآخر كلمتين (آخرها = المميّز: M/F/<5y…)
    w=s.split()
    if len(w)<=3: return s[:maxlen]
    tail=" ".join(w[-2:])
    head=[]
    used=len(tail)+3                       # 3 = رمز القصّ " … "
    for word in w[:-2]:
        if used+len(word)+1>maxlen: break
        head.append(word); used+=len(word)+1
    if not head: return s[:maxlen]
    return " ".join(head)+" … "+tail

def render_hhs_generic(fdata,alldata):
    # =========================================================================
    # ===== الداشبورد العام (١٩ وحدة) =====
    # نفس هوية داشبورد العمليات الجراحية: لوحة زرقاء بالكامل
    # ① شريط بطاقات  ② ٣ سلايدات جنب بعض  ③ خط/منشآت بعرض الداشبورد  ④ جدول
    # =========================================================================
    _k=ss.get("_hhs_key")
    cols=_match_cols(alldata,_k)
    if not cols:
        st.warning(T("no_cols")); return
    _title=T(_k); _sn=ss.get("_srcname") or ""
    _dash_head(_title,fdata,_sn,"\U0001F4CA",
               f' \u00b7 {T("matched_cols")}: <b>{len(cols)}</b> {T("g_cols_n")}')
    if not len(fdata):
        st.info(T("no_rows_match"))
        _dash_foot(_sn)
        return
    S=lambda c: float(_num(fdata,[c])[c].sum()) if c in fdata.columns else 0.0
    fmt=lambda v: f"{v:,.0f}"
    pct=lambda a,b: f"{(a/b*100):.1f}%" if b else "\u2014"
    # ===== لوحة أزرق للسلايد: تدرّج فاتح ⇄ غامق بلا أسماء خارج الأزرق =====
    def blueramp(n):
        src=[BL_L,BL_M,BL_M2,BL_D2,BL_D]
        return [src[i%len(src)] for i in range(max(1,n))]
    def gdonut(data,title,colors,tile=False):
        """دونت — بسلايد بثلث العرض أو بعرض الداشبورد كامل"""
        data=[(n,v) for n,v in data if v>0]
        if not data: return None
        if len(data)>8:
            data=sorted(data,key=lambda t:-t[1])[:7]+[(T("other_val"),sum(v for _,v in data[7:]))]
        st.markdown(f'<div class="ct">{title}</div>',unsafe_allow_html=True)
        if tile:
            return _donut_fig([(_lbl(n,22),v) for n,v in data],colors,T("grand_total"),
                              w=TILE_W,tsize=14,lfont=10,key_below=True,lmax=18)
        return _donut_fig([(_lbl(n),v) for n,v in data],colors,T("grand_total"))
    def show(f):
        _show(f)
    def hbar(series,color,title,mode="tile"):
        """أعمدة أفقية — tile=ثلث العرض، half=نصف، full=الداشبورد كامل"""
        if not len(series): return None
        st.markdown(f'<div class="ct">{title}</div>',unsafe_allow_html=True)
        _w,_h=(TILE_W,TILE_H) if mode=="tile" else ((HALF_W,TILE_H) if mode=="half" else (PG_W,LINE_H))
        fig,ax=_dark_fig(_w,_h)
        _lb=[_lbl(i,16 if mode=="tile" else 26) for i in series.index][::-1]
        ax.barh(_lb,series.values[::-1],color=color,alpha=.9,height=.68)
        ax.set_title("")
        _mv=max(series.values) if len(series) else 0
        ax.set_xlim(0,_mv*1.16 if _mv>0 else 1)      # مساحة حتى لا يُقصّ آخر رقم محور
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4 if mode=="tile" else 6,prune="upper"))
        if mode=="tile":
            ax.tick_params(labelsize=9.5); ax.tick_params(axis="y",labelsize=9.5)
            for lb in ax.get_yticklabels(): lb.set_ha("right")
            fig.subplots_adjust(left=0.345,right=0.975,top=0.965,bottom=0.115)
        elif mode=="half":
            ax.tick_params(labelsize=11); ax.tick_params(axis="y",labelsize=10.5)
            for lb in ax.get_yticklabels(): lb.set_ha("right")
            fig.subplots_adjust(left=0.255,right=0.985,top=0.965,bottom=0.115)
        else:
            ax.tick_params(labelsize=12); ax.tick_params(axis="y",labelsize=11.5)
            for lb in ax.get_yticklabels(): lb.set_ha("right")
            fig.subplots_adjust(left=0.215,right=0.985,top=0.965,bottom=0.105)
        return fig
    def tline(ser,title,color=BL_M,mode="tile"):
        """خط زمني — tile=ثلث العرض، full=الداشبورد كامل"""
        if ser is None or not len(ser): return None
        st.markdown(f'<div class="ct">{title}</div>',unsafe_allow_html=True)
        _w,_h=(TILE_W,TILE_H) if mode=="tile" else (PG_W,LINE_H)
        fig,ax=_dark_fig(_w,_h)
        ax.plot(ser.index,ser.values,color=color,marker="o",markersize=5,
                linewidth=2.6,markeredgecolor=DC_CARD,markeredgewidth=1.1)
        ax.fill_between(ser.index,ser.values,alpha=.16,color=color)
        ax.set_title("")
        _mv=float(ser.values.max()) if len(ser) else 0
        ax.set_ylim(0,max(1.0,_mv)*1.18)            # مساحة أعلى حتى لا يُقصّ رقم المحور
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_: f"{v/1000:,.0f}k" if v>=1000 else f"{v:,.0f}"))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4 if mode=="tile" else 5,prune="upper"))
        if mode=="tile":
            ax.tick_params(labelsize=9.5)
            fig.autofmt_xdate(rotation=25,ha="right")
            fig.subplots_adjust(left=0.16,right=0.975,top=0.965,bottom=0.235)
        else:
            ax.tick_params(labelsize=10)
            fig.autofmt_xdate(rotation=25,ha="right")
            fig.subplots_adjust(left=0.075,right=0.985,top=0.965,bottom=0.19)
        return fig
    # ===== تجميع الأعمدة إلى مجموعات قياس =====
    from collections import OrderedDict
    grp=OrderedDict()
    for c in cols: grp.setdefault(_group_of(c),[]).append(c)
    _N=_num(fdata,cols)
    rows=[(gname,len(gcols),float(_N[gcols].sum().sum()) if gcols else 0.0)
          for gname,gcols in grp.items()]
    prev=list(rows)
    rows=[r for r in rows if r[2]!=0] or prev
    rows.sort(key=lambda r:-r[2])
    if not rows:
        st.info(T("no_values"))
        _dash_foot(_sn)
        return
    _tot=float(_N.sum().sum())
    _main=rows[0][0]
    _mcols=[c for c in grp.get(_main,[]) if c in alldata.columns]
    # ===== ① شريط البطاقات (كله بتدرّج أزرق) =====
    _rhead("\u2460","\U0001F4CC",T("grand_total"),BL_M,f'{T("matched_cols")} {len(cols)}')
    _cards=[("\U0001F522",T("grand_total"),fmt(_tot),BL_M,f'{T("rows_label")}: {len(fdata):,}')]
    _ramp=blueramp(8)
    for i,(g,n,s_) in enumerate(rows[:4]):
        _cards.append((str(i+1),_lbl(g,22),fmt(s_),_ramp[i+1],f"{pct(s_,_tot)} \u00b7 {n} {T('g_cols_n')}"))
    while len(_cards)<5:
        _cards.append(("\u2014","\u2014","\u2014",BL_D,""))
    _kcards(_cards[:5])
    # ===== ② ثلاثة سلايدات جنب بعض =====
    _cr=rows[:6] if len(rows)>6 else rows
    _gc=[(g,s_) for g,n,s_ in _cr]+([(T("other_val"),sum(s_ for g,n,s_ in rows[6:]))] if len(rows)>6 else [])
    _cc=sorted([(c,float(_N[c].sum())) for c in _mcols
                if c in _N.columns and float(_N[c].sum())>0],key=lambda t:-t[1])[:6]
    if len(_cc)>6: _cc=_cc[:5]+[(T("other_val"),sum(v for _,v in _cc[5:]))]
    _rhead("\u2461","\U0001F4CA",T("by_group")+" \u00b7 "+T("by_col"),BL_M2,
           f'{T("main_group")}: {_lbl(_main,26)}')
    _c1,_c2,_c3=st.columns(3,gap="medium")
    with _c1: show(gdonut(_gc,T("by_group"),blueramp(len(_gc)),tile=True))
    with _c2: show(gdonut([(c,v) for c,v in _cc],T("by_col"),blueramp(len(_cc))[::-1],tile=True))
    with _c3:
        f=hbar(pd.Series({_lbl(g,22):s_ for g,n,s_ in rows[:8][::-1]}),BL_M,T("top_groups"),mode="tile")
        if f is None: st.info(T("no_values"))
        else: show(f)
    # ===== ③ الخط + أعلى المنشآت بعرض الداشبورد =====
    _has_t=bool(_mcols) and "Date" in fdata.columns and len(fdata)
    _ser=None
    if _has_t:
        _ts=_N[_mcols].sum(axis=1)
        _sm=pd.DataFrame({"Date":fdata["Date"],"v":_ts}).groupby("Date")["v"].sum().sort_index()
        if len(_sm)>1: _ser=_sm
    _fac=None
    if _has_t and "Facility Name" in fdata.columns:
        _g=pd.DataFrame({"Facility Name":fdata["Facility Name"].astype(str),
                         "v":_N[_mcols].sum(axis=1)})
        _fac=_g.groupby("Facility Name")["v"].sum().sort_values(ascending=False).head(10)[::-1]
        if not len(_fac) or float(_fac.sum())==0: _fac=None
    _rhead("\u2462","\U0001F4C8",T("over_time")+" \u00b7 "+T("top_fac_main"),BL_D2,_lbl(_main,28))
    f=tline(_ser,f'{_lbl(_main,26)} \u2014 {T("over_time")}',BL_M,mode="full")
    if f is not None: show(f)
    else: st.info(T("no_values"))
    f=hbar(_fac,BL_D,T("top_fac_main"),mode="full") if _fac is not None else None
    if f is not None: show(f)
    # ===== ④ جدول كل الأعمدة =====
    _rhead("\u2463","\U0001F4CB",T("all_cols"),BL_D,str(len(cols)))
    with st.expander(f"{T('all_cols')} ({len(cols)})"):
        _tab=pd.DataFrame({
            "Group":[_group_of(c) for c in cols],
            "Column":cols,
            "Total":[_N[c].sum() if c in _N else 0.0 for c in cols],
            "Mean":[_N[c].mean() if c in _N else 0.0 for c in cols],
            "Max":[_N[c].max() if c in _N else 0.0 for c in cols],
        }).sort_values("Total",ascending=False)
        st.dataframe(_tab,use_container_width=True,height=340)
    _dash_foot(_sn)


# تنظيف اسم المنحة ليصبح اسم ملف صالحًا في ويندوز (بدون رموز ممنوعة)
def safe_name(name):
    return re.sub(r"[^\w\- ]","",str(name)).strip() or "unsaved"

# حفظ مشروع كامل: ملف واحد ثابت لكل منحة بنفس الاسم.
# الحفظ يستبدل النسخة القديمة (نفس الاسم) بدل إنشاء نسخة جديدة بالطابع الزمني،
# حتى لا تتراكم نسخ مكرّرة لنفس المنحة على جدار المحفظة.
def save_dashboard():
    nm=(st.session_state.get("grant") or {}).get("name") or st.session_state.get("gname","unsaved")
    base=safe_name(nm)
    data={"grant":st.session_state.get("grant",{}),"indicators":st.session_state.get("indicators",[]),"phase":st.session_state.get("phase","setup"),"saved_at":datetime.datetime.now().isoformat(),"draft":st.session_state.get("_draft",{})}
    # ابحث عن نسخة سابقة بنفس الاسم (أحدثها) واستبدلها، وإلا أنشئ ملفًا جديدًا
    p=None
    for old in sorted(glob.glob(os.path.join(SAVES_DIR,base+"_*.pkl")),key=os.path.getmtime,reverse=True):
        p=old; break
    if p is None:
        p=os.path.join(SAVES_DIR,base+"_"+datetime.datetime.now().strftime("%Y%m%d_%H%M%S")+".pkl")
    with open(p,"wb") as f: pickle.dump(data,f)
    # احذف أي نسخ أقدم لنفس المنحة حتى يبقى ملف واحد فقط
    for extra in glob.glob(os.path.join(SAVES_DIR,base+"_*.pkl")):
        if os.path.abspath(extra)!=os.path.abspath(p):
            try: os.remove(extra)
            except Exception: pass
    return p

# قراءة كل المنح المحفوظة (الأحدث أولًا) مع تجاهل الملفات الداخليّة والمتحطّمة
# وتجاهل النسخ المكرّرة: يظهر لكل منحة أحدث ملف فقط
def list_saves():
    out=[]
    seen_names=set()
    for p in sorted(glob.glob(os.path.join(SAVES_DIR,"*.pkl")),key=os.path.getmtime,reverse=True):
        bn=os.path.basename(p)
        if bn.startswith("_"): continue
        # اسم المنحة = الملف بلا ختم الزمن (_YYYYMMDD_HHMMSS.pkl)
        key=re.sub(r"_\d{8}_\d{6}\.pkl$","",bn)
        if key in seen_names: continue
        try:
            with open(p,"rb") as f: d=pickle.load(f)
            seen_names.add(key)
            out.append((p,d))
        except Exception: pass
    return out

# فتح ملف منحة محفوظ واحد
def load_save(path):
    with open(path,"rb") as f: return pickle.load(f)

# الحفظ التلقائي: يلتقط حقول الإعداد الظاهرة (الاسم/الخدمات/المستفيدين/المدة) كمسودة
# ويكتبها في _auto.pkl مع تاريخ الحفظ؛ أي خطأ يُبتلع صامتًا حتى لا تتعطل الواجهة
def autosave():
    try:
        st.session_state.pop("_autoserr",None)
        draft=None
        if st.session_state.get("phase")=="setup":
            gt=st.session_state.get("gtime")
            try:
                if isinstance(gt,(tuple,list)) and len(gt)==2: gt=list(gt)
            except Exception: pass
            draft={"name":st.session_state.get("gname",""),"services":st.session_state.get("gserv",0),"beneficiaries":st.session_state.get("gben",0),"gtime":gt}
        d={"grant":st.session_state.get("grant"),"indicators":st.session_state.get("indicators",[]),"phase":st.session_state.get("phase"),"saved_at":datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),"draft":draft}
        if d["grant"] is None and not d["indicators"] and not d["draft"]:
            return
        with open(AUTO,"wb") as f: pickle.dump(d,f)
    except Exception:
        pass

# حذف ملف الحفظ التلقائي (يُستخدم عند بدء منحة جديدة أو مسح آخر عمل)
def clear_auto():
    try:
        if os.path.exists(AUTO): os.remove(AUTO)
    except Exception: pass

# استئناف آخر عمل تلقائيًا عند تشغيل التطبيق مرة واحدة فقط (حارس _resumed):
# - إذا كانت الجلسة قد بدأت من منحة (grant ليس None) نتوقف فورًا.
# - إذا وُجد _auto.pkl نعيد المؤشرات والمنحة، والمرحلة كما كانت.
# - إذا كانت المسودة فقط (بدون مؤشرات/منحة) نعود لشاشة الإعداد form.
def maybe_resume():
    if st.session_state.get("_resumed"): return
    if st.session_state.get("grant") is not None:
        st.session_state["_resumed"]=True
        return
    if not os.path.exists(AUTO):
        st.session_state["_resumed"]=True
        return
    try:
        with open(AUTO,"rb") as f: d=pickle.load(f)
        st.session_state["_resumed"]=True
        st.session_state["_draft"]=d.get("draft") or {}
        if d.get("indicators") or d.get("grant"):
            st.session_state["indicators"]=d.get("indicators") or []
            st.session_state["grant"]=d.get("grant")
            st.session_state["phase"]=d.get("phase") or ("dashboard" if d.get("grant") else "setup")
            # ملاحظة: ما منغيّر «view» هون — أول واجهة دائمًا الصفحة الرئيسية (home).
        if d.get("draft"):
            st.session_state["phase"]="setup"
            return
    except Exception as e:
        st.session_state["_resumed"]=True
        st.session_state["_autoserr"]=str(e)

# ألوان هوية السمة الداكنة + لوحة ألوان الرسوم المتنوعة
ACCENT="#00d4ff"; BG="#0f1626"; CARD="#182341"; TEXT="#e6edf7"
COLS=("#00d4ff","#7c5cff","#ff7a59","#4ade80","#f59e0b","#ef4444","#22d3ee")

# قاموس أسماء طرق العرض بالعربية (المفتاح الإنجليزي المستخدم في الكود = التسمية العربية للنظام)
TLBL={
 "Line":"خط زمني","Bar":"أعمدة بسيطة","StackedBar":"أعمدة متراكمة","Clustered":"أعمدة مجمّعة","Area":"منطقة",
 "Combo":"خط + أعمدة","Scatter":"نقاط مبعثرة","Bubble":"فقاعات","Pie":"دائري","Donut":"دونات","Semicircle":"نصف دائرة",
 "Treemap":"أقسام Treemap","KPI":"بطاقة KPI","Histogram":"مدرج تكراري","Box":"صندوق Box","Funnel":"قمع",
 "Waterfall":"شلال","Map":"خريطة حسب الموقع","Table":"جدول بيانات","Pivot":"مصفوفة محورية","Gauge":"مقياس Gauge",
 "AgeSplit":"أعمدة عمرية (ذكور/إناث)",
}

# ===== خلفية الموقع: صورة 2.png مع طبقة تعتيم حتى تطلع الكتابة واضحة =====
BG_IMG=os.path.join(os.path.dirname(os.path.abspath(__file__)),"2.png")
def _bg_css():
    """CSS الخلفية: الصورة ثابتة خلف كل الصفحة + تعتيم ونعومة + vignette."""
    _url=""
    try:
        import base64
        if os.path.isfile(BG_IMG):
            with open(BG_IMG,"rb") as _f:
                _url="data:image/png;base64,%s"%base64.b64encode(_f.read()).decode("ascii")
    except Exception:
        _url=""
    if not _url:
        return ".stApp{background:radial-gradient(circle at 20% -10%,#14203a 0%,#0f1626 45%)}"
    return """
<style>
/* ===== لون الخلفية: كحلية بتعمى الواجهة كلها ===== */
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stHeader"]{
  background-color:#0b1220 !important;
}
/* ===== الصورة بنص الشاشة، بمقاس مربع (ما بتتمدّش مهما كان مقاس الشاشة) ===== */
#bgimg{position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:linear-gradient(180deg,rgba(9,14,26,.30) 0%,
    rgba(11,18,32,.38) 50%,rgba(7,11,21,.46) 100%),url(__BGURL__);
  background-size:100% 100%,min(50vw,50vh) min(50vw,50vh);
  background-position:center center,center center;
  background-repeat:no-repeat,no-repeat;
  background-attachment:fixed,fixed}
.block-container,.block-container *{position:relative;z-index:2}
[data-testid="stSidebar"]{background:rgba(16,26,48,.94)!important;border-right:1px solid #23324f}
[data-testid="stSidebar"] *{backdrop-filter:none}
h1{text-shadow:0 2px 12px rgba(0,0,0,.85),0 0 3px rgba(0,0,0,.75)}
h2,h3,h4,.dashhead .t{text-shadow:0 1px 10px rgba(0,0,0,.8),0 0 3px rgba(0,0,0,.7)}
p,span,div,label,li{text-shadow:0 1px 4px rgba(0,0,0,.7)}
</style>""".replace("__BGURL__",_url)

st.markdown(_bg_css(),unsafe_allow_html=True)
st.markdown('<div id="bgimg"></div>',unsafe_allow_html=True)

# ===== أنماط CSS العامة: الخلفية، بطاقات الإحصاء، شريط الخط الزمني، KPI، علب المؤشرات، الجدار =====
st.markdown(r'''
<style>
.stApp{background:transparent}
[data-testid="stSidebar"]{background:rgba(16,26,48,.97)}
h1{color:#00d4ff!important}h3{color:#e6edf7!important}
.block-container{padding-top:26px}
.stat{background:#182341;border:1px solid #23324f;border-radius:14px;padding:14px;text-align:center;color:#e6edf7;box-shadow:0 4px 18px rgba(0,0,0,.25)}
.stat b{display:block;font-size:22px;color:#00d4ff;margin-top:4px}
.stat small{color:#8aa0c0}
.up{color:#4ade80}.down{color:#ff7a59}
.tl{background:linear-gradient(180deg,#131f38,#101a30);border:1px solid #23324f;border-radius:16px;padding:14px 18px;margin-bottom:10px;box-shadow:0 4px 18px rgba(0,0,0,.28)}
.tl-bar{display:flex;align-items:center;justify-content:space-between;color:#8aa0c0;font-size:13px;margin-bottom:10px}
.tl-track{position:relative;height:14px;background:#1d2c4f;border-radius:8px}
.tl-fill{position:absolute;top:0;left:0;height:100%;background:linear-gradient(90deg,#00d4ff,#7c5cff);border-radius:8px;box-shadow:0 0 14px rgba(0,212,255,.45)}
.tl-globe{position:absolute;top:50%;transform:translate(-50%,-50%);font-size:26px}
.tl-marks{display:flex;justify-content:space-between;color:#8aa0c0;font-size:12px;margin-top:8px}
.tl-now{color:#00d4ff}
.kpis{display:flex;gap:14px;direction:ltr}
.kpi{flex:1;background:linear-gradient(180deg,#182341,#141e36);border:1px solid #23324f;border-radius:16px;padding:16px 12px;text-align:center;box-shadow:0 4px 18px rgba(0,0,0,.28)}
.kico{font-size:24px}
.klab{color:#8aa0c0;font-size:13px;margin-top:6px}
.knum{color:#00d4ff;font-size:26px;font-weight:800;margin-top:4px}
.knum.knam{color:#e6edf7;font-size:17px}
.ibox{background:linear-gradient(180deg,#182341,#151f38);border:1px solid #23324f;border-radius:18px;padding:16px;margin-bottom:14px;height:100%;box-shadow:0 6px 22px rgba(0,0,0,.3);transition:transform .15s ease}
.ibox:hover{transform:translateY(-2px);border-color:#2b3f66}
.ibox-head{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #23324f;padding-bottom:10px;margin-bottom:8px}
.ibox-title{color:#00d4ff;font-size:16px;font-weight:800}
.ibox-sub{color:#8aa0c0;font-size:12px;margin-top:3px}
.hintbox{height:100%;min-height:160px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:10px;color:#8aa0c0;background:rgba(16,26,48,.35);border:2px dashed #23324f;border-radius:18px;font-size:14px;text-align:center;padding:16px}
.hintbox b{color:#00d4ff}
.bigval{display:flex;flex-direction:column;align-items:center;line-height:1;padding:0 8px}
.bigval .bv{font-size:40px;font-weight:900}
.bigval.green .bv{color:#4ade80;text-shadow:0 0 18px rgba(74,222,128,.4)}
.bigval.warn .bv{color:#ff7a59;text-shadow:0 0 18px rgba(255,122,89,.4)}
.bigval .bvlab{color:#8aa0c0;font-size:12px;margin-top:3px}
.chip{padding:3px 12px;border-radius:20px;font-size:13px;font-weight:700;background:#10243a;color:#8aa0c0;border:1px solid #23324f}
.chip.target{color:#f59e0b;border-color:#3a2f19}
.ibx-rows{font-size:13px;color:#c7d4ea;line-height:2;background:#101a30;border:1px solid #23324f;border-radius:12px;padding:10px 12px;height:100%}
/* ===== لوحة الخدمات الصحية: كروت موحّدة + مؤشر حالة (بور بي) ===== */
.hhs-meta{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.hhs-meta .hm-ic{font-size:17px;line-height:1}
.hhs-badge{font-size:10.5px;font-weight:800;padding:3px 9px;border-radius:20px;letter-spacing:.2px;white-space:nowrap}
.hhs-badge.custom{color:#00d4ff;background:rgba(0,212,255,.12);border:1px solid rgba(0,212,255,.42)}
.hhs-badge.generic{color:#8aa0c0;background:rgba(138,160,192,.10);border:1px solid rgba(138,160,192,.30)}
.hhs-dot{display:inline-flex;align-items:center;gap:5px;font-size:10.5px;font-weight:700;color:#8aa0c0;white-space:nowrap}
.hhs-dot i{width:8px;height:8px;border-radius:50%;display:inline-block;flex:0 0 8px}
.hhs-dot.has i{background:#4ade80;box-shadow:0 0 9px rgba(74,222,128,.75)}
.hhs-dot.no  i{background:#64748b}
.hhs-dot.no{color:#64748b}
.hhs-sec{display:flex;align-items:center;gap:9px;color:#00d4ff;font-size:18px;font-weight:800;margin:20px 0 10px}
.hhs-sec .hs-n{background:#0e2a3d;border:1px solid #1d4a63;color:#00d4ff;border-radius:20px;
  font-size:11.5px;font-weight:800;padding:2px 9px;letter-spacing:.3px}
.ibx-rows b{color:#e6edf7}
.sect{display:flex;align-items:center;gap:10px;color:#00d4ff;font-size:19px;font-weight:800;margin:22px 0 12px}
.sect::after{content:"";flex:1;height:2px;background:linear-gradient(90deg,#00d4ff,#23324f)}
/* ===== شريط عنوان القسم: مستطيل واضح يبيّن إنه هون بلّش قسم جديد ===== */
.sectband{display:flex;align-items:center;gap:10px;margin:26px 0 14px;padding:11px 16px;
  border-radius:14px;border:1px solid #23324f;border-left:4px solid #00d4ff;
  background:linear-gradient(90deg,rgba(0,212,255,.16) 0%,rgba(124,92,255,.10) 45%,rgba(20,30,54,.30) 100%);
  color:#e6edf7;font-size:19px;font-weight:900;letter-spacing:.2px;
  box-shadow:0 4px 16px rgba(0,0,0,.25)}
.sectband .sb-sub{color:#8aa0c0;font-size:11px;font-weight:800;letter-spacing:1.4px;
  margin-left:auto;text-transform:uppercase}
/* ===== ترويسة الصفحة الرئيسية ===== */
.pagehead{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;
  padding:14px 18px;margin:2px 0 8px;border-radius:16px;border:1px solid #23324f;
  background:linear-gradient(90deg,rgba(0,212,255,.10),rgba(124,92,255,.08))}
.pagehead .ph-t{color:#e6edf7;font-size:26px;font-weight:900;letter-spacing:.3px;line-height:1.2}
.pagehead .ph-s{color:#00d4ff;font-size:14px;font-weight:800;margin-top:3px}
.pagehead .ph-b{color:#8aa0c0;font-size:11px;font-weight:800;letter-spacing:1.4px;text-transform:uppercase}
.wallcard{background:linear-gradient(180deg,#182341,#141e36);border:1px solid #23324f;border-radius:18px;padding:16px;margin-bottom:8px;box-shadow:0 6px 22px rgba(0,0,0,.3);transition:transform .15s ease}
.wallcard:hover{transform:translateY(-2px);border-color:#2b3f66}
/* ===== بطاقة الحساب بالسايدبار ===== */
.accbox{display:flex;gap:10px;align-items:flex-start;background:linear-gradient(180deg,#182341,#141e36);
  border:1px solid #23324f;border-radius:14px;padding:10px 12px;margin:6px 0 10px}
.acc-ic{font-size:22px;line-height:1}
.acc-meta{min-width:0}
.acc-name{color:#e6edf7;font-size:13.5px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.acc-mail{color:#8aa0c0;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:4px}
/* ===== رسم الجنس: أشخاص (ذكر/أنثى/رمادي للي ما له تصنيف) ===== */
.sexfwrap{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:4px 0 14px}
.sexf{background:linear-gradient(180deg,#182341,#141e36);border:1px solid #23324f;border-top:3px solid #23324f;
  border-radius:16px;padding:14px 10px;text-align:center;box-shadow:0 4px 18px rgba(0,0,0,.28)}
.sexf.m{border-top-color:#38bdf8}.sexf.f{border-top-color:#f472b6}.sexf.u{border-top-color:#64748b}
.sexf-ic{font-size:34px;line-height:1.1}
.sexf-v{font-size:30px;font-weight:900;color:#e6edf7;margin-top:2px;letter-spacing:-.5px}
.sexf-l{color:#8aa0c0;font-size:12.5px;font-weight:800}
.sexf-bar{height:6px;background:#1d2c4f;border-radius:6px;margin:8px 0 4px;overflow:hidden}
.sexf-bar i{display:block;height:100%;border-radius:6px}
.sexf.m .sexf-bar i{background:#38bdf8}.sexf.f .sexf-bar i{background:#f472b6}.sexf.u .sexf-bar i{background:#64748b}
.sexf-p{color:#8aa0c0;font-size:11.5px;font-weight:700}
.whead{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.wtitle{color:#00d4ff;font-size:17px;font-weight:800}
.wdate{color:#8aa0c0;font-size:11px}
.wrows{color:#c7d4ea;font-size:13px;line-height:1.9}
.wrows b{color:#e6edf7}
.wbar{height:9px;background:#1d2c4f;border-radius:6px;overflow:hidden;margin:10px 0 6px}
.wbar div{height:100%;background:linear-gradient(90deg,#00d4ff,#7c5cff);border-radius:6px}
.wfoot{color:#8aa0c0;font-size:12px}
/* ===== داشبورد خدمات الصحة: شكل احترافي ===== */
.dashwrap{background:linear-gradient(180deg,#182341,#141d34);border:1px solid #23324f;border-radius:20px;padding:16px 18px 20px;box-shadow:0 8px 28px rgba(0,0,0,.35)}
.dashhead{display:flex;align-items:center;justify-content:space-between;gap:14px;border-bottom:1px solid #23324f;padding-bottom:12px;margin-bottom:4px}
.dashhead .t{color:#e6edf7;font-size:22px;font-weight:900}
.dashhead .s{color:#8aa0c0;font-size:12.5px;margin-top:3px}
.dashhead .badge{background:linear-gradient(90deg,#00d4ff,#7c5cff);color:#06111f;font-weight:900;font-size:12px;padding:5px 14px;border-radius:20px;white-space:nowrap}
/* ===== قائمة الأسماء: تفتح بالضغط وتحطّ الداتا تحتها (ما بتغطي أي شي) ===== */
.hovlist{display:inline-block;vertical-align:top;margin:2px 0}
.hovlist>summary{cursor:pointer;list-style:none;color:#e6edf7;font-weight:900;
  border-bottom:1px dashed #00d4ff;padding:0 3px 1px;border-radius:4px}
.hovlist>summary::-webkit-details-marker{display:none}
.hovlist>summary::before{content:"▸ ";color:#00d4ff;font-size:10px;vertical-align:1px}
.hovlist[open]>summary::before{content:"▾ "}
.hovlist>summary:hover{background:#16233d;color:#fff}
.hovbody{margin-top:7px;padding:9px 12px;background:#101c33;border:1px solid #24395e;
  border-radius:10px;column-width:158px;column-gap:20px;column-rule:1px solid #1e2f4e;
  text-align:right;color:#cfe2ff;font-size:12px;font-weight:600;line-height:1.8;
  max-height:340px;overflow-y:auto}
.sechead{display:flex;align-items:center;gap:10px;margin:24px 0 12px}
.sechead .bar{width:5px;height:23px;border-radius:3px;background:linear-gradient(180deg,#00d4ff,#7c5cff)}
.sechead h4{margin:0;color:#e6edf7;font-size:16.5px;font-weight:800}
.sechead .n{color:#63779a;font-size:11.5px;margin-left:auto;white-space:nowrap}
.kcards{display:flex;gap:12px;flex-wrap:wrap}
.kcard{flex:1 1 140px;background:linear-gradient(180deg,#1c2846,#151f38);border:1px solid #23324f;border-top:3px solid var(--c,#00d4ff);border-radius:14px;padding:12px 10px;text-align:center;box-shadow:0 4px 16px rgba(0,0,0,.32)}
.kcard .ic{font-size:17px;line-height:1}
.kcard .lb{color:#8aa0c0;font-size:12px;margin-top:5px;min-height:31px;line-height:1.25}
.kcard .vl{color:var(--c,#00d4ff);font-size:25px;font-weight:900;margin-top:2px;letter-spacing:-.5px}
.kcard .sb{color:#5f739a;font-size:10.5px;margin-top:3px}
/* ===== مربع واحد فيه رقمان ===== */
.tbox{display:flex;align-items:stretch;gap:0;background:#141d34;border:1px solid #23324f;border-radius:16px;padding:5px;box-shadow:0 4px 16px rgba(0,0,0,.32)}
.tbox .sep{width:1px;background:#2b3f66;margin:8px 0}
.tbox .half{flex:1 1 0;min-width:0;background:linear-gradient(180deg,#1c2846,#161f3a);border-top:3px solid var(--c,#00d4ff);border-radius:13px;padding:13px 12px;text-align:center}
.tbox .lb{color:#8aa0c0;font-size:12.5px;line-height:1.3;min-height:32px;display:flex;align-items:center;justify-content:center}
.tbox .vl{color:var(--c,#00d4ff);font-size:28px;font-weight:900;margin-top:3px;letter-spacing:-.5px}
/* ===== مربع رقم واحد كبير ===== */
.onebig{background:linear-gradient(180deg,#1c2846,#151f38);border:1px solid #23324f;
  border-top:3px solid var(--c,#00d4ff);border-radius:14px;padding:16px 10px;text-align:center;
  display:flex;flex-direction:column;justify-content:center;min-height:150px;
  box-shadow:0 4px 16px rgba(0,0,0,.32)}
.onebig .lb{color:#8aa0c0;font-size:13px}
.onebig .vl{color:var(--c,#00d4ff);font-size:34px;font-weight:900;margin-top:8px;letter-spacing:-.5px}
/* ===== صف واحد من ٤ مربعات ===== */
.qbox4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:2px 0 6px}
.qbox4 .q{background:linear-gradient(180deg,#1c2846,#151f38);border:1px solid #23324f;
  border-top:3px solid var(--c,#00d4ff);border-radius:14px;padding:14px 8px;text-align:center;
  display:flex;flex-direction:column;justify-content:center;min-height:104px;
  box-shadow:0 4px 16px rgba(0,0,0,.32)}
.qbox4 .q .lb{color:#8aa0c0;font-size:12.5px;line-height:1.3}
.qbox4 .q .vl{color:var(--c,#00d4ff);font-size:25px;font-weight:900;margin-top:7px;letter-spacing:-.5px}
.tbox .sb{color:#5f739a;font-size:10.5px;margin-top:3px}
.tbox.t3 .vl{font-size:25px}
.agrid{width:100%;border-collapse:separate;border-spacing:6px}
.agrid th{color:#8aa0c0;font-size:12.5px;font-weight:700;padding:4px}
.agrid th.sex{color:#e6edf7;font-size:13.5px;text-align:left;width:92px}
.agrid td{background:linear-gradient(180deg,#1c2846,#161f3a);border:1px solid #23324f;border-radius:10px;padding:9px 6px;text-align:center}
.agrid td .a{color:#8aa0c0;font-size:10.5px}
.agrid td .v{font-size:18px;font-weight:900;margin-top:2px}
.agrid td.bv{color:#86efac}.agrid td.gv{color:#ef4444}
 .agrid tr.boyrow td{border-left:3px solid #86efac}
 .agrid tr.girlrow td{border-left:3px solid #ef4444}
 .agrid th.totcol{color:#e6edf7;font-size:12.5px}
 .agrid td.totcol{background:linear-gradient(180deg,#243252,#1a2542);border:1px solid #3a4d73}
 .agrid td.totcol .v{color:#e6edf7;font-size:19px;font-weight:900}
 .agrid td.totcol .a{color:#7f95b8;font-size:10px}
 .agrid tr.grandrow td{background:linear-gradient(180deg,#1f2c4d,#182142);border:1px solid #4b5f88}
 .agrid tr.grandrow th.sex{color:#00d4ff;font-size:13px}
 .agrid td.gc .v{color:#00d4ff;font-size:17px;font-weight:900}
 .qbox{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:2px 0 4px}
 .qcell{background:linear-gradient(180deg,#1c2846,#161f3a);border:1px solid #23324f;border-left:3px solid var(--c,#00d4ff);border-radius:12px;padding:10px 12px}
 .qcell .qh{color:#8aa0c0;font-size:11.5px;font-weight:700;margin-bottom:4px;display:flex;justify-content:space-between;align-items:center;gap:6px}
 .qcell .qh b{color:#cfe0ff;font-size:12.5px;font-weight:800}
 .qcell .qv{font-size:20px;font-weight:900;color:#e6edf7;line-height:1.15}
 .qcell .qs{font-size:10.5px;color:#8aa0c0;margin-top:3px}
 .qcell .qs b{font-weight:800}
 .hbox2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:2px 0 4px}
.hstack{display:grid;grid-template-columns:1fr;gap:8px;margin:2px 0 4px}
 .hbox8{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:2px 0 4px}
 .scell{background:linear-gradient(180deg,#1c2846,#161f3a);border:1px solid #23324f;border-top:3px solid var(--c,#7c5cff);border-radius:12px;padding:9px 10px;text-align:center}
 .scell .sh{color:#8aa0c0;font-size:11px;font-weight:700;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .scell .sv{font-size:18px;font-weight:900;color:#e6edf7}
 .scell .sp{font-size:10px;color:#7f95b8;margin-top:2px}
 .rhead{display:flex;align-items:center;gap:9px;margin:20px 0 10px;padding:9px 13px;
        border-radius:12px;background:linear-gradient(90deg,var(--c) 22%,var(--c) 8% 55%,#0000);
        border-right:1px solid #23324f;border-left:3px solid var(--c)}
 .rhead .rn{font-size:19px;font-weight:900;color:var(--c);opacity:.85;line-height:1}
 .rhead .ri{font-size:17px;line-height:1;filter:saturate(1.2)}
 .rhead h4{margin:0;font-size:15px;font-weight:800;color:#e6edf7;flex:1;line-height:1.25}
 .rhead .n{font-size:11px;color:#8aa0c0;font-weight:700;text-align:left;white-space:nowrap}
 .pbar{height:4px;border-radius:99px;background:#ffffff14;overflow:hidden;margin-top:6px}
 .pbar i{display:block;height:100%;border-radius:99px}
 .stack{display:flex;height:9px;border-radius:99px;overflow:hidden;background:#ffffff14;margin:4px 0 2px}
 .stack i{display:block;height:100%}
 .qcell{position:relative;overflow:hidden}
 .scell{transition:transform .12s ease}
 .legendrow{display:flex;gap:12px;flex-wrap:wrap;margin:2px 0 8px;font-size:11px;color:#8aa0c0}
 .legendrow span{display:flex;align-items:center;gap:5px}
 .legendrow b{width:9px;height:9px;border-radius:3px;display:inline-block}
 .ct{color:#e6edf7;font-size:12.5px;font-weight:800;text-align:center;margin:6px 0 2px}
 .ctwrap{display:flex;flex-direction:column;align-items:center}
 /* ===== شبكة المربعات: كل مربع بلاطة مستقلة بعنوانها ===== */
 .mbox{border:1px solid #2b3f66;border-radius:14px;background:#1c2846;
       padding:10px 12px 12px;margin:0 0 12px;height:100%}
 .mbox .mh{display:flex;align-items:center;gap:8px;margin:0 0 6px;
           border-bottom:1px solid #2b3f66;padding-bottom:6px}
 .mbox .mh .mi{font-size:19px;line-height:1}
 .mbox .mh h4{margin:0;font-size:16px;font-weight:800;color:#e6edf7;flex:1}
 .mbox .mh .mn{font-size:11.5px;color:#8aa0c0;font-weight:600}
 .mbox .ct{text-align:right;padding-right:2px}
 .mbox .qcell{font-size:13px}
.mini2{display:flex;gap:12px;flex-wrap:wrap}
.mini2 .kcard{flex:1 1 200px}
.foot-note{color:#63779a;font-size:11.5px;text-align:center;margin-top:14px;padding-top:10px;border-top:1px solid #23324f}
</style>
''',unsafe_allow_html=True)

# ===== شاشة الافتتاح Splash: تختفي تلقائيًا بعد 2.2 ثانية =====
st.markdown(r'''
<style>
@keyframes splSh{0%,70%{opacity:1;visibility:visible}100%{opacity:0;visibility:hidden}}
@keyframes splSpin{to{transform:rotate(360deg)}}
#spl{position:fixed;top:0;left:0;width:100vw;height:100vh;background:#0f1626;z-index:99999;display:flex;align-items:center;justify-content:center;flex-direction:column;animation:splSh 2.2s ease 1.6s forwards}
#spl h1{color:#00d4ff;font-size:54px;margin:0;letter-spacing:6px}
#spl .splabel{color:#8aa0c0;font-size:15px;margin-top:18px;letter-spacing:3px}
#spl .spn{width:52px;height:52px;border:5px solid #23324f;border-top-color:#00d4ff;border-radius:50%;animation:splSpin 0.7s linear infinite}
</style>
<div id="spl"><h1>SAMS</h1><div class="splabel">لوحة متابعة المشاريع الإنسانية</div><div class="spn"></div></div>
''',unsafe_allow_html=True)

# رسم Treemap مبسّط يدويًا: مستطيلات أفقية متجاورة بنسب القيم
def _treemap(ax,sizes,labels,colors):
    import matplotlib.patches as mpatches
    tot=float(sum(sizes)) or 1.0
    order=sorted(range(len(sizes)),key=lambda k:sizes[k],reverse=True)
    x,y,w,h=0.0,0.0,1.0,1.0
    for k in order:
        fw=sizes[k]/tot
        c=colors[k%len(colors)]
        ax.add_patch(mpatches.Rectangle((x,y),w,fw*h,facecolor=c,edgecolor="#0f1626",linewidth=2))
        if w*fw>0.13 and h>0.18:
            ax.text(x+w*fw/2,y+h/2,f"{labels[k]}\n{sizes[k]:,.0f}",ha="center",va="center",color="#e6edf7",fontsize=7.5,linespacing=1.5)
        x+=w*fw
    ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")

def _sq_layoutrow(sizes,x,y,dx,dy):
    covered=sum(sizes); width=covered/dy; rects=[]; cy=y
    for s in sizes:
        rects.append((x,cy,width,s/width)); cy+=s/width
    return rects

def _sq_layoutcol(sizes,x,y,dx,dy):
    covered=sum(sizes); height=covered/dx; rects=[]; cx=x
    for s in sizes:
        rects.append((cx,y,s/height,height)); cx+=s/height
    return rects

def _sq_layout(sizes,x,y,dx,dy):
    return _sq_layoutrow(sizes,x,y,dx,dy) if dx>=dy else _sq_layoutcol(sizes,x,y,dx,dy)

def _sq_leftover(sizes,x,y,dx,dy):
    covered=sum(sizes)
    if dx>=dy:
        width=covered/dy; return (x+width,y,dx-width,dy)
    height=covered/dx; return (x,y+height,dx,dy-height)

def _sq_worst(sizes,x,y,dx,dy):
    rects=_sq_layout(sizes,x,y,dx,dy)
    return max([max(r[2]/r[3],r[3]/r[2]) for r in rects])

def _squarify(sizes,x,y,dx,dy):
    rects=[]; row=[]; i=0
    while i<len(sizes):
        cand=row+[sizes[i]]
        if not row or _sq_worst(cand,x,y,dx,dy)<=_sq_worst(row,x,y,dx,dy):
            row=cand; i+=1
        else:
            rects+=_sq_layout(row,x,y,dx,dy)
            x,y,dx,dy=_sq_leftover(row,x,y,dx,dy); row=[]
    if row: rects+=_sq_layout(row,x,y,dx,dy)
    return rects

def _treemap_sq(ax,sizes,labels,colors):
    import matplotlib.patches as mpatches
    tot=float(sum(sizes)) or 1.0
    order=sorted(range(len(sizes)),key=lambda k:sizes[k],reverse=True)
    norm=[sizes[k]/tot for k in order]
    for k,r in zip(order,_squarify(norm,0.0,0.0,1.0,1.0)):
        x,y,w,h=r
        ax.add_patch(mpatches.Rectangle((x,y),w,h,facecolor=colors[k%len(colors)],
                                        edgecolor="#0f1626",linewidth=2))
        if w>0.10 and h>0.10:
            fs=9 if (w>0.25 and h>0.25) else 7.2
            ax.text(x+w/2,y+h/2,f"{labels[k]}\n{sizes[k]:,}",ha="center",va="center",
                    color="#e6edf7",fontsize=fs,fontweight="700",linespacing=1.5)
    ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")

# تحويل قيم عمود Y2 إلى أحجام فقاعات بين 300 و 1120 (للرسم الفقاعي)
def _rescale(vals2):
    a=min(vals2); b=max(vals2)
    return [300+(x-a)/max(1e-09,b-a)*820 for x in vals2]

# ===== إعدادات موحّدة لكل الرسومات (مقاس + خطوط + هوامش) =====
# FW,FH: مقاس واحد ثابت لكل أنواع الرسوم => رسوم متناظرة ومتساوية الأبعاد
FW,FH=(8.6,5.0)
FS_TICK=11        # خط أرقام المحاور
FS_LABEL=11       # خط أسماء المحاور
FS_TITLE=14       # خط عنوان الرسم
FS_VALUE=10       # خط الأرقام فوق النقاط والأشرطة
FS_LEGEND=10      # خط مفتاح الألوان (legend)
# مساحة محفوظة لعنوان الرسم ومفتاح الألوان وللمجاميع حتى لا تختفي تحت الرسم
PAD_TOP=0.86
PAD_BOTTOM=0.14
PAD_LEFT=0.10
PAD_RIGHT=0.97

# المولّد الرئيسي لكل الرسوم: يعيد (fig, None, err) حيث err رسالة خطأ بالعربية عند الفشل.
# يعمل أولًا على تجميع زمني اختياري (يومي/أسبوعي/شهري/سنوي) لطرق الخط/المساحة/الكومبو،
# ثم يوزع على كل فرع حسب ctype (خط، أعمدة، شلال، قمع، KPI، وغيرها).
def _is_male_col(name):
    # كلمة «male» تظهر داخل «Female» أيضًا، لذلك نفحص «males»/«male» بشكل مستقل
    # ونستبعد العمود إذا بدأ بكلمة Female/ Women / Girl.
    s=str(name)
    if re.search(r"\b(female|females|woman|women|girl|girls)\b",s,re.I): return False
    return bool(re.search(r"\b(male|males|man|men|boy|boys)\b",s,re.I))

def _is_female_col(name):
    return bool(re.search(r"\b(female|females|woman|women|girl|girls)\b",str(name),re.I))

def _age_gender_pairs(df):
    # ===== كشف أعمدة الفئات العمرية للنوعين (ذكور/إناث) =====
    # يبحث عن أعمدة بصيغة «<sex> <age phrase>» مثل:
    #   Females under 5 / Males from 18 to 49 / ...
    # ملاحظة: كلمة «male» تظهر داخل «Female» أيضًا، لذلك نفصل بين الجنسين بدالة
    # مستقلة (_is_male_col) تستبعد الكلمات الأنثوية أولًا قبل مطابقة «male».
    mcols=[c for c in df.columns if _is_male_col(c)]
    fcols=[c for c in df.columns if _is_female_col(c)]
    if not mcols or not fcols: return None
    return mcols,fcols

def _age_order_key(name):
    # ترتيب الفئات العمرية منطقيًا: أقل من 5 ثم 5-17 ثم 18-49 ثم 50+
    s=str(name).lower()
    if re.search(r"under\s*5|less than\s*5|أقل من|تحت",s): return 0
    if re.search(r"5\s*(to|-|–)\s*17",s): return 1
    if re.search(r"18\s*(to|-|–)\s*49",s): return 2
    if re.search(r"over\s*5|above\s*5|فوق|أكثر من",s): return 3
    m=re.search(r"(\d+)\s*(to|-|–)\s*(\d+)",s)
    if m: return 10+int(m.group(1))
    return 99

def make_agesplit_fig(df,target=None,title=None,use_improved=False,period_label="",cols=None,fcol=None,fvals=None,dcol=None,sd=None,ed=None):
    # ===== رسم «الأعمدة العمرية»: 4 فئات عمرية على المحور X، وعمودان متجاوران لكل فئة =====
    # عمود للذكور وعمود للإناث. المحور Y = عدد الأشخاص (مجموع كل الجلسات).
    # البيانات مخزنة كأعمدة عريضة (كل جلسة صف وكل فئة عمود)، فنجمع الأعمدة أفقيًا.
    # cols  = أعمدة يختارها المستخدم بنفسه: {"m0".."m3" للذكور, "f0".."f3" للإناث}.
    # fcol/fvals = فلتر اختياري (مثل Service provider code) يُطبَّق قبل الحساب.
    # dcol/sd/ed = قصّ زمن المنحة على عمود التاريخ (مثل Session date) قبل الحساب.
    # ملاحظة: الفلاتر هنا تُطبَّق على الرسم العمري فقط، ولا تمسّ فلاتر المؤشرات الأخرى.
    _srcdf=df
    _n0=len(df)
    _warn=None
    if dcol and dcol in df.columns and sd and ed:
        _d=pd.to_datetime(df[dcol],errors="coerce")
        _s=pd.to_datetime(sd); _e=pd.to_datetime(ed)
        df=df[_d.notna() & (_d>=_s) & (_d<_e+pd.Timedelta(days=1))]
    if fcol and fcol in df.columns and fvals:
        _s=df[fcol].astype(str)
        _want=set(str(v) for v in fvals)
        df=df[_s.isin(_want)]
    labmap={0:"أقل من 5",1:"5 - 17",2:"18 - 49",3:"50 فأكثر"}
    if cols:
        _need=("m0","m1","m2","m3","f0","f1","f2","f3")
        if not all(cols.get(k) for k in _need):
            return None,None,"لازم تختار الأعمدة الثمانية (٤ ذكور + ٤ إناث) من إعدادات المؤشر"
        missing=[cols[k] for k in _need if cols[k] not in df.columns]
        if missing:
            return None,None,("أعمدة غير موجودة بالملف: " + "، ".join(str(m) for m in missing))
        mv=[float(pd.to_numeric(df[cols["m%d"%i]],errors="coerce").fillna(0).sum()) for i in range(4)]
        fv=[float(pd.to_numeric(df[cols["f%d"%i]],errors="coerce").fillna(0).sum()) for i in range(4)]
        labels=[labmap[i] for i in range(4)]
        used=[cols[k] for k in _need]
    else:
        pr=_age_gender_pairs(df)
        if pr is None: return None,None,"لا توجد أعمدة ذكور/إناث مع الفئات العمرية في هذا الملف"
        mcols,fcols=pr
        sfx=".1" if use_improved else ""
        def _sel(cc):
            out=[]
            for c in cc:
                cn=str(c)
                if use_improved:
                    if cn.endswith(sfx): out.append(c)
                else:
                    if not cn.endswith(".1"): out.append(c)
            return out
        mc=_sel(mcols); fc=_sel(fcols)
        if not mc and not fc: return None,None,"لم يتم العثور على أعمدة الفئات العمرية"
        def _by_band(cc):
            d={}
            for c in cc:
                k=_age_order_key(c)
                k=min(k,3) if k<99 else k
                d[k]=d.get(k,0.0)+pd.to_numeric(df[c],errors="coerce").fillna(0).sum()
            return d
        mb=_by_band(mc); fb=_by_band(fc)
        keys=sorted(set(list(mb.keys())+list(fb.keys())))
        labels=[labmap.get(k,f"فئة {k}") for k in keys]
        mv=[float(mb.get(k,0.0)) for k in keys]
        fv=[float(fb.get(k,0.0)) for k in keys]
        used=list(mc)+list(fc)
    if not labels: return None,None,"لا توجد فئات عمرية صالحة"
    # ===== تحذير: لا صفوف داخل الفترة الحالية =====
    # إذا كان الملف بعد الفلترة فارغًا (أو كل الأعمدة صفرية) فلا يظهر أي عمود،
    # ويبدو الرسم وكأنه محاور فقط. نُنبّه المستخدم ونرجع الخطأ مع الأرقام الكاملة.
    if len(df)==0:
        _extra=""
        if dcol and dcol in _srcdf.columns:
            _all=pd.to_datetime(_srcdf[dcol],errors="coerce").dropna()
            if len(_all):
                _extra=(" — نطاق «%s» بالملف من %s إلى %s"
                        % (dcol,_all.min().date(),_all.max().date()))
        if fcol and fcol in _srcdf.columns:
            _extra+=(" | عمود الفلتر «%s» فيه %d قيمة مختلفة"
                     % (fcol,_srcdf[fcol].nunique(dropna=True)))
        return None,None,("لا توجد صفوف بعد الفلترة" + _extra +
                          " — وسّع زمن المنحة أو راجع قيم الفلتر.")
    if (sum(mv)+sum(fv))<=0:
        # صفوف موجودة لكن كل الأرقام صفر: نُظهر أصفارًا بدل رسالة خطأ، مع تنبيه.
        _warn="⚠️ كل أرقام الفئات العمرية صفر داخل الفترة/الفلاتر الحالية."
        if dcol and dcol in _srcdf.columns:
            _all=pd.to_datetime(_srcdf[dcol],errors="coerce").dropna()
            if len(_all): _warn+=f" نطاق «{dcol}» بالملف: {_all.min().date()} → {_all.max().date()}."
        _warn+=" وسّع زمن المنحة أو راجع قيم الفلتر."
    fig,ax=plt.subplots(figsize=(FW,FH),facecolor="#0f1626",dpi=110)
    ax.set_facecolor("#0f1626")
    for s in ax.spines.values(): s.set_color("#23324f")
    ax.tick_params(colors="#8aa0c0",labelsize=FS_TICK)
    n=len(labels)
    w=0.36
    idx=list(range(n))
    # عمود ذكور (أروق فاتح) وعمود إناث (أحمر) متجاوران لكل فئة عمرية
    ax.bar([i-w/2 for i in idx],mv,width=w,color=SEX_M,alpha=0.92,label=sex_lab("ذكور"),zorder=3)
    ax.bar([i+w/2 for i in idx],fv,width=w,color=SEX_F,alpha=0.92,label=sex_lab("إناث"),zorder=3)
    # الأرقام فوق كل عمود
    for i,(a_,b_) in enumerate(zip(mv,fv)):
        if a_: ax.text(i-w/2,a_,f"{a_:,.0f}",ha="center",va="bottom",color="#e6edf7",fontsize=FS_VALUE-2,zorder=4)
        if b_: ax.text(i+w/2,b_,f"{b_:,.0f}",ha="center",va="bottom",color="#e6edf7",fontsize=FS_VALUE-2,zorder=4)
    ax.set_xticks(idx); ax.set_xticklabels(labels)
    ax.set_xlabel("الفئة العمرية",color="#8aa0c0",fontsize=FS_LABEL)
    ax.set_ylabel("عدد الأشخاص",color="#8aa0c0",fontsize=FS_LABEL)
    ax.grid(color="#23324f",alpha=0.4,axis="y",zorder=0)
    ax.set_axisbelow(True)
    _tot_m=sum(mv); _tot_f=sum(fv)
    ax.set_title(f"ذكور: {_tot_m:,.0f}   |   إناث: {_tot_f:,.0f}   |   الإجمالي: {_tot_m+_tot_f:,.0f}",
                 color="#e6edf7",fontsize=FS_VALUE,pad=10)
    leg=ax.legend(loc="upper right",facecolor="#101a30",edgecolor="#23324f",fontsize=FS_TICK-1)
    for t_ in leg.get_texts(): t_.set_color("#e6edf7")
    fig.tight_layout()
    return fig,{"males":mv,"females":fv,"labels":labels,"used_cols":used,
                "total_males":_tot_m,"total_females":_tot_f,
                "grand_total":_tot_m+_tot_f,
                "rows_used":len(df),"rows_before":_n0,
                "warning":_warn},None


def md_html(block):
    # ===== عرض HTML داخل st.markdown بدون ما يتحوّل إلى نص =====
    # السبب: محرّك markdown إذا واجد أول سطر بـ 4 مسافات أو أكثر يعتبره
    # «code block» ويطبع الـ HTML كنص عادي بدل ما يرسمه.
    # الحل: نزيح المسافات البادئة من كل سطر قبل العرض.
    # الدالة ما بتحذف ولا بتغيّر المحتوى — فقط بتزيل الفراغات البادئة.
    return "\n".join(
        ln.strip() for ln in str(block).strip().split("\n") if ln.strip()
    )


def agesplit_counts(df,use_improved=False,cols=None,fcol=None,fvals=None,dcol=None,sd=None,ed=None):
    # ===== نفس حساب «الأعمدة العمرية» لكن بلا رسم =====
    # تُستخدم في بطاقة المؤشر ليكون «المحقق» = مجموع الذكور + الإناث
    # من نفس الفلترة (نفس زمن المنحة ونفس Service provider code).
    # ترجع قاموسًا فيه الذكور والإناث والإجمالي، أو (None, رسالة الخطأ).
    labmap={0:"أقل من 5",1:"5 - 17",2:"18 - 49",3:"50 فأكثر"}
    if dcol and dcol in df.columns and sd and ed:
        _d=pd.to_datetime(df[dcol],errors="coerce")
        _s=pd.to_datetime(sd); _e=pd.to_datetime(ed)
        df=df[_d.notna() & (_d>=_s) & (_d<_e+pd.Timedelta(days=1))]
    if fcol and fcol in df.columns and fvals:
        _want=set(str(v) for v in fvals)
        df=df[df[fcol].astype(str).isin(_want)]
    if cols:
        _need=("m0","m1","m2","m3","f0","f1","f2","f3")
        if not all(cols.get(k) for k in _need):
            return None,"لازم تختار الأعمدة الثمانية (٤ ذكور + ٤ إناث) من إعدادات المؤشر"
        missing=[cols[k] for k in _need if cols[k] not in df.columns]
        if missing:
            return None,("أعمدة غير موجودة بالملف: " + "، ".join(str(m) for m in missing))
        mv=[float(pd.to_numeric(df[cols["m%d"%i]],errors="coerce").fillna(0).sum()) for i in range(4)]
        fv=[float(pd.to_numeric(df[cols["f%d"%i]],errors="coerce").fillna(0).sum()) for i in range(4)]
        labels=[labmap[i] for i in range(4)]
    else:
        pr=_age_gender_pairs(df)
        if pr is None: return None,"لا توجد أعمدة ذكور/إناث مع الفئات العمرية في هذا الملف"
        mcols,fcols=pr
        sfx=".1" if use_improved else ""
        def _sel(cc):
            out=[]
            for c in cc:
                cn=str(c)
                if use_improved:
                    if cn.endswith(sfx): out.append(c)
                else:
                    if not cn.endswith(".1"): out.append(c)
            return out
        mc=_sel(mcols); fc=_sel(fcols)
        if not mc and not fc: return None,"لم يتم العثور على أعمدة الفئات العمرية"
        def _by_band(cc):
            d={}
            for c in cc:
                k=_age_order_key(c)
                k=min(k,3) if k<99 else k
                d[k]=d.get(k,0.0)+pd.to_numeric(df[c],errors="coerce").fillna(0).sum()
            return d
        mb=_by_band(mc); fb=_by_band(fc)
        keys=sorted(set(list(mb.keys())+list(fb.keys())))
        labels=[labmap.get(k,f"فئة {k}") for k in keys]
        mv=[float(mb.get(k,0.0)) for k in keys]
        fv=[float(fb.get(k,0.0)) for k in keys]
    tm=float(sum(mv)); tf=float(sum(fv))
    return {"males":mv,"females":fv,"labels":labels,
            "total_males":tm,"total_females":tf,"grand_total":tm+tf,
            "rows_used":len(df)},None

def make_fig(df,lcol,vcol,ctype,vcol2=None,xlabel=None,ylabel=None,nticks=None,full=None,period=None,agg="مجموع",title=None,target=None,pctv=None,good_vals=None,done=None,pct_mode=None):
    if (ctype in ("Line","Area","Combo")) and period and lcol in df.columns and vcol in df.columns:
        # تجميع زمني (يومي/أسبوعي/شهري/سنوي) قبل الرسم — الفهرس يُصنع من التواريخ
        dcol=pd.to_datetime(df[lcol],errors="coerce")
        tmp=df[dcol.notna()].copy()
        if tmp.empty: return None,None,"لا توجد تواريخ صالحة"
        d2=pd.to_datetime(tmp[lcol],errors="coerce")
        if period=="يومي": key=d2.dt.floor("D")
        elif period=="أسبوعي": key=d2.dt.to_period("W").dt.start_time
        elif period=="شهري": key=d2.dt.to_period("M").dt.start_time
        else: key=d2.dt.to_period("Y").dt.start_time
        tmp["_k"]=key
        # طريقة الحساب المختارة: «مجموع» = عدد السجلات، «متوسط» = المتوسط الحسابي
        def _agg(colname):
            if agg=="متوسط":
                nums=pd.to_numeric(tmp[colname],errors="coerce")
                g=pd.DataFrame({"_k":key,"_v":nums}).groupby("_k")["_v"]
                return g.mean()
            return tmp.groupby("_k")[colname].count()
        def _lab(ix):
            return (ix.strftime("%Y-%m-%d") if period!="شهري" else ix.strftime("%Y-%m"))
        grp=_agg(vcol)
        if grp.empty: return None,None,"لا توجد بيانات بعد التجميع"
        out={lcol:[_lab(d) for d in grp.index], vcol:grp.values}
        if vcol2 in df.columns:
            out[vcol2]=_agg(vcol2).values
        df=pd.DataFrame(out)
    labels=df[lcol].astype(str).tolist()
    raw=df[vcol]
    if pd.to_numeric(raw,errors="coerce").notna().mean() < 0.6:
        # العمود ليس رقميًا — نحسب تكرار كل فئة ونرسمها دائريًا مع عدد السجلات
        cnt=raw.astype(str).value_counts()
        cats=cnt.index.tolist(); vs=cnt.values.tolist()
        if not vs or len(vs)==0:
            return None,None,"لا توجد قيم لذلك المؤشر"
        fcnt=None
        if full is not None and vcol in full.columns:
            fcnt=full[vcol].astype(str).value_counts()
        # نفس مقاس كل الرسومات (FW,FH) الموحّد حتى تكون متناظرة ومتساوية الأبعاد
        fig,ax=plt.subplots(figsize=(FW,FH),facecolor="#0f1626",dpi=110)
        ax.set_facecolor("#0f1626")
        colors=[COLS[i%len(COLS)] for i in range(len(vs))]
        ax.pie(vs,labels=[str(c) for c in cats],autopct=lambda p:(f"{p:.0f}%" if p else ""),startangle=90,textprops={"color":"#e6edf7","fontsize":8},colors=colors,wedgeprops={"edgecolor":"#0f1626","linewidth":2})
        ax.axis("equal")
        if fcnt is not None:
            note=" | ".join(f"{c}: {v} / {int(fcnt.get(str(c),0))}" for c,v in zip(cats,vs))
            ax.set_title(f"[المفلك / الكلي] {note}",color="#8aa0c0",fontsize=7,pad=8)
        else:
            ax.set_title(f"عدد السجلات: {len(raw)}",color="#8aa0c0",fontsize=8)
        return fig,None,None
    vals=pd.to_numeric(raw,errors="coerce").dropna().replace([np.inf,-np.inf],np.nan).dropna().tolist()
    if not vals: return None,None,"عمود القيم ما فيه أرقام"
    vals2=[]
    if vcol2 is not None:
        vals2=pd.to_numeric(df[vcol2],errors="coerce").dropna().replace([np.inf,-np.inf],np.nan).dropna().tolist()
    n=len(vals)
    if ctype in ("StackedBar","Clustered","Combo") and not vals2:
        return None,None,f"{TLBL.get(ctype,ctype)} يحتاج عمودًا ثانيًا (Y2) — اختره من «عمود ثانٍ» في إعداد المؤشر"
    # مقاس موحّد لكل أنواع الرسوم عبر الثوابت العامة FW,FH => كل الرسومات متناظرة
    fw,fh=(FW,FH); fs_min=FS_VALUE
    fig,ax=plt.subplots(figsize=(fw,fh),facecolor="#0f1626",dpi=110)
    ax.set_facecolor("#0f1626")
    for s in ax.spines.values(): s.set_color("#23324f")
    ax.tick_params(colors="#8aa0c0",labelsize=FS_TICK)
    if ctype=="Line":
        # ===== تلوين الرسم حسب قيمة كل نقطة =====
        # القيم المحققة (4 و5 افتراضيًا) بالأخضر، وباقي القيم (1 و2 و3) بالأحمر.
        # كل خط/نقطة تأخذ لون فئتها، ويُبنى مفتاح ألوان حقيقي (legend) يشرح كل لون للقارئ.
        try:
            _gvk=set()
            for _g in (good_vals or [4,5]):
                try: _gvk.add(float(_g))
                except Exception: pass
        except Exception: _gvk={4.0,5.0}
        def _vc(z):
            # لون القيمة: أخضر للقيم المحققة (سهل الوصول 4/5)، وعنبري فاتح للباقي (صعب الوصول 1/2/3)
            try: return "#22c55e" if float(z) in _gvk else "#fbbf24"
            except Exception: return "#8aa0c0"
        # نرسم كل نقطة لوحدها بلونها، ونترك الخط يجمعها بشكل متصل
        ax.plot(range(n),vals,marker="o",markersize=6,linewidth=2.4,color=COLS[0],alpha=0.35,zorder=2)
        ax.fill_between(range(n),vals,alpha=0.06,color=COLS[0])
        ax.grid(color="#23324f",alpha=0.4,axis="y")
        for k in range(n):
            _c=_vc(vals[k])
            ax.plot([k],[float(vals[k])],marker="o",markersize=8,color=_c,markeredgecolor="white",markeredgewidth=1.2,zorder=4,linestyle="none")
            ax.text(k,float(vals[k]),f"{vals[k]:,.0f}",ha="center",va="bottom",color=_c,fontsize=FS_VALUE,fontweight="bold",zorder=5,
                    bbox=dict(boxstyle="round,pad=0.15",facecolor="#0f1626",edgecolor="none"))
        # مفتاح ألوان حقيقي يشرح معنى كل لون (يظهر في كل الرسوم الخطية)
        from matplotlib.lines import Line2D as _L2
        _lbl_ok=("، ".join(str(int(x)) for x in sorted(_gvk))) if _gvk else "—"
        ax.legend(handles=[
            _L2([0],[0],marker="o",color="#22c55e",markersize=8,linestyle="none",label=f"سهل الوصول ({_lbl_ok}) — محقق"),
            _L2([0],[0],marker="o",color="#fbbf24",markersize=8,linestyle="none",label="صعب الوصول (1، 2، 3) — غير محقق"),
        ],facecolor=CARD,edgecolor="#23324f",labelcolor="#aebfe0",fontsize=FS_LEGEND,loc="upper right",framealpha=0.9)
        if vals2:
            nn2=min(len(vals2),n)
            ax.plot(range(nn2),vals2[:nn2],marker="s",markersize=5,linewidth=2.2,color=COLS[1],alpha=0.35,zorder=2)
            for k in range(nn2):
                _c2=_vc(vals2[k])
                ax.plot([k],[float(vals2[k])],marker="s",markersize=7,color=_c2,markeredgecolor="white",markeredgewidth=1.1,zorder=4,linestyle="none")
                ax.text(k,float(vals2[k]),f"{vals2[k]:,.0f}",ha="center",va="bottom",color=_c2,fontsize=FS_VALUE,fontweight="bold",zorder=5,
                        bbox=dict(boxstyle="round,pad=0.15",facecolor="#0f1626",edgecolor="none"))
            # شريط أرقام مجمّعة سريعة: مجموع Y، مجموع Y2، والإجمالي
            # أرقام مجمّعة سريعة تُحسب من الجدول الكامل (بلا فلتر) — لأن النتيجة = كامل الجدول
            s1=float(sum(vals)); s2=float(sum(vals2[:nn2]))
            if full is not None:
                try:
                    if vcol in full.columns:
                        s1=float(sum(pd.to_numeric(full[vcol],errors="coerce").replace([np.inf,-np.inf],np.nan).dropna()))
                    if vcol2 in full.columns:
                        s2=float(sum(pd.to_numeric(full[vcol2],errors="coerce").replace([np.inf,-np.inf],np.nan).dropna()))
                except Exception: pass
            ax.text(0.5,1.035,f"مجموع {vcol}: {s1:,.0f}   |   مجموع {vcol2}: {s2:,.0f}   |   الإجمالي: {s1+s2:,.0f}",
                    transform=ax.transAxes,ha="center",va="bottom",color="#e6edf7",fontsize=9.2,
                    bbox=dict(boxstyle="round,pad=0.35",facecolor="#182442",edgecolor="#33476b",linewidth=1))
        elif target is not None and target>0:
            ax.text(0.5,1.02,f"الإجمالي: {float(sum(vals)):,.0f}   —   الهدف {target:.0f}%",transform=ax.transAxes,ha="center",va="bottom",color="#8aa0c0",fontsize=8)
        # ===== مفتاح الألوان: معنى كل لون + عدد الإجابات في كل فئة =====
        # القيم المحققة (4 و5) = سهل الوصول بأخضر، وباقي القيم (1 و2 و3) = صعب الوصول بعنبري فاتح.
        # يُحسب العدد من الجدول الكامل (بلا فلتر) حتى يطابق النسبة المحسوبة.
        try:
            _gv=good_vals or [4,5]
            _ok=set()
            for _g in _gv:
                try: _ok.add(float(_g))
                except Exception: pass
            if full is not None and vcol in full.columns:
                _src=full
            else:
                _src=df
            _vv=pd.to_numeric(_src[vcol],errors="coerce").replace([np.inf,-np.inf],np.nan).dropna()
            _nok=int(sum(1 for z in _vv if float(z) in _ok))
            _nbad=int(len(_vv)-_nok)
            _g1=("، ".join(str(int(x)) for x in sorted(_ok))) if _ok else "—"
            _g2=("، ".join(str(int(z)) for z in sorted(set(float(x) for x in _vv) - _ok))) if (set(float(x) for x in _vv)-_ok) else "—"
            ax.text(0.5,-0.135,
                    f"🟢 {vcol}: {_g1} = سهل الوصول / محقق — {_nok:,} رد   |   🟡 باقي القيم ({_g2}) = صعب الوصول — {_nbad:,} رد",
                    transform=ax.transAxes,ha="center",va="top",color="#aebfe0",fontsize=9,
                    bbox=dict(boxstyle="round,pad=0.35",facecolor="#182442",edgecolor="#33476b",linewidth=1))
        except Exception: pass
    elif ctype=="Bar":
        if vals2:
            w=0.35;nn=len(vals2)
            ax.bar([i-w/2 for i in range(n)],vals,color=COLS[0],alpha=0.92,width=w,label=vcol)
            ax.bar([i+w/2 for i in range(nn)],vals2[:nn],color=COLS[1],alpha=0.92,width=w,label=vcol2)
        else: ax.bar(range(n),vals,color=COLS[0],alpha=0.92,width=0.6)
        ax.grid(color="#23324f",alpha=0.35,axis="y")
        for i,v in enumerate(vals): ax.text(i,v,f"{v:,.0f}",ha="center",va="bottom",fontsize=8.5,color="#e6edf7")
    elif ctype=="Area":
        ax.fill_between(range(n),vals,color=COLS[2],alpha=0.5,label=vcol);ax.plot(range(n),vals,color=COLS[2],linewidth=2)
        ax.grid(color="#23324f",alpha=0.35,axis="y")
        if vals2: ax.fill_between(range(min(len(vals2),n)),vals2[:n],color=COLS[1],alpha=0.35,label=vcol2);ax.plot(range(min(len(vals2),n)),vals2[:n],color=COLS[1],linewidth=2)
    elif ctype=="Scatter":
        xr=pd.to_numeric(df[lcol],errors="coerce").replace([np.inf,-np.inf],np.nan).dropna().tolist()
        if len(xr)==n:
            ax.scatter(xr,vals,s=70,color=COLS[1],alpha=0.9,edgecolors="white",linewidths=0.6,label=vcol)
            if vals2: ax.scatter(xr[:len(vals2)],vals2[:len(vals2)],s=60,color=COLS[4],alpha=0.9,edgecolors="white",linewidths=0.6,marker="^",label=vcol2)
        else:
            ax.scatter(range(n),vals,s=70,color=COLS[1],alpha=0.9,edgecolors="white",linewidths=0.6,label=vcol)
            if vals2: ax.scatter(range(len(vals2)),vals2[:len(vals2)],s=60,color=COLS[4],alpha=0.9,edgecolors="white",linewidths=0.6,marker="^",label=vcol2)
        ax.grid(color="#23324f",alpha=0.35)
    elif ctype=="Pie":
        ax.pie(vals,labels=labels[:n],autopct="%1.1f%%",colors=COLS[:n],textprops={"color":TEXT,"fontsize":8})
    elif ctype=="Histogram":
        ax.hist(vals,bins=min(15,n),color=COLS[0],alpha=0.85,edgecolor="white")
        ax.grid(color="#23324f",alpha=0.35,axis="y")
    elif ctype=="Box":
        ax.boxplot(vals,patch_artist=True,boxprops=dict(facecolor=COLS[0],alpha=0.6),medianprops=dict(color="white"))
    elif ctype=="StackedBar":
        ax.bar(range(n),vals,color=COLS[0],alpha=0.92,width=0.6,label=vcol)
        if vals2:
            mn=min(len(vals2),n)
            ax.bar(range(mn),vals2[:mn],bottom=vals[:mn],color=COLS[1],alpha=0.92,width=0.6,label=vcol2)
        ax.grid(color="#23324f",alpha=0.4,axis="y")
    elif ctype=="Clustered":
        w=0.35; nn=len(vals2) if vals2 else 0
        ax.bar([i-w/2 for i in range(n)],vals,color=COLS[0],alpha=0.92,width=w,label=vcol)
        if nn: ax.bar([i+w/2 for i in range(nn)],vals2[:nn],color=COLS[1],alpha=0.92,width=w,label=vcol2)
        ax.grid(color="#23324f",alpha=0.4,axis="y")
    elif ctype=="Combo":
        ax.bar(range(n),vals,color=COLS[0],alpha=0.55,width=0.6,label=vcol)
        if vals2:
            mn=min(len(vals2),n)
            ax.plot(range(mn),vals2[:mn],marker="o",linewidth=2.2,color=COLS[1],markerfacecolor="white",markeredgecolor=COLS[1],zorder=3,label=vcol2)
        ax.grid(color="#23324f",alpha=0.35,axis="y")
    elif ctype=="Bubble":
        xr=pd.to_numeric(df[lcol],errors="coerce").replace([np.inf,-np.inf],np.nan).dropna().tolist()
        if vals2: ss=_rescale(vals2)
        else: ss=[300]*n
        if len(xr)==n:
            ax.scatter(xr,vals,s=ss,color=COLS[4],alpha=0.72,edgecolors="white",linewidths=0.7,label=vcol)
        else:
            ax.scatter(range(n),vals,s=ss,color=COLS[4],alpha=0.72,edgecolors="white",linewidths=0.7,label=vcol)
        ax.grid(color="#23324f",alpha=0.35,axis="y")
    elif ctype=="Donut":
        ax.pie(vals,labels=labels[:n],autopct="%1.1f%%",colors=COLS[:n],textprops={"color":TEXT,"fontsize":8},wedgeprops=dict(width=0.42,edgecolor="#0f1626",linewidth=2))
        ax.axis("equal")
    elif ctype=="Semicircle":
        # ===== نصف دائرة (Gauge) محسوبة من نسبة الإنجاز =====
        # نصف دائرة حقيقية: تجويف علوي من 0% (يمين) إلى 100% (يسار)، تُملأ بنسبة الإنجاز
        # فقط، مع إبرة على النسبة الفعلية وخط للهدف، وقوس Y2 كقوس رفيع خارجي.
        from matplotlib.patches import Wedge
        pv=0.0 if pctv is None else min(max(float(pctv),0.0),1.0)
        # 1) مسار النصف الدائرة كاملًا (رمادي غامق) — هذا ما يجعله «نصف دائرة» لا دائرة كاملة
        ax.add_patch(Wedge((0,0),1.0,0.0,180.0,width=0.34,facecolor="#23324f",edgecolor="#0f1626",linewidth=2))
        # 2) التعبئة بنسبة الإنجاز فقط، ملوّنة: أخضر إذا بلغت الهدف، عنبري فاتح إذا لم تبلغه
        _met=(target is not None and target>0 and 100.0*pv>=float(target))
        _fill=("#4ade80" if _met else "#fbbf24")
        if pv>0:
            ax.add_patch(Wedge((0,0),1.0,0.0,180.0*pv,width=0.34,facecolor=_fill,edgecolor="#0f1626",linewidth=2))
        # 3) قوس العمود الثالث Y2 — رفيع وخارجي، يبيّن نسبته من نفس المدى 0..100%
        if vals2 and len(vals2)>0:
            try:
                _a2=[abs(float(z)) for z in vals2]
                _t2=sum(_a2)
                if _t2>0:
                    _p2=min(max(max(_a2)/_t2,0.0),1.0)
                    if _p2>0:
                        ax.add_patch(Wedge((0,0),1.20,0.0,180.0*_p2,width=0.045,facecolor=COLS[1],edgecolor="#0f1626",linewidth=1))
            except Exception: pass
        # 4) خط الهدف: علامة عمودية صغيرة على القوس عند نسبة الهدف المطلوب
        if target is not None and target>0:
            _ta=float(np.deg2rad(180.0*min(max(float(target)/100.0,0.0),1.0)))
            ax.plot([0.94*np.cos(_ta),1.13*np.cos(_ta)],[0.94*np.sin(_ta),1.13*np.sin(_ta)],
                    color="#e6edf7",linewidth=2.2,zorder=6,solid_capstyle="round")
        # 5) الإبرة: من المركز إلى نسبة الإنجاز الفعلية (0% يمين ← 100% يسار)
        _nr=float(np.deg2rad(180.0*(1.0-pv)))
        ax.plot([0.0,0.78*np.cos(_nr)],[0.0,0.78*np.sin(_nr)],color="#e6edf7",linewidth=2.6,zorder=7,solid_capstyle="round")
        ax.plot([0.0],[0.0],marker="o",markersize=6,color="#e6edf7",zorder=7)
        # 6) النصوص: نسبة الإنجاز كبيرة بالمنتصف + الهدف + طرفي المقياس
        ax.text(0,0.20,f"{100.0*pv:.1f}%",ha="center",va="center",color=_fill,fontsize=18,fontweight="bold")
        ax.text(0,-0.14,"نسبة الإنجاز",ha="center",va="center",color="#8aa0c0",fontsize=9)
        if target is not None and target>0:
            ax.text(0,-0.44,f"الهدف {float(target):.0f}%",ha="center",va="center",
                    color=("#4ade80" if _met else "#ef4444"),fontsize=9)
        ax.text(-1.22,-0.10,"0%",ha="center",va="center",color="#8aa0c0",fontsize=8)
        ax.text(1.22,-0.10,"100%",ha="center",va="center",color="#8aa0c0",fontsize=8)
        # 7) مفتاح صغير يشرح اللونين (التعبئة وقوس Y2)
        try:
            from matplotlib.lines import Line2D as _L2s
            _hd=[_L2s([0],[0],marker="s",color=_fill,markersize=8,linestyle="none",label="نسبة الإنجاز المحققة")]
            if vals2 and len(vals2)>0:
                _hd.append(_L2s([0],[0],marker="s",color=COLS[1],markersize=8,linestyle="none",label="قوس Y2 (العمود الثالث)"))
            ax.legend(handles=_hd,facecolor=CARD,edgecolor="#23324f",labelcolor="#aebfe0",
                      fontsize=FS_LEGEND,loc="lower center",framealpha=0.9)
        except Exception: pass
        ax.set_xlim(-1.45,1.45); ax.set_ylim(-0.78,1.22)
        ax.set_axis_off()
    elif ctype=="Treemap":
        _treemap(ax,vals,labels[:n],[COLS[i%len(COLS)] for i in range(n)])
    elif ctype=="Funnel":
        # قمع: ترتيب القيم تنازليًا ووضع الأرقام على أطراف الأشرطة
        kk=sorted(range(len(vals)),key=lambda i:vals[i],reverse=True)
        yy=list(range(len(kk)))
        ax.barh(yy,[vals[i] for i in kk],height=0.62,color=[COLS[i%len(COLS)] for i in kk],alpha=0.93)
        ax.set_yticks(yy); ax.set_yticklabels([labels[i] for i in kk])
        for a,b in zip(yy,[vals[i] for i in kk]):
            ax.text(b+0.01*max(1,max(vals)),a,f"{b:,.0f}",va="center",ha="left",color="#e6edf7",fontsize=8,fontweight="bold")
        ax.invert_yaxis()
    elif ctype=="Waterfall":
        # شلال: كل عمود يبدأ من نهاية السابق (bases) + عمود إجمالي بغير سهم
        bases=[0.0]
        for k in range(1,n):
            bases.append(bases[-1]+vals[k-1])
        for k in range(n):
            ax.bar(k,vals[k],bottom=bases[k],color=("#4ade80" if vals[k]>=0 else "#ef4444"),width=0.55,alpha=0.92)
            ax.plot([k,k],[bases[k],bases[k]+vals[k]],color="#0f1626",lw=0.8)
        ax.bar(n,bases[-1],bottom=0.0,color=COLS[0],width=0.55,alpha=0.95)
        ax.set_xticks(range(n))
        ax.set_xticklabels(labels[:n],rotation=35,ha="right",color="#8aa0c0",fontsize=7)
        ax.grid(color="#23324f",alpha=0.35,axis="y")
        if title:
            title=TLBL.get(ctype,ctype)+f"   (المجموع {bases[-1]:,.0f})"
    elif ctype=="KPI":
        # بطاقة KPI: رقم كبير + المحقق/الهدف + مقارنة بالهدف (فوق/تحت)
        # في وضع «رقم» (pct_mode=="رقم") يعرض الرقم المحقق (done) والهدف بدل النسبة،
        # لأن الهدف رقم وليس نسبة — والموضوع هو عدد المستفيدين.
        fig,ax=plt.subplots(figsize=(FW,FH),facecolor="#0f1626",dpi=110)
        ax.set_facecolor("#0f1626")
        ax.add_patch(plt.Rectangle((0.34,0.40),0.32,0.20,transform=ax.transAxes,facecolor="#1d2c4f",edgecolor="#23324f"))
        _num_mode=(pct_mode=="رقم")
        if _num_mode:
            _d=float(done) if done is not None else 0.0
            big=f"{_d:,.0f}"
            ax.text(0.5,0.5,big,ha="center",va="center",transform=ax.transAxes,fontsize=44,fontweight="bold",color="#e6edf7")
            ax.text(0.5,0.78,"المحقق (عدد المستفيدين)",ha="center",transform=ax.transAxes,fontsize=13,color="#8aa0c0")
            if target is not None and target>0:
                _t=float(target)
                _gp=(_d/_t*100.0)
                ax.text(0.5,0.64,f"الهدف: {_t:,.0f}   |   نسبة الإنجاز: {_gp:.1f}%",
                        ha="center",transform=ax.transAxes,fontsize=13,color="#e6edf7")
                _gap=_d-_t
                ax.text(0.5,0.22,f"{_gap:+,.0f}"+("  فوق الهدف" if _gap>=0 else "  تحت الهدف"),
                        ha="center",transform=ax.transAxes,fontsize=12,color=("#4ade80" if _gap>=0 else "#ef4444"))
        else:
            big=(f"{pctv:,.0f}" if pctv is not None and isinstance(pctv,(int,float)) and not isinstance(pctv,bool) else f"{pctv or 0:,.0f}") + ("%" if pctv is not None and pctv<=1 else "")
            ax.text(0.5,0.5,big,ha="center",va="center",transform=ax.transAxes,fontsize=44,fontweight="bold",color="#e6edf7")
            ax.text(0.5,0.78,"النسبة المحققة: "+f"{pct:.1f}%",ha="center",transform=ax.transAxes,fontsize=14,color="#8aa0c0")
            if target is not None and target>0:
                over=pct-target
                ax.text(0.5,0.22,f"{over:+.1f}%"+("  فوق الهدف" if over>=0 else "  تحت الهدف"),ha="center",transform=ax.transAxes,fontsize=12,color=("#4ade80" if over>=0 else "#ef4444"))
        ax.axis("off")
    else:
        nall=df[lcol].nunique() if hasattr(df[lcol],"nunique") else len(set(labels))
        cnx=pd.to_numeric(df[lcol],errors="coerce")
        xdtv=cnx.notna().mean()>0.9
        return None,None,"نوع الرسم غير معروف"
    if ctype in ("Line","Bar","Area","Scatter","Bubble","StackedBar","Clustered","Combo") and ctype!="Line":
        ax.legend(facecolor=CARD,edgecolor="#23324f",labelcolor="#aebfe0",fontsize=FS_LEGEND)
    if ctype in ("Line","Bar","Area","Scatter","Bubble","StackedBar","Clustered","Combo","Histogram","Box","Treemap","Funnel","Waterfall"):
        nnx=len(labels)
        if nnx<= (nticks or 5): tots=range(nnx)
        else:
            tots=sorted(set(int(round(i*(nnx-1)/((nticks or 5)-1))) for i in range(nticks or 5)))
        ax.set_xticks(list(tots))
        ax.set_xticklabels([labels[i] for i in tots],rotation=35 if nnx>8 else 0,ha="right",color="#8aa0c0",fontsize=FS_TICK)
    if xlabel: ax.set_xlabel(xlabel,color="#8aa0c0",fontsize=FS_LABEL)
    if ylabel: ax.set_ylabel(ylabel,color="#8aa0c0",fontsize=FS_LABEL)
    ax.tick_params(colors="#8aa0c0",labelsize=FS_TICK)
    if title: ax.set_title(title,fontsize=FS_TITLE,fontweight="bold",color="#e6edf7")
    # هوامش موحّدة تمنع اختفاء المحاور والأرقام عند تغيير المقاس
    try: fig.subplots_adjust(top=PAD_TOP,bottom=PAD_BOTTOM,left=PAD_LEFT,right=PAD_RIGHT)
    except Exception:
        try: fig.tight_layout()
        except Exception: pass
    return fig,None,None

def date_like(df,col):
    # عائد: هل العمود يمثل تواريخًا؟ (نموذجيًا >85% من القيم قابلة للتحويل لتواريخ)
    if col is None or col not in df.columns: return False
    s=df[col].dropna()
    if len(s)==0: return False
    if pd.api.types.is_numeric_dtype(s): return False
    try:
        dd=pd.to_datetime(s.astype(str),errors="coerce",dayfirst=True)
        return dd.notna().mean()>0.85
    except Exception: return False

def q5_mask(row,qcols,qvals):
    # ===== فلتر الأسئلة الخمسة: هل هذا الصف يجتاز كل الأسئلة معًا؟ =====
    # يجتاز الصف إذا كانت قيمته في كل سؤال من الخمسة ضمن القيم المقبولة لذلك السؤال.
    # سؤال بلا قيم مختارة = يُتجاهل (لا يقيّد الصف)، حتى لا يصير الفلتر صفريًا بلا سبب.
    for c in qcols:
        allowed=qvals.get(c)
        if allowed is None: continue
        vals=[str(v) for v in allowed]
        if not vals: continue
        if str(row[c]) not in vals: return False
    return True


def column_filters(cur,col,key,saved=None):
    # فلاتر تفاعلية حسب نوع العمود: رقمي (نطاق + شرط) / تاريخي (نطاق أيام) / نصي (قائمة + شرط)
    # الفلاتر تُحفظ في _flt عبر capture_flt ليُعاد عرضها عند العودة للإعداد
    if col is None or cur is None or col not in cur.columns: return cur
    saved=saved or {}
    s=cur[col].dropna()
    if pd.api.types.is_numeric_dtype(s):
        lo,hi=float(s.min()),float(s.max())
        if lo<hi:
            sv=saved.get(key+"_num",(lo,hi))
            try:
                rng=st.slider(f"نطاق {col}",min_value=lo,max_value=hi,value=(float(sv[0]),float(sv[1])),key=key+"_num")
            except Exception:
                rng=st.slider(f"نطاق {col}",min_value=lo,max_value=hi,value=(lo,hi),key=key+"_num")
            out=cur[(cur[col]>=rng[0])&(cur[col]<=rng[1])]
        else: out=cur
        cond=st.selectbox(f"شرط رقمي {col}",["أكبر من","أصغر من","يساوي","أكبر أو يساوي","أصغر أو يساوي","لا يساوي"],index=(None if saved.get(key+"_numop") not in ["أكبر من","أصغر من","يساوي","أكبر أو يساوي","أصغر أو يساوي","لا يساوي"] else ["أكبر من","أصغر من","يساوي","أكبر أو يساوي","أصغر أو يساوي","لا يساوي"].index(saved.get(key+"_numop"))),placeholder="بدون شرط",key=key+"_numop")
        v=st.number_input(f"اكتب قيمة {col}",value=float(saved.get(key+"_numval",0.0)),key=key+"_numval")
        if cond is not None:
            c=pd.to_numeric(out[col],errors="coerce")
            if cond=="أكبر من": out=out[c>v]
            elif cond=="أصغر من": out=out[c<v]
            elif cond=="يساوي": out=out[c==v]
            elif cond=="أكبر أو يساوي": out=out[c>=v]
            elif cond=="أصغر أو يساوي": out=out[c<=v]
            elif cond=="لا يساوي": out=out[c!=v]
        return out
    elif date_like(cur,col):
        d=pd.to_datetime(s,errors="coerce").dropna()
        if len(d)==0: return cur
        d0,d1=d.min().date(),d.max().date()
        if d0<d1:
            sv=saved.get(key+"_date",(d0,d1))
            try:
                rng=st.date_input(f"نطاق {col}",(pd.Timestamp(sv[0]).date(),pd.Timestamp(sv[1]).date()),key=key+"_date")
            except Exception:
                rng=st.date_input(f"نطاق {col}",(d0,d1),key=key+"_date")
            if len(rng)==2: return cur[pd.to_datetime(cur[col],errors="coerce").dt.date.between(rng[0],rng[1])]
        return cur
    else:
        opts=s.dropna().unique().tolist()
        saved_sel=[x for x in (saved.get(key+"_cat") or []) if x in opts]
        sel=st.multiselect(f"اختر {col}",opts,default=saved_sel,key=key+"_cat")
        out=cur[cur[col].isin(sel)] if sel else cur.copy()
        op=st.selectbox(f"شرط نصي {col}",["يحتوي","يساوي","لا يحتوي","يبدأ بـ","ينتهي بـ"],index=(None if saved.get(key+"_op") not in ["يحتوي","يساوي","لا يحتوي","يبدأ بـ","ينتهي بـ"] else ["يحتوي","يساوي","لا يحتوي","يبدأ بـ","ينتهي بـ"].index(saved.get(key+"_op"))),placeholder="بدون شرط",key=key+"_op")
        val=st.text_input(f"اكتب القيمة لـ {col}",value=str(saved.get(key+"_val","")),key=key+"_val")
        if op and val.strip():
            v=str(val).strip().lower();cs=out[col].astype(str).str.lower()
            out=out[cs.str.contains(v,regex=False)] if op=="يحتوي" else out[cs==v] if op=="يساوي" else out[~cs.str.contains(v,regex=False)] if op=="لا يحتوي" else out[cs.str.startswith(v)] if op=="يبدأ بـ" else out[cs.str.endswith(v)]
        return out

def _flt_sfx():
    # لاحقات مفاتيح الفلاتر في session_state (تُستخدم للالتقاط والاستعادة)
    return ("_num","_numop","_numval","_date","_cat","_op","_val")

def capture_flt(it,bkeys):
    # نسخ قيم فلاتر widgets المحددة من الجلسة إلى it["_flt"] للاستعادة لاحقًا
    fl=it.get("_flt") or {}
    for k0 in bkeys:
        for suf in _flt_sfx():
            k=k0+suf
            if k in st.session_state:
                fl[k]=st.session_state[k]
    it["_flt"]=fl

def compute(v):
    # إحصاءات وصفية سريعة (عدد/أصغر/أكبر/مجموع/متوسط/وسيط/انحراف)
    if not v: return None
    return {"العدد":len(v),"الأصغر":min(v),"الأكبر":max(v),"المجموع":sum(v),"المتوسط":sum(v)/len(v),"الوسيط":stt.median(v),"الانحراف":np.std(v)}

def _intersect_rows(df,it):
    # ===== الفلترة الموحّدة للثلاثة أعمدة =====
    # يجمع فلاتر X و Y و Y2 معًا في «الفلتر النهائي»: الصف يبقى فقط إذا اجتاز
    # فلتر X وفلتر Y وفلتر Y2 في نفس الوقت. هذا هو العدد الصح يلي طلبه المستخدم.
    # ملاحظة: إن كان Y2 هو نفسه Y، نتجاهل فلتر Y2 لتفادي تقاطع متعاكس (=صفر).
    if df is None: return None
    out=df
    _same=(it.get("ycol2") is not None and it.get("ycol2")==it.get("ycol"))
    keys=["xrows","yrows"]+( [] if _same else ["y2rows"] )
    for key in keys:
        rows=it.get(key)
        if rows is None: continue
        try: rows=list(rows)
        except Exception: continue
        if len(rows)==0: continue
        out=out[out.index.isin(rows)]
    return out

def _pick_date_col(df,xcol):
    # اختيار عمود التاريخ المستخدَم في قصّ فترة المنحة:
    #   1) عمود X إن كان تاريخيًا وله قيم حقيقية (الأولوية: يتبع فلتر المستخدم).
    #   2) وإلا أول عمود يحمل كلمة «تاريخ» وله قيم حقيقية (مثل «تاريخ الزيارة»).
    # يُرجع اسم العمود أو None. هذا يضمن أن كل مؤشر يفلتر على زمن المنحة تلقائيًا
    # حتى لو كان عمود X نصيًا (نعم/لا) كما في المؤشرات الثانية.
    if df is None: return None
    if xcol and xcol in df.columns:
        try:
            if pd.to_datetime(df[xcol],errors="coerce").notna().any(): return xcol
        except Exception: pass
    for c in df.columns:
        if any(k in str(c) for k in ("تاريخ","date","Date","التاريخ")):
            try:
                if pd.to_datetime(df[c],errors="coerce").notna().any(): return c
            except Exception: pass
    return None

def _period_mask(df,datecol,sd,ed):
    # قناع الصفوف الواقعة ضمن فترة المنحة [sd, ed] على عمود تاريخ.
    # الصفوف بلا تاريخ (NaN) لا تنتمي لأي فترة فتُحذف. يرجع None إن تعذّر القصّ.
    if df is None or not datecol or not sd or not ed: return None
    if datecol not in df.columns: return None
    try:
        d=pd.to_datetime(df[datecol],errors="coerce")
        return d.notna() & (d>=pd.Timestamp(sd)) & (d<pd.Timestamp(ed)+pd.Timedelta(days=1))
    except Exception: return None

def indicator_pct(it,sd,ed):
    # ================= حساب النسبة المحققة للمؤشر =================
    # ===== القاعدة الأساسية التي طلبها المستخدم =====
    #   المقام (الإجمالي) = زمن المنحة + عدد قيم X   ← فلتر X يُطبَّق على المقام
    #   البسط (المحقق)   = الفلتر النهائي = Y ∩ Y2  (أو Y فقط)
    #   النسبة           = البسط ÷ المقام × 100
    # أي: المقام لا يتأثر بفلتر Y أو Y2 إطلاقًا — هو مرجع واحد لكل المؤشر.
    # ملاحظة: لا يوجد فلتر قيم 1..5 في الواجهة؛ القيم المحققة هي التي يختارها
    #         المستخدم في فلتر عمود Y (أو Y2).
    full=it.get("df")
    yc=it.get("ycol")
    if full is None or not yc or yc not in full.columns: return 0,0,0.0
    # 1) زمن المنحة: X إن كان تاريخيًا وإلا أول عمود «تاريخ» (مثل «تاريخ الزيارة»)
    _dcol=_pick_date_col(full,it.get("xcol"))
    _m=_period_mask(full,_dcol,sd,ed)
    period_df=full[_m] if _m is not None else full
    # ===== المقام = «زمن المنحة + عدد قيم X» =====
    # أي بعد تطبيق فلتر X على صفوف الفترة. لو لم يختار المستخدم فلترًا على X
    # يبقى المقام = كل صفوف الفترة. لكن Y و Y2 لا يلمسان المقام أبدًا.
    base=period_df
    _xr=it.get("xrows")
    if _xr is not None:
        try:
            _xl=list(_xr)
            if len(_xl): base=base[base.index.isin(_xl)]
        except Exception: pass
    total=int(len(base))
    if total==0: return 0,0,0.0
    # 2) البسط = تقاطع فلاتر Y و Y2 على نفس الأساس (الصف لازم يحقق الكل)
    #    كل فلتر يُطبَّق فقط إن اختاره المستخدم (أي فهرسته غير فارغة).
    #    حالة خاصة: إذا كان عمود Y2 هو نفسه عمود Y، نتجاهل فلتر Y2 لتفادي تقاطع متعاكس.
    _same_col=(it.get("ycol2") is not None and it.get("ycol2")==yc)
    _keys=["yrows"]+( [] if _same_col else ["y2rows"] )
    # ===== فلتر الأسئلة الخمسة (المؤشر الأول) =====
    # يُطبَّق مع فلاتر Y/Y2 بالتقاطع. مهم: قائمة فارغة تعني «لا صف اجتاز الفلتر»
    # أي done=0، ولا تُعامل كأن الفلتر غير مفعول (وإلا لأعادت النسبة 100% خطأً).
    _q5_active=(bool(it.get("q5on")) and bool(it.get("q5allow")) and (it.get("q5rows") is not None))
    _fin=base
    _has_filter=_q5_active
    for k in _keys:
        rows=it.get(k)
        if rows is None: continue
        try: rows=list(rows)
        except Exception: continue
        if len(rows)==0: continue
        _fin=_fin[_fin.index.isin(rows)]
        _has_filter=True
    if _q5_active:
        _q5r=list(it.get("q5rows") or [])
        _fin=_fin[_fin.index.isin(_q5r)]
    if not _has_filter:
        # لا فلتر معتمد => نعتبر كل الأساس محققة (نسبة 100%)
        return total,total,100.0
    done=int(len(_fin))
    # 3) النسبة = البسط ÷ المقام (المقام = X داخل زمن المنحة)
    pct=(done/total*100.0) if total>0 else 0.0
    return done,total,pct

def _count_done(series,good=None):
    # عدّ الصفوف «المحققة» لعمود واحد بنفس قواعد indicator_pct:
    # رقمي => قيم النجاح (good_vals)؛ نصي => كل إجابة مؤكَّدة غير «لا» وغير فارغة.
    # تُستخدم لحساب نسبة Y2 في مقياس Gauge.
    if series is None: return 0,0
    good=good or [4,5]
    s=pd.to_numeric(series,errors="coerce")
    if int(s.notna().sum())>=max(1,int(0.5*len(series))):
        ok=set()
        for g in good:
            try: ok.add(float(g))
            except Exception: pass
        return int(s.apply(lambda z: (not pd.isna(z)) and (float(z) in ok)).sum()),int(len(series))
    _sv=series.astype("object").where(series.notna(),"")
    _sv=_sv.astype(str).str.strip().str.lower()
    _bad={"","لا","no","n","none","nan","غير معروف","-","0","false","na","n/a"}
    return int((~_sv.isin(_bad)).sum()),int(len(series))

def indicator_y2_pct(it):
    # نسبة Y2 (العمود الثالث) كنسبة مئوية 0..100 لعرضها في مقياس Gauge.
    full=it.get("df"); y2=it.get("ycol2")
    if full is None or not y2 or y2 not in full.columns: return None
    try:
        d,t=_count_done(full[y2],it.get("good_vals") or [4,5])
        return (d/t*100.0) if t>0 else None
    except Exception: return None

def fmt(v,comma=False):
    # تنسيق الأرقام: ملايين (M) وآلاف (K) واختياريًا فواصل الآلاف
    try:
        v=float(v)
        if v>=1000000: return f"{v/1000000:.2f}M"
        if v>=1000: return f"{v/1000:.1f}K"
        return f"{v:,.0f}" if comma else f"{v:.0f}"
    except Exception: return str(v)

def gauge_html(pct,target,uid="g",y2_label=None,y2_pct=None,num_mode=False,base_txt=None):
    # مقياس Gauge (نصف دائرة SVG) يتلوّن حسب تحقيق الهدف.
    # يقبل أيضًا عمود Y2: يُعرض كقوس خارجي رفيع + بطاقة جانبية تبيّن قيمته.
    # ===== num_mode=True: نرسم نسبة الإنجاز (٪) فقط، والهدف رقم هو الأصل 100 =====
    # المتغير الأول = نسبة الإنجاز، والثاني = 100 (للتلوين فقط)، وbase_txt = وصف الأصل.
    t=float(target or 0)
    if num_mode:
        p=min(100.0,max(0.0,float(pct or 0)))
        col="#4ade80" if p>=t else "#fbbf24"
        y2bar=""
        if y2_pct is not None:
            q=min(100,max(0,float(y2_pct)))
            y2bar=(
              f'<path d="M 30 100 A 90 90 0 0 1 170 100" fill="none" stroke="#7c5cff" stroke-width="7" '
              f'stroke-linecap="round" pathLength="100" stroke-dasharray="{q} 100"></path>'
              f'<text x="100" y="116" text-anchor="middle" fill="#aebfe0" font-size="12">{y2_label or "Y2"}: '
              f'<tspan fill="#7c5cff" font-weight="700">{q:.1f}%</tspan></text>')
        return f'''<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:4px">
    <svg viewBox="0 0 200 120" width="100%" style="max-height:220px">
      <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="#1d2c4f" stroke-width="18" stroke-linecap="round"></path>
      <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="{col}" stroke-width="18" stroke-linecap="round" pathLength="100" stroke-dasharray="{p} 100"></path>
      {y2bar}
      <text x="100" y="86" text-anchor="middle" fill="#e6edf7" font-size="30" font-weight="800">{p:.1f}%</text>
    </svg>
    <div style="color:#8aa0c0;font-size:13px">{base_txt or ("الهدف: %d" % t)}</div></div>'''
    p=min(100,max(0,float(pct)))
    col="#4ade80" if p>=t else "#fbbf24"
    y2bar=""
    if y2_pct is not None:
        q=min(100,max(0,float(y2_pct)))
        y2bar=(
          f'<path d="M 30 100 A 90 90 0 0 1 170 100" fill="none" stroke="#7c5cff" stroke-width="7" '
          f'stroke-linecap="round" pathLength="100" stroke-dasharray="{q} 100"></path>'
          f'<div style="color:#aebfe0;font-size:12px;margin-top:2px">{y2_label or "Y2"}: <b style="color:#7c5cff">{q:.1f}%</b></div>')
    return f'''<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:4px">
    <svg viewBox="0 0 200 120" width="100%" style="max-height:220px">
      <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="#1d2c4f" stroke-width="18" stroke-linecap="round"></path>
      <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="{col}" stroke-width="18" stroke-linecap="round" pathLength="100" stroke-dasharray="{p} 100"></path>
      {y2bar}
      <text x="100" y="86" text-anchor="middle" fill="#e6edf7" font-size="30" font-weight="800">{p:.1f}%</text>
    </svg>
    <div style="color:#8aa0c0;font-size:13px">الهدف: {t:.0f}%</div></div>'''

def kpis_html(labels,vals,icons):
    # شريط بطاقات KPI العامة بتنسيق HTML/CSS
    h=['<div class="kpis">']
    for l,v,ic in zip(labels,vals,icons):
        h.append(f'<div class="kpi"><div class="kico">{ic}</div><div class="klab">{l}</div><div class="knum">{v}</div></div>')
    h.append('</div>')
    return "".join(h)

# =============================================================================
# ===== الصفحة الرئيسية الموحّدة: Grant + Health Services Dashboard + CRM =====
# كل شي صار بصفحة واحدة (بنفس ترتيب وتنسيق لوحة خدمات الصحة)، وأزرار التنقّل
# انشالت من السايدبار. الأزرار الحسّاسة (New Grant / Edit / حذف) للأدمن فقط.
# =============================================================================
def _crm_ensure():
    """يحمّل أول جدول CRM مرة واحدة بالجلسة إذا ما في جدول محمّل."""
    if st.session_state.get("crm_df") is None:
        _n=_crm_names()
        if _n:
            _d=_crm_load(_n[0])
            if _d is not None:
                st.session_state["crm_df"]=_d
                st.session_state["crm_name_cur"]=_n[0]
                st.session_state["crm_pick_loaded"]=_n[0]
    return st.session_state.get("crm_df")

@st.cache_data(show_spinner=False)
def _saves_meta(key):
    """ميتاداتا المنح المحفوظة (بدون تحميل البيكل الضخم كل مرة) — الكاش يتبدّل بتغيّر الملفات."""
    out=[]
    for p,d in list_saves():
        g=d.get("grant") or {}
        ind=d.get("indicators") or []
        tot=don=0
        try:
            for x in ind:
                _d=x.get("df"); _p=x.get("pdf")
                if _p is None: _p=x.get("fdf")
                if _d is not None: tot+=len(_d)
                if _p is not None: don+=len(_p)
        except Exception:
            tot=0; don=0
        pct=(don/tot*100.0) if tot else None
        try: mb=os.path.getsize(p)/1048576.0
        except Exception: mb=0.0
        out.append({"path":p,"name":(g.get("name") or os.path.splitext(os.path.basename(p))[0]),
                    "saved":str(d.get("saved_at",""))[:16],"services":g.get("services",0),
                    "beneficiaries":g.get("beneficiaries",0),"n_ind":len(ind),
                    "pct":pct,"mb":mb})
    return out

def _saves_key():
    _k=[]
    for p in glob.glob(os.path.join(SAVES_DIR,"*.pkl")):
        if os.path.basename(p).startswith("_"): continue
        try: _k.append((os.path.basename(p),round(os.path.getmtime(p),3)))
        except Exception: pass
    return tuple(sorted(_k))

def render_grant_cards():
    """كروت المنح المحفوظة بنفس شكل كروت لوحة خدمات الصحة (٤ أعمدة)."""
    _metas=_saves_meta(_saves_key())
    if not _metas:
        st.markdown(f'<div class="hintbox">📁 {_L("ما في منح محفوظة بعد — اضغط New Grant لإنشاء أول منحة.","No saved grants yet — press New Grant to create your first one.")}</div>',
                    unsafe_allow_html=True)
        return
    for _i in range(0,len(_metas),4):
        _row=_metas[_i:_i+4]
        _cols=st.columns(4,gap="small")
        for _j,_m in enumerate(_row):
            _bn=safe_name(os.path.basename(_m["path"]))
            with _cols[_j]:
                with st.container(border=True):
                    _pct="—" if _m["pct"] is None else f'{_m["pct"]:.1f}%'
                    _pv=_m["pct"] or 0.0
                    st.markdown(f'''<div class="hhs-meta"><span class="hm-ic">📊</span>
<span class="hhs-badge custom">{T("ach_ratio")} {_pct}</span>
<span class="hhs-dot has"><i></i>{_m["n_ind"]} {T("n_ind")}</span></div>
<div class="wtitle" style="margin-bottom:2px">{_m["name"]}</div>
<div class="wdate">📅 {_m["saved"]} · {_m["mb"]:.1f} MB</div>
<div class="wrows" style="margin-top:6px">{_L("الخدمات","Services")}: <b>{fmt(_m["services"],True)}</b>
 · {_L("المستفيدون","Beneficiaries")}: <b>{fmt(_m["beneficiaries"],True)}</b></div>
<div class="wbar"><div style="width:{min(100,_pv):.1f}%"></div></div>''',unsafe_allow_html=True)
                    if st.button("📂 "+_L("فتح","Open"),key="gopen_"+_bn,
                                 use_container_width=True,type="primary"):
                        try:
                            _d=load_save(_m["path"])
                        except Exception:
                            _d=None
                        if _d:
                            ss["grant"]=_d.get("grant") or {}
                            ss["indicators"]=_d.get("indicators") or []
                            ss["phase"]="dashboard"; ss["view"]="dashboard"
                            ss["_draft"]={}
                        st.rerun()
                    if is_admin():
                        if st.button("🗑 "+_L("حذف","Delete"),key="gdel_"+_bn,
                                     use_container_width=True):
                            try: os.remove(_m["path"])
                            except Exception: pass
                            _saves_meta.clear(); st.rerun()

# ===== CRM: كروت الجداول المحفوظة (نفس فكرة كروت المنح) =====
def _crm_meta_all(key=None):
    """ميتاداتا جداول CRM (اسم/صفوف/أعمدة/آخر تحديث) — الكاش بيتبدّل بتغيّر الملفات."""
    out=[]
    for _n in _crm_names():
        _p=_crm_path(_n); _rows=0; _cols=0; _mt=""
        try:
            _d=pd.read_csv(_p,dtype=str,encoding="utf-8-sig"); _rows=len(_d); _cols=len(_d.columns)
        except Exception:
            pass
        try: _mt=datetime.datetime.fromtimestamp(os.path.getmtime(_p)).strftime("%Y-%m-%d %H:%M")
        except Exception: pass
        out.append({"name":_n,"rows":_rows,"cols":_cols,"mt":_mt})
    return out

def _crm_key():
    _k=[]
    for _n in _crm_names():
        _p=_crm_path(_n)
        try: _k.append((os.path.basename(_p),round(os.path.getmtime(_p),3)))
        except Exception: pass
    return tuple(sorted(_k))

def _crm_open_table(n,dash=True):
    """يفتح جدول CRM: داشبورد فقط (dash=True) أو شاشة التعديل (dash=False)."""
    _d=_crm_load(n)
    ss["crm_df"]=_d; ss["crm_name_cur"]=n; ss["crm_pick_loaded"]=n
    ss.pop("crm_seg",None); ss.pop("crm_rad",None)
    if dash: ss["crm_open"]="dash"
    ss["view"]="crm"; st.rerun()

def render_crm_cards():
    """كروت جداول CRM بنفس شكل كروت المنح — الداشبورد ما بيظهر إلا بعد الضغط."""
    _metas=_crm_meta_all(_crm_key())
    if not _metas:
        st.markdown(f'<div class="hintbox">🤝 {_L("ما في جدول CRM محفوظ بعد.","No saved CRM table yet.")}</div>',
                    unsafe_allow_html=True)
        return
    for _i in range(0,len(_metas),4):
        _row=_metas[_i:_i+4]
        _cols=st.columns(4,gap="small")
        for _j,_m in enumerate(_row):
            _bn=safe_name(_m["name"])
            with _cols[_j]:
                with st.container(border=True):
                    st.markdown(f'''<div class="hhs-meta"><span class="hm-ic">🤝</span>
<span class="hhs-badge custom">{_L("صفوف","Rows")} {fmt(_m["rows"],True)}</span>
<span class="hhs-dot has"><i></i>{_m["cols"]} {_L("عمود","Columns")}</span></div>
<div class="wtitle" style="margin-bottom:2px">{_m["name"]}</div>
<div class="wdate">📅 {_m["mt"]}</div>''',unsafe_allow_html=True)
                    if st.button("📊 "+_L("فتح الداشبورد","Open dashboard"),key="crmdash_"+_bn,
                                 use_container_width=True,type="primary"):
                        _crm_open_table(_m["name"],True)
                    if is_admin():
                        if st.button("✏️ "+_L("تعديل الداتا","Edit data"),key="crmedit_"+_bn,
                                     use_container_width=True):
                            _crm_open_table(_m["name"],False)

def render_home(fdata,alldata):
    """الصفحة الرئيسية: Main Dashboard ← Grant + Health Services Dashboard + CRM."""
    # ===== العنوان الرئيسي (تحت شعار سامز) =====
    st.markdown('<div class="pagehead"><div><div class="ph-t">Main Dashboard</div>'
                f'<div class="ph-s">{_L("لوحة المتابعة الرئيسية","Grants · Health Services · CRM overview")}</div></div>'
                '<div class="ph-b">SAMS · Grant · Health Services · CRM</div></div>',
                unsafe_allow_html=True)
    # ===== ① عنوان Grant + زر New Grant بنهاية نفس السطر =====
    _h1,_h2=st.columns([6,1.45],vertical_alignment="center")
    with _h1:
        st.markdown(f'<div class="sectband" style="margin:22px 0 8px">📁 {_L("المنح","Grant")}'
                    f'<span class="sb-sub">{_L("المنح المحفوظة","Saved Grants")}</span></div>',
                    unsafe_allow_html=True)
    with _h2:
        st.markdown('<div style="height:12px"></div>',unsafe_allow_html=True)
        if is_admin():
            if st.button("➕ New Grant",key="home_newgrant",use_container_width=True,type="primary"):
                clear_auto()
                ss["grant"]={}; ss["indicators"]=[]; ss["_draft"]={}
                ss["phase"]="setup"; ss["view"]="form"; ss["gname"]=""
                st.rerun()
        else:
            st.caption(_L("عرض فقط","View only"))
    render_grant_cards()
    # ===== ② Health Services Dashboard + تفاصيله =====
    render_health_services(fdata,alldata,embedded=True)
    # ===== ③ متابعة المشاريع (MEAL): الإنجاز الشهري + التقارير + الصلاحيات =====
    st.markdown(f'<div class="sectband">📊 {_L("متابعة المشاريع (MEAL)","Projects Follow-up (MEAL)")}'
                f'<span class="sb-sub">{_L("الإنجاز الشهري · التقارير · الصلاحيات","Monthly actuals · Reports · Permissions")}</span></div>',
                unsafe_allow_html=True)
    meal.render_meal_section(fdata,alldata,lang=ss.get("lang","ar"),admin=is_admin())
    # ===== ④ CRM: عنوان + كروت (الداشبورد ما بيظهر هون — بينفتح بالضغط على الكرت) =====
    st.markdown(f'<div class="sectband">🤝 CRM<span class="sb-sub">{_L("الشكاوى","Complaints")}</span></div>',
                unsafe_allow_html=True)
    render_crm_cards()

# =============================================================================
# ===== تسجيل الدخول والصلاحيات (Viewer / Admin) =====
# - حساب الأدمن ثابت: SAMSAD / lifesave — كل الصلاحيات (تعديل الداتا والواجهات).
# - أي مستخدم عادي: يسجّل إيميله وكلمة مروره مرة واحدة، بينحفظوا في users.json،
#   وبعدها بيفوت بنفس الإيميل. صلاحيته: يشوف الواجهات ويفلتر بس ما يعدّل أي داتا.
# =============================================================================
USERS_FILE=meal.USERS_FILE   # .sams_private/users.json — مستثنى من Git
ADMIN_USER="SAMSAD"
ADMIN_PASS="lifesave"

def _pw_hash(pw,salt=""):
    """تشفير كلمة المرور (SHA-256 + salt) — ما بنخزّن كلمة المرور نصّ صريح."""
    return hashlib.sha256((str(salt)+str(pw)).encode("utf-8")).hexdigest()

def _users_load():
    # كل الحسابات بملف خاص خارج Git (مع ترحيل users.json القديم تلقائياً)
    return meal.load_users()

def _users_save(d):
    return meal.save_users(d)

def current_user():
    return st.session_state.get("auth") or {}

def is_admin():
    return (st.session_state.get("auth") or {}).get("role")=="admin"

def _login_page():
    """شاشة الدخول/التسجيل — أول شي بيشوفه المستخدم قبل أي داتا."""
    st.markdown('''<style>
    .authwrap{display:flex;justify-content:center;margin-top:6px}
    .authcard{background:linear-gradient(180deg,#182341,#141e36);border:1px solid #23324f;
      border-radius:20px;padding:18px 20px 14px;box-shadow:0 12px 40px rgba(0,0,0,.45)}
    .authtitle{font-size:21px;font-weight:900;color:#00d4ff;text-align:center;margin-bottom:8px}
    .authnote{color:#8aa0c0;font-size:12px;text-align:center;margin-top:10px;line-height:1.6}
    </style>''',unsafe_allow_html=True)
    _org_header()
    _c0,_c1,_c2=st.columns([1,1.25,1])
    with _c1:
        _lng=ss.get("lang","en")
        _ll,_lr=st.columns(2)
        with _lr:
            if st.button(("🌐 English" if _lng=="ar" else "🌐 العربية"),key="lg_lang",
                         use_container_width=True):
                ss["lang"]="en" if _lng=="ar" else "ar"; st.rerun()
        st.markdown('<div class="authwrap"><div style="width:100%">',unsafe_allow_html=True)
        st.markdown(f'<div class="authtitle">🔐 {_L("تسجيل الدخول","Sign in")}</div>',unsafe_allow_html=True)
        _tab_in,_tab_up=st.tabs([_L("دخول","Login"),
                                 _L("حساب جديد","Create account")])
        with _tab_in:
            with st.form("sams_login",clear_on_submit=False):
                _em=st.text_input(_L("الإيميل أو اسم المستخدم","Email or username"),key="lg_email")
                _pw=st.text_input(_L("كلمة المرور","Password"),type="password",key="lg_pw")
                _go=st.form_submit_button(_L("دخول","Sign in"),use_container_width=True,type="primary")
            if _go:
                _em=(_em or "").strip()
                if not _em or not _pw:
                    st.error(_L("رجاءً أدخل الإيميل وكلمة المرور.","Please enter your email and password."))
                elif _em.lower()==ADMIN_USER.lower() and _pw==ADMIN_PASS:
                    ss["auth"]={"email":ADMIN_USER,"name":ADMIN_USER,"role":"admin"}
                    ss["view"]="home"; st.rerun()
                else:
                    _u=_users_load().get(_em.lower())
                    if _u and _u.get("pw")==_pw_hash(_pw,_u.get("salt","")):
                        ss["auth"]={"email":_em.lower(),
                                    "name":_u.get("name") or _em,
                                    "role":(_u.get("role") or "viewer")}
                        ss["view"]="home"; st.rerun()
                    else:
                        st.error(_L("الإيميل أو كلمة المرور غير صحيحة.","Wrong email or password."))
        with _tab_up:
            with st.form("sams_register",clear_on_submit=False):
                _rn=st.text_input(_L("الاسم (اختياري)","Name (optional)"),key="rg_name")
                _re=st.text_input(_L("الإيميل","Email"),key="rg_email")
                _rp=st.text_input(_L("كلمة المرور","Password"),type="password",key="rg_pw")
                _rp2=st.text_input(_L("تأكيد كلمة المرور","Confirm password"),type="password",key="rg_pw2")
                _rg=st.form_submit_button(_L("إنشاء الحساب","Create account"),use_container_width=True)
            if _rg:
                _re=(_re or "").strip().lower()
                if "@" not in _re or "." not in _re.split("@")[-1]:
                    st.error(_L("أدخل إيميل صحيح.","Enter a valid email."))
                elif len(_rp or "")<4:
                    st.error(_L("كلمة المرور لازم ٤ أحرف على الأقل.","Password must be at least 4 characters."))
                elif _rp!=_rp2:
                    st.error(_L("كلمتا المرور غير متطابقتين.","Passwords do not match."))
                elif _re==ADMIN_USER.lower():
                    st.error(_L("هذا الاسم محجوز لحساب الأدمن.","This username is reserved for the admin."))
                else:
                    _d=_users_load()
                    if _re in _d:
                        st.error(_L("هذا الإيميل مسجّل مسبقًا — سجّل دخول.","This email already exists — please sign in."))
                    else:
                        _salt=os.urandom(8).hex()
                        _d[_re]={"name":(_rn or "").strip() or _re.split("@")[0],
                                 "pw":_pw_hash(_rp,_salt),"salt":_salt,
                                 "role":"viewer","created":datetime.datetime.now().isoformat(timespec="seconds")}
                        if _users_save(_d):
                            ss["auth"]={"email":_re,"name":_d[_re]["name"],"role":"viewer"}
                            ss["view"]="home"; st.rerun()
                        else:
                            st.error(_L("تعذّر حفظ الحساب — تأكّد من صلاحيات المجلد.","Could not save the account."))
        st.markdown('</div></div>',unsafe_allow_html=True)
        st.markdown(f'<div class="authnote">{_L("الحساب العادي بيشوف الواجهات ويعمل فلترة بس ما بيعدّل الداتا.","Regular accounts can view and filter data but cannot edit it.")}<br>'
                    f'{_L("🔒 البيانات تُخزَّن محلياً داخل .sams_private ولا تُرفع على GitHub.","🔒 Data is stored locally in .sams_private and is never pushed to GitHub.")}</div>',
                    unsafe_allow_html=True)

# ===== تهيئة الجلسة =====
# مهم: maybe_resume يُستدعى قبل setdefault الافتراضية حتى يعمل فحص «grant ليس None»
# (الجلسة الجديدة لا تملك grant أصلاً، فأي مسودة/dashboard محفوظ يُستأنف من _auto.pkl)
ss=st.session_state
ss.setdefault("lang","en")

# شاشة الافتتاح: مرة واحدة لكل جلسة (قبل الدخول)
if not ss.get("splash_shown"):
    ss["splash_shown"]=True
    components.html('''<div id="spl"><h1>SAMS</h1><div class="splabel">لوحة متابعة المشاريع الإنسانية</div><div class="spn"></div></div>''',height=0)

# ===== بوابة الدخول: بدون تسجيل دخول ما بنعرض ولا بنحمّل أي داتا =====
if not ss.get("auth"):
    _auto_tr_flush()
    _login_page()
    st.stop()

maybe_resume()
ss.setdefault("phase","setup")
ss.setdefault("view","home")
ss.setdefault("grant",{})
ss.setdefault("indicators",[])
ss.setdefault("splash_shown",False)
ss.setdefault("_draft",{})

# ===== الشريط الجانبي =====
# بعد نقل كل الأزرار للصفحة الرئيسية، صار السايدبار فيه بس:
# تبديل اللغة + بيانات الحساب والخروج + مصدر الداتا والفلاتر (الفلترة مسموحة للجميع).
with st.sidebar:
    _auto_tr_flush()
    _lang_now=ss.get("lang","en")
    st.markdown('<div class="sect" style="margin-top:0">🌐 Language</div>',unsafe_allow_html=True)
    if st.button(T("btn_lang"),key="lang_toggle",use_container_width=True,type="primary"):
        ss["lang"]="en" if _lang_now=="ar" else "ar"
        st.rerun()
    st.caption("English" if _lang_now=="ar" else "العربية")
    # ===== بيانات الحساب + الخروج =====
    _u=current_user()
    _role_lbl=_L("أدمن — كل الصلاحيات","Admin — full access") if is_admin() else _L("مشاهد — عرض وفلترة","Viewer — view & filter")
    _role_cls="custom" if is_admin() else "generic"
    st.markdown(f'''<div class="accbox">
      <div class="acc-ic">{'🛡️' if is_admin() else '👤'}</div>
      <div class="acc-meta"><div class="acc-name">{_u.get('name') or _u.get('email') or ''}</div>
      <div class="acc-mail">{_u.get('email') or ''}</div>
      <span class="hhs-badge {_role_cls}">{_role_lbl}</span></div></div>''',unsafe_allow_html=True)
    if st.button("🚪 "+_L("تسجيل الخروج","Sign out"),key="logout_btn",
                 use_container_width=True):
        ss.pop("auth",None)
        for _k in ("crm_df","crm_name_cur","crm_pick_loaded","crm_seg","_crm_loaded"):
            ss.pop(_k,None)
        st.rerun()
    st.markdown("<br>",unsafe_allow_html=True)
    # ===== مصدر الداتا + الفلاتر: بالصفحة الرئيسية والأقسام والداشبورد =====
    if ss.get("view") in ("home","hhs","dash"):
        _src,_srcname,_srckind=render_data_source()
        _fdata,_alldata=render_global_filters(_src)
        ss["_fdata"]=_fdata; ss["_alldata"]=_alldata; ss["_srcname"]=_srcname

# ===== ترويسة المنظمة: أعلى كل صفحة (جدار المنح، الأقسام، الداشبورد، المنحة، الإعداد) =====
_org_header()

# ===== حماية الصلاحيات: شاشات إنشاء/إعداد المنحة للأدمن فقط =====
if not is_admin() and ss.get("view") in ("form","setup"):
    ss["view"]="home"; st.rerun()
# أي جلسة قديمة على «wall» تنتقل للصفحة الرئيسية الجديدة
if ss.get("view")=="wall":
    ss["view"]="home"; st.rerun()

# ===== الصفحة الرئيسية الموحّدة (Grant + Health Services + CRM) =====
if ss.get("view")=="home":
    if _fdata is None or _alldata is None:
        st.error(T("src_bad")); st.stop()
    render_home(_fdata,_alldata)

# ===== واجهة الأقسام (23 زر) =====
if ss.get("view")=="hhs":
    if _fdata is None or _alldata is None:
        st.error(T("src_bad")); st.stop()
    render_health_services(_fdata,_alldata)

# ===== واجهة الداشبورد: داشبورد واحد لحاله لكل زر =====
if ss.get("view")=="dash":
    if _fdata is None or _alldata is None:
        st.error(T("src_bad")); st.stop()
    render_dash_page(_fdata,_alldata)

# ===== واجهة CRM: قاعدة بيانات مستقلة (اختيار/تعديل/حفظ) =====
if ss.get("view")=="crm":
    render_crm()

# ===== جدار المنح (الشاشة الرئيسية) =====
# بطاقة استئناف آخر عمل + زر منحة جديدة + بطاقات كل المنح المحفوظة
if ss.get("view")=="wall":
    if os.path.exists(AUTO):
        try:
            _ad=pickle.load(open(AUTO,"rb"))
        except Exception:
            _ad=None
        _dr=ss.get("_draft") or {}
        _nm=_dr.get("name") or ((_ad.get("grant") or {}).get("name") if _ad else "") or "آخر عمل"
        # نسبة إنجاز آخر عمل: السجلات المحققة (pdf) ÷ الكلية (df) — معالجة None بدون حوّل منطقي
        _tot=0; _don=0
        if _ad:
            try:
                for _x in (_ad.get("indicators") or []):
                    _dx=_x.get("df"); _px=_x.get("pdf")
                    if _px is None: _px=_x.get("fdf")
                    if _dx is not None: _tot+=len(_dx)
                    if _px is not None: _don+=len(_px)
            except Exception:
                _tot=0; _don=0
        _pnum=(_don/_tot*100) if _tot else 0.0
        _pc=f"{_pnum:.1f}%" if _tot else "—"
        _pccls="up" if _pnum>=50 else "down"
        st.markdown(f'''<div class="wallcard" style="border:1.5px solid #00d4ff"><div class="whead"><span class="wtitle">▶️ {T("last_work")} ({T("status_done") if (_ad or {}).get('phase')=='dashboard' else T("status_draft")})</span><span class="wdate">{str((_ad or {}).get('saved_at',''))[:19]}</span></div>
        <div class="wrows">{T("value_lbl")}: {_nm} ‏— {T("n_ind")}: <b>{len((_ad or {}).get('indicators') or [])}</b></div>
        <div class="wbar"><div style="width:{min(100,_pnum):.1f}%"></div></div>
        <div class="wfoot" style="color:#00d4ff">{T("ach_ratio")}: <b class="{_pccls}">{_pc}</b> — {T("can_continue")}</div></div>''',unsafe_allow_html=True)
        c1,c2=st.columns(2)
        # بطاقة آخر عمل مفتوح (مكتمل أو مسودة) تظهر دائمًا عند وجود ملف الحفظ التلقائي
        if c1.button(T("btn_resume"),key="resume_auto",use_container_width=True):
            if _ad:
                ss["indicators"]=_ad.get("indicators") or []
                ss["grant"]=_ad.get("grant")
                ss["_draft"]=_ad.get("draft") or {}
                ss["phase"]=_ad.get("phase") or ("dashboard" if _ad.get("grant") else "setup")
                ss["view"]=ss["phase"]
            st.rerun()
        # مسح ملف الحفظ التلقائي وتجاهل آخر عمل
        if c2.button(T("btn_clear"),key="clear_auto_btn",use_container_width=True):
            ss["indicators"]=[]; ss["grant"]=None; ss["_draft"]={}; clear_auto()
            st.rerun()
    st.markdown("<br>",unsafe_allow_html=True)
    # ملاحظة: زرّا «منحة جديدة» و«لوحة خدمات الصحة» نُقلا إلى الشريط الجانبي
    # (اللوحة المنسدلة يلي فيها زر تغيير اللغة) — لذلك ما هنّي ظاهرين هون.
    st.markdown('<div class="sect">%s</div>'%T("saved_grants"),unsafe_allow_html=True)
    # عرض بطاقات المنح المحفوظة مع شريط تقدم النسبة المحققة وزرّي فتح/حذف
    for p,d in list_saves():
        g=d.get("grant") or {}
        ind=d.get("indicators") or []
        saved=d.get("saved_at","")[:16]
        a=g.get("name","unsaved")
        # مفتاح فريد لكل بطاقة: اسم المنحة + اسم الملف. الاسم وحده غير كافٍ لأن
        # منحين بنفس الاسم يولّدان نفس الـ key وStreamlit يرمي DuplicateElementKey.
        uk="open_"+safe_name(a)+"_"+safe_name(os.path.splitext(os.path.basename(p))[0])
        pctcell="—"
        try:
            tot=0; don=0
            for x in ind:
                _d=x.get("df"); _p=x.get("pdf")
                if _p is None: _p=x.get("fdf")
                if _d is not None: tot+=len(_d)
                if _p is not None: don+=len(_p)
            pctcell=f"{don/tot*100:.1f}" if tot else "—"
        except Exception:
            pctcell="—"
        try:
            pctf=float(pctcell)
        except Exception:
            pctf=0.0
        wcls="up" if pctf>=50 else "down"
        mb=os.path.getsize(p)/1048576
        st.markdown(f'''<div class="wallcard">
          <div class="whead"><span class="wtitle">📊 {a}</span><span class="wdate">📅 {saved}</span></div>
          <div class="wrows">الخدمات المضافة: <b>{fmt(g.get('services',0))}</b>‏ — عدد المستفيدين: <b>{fmt(g.get('beneficiaries',0))}</b> — عدد المؤشرات: <b>{len(ind)}</b></div>
          <div class="wbar"><div style="width:{min(100,pctf):.1f}%"></div></div>
          <div class="wfoot">نسبة الإنجاز <b class="{wcls}">{pctf:.1f}%</b> ‏— {mb:.1f} م.ب</div>
        </div>
        ''',unsafe_allow_html=True)
        b1,b2=st.columns(2)
        if b1.button("💾 فتح المحفظة",key=uk,use_container_width=True):
            ss["grant"]=g; ss["indicators"]=ind; ss["phase"]="dashboard"; ss["view"]="dashboard"; ss["_draft"]={}
            st.rerun()
        if b2.button("🗑 حذف",key="del_"+uk,use_container_width=True):
            try: os.remove(p)
            except Exception: pass
            st.rerun()

# ===== شاشة الإعداد: بيانات المنحة الأساسية (الاسم/الخدمات/المستفيدين/المدة) =====
# ملاحظة: حقول المنحة تخصّ «إنشاء منحة» فقط، لذلك ما بتظهر مع أي صفحة أخرى.
# بدون الاستثناء كان الحقل بيطلع مع «🏥 لوحة خدمات الصحة» لأن phase الافتراضي setup.
if ss.get("phase")=="setup" and ss.get("view") in ("form","setup"):
    gr=ss.get("grant") or {}
    dr=ss.get("_draft") or {}
    st.markdown('<div class="sect">إنشاء منحة — البيانات الأساسية</div>',unsafe_allow_html=True)
    # الأولوية لتعيين «المدة الافتراضية»: منحة محفوظة ← مسودة محفوظة ← بداية السنة الحالية
    if gr.get("start") and gr.get("end"):
        d0=gr["start"].date() if hasattr(gr["start"],"date") else gr["start"]
        d1=gr["end"].date() if hasattr(gr["end"],"date") else gr["end"]
        if d0>d1: d1,d0=d0,d1
        d0=max(d0,datetime.date(2000,1,1))
        d1=max(d0,d1)
    elif isinstance(dr.get("gtime"),(tuple,list)) and len(dr.get("gtime"))==2:
        d0=pd.Timestamp(dr["gtime"][0]).date()
        d1=pd.Timestamp(dr["gtime"][1]).date()
        if d0>d1: d1,d0=d0,d1
        d0=max(d0,datetime.date(2000,1,1))
        d1=max(d0,d1)
    else:
        d0=datetime.date(datetime.datetime.now().year,1,1)
        d1=datetime.date.today()
    gname=st.text_input("اسم المنحة",value=str(dr.get("name") or gr.get("name") or ""),key="gname")
    cg1,cg2=st.columns(2)
    gserv=cg1.number_input("عدد الخدمات المضافة",min_value=0,value=int(dr.get("services") or gr.get("services") or 0),step=1,key="gserv")
    gben=cg2.number_input("عدد المستفيدين المستفيدين",min_value=0,value=int(dr.get("beneficiaries") or gr.get("beneficiaries") or 0),step=1,key="gben")
    st.markdown('<div class="sect">مدة المنحة (من تاريخ إلى تاريخ)</div>',unsafe_allow_html=True)
    # Widget مدة المنحة — عند العودة للإعداد تُحفظ القيمة المعتمدة سابقًا ولا يُعاد الافتراضي
    gtime=st.date_input("مدة المنحة (من تاريخ إلى تاريخ)",(d0,d1),key="gtime")
    # تحويل المدة المدخلة إلى تواريخ قص (start_dt/end_dt) + سطر الخط الزمني التوضيحي
    start_dt=None; end_dt=None; tl=""
    if isinstance(gtime,(tuple,list)) and len(gtime)==2 and gtime[0] and gtime[1]:
        d_from,d_to=gtime
        if d_from>d_to: d_to,d_from=d_from,d_to
        start_dt=datetime.datetime(d_from.year,d_from.month,d_from.day)
        end_dt=datetime.datetime(d_to.year,d_to.month,d_to.day)
        tl="من تاريخ إلى تاريخ"
        timeline=f"{d_from.strftime('%Y-%m-%d')} إلى {d_to.strftime('%Y-%m-%d')}"
        st.caption(f"**الخط الزمني:** {timeline}")
    else:
        timeline="لم تختار"
        st.caption("سيتم عرض اللوحة بدون تحديد زمني")
    st.markdown("**حقوق المنحة:** ")
    # حفظ تلقائي بعد كل تعديل في حقول الإعداد (تُحفظ كمسودة لحين الإتمام)
    autosave()

# ===== إعداد المؤشرات: لكل مؤشر ← رفع ملف + اختيار أعمدة + فلاتر + أنواع رسوم =====
if ss.get("view")=="form" or ss.get("view")=="setup":
    st.markdown('<div class="sect">إعداد المؤشرات</div>',unsafe_allow_html=True)
    # إعادة قراءة المدة الحية (widget gtime) لتطبيقها داخل حلقة المؤشرات على بيانات كل ملف
    start_dt=None; end_dt=None
    try:
        _gt=st.session_state.get("gtime")
        if isinstance(_gt,(tuple,list)) and len(_gt)==2:
            start_dt=pd.Timestamp(_gt[0]).date(); end_dt=pd.Timestamp(_gt[1]).date()
    except Exception: pass
    # ===== حلقة كل مؤشر: رفع ملفه وتحديد أعمدة X/Y/Y2 ثم الفلاتر ثم الطرق =====
    for i,it in enumerate(ss["indicators"]):
        st.markdown(f'<div class="ibox"><div class="ibox-head"><span class="ibox-title">📊 المؤشر {i+1}</span></div>',unsafe_allow_html=True)
        it["name"]=st.text_input(f"اسم المؤشر {i+1}",value=str(it.get("name") or ""),key="Iname_"+str(i))
        has_df=it.get("df") is not None
        if has_df:
            st.caption(f"✅ الفايل محمّل مسبقًا: **{it.get('file_name','المعطيات')}** | {len(it['df'])} سجل")
            want_chg=st.checkbox(f"اختياري: تغيير الفايل — مؤشر {i+1}",key="chfile_"+str(i))
        else:
            want_chg=False
        if (not has_df) or want_chg:
            f=st.file_uploader(f"فايل مؤشر {i+1}",type=["xlsx","xls","csv"],key="Ifile_"+str(i))
        else:
            f=None
        # قراءة ملف جديد (Excel/CSV) واستخراج الأعمدة الرقمية والنصية تلقائيًا
        if f is not None and it.get("file_name")!=f.name:
            try:
                d=pd.read_excel(io.BytesIO(f.read())) if f.name.endswith((".xlsx",".xls")) else pd.read_csv(io.BytesIO(f.read()))
                it["df"]=d; it["file_name"]=f.name
                it["numc"]=[c for c in d.columns if pd.api.types.is_numeric_dtype(d[c])]
                it["txtc"]=[c for c in d.columns if c not in it["numc"]]
                it["allc"]=it["txtc"]+it["numc"]
                it["xcol"]=it["allc"][0] if it["allc"] else ""
                it["ycol"]=it["numc"][0] if it["numc"] else (it["allc"][0] if it["allc"] else None)
            except Exception as e: st.error("خطأ في قراءة الفايل: "+str(e))
        if it.get("df") is not None:
            c1,c2=st.columns(2)
            # اختيار عمود التسميات X وعمود القيم Y (وعمود ثانٍ Y2 اختياري للمقارنة)
            it["xcol"]=c1.selectbox("عمود التسميات (X) — كل الأعمدة",it["allc"],index=it["allc"].index(it["xcol"]) if it["xcol"] in it["allc"] else 0,key="ix_"+str(i))
            it["ycol"]=c2.selectbox("عمود القيم (Y) — كل الأعمدة",it["allc"],index=it["allc"].index(it["ycol"]) if it["ycol"] and it["ycol"] in it["allc"] else 0,key="iy_"+str(i))
            y2opts=["—"]+list(it["allc"])
            cur2=it.get("ycol2")
            if cur2 not in y2opts: cur2="—"
            it["ycol2"]=st.selectbox("عمود ثانٍ (Y2) — للرسم المشترك (متراكمة/مجمّعة/كومبو/فقاعي) — «—» بدون مقارنة وتظهر فيه كل الأعمدة بما فيها عمود Y نفسه",y2opts,index=y2opts.index(cur2) if cur2 in y2opts else 0,key="iy2b_"+str(i))
            if it["ycol2"]=="—": it["ycol2"]=None
            it["y2rows"]=None
            if it["ycol2"] is not None and it["df"] is not None:
                # فلترة Y2 المستقلة: تعمل على عمود المقارنة وحده ولا تمسّ Y ولا النسبة المحققة
                st.markdown(f"**فلترة مستقلة لعمود Y2 ({it['ycol2']})** — تعمل على هذا العمود وحده ولا تمسّ Y ولا النسبة المحققة:")
                fx=column_filters(it["df"].copy(), it["ycol2"], "sfy2"+str(i), it.get("_flt") or None)
                it["y2rows"]=list(fx.index)
            if it.get("types") and any(t in it["types"] for t in ("StackedBar","Clustered","Combo")) and it["ycol2"] is None:
                st.warning("⚠️ اختر عمودًا ثانيًا (Y2) من القائمة أعلاه ليظهر الرسم المختار، أو أزله من طرائق العرض")
            st.markdown("**%s**"%T("filter_before"),unsafe_allow_html=True)
            _sav=it.get("_flt") or None
            yf=column_filters(it["df"].copy(),it["ycol"],"sfy"+str(i),_sav)
            it["yrows"]=list(yf.index)
            base=it["df"].copy()
            xcol=it["xcol"]
            # فلتر عمود X الاختياري (نصّي/رقمي/تاريخي حسب نوعه) — ونحفظ صفوفه في xrows
            fdf=column_filters(base,xcol,"sfx"+str(i),_sav)
            it["xrows"]=list(fdf.index)
            # ===== فلتر الأسئلة الخمسة (لمؤشرات الرضا/التحسّن) =====
            # يختار المستخدم خمسة أعمدة، ولكل عمود يختار القيم «المقبولة».
            # الصف يُحتسب إذا اجتاز **كل** الأسئلة الخمسة (أي قيمته ضمن قيم كل سؤال).
            # هذا يحسب «نسبة الذين تحسّنوا» = (أجتازوا الخمسة) ÷ (داخل الفترة) × 100.
            # ملاحظة: الفلتر اختياري ويظهر **للمؤشر الأول فقط** (i==0)،
            # فبقية المؤشرات لا تعرض المفتاح ولا تتأثر إطلاقًا.
            it["q5cols"]=None; it["q5vals"]=None
            if i!=0:
                # ===== ضمان العزل: المؤشر الأول فقط هو الذي يملك فلتر الأسئلة =====
                # نمسح أي حالة قديمة محفوظة، فلا يمكن لبقية المؤشرات أن تتأثر.
                it["q5on"]=False; it["q5rows"]=None; it["q5allow"]=False
            if i==0 and st.checkbox("🧮 فعّل فلتر الأسئلة الخمسة لهذا المؤشر",key=f"q5on_{i}",
                           value=bool(it.get("q5on"))):
                it["q5on"]=True
                it["q5allow"]=True
                with st.expander("اختر الأسئلة الخمسة وقيمها",expanded=True):
                    st.caption("يُحتسب الصف إذا كانت قيمته ضمن القيم المختارة في **كل** الأسئلة الخمسة معًا.")
                    _qcols=it["allc"]
                    _prev5=list(it.get("q5cols") or [])
                    _picks=[]
                    for _n in range(5):
                        _cur=_prev5[_n] if _n<len(_prev5) and _prev5[_n] in _qcols else None
                        _o=["—"]+list(_qcols)
                        _picks.append(st.selectbox(f"السؤال {[_n+1]}",_o,
                            index=_o.index(_cur) if _cur in _o else 0,key=f"q5c_{i}_{_n}"))
                    _sel5=[x for x in _picks if x!="—"]
                    if len(_sel5)<5:
                        st.caption("اختر الأسئلة الخمسة لتفعيل الفلتر (اخترت %d من 5)."%len(_sel5))
                    else:
                        _prevv=it.get("q5vals") or {}
                        _vv={}
                        for _n,_c in enumerate(_sel5):
                            _u=sorted(set(base[_c].dropna().astype(str).tolist()))
                            _sv=_prevv.get(_c,[])
                            _sv=[x for x in _sv if x in _u]
                            _vv[_c]=st.multiselect(f"قيم مقبولة — «{str(_c)[:46]}» ({len(_u)} قيمة)",
                                _u,default=_sv or _u,key=f"q5v_{i}_{_n}")
                        it["q5cols"]=_sel5
                        it["q5vals"]={k:v for k,v in _vv.items() if len(v)<len(set(map(str,base[k].dropna())))}
                        st.caption("✅ الفلتر مفعّل: الصف يجب أن يطابق كل الأسئلة الخمسة.")
            elif i==0:
                it["q5on"]=False; it["q5rows"]=None; it["q5allow"]=False
            # ===== قاعدة الخط الزمني (موحّدة) =====
            # كل مؤشر ينقص على فترة المنحة تلقائيًا حتى لو كان عمود X نصيًا:
            # عمود التاريخ يُختار: X إن كان تاريخيًا، وإلا أول عمود «تاريخ» في الجدول.
            # المقام في النسبة المحققة = عدد صفوف الفترة نفسها بلا أي فلتر آخر.
            _pcol=_pick_date_col(base,it.get("xcol"))
            xdt=bool(_pcol)
            if xdt:
                st.caption(f"⏱ زمن المنحة مطبّق تلقائًا على العمود «{_pcol}» — الرسم والنسبة تستخدمان صفوف الفترة فقط.")
            _pmask=_period_mask(fdf,_pcol,start_dt,end_dt)
            if _pmask is not None:
                fdf=fdf[_pmask].copy()
                pdf=fdf.copy()
            else:
                pdf=fdf.copy()
            _pm_total=len(pdf)
            # تطبيق فلتر عمود Y على pdf (المحقق) — Y2 لا يدخل في حساب النسبة المحققة
            if isinstance(it.get("yrows"),list) and len(it.get("yrows") or [])>0:
                pdf=pdf[pdf.index.isin(it["yrows"])].copy()
            # ===== تطبيق فلتر الأسئلة الخمسة (للمؤشر الأول فقط) =====
            # الصف يجب أن يجتاز الأسئلة الخمسة مجتمعةً، فيكون pdf = الفئة المحققة.
            if it.get("q5on") and it.get("q5cols") and it.get("q5vals"):
                _qm=base.apply(q5_mask,axis=1,qcols=it["q5cols"],qvals=it["q5vals"])
                fdf=fdf[_qm.reindex(fdf.index).fillna(False)].copy()
                _m2=_qm.reindex(pdf.index).fillna(False)
                it["q5rows"]=list(pdf.index[_m2])
                pdf=pdf[_m2].copy()
                st.caption(f"🧮 فلتر الأسئلة الخمسة: {_pm_total:,} صف داخل الفترة، اجتاز {len(pdf):,} صف.")
            else:
                it["q5rows"]=None
            it["fdf"]=fdf
            it["pdf"]=pdf
            capture_flt(it,["sfy"+str(i),"sfx"+str(i),"sfy2"+str(i)])
        # الهدف المخصص + نوع النسبة (نسبة مئوية % أو رقم) + طرق العرض المطلوبة
        # نقرأ الوضع من رقم الخيار (0=نسبة، 1=رقم) بدل نصّه، حتى لا يتأثر بترجمة الواجهة
        _pmode=st.radio(f"{T('target_mode')} — مؤشر {i+1}",[T("pct_mode_pct"),T("pct_mode_num")],
                        horizontal=True,index=(0 if it.get("pct_mode","%")!="رقم" else 1),key="ipct_"+str(i))
        # الوضع من رقم الخيار (0=نسبة، 1=رقم) — مستقل عن اللغة، والقيمة الداخلية تبقى "رقم"/"%"
        it["pct_mode"]="رقم" if ss.get("ipct_"+str(i))==1 else "%"
        if it["pct_mode"]=="رقم":
            it["target"]=st.number_input(f"الهدف المخصص للمؤشر {i+1} (رقم — وهو الأصل 100)",min_value=0.0,value=float(it.get("target",0.0)),key="itgt_"+str(i))
        else:
            it["target"]=st.number_input(f"الهدف المخصص للمؤشر {i+1} (%)",min_value=0.0,value=float(it.get("target",0.0)),key="itgt_"+str(i))
        # لا يوجد فلتر قيم 1..5 — الفلترة على الأعمدة الثلاثة (X/Y/Y2) فقط،
        # والقيم المحققة تُشتق من الفلتر الذي يختاره المستخدم على عمود Y.
        it.pop("good_vals",None)
        # عندما يكون هناك 3 مدخلات (X + Y + Y2) تُقيّد طرق الرسم إلى «الخط» أو «مقياس Gauge» فقط،
        # لأن هذين الطريقتين تُظهران الأرقام الثلاثة بوضوح، ولا يُطلب أي رسم دائري.
        y2_on=it.get("ycol2") is not None
        _avail=list(TLBL.keys()) if not y2_on else ["Line","Gauge"]
        cur=it.get("types") or ["Line"]
        if y2_on:
            cur=[x for x in cur if x in _avail] or ["Line"]
        it["types"]=st.multiselect(f"طرق العرض — مؤشر {i+1}",_avail,default=cur,format_func=lambda x:TLBL[x],key="itypes_"+str(i))
        # ===== «الأعمدة العمرية» رسم واحد حصري: لا يُعرض معه رسم آخر للمؤشر نفسه =====
        if "AgeSplit" in (it.get("types") or []) and len(it.get("types") or [])>1:
            it["types"]=["AgeSplit"]
            st.info("ℹ️ «أعمدة عمرية (ذكور/إناث)» رسم واحد، لذلك تم إلغاء بقية طرق العرض لهذا المؤشر.")
        # ===== بعد اختيار نوع الرسم: المستخدم يختار بنفسه أعمدة الفئات العمرية الثمانية =====
        if "AgeSplit" in (it.get("types") or []) and it.get("df") is not None:
            _adf=it["df"]
            _acols=[c for c in _adf.columns if pd.api.types.is_numeric_dtype(_adf[c])]
            if not _acols: _acols=list(_adf.columns)
            _amc,_afc=_age_gender_pairs(_adf) or ([],[])
            def _guess(src,k):
                # k = رقم الفئة العمرية (0..3)، وليس قائمة
                got=[c for c in src if _age_order_key(c)==k]
                return got[0] if got else None
            _prev=it.get("agesplit_cols") or {}
            if not isinstance(_prev,dict): _prev={}
            _gm=[_prev.get("m0") or _guess(_amc,0),_prev.get("m1") or _guess(_amc,1),
                 _prev.get("m2") or _guess(_amc,2),_prev.get("m3") or _guess(_amc,3)]
            _gf=[_prev.get("f0") or _guess(_afc,0),_prev.get("f1") or _guess(_afc,1),
                 _prev.get("f2") or _guess(_afc,2),_prev.get("f3") or _guess(_afc,3)]
            _gm=[c if c in _acols else (_acols[0] if _acols else None) for c in _gm]
            _gf=[c if c in _acols else (_acols[0] if _acols else None) for c in _gf]
            def _ix(c):
                # فهرس العمود داخل القائمة، بأمان (إن لم يوجد نعود لأول عنصر)
                try: return _acols.index(c)
                except Exception: return 0
            st.markdown("**اختر أعمدة الفئات العمرية الثمانية (٤ ذكور + ٤ إناث):**")
            _c1,_c2=st.columns(2)
            _new={}
            with _c1:
                st.caption("♂️ ذكور")
                _new["m0"]=st.selectbox("ذكور — أقل من 5",_acols,index=_ix(_gm[0]),key=f"agm0_{i}")
                _new["m1"]=st.selectbox("ذكور — 5 إلى 17",_acols,index=_ix(_gm[1]),key=f"agm1_{i}")
                _new["m2"]=st.selectbox("ذكور — 18 إلى 49",_acols,index=_ix(_gm[2]),key=f"agm2_{i}")
                _new["m3"]=st.selectbox("ذكور — 50 فأكثر",_acols,index=_ix(_gm[3]),key=f"agm3_{i}")
            with _c2:
                st.caption("♀️ إناث")
                _new["f0"]=st.selectbox("إناث — أقل من 5",_acols,index=_ix(_gf[0]),key=f"agf0_{i}")
                _new["f1"]=st.selectbox("إناث — 5 إلى 17",_acols,index=_ix(_gf[1]),key=f"agf1_{i}")
                _new["f2"]=st.selectbox("إناث — 18 إلى 49",_acols,index=_ix(_gf[2]),key=f"agf2_{i}")
                _new["f3"]=st.selectbox("إناث — 50 فأكثر",_acols,index=_ix(_gf[3]),key=f"agf3_{i}")
            it["agesplit_cols"]=_new
            # ===== فلتر اختياري على عمود (مثل Service provider code) قبل حساب الأعمدة العمرية =====
            _fall=list(_adf.columns)
            _dflt="Service provider code" if "Service provider code" in _fall else (_fall[0] if _fall else None)
            _fcol=st.selectbox("فلتر الأعمدة العمرية حسب عمود",_fall,index=(_fall.index(_dflt) if _dflt in _fall else 0),
                               key=f"agfc_{i}")
            if _fcol:
                _fvals=[str(v) for v in pd.Series(_adf[_fcol]).dropna().unique().tolist()]
                _prevf=it.get("agesplit_fvals") or []
                _prevf=[v for v in _prevf if v in _fvals] or _fvals
                it["agesplit_fcol"]=_fcol
                it["agesplit_fvals"]=st.multiselect(f"القيم المطلوبة من «{_fcol}»",_fvals,default=_prevf,key=f"agfv_{i}")
            else:
                it["agesplit_fcol"]=None; it["agesplit_fvals"]=[]
            # ===== قصّ زمن المنحة على عمود التاريخ (مثل Session date) =====
            # ملاحظة أداء: لا نفحص كل الأعمدة بـ to_datetime لأن ذلك بطيء جدًا
            # على الملفات الكبيرة (‏1.2 ثانية لكل 136 عمود × كل مؤشر × كل تحديث).
            # نكتفي بالأعمدة المرشَّحة: أعمدة datetime فعلًا، أو أسماءها فيها «تاريخ/date»،
            # واللي بنمط تاريخ نتحقق منه فقط عبر date_like.
            _dcols=[]
            for c in _adf.columns:
                if pd.api.types.is_datetime64_any_dtype(_adf[c]):
                    _dcols.append(c)
                elif any(k in str(c) for k in ("تاريخ","date","Date","التاريخ")):
                    if date_like(_adf,c): _dcols.append(c)
            if _dcols:
                _dd="Session date" if "Session date" in _dcols else _dcols[0]
                it["agesplit_dcol"]=st.selectbox("عمود التاريخ لقصّ زمن المنحة",_dcols,
                    index=_dcols.index(it.get("agesplit_dcol") if it.get("agesplit_dcol") in _dcols else _dd),
                    key=f"agdc_{i}")
                st.caption("يتقصّ الرسم العمري على زمن المنحة المحدد أعلى الصفحة (لا يبدأ قبل ولا ينتهي بعد).")
            else:
                it["agesplit_dcol"]=None
                st.caption("⚠️ لا يوجد عمود تاريخ صالح في هذا الملف — الرسم العمري سيعرض كل التواريخ.")
            if any(_new.get(k) for k in ("m0","m1","m2","m3","f0","f1","f2","f3")):
                st.caption("الأعمدة على المحور X، وعمودان لكل فئة: ذكور وإناث. المحور Y = عدد الأشخاص (مجموع كل الجلسات).")
        # إن اختيرت طريقة (متراكمة/مجمّعة/كومبو) بلا Y2 محدد → نعيّن عمودًا رقميًا تلقائيًا وننبه
        reqt=("StackedBar","Clustered","Combo")
        if it["types"] and it.get("ycol2") is None and any(t in it["types"] for t in reqt) and it.get("df") is not None:
            fb=None
            for c in (it.get("numc") or []):
                if c!=it.get("ycol") and c!=it.get("xcol"): fb=c; break
            if fb is None:
                for c in it.get("allc",[]):
                    if c!=it.get("ycol") and c!=it.get("xcol"): fb=c; break
            if fb is not None:
                it["ycol2"]=fb
                try: st.session_state["iy2b_"+str(i)]=fb
                except Exception: pass
                st.caption(f"⚙️ اخترت نوع رسم يتطلب مقارنة — عيّنت عمود Y2 تلقائيًا: **{fb}** (غيّره من القائمة أعلاه أو اعمل «—» لتعطيله)")
        # إعداد عنوان الرسم وأسماء المحاور وعدد التقسيمات (يُتجاوز هذا القسم لمقياس Gauge)
        if it["types"] and "Gauge" not in it["types"]:
            it["title"]=st.text_input(f"عنوان الرسم — مؤشر {i+1}",it.get("title",""),key="ittl_"+str(i))
            a1,a2,a3=st.columns([1,1,1])
            it["xlabel"]=a1.text_input(f"عنوان محور X — مؤشر {i+1}",it.get("xlabel",""),key="ixl_"+str(i))
            it["ylabel"]=a2.text_input(f"عنوان محور Y — مؤشر {i+1}",it.get("ylabel",""),key="Iyl_"+str(i))
            it["nticks"]=a3.number_input(f"تقسيمات محور X — مؤشر {i+1}",min_value=1,value=int(it.get("nticks",5) or 5),step=1,key="intk_"+str(i))
            xc2=it.get("xcol") or ""
            dtcol=(it.get("df") is not None and date_like(it["df"],xc2))
            # عمود زمني → خيارات تجميع الوقت (يومي/أسبوعي/شهري/سنوي) والطريقة الحسابية للخط/المساحة
            if dtcol and (("Line" in it["types"]) or ("Area" in it["types"])):
                b1,b2=st.columns(2)
                units=["يومي","أسبوعي","شهري","سنوي"]
                it["unit"]=b1.selectbox(f"تجميع الخط الزمني — مؤشر {i+1}",units,index=(units.index(it.get("unit")) if it.get("unit") in units else 2),key="iunit_"+str(i))
                aggs=["مجموع","عدد السجلات","متوسط"]
                it["agg"]=b2.selectbox(f"طريقة الحساب — مؤشر {i+1}",aggs,index=(aggs.index(it.get("agg")) if it.get("agg") in aggs else 0),key="iagg_"+str(i))
            # الخريطة: اختيار عمودي خط/طول العرض شرط وجود عمودين رقميين على الأقل
            if "Map" in it["types"] and it.get("df") is not None:
                nc=it.get("numc") if it.get("numc") else [c for c in it["df"].columns if pd.api.types.is_numeric_dtype(it["df"][c])]
                if len(nc)>=2:
                    m1,m2=st.columns(2)
                    curlat=it.get("latc"); curlon=it.get("lonc")
                    lati=nc.index(curlat) if curlat in nc else (nc.index(it.get("ycol")) if it.get("ycol") in nc else 0)
                    loni=nc.index(curlon) if curlon in nc else (nc.index(it.get("xcol")) if it.get("xcol") in nc else (1 if len(nc)>1 else 0))
                    it["latc"]=m1.selectbox(f"عمود خط العرض (Lat) - مؤشر {i+1}",nc,index=lati,key="ilat_"+str(i))
                    it["lonc"]=m2.selectbox(f"عمود خط الطول (Lon) - مؤشر {i+1}",nc,index=loni,key="ilon_"+str(i))
                else:
                    st.caption("الخريطة تحتاج عمودين رقميين على الأقل (Lat/Lon)")
        it.setdefault("latc",None); it.setdefault("lonc",None)
        st.markdown("</div>",unsafe_allow_html=True)
        # حفظ تلقائي بعد كل تعديل على هذا المؤشر (مسودة مستمرة)
        it["_draft"]=ss.get("_draft") or {}
        autosave()
    # إضافة مؤشر جديد فارغ إلى القائمة
    if st.button(T("btn_add_ind"),key="iadd_",use_container_width=True):
        ss["indicators"].append({"name":"","df":None,"xcol":"","ycol":"","ycol2":None,"target":0.0,"types":["Line"],"file_name":"","pct_mode":"%"})
        st.rerun()
    # أزرار الإجراء: العودة للجدار / إنهاء الإعداد والانتقال إلى اللوحة / حفظ المسودة فقط
    cB1,cB2,cB3=st.columns(3)
    if cB1.button(T("btn_home2"),use_container_width=True):
        ss["view"]="home"; ss["phase"]="setup"; st.rerun()
    if cB2.button("اتم — الانتقال إلى اللوحة",use_container_width=True):
        ss["grant"]={"name":st.session_state.get("gname",""),"services":int(st.session_state.get("gserv",0) or 0),"beneficiaries":int(st.session_state.get("gben",0) or 0),"start":start_dt,"end":end_dt}
        ss["_draft"]={}
        ss["phase"]="dashboard"; ss["view"]="dashboard"
        autosave()
        st.rerun()
    if cB3.button("💾 حفظ المسودة فقط",use_container_width=True):
        autosave(); st.success("تم حفظ المسودة تلقائيًا")

# ===== لوحة المتابعة (Dashboard): شريط الخط الزمني + بطاقات إحصائية + رسوم المؤشرات =====
if ss.get("view")=="dashboard":
    if ss.get("phase")=="setup":
        ss["phase"]="dashboard"
    autosave()
    g=ss.get("grant") or {}
    ind=ss.get("indicators") or []
    sd=ed=None
    try:
        if g.get("start"): sd=pd.Timestamp(g["start"]).date()
        if g.get("end"): ed=pd.Timestamp(g["end"]).date()
    except Exception: pass
    # شريط الخط الزمني: نسبة انقضاء فترة المنحة حتى اليوم مع مؤشر «الآن»
    tl=None
    if sd and ed:
        today=datetime.date.today()
        try:
            gap=(pd.Timestamp(ed)-pd.Timestamp(sd)).days or 1
            pctt=max(0,min(100,(pd.Timestamp(today)-pd.Timestamp(sd)).days/gap*100))
            tl=f'''
    <div class="tl">
      <div class="tl-bar"><span><b style="color:#00d4ff">{sd.strftime("%Y-%m-%d")}</b> آخر إلى <b style="color:#00d4ff">{ed.strftime("%Y-%m-%d")}</b> اليوم</span><span style="color:#4ade80">{pctt:.0f}%</span></div>
      <div class="tl-track">
        <div class="tl-fill" style="width:{pctt:.1f}%"></div>
        <div class="tl-globe" style="left:{pctt:.1f}%">📍</div>
      </div>
      <div class="tl-marks"><span>البداية: {sd.strftime("%Y-%m-%d")}</span><span class="tl-now">الآن: {today.strftime("%Y-%m-%d")}</span><span>النهاية: {ed.strftime("%Y-%m-%d")}</span></div>
    </div>
    '''
            st.markdown(md_html(tl),unsafe_allow_html=True)
        except Exception: pass
    # شريط العنوان والأزرار: العودة للإعداد / حفظ المشروع / الذهاب للرئيسية (الأزرار للأدمن فقط)
    top=st.columns([3,1,1,1]) if is_admin() else st.columns([3,1])
    with top[0]: st.title(f"SAMS — {g.get('name','بدون اسم')}")
    if is_admin():
        with top[1]:
            if st.button(T("btn_edit"),use_container_width=True):
                ss["phase"]="setup"; ss["view"]="form"; st.rerun()
        with top[2]:
            if st.button(T("btn_save"),use_container_width=True):
                p=save_dashboard(); st.success("تم الحفظ داخل الموقع: "+os.path.basename(p))
        with top[3]:
            if st.button(T("btn_home2"),use_container_width=True): ss["view"]="home"; st.rerun()
    else:
        with top[1]:
            if st.button(T("btn_home2"),use_container_width=True): ss["view"]="home"; st.rerun()
    # بطاقات الإحصاء العامة: الاسم / الخدمات / المستفيدون / عدد المؤشرات
    c1,c2,c3,c4=st.columns(4)
    with c1: st.markdown('<div class="stat"><small>اسم المنحة</small><b style="font-size:15px;color:#e6edf7">'+str(g.get("name","-"))+'</b></div>',unsafe_allow_html=True)
    with c2: st.markdown('<div class="stat"><small>عدد الخدمات المضافة</small><b>'+fmt(g.get("services",0),True)+'</b></div>',unsafe_allow_html=True)
    with c3: st.markdown('<div class="stat"><small>عدد المستفيدين</small><b>'+fmt(g.get("beneficiaries",0),True)+'</b></div>',unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="stat"><small>عدد المؤشرات</small><b>{len(ind)}</b></div>',unsafe_allow_html=True)
    st.markdown("<br>",unsafe_allow_html=True)
    # بطاقات متابعة المؤشرات: تُعرض في صفوف من اثنين (عمودان في كل صف)
    boxes=[it for it in ind if it.get("fdf") is not None and it.get("ycol")]
    if boxes:
        st.markdown('<div class="sect">%s</div>'%T("monitor"),unsafe_allow_html=True)
        for r in range(0,len(boxes),2):
            row=boxes[r:r+2]
            cols=st.columns(2)
            for j,it in enumerate(row):
                with cols[j]:
                    df=it["fdf"].copy()
                    # حساب الإنجاز (done/total) والهدف ولون البطاقة (أخضر عند بلوغ الهدف)
                    done,total_n,pct=indicator_pct(it,sd,ed)
                    target=float(it.get("target",0) or 0)
                    nummode=(it.get("pct_mode") or "%")=="رقم"
                    # ===== «الأعمدة العمرية»: المحقق = مجموع الذكور + الإناث =====
                    # يُحسب بنفس فلترة الرسم تمامًا (نفس زمن المنحة ونفس Service provider code)،
                    # ثم يُقارَن بالهدف الرقمي (مثل 6600). فمثلًا ذكور 3,100 + إناث 3,250
                    # = محقق 6,350 من هدف 6,600.
                    agc=None; agerr=None
                    if "AgeSplit" in (it.get("types") or []):
                        _agsrc_c=it.get("df") if it.get("df") is not None else df
                        agc,agerr=agesplit_counts(_agsrc_c,
                                                  use_improved=bool(it.get("agesplit_improved",False)),
                                                  cols=it.get("agesplit_cols"),
                                                  fcol=it.get("agesplit_fcol"),
                                                  fvals=it.get("agesplit_fvals"),
                                                  dcol=it.get("agesplit_dcol"),
                                                  sd=sd,ed=ed)
                        if agc: done=float(agc["grand_total"])
                    # ===== وضع «رقم»: الهدف رقم، والهدف هو الأصل (100) =====
                    # البطاقة تعرض أرقامًا فقط (المحقق/الهدف/الفرق) بلا أي نسبة مؤوية.
                    # أما مقياس Gauge فيحسب نسبة الإنجاز من الهدف: المحقق ÷ الهدف × 100.
                    # وضع «نسبة مئوية %» (المؤشران 1 و 2): كل شيء كما كان —
                    #   المقام/الأصل = عدد الصفوف، والهدف يبقى بنسبة مئوية.
                    _tgsuf="" if nummode else "%"
                    _tg=f"{target:,.0f}" if nummode else f"{target:.1f}{_tgsuf}"
                    if nummode:
                        gpct=(float(done)/target*100.0) if target>0 else 0.0
                        ok=(float(done)>=target) if target>0 else True
                        goodcls="green" if ok else "warn"
                        title=it.get('name') or (f'مؤشر {it["xcol"]}' if it.get("xcol") else "مؤشر")
                        base_txt=f"{target:,.0f}"
                        _gap=(float(done)-target)
                        sub2=(f'<div class="ibox-sub">↕️ الفرق عن الهدف: {_gap:+,.0f}</div>'
                              if target>0 else "")
                        bv=f"{done:,.0f}"
                        bvlab="المحقق"
                    else:
                        gpct=pct
                        ok=pct>=target
                        goodcls="green" if ok else "warn"
                        title=it.get('name') or (f'مؤشر {it["xcol"]}' if it.get("xcol") else "مؤشر")
                        base_txt=f"{total_n:,}"
                        sub2=f'<div class="ibox-sub">📊 نسبة الإنجاز: {pct:.1f}%</div>'
                        bv=f"{pct:.1f}%"
                        bvlab="المنجز"
                    # ===== تفصيل الذكور والإناث داخل البطاقة (لمؤشر الأعمدة العمرية) =====
                    # يوضّح مصدر رقم «المحقق»: ذكور + إناث، مع الفارق عن الهدف.
                    if agc:
                        _am=agc["total_males"]; _af=agc["total_females"]
                        _ap=(float(done)/target*100.0) if target>0 else 0.0
                        agsub=(f'<div class="ibox-sub">👨 ذكور: {int(round(_am)):,} | 👩 إناث: {int(round(_af)):,}'
                               f' | المجموع: {int(round(done)):,}</div>'
                               f'<div class="ibox-sub">📈 نسبة المحقق من الهدف: {_ap:.1f}%'
                               + (f" | المتبقي: {max(0,target-done):,.0f}" if target>0 else "")
                               + "</div>")
                    elif agerr:
                        agsub=f'<div class="ibox-sub">⚠️ تعذّر حساب الذكور/الإناث: {agerr}</div>'
                    else:
                        agsub=""
                    st.markdown(md_html(f'''
                    <div class="ibox">
                      <div class="ibox-head">
                        <div>
                          <span class="ibox-title">📋 {title}</span>
                          <div class="ibox-sub">🔢 {done:,} من أصل {base_txt}</div>
                          {sub2}
                          {agsub}
                        </div>
                        <div style="display:flex;align-items:center;gap:12px">
                          <span class="chip {'target' if ok else ''}">هدف {_tg}</span>
                          <span class="bigval {goodcls}"><span class="bv">{bv}</span><span class="bvlab">{bvlab}</span></span>
                        </div>
                      </div>
                    </div>'''),unsafe_allow_html=True)
                    # ===== «الأعمدة العمرية» مفردة: بلا مقياس نسبة في البطاقة =====
                    # وإلا ظهر معه مقياس نسبة إضافةً إلى الأعمدة = رسمان، والمستخدم يريد رسمًا واحدًا.
                    # نفس القاعدة تنطبق على أي رسم مُختار فعليًا (KPI/Line/Bar/...):
                    # إذا اختار المستخدم رسمًا، لا نضيف له مقياس نسبة — يكون للمؤشر رسم واحد فقط.
                    _agsplit_only="AgeSplit" in (it.get("types") or [])
                    _has_own_chart=bool([x for x in (it.get("types") or [])
                                         if x not in ("Gauge",)])
                    if nummode and not _agsplit_only and not _has_own_chart:
                        # ===== الرسم فقط: مقياس نسبة الإنجاز من الهدف =====
                        # النسبة = المحقق ÷ الهدف × 100 (والهدف هو الأصل 100).
                        # استثناء «الأعمدة العمرية»: مقياس النسبة يُلغى له حتى لا يظهر معه
                        # لأنه رسم واحد بحد ذاته والمستخدم لا يريد أكثر من رسم للمؤشر.
                        components.html(
                            gauge_html(gpct,100.0,str(id(it)),
                                       y2_label=it.get("ycol2") or "Y2",y2_pct=indicator_y2_pct(it),
                                       num_mode=True,base_txt=f"الهدف {target:,.0f}"),
                            height=340)
                    elif "Gauge" in (it.get("types") or []) and "AgeSplit" not in (it.get("types") or []):
                        components.html(gauge_html(pct,target,str(id(it)),y2_label=it.get("ycol2") or "Y2",y2_pct=indicator_y2_pct(it)),height=340)
                    # ===== صندوق فلترة النتائج: العدد الكلي + العدد بعد فلترة الثلاثة + النسبة =====
                    # الفلتر النهائي = تقاطع فلاتر X و Y و Y2 معًا على بيانات فترة المنحة،
                    # فيعطي «العدد الصح» لأي تركيبة فلاتر يختارها المستخدم.
                    with st.expander("🔎 فلترة البيانات ونتائجها",expanded=False):
                        _full=it.get("df"); _f=it.get("fdf")
                        # 1) كل الجدول
                        _n_all=len(_full) if _full is not None else 0
                        # 2) داخل فترة المنحة (بلا فلاتر الأعمدة)
                        _pd=_pick_date_col(_full,it.get("xcol")) if _full is not None else None
                        _pm=_period_mask(_full,_pd,sd,ed) if _full is not None else None
                        _inper=_full[_pm] if _pm is not None else _full
                        _n_per=len(_inper) if _inper is not None else 0
                        # 3) الفلتر النهائي = تقاطع فلاتر Y و Y2 (وكذا X إن وُجد) على بيانات الفترة
                        _fin=_intersect_rows(_inper,it)
                        _n_fin=len(_fin) if _fin is not None else 0
                        # 4) النسبة = المحقق ÷ المقام (المقام = صفوف X داخل زمن المنحة، بلا فلتر Y)
                        _p_fil=(100.0*_n_fin/_n_per) if _n_per>0 else 0.0
                        _kept=_p_fil
                        _fc1,_fc2,_fc3,_fc4=st.columns(4)
                        with _fc1:
                            st.markdown(f'<div class="stat"><small>العدد الكلي (الملف كلو)</small><b>{_n_all:,}</b></div>',unsafe_allow_html=True)
                        with _fc2:
                            st.markdown(f'<div class="stat"><small>داخل زمن المنحة</small><b>{_n_per:,}</b></div>',unsafe_allow_html=True)
                        with _fc3:
                            st.markdown(f'<div class="stat"><small>بعد فلترة الثلاثة</small><b>{_n_fin:,}</b></div>',unsafe_allow_html=True)
                        with _fc4:
                            st.markdown(f'<div class="stat"><small>نسبة المحققين (بعد الفلترة)</small><b>{_p_fil:.1f}%</b></div>',unsafe_allow_html=True)
                        st.caption(f"الفلاتر الثلاثة (X و Y و Y2) مجمّعة معًا: {_n_fin:,} صف من {_n_per:,} صف داخل فترة المنحة — أي {_kept:.1f}% متبقي بعد الفلترة.")
                        # تنبيه: إذا كان فلتر Y و Y2 متعاكسين (مثلًا Y=4,5 و Y2=1,2,3 على نفس العمود)
                        # ستحدث النتيجة صفرية. نُنبّه المستخدم بدل ما يشوف صفر بدون تفسير.
                        if _n_per>0 and _n_fin==0:
                            st.warning("⚠️ الفلترة أعطت صفر صفوف — غالبًا فلاتر Y و Y2 متعاكسين على نفس العمود، أو الفلاتر لا تتقاطع. راجع الفلاتر.")
                        if _fin is not None and _n_fin>0:
                            st.dataframe(_fin.head(200),use_container_width=True)
                    cd=df
                    cd2=cd.copy()
                    yc_=it.get("ycol"); y2_=it.get("ycol2")
                    # تجهيز أعمدة العرض: قص Y و Y2 على فلاترهما الخاصة وإعادة تسمية المخالف لتجنب
                    # تصادم الأسماء في الجدول الناتج ثم تمريرهما لرسم الطرق المختارة
                    it["_ydisp"]=yc_; it["_y2disp"]=y2_
                    for col,rows,dv,tag in ((yc_,it.get("yrows"),"_ydisp","(Y)"),(y2_,it.get("y2rows"),"_y2disp","(Y2)")):
                        if not col or col not in cd.columns: continue
                        dn=col
                        if col==it.get("xcol") or (tag=="(Y)" and col==y2_) or (tag=="(Y2)" and col==yc_):
                            dn=col+" "+tag
                        cd2[dn]=cd[col].where(cd.index.isin(rows)) if rows is not None else cd[col]
                        it[dv]=dn
                    if it.get("_y2disp") is None and it.get("types") and any(t in it["types"] for t in ("StackedBar","Clustered","Combo")):
                        fb=None
                        for c in cd.columns:
                            if c not in (it["xcol"],it["ycol"]): fb=c; break
                        if fb is not None:
                            it["_y2disp"]=fb
                            cd2[fb]=cd[fb]
                            _reqn=next((t for t in it["types"] if t in ("StackedBar","Clustered","Combo")),None)
                            st.caption(f"⚠️ {TLBL.get(_reqn,_reqn or '')} استخدم عمودًا ثانيًا تلقائيًا: **{fb}** — حدده من «عمود ثانٍ» في الإعداد للتحكم")
                    # حلقة عرض كل طريقة من طرق الرسم المختارة على نفس البيانات المفلترة
                    cd_main=cd
                    # ===== «الأعمدة العمرية» حصري: لا يُعرض معه رسم آخر لهذا المؤشر =====
                    # يُطبَّق هنا أيضًا (وليس بصفحة الإعداد فقط) حتى لو كانت طرق العرض
                    # محفوظة قديمة بأكثر من طريقة، فلا يظهر للمؤشر أكثر من رسم واحد.
                    _types=list(it.get("types") or ["Line"])
                    if "AgeSplit" in _types:
                        _dropped=[x for x in _types if x!="AgeSplit"]
                        _types=["AgeSplit"]
                        if _dropped:
                            st.caption("ℹ️ «أعمدة عمرية (ذكور/إناث)» رسم واحد — تم تجاهل: "
                                       + "، ".join(TLBL.get(x,x) for x in _dropped))
                    for t in _types:
                        if t=="Gauge": continue
                        if t=="Table":
                            st.caption(f"جدول البيانات بعد الفلترة — أول 200 صف من {len(cd_main):,}")
                            st.dataframe(cd_main.reset_index(drop=True).head(200),use_container_width=True)
                            continue
                        if t=="Pivot":
                            y2c=it.get("ycol")
                            if it["xcol"] in cd_main.columns and y2c in cd_main.columns:
                                aggf={"مجموع":"count","عدد السجلات":"count","متوسط":"mean"}.get(it.get("agg","مجموع"),"count")
                                pv=cd_main.pivot_table(index=it["xcol"],values=y2c,aggfunc=aggf)
                                st.caption("المصفوفة المحورية (تجميع حسب X):")
                                st.dataframe(pv,use_container_width=True)
                            else:
                                st.error("المصفوفة تحتاج أعمدة X و Y")
                            continue
                        if t=="Map":
                            lat=it.get("latc");lon=it.get("lonc")
                            if lat in cd_main.columns and lon in cd_main.columns:
                                mdf=pd.DataFrame({"lat":pd.to_numeric(cd_main[lat],errors="coerce"),"lon":pd.to_numeric(cd_main[lon],errors="coerce")}).dropna()
                                if len(mdf): st.map(mdf)
                                else: st.error("لا إحداثيات صالحة في البيانات المفلترة")
                            else:
                                st.error("الخريطة تحتاج اختيار عمودي Lat و Lon من الإعداد")
                            continue
                        if t=="AgeSplit":
                            # ===== الأعمدة العمرية: 4 فئات على X، وعمودان (ذكور/إناث) لكل فئة =====
                            # تُحسب الأعمدة الثمانية تلقائيًا من الملف الكامل بلا أي اختيار يدوي،
                            # وبلا تأثّر بفلتر الفترة/الفلاتر المخصصة (حتى لا تظهر أعمدة صفرية).
                            _imp=bool(it.get("agesplit_improved",False))
                            _agsrc=it.get("df") if it.get("df") is not None else cd_main
                            _agf,_aginfo,_agerr=make_agesplit_fig(_agsrc,target=target,
                                                  use_improved=_imp,period_label=it.get("unit") or "",
                                                  cols=it.get("agesplit_cols"),
                                                  fcol=it.get("agesplit_fcol"),
                                                  fvals=it.get("agesplit_fvals"),
                                                  dcol=it.get("agesplit_dcol"),
                                                  sd=sd,ed=ed)
                            if _agerr:
                                st.error(_agerr)
                                st.caption(f"📄 صفوف البيانات المستخدمة للرسم: **{len(_agsrc):,}** "
                                           f"(الملف كامل: **{len(it.get('df') or []):,}**)")
                            else:
                                _fig_tr(_agf); st.pyplot(_agf,use_container_width=True)
                                if _aginfo:
                                    if _aginfo.get("warning"): st.warning(_aginfo["warning"])
                                    st.caption(f"📄 صفوف داخل الفلترة: **{_aginfo.get('rows_used',0):,}** "
                                               f"من **{_aginfo.get('rows_before',0):,}**"
                                               f" | 🗓️ القصّ: {it.get('agesplit_dcol') or 'بدون تاريخ'}"
                                               f" | 🔎 فلتر: {it.get('agesplit_fcol') or 'بدون'}")
                                    st.caption(f"ذكور: {_aginfo['total_males']:,} | إناث: {_aginfo['total_females']:,} | الإجمالي: {_aginfo['grand_total']:,}")
                            continue
                        fig,_,err=make_fig(cd2,it["xcol"],it.get("_ydisp") or it["ycol"],t,vcol2=it.get("_y2disp") or None,xlabel=it.get("xlabel") or None,ylabel=it.get("ylabel") or None,nticks=it.get("nticks"),full=it.get("df"),period=it.get("unit") or None,agg=it.get("agg","مجموع"),title=it.get("title") or None,target=target,pctv=pct,good_vals=it.get("good_vals") or [4,5],done=done,pct_mode=it.get("pct_mode") or "%")
                        if err: st.error(err); continue
                        _fig_tr(fig); st.pyplot(fig,use_container_width=True)
                    # معاينة تفاعلية: تجربة كل أنواع الرسوم على نفس البيانات دون تغيير إعدادات المؤشر
                    with st.expander("🎛️ جرّب كل أنواع الرسوم على هذه البيانات (بنفس الفلترة)",expanded=False):
                        prev=st.selectbox("اختر نوع الرسم لتجربته", list(TLBL.keys()), format_func=lambda x:TLBL[x], key="prev_"+str(id(it)))
                        if prev=="Gauge":
                            components.html(gauge_html(pct,target,str(id(it))+"pv",y2_label=it.get("ycol2") or "Y2",y2_pct=indicator_y2_pct(it)),height=340)
                        elif prev=="Table":
                            st.dataframe(cd_main.reset_index(drop=True).head(200),use_container_width=True)
                        elif prev=="Pivot":
                            y2c=it.get("ycol")
                            if it["xcol"] in cd_main.columns and y2c in cd_main.columns:
                                aggf={"مجموع":"count","عدد السجلات":"count","متوسط":"mean"}.get(it.get("agg","مجموع"),"count")
                                pv=cd_main.pivot_table(index=it["xcol"],values=y2c,aggfunc=aggf)
                                st.dataframe(pv,use_container_width=True)
                        elif prev=="Map":
                            lat=it.get("latc");lon=it.get("lonc")
                            if lat in cd_main.columns and lon in cd_main.columns:
                                mdf=pd.DataFrame({"lat":pd.to_numeric(cd_main[lat],errors="coerce"),"lon":pd.to_numeric(cd_main[lon],errors="coerce")}).dropna()
                                if len(mdf): st.map(mdf)
                            else: st.error("الخريطة تحتاج اختيار Lat/Lon من الإعداد")
                        elif prev=="AgeSplit":
                            _agsrc=it.get("df") if it.get("df") is not None else cd_main
                            _agf,_aginfo,_agerr=make_agesplit_fig(_agsrc,target=target,
                                                  use_improved=bool(it.get("agesplit_improved",False)),
                                                  period_label=it.get("unit") or "",
                                                  cols=it.get("agesplit_cols"),
                                                  fcol=it.get("agesplit_fcol"),
                                                  fvals=it.get("agesplit_fvals"),
                                                  dcol=it.get("agesplit_dcol"),
                                                  sd=sd,ed=ed)
                            if _agerr: st.error(_agerr)
                            else:
                                _fig_tr(_agf); st.pyplot(_agf,use_container_width=True)
                                if _aginfo:
                                    st.caption(f"ذكور: {_aginfo['total_males']:,} | إناث: {_aginfo['total_females']:,} | الإجمالي: {_aginfo['grand_total']:,}")
                        else:
                            fig,_,err=make_fig(cd2,it["xcol"],it.get("_ydisp") or it["ycol"],prev,vcol2=it.get("_y2disp") or None,xlabel=it.get("xlabel") or None,ylabel=it.get("ylabel") or None,nticks=it.get("nticks"),full=it.get("df"),period=it.get("unit") or None,agg=it.get("agg","مجموع"),title=it.get("title") or None,target=target,pctv=pct,good_vals=it.get("good_vals") or [4,5],done=done,pct_mode=it.get("pct_mode") or "%")
                            if err: st.error(err)
                            else: _fig_tr(fig); st.pyplot(fig,use_container_width=True)
                    st.markdown('</div>',unsafe_allow_html=True)
            if len(row)==1:
                with cols[1]:
                    st.markdown('<div class="hintbox">➕ أضف مؤشرًا آخر من <b>«🔄 عدّل الإعداد»</b> ليملأ الصفحة ويظهر جنب هذا المؤشر</div>',unsafe_allow_html=True)

# ===== حفظ كاش الترجمة التلقائية بعد رسم الصفحة كلها =====
_auto_tr_flush()
