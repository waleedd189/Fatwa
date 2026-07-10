def search_fatwas_text(fiqh_q):
    system = """أنت خبير فقه إسلامي. أجب على السؤال التالي باختصار ووضوح.

السؤال: """ + fiqh_q + """

أرجع النتيجة بهذا التنسيق بالظبط:

OPINIONS_START
OPINION_START
العنوان: islamqa.info
النص: [ملخص الفتوى في جملتين أو ثلاث]
المصدر_النص: islamqa
الرابط: https://islamqa.info/ar/answers/...
OPINION_END
OPINIONS_END

SUMMARY_START
[خلاصة عملية مباشرة]
SUMMARY_END"""
    
    try:
        return gemini_search(fiqh_q, system)
    except Exception as e:
        print("Search failed:", e)
        return "OPINIONS_START OPINION_START العنوان: خطأ النص: لم أتمكن من جلب فتوى مكتوبة OPINION_END OPINIONS_END SUMMARY_START حاول مرة أخرى SUMMARY_END"
