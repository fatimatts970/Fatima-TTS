from flask import Flask, request, jsonify, send_from_directory, session, redirect, render_template_string
import os
import asyncio
import edge_tts
import random
import time
import hmac
import json
import requests
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fatima-tts-dev-secret-change-me")

PORT = int(os.environ.get("PORT", 10000))
BASE_DIR = "/tmp"
HTML_DIR = os.getcwd()

UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
ONLINE_TTL_SECONDS = 30

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


# ---------- Upstash Redis helper ----------
def redis_command(*args):
    if not UPSTASH_URL or not UPSTASH_TOKEN:
        print("REDIS_DEBUG: URL or TOKEN missing!")
        return None
    try:
        resp = requests.post(
            UPSTASH_URL,
            json=list(args),
            headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("result")
    except Exception as e:
        print(f"REDIS_DEBUG: command={args[0] if args else '?'} error={e}")
        return None


# ---------- Visitor tracking & IP blocking ----------
def get_client_ip():
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"


def lookup_location(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,city", timeout=3)
        data = r.json()
        if data.get("status") == "success":
            city = data.get("city") or ""
            country = data.get("country") or ""
            return f"{city}, {country}".strip(", ")
    except Exception:
        pass
    return "Unknown"


def log_visitor(ip):
    existing = redis_command("HGET", "visitors", ip)
    now = int(time.time())
    if existing:
        try:
            record = json.loads(existing)
        except Exception:
            record = {"first_seen": now, "location": "Unknown"}
        record["last_seen"] = now
        record["visits"] = record.get("visits", 0) + 1
    else:
        record = {
            "first_seen": now,
            "last_seen": now,
            "visits": 1,
            "location": lookup_location(ip),
        }
    redis_command("HSET", "visitors", ip, json.dumps(record))


def is_ip_blocked(ip):
    result = redis_command("SISMEMBER", "blocked_ips", ip)
    return result == 1


def get_all_visitors():
    raw = redis_command("HGETALL", "visitors")
    visitors = []
    if isinstance(raw, list):
        for i in range(0, len(raw), 2):
            ip = raw[i]
            try:
                record = json.loads(raw[i + 1])
            except Exception:
                record = {}
            record["ip"] = ip
            visitors.append(record)
    visitors.sort(key=lambda v: v.get("last_seen", 0), reverse=True)
    return visitors


def get_blocked_set():
    result = redis_command("SMEMBERS", "blocked_ips")
    return set(result) if isinstance(result, list) else set()


@app.before_request
def enforce_block_and_log():
    if request.path.startswith("/admin") or request.path.startswith("/static"):
        return
    ip = get_client_ip()
    if is_ip_blocked(ip):
        return "Access denied.", 403
    if request.path in ("/", "/generate", "/preview"):
        log_visitor(ip)


# ---------- Admin auth ----------
def admin_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper


ADMIN_LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Login - Fatima TTS</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
<style>body{font-family:'Poppins',sans-serif;background:linear-gradient(180deg,#155dfc 0%,#0a46c8 100%);min-height:100vh;}</style>
</head>
<body class="flex items-center justify-center p-6">
  <div class="w-full max-w-sm bg-white/10 border border-white/20 rounded-2xl p-6 backdrop-blur">
    <h1 class="text-white text-xl font-bold mb-1">Admin Login</h1>
    <p class="text-white/60 text-xs mb-5">Fatima TTS Studio control panel</p>
    {% if error %}<div class="bg-red-500/20 border border-red-400/40 text-red-100 text-xs rounded-lg p-2.5 mb-4">{{ error }}</div>{% endif %}
    <form method="POST" class="space-y-3">
      <div class="flex gap-2 mb-2">
        <label class="flex-1 text-xs text-white/80"><input type="radio" name="method" value="email" checked class="mr-1"> Email</label>
        <label class="flex-1 text-xs text-white/80"><input type="radio" name="method" value="phone" class="mr-1"> Phone</label>
      </div>
      <input type="text" name="identifier" placeholder="Email or Pakistani phone number" required
        class="w-full px-4 py-3 bg-black/20 border border-white/20 rounded-xl text-white placeholder-white/40 text-sm focus:outline-none focus:border-white">
      <input type="password" name="password" placeholder="Password" required
        class="w-full px-4 py-3 bg-black/20 border border-white/20 rounded-xl text-white placeholder-white/40 text-sm focus:outline-none focus:border-white">
      <button type="submit" class="w-full py-3 bg-white text-[#155dfc] font-bold rounded-xl text-sm">Login</button>
    </form>
  </div>
</body>
</html>
"""

ADMIN_DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Panel - Fatima TTS</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>body{font-family:'Poppins',sans-serif;background:linear-gradient(180deg,#155dfc 0%,#0a46c8 100%);min-height:100vh;}</style>
</head>
<body class="p-4 md:p-6">
  <div class="max-w-2xl mx-auto">
    <div class="flex items-center justify-between mb-5">
      <h1 class="text-white text-lg font-bold">Visitor Control Panel</h1>
      <a href="/admin/logout" class="text-white/70 text-xs bg-white/10 border border-white/20 rounded-full px-3 py-1.5">Logout</a>
    </div>

    <div class="space-y-2.5">
      {% for v in visitors %}
      <div class="bg-white/10 border border-white/20 rounded-xl p-3.5 flex items-center justify-between">
        <div class="min-w-0">
          <p class="text-white text-sm font-semibold">{{ v.ip }}</p>
          <p class="text-white/60 text-xs mt-0.5"><i class="fa-solid fa-location-dot mr-1"></i>{{ v.location or 'Unknown' }}</p>
          <p class="text-white/40 text-[10px] mt-0.5">{{ v.visits or 1 }} visit(s)</p>
        </div>
        <form method="POST" action="{{ '/admin/unblock' if v.ip in blocked else '/admin/block' }}">
          <input type="hidden" name="ip" value="{{ v.ip }}">
          <button type="submit" class="text-xs font-bold rounded-lg px-3 py-2 {{ 'bg-green-500 text-white' if v.ip in blocked else 'bg-red-500 text-white' }}">
            {{ 'Unblock' if v.ip in blocked else 'Block' }}
          </button>
        </form>
      </div>
      {% else %}
      <p class="text-white/50 text-sm text-center py-10">No visitors logged yet.</p>
      {% endfor %}
    </div>
  </div>
</body>
</html>
"""


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        password = request.form.get("password") or ""
        valid_id = (identifier == ADMIN_EMAIL and ADMIN_EMAIL) or (identifier == ADMIN_PHONE and ADMIN_PHONE)
        valid_pw = ADMIN_PASSWORD and hmac.compare_digest(password, ADMIN_PASSWORD)
        if valid_id and valid_pw:
            session["is_admin"] = True
            return redirect("/admin")
        error = "Invalid email/phone or password."
    return render_template_string(ADMIN_LOGIN_HTML, error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login")


@app.route("/admin")
@admin_login_required
def admin_dashboard():
    visitors = get_all_visitors()
    blocked = get_blocked_set()
    return render_template_string(ADMIN_DASHBOARD_HTML, visitors=visitors, blocked=blocked)


@app.route("/admin/block", methods=["POST"])
@admin_login_required
def admin_block():
    ip = request.form.get("ip", "").strip()
    if ip:
        redis_command("SADD", "blocked_ips", ip)
    return redirect("/admin")


@app.route("/admin/unblock", methods=["POST"])
@admin_login_required
def admin_unblock():
    ip = request.form.get("ip", "").strip()
    if ip:
        redis_command("SREM", "blocked_ips", ip)
    return redirect("/admin")


# ---------- Online users heartbeat ----------
@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    data = request.json or {}
    sid = str(data.get("session_id") or "")[:64]
    if not sid:
        return jsonify({"success": False, "count": 1}), 400
    redis_command("SET", f"online:{sid}", "1", "EX", str(ONLINE_TTL_SECONDS))
    keys = redis_command("KEYS", "online:*")
    count = len(keys) if isinstance(keys, list) else 1
    return jsonify({"success": True, "count": max(count, 1)})


# ---------- TTS core ----------
def cleanup_tmp():
    now = time.time()
    try:
        for file in os.listdir(BASE_DIR):
            if file.endswith(".mp3"):
                path = os.path.join(BASE_DIR, file)
                try:
                    if os.path.isfile(path) and now - os.path.getmtime(path) > 600:
                        os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass


async def generate_voice_async(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


@app.route('/')
def index():
    return send_from_directory(HTML_DIR, 'index.html')


@app.route('/preview', methods=['POST'])
def preview():
    cleanup_tmp()
    data = request.json or {}
    voice = data.get('voice', 'ur-PK-UzmaNeural')
    if voice.startswith(("ur-PK", "ur-IN")):
        preview_text = "فاطمہ ٹی ٹی ایس اسٹوڈیو میں آپ کا خوش آمدید ہے۔"
    elif voice.startswith("hi-IN"):
        preview_text = "फ़ातिमा टीटीएस स्टूडियो में आपका स्वागत है।"
    elif voice.startswith("en-"):
        preview_text = "Welcome to the Fatima T.T.S. Studio."
    elif voice.startswith("es-"):
        preview_text = "Bienvenido a Fatima T.T.S. Studio."
    elif voice.startswith("ar-"):
        preview_text = "مرحباً بكم في استوديو فاطمة للأصوات."
    elif voice.startswith("af-"):
        preview_text = "Welkom by Fatima T.T.S. Studio."
    elif voice.startswith("he-"):
        preview_text = "ברוכים הבאים לסטודיו פאטימה."
    else:
        preview_text = "Welcome to Fatima TTS Studio."
    output_file = f"preview-{voice}.mp3"
    output_path = os.path.join(BASE_DIR, output_file)
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass
    try:
        asyncio.run(generate_voice_async(preview_text, voice, output_path))
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return jsonify({"success": True, "audio_url": f"/download/{output_file}?v={os.urandom(4).hex()}"})
        return jsonify({"success": False, "error": "Zero-byte file generated."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/generate', methods=['POST'])
def generate():
    cleanup_tmp()
    data = request.json or {}
    text = data.get('text', '').strip()
    voice = data.get('voice', 'ur-PK-UzmaNeural')
    if not text:
        return jsonify({"success": False, "error": "Script is empty!"})
    if len(text) > 100000:
        return jsonify({"success": False, "error": "Maximum limit is 100000 characters."})
    random_num = random.randint(100000000000000000, 999999999999999999)
    output_file = f"FatimaTTS-{random_num}.mp3"
    output_path = os.path.join(BASE_DIR, output_file)
    try:
        asyncio.run(generate_voice_async(text, voice, output_path))
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return jsonify({"success": True, "audio_url": f"/download/{output_file}?v={os.urandom(4).hex()}", "filename": output_file})
        return jsonify({"success": False, "error": "Server failed to process TTS."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/stop', methods=['POST'])
def stop():
    return jsonify({"success": True})


@app.route('/download/<filename>')
def download_file(filename):
    cleanup_tmp()
    filename = secure_filename(filename)
    return send_from_directory(BASE_DIR, filename, as_attachment=False)


@app.route("/about")
def about():
    return send_from_directory(HTML_DIR, "about.html")


@app.route("/privacy")
def privacy():
    return send_from_directory(HTML_DIR, "privacy.html")


@app.route("/terms")
def terms():
    return send_from_directory(HTML_DIR, "terms.html")


@app.route("/contact")
def contact():
    return send_from_directory(HTML_DIR, "contact.html")


@app.route("/robots.txt")
def robots():
    return send_from_directory(HTML_DIR, "robots.txt")


@app.route("/sitemap.xml")
def sitemap():
    return send_from_directory(HTML_DIR, "sitemap.xml")


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(HTML_DIR, "favicon.ico")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
