import json
import urllib.request
import os
import re
import threading
import time
from urllib.parse import quote
from html.parser import HTMLParser
from collections import defaultdict, deque

GEMINI_KEY  = os.environ.get("AQ.Ab8RN6L-MIe7WP1HVy9G1DqR5Rt5dAPgdCX3c4hGJbbOOfrUmg")
YOUTUBE_KEY = os.environ.get("AIzaSyB4-e-z1mhX7t3pxmIEjlbqoz15nsqkngk")
GEMINI_URL  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

MAX_QUESTION_LEN = 1000

def remove_markdown(text):
    if not text: return ''
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\*(.*?)\*', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'__(.*?)__', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'_(.*?)_', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'`{1,3}.*?`{1,3}', '', text, flags=re.DOTALL)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'-{3,}', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, d):
        self.parts.append(d)
    def get_text(self):
        return ' '.join(self.parts)

def strip_html(html):
    s = HTMLStripper()
    s.feed(html)
    return s.get_text().strip()

def _gemini_call(text, use_search=False):
    payload_obj = {
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"maxOutputTokens": 3000 if use_search else 2000, "temperature": 0.3},
    }
    if use_search:
        payload_obj["tools"] = [{"google_search_retrieval": {}}]

    payload = json.dumps(payload_obj).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_URL,
        data=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    return result["candidates"][0]["content"]["parts"][0]["text"]

def gemini(prompt, system=""):
    return _gemini_call((system + "\n\n" + prompt) if system else prompt)

def gemini_search(prompt, system=""):
    return _gemini_call((system + "\n\n" + prompt) if system else prompt, True)

def search_youtube(query, max_results=3):
    if not YOUTUBE_KEY: return []
    q = quote(query + " فتوى")
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={q}&type=video&maxResults={max_results}&relevanceLanguage=ar&key={YOUTUBE_KEY}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        videos = []
        for item in data.get("items", []):
            if "videoId" not in item.get("id", {}): continue
            vid_id = item["id"]["videoId"]
            snippet = item["snippet"]
            videos.append({
                "youtube_id": vid_id,
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "link": f"https://www.youtube.com/watch?v={vid_id}",
            })
        return videos
    except:
        return []

def search_dorar(keywords, max_results=3):
    try:
        url = f"http://dorar.net/dorar_api.json?skey={quote(keywords)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        results_html = data.get("ahadith", {}).get("result", "")
        if not results_html: return []
        hadiths = []
        texts = re.split(r'</?div[^>]*>|<br\s*/?>', results_html)
        for t in texts:
            clean = strip_html(t).strip()
            if len(clean) > 40:
                grade = ''
                gm = re.search(r'(صحيح|حسن|ضعيف|موضوع)', clean)
                if gm: grade = gm.group(1)
                hadiths.append({"text": clean, "grade": grade})
            if len(hadiths) >= max_results: break
        return hadiths
    except:
        return []

def understand_question(raw):
    system = """أجب بهذا الشكل فقط:
QUESTION: [السؤال الفقهي]
SEARCH: [كلمات بحث يوتيوب]
HADITH_SEARCH: [كلمات بحث أحاديث]"""
    try:
        text = gemini(raw, system)
        q = re.search(r'QUESTION:\s*(.+)', text, re.DOTALL)
        s = re.search(r'SEARCH:\s*(.+)', text, re.DOTALL)
        h = re.search(r'HADITH_SEARCH:\s*(.+)', text, re.DOTALL)
        return q.group(1).strip() if q else raw, s.group(1).strip() if s else raw, h.group(1).strip() if h else raw
    except:
        return raw, raw, raw

def search_fatwas_text(fiqh_q):
    system = """أجب على السؤال بفتاوى موثوقة بهذا التنسيق بالظبط:

OPINIONS_START
OPINION_START
العنوان: islamqa
النص: [ملخص الفتوى]
المصدر_النص: islamqa.info
الرابط: https://islamqa.info/...
OPINION_END
OPINIONS_END

SUMMARY_START
[الخلاصة العملية]
SUMMARY_END"""
    try:
        return gemini_search(fiqh_q, system)
    except:
        return ""

def handler(request):
    if request.method == "OPTIONS":
        return {"statusCode": 200, "headers": {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type"}}

    try:
        body = json.loads(request.body.decode('utf-8'))
        raw_q = (body.get("question") or "").strip()

        if not raw_q or len(raw_q) > MAX_QUESTION_LEN:
            return {"statusCode": 400, "body": json.dumps({"error": "سؤال غير صالح"})}

        if not GEMINI_KEY:
            return {"statusCode": 500, "body": json.dumps({"error": "GEMINI_KEY غير معرف"})}

        fiqh_q, yt_search, hadith_search = understand_question(raw_q)

        yt_results = []
        dorar_results = []

        def fetch_yt():
            nonlocal yt_results
            yt_results.extend(search_youtube(yt_search))
        def fetch_dorar():
            nonlocal dorar_results
            dorar_results.extend(search_dorar(hadith_search))

        t1 = threading.Thread(target=fetch_yt)
        t2 = threading.Thread(target=fetch_dorar)
        t1.start(); t2.start()

        full_text = search_fatwas_text(fiqh_q)

        t1.join(timeout=15)
        t2.join(timeout=15)

        opinions = []
        for blk in re.findall(r'OPINION_START(.*?)OPINION_END', full_text, re.DOTALL):
            def get(name):
                m = re.search(rf'{name}:\s*(.+?)(?=\n[A-Z]|$)', blk, re.DOTALL)
                return m.group(1).strip() if m else ''
            opinions.append({
                "title": remove_markdown(get('العنوان')),
                "text": remove_markdown(get('النص')),
                "source": remove_markdown(get('المصدر_النص')),
                "link": get('الرابط') if get('الرابط').startswith('http') else '',
                "type": "text"
            })

        for v in yt_results:
            opinions.append({**v, "type": "video", "source": "يوتيوب"})

        summary_m = re.search(r'SUMMARY_START(.*?)SUMMARY_END', full_text, re.DOTALL)
        summary = remove_markdown(summary_m.group(1).strip()) if summary_m else ""

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "original_question": raw_q,
                "fiqh_question": fiqh_q,
                "opinions": opinions,
                "summary": summary,
                "hadiths": dorar_results
            }, ensure_ascii=False)
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": str(e)})
        }
