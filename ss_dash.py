# -*- coding: utf-8 -*-
"""
SAMS Dashboard — نقطة التشغيل الرئيسية
=====================================
شغّل التطبيق بهذا الأمر:

    streamlit run ss_dash.py

هذا الملف مجرد واجهة تشغيل: يستدعي app.py (كل منطق اللوحة والتصميم) بنفس الجلسة.
كذلك يستورد sams_meal.py تلقائياً عبر app.py لقسم متابعة المشاريع (MEAL).
"""
import os
import runpy

_HERE = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    runpy.run_path(os.path.join(_HERE, "app.py"), run_name="__main__")
