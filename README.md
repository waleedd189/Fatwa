# مساعد الفتاوى - دليل الإعداد

هذا التطبيق يعتمد على ذكاء Gemini الاصطناعي وخدمات البحث من Google وYouTube. لتشغيله بنجاح، تحتاج إلى توفير مفاتيحك الخاصة (API Keys).

## المتطلبات الأساسية
- Python 3.x مثبت على جهازك.
- مفتاح API لـ Gemini (مجاني) من [Google AI Studio](https://aistudio.google.com/).
- مفتاح API لـ YouTube من [Google Cloud Console](https://console.cloud.google.com/).

## كيفية التشغيل

1. **إعداد مفاتيح البيئة:**
   يجب عليك تعيين المفاتيح في نظامك قبل تشغيل السيرفر.

   **على Linux/Mac:**
   ```bash
   export GEMINI_KEY="مفتاحك_هنا"
   export YOUTUBE_KEY="مفتاحك_هنا"
   ```

   **على Windows (PowerShell):**
   ```powershell
   $env:GEMINI_KEY="مفتاحك_هنا"
   $env:YOUTUBE_KEY="مفتاحك_هنا"
   ```

2. **تشغيل السيرفر:**
   ```bash
   python server.py
   ```

3. **فتح التطبيق:**
   افتح المتصفح على الرابط التالي: `http://localhost:8000`

## ملاحظة أمنية
تم نقل كافة المفاتيح من الكود الأمامي إلى السيرفر الخلفي لحماية خصوصيتك ومنع سرقة حصتك البرمجية. لا تقم أبداً بمشاركة ملفات الكود التي تحتوي على مفاتيحك الخاصة.
