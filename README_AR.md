# SAMS Dashboard - Grant Monitoring

لوحة متابعة المشاريع الإنسانية لمنظمة Syrian American Medical Society (SAMS).

## تشغيل المشروع محلياً

1. تثبيت المتطلبات
```bash
pip install -r requirements.txt
```

2. تشغيل التطبيق
```bash
streamlit run app.py
```

سيتم فتح التطبيق تلقائياً على: `http://localhost:8501`

## رفعه على مواقع المشاركة
يمكنك رفع ملف `SAMS_DASHBOARD_READY.zip` على:
- [Pixeldrain](https://pixeldrain.com) - سريع وسهل ويعطي رابط مباشر
- [GoFile](https://gofile.io) - مجاني ومناسب للمشاركة
- [Filebin](https://filebin.net) - بسيط جداً

## ملاحظات
- ملف البيانات الرئيسي: `Basic and Final Update june 2026.xlsx`
- مجلد `crm/` يحتوي على جداول CRM المحفوظة
- مجلد `saves/` يحتوي on نسخ المنح المحفوظة تلقائياً
- يدعم التطبيق العربية والإنجليزية
