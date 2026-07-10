from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json, urllib.request, urllib.error, os, re, threading, time
from urllib.parse import quote
from html.parser import HTMLParser
from collections import defaultdict, deque

GEMINI_KEY  = os.environ.get("GEMINI_KEY", "")
YOUTUBE_KEY = os.environ.get("YOUTUBE_KEY", "")
# المفتاح لم يعد في الـ URL — يُمرّر عبر Header لتجنّب ظهوره في اللوجات ورسائل الخطأ
GEMINI_URL  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

MAX_QUESTION_LEN = 1000

# ===== Rate Limiting (بسيط، في الذاكرة، لكل IP) =====
RATE_LIMIT_WINDOW = 60   # نافذة زمنية بالثواني
RATE_LIMIT_MAX    = 15   # عدد الطلبات المسموح لكل IP خلال النافذة
_rate_lock = threading.Lock()
_rate_log  = defaultdict(deque)   # ip -> deque of timestamps

def _is_rate_limited(ip):
    now    = time.time()
    cutoff = now - RATE_LIMIT_WINDOW
    with _rate_lock:
        log = _rate_log[ip]
        while log and log[0] < cutoff:        # تجاهل الطوابع القديمة
            log.popleft()
        if len(log) >= RATE_LIMIT_MAX:
            return True
        log.append(now)
        return False


def remove_markdown(text):
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

def extract_youtube_id(url):
    for p in [r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
              r'youtu\.be/([a-zA-Z0-9_-]{11})',
              r'youtube\.com/embed/([a-zA-Z0-9_-]{11})']:
        m = re.search(p, url)
        if m: return m.group(1)
    return ''

def _gemini_call(text, use_search=False):
    """استدعاء Gemini موحّد: عادي أو مع Google Search."""
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
            "x-goog-api-key": GEMINI_KEY,        # المفتاح في Header
        },
        method="POST",
    )
    label = "Gemini Search" if use_search else "Gemini"
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode()
        print(f"{label} API Error: {e.code} - {err_msg}")
        if "API_KEY_INVALID" in err_msg:
            raise Exception("مفتاح Gemini غير صحيح أو منتهي الصلاحية.")
        raise Exception(f"خطأ في {label}: {err_msg}")

def gemini(prompt, system=""):
    return _gemini_call((system + "\n\n" + prompt) if system else prompt, use_search=False)

def gemini_search(prompt, system=""):
    return _gemini_call((system + "\n\n" + prompt) if system else prompt, use_search=True)

def search_youtube(query, max_results=3):
    q = quote(query + " فتوى")
    url = (f"https://www.googleapis.com/youtube/v3/search"
           f"?part=snippet&q={q}&type=video&maxResults={max_results}"
           f"&relevanceLanguage=ar&key={YOUTUBE_KEY}")
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        videos = []
        for item in data.get("items", []):
            # بعض النتائج (قنوات/قوائم) لا تحتوي على videoId
            if "videoId" not in item.get("id", {}):
                continue
            vid_id  = item["id"]["videoId"]
            snippet = item["snippet"]
            videos.append({
                "youtube_id": vid_id,
                "title":      snippet.get("title", ""),
                "channel":    snippet.get("channelTitle", ""),
                "link":       f"https://www.youtube.com/watch?v={vid_id}",
            })
        return videos
    except Exception as e:
        print(f"YouTube error: {e}")
        return []

def understand_question(raw):
    system = """أنت مساعد يفهم الأسئلة الدينية بأي أسلوب عامي أو فصيح.
أجب بهذا الشكل فقط:
QUESTION: [السؤال الفقهي بالعربية الفصحى]
TOPIC: [الموضوع في كلمة أو كلمتين]
SEARCH: [كلمات البحث في يوتيوب مثل: حكم الأكل في رمضان ابن باز]"""
    try:
        text = gemini(raw, system)
        q = re.search(r'QUESTION:\s*(.+)', text)
        t = re.search(r'TOPIC:\s*(.+)',    text)
        s = re.search(r'SEARCH:\s*(.+)',   text)
        return (
            q.group(1).strip() if q else raw,
            t.group(1).strip() if t else '',
            s.group(1).strip() if s else raw
        )
    except Exception as e:
        print(f"Understand error: {e}")
        return raw, '', raw

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

قواعد: لا Markdown - من 2 إلى 3 نتائج - ابحث فعلاً - عربي فصيح بسيط"""
    try:
        return gemini_search(fiqh_q, system)
    except Exception as e:
        print(f"Search error: {e}")
        return ""

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def _client_ip(self):
        """عنوان العميل (مع احترام X-Forwarded-For لو وراء proxy)."""
        fwd = self.headers.get("X-Forwarded-For")
        if fwd:
            return fwd.split(",")[0].strip()
        return self.client_address[0]

    def _send_json(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path != "/ask":
            self._send_json(404, {"error": "غير موجود"})
            return

        # التحقق من المُدخلات
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0 or length > 10000:
            self._send_json(400, {"error": "طلب غير صالح"})
            return
        try:
            body  = json.loads(self.rfile.read(length))
            raw_q = (body.get("question") or "").strip()
        except (json.JSONDecodeError, ValueError):
            self._send_json(400, {"error": "صيغة JSON غير صالحة"})
            return

        if not raw_q:
            self._send_json(400, {"error": "الرجاء كتابة سؤال"})
            return
        if len(raw_q) > MAX_QUESTION_LEN:
            self._send_json(400, {"error": f"السؤال طويل جداً (الحد {MAX_QUESTION_LEN} حرف)"})
            return

        # Rate limiting
        if _is_rate_limited(self._client_ip()):
            self._send_json(429, {"error": "طلبات كثيرة جداً. حاول بعد دقيقة."})
            return

        try:
            print(f"Q: {raw_q}")

            if not GEMINI_KEY:
                raise Exception("لم يتم تعيين GEMINI_KEY في متغيرات البيئة.")

            # الخطوة 1: افهم السؤال
            fiqh_q, topic, yt_search = understand_question(raw_q)
            print(f"Fiqh: {fiqh_q}")

            # الخطوة 2: يوتيوب في thread
            yt_results = []

            def fetch_yt():
                yt_results.extend(search_youtube(yt_search, 3))

            t1 = threading.Thread(target=fetch_yt)
            t1.start()

            # الخطوة 3: ابحث في الفتاوى (Gemini + Google Search)
            full_text = search_fatwas_text(fiqh_q)

            t1.join()

            # parse الفتاوى
            opinions  = []
            for blk in re.findall(r'OPINION_START(.*?)OPINION_END', full_text, re.DOTALL):
                def get(name, b=blk):
                    m = re.search(rf'{name}:\s*(.+)', b)
                    v = m.group(1).strip() if m else ''
                    return '' if v.lower() == 'none' else v
                def get_text(b=blk):
                    m = re.search(r'النص:\s*(.+?)(?=المصدر_النص:|الرابط:|$)', b, re.DOTALL)
                    return m.group(1).strip() if m else ''
                link = get('الرابط')
                opinions.append({
                    "title":      remove_markdown(get('العنوان')),
                    "text":       remove_markdown(get_text()),
                    "source":     remove_markdown(get('المصدر_النص')),
                    "link":       link if link.startswith('http') else '',
                    "youtube_id": '',
                    "type":       "text"
                })

            # أضف فيديوهات
            for v in yt_results:
                opinions.append({
                    "title":      v["title"],
                    "text":       f'فيديو من قناة: {v["channel"]}',
                    "source":     "يوتيوب",
                    "link":       v["link"],
                    "youtube_id": v["youtube_id"],
                    "type":       "video"
                })

            summary_m = re.search(r'SUMMARY_START(.*?)SUMMARY_END', full_text, re.DOTALL)
            summary   = remove_markdown(summary_m.group(1).strip()) if summary_m else ""

            self._send_json(200, {
                "original_question": raw_q,
                "fiqh_question":     fiqh_q,
                "topic":             topic,
                "opinions":          opinions,
                "summary":           summary
            })

        except Exception as e:
            print(f"Error: {e}")
            self._send_json(500, {"error": str(e)})

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

if __name__ == "__main__":
    print("Running on: http://localhost:8000")
    print("Open: http://localhost:8000/index.html")
    # ThreadingHTTPServer: معالجة عدة طلبات بالتوازي بدل طلب واحد في كل مرة
    ThreadingHTTPServer(("", 8000), Handler).serve_forever()
