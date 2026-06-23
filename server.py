from http.server import HTTPServer, SimpleHTTPRequestHandler
import json, urllib.request, urllib.error, os, re, threading
from urllib.parse import quote
from html.parser import HTMLParser

GEMINI_KEY  = os.environ.get("GEMINI_KEY", "")
YOUTUBE_KEY = os.environ.get("YOUTUBE_KEY", "")
GEMINI_URL  = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"

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

def gemini(prompt, system=""):
    """استدعاء Gemini API"""
    contents = []
    if system:
        # Gemini expects system instruction as a separate field or prepended to the first message
        # Prepending is safer for older versions or simple calls
        contents.append({"role": "user", "parts": [{"text": system + "\n\n" + prompt}]})
    else:
        contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = json.dumps({
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 2000, "temperature": 0.3}
    }).encode("utf-8")

    req = urllib.request.Request(
        GEMINI_URL, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode()
        print(f"Gemini API Error: {e.code} - {err_msg}")
        raise Exception(f"Gemini API Error: {err_msg}")

def gemini_search(prompt, system=""):
    """Gemini مع Google Search مدمج"""
    contents = []
    if system:
        contents.append({"role": "user", "parts": [{"text": system + "\n\n" + prompt}]})
    else:
        contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = json.dumps({
        "contents": contents,
        "tools": [{"google_search_retrieval": {}}],
        "generationConfig": {"maxOutputTokens": 3000, "temperature": 0.3}
    }).encode("utf-8")

    req = urllib.request.Request(
        GEMINI_URL, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode()
        print(f"Gemini Search API Error: {e.code} - {err_msg}")
        raise Exception(f"Gemini Search API Error: {err_msg}")

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

def search_dorar(keywords, max_results=3):
    try:
        url = f"http://dorar.net/dorar_api.json?skey={quote(keywords)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=8) as resp:
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
        q = re.search(r'QUESTION:\s*(.+)', text)
        t = re.search(r'TOPIC:\s*(.+)',    text)
        s = re.search(r'SEARCH:\s*(.+)',   text)
        h = re.search(r'HADITH_SEARCH:\s*(.+)', text)
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

قواعد: لا Markdown - من 2 إلى 3 نتائج - ابحث فعلاً - عربي فصيح بسيط"""
    try:
        return gemini_search(fiqh_q, system)
    except Exception as e:
        print(f"Search error: {e}")
        return ""

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path != "/ask":
            self.send_response(404); self.end_headers(); return

        length = int(self.headers.get("Content-Length", 0))
        raw_q  = json.loads(self.rfile.read(length)).get("question", "")

        try:
            print(f"Q: {raw_q}")

            if not GEMINI_KEY:
                raise Exception("API Key Missing: GEMINI_KEY is not set in environment variables.")

            # الخطوة 1: افهم السؤال
            fiqh_q, topic, yt_search, hadith_search = understand_question(raw_q)
            print(f"Fiqh: {fiqh_q}")

            # الخطوة 2: يوتيوب والدرر في threads
            yt_results    = []
            dorar_results = []

            def fetch_yt():
                yt_results.extend(search_youtube(yt_search, 3))
            def fetch_dorar():
                dorar_results.extend(search_dorar(hadith_search, 3))

            t1 = threading.Thread(target=fetch_yt)
            t2 = threading.Thread(target=fetch_dorar)
            t1.start(); t2.start()

            # الخطوة 3: ابحث في الفتاوى (Gemini + Google Search)
            full_text = search_fatwas_text(fiqh_q)

            t1.join(); t2.join()

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

            response_data = json.dumps({
                "original_question": raw_q,
                "fiqh_question":     fiqh_q,
                "topic":             topic,
                "opinions":          opinions,
                "summary":           summary,
                "hadiths":           dorar_results
            }, ensure_ascii=False).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response_data)

        except Exception as e:
            print(f"Error: {e}")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

if __name__ == "__main__":
    print("Running on: http://localhost:8000")
    print("Open: http://localhost:8000/index.html")
    HTTPServer(("", 8000), Handler).serve_forever()
