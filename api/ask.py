from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import os
import re
import threading
import time
from urllib.parse import quote
from html.parser import HTMLParser
from collections import defaultdict, deque

GEMINI_KEY  = os.environ.get("GEMINI_KEY", "")
YOUTUBE_KEY = os.environ.get("YOUTUBE_KEY", "")
GEMINI_URL  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

MAX_QUESTION_LEN = 1000

# Rate Limiting
_rate_lock = threading.Lock()
_rate_log  = defaultdict(deque)

def _is_rate_limited(ip):
    now    = time.time()
    cutoff = now - 60
    with _rate_lock:
        log = _rate_log[ip]
        while log and log[0] < cutoff:
            log.popleft()
        if len(log) >= 15:
            return True
        log.append(now)
        return False

def remove_markdown(text):
    if not text:
        return ''
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\*(.*?)\*',   r'\1', text, flags=re.DOTALL)
    text = re.sub(r'__(.*?)__',   r'\1', text, flags=re.DOTALL)
    text = re.sub(r'_(.*?)_',     r'\1', text, flags=re.DOTALL)
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
        "generationConfig": {
            "maxOutputTokens": 3000 if use_search else 2000,
            "temperature": 0.3,
        },
    }
    if use_search:
        payload_obj["tools"] = [{"google_search_retrieval": {}}]

    payload = json.dumps(payload_obj).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            result = json.loads(resp.read())
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"Gemini Error: {e}")
        raise Exception("خطأ في Gemini - تأكد من المفتاح")

def gemini(prompt, system=""):
    return _gemini_call((system + "\n\n" + prompt) if system else prompt, use_search=False)

def gemini_search(prompt, system=""):
    return _gemini_call((system + "\n\n" + prompt) if system else prompt, use_search=True)

def search_youtube(query, max_results=3):
    if not YOUTUBE_KEY:
        return []
    q = quote(query + " فتوى")
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={q}&type=video&maxResults={max_results}&relevanceLanguage=ar&key={YOUTUBE_KEY}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        videos = []
        for item in data.get("items", []):
            if "videoId" not in item.get("id", {}):
                continue
            vid_id = item["id"]["videoId"]
            snippet = item["snippet"]
            videos.append({
                "youtube_id": vid_id,
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "link": f"https://www.youtube.com/watch?v={vid_id}",
            })
        return videos
    except Exception as e:
        print(f"YouTube error: {e}")
        return []

def search_dorar(keywords, max_results=3):
    try:
        url = f"http://dorar.net/dorar_api.json?skey={quote(keywords)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        results_html = data.get("ahadith", {}).get("result", "")
        if not results_html:
            return []
        hadiths = []
        texts = re.split(r'</?div[^>]*>|<br\s*/?>', results_html)
        for t in texts:
            clean = strip_html(t).strip()
            if len(clean) > 40:
                grade = ''
                gm = re.search(r'(صحيح|حسن|ضعيف|موضوع)', clean)
                if gm: grade = gm.group(1)
                hadiths.append({"text": clean, "grade": grade})
            if len(hadiths) >= max_results:
                break
        return hadiths
    except Exception as e:
        print(f"Dorar error: {e}")
        return []

def understand_question(raw):
    system = """أنت مساعد يفهم الأسئلة الدينية بأي أسلوب عامي أو فصيح.
أجب بهذا الشكل فقط:
QUESTION: [السؤال الفقهي بالعربية الفصحى]
TOPIC: [الموضوع في كلمة أو كلمتين]
SEARCH: [كلمات البحث في يوتيوب مثل: حكم الأكل في رمضان ابن باز]
HADITH_SEARCH: [كلمات للبحث في الأحاديث مثل: الصيام رمضان]"""
    try:
        text = gemini(raw, system)
        q = re.search(r'QUESTION:\s*(.+)', text, re.DOTALL)
        t = re.search(r'TOPIC:\s*(.+)', text, re.DOTALL)
        s = re.search(r'SEARCH:\s*(.+)', text, re.DOTALL)
        h = re.search(r'HADITH_SEARCH:\s*(.+)', text, re.DOTALL)
        return (
            q.group(1).strip() if q else raw,
            t.group(1).strip() if t else '',
            s.group(1).strip() if s else raw,
            h.group(1).strip() if h else raw
        )
    except Exception as e:
        print(f"Understand error: {e}")
        return raw, '', raw, raw

def search_fatwas_text(fiqh_q):
    system = """أنت مساعد متخصص في الفقه الإسلامي.
ابحث على الإنترنت عن فتاوى للسؤال من مواقع موثوقة مثل islamqa.info أو dar-alifta.org أو dorar.net أو islamweb.net

قدّم النتائج بهذا الشكل:
OPINIONS_START
OPINION_START
العنوان: [اسم الموقع أو العالم]
النص: [ملخص الفتوى في 2-3 جمل]
المصدر_النص: [اسم الموقع]
الرابط: [رابط الصفحة أو none]
OPINION_END
OPINIONS_END

SUMMARY_START
[خلاصة عملية في جملة أو جملتين]
SUMMARY_END

قواعد: لا Markdown - من 2 إلى 3 نتائج - عربي فصيح بسيط"""
    try:
        return gemini_search(fiqh_q, system)
    except Exception as e:
        print(f"Search error: {e}")
        return ""

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

    def do_POST(self):
        if self.path not in ["/ask", "/api/ask"]:
            self.send_response(404)
            self.end_headers()
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 10000 or length == 0:
                self.send_response(400)
                self.end_headers()
                return

            body = json.loads(self.rfile.read(length).decode('utf-8'))
            raw_q = (body.get("question") or "").strip()

            if not raw_q or len(raw_q) > MAX_QUESTION_LEN:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "السؤال غير صالح"}).encode())
                return

            if _is_rate_limited(self.headers.get("X-Forwarded-For", "unknown").split(',')[0]):
                self.send_response(429)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "طلبات كثيرة"}).encode())
                return

            if not GEMINI_KEY:
                raise Exception("GEMINI_KEY غير معرف في Vercel")

            fiqh_q, topic, yt_search, hadith_search = understand_question(raw_q)

            yt_results = []
            dorar_results = []

            def fetch_yt():
                yt_results.extend(search_youtube(yt_search, 3))
            def fetch_dorar():
                dorar_results.extend(search_dorar(hadith_search, 3))

            t1 = threading.Thread(target=fetch_yt)
            t2 = threading.Thread(target=fetch_dorar)
            t1.start()
            t2.start()

            full_text = search_fatwas_text(fiqh_q)

            t1.join(timeout=12)
            t2.join(timeout=12)

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
                    "youtube_id": '',
                    "type": "text"
                })

            for v in yt_results:
                opinions.append({
                    "title": v["title"],
                    "text": f'فيديو من قناة: {v["channel"]}',
                    "source": "يوتيوب",
                    "link": v["link"],
                    "youtube_id": v["youtube_id"],
                    "type": "video"
                })

            summary_m = re.search(r'SUMMARY_START(.*?)SUMMARY_END', full_text, re.DOTALL)
            summary = remove_markdown(summary_m.group(1).strip()) if summary_m else ""

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "original_question": raw_q,
                "fiqh_question": fiqh_q,
                "opinions": opinions,
                "summary": summary,
                "hadiths": dorar_results
            }, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            print(f"Error: {e}")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()