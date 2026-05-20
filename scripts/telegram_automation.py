"""
Telegram Automation Bot - Told By Nova
Full pipeline: story -> voice -> clips -> build -> preview -> YouTube upload
"""
import os, sys, json, time, re, subprocess, random, hashlib, shutil, threading
import urllib.request, urllib.error


PROJECT = os.environ.get("NOVA_PROJECT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ENV = {}
_env_path = os.path.join(PROJECT, "assets", "channel", ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _ENV[_k.strip()] = _v.strip()

ASSETS = f"{PROJECT}/assets"
CLIPS_DIR = f"{ASSETS}/clips_manual"
DEFAULT_CLIPS_DIR = f"{ASSETS}/clips_default"
OUTPUT = f"{PROJECT}/output"
DATA_DIR = f"{PROJECT}/data"
SCRIPTS = f"{PROJECT}/scripts"
SUBSCRIBE_VID = f"{ASSETS}/subscribe.mp4"
BGM_DIR = f"{ASSETS}/bgm"

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
OLLAMA_API = os.environ.get("OLLAMA_API", "https://api.ollama.com/api/chat")
OLLAMA_KEY = os.environ.get("OLLAMA_API_KEY", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:31b-cloud")

_last_ai_source = "Ollama"
_ollama_last_call = 0
_ollama_calls_minute = []
OLLAMA_MIN_GAP = 5
OLLAMA_MAX_PER_MINUTE = 5

HISTORY_FILE = f"{DATA_DIR}/story_history.json"
SCHEDULE_FILE = f"{DATA_DIR}/upload_schedule.json"
URL_HISTORY = f"{CLIPS_DIR}/.url_history.json"
STATE_FILE = f"{DATA_DIR}/bot_state.json"
USERS_FILE = f"{DATA_DIR}/allowed_users.json"
NOTIFY_FILE = f"{DATA_DIR}/slot_notifications.json"
JOBS_FILE = f"{DATA_DIR}/pending_jobs.json"
ELEVENLABS_CONFIG = f"{DATA_DIR}/elevenlabs_config.json"
GDRIVE_TOKEN_FILE = f"{DATA_DIR}/gdrive_token.json"

# YT Shorts max 3 min, optimal 35-60s for stories
MAX_DURATION = 180

# USA peak: Shorts 12-1 PM + 7-9 PM EDT
# Sources: SocialPilot (301K vids), Buffer (1.8M vids), IQFluence (325 campaigns),
# Sprout Social, HopperHQ — upload 2-3 hrs before peak for algorithm indexing
UPLOAD_SLOTS_IST = [
    ("11:30 PM", "02:00 PM EDT"),   # afternoon
    ("02:30 AM", "05:00 PM EDT"),   # pre-evening — algorithm indexes before 7 PM surge
    ("04:30 AM", "07:00 PM EDT"),   # evening prime — peak Shorts feed + mobile scrolling
    ("06:30 AM", "09:00 PM EDT"),   # late evening scroll — post-dinner relaxation peak
]


os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CLIPS_DIR, exist_ok=True)
os.makedirs(OUTPUT, exist_ok=True)

# ============ STATE MANAGEMENT ============

_data_io_lock = threading.RLock()

def load_json(path, default=None):
    with _data_io_lock:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default if default is not None else {}

def save_json(path, data):
    with _data_io_lock:
        tmp = path + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

def _sanitize_saved_seo(seo):
    """Auto-fix pre-saved SEO data on load — strips #, caps tags, cleans title."""
    if not seo or not isinstance(seo, dict):
        return seo
    title = seo.get('yt_title', '')
    if title:
        title = re.sub(r'#\w+', '', title).strip()
        title = re.sub(r'[^\x00-\x7F]', '', title)
        title = re.sub(r'\s{2,}', ' ', title).strip()
        title = title.strip('—–-_ .')[:60]
        seo['yt_title'] = title
    desc = seo.get('description', '')
    if desc:
        hashtags = re.findall(r'#\w+', desc)
        if len(hashtags) > 3:
            for ht in hashtags[3:]:
                desc = desc.replace(ht, '', 1)
        desc = re.sub(r'[ \t]{2,}', ' ', desc)
        desc = re.sub(r'\n{3,}', '\n\n', desc).strip()
        seo['description'] = desc
    tags = seo.get('tags', '')
    if tags:
        if isinstance(tags, list):
            tags = ','.join(tags)
        parts = [t.strip().strip('#').strip() for t in tags.split(',') if t.strip()]
        clean, total, seen = [], 0, set()
        for t in parts:
            t = re.sub(r'[<>]', '', t)
            if not t or len(t) > 100 or t.lower() in seen:
                continue
            if len(clean) >= 20 or total + len(t) + 1 > 480:
                break
            seen.add(t.lower())
            clean.append(t)
            total += len(t) + 1
        seo['tags'] = ','.join(clean)
    return seo


class BotState:
    def __init__(self):
        self.state = "IDLE"
        self.current_story = None
        self.current_script = None
        self.voice_mp3 = None
        self.srt_file = None
        self.video_path = None
        self.video_details = None
        self.video_id_counter = 0
        self.clips_count = 0
        self.mood = None
        self.trim_clips = True
        self.max_duration = 0
        self._clip_status_msg = None
        self.short_seo = None
        self.clip_suggestions = None
        self.load()

    def load(self):
        d = load_json(STATE_FILE, {})
        self.state = d.get("state", "IDLE")
        self.current_story = d.get("current_story")
        self.current_script = d.get("current_script")
        self.voice_mp3 = d.get("voice_mp3")
        self.srt_file = d.get("srt_file")
        self.video_path = d.get("video_path")
        self.video_details = d.get("video_details")
        self.video_id_counter = d.get("video_id_counter", 0)
        self.mood = d.get("mood")
        self.trim_clips = d.get("trim_clips", True)
        self.max_duration = d.get("max_duration", 0)
        self.short_seo = _sanitize_saved_seo(d.get("short_seo"))
        self.clip_suggestions = d.get("clip_suggestions")

    def save(self):
        save_json(STATE_FILE, {
            "state": self.state,
            "current_story": self.current_story,
            "current_script": self.current_script,
            "voice_mp3": self.voice_mp3,
            "srt_file": self.srt_file,
            "video_path": self.video_path,
            "video_details": self.video_details,
            "video_id_counter": self.video_id_counter,
            "mood": self.mood,
            "trim_clips": self.trim_clips,
            "max_duration": self.max_duration,
            "short_seo": self.short_seo,
            "clip_suggestions": self.clip_suggestions,
        })

    def reset_for_new_video(self):
        self.state = "IDLE"
        self.current_story = None
        self.current_script = None
        self.voice_mp3 = None
        self.srt_file = None
        self.video_path = None
        self.video_details = None
        self.mood = None
        self._clip_status_msg = None
        self.max_duration = 0
        self.short_seo = None
        self.clip_suggestions = None
        self.save()

bot = BotState()

# ============ STOP SYSTEM ============

_stop_flag = False
_stop_watcher = None

class StopWatcher:
    """Background thread that polls Telegram for /stop while a long operation runs."""
    def __init__(self):
        self.running = False
        self.thread = None

    def start(self):
        global _stop_flag
        _stop_flag = False
        self.running = True
        self.thread = threading.Thread(target=self._poll, daemon=True)
        self.thread.start()

    def _poll(self):
        global _stop_flag, last_update
        while self.running:
            time.sleep(1.5)
            if not self.running:
                break
            try:
                updates = api_call("getUpdates", {"offset": last_update + 1, "timeout": 1}, timeout=5)
                for update in updates.get("result", []):
                    last_update = update["update_id"]
                    msg = update.get("message", {})
                    txt = msg.get("text", "").strip().lower()
                    cb = update.get("callback_query")
                    if cb:
                        answer_callback(cb["id"])
                        txt = cb.get("data", "").strip().lower()
                    if txt == "/stop":
                        _stop_flag = True
                        self.running = False
                        return
            except:
                pass

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)


def is_stopped():
    return _stop_flag

# ============ INSTANCE LOCK + DATA SYNC ============

_instance_lock_violated = False
_lock_system_name = None
_lock_local_ips = set()
_gdrive_auth_pending = False
_gdrive_auth_flow = None
_last_data_hashes = {}
_drive_folder_id = None

def _load_lock_config():
    doc_url = _ENV.get("lock_doc", "")
    doc_id = ""
    if "/d/" in doc_url:
        doc_id = doc_url.split("/d/")[1].split("/")[0]
    interval = int(_ENV.get("lock_check_interval", "5"))
    systems = {}
    for k, v in _ENV.items():
        if k.startswith("system_"):
            name = k[7:]
            systems[name] = [ip.strip() for ip in v.split(",") if ip.strip()]
    return {"doc_id": doc_id, "systems": systems, "check_interval": interval}

def _detect_system_name():
    import socket
    cfg = _load_lock_config()
    systems = cfg.get("systems", {})
    local_ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                local_ips.add(ip)
    except:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ips.add(s.getsockname()[0])
        s.close()
    except:
        pass
    for sys_name, ips in systems.items():
        if local_ips & set(ips):
            return sys_name, local_ips
    return "UNKNOWN", local_ips

_last_doc_error = None
def _read_doc_status():
    global _last_doc_error
    cfg = _load_lock_config()
    doc_id = cfg.get("doc_id", "")
    if not doc_id:
        return {}
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode("utf-8-sig", errors="ignore").strip()
        status = {}
        for line in text.replace("\r", "").split("\n"):
            line = line.strip()
            if "=" in line:
                parts = line.split("=", 1)
                name = parts[0].strip().upper()
                val = parts[1].strip().upper()
                status[name] = val
            elif ":" in line:
                parts = line.split(":", 1)
                name = parts[0].strip().upper()
                val = parts[1].strip().upper()
                status[name] = val
        if _last_doc_error:
            print(f"[LOCK] Doc read recovered")
            _last_doc_error = None
        return status
    except Exception as e:
        err_key = str(e)
        if err_key != _last_doc_error:
            print(f"[LOCK] Doc read failed: {e}")
            _last_doc_error = err_key
        return None

def _check_instance_lock():
    global _lock_system_name, _lock_local_ips
    _lock_system_name, _lock_local_ips = _detect_system_name()
    print(f"[LOCK] Detected: {_lock_system_name} ({', '.join(_lock_local_ips)})")
    status = _read_doc_status()
    if status is None:
        print("[LOCK] Could not read doc — starting without lock")
        return True
    if not status:
        print("[LOCK] Doc empty — starting without lock")
        return True
    my_status = status.get(_lock_system_name, "").upper()
    if my_status == "ON":
        print(f"[LOCK] Doc says {_lock_system_name}: ON — starting")
        return True
    elif my_status == "OFF":
        print(f"[LOCK] Doc says {_lock_system_name}: OFF — NOT starting")
        return False
    else:
        print(f"[LOCK] No entry for {_lock_system_name} in doc — starting without lock")
        return True

def _lock_watcher_loop():
    global _instance_lock_violated
    cfg = _load_lock_config()
    interval = cfg.get("check_interval", 5)
    fail_count = 0
    while True:
        wait = interval if fail_count < 3 else min(interval * fail_count, 30)
        time.sleep(wait)
        try:
            status = _read_doc_status()
            if status is None:
                fail_count += 1
                continue
            fail_count = 0
            my_status = status.get(_lock_system_name, "").upper()
            if my_status == "OFF":
                print(f"[LOCK] {_lock_system_name}: OFF detected — shutting down!")
                _instance_lock_violated = True
                return
        except:
            fail_count += 1

def _get_drive_client():
    if not os.path.exists(GDRIVE_TOKEN_FILE):
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build as g_build
        td = load_json(GDRIVE_TOKEN_FILE, {})
        if not td.get("refresh_token"):
            return None
        creds = Credentials(
            token=td.get("token"), refresh_token=td["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=td["client_id"], client_secret=td["client_secret"],
            scopes=td.get("scopes", ["https://www.googleapis.com/auth/drive.file"]))
        if creds.expired or not creds.valid:
            creds.refresh(Request())
            td["token"] = creds.token
            save_json(GDRIVE_TOKEN_FILE, td)
        return g_build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"[SYNC] Drive client error: {e}")
        return None

def _ensure_drive_folder(service):
    global _drive_folder_id
    if _drive_folder_id:
        return _drive_folder_id
    try:
        r = service.files().list(
            q="name='ToldByNova_Data' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces="drive", fields="files(id)").execute()
        files = r.get("files", [])
        if files:
            _drive_folder_id = files[0]["id"]
        else:
            meta = {"name": "ToldByNova_Data", "mimeType": "application/vnd.google-apps.folder"}
            folder = service.files().create(body=meta, fields="id").execute()
            _drive_folder_id = folder["id"]
        return _drive_folder_id
    except Exception as e:
        print(f"[SYNC] Folder error: {e}")
        return None

_SYNC_EXCLUDE = {"gdrive_token.json", "bot.log", "bot_stdout.log", "bot_stderr.log", "cli_debug.log"}

def _compute_data_hashes():
    with _data_io_lock:
        hashes = {}
        if not os.path.isdir(DATA_DIR):
            return hashes
        for f in os.listdir(DATA_DIR):
            if not f.endswith(".json") or f in _SYNC_EXCLUDE:
                continue
            path = os.path.join(DATA_DIR, f)
            try:
                with open(path, "rb") as fh:
                    hashes[f] = hashlib.md5(fh.read()).hexdigest()
            except:
                pass
        return hashes

def _sync_to_drive(force=False):
    global _last_data_hashes
    if _instance_lock_violated:
        return
    service = _get_drive_client()
    if not service:
        return
    folder_id = _ensure_drive_folder(service)
    if not folder_id:
        return
    current = _compute_data_hashes()
    if not force:
        changed = {f for f in current if current[f] != _last_data_hashes.get(f)}
        deleted = {f for f in _last_data_hashes if f not in current}
    else:
        changed = set(current.keys())
        deleted = set()
    if not changed and not deleted:
        return
    existing = {}
    try:
        r = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            spaces="drive", fields="files(id, name)").execute()
        for f in r.get("files", []):
            existing[f["name"]] = f["id"]
    except:
        pass
    from googleapiclient.http import MediaFileUpload
    uploaded = 0
    for fname in changed:
        path = os.path.join(DATA_DIR, fname)
        if not os.path.exists(path):
            continue
        try:
            media = MediaFileUpload(path, mimetype="application/json", resumable=False)
            if fname in existing:
                service.files().update(fileId=existing[fname], media_body=media).execute()
            else:
                meta = {"name": fname, "parents": [folder_id]}
                service.files().create(body=meta, media_body=media, fields="id").execute()
            uploaded += 1
        except Exception as e:
            print(f"[SYNC] Upload {fname} failed: {e}")
    if uploaded:
        print(f"[SYNC] Uploaded {uploaded} file(s) to Drive")
    _last_data_hashes = current

def _sync_from_drive():
    service = _get_drive_client()
    if not service:
        print("[SYNC] Drive not authorized — use /auth_drive")
        return 0
    folder_id = _ensure_drive_folder(service)
    if not folder_id:
        return 0
    try:
        r = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            spaces="drive", fields="files(id, name, modifiedTime)").execute()
        files = r.get("files", [])
    except Exception as e:
        print(f"[SYNC] List failed: {e}")
        return 0
    downloaded = 0
    os.makedirs(DATA_DIR, exist_ok=True)
    for f in files:
        fname = f["name"]
        if fname in _SYNC_EXCLUDE or not fname.endswith(".json"):
            continue
        path = os.path.join(DATA_DIR, fname)
        if os.path.exists(path):
            try:
                import datetime as _dt
                local_mtime = os.path.getmtime(path)
                drive_time = _dt.datetime.fromisoformat(
                    f.get("modifiedTime", "").replace("Z", "+00:00")).timestamp()
                if local_mtime > drive_time:
                    continue
            except:
                pass
        try:
            content = service.files().get_media(fileId=f["id"]).execute()
            with _data_io_lock:
                with open(path, "wb") as fh:
                    fh.write(content)
            downloaded += 1
        except Exception as e:
            print(f"[SYNC] Download {fname} failed: {e}")
    if downloaded:
        print(f"[SYNC] Downloaded {downloaded} file(s) from Drive")
    global _last_data_hashes
    _last_data_hashes = _compute_data_hashes()
    return downloaded

def _sync_loop():
    while True:
        time.sleep(10)
        try:
            _sync_to_drive()
        except Exception as e:
            print(f"[SYNC] Sync error: {e}")


def run_with_stop(func, *args, **kwargs):
    """Run func while watching for /stop. Returns (result, was_stopped)."""
    global _stop_flag
    _stop_flag = False
    watcher = StopWatcher()
    watcher.start()
    try:
        result = func(*args, **kwargs)
        stopped = _stop_flag
        return result, stopped
    except StopRequested:
        return None, True
    finally:
        watcher.stop()


class StopRequested(Exception):
    pass


def check_stop():
    if _stop_flag:
        raise StopRequested()


# ============ STORY HISTORY ============

def load_history():
    return load_json(HISTORY_FILE, [])

def save_history(history):
    save_json(HISTORY_FILE, history)

def is_story_used(title):
    history = load_history()
    title_lower = title.lower().strip()
    return any(h.get("title","").lower().strip() == title_lower for h in history)

def record_story(title, script, video_id=None):
    history = load_history()
    history.append({
        "title": title,
        "hash": hashlib.md5(script.encode()).hexdigest(),
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "video_id": video_id,
    })
    save_history(history)

def get_used_titles():
    titles = [h.get("title","") for h in load_history()]
    pending = load_json(f"{DATA_DIR}/pending_stories.json", {})
    for s in pending.get("stories", []):
        t = s.get("title", "")
        if t and t not in titles:
            titles.append(t)
    return titles

# ============ USER ACCESS ============

_current_user_id = None
_current_user_label = None

def load_users():
    return load_json(USERS_FILE, {"users": {}})

def save_users(data):
    save_json(USERS_FILE, data)

def init_users():
    if not os.path.exists(USERS_FILE):
        entry = {"role": "admin", "added": time.strftime("%Y-%m-%d")}
        save_users({"users": {str(ADMIN_ID): entry}})
    data = load_users()
    admin = data.get("users", {}).get(str(ADMIN_ID), {})
    if admin and not admin.get("first_name"):
        info = fetch_user_info(ADMIN_ID)
        if info:
            if info.get("first_name"): admin["first_name"] = info["first_name"]
            if info.get("last_name"): admin["last_name"] = info["last_name"]
            if info.get("username"): admin["username"] = info["username"]
            data["users"][str(ADMIN_ID)] = admin
            save_users(data)

def is_allowed(user_id):
    data = load_users()
    return str(user_id) in data.get("users", {})

def is_admin(user_id):
    data = load_users()
    u = data.get("users", {}).get(str(user_id))
    return u is not None and u.get("role") == "admin"

def get_user_label(msg_from):
    first = msg_from.get("first_name", "")
    last = msg_from.get("last_name", "")
    uid = msg_from.get("id", "")
    name = f"{first} {last}".strip() if (first or last) else ""
    if name:
        return f"{name}, {uid}"
    return str(uid)

def fetch_user_info(chat_id):
    try:
        r = api_call("getChat", {"chat_id": chat_id}, timeout=10)
        c = r.get("result", {})
        return {
            "first_name": c.get("first_name", ""),
            "last_name": c.get("last_name", ""),
            "username": c.get("username", ""),
        }
    except:
        return {}

def update_user_details(user_id, msg_from):
    data = load_users()
    uid = str(user_id)
    if uid not in data.get("users", {}):
        return
    first = msg_from.get("first_name", "")
    last = msg_from.get("last_name", "")
    username = msg_from.get("username", "")
    changed = False
    if first and data["users"][uid].get("first_name") != first:
        data["users"][uid]["first_name"] = first
        changed = True
    if last and data["users"][uid].get("last_name") != last:
        data["users"][uid]["last_name"] = last
        changed = True
    if username and data["users"][uid].get("username") != username:
        data["users"][uid]["username"] = username
        changed = True
    if changed:
        save_users(data)

def format_user_display(uid, info):
    first = info.get("first_name", "")
    last = info.get("last_name", "")
    username = info.get("username", "")
    role = info.get("role", "user")
    added = info.get("added", "?")
    parts = []
    name = f"{first} {last}".strip()
    if name:
        parts.append(f"<b>{name}</b>")
    if username:
        parts.append(f"@{username}")
    parts.append(f"<code>{uid}</code>")
    if role == "admin":
        parts.append("(admin)")
    line = " | ".join(parts)
    line += f"\nAdded: {added}"
    return line

# ============ TELEGRAM API ============

last_update = 0

def api_call(method, params=None, files=None, timeout=30):
    url = f"{API}/{method}"
    if files:
        import io
        boundary = '----PythonBoundary'
        body = b''
        for k, v in (params or {}).items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, (fname, fdata, mime) in files.items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
            body += fdata + b'\r\n'
        body += f'--{boundary}--\r\n'.encode()
        req = urllib.request.Request(url, data=body,
              headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    elif params:
        data = json.dumps(params).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())

_button_messages = {}

def _track_button_msg(chat_id, msg_id):
    cid = str(chat_id)
    if cid not in _button_messages:
        _button_messages[cid] = []
    _button_messages[cid].append(msg_id)
    if len(_button_messages[cid]) > 50:
        _button_messages[cid] = _button_messages[cid][-50:]

def _clear_all_buttons(chat_id):
    cid = str(chat_id)
    for mid in _button_messages.get(cid, []):
        try:
            api_call("editMessageReplyMarkup", {
                "chat_id": int(cid), "message_id": mid,
                "reply_markup": json.dumps({"inline_keyboard": []})
            }, timeout=3)
        except:
            pass
    _button_messages[cid] = []

def send(text, reply_markup=None, chat_id=None, reply_to=None):
    target = chat_id or _current_user_id or ADMIN_ID
    params = {"chat_id": target, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup)
    if reply_to:
        params["reply_to_message_id"] = reply_to
    try:
        r = api_call("sendMessage", params)
        mid = r.get("result", {}).get("message_id")
        if mid and reply_markup:
            _track_button_msg(target, mid)
        return mid
    except urllib.error.HTTPError as e:
        if e.code == 400:
            try:
                plain = re.sub(r'<[^>]+>', '', text)
                params["text"] = plain
                params.pop("parse_mode", None)
                r = api_call("sendMessage", params)
                mid = r.get("result", {}).get("message_id")
                if mid and reply_markup:
                    _track_button_msg(target, mid)
                return mid
            except:
                pass
        print(f"Send error: {e}")
        return None
    except Exception as e:
        print(f"Send error: {e}")
        return None

def _send_admin_msg(text):
    """Send a message to admin. Never crashes."""
    try:
        send(text, chat_id=ADMIN_ID)
    except:
        pass


def btn(*buttons):
    """Build InlineKeyboardMarkup. Each arg is (emoji_label, callback_data) or a list for a row."""
    rows = []
    row = []
    for b in buttons:
        if isinstance(b, list):
            if row: rows.append(row); row = []
            rows.append([{"text": t, "callback_data": d} for t, d in b])
        else:
            row.append({"text": b[0], "callback_data": b[1]})
    if row: rows.append(row)
    return {"inline_keyboard": rows}

def edit_msg(msg_id, text, reply_markup=None, chat_id=None):
    try:
        params = {"chat_id": chat_id or _current_user_id or ADMIN_ID, "message_id": msg_id,
                  "text": text, "parse_mode": "HTML"}
        if reply_markup:
            params["reply_markup"] = json.dumps(reply_markup)
        api_call("editMessageText", params, timeout=10)
    except:
        pass

def answer_callback(cb_id):
    try:
        api_call("answerCallbackQuery", {"callback_query_id": cb_id}, timeout=5)
    except:
        pass

def delete_msg(msg_id, chat_id=None):
    try:
        api_call("deleteMessage", {"chat_id": chat_id or _current_user_id or ADMIN_ID, "message_id": msg_id}, timeout=5)
    except:
        pass

class ProgressBar:
    """Live updating Unicode progress bar on Telegram.
    If .update() is called, shows real %. Otherwise auto-increments."""
    BAR_LEN = 15
    SPINNER = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

    def __init__(self, title):
        self.title = title
        self.msg_id = None
        self.running = False
        self.thread = None
        self.start_time = time.time()
        self._pct = 0
        self._detail = ""
        self._manual = False
        self._lock = threading.Lock()

    def _bar(self, pct):
        filled = int(self.BAR_LEN * pct / 100)
        empty = self.BAR_LEN - filled
        return "🟩" * filled + "⬜" * empty

    def update(self, pct, detail=""):
        with self._lock:
            self._manual = True
            self._pct = min(100, max(0, int(pct)))
            self._detail = detail

    def start(self):
        self.start_time = time.time()
        self.msg_id = send(f"<b>{self.title}</b>\n<code>{self._bar(0)}</code> 0%")
        self.running = True
        self._pct = 0
        self._manual = False
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        last_txt = ""
        step = 0
        while self.running:
            time.sleep(2)
            if not self.running:
                break
            step += 1
            with self._lock:
                if self._manual:
                    pct = self._pct
                    detail = self._detail
                else:
                    pct = min(92, int(step * 3.5))
                    self._pct = pct
                    detail = ""
            elapsed = int(time.time() - self.start_time)
            spin = self.SPINNER[step % len(self.SPINNER)]
            line = f"<b>{self.title}</b> {spin}\n<code>{self._bar(pct)}</code> {pct}%  {elapsed}s"
            if detail:
                line += f"\n{detail}"
            if line != last_txt:
                edit_msg(self.msg_id, line)
                last_txt = line

    def stop(self, remove=True):
        self.running = False
        if self.thread:
            self.thread.join(timeout=4)
        mid = self.msg_id
        if mid:
            with self._lock:
                cur = self._pct
            if cur < 100:
                for p in range(max(cur, 10), 101, 15):
                    p = min(p, 100)
                    edit_msg(mid, f"<b>{self.title}</b>\n<code>{self._bar(p)}</code> {p}%")
                    if p < 100:
                        time.sleep(0.25)
                time.sleep(0.5)
        self.msg_id = None
        if remove and mid:
            delete_msg(mid)
            delete_msg(mid)

def send_video(path, chat_id=None):
    """Send video file to Telegram. Auto-compress if >50MB."""
    sz = os.path.getsize(path) / (1024 * 1024)
    send_path = path
    compressed = None

    if sz > 50:
        if sz > 2048:
            send(f"Video too large ({sz:.0f}MB), cannot compress.")
            return
        compressed = path.replace(".mp4", "_preview.mp4")
        target_mb = 45
        try:
            r = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                 '-of', 'csv=p=0', path],
                capture_output=True, text=True, timeout=30)
            duration = float(r.stdout.strip())
        except:
            duration = 60
        video_bitrate = max(int((target_mb * 8 * 1024) / duration) - 128, 500)
        send(f"Original: {sz:.0f}MB — compressing for Telegram preview...")
        try:
            gpu_comp = subprocess.run([
                'ffmpeg', '-y', '-i', path,
                '-vf', 'scale=-2:720',
                '-c:v', 'h264_nvenc', '-preset', 'p4', '-b:v', f'{video_bitrate}k',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart', compressed
            ], capture_output=True, text=True, timeout=600)
            if gpu_comp.returncode != 0:
                r = subprocess.run([
                    'ffmpeg', '-y', '-i', path,
                    '-vf', 'scale=-2:720',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-b:v', f'{video_bitrate}k',
                    '-c:a', 'aac', '-b:a', '128k',
                    '-movflags', '+faststart', compressed
                ], capture_output=True, text=True, timeout=600)
            else:
                r = gpu_comp
            if r.returncode == 0 and os.path.exists(compressed):
                csz = os.path.getsize(compressed) / (1024 * 1024)
                if csz <= 50:
                    send_path = compressed
                    send(f"Compressed: {csz:.1f}MB (720p preview)")
                else:
                    send(f"Still {csz:.0f}MB after compression. Trying harder...")
                    os.remove(compressed)
                    video_bitrate = max(int((40 * 8 * 1024) / duration) - 96, 300)
                    gpu_comp2 = subprocess.run([
                        'ffmpeg', '-y', '-i', path,
                        '-vf', 'scale=-2:480',
                        '-c:v', 'h264_nvenc', '-preset', 'p4', '-b:v', f'{video_bitrate}k',
                        '-c:a', 'aac', '-b:a', '96k',
                        '-movflags', '+faststart', compressed
                    ], capture_output=True, text=True, timeout=600)
                    if gpu_comp2.returncode != 0:
                        r2 = subprocess.run([
                            'ffmpeg', '-y', '-i', path,
                            '-vf', 'scale=-2:480',
                            '-c:v', 'libx264', '-preset', 'ultrafast', '-b:v', f'{video_bitrate}k',
                            '-c:a', 'aac', '-b:a', '96k',
                            '-movflags', '+faststart', compressed
                        ], capture_output=True, text=True, timeout=600)
                    else:
                        r2 = gpu_comp2
                    if r2.returncode == 0 and os.path.exists(compressed):
                        csz2 = os.path.getsize(compressed) / (1024 * 1024)
                        if csz2 <= 50:
                            send_path = compressed
                            send(f"Compressed: {csz2:.1f}MB (480p preview)")
                        else:
                            send(f"Still too large ({csz2:.0f}MB). Cannot send preview.")
                            os.remove(compressed)
                            return
                    else:
                        send("Compression failed.")
                        return
            else:
                stderr = (r.stderr or "")[-200:]
                send(f"Compression failed: {stderr}")
                return
        except Exception as e:
            send(f"Compression error: {e}")
            return

    with open(send_path, 'rb') as f:
        data = f.read()
    target = str(chat_id or _current_user_id or ADMIN_ID)
    upload_timeout = max(120, int(len(data) / (100 * 1024)))
    last_err = None
    for attempt in range(2):
        try:
            api_call("sendVideo", {"chat_id": target,
                      "caption": "Preview — reply 'ok' to upload or 'redo' to rebuild"},
                     {"video": ("preview.mp4", data, "video/mp4")},
                     timeout=upload_timeout)
            last_err = None
            break
        except Exception as e:
            last_err = e
            if attempt == 0:
                send("Upload slow, retrying...")
    if last_err:
        send(f"Preview send failed: {last_err}")
        try:
            api_call("sendDocument", {"chat_id": target,
                      "caption": "Preview (as document)"},
                     {"document": ("preview.mp4", data, "video/mp4")},
                     timeout=upload_timeout)
        except Exception as e2:
            send(f"Document fallback also failed: {e2}")
    if compressed and os.path.exists(compressed):
        try: os.remove(compressed)
        except: pass

def notify_admin(action):
    uid = _current_user_id
    if uid == ADMIN_ID or uid is None:
        return
    label = _current_user_label or str(uid)
    send(f"[{label}] {action}", chat_id=ADMIN_ID)

def send_and_notify(text, reply_markup=None, chat_id=None):
    send(text, reply_markup=reply_markup, chat_id=chat_id)
    target = chat_id or _current_user_id
    if target and target != ADMIN_ID:
        label = _current_user_label or str(target)
        send(f"[{label}] {text}", chat_id=ADMIN_ID)

_last_notify_check = 0

def _format_countdown(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def _deadline_bar(secs_left, total_secs=3600):
    BAR_LEN = 15
    pct = max(0, min(1, secs_left / total_secs))
    filled = round(BAR_LEN * pct)
    empty = BAR_LEN - filled
    bar = ""
    for i in range(filled):
        pos = i / BAR_LEN
        if pos < 0.35:
            bar += "🟩"
        elif pos < 0.7:
            bar += "🟨"
        else:
            bar += "🟥"
    bar += "⬜" * empty
    if pct > 0.5:
        label = "Plenty of time"
    elif pct > 0.2:
        label = "Hurry up!"
    else:
        label = "Almost out of time!"
    return f"{bar} {label}"

def _slot_reminder_text(slot, upload_by, countdown_str, secs_left, slot_date=""):
    bar = _deadline_bar(secs_left)
    date_line = f"Date: <b>{slot_date}</b>\n" if slot_date else ""
    header = "<b>Short video due!</b>"
    guide = (
        f"<b>Viral Shorts Guide:</b>\n"
        f"- Duration: <b>33-38 seconds</b> (proven sweet spot)\n"
        f"- First line: shocking hook under 10 words\n"
        f"- Hook - Escalation - Twist - Punchline\n"
        f"- CTA only at end: \"Follow for more\"\n"
        f"- USA-relatable stories only"
    )
    return (
        f"{header}\n\n"
        f"{date_line}"
        f"Slot: <b>{slot[0]} IST</b> ({slot[1]})\n"
        f"Upload by: <b>{upload_by.strftime('%I:%M %p')} IST</b>\n\n"
        f"{bar}\n"
        f"<code>  {countdown_str}  </code>\n\n"
        f"{guide}\n\n"
        f"Use /auto to generate or /story to paste your own."
    )

def _delete_slot_reminders(key):
    notified = load_json(NOTIFY_FILE, {"msg_ids": {}})
    old_msgs = notified.get("msg_ids", {}).get(key, {})
    for uid, mid in old_msgs.items():
        try:
            delete_msg(mid, chat_id=int(uid))
        except:
            pass
    if key in notified.get("msg_ids", {}):
        del notified["msg_ids"][key]
        save_json(NOTIFY_FILE, notified)

def check_slot_notifications():
    """Live countdown reminder for upcoming slot.
    Sends message once, then edits it every 30s with updated hh:mm:ss.
    Deletes when: bot busy, deadline passed, or slot used."""
    global _last_notify_check
    from datetime import datetime, timedelta, timezone

    now_ts = time.time()
    if now_ts - _last_notify_check < 30:
        return
    _last_notify_check = now_ts

    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")

    notified = load_json(NOTIFY_FILE, {"msg_ids": {}})
    schedule = load_json(SCHEDULE_FILE, {"used": []})
    used_keys = set(u.get("key", "") for u in schedule.get("used", []))

    # Clean up reminders for slots that are now used or expired
    for key in list(notified.get("msg_ids", {}).keys()):
        if key in used_keys:
            _delete_slot_reminders(key)

    if bot.state != "IDLE":
        for key in list(notified.get("msg_ids", {}).keys()):
            _delete_slot_reminders(key)
        return

    # Build all slots for today and tomorrow
    all_slots = []
    for day_offset in range(2):
        check_date = (now_ist + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        for slot in UPLOAD_SLOTS_IST:
            slot_time = datetime.strptime(f"{check_date} {slot[0]}", "%Y-%m-%d %I:%M %p").replace(tzinfo=IST)
            key = f"{check_date}_{slot[0]}"
            all_slots.append((slot, slot_time, key))

    for slot, slot_time, key in all_slots:
        if key in used_keys:
            continue

        lead_hours = 3
        notify_start = slot_time - timedelta(hours=lead_hours)
        upload_by = slot_time - timedelta(hours=2)

        if now_ist >= upload_by:
            _delete_slot_reminders(key)
            continue

        if notify_start <= now_ist < upload_by:
            secs_left = (upload_by - now_ist).total_seconds()
            countdown = _format_countdown(secs_left)
            slot_date = slot_time.strftime("%d/%m/%Y")
            text = _slot_reminder_text(slot, upload_by, countdown, secs_left, slot_date=slot_date)
            markup = btn(("Auto", "/auto"), ("Story", "/story"))

            existing_msgs = notified.get("msg_ids", {}).get(key, {})
            users = load_users().get("users", {})

            if existing_msgs:
                for uid, mid in existing_msgs.items():
                    try:
                        edit_msg(mid, text, reply_markup=markup, chat_id=int(uid))
                    except:
                        pass
            else:
                new_msgs = {}
                for uid in users:
                    try:
                        r = api_call("sendMessage", {
                            "chat_id": int(uid),
                            "text": text,
                            "parse_mode": "HTML",
                            "reply_markup": json.dumps(markup)
                        })
                        mid = r.get("result", {}).get("message_id")
                        if mid:
                            new_msgs[str(uid)] = mid
                    except Exception as e:
                        print(f"Notify {uid} failed: {e}")
                notified["msg_ids"][key] = new_msgs
                save_json(NOTIFY_FILE, notified)
            break

def flush_old():
    global last_update
    try:
        updates = api_call("getUpdates", {"offset": -1})
        results = updates.get("result", [])
        if results:
            last_update = results[-1]["update_id"]
    except:
        pass

# ============ CLIP DOWNLOAD (reused from telegram_bot_final.py) ============

url_history = {}
HASH_HISTORY = f"{CLIPS_DIR}/.hash_history.json"
hash_history = {}

def load_url_history():
    global url_history, hash_history
    url_history = load_json(URL_HISTORY, {})
    hash_history = load_json(HASH_HISTORY, {})

def save_url_history():
    save_json(URL_HISTORY, url_history)

def save_hash_history():
    save_json(HASH_HISTORY, hash_history)

def normalize_url(url):
    url = url.split('?')[0].rstrip('/')
    return url

def is_duplicate_url(url):
    return normalize_url(url) in url_history

def record_url(url, filename):
    url_history[normalize_url(url)] = filename
    save_url_history()

def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()[:16]

def is_duplicate_file(path):
    h = file_hash(path)
    return h in hash_history

def record_file_hash(path, filename):
    h = file_hash(path)
    hash_history[h] = filename
    save_hash_history()

def try_ytdlp(url, filename):
    out = f"{CLIPS_DIR}/{filename}"
    try:
        r = subprocess.run(
            ["yt-dlp","--impersonate","chrome","-o",out,
             "--format","best[ext=mp4]/best","--no-playlist","--max-filesize","500M",url],
            capture_output=True, text=True, timeout=300)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 50000:
            return os.path.getsize(out) / (1024*1024)
    except: pass
    if os.path.exists(out) and os.path.getsize(out) < 50000:
        os.remove(out)
    return None

def try_direct(url, filename):
    out = f"{CLIPS_DIR}/{filename}"
    try:
        from curl_cffi import requests as cffi_req
        r = cffi_req.get(url, impersonate='chrome131', timeout=300)
        if len(r.content) > 50000:
            with open(out, 'wb') as f: f.write(r.content)
            return len(r.content) / (1024*1024)
    except: pass
    return None

def save_telegram_file(file_id, filename):
    for attempt in range(3):
        try:
            result = api_call("getFile", {"file_id": file_id})
        except urllib.error.HTTPError as e:
            if e.code == 400:
                raise Exception("File >20MB. Send as video (not file) or paste a URL.")
            raise
        if not result.get("ok"):
            desc = result.get("description", "Unknown error")
            raise Exception(f"getFile failed: {desc}")
        fp = result["result"]["file_path"]
        furl = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fp}"
        out = f"{CLIPS_DIR}/{filename}"
        try:
            urllib.request.urlretrieve(furl, out)
            if os.path.exists(out) and os.path.getsize(out) > 1000:
                return os.path.getsize(out) / (1024*1024)
            raise Exception("Downloaded file too small or empty")
        except urllib.error.HTTPError as e:
            if attempt < 2:
                time.sleep(1)
                continue
            raise Exception(f"File download failed: HTTP {e.code}")
    raise Exception("File download failed after retries")

def trim_last_5s(filepath):
    """Trim last 6 seconds from a clip (removes RedNote/TikTok watermark)."""
    try:
        r = subprocess.run(
            ['ffprobe','-v','quiet','-show_entries','format=duration','-of','csv=p=0', filepath],
            capture_output=True, text=True, timeout=10)
        clip_dur = float(r.stdout.strip())
        if clip_dur <= 7:
            return
        trimmed = filepath + ".trimmed.mp4"
        subprocess.run([
            'ffmpeg','-y','-i', filepath,'-t', str(clip_dur - 6),
            '-c','copy', trimmed
        ], capture_output=True, timeout=30)
        if os.path.exists(trimmed) and os.path.getsize(trimmed) > 10000:
            os.replace(trimmed, filepath)
        else:
            if os.path.exists(trimmed): os.remove(trimmed)
    except:
        pass

def count_clips(include_default=False):
    user = len([f for f in os.listdir(CLIPS_DIR) if f.endswith(('.mp4','.webm','.mov')) and not f.startswith('.')])
    if include_default and os.path.isdir(DEFAULT_CLIPS_DIR):
        user += len([f for f in os.listdir(DEFAULT_CLIPS_DIR) if f.endswith(('.mp4','.webm','.mov')) and not f.startswith('.')])
    return user




# ============ OLLAMA FALLBACK (gemma4 cloud) ============

def _ollama_rate_check():
    global _ollama_last_call, _ollama_calls_minute
    now = time.time()
    _ollama_calls_minute = [t for t in _ollama_calls_minute if now - t < 60]
    if len(_ollama_calls_minute) >= OLLAMA_MAX_PER_MINUTE:
        wait = 60 - (now - _ollama_calls_minute[0])
        if wait > 0:
            print(f"[OLLAMA RATE] Waiting {wait:.0f}s (hit {OLLAMA_MAX_PER_MINUTE}/min limit)")
            time.sleep(wait)
    gap = now - _ollama_last_call
    if gap < OLLAMA_MIN_GAP and _ollama_last_call > 0:
        time.sleep(OLLAMA_MIN_GAP - gap)
    _ollama_last_call = time.time()
    _ollama_calls_minute.append(_ollama_last_call)


# ============ WEB SEARCH (for Ollama fallback) ============

_ddg_last_call = 0
DDG_MIN_GAP = 3

def _ddg_rate_check():
    global _ddg_last_call
    now = time.time()
    gap = now - _ddg_last_call
    if gap < DDG_MIN_GAP and _ddg_last_call > 0:
        time.sleep(DDG_MIN_GAP - gap)
    _ddg_last_call = time.time()


def search_viral_stories():
    """Search DuckDuckGo for real viral Reddit/news stories. Returns formatted string or ''."""
    try:
        from ddgs import DDGS
    except ImportError:
        print("[SEARCH] duckduckgo-search not installed")
        return ""

    reddit_queries = [
        "reddit AITA viral story this week",
        "reddit ProRevenge best story this month",
        "reddit MaliciousCompliance viral story",
        "reddit NuclearRevenge best revenge story",
        "reddit EntitledPeople viral Karen story",
        "reddit ChoosingBeggars viral story",
        "reddit PettyRevenge satisfying karma",
        "reddit relationship_advice cheating exposed",
        "reddit AmItheAsshole controversial update",
        "reddit legaladvice insane lawsuit",
    ]
    news_queries = [
        "viral news story USA caught on camera today",
        "shocking lawsuit USA news this week",
        "Karen caught on camera viral USA",
        "neighbor war viral news USA",
        "cheating exposed viral story USA",
        "scammer caught viral USA news",
        "entitled person destroyed viral video",
        "instant karma caught on camera USA",
        "court case shocking verdict USA this week",
        "trending drama story USA today",
    ]

    stories_text = []
    try:
        ddgs = DDGS(timeout=15)
        _ddg_rate_check()
        results = ddgs.text(random.choice(reddit_queries), region="us-en", max_results=5)
        for r in (results or []):
            title = r.get("title", "").strip()
            body = r.get("body", "").strip()
            if title and body:
                stories_text.append(f"[Reddit] {title}: {body}")
    except Exception as e:
        print(f"[SEARCH] Reddit search failed: {e}")

    try:
        ddgs = DDGS(timeout=15)
        _ddg_rate_check()
        results = ddgs.news(random.choice(news_queries), region="us-en", timelimit="m", max_results=5)
        for r in (results or []):
            title = r.get("title", "").strip()
            body = r.get("body", "").strip()
            if title and body:
                stories_text.append(f"[News] {title}: {body}")
    except Exception as e:
        print(f"[SEARCH] News search failed: {e}")

    if stories_text:
        print(f"[SEARCH] Found {len(stories_text)} story leads from web")
    else:
        print("[SEARCH] No web results — AI will use training data")
    return "\n".join(stories_text)


def search_seo_trends(topic):
    """Search for YouTube SEO trends: popular titles, hashtags, descriptions for a topic."""
    try:
        from ddgs import DDGS
    except ImportError:
        return ""

    safe_topic = re.sub(r'[^\w\s]', '', topic)[:60]
    queries = [
        f"best YouTube title for {safe_topic} story 2026",
        f"trending YouTube hashtags {safe_topic} shorts",
        f"viral YouTube shorts description {safe_topic}",
    ]

    results_text = []
    try:
        ddgs = DDGS(timeout=15)
        _ddg_rate_check()
        results = ddgs.text(random.choice(queries), region="us-en", timelimit="m", max_results=5)
        for r in (results or []):
            title = r.get("title", "").strip()
            body = r.get("body", "").strip()
            if title:
                results_text.append(f"- {title}: {body[:200] if body else ''}")
    except Exception as e:
        print(f"[SEARCH] SEO trends search failed: {e}")

    if results_text:
        print(f"[SEARCH] Found SEO trends for: {safe_topic}")
    return "\n".join(results_text)


def search_trending_keywords(topic):
    """Search for trending YouTube keywords for a topic. Returns formatted string or ''."""
    try:
        from ddgs import DDGS
    except ImportError:
        return ""

    safe_topic = re.sub(r'[^\w\s]', '', topic)[:80]
    queries = [
        f"{safe_topic} YouTube trending",
        f"trending YouTube shorts {safe_topic}",
        f"{safe_topic} viral video trending keywords",
    ]

    keywords_text = []
    try:
        ddgs = DDGS(timeout=15)
        _ddg_rate_check()
        results = ddgs.text(random.choice(queries), region="us-en", timelimit="w", max_results=5)
        for r in (results or []):
            title = r.get("title", "").strip()
            body = r.get("body", "").strip()
            if title:
                keywords_text.append(f"- {title}: {body[:150] if body else ''}")
    except Exception as e:
        print(f"[SEARCH] Keyword search failed: {e}")

    if keywords_text:
        print(f"[SEARCH] Found trending keywords for: {safe_topic}")
    return "\n".join(keywords_text)


def ollama_run(prompt, timeout=180):
    """Fallback: call Ollama cloud API with gemma4:31b-cloud. Handles 429 with backoff."""
    import urllib.request, ssl
    _ollama_rate_check()
    print(f"[FALLBACK] Using Ollama gemma4:31b-cloud...")
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode('utf-8')

    ctx = ssl.create_default_context()
    max_retries = 3
    backoff = 10

    for attempt in range(max_retries + 1):
        req = urllib.request.Request(OLLAMA_API, data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Authorization', f'Bearer {OLLAMA_KEY}')
        req.add_header('User-Agent', 'ToldByNova/1.0')

        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                content = data.get("message", {}).get("content", "")
                if content:
                    print(f"[FALLBACK] Ollama OK: {len(content)} chars")
                    return content
                print(f"[FALLBACK] Ollama empty response")
                return None
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                wait = backoff * (2 ** attempt)
                print(f"[FALLBACK] Ollama 429 rate limited — waiting {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            print(f"[FALLBACK] Ollama HTTP {e.code}: {e.reason}")
            return None
        except Exception as e:
            print(f"[FALLBACK] Ollama error: {e}")
            return None
    return None


# ============ CLI AI (claude / codex / trexocli) + OLLAMA FALLBACK ============

STORY_SYSTEM_PROMPT = (
    "You are a viral story writer for YouTube channel 'Told By Nova'. "
    "You write ONLY about: revenge, karma, cheating, betrayal, court cases, neighbor wars, "
    "Karen stories, workplace revenge, family drama, scams exposed, entitled people, justice served. USA audience. "
    "EVERY story MUST have a clear protagonist, antagonist, conflict, and satisfying resolution. "
    "NEVER write about: math, science, health tips, professors, universities, janitors, genius stories, "
    "academic topics, educational content, history lessons, inspirational scholars, "
    "fun facts, life hacks, food facts, body facts, psychology facts, 'did you know' content. "
    "Output ONLY raw JSON. No markdown, no code blocks."
)

def claude_run(prompt, timeout=120, ollama_prompt=None, min_words=0):
    global _last_ai_source
    _last_ai_source = "Ollama"
    return ollama_run(ollama_prompt or prompt, timeout=max(timeout, 180))

CATEGORY_TO_MOOD = {
    "crime": "dark", "horror": "dark", "murder": "dark", "dark": "dark",
    "mystery": "suspense", "suspense": "suspense", "psychology": "suspense", "betrayal": "suspense",
    "revenge": "dramatic", "justice": "dramatic", "court": "dramatic", "law": "dramatic", "dramatic": "dramatic",
    "history": "dramatic", "science": "suspense",
    "emotional": "emotional", "sad": "emotional", "family": "emotional", "heartbreak": "emotional",
    "uplifting": "uplifting", "happy": "uplifting", "success": "uplifting", "karma": "uplifting",
}

def _extract_text(val):
    """Extract text from a value that might be a string or a nested dict."""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        return (val.get("script") or val.get("text") or val.get("narration") or val.get("body") or val.get("content") or "").strip()
    return ""

def normalize_story(s):
    """Map Claude's varying JSON keys to our expected format."""
    # Unwrap nested "story" metadata dict if present
    story_meta = s.get("story") if isinstance(s.get("story"), dict) else {}

    # Flatten: if top-level "story" dict has script/narration inside, merge up
    story_obj = s.get("story")
    if isinstance(story_obj, dict):
        for pull_key in ["script", "short_script", "narration", "body", "text",
                         "clip_suggestions", "clips", "mood", "dramatic_words"]:
            if pull_key not in s and pull_key in story_obj:
                s[pull_key] = story_obj[pull_key]

    script = _extract_text(s.get("script") or s.get("short_script") or s.get("body") or s.get("narration") or s.get("text") or "")

    title = s.get("title") or s.get("story_title") or story_meta.get("title") or ""
    if isinstance(title, dict):
        title = title.get("text") or title.get("title") or ""
    title = title.strip()
    if not title or title.lower() in ("untitled", "title", "short searchable title with keyword"):
        if hook and len(hook) < 80:
            title = hook.rstrip(".")
        elif script:
            title = script.split(".")[0][:70]
        else:
            title = "Untitled"
    hook = s.get("hook") or story_meta.get("hook") or ""
    if isinstance(hook, dict):
        hook = hook.get("text") or hook.get("hook") or ""
    if not hook and isinstance(s.get("short_script"), dict):
        hook = s["short_script"].get("hook", "")
    if not hook and script:
        hook = script.split(".")[0]

    if len(script.split()) < 30:
        print(f"[normalize] Short script has only {len(script.split())} words — flagged as incomplete")

    # Trim short script if too long (target ~33-38s = 85-100 words before CTA)
    max_words = 100  # 100 words body + ~25 CTA = ~125 total = ~46 sec max
    if len(script.split()) > max_words:
        print(f"[normalize] Short script too long ({len(script.split())}w > {max_words}w) — trimming")
        sentences = [x.strip() for x in script.replace("...", ".").split(". ") if x.strip()]
        trimmed = []
        wc = 0
        for sent in sentences:
            trimmed.append(sent)
            wc += len(sent.split())
            if wc >= max_words - 10:
                break
        script = ". ".join(trimmed).rstrip(". ") + "."

    if len(script.split()) >= 30:
        # Structure: Story → CTA (subscribe/follow) → Loop-trick cliffhanger (LAST thing before loop)
        _closed_endings = [
            "justice was served", "she finally got peace", "and they lived happily",
            "he got what he deserved", "karma came through", "in the end",
            "the case was closed", "everything worked out", "it was finally over",
            "she moved on", "he never bothered her again", "and that was that",
            "they never spoke again", "the truth came out", "she won the case",
            "he was arrested", "they got their money back", "the judge ruled",
        ]
        _open_endings = [
            "But that wasn't even the worst part.",
            "And then everything changed.",
            "Little did he know what was coming next.",
            "But she had no idea what I was planning.",
            "And that's when the real story began.",
            "But what happened next... no one saw it coming.",
            "And that was only the beginning.",
        ]
        import random as _rnd

        # Split into sentences, separate story body from CTA and ending
        sentences = [x.strip() for x in script.split(". ") if x.strip()]
        story_parts = []
        cta_parts = []
        ending_part = None

        for sent in sentences:
            sl = sent.lower()
            if 'subscribe' in sl or 'follow' in sl or 'comment' in sl:
                cta_parts.append(sent)
            else:
                story_parts.append(sent)

        # Check if last story sentence is already a good open ending
        if story_parts:
            last = story_parts[-1].lower().rstrip(".")
            is_closed = any(closed in last for closed in _closed_endings)
            is_open = any(op.lower().rstrip(".") in last for op in _open_endings) or \
                      any(w in last for w in ["wasn't even", "everything changed", "little did",
                                              "no one saw", "what was coming", "real story began",
                                              "only the beginning", "what happened next"])
            if is_open:
                ending_part = story_parts.pop()
            elif is_closed:
                story_parts.pop()
                ending_part = _rnd.choice(_open_endings)
            else:
                ending_part = _rnd.choice(_open_endings)
        else:
            ending_part = _rnd.choice(_open_endings)

        _viral_ctas = [
            "Was this justified? Type YES or NO. Like and subscribe for more.",
            "Would you have done the same? Comment below. Like if you agree.",
            "Who was wrong here? Drop your answer. Hit like and subscribe.",
            "Am I wrong for this? Tell me in the comments. Like and subscribe.",
        ]
        has_subscribe = any('subscribe' in c.lower() for c in cta_parts)
        if not cta_parts:
            cta_parts = [random.choice(_viral_ctas)]
        elif not has_subscribe:
            cta_parts.append("Like and subscribe for more stories like this.")

        # Rebuild: Story → CTA → Loop cliffhanger
        script = ". ".join(story_parts).rstrip(". ") + ". "
        script += ". ".join(cta_parts).rstrip(". ") + ". "
        script += ending_part
        if not script.endswith("."):
            script += "."

    mood = s.get("mood") or ""
    if not mood or mood not in ("emotional", "suspense", "dramatic", "uplifting", "dark"):
        cat = (s.get("category") or s.get("genre") or s.get("tone") or "dramatic").lower()
        mood = CATEGORY_TO_MOOD.get(cat, "dramatic")
        for k, v in CATEGORY_TO_MOOD.items():
            if k in cat:
                mood = v
                break

    dramatic_words = s.get("dramatic_words") or s.get("keywords") or s.get("tags") or []
    if not dramatic_words:
        try:
            from pipeline import DRAMATIC
        except ImportError:
            from scripts.pipeline import DRAMATIC
        dramatic_words = [w for w in script.lower().split() if w.strip('.,!?;:\'"') in DRAMATIC][:8]

    # --- SEO extraction (handles nested / variant keys) ---
    def _fix_seo(seo):
        if not isinstance(seo, dict):
            return None
        if seo.get("title") and not seo.get("yt_title"):
            seo["yt_title"] = seo.pop("title")
        if not seo.get("yt_title"):
            return None
        if isinstance(seo.get("tags"), list):
            seo["tags"] = ",".join(seo["tags"])
        return seo

    short_seo = _fix_seo(s.get("short_seo") or s.get("seo_short") or s.get("seo") or None)

    # --- clip suggestions ---
    clips = s.get("clip_suggestions") or s.get("clips") or s.get("visual_suggestions") or s.get("visuals") or None
    if isinstance(clips, str):
        clips = [c.strip() for c in clips.split(",") if c.strip()]

    result = {
        "title": title,
        "hook": hook,
        "script": script,
        "dramatic_words": dramatic_words,
        "mood": mood,
    }
    if clips:
        result["clip_suggestions"] = clips
    if short_seo:
        result["short_seo"] = short_seo
    return result

def parse_claude_json(text, label=""):
    """Extract JSON from Claude response, normalize story fields."""
    cleaned = re.sub(r'```(?:json)?\s*', '', text).strip()

    parsed = None
    # Try direct parse
    try:
        parsed = json.loads(cleaned)
    except:
        pass
    # Try regex for object
    if parsed is None:
        try:
            match = re.search(r'\{[\s\S]*\}', cleaned)
            if match:
                parsed = json.loads(match.group())
        except:
            pass
    # Try regex for array
    if parsed is None:
        try:
            match = re.search(r'\[[\s\S]*\]', cleaned)
            if match:
                parsed = json.loads(match.group())
        except:
            pass

    if parsed is None:
        print(f"{label}: no valid JSON in: {cleaned[:200]}")
        return None

    # For SEO calls, don't normalize as stories
    if "seo" in label.lower():
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed else None
        print(f"{label}: OK, {type(parsed).__name__}")
        return parsed

    if isinstance(parsed, list):
        parsed = {"stories": parsed}

    # Normalize: accept "scripts" key too
    if "scripts" in parsed and "stories" not in parsed:
        parsed["stories"] = parsed.pop("scripts")

    # Normalize each story
    if "stories" in parsed:
        parsed["stories"] = [normalize_story(s) for s in parsed["stories"]]
        print(f"{label}: OK, {len(parsed['stories'])} stories")
    else:
        parsed = {"stories": [normalize_story(parsed)]}
        print(f"{label}: OK, single story")

    return parsed

def generate_stories():
    """Generate 1 viral short story."""
    used = get_used_titles()
    used_list = "\n".join(f"- {t}" for t in used[-50:]) if used else "None yet"

    dur = bot.max_duration if bot.max_duration > 0 else random.randint(28, 33)
    words_min = int(dur * 2.5)
    words_max = int(dur * 3)
    print(f"Story mode: SHORT ONLY | short={dur}s ({words_min}-{words_max}w)")

    cta_options = [
        "Was she wrong? Type YES or NO. Like and subscribe for more.",
        "Would you have done the same? Comment below. Like if you agree.",
        "Who was wrong here? Drop your answer. Hit like and subscribe.",
        "Type 1 if she was right, 2 if he was. Like this and subscribe.",
        "Am I wrong for this? Tell me in the comments. Like and subscribe.",
        "What would you have done? Comment NOW. Double tap and subscribe.",
    ]
    short_cta = random.choice(cta_options)
    json_format = f"""{{"stories":[{{"title":"Short searchable title with keyword","hook":"Shocking first sentence under 10 words","script":"MANDATORY complete SHORT narration {words_min}-{words_max} words ending with {short_cta}","dramatic_words":["word1","word2","word3","word4","word5"],"mood":"dramatic","clip_suggestions":["search term 1","search term 2","search term 3","search term 4","search term 5"],"short_seo":{{"yt_title":"Viral YT Shorts title under 50 chars","description":"#shorts #storytime #redditstories + hook + summary + Follow @ToldByNova","tags":"shorts,storytime,viral,reddit stories,true story,justice,revenge,karma,real stories,plus 10 story-specific tags","category":"Entertainment"}}}}]}}"""

    base_rules = f"""Generate SHORT script only.

===== BANNED TOPICS (INSTANT REJECTION — DO NOT USE) =====
NEVER write about ANY of these:
ACADEMIC: math, science, physics, chemistry, biology, equations, theorems, professors, universities, MIT, Harvard, NASA, Nobel Prize, Fields Medal, PhD, research papers, discoveries, inventions, academic achievements, janitors solving problems, hidden genius, underdog scholars, homework, exams, lectures, blackboards, inspirational teacher stories.
HEALTH/BODY: health tips, medical facts, body facts, drinking water, nutrition, diet, fitness, brain science, neuroscience, psychology facts, optical illusions, brain glitches, "did you know" body facts, sleep tips, hydration.
SCIENCE/FACTS: fun facts, mind blowing facts, space facts, animal facts, history facts, geography facts, "things you didn't know", life hacks, food facts, cooking tips.
MOTIVATIONAL: inspirational quotes, success stories without conflict, self-help, productivity tips, morning routines, positive thinking.
If your story does NOT have a clear VILLAIN + VICTIM + CONFLICT + REVENGE/KARMA — STOP and start over. Every story MUST be drama/revenge/karma/justice.
===== END BANNED TOPICS =====

ONLY THESE TOPICS (USA viral drama — what people actually watch):
- Reddit revenge stories (ProRevenge, MaliciousCompliance, NuclearRevenge, PettyRevenge)
- Cheating caught on camera, divorce revenge, toxic in-laws exposed
- Boss gets fired by employee, workplace revenge, wrongful termination lawsuits
- Neighbor wars, Karen gets karma, entitled people destroyed
- Court cases, lawsuits, legal drama with satisfying justice
- Family betrayal, inheritance fights, secrets exposed at weddings/funerals
- Scammer gets scammed, fraud exposed, catfish caught
- HOA revenge, landlord karma, roommate from hell stories
THE STORY MUST HAVE: a villain, a victim, conflict, and SATISFYING REVENGE/KARMA/JUSTICE ending.

===== STORY UNIQUENESS (MANDATORY — GENERIC STORIES GET 0 VIEWS) =====
Every story MUST have a BIZARRE/UNUSUAL specific detail that makes it stand out:
BAD (generic, oversaturated, will flop): "My boss demanded I follow rules" / "My neighbor was rude" / "My coworker stole my idea" / "My landlord was terrible" / "My ex cheated on me"
GOOD (unique, bizarre, will go viral): "My boss made me count every paperclip — so I counted 47,000" / "My neighbor called the cops because my DOG was too happy" / "She sued Red Bull because it didn't give her wings" / "Karen broke into my house at 3 AM to complain about my lawn"
THE DIFFERENCE: Generic = been told 1 million times. Bizarre = has ONE specific absurd detail that makes someone say "WAIT WHAT?"
If your story could be titled "Boss/Neighbor/Ex was bad and got karma" — it is TOO GENERIC. Start over.
===== END UNIQUENESS RULE =====

RULES FOR SHORT SCRIPT (field: "script"):
- Target: {dur} seconds. Script MUST be {words_min}-{words_max} words (voice reads at ~2.7 words/sec).
- FIRST WORD RULE (MOST IMPORTANT — THIS DECIDES IF VIDEO GETS 200 OR 2000 VIEWS):
  The first sentence is heard in 1 second. It MUST contain a SPECIFIC shocking detail.
  Start with: "She", "He", "My", "They" + immediate SPECIFIC action (not vague).
  NEVER start with: "So", "Well", "Today", "I want to", "Let me tell you", "This is a story"
  GREAT HOOKS (specific + shocking): "She faked her own kidnapping for 22 days." / "He sued Red Bull for not giving him wings." / "My neighbor called the cops because my dog was too happy." / "Karen broke into my house at 3 AM over a lawn ornament."
  BAD HOOKS (vague + generic): "My boss was terrible." / "My neighbor was rude to me." / "Something crazy happened." / "My ex did something unforgivable."
  THE RULE: First sentence must have a SPECIFIC bizarre detail. "Boss demanded rules" = generic. "Boss made me count 47,000 paperclips" = specific + bizarre.
- HOOK (first sentence): A shocking accusation with ONE bizarre specific detail, under 10 words.
- Structure: Hook → Escalation → SECOND HOOK → Twist → CTA → Loop Cliffhanger (LAST LINE)
- CONTROVERSY RULE: The story MUST make viewers pick a side. Include a morally gray moment where the "hero" does something questionable. Viewers should DEBATE in comments whether they were right or wrong.
- SECOND HOOK (at ~14-15 second mark, around word 38-42 in script):
  YouTube algorithm checks retention at 15s — this is the "sustained distribution gate". You MUST insert a SURPRISE sentence here that re-hooks the viewer.
  Examples: "But here's what nobody expected." / "That's when she found the hidden camera." / "What he said next shocked everyone."
  This must be a NEW revelation mid-story, not a recap. One shocking sentence that makes them NEED to keep watching.
- CTA (subscribe/follow) comes BEFORE the loop ending: "{short_cta}"
  This reminds viewer to subscribe WHILE the story tension is still high.
- SEAMLESS LOOP TRICK (THE VERY LAST LINE OF THE SCRIPT — MANDATORY):
  YouTube Shorts loop automatically. The VERY LAST sentence of the entire script (AFTER CTA) MUST be an open-ended cliffhanger. When video loops back to the HOOK, viewer thinks the story CONTINUES. They should NOT notice the restart.
  SCRIPT ORDER: [Story]... [CTA: subscribe/follow]... [LAST LINE: loop cliffhanger]
  HOW: End with a mysterious/unresolved line → viewer hears the hook again → thinks it's what happens next.
  EXAMPLE 1:
    Script ends: "...Subscribe for more stories like this. But she had no idea what I was planning next."
    → Loops to hook: "My neighbor called the cops on me for the last time." ← viewer thinks THIS is the plan!
  EXAMPLE 2:
    Script ends: "...Follow for more stories. And that's when the real story began."
    → Loops to hook: "She caught him with her best friend." ← viewer thinks THIS is the real story!
  EXAMPLE 3:
    Script ends: "...Subscribe if you want to know what happened next. But what happened next... no one saw it coming."
    → Loops to hook: "He fired me in front of everyone." ← feels continuous!
  BANNED LAST LINES (NEVER end with these):
    "Justice was served." / "She finally got peace." / "He got what he deserved." / "The case was closed." / "Everything worked out." / "She won." / "He was arrested." / "Karma came through." / "It was finally over." / "They never spoke again."
  GOOD LAST LINES (use one of these or similar as the FINAL sentence):
    "But that wasn't even the worst part." / "And then everything changed." / "Little did he know..." / "But she had no idea what was coming." / "And that's when the real story began." / "But what happened next changed everything."
  TEST: Read your LAST line → then your hook. Must feel like ONE continuous story.
- Short punchy sentences. 1 thought per sentence. Natural female narrator voice.
SEO RULES:
- short_seo.yt_title: MUST follow these rules:
  1. Under 50 chars, no emojis, no hashtags
  2. MUST contain the BIZARRE specific detail (the thing that makes it unique)
  3. MUST create curiosity gap — viewer needs to click to know what happened
  4. NEVER reveal the outcome in the title ("Lost Everything", "Got Karma", "Was Destroyed" = BAD)
  5. NEVER use generic formats: "X Gets Karma" / "X Loses Everything" / "X Was Wrong"
  BAD TITLES: "Boss Demanded Rules Then Lost Everything" / "Karen Gets What She Deserves" / "Cheater Gets Caught"
  GOOD TITLES: "He Sued Red Bull Because It Didn't Give Him Wings" / "She Found His Secret Phone" / "Karen's Midnight Raid Backfires"
  THE TEST: Would someone screenshot this title and send it to a friend? If not, rewrite it.
  MUST be UNIQUE — never similar to: {used_list}
- short_seo.description: START with the most shocking sentence from the story (no hashtags at start!), then summary, then "Subscribe to @ToldByNova", then LAST LINE = exactly 3 hashtags (#shorts + 2 story-specific). NEVER start description with a hashtag.
- short_seo.tags: 20 comma-separated tags starting with "shorts", mix trending + story-specific
- All category: Entertainment

CLIP SUGGESTIONS: 5-6 search keywords matching STORY MOOD (not generic). 2-4 words each."""

    task_label = "Generate 1 viral YouTube story with a short script PLUS SEO"

    prompt = f"""TASK: {task_label}. Output ONLY raw JSON, no markdown, no code blocks.

Channel: "Told By Nova" — female narrator, real viral true stories for USA audience.

IMPORTANT: Search the web for REAL trending viral stories from Reddit (ProRevenge, AITA, MaliciousCompliance, NuclearRevenge, ChoosingBeggars, EntitledPeople), TMZ, court news. Find DRAMA/REVENGE/KARMA stories from last 1-2 months. Base your script on a REAL story — do NOT invent stories.

CRITICAL: The story MUST have a BIZARRE/UNUSUAL angle. Generic "boss was mean" or "neighbor was rude" stories get ZERO views. Find stories with ABSURD specific details — the kind of detail that makes someone say "wait, WHAT?" and share it with friends. Examples: sued over Red Bull wings, broke into house at 3 AM over a lawn, faked kidnapping for attention. If your story sounds like it could happen to anyone — it is TOO BORING. Find the WEIRD ones.

REMINDER: NO math, NO science, NO professors, NO genius stories, NO universities, NO inspirational academic stories. ONLY revenge, karma, drama, cheating, betrayal, court cases, neighbor wars, Karen stories. If your story has anything to do with education or academics — START OVER.

{base_rules}

DO NOT repeat these stories: {used_list}

RESPOND WITH ONLY THIS JSON (no other text):
{json_format}

mood must be exactly one of: emotional, suspense, dramatic, uplifting, dark"""

    web_stories = search_viral_stories()
    if web_stories:
        web_section = f"""REAL STORIES FROM THE WEB — you MUST base your story on one of these:
{web_stories}

Pick 1 story from above. Rewrite as a narration script in your own words. Do NOT copy text verbatim."""
    else:
        web_section = "Write a REAL viral story: Reddit revenge, karma, court drama, relationship betrayal (USA only). NEVER educational or inspirational."

    trending_kw = search_trending_keywords("reddit revenge karma viral story")
    trending_for_ollama = f"\nTRENDING TOPICS (use these for inspiration):\n{trending_kw}" if trending_kw else ""

    ollama_prompt = f"""TASK: {task_label}. Output ONLY raw JSON, no markdown, no code blocks.

Channel: "Told By Nova" - female narrator, real viral true stories for USA audience.

{web_section}
{trending_for_ollama}

{base_rules}

DO NOT repeat these stories: {used_list}

RESPOND WITH ONLY THIS JSON (no other text):
{json_format}

mood must be exactly one of: emotional, suspense, dramatic, uplifting, dark

NOTE: You cannot search the web. Use the stories and trending topics provided above."""

    BANNED_WORDS = [
        "math", "equation", "theorem", "professor", "university", "MIT", "Harvard",
        "NASA", "Nobel", "Fields Medal", "PhD", "physics", "chemistry", "biology",
        "scientist", "research paper", "discovery", "invention", "blackboard",
        "lecture", "exam", "homework", "genius solved", "janitor solved",
        "hidden genius", "secret genius", "solved a problem", "solved the equation",
        "million-dollar problem", "unsolvable", "mathematical", "scientific",
        "encyclopedia", "quantum", "relativity", "periodic table", "laboratory",
        "dissertation", "scholarship", "valedictorian", "academic", "scholar",
        "chalkboard", "janitor", "mopping", "custodian",
    ]

    RETRY_TOPICS = [
        "Write about a CHEATING WIFE caught by husband who got ultimate divorce revenge. She lost the house, the car, and her affair partner dumped her.",
        "Write about a TOXIC BOSS who fired a loyal employee. The employee sued, won $2M, and the boss got fired by corporate. Classic workplace revenge.",
        "Write about a KAREN NEIGHBOR who kept calling cops on a family. The family set up cameras, caught the Karen vandalizing, and she got arrested. Neighbor karma.",
        "Write about an INHERITANCE FIGHT where greedy siblings tried to steal everything. The quiet sibling had a secret will copy and exposed them at the reading. Family betrayal.",
        "Write about a LANDLORD FROM HELL who refused repairs and kept the deposit. Tenant took them to court, won triple damages, landlord lost the property.",
        "Write about a WEDDING DISASTER where the groom's ex showed up and exposed his double life. Bride walked out and got the ultimate revenge.",
    ]

    def _is_banned_story(story_dict):
        check = ((story_dict.get("title") or "") + " " + (story_dict.get("script") or "") + " " + (story_dict.get("hook") or "")).lower()
        for bw in BANNED_WORDS:
            if bw.lower() in check:
                return bw
        return None

    rejected_titles = []
    for attempt in range(5):
        if attempt == 0:
            cur_prompt = prompt
            cur_ollama = ollama_prompt
        else:
            topic = random.choice(RETRY_TOPICS)
            reject_note = f"PREVIOUS REJECTED: {', '.join(rejected_titles)}. " if rejected_titles else ""
            topic_override = f"""YOUR STORY MUST BE ABOUT: {topic}
{reject_note}ABSOLUTELY NO math, science, professors, universities, genius stories, janitors, academic content."""
            cur_prompt = prompt.replace(
                "IMPORTANT: Search the web for REAL trending viral stories",
                f"{topic_override}\n\nIMPORTANT: Search the web for REAL trending viral stories"
            )
            cur_ollama = ollama_prompt.replace(
                web_section,
                f"{topic_override}\n\n{web_section}"
            ) if web_section in ollama_prompt else cur_prompt

        result = claude_run(cur_prompt, 300, ollama_prompt=cur_ollama, min_words=100)
        if not result:
            print(f"generate_stories attempt {attempt+1}/5: claude_run returned None")
            if attempt < 4:
                continue
            return None

        print(f"generate_stories attempt {attempt+1}/5: got {len(result)} chars")
        parsed = parse_claude_json(result, "generate_stories")
        if not parsed or "stories" not in parsed:
            if attempt < 4:
                print(f"generate_stories attempt {attempt+1}/5: no valid stories, retrying...")
                continue
            return parsed

        rejected = False
        used_lower = [t.lower().strip() for t in used]
        used_hashes = set(h.get("hash", "") for h in load_history())
        for s in parsed["stories"]:
            banned = _is_banned_story(s)
            if banned:
                rej_title = s.get("title") or "unknown"
                print(f"[generate_stories] REJECTED - banned topic '{banned}' in: {rej_title}")
                rejected_titles.append(rej_title)
                rejected = True
                break
            gen_title = (s.get("title") or "").lower().strip()
            gen_hash = hashlib.md5((s.get("script") or "").encode()).hexdigest()
            if gen_title and gen_title in used_lower:
                print(f"[generate_stories] REJECTED - duplicate title: {s.get('title')}")
                rejected_titles.append(s.get("title", ""))
                rejected = True
                break
            if gen_hash in used_hashes:
                print(f"[generate_stories] REJECTED - duplicate script hash: {gen_hash}")
                rejected_titles.append(s.get("title", ""))
                rejected = True
                break
            sc_wc = len((s.get("script") or "").split())
            if sc_wc < 30:
                print(f"[generate_stories] REJECTED - empty short script: {sc_wc}w")
                rejected = True
                break

        if rejected:
            if attempt < 4:
                print(f"[generate_stories] Retrying with specific topic (attempt {attempt+2}/5)...")
                continue
            else:
                print("[generate_stories] All 5 attempts failed (banned or empty)!")
                return None

        return parsed

    return None

def refine_story(raw_text):
    """Refine a user-provided story into a YouTube Shorts narration script."""
    dur = bot.max_duration if bot.max_duration > 0 else random.randint(28, 33)
    words_min = int(dur * 2.5)
    words_max = int(dur * 3)
    cta_options = [
        "Was she wrong? Type YES or NO. Like and subscribe for more.",
        "Would you have done the same? Comment below. Like if you agree.",
        "Who was wrong here? Drop your answer. Hit like and subscribe.",
        "Type 1 if she was right, 2 if he was. Like this and subscribe.",
        "Am I wrong for this? Tell me in the comments. Like and subscribe.",
        "What would you have done? Comment NOW. Double tap and subscribe.",
    ]
    short_cta = random.choice(cta_options)
    json_fmt = f"""{{"title":"Short searchable title","script":"Short narration {words_min}-{words_max} words.","dramatic_words":["word1","word2","word3"],"mood":"dramatic","clip_suggestions":["term1","term2","term3","term4","term5"]}}"""

    prompt = f"""TASK: Rewrite this raw story as a YouTube Shorts narration script. Output ONLY raw JSON, no markdown, no code blocks.

Raw story:
---
{raw_text}
---

SHORT SCRIPT RULES:
- Target: {dur} seconds. Script MUST be {words_min}-{words_max} words (voice reads at ~2.7 words/sec).
- HOOK (first sentence): Shocking statement or question under 10 words that stops the scroll.
- Structure: Hook → Escalation → SECOND HOOK → Twist → CTA → Loop Cliffhanger (LAST LINE)
- SECOND HOOK (at ~14-15 second mark, around word 38-42): Insert a SURPRISE sentence that re-hooks the viewer. Example: "But here's what nobody expected." This is the algorithm's "sustained distribution gate".
- CTA goes BEFORE the loop ending: "{short_cta}" — this reminds viewer to subscribe while tension is high.
- SEAMLESS LOOP TRICK (MANDATORY — VERY LAST LINE): After CTA, the FINAL sentence must be an open-ended cliffhanger so when video loops to the HOOK, viewer thinks story CONTINUES. End with: "But that wasn't even the worst part." / "And then everything changed." / "Little did he know..." / "But what happened next changed everything." NEVER end with: "Justice was served" / "He got what he deserved" / "She won" / "It was finally over". TEST: read your last line → then your hook. Must feel like ONE continuous story.
- NO subscribe/follow CTA in the middle of the story. CTA only near the end, before the loop cliffhanger.
- Short punchy sentences, 1 thought per sentence, natural female narrator voice.

CLIP SUGGESTIONS: Suggest 5-6 search keywords matching STORY MOOD and THEME. NOT generic satisfying/ASMR. 2-4 words each.

RESPOND WITH ONLY THIS JSON:
{json_fmt}

mood must be exactly one of: emotional, suspense, dramatic, uplifting, dark"""

    result = claude_run(prompt, 300, min_words=100)
    if not result:
        return None
    return parse_claude_json(result, "refine_story")



def _sanitize_tags(raw_tags, max_tags=20, max_total=480):
    """Sanitize tags: strip #, remove <>, deduplicate, cap count and length."""
    if isinstance(raw_tags, list):
        raw_tags = ','.join(raw_tags)
    parts = [t.strip() for t in raw_tags.split(',') if t.strip()]
    clean = []
    total_len = 0
    seen = set()
    for t in parts:
        t = t.strip().strip('#').strip()
        t = re.sub(r'[<>]', '', t)
        if not t or len(t) > 100:
            continue
        if t.lower() in seen:
            continue
        if len(clean) >= max_tags:
            break
        if total_len + len(t) + 1 > max_total:
            break
        seen.add(t.lower())
        clean.append(t)
        total_len += len(t) + 1
    return ','.join(clean)


def _sanitize_title(title):
    """Remove hashtags, emojis, and non-ASCII characters from title."""
    title = re.sub(r'#\w+', '', title).strip()
    title = re.sub(r'[^\x00-\x7F]', '', title)
    title = re.sub(r'\s{2,}', ' ', title).strip()
    title = title.strip('—–-_ .')
    return title[:60]


def _sanitize_description(desc, max_hashtags=3):
    """Ensure description starts with hook text, hashtags only at end, max 3."""
    if not desc:
        return desc
    all_hashtags = re.findall(r'#\w+', desc)
    stripped = desc
    for ht in all_hashtags:
        stripped = stripped.replace(ht, '', 1)
    stripped = re.sub(r'[ \t]{2,}', ' ', stripped)
    stripped = re.sub(r'\n{3,}', '\n\n', stripped).strip()
    keep = []
    seen = set()
    for ht in all_hashtags:
        if ht.lower() not in seen and len(keep) < max_hashtags:
            seen.add(ht.lower())
            keep.append(ht)
    if keep:
        stripped = stripped.rstrip('\n') + '\n\n' + ' '.join(keep)
    return stripped.strip()


def _is_title_duplicate(new_title):
    """Check if title is too similar to any previously used title."""
    if not new_title:
        return False
    new_words = set(new_title.lower().split())
    history = load_history()
    for h in history:
        old = h.get("title", "")
        if not old:
            continue
        old_words = set(old.lower().split())
        if not old_words:
            continue
        overlap = len(new_words & old_words)
        similarity = overlap / max(len(new_words), len(old_words))
        if similarity >= 0.6:
            print(f"[SEO] Title too similar: '{new_title}' vs '{old}' ({similarity:.0%})")
            return True
    return False


def _parse_seo_json(result_text):
    """Parse SEO JSON from AI response, handles markdown wrapping. Sanitizes output."""
    try:
        seo = json.loads(result_text)
    except:
        cleaned = re.sub(r'```(?:json)?\s*', '', result_text).strip()
        try:
            match = re.search(r'\{[\s\S]*\}', cleaned)
            seo = json.loads(match.group()) if match else None
        except:
            seo = None

    if not seo or not isinstance(seo, dict):
        return None

    yt_title = (seo.get('yt_title') or seo.get('title') or seo.get('name') or '').strip()
    desc = (seo.get('description') or seo.get('desc') or seo.get('body') or '').strip()
    tags = seo.get('tags') or seo.get('keywords') or seo.get('hashtags') or ''
    cat = seo.get('category', 'Entertainment')

    yt_title = _sanitize_title(yt_title)
    desc = _sanitize_description(desc)
    tags = _sanitize_tags(tags)

    if _is_title_duplicate(yt_title):
        print(f"[SEO] Rejecting duplicate title: {yt_title}")
        return None

    if yt_title and desc and tags:
        result = {"yt_title": yt_title, "description": desc, "tags": tags, "category": cat}
        pinned_comment = (seo.get('pinned_comment') or seo.get('comment') or '').strip()
        if pinned_comment:
            result["pinned_comment"] = pinned_comment[:150]
        return result
    return None


def generate_seo(title, script):
    """Generate viral YouTube Shorts SEO — uses claude_run waterfall."""
    safe_title = title.replace('"', "'").replace('\\', '')
    safe_script = script[:400].replace('"', "'").replace('\\', '')
    print(f"[SEO] Generating Short SEO...")

    desc_rule = (
        "2. description = Use this EXACT structure with blank lines between sections:\n"
        "   LINE 1: Attention-grabbing hook sentence (max 150 chars)\n"
        "   BLANK LINE\n"
        "   LINES 2-4: 2-3 sentence story summary (what happened, who was involved, what went wrong)\n"
        "   BLANK LINE\n"
        "   LAST SECTION: \"Subscribe to @ToldByNova for more true stories.\" then new line "
        "\"Follow @ToldByNova on YouTube for daily stories.\" then new line then exactly 3 hashtags: #shorts plus 2 story-specific"
    )

    seo_rules = f"""Write a JSON object with exactly these 5 keys:
1. yt_title = a searchable viral title about THIS SPECIFIC story. Under 50 characters. No emojis. No hashtags (no #shorts, no #anything). Use curiosity gap.
{desc_rule}
3. tags = a comma-separated string with EXACTLY 20 tags. NEVER use # symbol in tags — just plain words. First tag must be "shorts". Mix: shorts, storytime, viral, reddit stories, true story, justice served, satisfying, revenge, real stories, story time, plus 10 story-specific keywords relevant to USA viewers. Keep total under 480 characters.
4. category = Entertainment
5. pinned_comment = a DEBATE question that forces viewers to pick a side. Under 100 characters. Must use "Type YES/NO", "Comment 1 or 2", "Was she right?", or "Am I wrong?" format. Examples: "Was she wrong for exposing him? Type YES or NO" / "Type 1 if he deserved it, 2 if she went too far"

STRICT RULES:
- Tags must NOT contain # symbol (write "shorts" not "#shorts")
- Title must NOT contain any hashtag
- Maximum 3 hashtags in description (last line only)
- Maximum 20 tags total
- Your entire response must be valid JSON and nothing else. No markdown, no code blocks, no explanation."""

    prompt = f"""Write YouTube Shorts SEO optimized for USA audience. This is a standalone Short. Output ONLY valid JSON, nothing else.

Story title: {safe_title}
Script: {safe_script}
Channel: Told By Nova (female narrator, real viral true stories, USA audience)

IMPORTANT: Search the web for current trending YouTube keywords and hashtags related to this story topic. Use real trending terms in the tags and title.

{seo_rules}"""

    trending = search_trending_keywords(safe_title)
    seo_trends = search_seo_trends(safe_title)
    web_data = ""
    if trending:
        web_data += f"\nTRENDING KEYWORDS (use these in tags and title):\n{trending}\n"
    if seo_trends:
        web_data += f"\nYOUTUBE SEO TRENDS (real data from web - use for inspiration):\n{seo_trends}\n"

    ollama_prompt = f"""Write YouTube Shorts SEO optimized for USA audience. This is a standalone Short. Output ONLY valid JSON, nothing else.

Story title: {safe_title}
Script: {safe_script}
Channel: Told By Nova (female narrator, real viral true stories, USA audience)
{web_data}
{seo_rules}"""

    result = claude_run(prompt, 120, ollama_prompt=ollama_prompt)
    if not result:
        return None
    seo = _parse_seo_json(result)
    if seo:
        print(f"[SEO] Short SEO OK via {_last_ai_source}: {seo['yt_title']}")
    return seo




# ============ VOICE GENERATION ============

def generate_voice(script, vid_id, mood=None):
    """Generate voice + SRT via Edge TTS"""
    sys.path.insert(0, SCRIPTS)
    import voice_generator
    import importlib
    importlib.reload(voice_generator)
    prefix = f"auto_{vid_id}"
    mp3, srt, n_words = voice_generator.run(script, ASSETS, prefix, mood=mood)
    return mp3, srt, n_words

# ============ VIDEO BUILD ============

def build_video(vid_id, progress_bar=None):
    """Build final video using pipeline"""
    sys.path.insert(0, SCRIPTS)
    import pipeline
    import importlib
    importlib.reload(pipeline)

    def _cb(pct, msg):
        print(f"Build: {msg}")
        if progress_bar:
            progress_bar.update(pct, msg)

    output_path = f"{OUTPUT}/nova_{vid_id}.mp4"
    ok, path, details = pipeline.build_video(
        bot.voice_mp3, bot.srt_file, CLIPS_DIR, output_path,
        progress_cb=_cb,
        mood=bot.mood,
        stop_check=is_stopped
    )
    return ok, path, details




# ============ THUMBNAIL GENERATION ============

THUMB_W, THUMB_H = 1280, 720
THUMB_MODEL_CHAIN = ["flux", "gptimage", "gptimage-large", "zimage", "klein", "qwen-image"]
BEBAS_FONT = f"{ASSETS}/channel/BebasNeue-Regular.ttf"
FONT_PATH_FALLBACK = "C:/Windows/Fonts/impact.ttf"

THUMB_MOOD_STYLES = {
    "dramatic": {
        "scene": "dark cinematic revenge scene, deep red and orange dramatic lighting, fire sparks, bold shadows",
        "colors": "red neon glow, black shadows, orange accents",
        "glow_rgb": (220, 30, 30), "highlight_rgb": (255, 60, 60),
    },
    "emotional": {
        "scene": "warm emotional cinematic scene, golden hour sunset light, rain drops, lonely atmosphere",
        "colors": "warm golden tones, amber light, soft shadows",
        "glow_rgb": (255, 215, 0), "highlight_rgb": (255, 200, 0),
    },
    "suspense": {
        "scene": "dark thriller mystery scene, cold blue lighting, fog and shadows, tension",
        "colors": "blue neon glow, cyan accents, deep black shadows",
        "glow_rgb": (30, 144, 255), "highlight_rgb": (0, 200, 255),
    },
    "uplifting": {
        "scene": "bright hopeful cinematic scene, sunrise rays, golden warm light, victory atmosphere",
        "colors": "green and gold tones, warm light rays, bright accents",
        "glow_rgb": (50, 205, 50), "highlight_rgb": (100, 255, 100),
    },
    "dark": {
        "scene": "very dark horror scene, creepy shadows, eerie fog, haunted atmosphere, moonlight",
        "colors": "purple and dark blue glow, deep black, eerie green accents",
        "glow_rgb": (139, 0, 139), "highlight_rgb": (200, 50, 200),
    },
}


def _thumb_build_prompt(title, mood="dramatic"):
    """Build a story-specific AI thumbnail prompt from title + mood."""
    import re as _re
    style = THUMB_MOOD_STYLES.get(mood, THUMB_MOOD_STYLES["dramatic"])

    stop_words = {'ki', 'ka', 'ke', 'ne', 'se', 'ko', 'me', 'mein', 'ek', 'the', 'a', 'an',
                  'in', 'on', 'of', 'and', 'or', 'for', 'to', 'is', 'was', 'hai', 'tha',
                  'thi', 'ye', 'wo', 'jo', 'kya', 'kaise', 'jab', 'tab', 'fir', 'phir',
                  'bhi', 'hi', 'par', 'per', 'apni', 'apne', 'apna', 'uski', 'uska', 'uske',
                  'meri', 'mera', 'mere', 'teri', 'tera', 'tere', 'kuch', 'bahut', 'bohot',
                  'nhi', 'nahi', 'hota', 'hoti', 'kab', 'aur', 'lekin', 'magar', 'jisse'}
    title_words = _re.sub(r'[^a-zA-Z\s]', '', title.lower()).split()
    keywords = [w for w in title_words if w not in stop_words and len(w) > 2][:5]
    keyword_str = ", ".join(keywords) if keywords else ""

    short_title = title.upper()
    if len(short_title) > 40:
        key_parts = [w for w in title.upper().split() if len(w) > 2][:5]
        short_title = " ".join(key_parts)

    return (
        f"Professional viral YouTube thumbnail for a story titled \"{title}\", "
        f"16:9 ratio, {style['scene']}, {keyword_str}, "
        f"{style['colors']}, "
        f"big bold white text with thick black stroke and {style['colors'].split(',')[0]} glow effect "
        f"saying \"{short_title}\" positioned at bottom right of image, "
        f"dark mysterious silhouette figure on left side with rim light, "
        f"cinematic depth of field, dramatic volumetric lighting, "
        f"dark vignette edges, film grain texture, "
        f"faceless story channel style, professional YouTube thumbnail design, ultra detailed 8k"
    )


def generate_thumbnail(title, mood="dramatic", save_path=None):
    """Generate complete YouTube thumbnail via AI API. Pillow fallback if all APIs fail."""
    from io import BytesIO

    if not save_path:
        save_path = f"{OUTPUT}/thumb_{int(time.time())}.jpg"

    full_prompt = _thumb_build_prompt(title, mood)
    print(f"[THUMB] Story: {title} | Mood: {mood}")

    # ── PRIMARY: AI API generation (try all models) ──
    for model in THUMB_MODEL_CHAIN:
        seed = random.randint(10000, 999999)
        encoded = urllib.request.quote(full_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={THUMB_W}&height={THUMB_H}&seed={seed}&nologo=true&model={model}"
        print(f"[THUMB] Trying {model} (seed={seed})...")

        for attempt in range(2):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    ct = resp.headers.get("Content-Type", "")
                    data = resp.read()
                    if len(data) > 5000 and "image" in ct:
                        from PIL import Image as PILImage
                        img = PILImage.open(BytesIO(data)).convert("RGB").resize((THUMB_W, THUMB_H), PILImage.LANCZOS)
                        img.save(save_path, "JPEG", quality=95)
                        print(f"[THUMB] OK — {model}, {len(data)//1024}KB → {save_path}")
                        return save_path
                    print(f"[THUMB] {model} attempt {attempt+1}: size={len(data)}, type={ct}")
            except Exception as e:
                print(f"[THUMB] {model} attempt {attempt+1}: {e}")
            if attempt < 1:
                time.sleep(10)

        print(f"[THUMB] {model} failed, trying next...")
        time.sleep(5)

    # ── FALLBACK: Pillow-based thumbnail (all APIs failed) ──
    print("[THUMB] All AI models failed — using Pillow fallback...")
    return _generate_thumbnail_pillow(title, mood, save_path)


def _generate_thumbnail_pillow(title, mood, save_path):
    """Pillow fallback: dark gradient bg + silhouette + text with glow/stroke."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        import numpy as np
    except ImportError as e:
        print(f"[THUMB-PILLOW] Missing dependency: {e}")
        return None

    try:
        style = THUMB_MOOD_STYLES.get(mood, THUMB_MOOD_STYLES["dramatic"])
        glow_color = style["glow_rgb"]
        highlight_color = style["highlight_rgb"]

        # Dark gradient background
        bg = Image.new("RGBA", (THUMB_W, THUMB_H), (15, 10, 20, 255))
        draw = ImageDraw.Draw(bg)
        for y in range(THUMB_H):
            r = int(15 + 25 * (y / THUMB_H))
            g = int(10 + 15 * (y / THUMB_H))
            b = int(20 + 30 * (y / THUMB_H))
            draw.line([(0, y), (THUMB_W, y)], fill=(r, g, b, 255))

        # Mood-colored accent glow (top-right area)
        glow_overlay = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_overlay)
        cx, cy = int(THUMB_W * 0.75), int(THUMB_H * 0.25)
        for r in range(300, 0, -2):
            a = int(40 * (1 - r / 300))
            gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*glow_color, a))
        bg = Image.alpha_composite(bg, glow_overlay)

        # Bottom + left gradient for text area
        grad = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
        gd2 = ImageDraw.Draw(grad)
        for y in range(int(THUMB_H * 0.35), THUMB_H):
            progress = (y - THUMB_H * 0.35) / (THUMB_H * 0.65)
            a = int(200 * progress * progress)
            gd2.line([(0, y), (THUMB_W, y)], fill=(0, 0, 0, min(a, 220)))
        for x in range(int(THUMB_W * 0.35)):
            progress = 1 - x / (THUMB_W * 0.35)
            a = int(120 * progress * progress)
            gd2.line([(x, 0), (x, THUMB_H)], fill=(0, 0, 0, a))
        bg = Image.alpha_composite(bg, grad)

        # Silhouette on left
        sil = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sil)
        sx = int(THUMB_W * 0.18)
        head_y, head_r = int(THUMB_H * 0.28), 45
        for r in range(head_r + 20, head_r, -1):
            al = int(80 * (1 - (r - head_r) / 20))
            sd.ellipse([sx - r, head_y - r, sx + r, head_y + r], fill=(0, 0, 0, al))
        sd.ellipse([sx - head_r, head_y - head_r, sx + head_r, head_y + head_r], fill=(0, 0, 0, 200))
        bt, bb = head_y + head_r, int(THUMB_H * 0.92)
        body = [(sx - 85, bt), (sx + 85, bt), (sx + 55, bb), (sx - 55, bb)]
        for exp in range(25, 0, -1):
            al = int(50 * (1 - exp / 25))
            ep = [(px + (-exp if px < sx else exp), py) for px, py in body]
            sd.polygon(ep, fill=(0, 0, 0, al))
        sd.polygon(body, fill=(0, 0, 0, 200))
        bg = Image.alpha_composite(bg, sil)

        # Rim light
        rim = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
        rd = ImageDraw.Draw(rim)
        for i in range(60):
            a = int(40 * (1 - i / 60))
            rd.line([(0, i), (THUMB_W, i)], fill=(*glow_color, a))
        for i in range(40):
            a = int(30 * (1 - i / 40))
            rd.line([(THUMB_W - i, 0), (THUMB_W - i, THUMB_H)], fill=(*glow_color, a))
        bg = Image.alpha_composite(bg, rim)

        # Text
        font_size = 120
        font = ImageFont.load_default()
        for p in [BEBAS_FONT, FONT_PATH_FALLBACK]:
            if os.path.exists(p):
                try:
                    font = ImageFont.truetype(p, font_size)
                    break
                except:
                    continue

        words = title.upper().split()
        lines, current = [], ""
        temp_draw = ImageDraw.Draw(bg)
        max_text_w = int(THUMB_W * 0.55)
        for w in words:
            test = f"{current} {w}".strip()
            bbox = temp_draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_text_w:
                if current:
                    lines.append(current)
                current = w
            else:
                current = test
        if current:
            lines.append(current)
        lines = lines[:3]

        line_h = int(font_size * 1.15)
        total_h = len(lines) * line_h
        y_start = THUMB_H - 50 - total_h
        text_x_start = int(THUMB_W * 0.43)

        for i, line in enumerate(lines):
            cx = text_x_start + (THUMB_W - text_x_start) // 2
            cy = y_start + i * line_h

            shadow_layer = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
            ImageDraw.Draw(shadow_layer).text((cx + 6, cy + 6), line, font=font, fill=(0, 0, 0, 180), anchor="mm")
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(4))
            bg = Image.alpha_composite(bg, shadow_layer)

            glow_layer = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
            for dx in range(-3, 4, 2):
                for dy in range(-3, 4, 2):
                    ImageDraw.Draw(glow_layer).text((cx + dx, cy + dy), line, font=font, fill=(*glow_color, 100), anchor="mm")
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(8))
            bg = Image.alpha_composite(bg, glow_layer)

            draw = ImageDraw.Draw(bg)
            for dx in range(-5, 6):
                for dy in range(-5, 6):
                    if dx * dx + dy * dy <= 25:
                        draw.text((cx + dx, cy + dy), line, font=font, fill=(0, 0, 0, 255), anchor="mm")

            line_words = line.split()
            bbox_full = font.getbbox(line)
            full_w = bbox_full[2] - bbox_full[0]
            wx = cx - full_w // 2
            for wi, word in enumerate(line_words):
                color = highlight_color if wi == 0 else (255, 255, 255)
                draw.text((wx, cy), word, font=font, fill=(*color, 255), anchor="lm")
                wbbox = font.getbbox(word + " ")
                wx += wbbox[2] - wbbox[0]

        # Vignette
        vignette = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
        vd = ImageDraw.Draw(vignette)
        for i in range(80):
            a = int(180 * (1 - i / 80))
            vd.rectangle([i, i, THUMB_W - i, THUMB_H - i], outline=(0, 0, 0, a))
        bg = Image.alpha_composite(bg, vignette)

        # Film grain + sharpen
        final = bg.convert("RGB")
        arr = np.array(final).astype(float)
        noise = np.random.normal(0, 8, arr.shape)
        final = Image.fromarray(np.clip(arr + noise, 0, 255).astype("uint8"))
        final = final.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=2))
        final.save(save_path, "JPEG", quality=92)
        sz = os.path.getsize(save_path) / 1024
        print(f"[THUMB-PILLOW] Fallback generated: {save_path} ({sz:.0f}KB)")
        return save_path
    except Exception as e:
        print(f"[THUMB-PILLOW] Fallback error: {e}")
        import traceback; traceback.print_exc()
        return None


def _yt_token_path():
    home = "C:/Users/chatu/mcp-servers/youtube-mcp-server/token.json"
    office = f"{DATA_DIR}/yt_token_1.json"
    return home if os.path.exists(home) else office

def _get_youtube_client():
    """Build authenticated YouTube API client. Used by new post-upload features."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build as yt_build
    token_path = _yt_token_path()
    with open(token_path) as f:
        td = json.load(f)
    creds = Credentials(
        token=td['token'], refresh_token=td['refresh_token'],
        token_uri='https://oauth2.googleapis.com/token',
        client_id=td['client_id'], client_secret=td['client_secret'],
        scopes=td.get('scopes', ['https://www.googleapis.com/auth/youtube']))
    if creds.expired or not creds.valid:
        creds.refresh(Request())
    return yt_build('youtube', 'v3', credentials=creds)


def _get_channel_comments(video_id):
    """Get all top-level comments by the channel owner on a video."""
    try:
        youtube = _get_youtube_client()
        resp = youtube.commentThreads().list(
            part="snippet", videoId=video_id, maxResults=100
        ).execute()
        channel_id = None
        try:
            ch = youtube.channels().list(part="id", mine=True).execute()
            channel_id = ch["items"][0]["id"]
        except:
            pass
        owner_comments = []
        for item in resp.get("items", []):
            snip = item["snippet"]["topLevelComment"]["snippet"]
            author_id = snip.get("authorChannelId", {}).get("value", "")
            if channel_id and author_id == channel_id:
                owner_comments.append({
                    "id": item["snippet"]["topLevelComment"]["id"],
                    "text": snip.get("textOriginal", ""),
                    "thread_id": item["id"]
                })
        return owner_comments
    except Exception as e:
        print(f"[COMMENT] Failed to get comments for {video_id}: {e}")
        return []

def post_pinned_comment(video_id, comment_text):
    """Post a comment on the video as channel owner. Skips if already commented."""
    if not comment_text:
        return False
    try:
        existing = _get_channel_comments(video_id)
        if existing:
            print(f"[COMMENT] Already {len(existing)} owner comment(s) on {video_id}, skipping")
            return True
        youtube = _get_youtube_client()
        resp = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": comment_text}
                    }
                }
            }
        ).execute()
        cid = resp["snippet"]["topLevelComment"]["id"]
        print(f"[COMMENT] Posted on {video_id}: {cid}")
        return True
    except Exception as e:
        print(f"[COMMENT] Failed on {video_id}: {e}")
        return False

def delete_duplicate_comments(video_id):
    """Delete all but the first owner comment on a video."""
    try:
        existing = _get_channel_comments(video_id)
        if len(existing) <= 1:
            return 0
        youtube = _get_youtube_client()
        deleted = 0
        for comment in existing[1:]:
            try:
                youtube.comments().delete(id=comment["id"]).execute()
                deleted += 1
                print(f"[COMMENT] Deleted duplicate {comment['id']} on {video_id}")
            except Exception as e:
                print(f"[COMMENT] Failed to delete {comment['id']}: {e}")
        return deleted
    except Exception as e:
        print(f"[COMMENT] Cleanup failed for {video_id}: {e}")
        return 0


def _save_job(job):
    """Save a background job to persistent file so it survives restarts."""
    jobs = load_json(JOBS_FILE, [])
    jobs = [j for j in jobs if j.get("id") != job["id"]]
    jobs.append(job)
    save_json(JOBS_FILE, jobs)
    print(f"[JOBS] Saved: {job['id']} ({job['type']})")


def _remove_job(job_id):
    """Remove a completed job from persistent file."""
    jobs = load_json(JOBS_FILE, [])
    jobs = [j for j in jobs if j.get("id") != job_id]
    save_json(JOBS_FILE, jobs)
    print(f"[JOBS] Removed: {job_id}")

def _claim_job(job_id):
    """Claim a job for this system. Returns True if claimed, False if already claimed by another."""
    import datetime as _dt
    jobs = load_json(JOBS_FILE, [])
    for job in jobs:
        if job.get("id") == job_id:
            claimed = job.get("claimed_by")
            if claimed and claimed != _lock_system_name:
                claim_time = job.get("claimed_at", "")
                try:
                    ct = _dt.datetime.fromisoformat(claim_time.replace("Z", "+00:00"))
                    age = (_dt.datetime.now(_dt.timezone.utc) - ct).total_seconds()
                    if age < 3600:
                        return False
                except:
                    return False
            job["claimed_by"] = _lock_system_name
            job["claimed_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
            break
    else:
        return False
    save_json(JOBS_FILE, jobs)
    return True


def _wait_for_video_public(video_id, publish_at=None, max_wait_hours=48):
    """Wait until a scheduled video becomes public. Returns True when public."""
    import datetime as _dt
    if publish_at:
        try:
            pub_time = _dt.datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
            now = _dt.datetime.now(_dt.timezone.utc)
            wait_secs = (pub_time - now).total_seconds()
            if wait_secs > 0:
                print(f"[DEFER] Waiting {wait_secs/3600:.1f}h until {video_id} goes live")
                time.sleep(max(0, wait_secs + 120))
        except:
            pass
    for attempt in range(max_wait_hours * 6):
        try:
            youtube = _get_youtube_client()
            resp = youtube.videos().list(part="status", id=video_id).execute()
            if resp.get("items"):
                status = resp["items"][0]["status"].get("privacyStatus", "")
                if status == "public":
                    print(f"[DEFER] Video {video_id} is now public!")
                    return True
        except:
            pass
        time.sleep(600)
    print(f"[DEFER] Timeout waiting for {video_id} to go public")
    return False


def _deferred_post_upload(video_id, comment_text, publish_at=None, job_id=None):
    """Background thread: wait for video to go public, then post comment + start auto-reply."""
    try:
        if not _wait_for_video_public(video_id, publish_at):
            return
        if job_id:
            _remove_job(job_id)
        if comment_text:
            ok = post_pinned_comment(video_id, comment_text)
            if ok:
                _send_admin_msg(f"Pinned comment posted on {video_id}")
        _auto_reply_comments(video_id)
    finally:
        if job_id:
            _active_comment_threads.discard(job_id)


def schedule_post_upload(video_id, comment_text, publish_at=None):
    """Schedule pinned comment + auto-reply for after video goes live. Persists to disk."""
    import datetime as _dt
    job_id = f"comment_{video_id}"
    if publish_at:
        _save_job({
            "id": job_id, "type": "post_comment",
            "video_id": video_id, "comment_text": comment_text,
            "publish_at": publish_at,
            "created": _dt.datetime.now(_dt.timezone.utc).isoformat()
        })
        _active_comment_threads.add(job_id)
        threading.Thread(target=_deferred_post_upload,
                        args=(video_id, comment_text, publish_at, job_id), daemon=False).start()
    else:
        if comment_text:
            post_pinned_comment(video_id, comment_text)
        start_auto_reply(video_id)


def upload_captions(video_id, srt_file):
    """Upload SRT file as closed captions for a YouTube video."""
    if not srt_file or not os.path.exists(srt_file):
        print(f"[CAPTIONS] SRT not found: {srt_file}")
        return False
    try:
        youtube = _get_youtube_client()
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(srt_file, mimetype='application/x-subrip', resumable=False)
        youtube.captions().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "language": "en",
                    "name": "English",
                    "isDraft": False
                }
            },
            media_body=media
        ).execute()
        print(f"[CAPTIONS] Uploaded for {video_id}")
        return True
    except Exception as e:
        print(f"[CAPTIONS] Failed for {video_id}: {e}")
        return False


def _translate_srt(srt_path, target_lang, lang_code):
    """Translate an SRT file to target language using AI. Returns new SRT path or None."""
    if not srt_path or not os.path.exists(srt_path):
        return None
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        if len(srt_content.strip()) < 20:
            return None
        prompt = f"""Translate the following SRT subtitle file to {target_lang}.
Keep ALL SRT formatting exactly the same (sequence numbers, timestamps, blank lines).
Only translate the text lines. Do NOT translate numbers or timestamps.
Output ONLY the translated SRT content, nothing else.

{srt_content}"""
        result = claude_run(prompt, timeout=90)
        if not result or len(result.strip()) < 20:
            print(f"[CAPTIONS] {target_lang} translation too short/empty")
            return None
        lines = result.strip().split('\n')
        cleaned = []
        started = False
        for line in lines:
            stripped = line.strip()
            if not started and stripped.isdigit():
                started = True
            if started:
                cleaned.append(line)
        if len(cleaned) < 4:
            return None
        out_path = srt_path.replace('.srt', f'_{lang_code}.srt')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(cleaned))
        print(f"[CAPTIONS] Translated to {target_lang}: {out_path}")
        return out_path
    except Exception as e:
        print(f"[CAPTIONS] {target_lang} translation failed: {e}")
        return None


def upload_multilang_captions(video_id, srt_file):
    """Upload English + translated captions for high-CPM countries."""
    uploaded = []
    if upload_captions(video_id, srt_file):
        uploaded.append("English")
    for lang_name, lang_code in [("Spanish", "es"), ("French", "fr"), ("German", "de"), ("Portuguese", "pt")]:
        translated = _translate_srt(srt_file, lang_name, lang_code)
        if translated and os.path.exists(translated):
            try:
                youtube = _get_youtube_client()
                from googleapiclient.http import MediaFileUpload
                media = MediaFileUpload(translated, mimetype='application/x-subrip', resumable=False)
                youtube.captions().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "videoId": video_id,
                            "language": lang_code,
                            "name": lang_name,
                            "isDraft": False
                        }
                    },
                    media_body=media
                ).execute()
                uploaded.append(lang_name)
                print(f"[CAPTIONS] {lang_name} uploaded for {video_id}")
            except Exception as e:
                print(f"[CAPTIONS] {lang_name} upload failed: {e}")
            finally:
                try: os.remove(translated)
                except: pass
    return uploaded


def _auto_reply_comments(video_id, duration_minutes=60, max_replies=5):
    """Poll for new comments on a video and auto-reply. Runs in background thread."""
    replied = set()
    reply_count = 0
    start = time.time()
    print(f"[COMMENTS] Auto-reply started for {video_id} ({duration_minutes}min, max {max_replies})")

    reply_templates = [
        "Right?! What would YOU have done though? I need to know 👀",
        "This one was WILD. But wait till you see tomorrow's story 🔥",
        "Exactly! But do you think they went too far? Be honest 💭",
        "You're so right! Like and subscribe if you want part 2 of this 👆",
        "I couldn't believe it either! Drop a 🔥 if you want more stories like this",
        "The real question is... was it justified? Tell me below 👇",
        "Your take is interesting! But what about the other side? 🤔",
        "Facts! Share this with someone who needs to hear it 📲",
    ]

    while time.time() - start < duration_minutes * 60 and reply_count < max_replies:
        try:
            youtube = _get_youtube_client()
            resp = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                order="time",
                maxResults=20
            ).execute()

            for item in resp.get("items", []):
                if reply_count >= max_replies:
                    break
                cid = item["id"]
                if cid in replied:
                    continue
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                author_channel = snippet.get("authorChannelId", {}).get("value", "")
                channel_resp = youtube.channels().list(part="snippet", mine=True).execute()
                my_channel = channel_resp["items"][0]["id"] if channel_resp.get("items") else ""
                if author_channel == my_channel:
                    replied.add(cid)
                    continue
                reply_text = reply_templates[reply_count % len(reply_templates)]
                youtube.comments().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "parentId": cid,
                            "textOriginal": reply_text
                        }
                    }
                ).execute()
                replied.add(cid)
                reply_count += 1
                author = snippet.get("authorDisplayName", "?")
                print(f"[COMMENTS] Replied to {author} on {video_id} ({reply_count}/{max_replies})")
        except Exception as e:
            print(f"[COMMENTS] Poll error: {e}")
        if reply_count < max_replies:
            time.sleep(120)

    print(f"[COMMENTS] Auto-reply done for {video_id}: {reply_count} replies sent")


def start_auto_reply(video_id):
    """Start auto-reply in background thread."""
    threading.Thread(target=_auto_reply_comments, args=(video_id,), daemon=True).start()
    print(f"[COMMENTS] Auto-reply thread started for {video_id}")




def _check_video_is_public(video_id):
    """Quick check if a video is already public. Returns True/False/None on error."""
    try:
        youtube = _get_youtube_client()
        resp = youtube.videos().list(part="status", id=video_id).execute()
        if resp.get("items"):
            return resp["items"][0]["status"].get("privacyStatus") == "public"
        return False
    except:
        return None


_last_job_check = 0
_active_comment_threads = set()

def _periodic_job_check():
    """Called from main loop every ~5 min. Catches jobs where threads died."""
    global _last_job_check
    now = time.time()
    if now - _last_job_check < 300:
        return
    _last_job_check = now
    try:
        jobs = load_json(JOBS_FILE, [])
    except:
        return
    if not jobs:
        return
    for job in jobs:
        try:
            if job.get("type") != "post_comment":
                continue
            vid = job.get("video_id")
            jid = job.get("id")
            if jid in _active_comment_threads:
                continue
            if not _claim_job(jid):
                continue
            is_public = _check_video_is_public(vid)
            if is_public:
                print(f"[JOBS-CHECK] {vid} is public — posting comment now")
                _remove_job(jid)
                comment = job.get("comment_text") or "Was this justified? Type YES or NO below!"
                ok = post_pinned_comment(vid, comment)
                if ok:
                    _send_admin_msg(f"Pinned comment posted on {vid}")
        except Exception as _je:
            print(f"[JOBS-CHECK] Error processing job: {_je}")


def _resume_pending_jobs():
    """On bot startup, resume any pending background jobs from disk."""
    jobs = load_json(JOBS_FILE, [])
    if not jobs:
        return
    print(f"[JOBS] Resuming {len(jobs)} pending jobs from previous session...")
    for job in jobs:
        jtype = job.get("type")
        vid = job.get("video_id")
        jid = job.get("id")
        if not _claim_job(jid):
            print(f"[JOBS] Skipping {jid} — claimed by another system")
            continue
        if jtype == "post_comment":
            is_public = _check_video_is_public(vid)
            if is_public:
                print(f"[JOBS] Video {vid} already public — posting comment immediately")
                _remove_job(jid)
                comment = job.get("comment_text") or "Was this justified? Type YES or NO below!"
                ok = post_pinned_comment(vid, comment)
                if ok:
                    _send_admin_msg(f"Pinned comment posted on {vid}")
            else:
                fallback_comment = job.get("comment_text") or "Was this justified? Type YES or NO below!"
                _active_comment_threads.add(jid)
                threading.Thread(target=_deferred_post_upload,
                    args=(vid, fallback_comment, job.get("publish_at"), jid),
                    daemon=False).start()
                print(f"[JOBS] Resumed comment+reply for {vid} (waiting for public)")
        elif jtype == "ab_test":
            _remove_job(jid)
            print(f"[JOBS] Removed old A/B test job for {vid}")
        else:
            print(f"[JOBS] Unknown job type: {jtype}, removing")
            _remove_job(jid)


_playlist_cache = {}

PLAYLIST_FULL = "Told By Nova | Full Stories"
PLAYLIST_ALL = "Told By Nova | True Stories"


def _get_or_create_playlist(youtube, title):
    """Find existing playlist by title or create it. Caches result."""
    if title in _playlist_cache:
        return _playlist_cache[title]
    try:
        playlists = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
        for pl in playlists.get("items", []):
            if pl["snippet"]["title"] == title:
                _playlist_cache[title] = pl["id"]
                return pl["id"]
    except Exception as e:
        print(f"[PLAYLIST] List error: {e}")
    try:
        resp = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {"title": title, "description": f"Videos from Told By Nova - {title}"},
                "status": {"privacyStatus": "public"}
            }
        ).execute()
        pid = resp["id"]
        _playlist_cache[title] = pid
        print(f"[PLAYLIST] Created '{title}': {pid}")
        return pid
    except Exception as e:
        print(f"[PLAYLIST] Create error '{title}': {e}")
        return None


def add_to_playlist(video_id):
    """Add video to playlists."""
    try:
        youtube = _get_youtube_client()
        playlists = [PLAYLIST_ALL]
        added = []
        for pl_name in playlists:
            pl_id = _get_or_create_playlist(youtube, pl_name)
            if not pl_id:
                continue
            try:
                youtube.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": pl_id,
                            "resourceId": {"kind": "youtube#video", "videoId": video_id}
                        }
                    }
                ).execute()
                added.append(pl_name)
            except Exception as e:
                print(f"[PLAYLIST] Add to '{pl_name}' failed: {e}")
        if added:
            print(f"[PLAYLIST] {video_id} added to: {', '.join(added)}")
        return len(added) > 0
    except Exception as e:
        print(f"[PLAYLIST] Error: {e}")
        return False


def generate_community_post(title, video_id):
    """Generate community post text ready for copy-paste to YouTube Studio."""
    url = f"https://youtu.be/{video_id}"
    text = (
        f"New story just posted!\n\n"
        f"🎬 {title}\n\n"
        f"Watch now → {url}\n\n"
        f"Would you have done the same thing? Comment below! 👇"
    )
    return text


def set_youtube_thumbnail(video_id, thumbnail_path):
    """Upload custom thumbnail to YouTube video."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build as yt_build
        from googleapiclient.http import MediaFileUpload

        token_path = _yt_token_path()
        with open(token_path) as f:
            td = json.load(f)

        creds = Credentials(
            token=td['token'], refresh_token=td['refresh_token'],
            token_uri='https://oauth2.googleapis.com/token',
            client_id=td['client_id'], client_secret=td['client_secret'],
            scopes=td.get('scopes', ['https://www.googleapis.com/auth/youtube']))
        if creds.expired or not creds.valid:
            creds.refresh(Request())

        youtube = yt_build('youtube', 'v3', credentials=creds)
        media = MediaFileUpload(thumbnail_path, mimetype='image/jpeg')
        youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
        print(f"[THUMB] Uploaded thumbnail for {video_id}")
        return True
    except Exception as e:
        print(f"[THUMB] Upload failed: {e}")
        return False


# ============ YOUTUBE UPLOAD ============

def upload_to_youtube(video_path, yt_title, description, tags, category=None, publish_at=None,
                      progress_bar=None):
    """Upload video to YouTube via API. If publish_at is set, schedules as private."""
    cat_id = "22"
    if category:
        cat_lower = category.lower()
        if "entertainment" in cat_lower:
            cat_id = "24"
        elif "people" in cat_lower or "blog" in cat_lower:
            cat_id = "22"
    cat_name = "Entertainment" if cat_id == "24" else "People & Blogs"

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build as yt_build
        from googleapiclient.http import MediaFileUpload

        token_path = _yt_token_path()
        with open(token_path) as f:
            td = json.load(f)

        creds = Credentials(
            token=td['token'], refresh_token=td['refresh_token'],
            token_uri='https://oauth2.googleapis.com/token',
            client_id=td['client_id'], client_secret=td['client_secret'],
            scopes=td.get('scopes', ['https://www.googleapis.com/auth/youtube']))

        if creds.expired or not creds.valid:
            creds.refresh(Request())

        import socket
        socket.setdefaulttimeout(600)
        youtube = yt_build('youtube', 'v3', credentials=creds)

        raw_tags = tags if isinstance(tags, list) else [t.strip() for t in tags.split(',') if t.strip()]
        tag_list = []
        total_len = 0
        seen = set()
        for t in raw_tags:
            t = t.strip().strip('#').strip()
            t = re.sub(r'[<>]', '', t)
            if not t or len(t) > 100:
                continue
            if t.lower() in seen:
                continue
            if total_len + len(t) + 1 > 480:
                break
            seen.add(t.lower())
            tag_list.append(t)
            total_len += len(t) + 1
        print(f"Upload tags: {len(tag_list)} tags, {total_len} chars")

        status = {
            "privacyStatus": "private" if publish_at else "public",
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
            "license": "youtube",
            "publicStatsViewable": True,
        }
        if publish_at:
            status["publishAt"] = publish_at

        clean_title = re.sub(r'#\w+', '', yt_title).strip()
        if not clean_title:
            clean_title = yt_title

        body = {
            "snippet": {
                "title": clean_title,
                "description": description,
                "tags": tag_list,
                "categoryId": cat_id,
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en",
            },
            "status": status,
            "recordingDetails": {
                "location": {
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                },
                "locationDescription": "New York, USA",
            },
        }
        print(f"Upload category: {cat_name} (ID: {cat_id})")

        def _fresh_upload():
            m = MediaFileUpload(video_path, chunksize=10*1024*1024, resumable=True, mimetype="video/mp4")
            r = youtube.videos().insert(
                part="snippet,status,recordingDetails", body=body, media_body=m
            )
            return m, r

        media, request = _fresh_upload()

        resp = None
        retries = 0
        max_retries = 10
        session_retries = 0
        while resp is None:
            if is_stopped():
                return False, None, "Stopped by user"
            try:
                upload_status, resp = request.next_chunk(num_retries=3)
                if upload_status:
                    pct = int(upload_status.progress() * 100)
                    print(f"Upload progress: {pct}%")
                    if progress_bar:
                        progress_bar.update(pct, f"Uploading: {pct}%")
                retries = 0
            except Exception as chunk_err:
                err_str = str(chunk_err)
                retries += 1

                # 409 Conflict or missing Location = stale session, start fresh
                if "409" in err_str or "Location" in err_str:
                    session_retries += 1
                    if session_retries > 3:
                        return False, None, f"Upload failed: {err_str}"
                    print(f"Session error ({err_str[:60]}), creating fresh upload...")
                    time.sleep(5)
                    if creds.expired:
                        creds.refresh(Request())
                        youtube = yt_build('youtube', 'v3', credentials=creds)
                    media, request = _fresh_upload()
                    retries = 0
                    continue

                if retries > max_retries:
                    return False, None, f"Upload failed after {max_retries} retries: {chunk_err}"

                if "400" in err_str and ("invalidTags" in err_str or "invalid" in err_str.lower()):
                    print(f"Upload failed (400 bad request - not retryable): {chunk_err}")
                    return False, None, f"Upload failed: {err_str[:200]}"

                # Timeout = increase wait, refresh creds
                wait = min(2 ** retries + random.random() * 2, 120)
                print(f"Upload chunk error (retry {retries}/{max_retries}): {chunk_err}")
                print(f"Waiting {wait:.0f}s before retry...")
                if progress_bar:
                    progress_bar.update(progress_bar._pct, f"Retry {retries}/{max_retries}...")
                time.sleep(wait)
                if creds.expired:
                    creds.refresh(Request())
                    youtube = yt_build('youtube', 'v3', credentials=creds)
                    media, request = _fresh_upload()

        if 'id' in resp:
            vid_url = f"https://youtube.com/shorts/{resp['id']}"
            return True, resp['id'], vid_url
        return False, None, "No video ID in response"
    except Exception as e:
        return False, None, str(e)

# ============ CLEANUP ============

def cleanup_assets(vid_id, video_path, yt_title):
    """Remove work files after confirmed upload, rename video"""
    # Remove ALL voice/srt files and work folders
    for f in os.listdir(ASSETS):
        fp = f"{ASSETS}/{f}"
        if f.startswith("auto_") and (f.endswith('.mp3') or f.endswith('.srt')):
            try: os.remove(fp)
            except: pass
        elif f.startswith("work_") and os.path.isdir(fp):
            try: shutil.rmtree(fp)
            except: pass

    # Delete ALL files from output — already uploaded, no need to keep
    for f in os.listdir(OUTPUT):
        fp = f"{OUTPUT}/{f}"
        if os.path.isfile(fp):
            try: os.remove(fp)
            except: pass

    # Delete user-provided clips only (not default clips)
    deleted = 0
    for f in os.listdir(CLIPS_DIR):
        fp = f"{CLIPS_DIR}/{f}"
        if os.path.isfile(fp) and not f.startswith('.'):
            try:
                os.remove(fp)
                deleted += 1
            except: pass
    if deleted:
        print(f"Cleaned up {deleted} user clips from {CLIPS_DIR}")

    # Reset URL + hash history so same links/files can be reused for next video
    global url_history, hash_history
    url_history = {}
    save_url_history()
    hash_history = {}
    save_hash_history()
    print("URL + hash history cleared")

# ============ SCHEDULE ============

def slot_label(slot_tuple, date_str=""):
    """Format slot tuple as readable string with optional date."""
    if date_str:
        return f"{slot_tuple[0]} IST ({slot_tuple[1]}) - {date_str}"
    return f"{slot_tuple[0]} IST ({slot_tuple[1]})"

def get_next_upload_slot(after_utc=None):
    """Get nearest available slot. If after_utc is set, only returns slots AFTER that time.
    Returns (slot_tuple, publish_at_utc_iso)."""
    from datetime import datetime, timedelta, timezone

    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")

    min_time = now_ist
    if after_utc:
        try:
            after_dt = datetime.strptime(after_utc.replace('.000Z', '+0000'), "%Y-%m-%dT%H:%M:%S%z")
            after_ist = after_dt.astimezone(IST) + timedelta(minutes=30)
            if after_ist > min_time:
                min_time = after_ist
        except:
            pass

    schedule = load_json(SCHEDULE_FILE, {"used": []})
    used_keys = set()
    for u in schedule.get("used", []):
        used_keys.add(u.get("key", ""))

    candidates = []
    for day_offset in range(0, 4):
        check_date = now_ist + timedelta(days=day_offset)
        check_str = check_date.strftime("%Y-%m-%d")
        for slot in UPLOAD_SLOTS_IST:
            slot_time = datetime.strptime(f"{check_str} {slot[0]}", "%Y-%m-%d %I:%M %p").replace(tzinfo=IST)
            if slot_time <= now_ist:
                continue
            if slot_time <= min_time:
                continue
            key = slot_time.strftime("%Y-%m-%d") + "_" + slot[0]
            if key not in used_keys:
                candidates.append((slot, slot_time, key))

    if not candidates:
        far_date = (now_ist + timedelta(days=4)).strftime("%Y-%m-%d")
        first_slot = UPLOAD_SLOTS_IST[0]
        slot_time = datetime.strptime(f"{far_date} {first_slot[0]}", "%Y-%m-%d %I:%M %p").replace(tzinfo=IST)
        candidates = [(first_slot, slot_time, far_date + "_" + first_slot[0])]

    candidates.sort(key=lambda x: x[1])
    slot, slot_time, key = candidates[0]

    publish_utc = slot_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    slot_date = slot_time.strftime("%d/%m/%Y")
    print(f"Schedule: {slot[0]} IST on {slot_time.strftime('%Y-%m-%d')} (key={key})")
    return slot, publish_utc, slot_date

def record_upload_slot(slot, publish_utc=None):
    from datetime import datetime, timedelta, timezone
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)

    if publish_utc:
        pub_dt = datetime.strptime(publish_utc.replace('.000Z', '+0000'), "%Y-%m-%dT%H:%M:%S%z")
        slot_time = pub_dt.astimezone(IST)
    else:
        today_str = now_ist.strftime("%Y-%m-%d")
        slot_time = datetime.strptime(f"{today_str} {slot[0]}", "%Y-%m-%d %I:%M %p").replace(tzinfo=IST)
        if slot_time <= now_ist:
            slot_time += timedelta(days=1)
    key = slot_time.strftime("%Y-%m-%d") + "_" + slot[0]

    schedule = load_json(SCHEDULE_FILE, {"used": []})
    used = schedule.get("used", [])
    used.append({
        "slot": slot[0],
        "scheduled_date": slot_time.strftime("%Y-%m-%d"),
        "uploaded_at": now_ist.strftime("%Y-%m-%d %H:%M IST"),
        "publish_utc": publish_utc or "",
        "key": key
    })
    if len(used) > 200:
        used = used[-200:]
    schedule["used"] = used
    save_json(SCHEDULE_FILE, schedule)




# ============ MAIN BOT LOOP ============

def handle_message(msg):
    global last_update, _current_user_id, _current_user_label

    user_id = msg.get("from", {}).get("id")
    if not is_allowed(user_id):
        return

    _current_user_id = user_id
    _current_user_label = get_user_label(msg.get("from", {}))
    update_user_details(user_id, msg.get("from", {}))

    text = msg.get("text", "").strip()
    text_lower = text.lower()

    # ---- DRIVE AUTH CODE INTERCEPTION ----
    global _gdrive_auth_pending, _gdrive_auth_flow
    if _gdrive_auth_pending and is_admin(user_id) and text and not text.startswith("/"):
        try:
            _gdrive_auth_flow.fetch_token(code=text.strip())
            creds = _gdrive_auth_flow.credentials
            save_json(GDRIVE_TOKEN_FILE, {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes or [])
            })
            _gdrive_auth_pending = False
            _gdrive_auth_flow = None
            send("Google Drive authorized!\nData sync is now active.\nRestart bot to enable sync.")
        except Exception as e:
            _gdrive_auth_pending = False
            _gdrive_auth_flow = None
            send(f"Auth failed: {e}\nTry /auth_drive again.")
        return

    # ---- COMMANDS ----

    if text_lower in ["/start", "/menu", "/help"]:
        clips = count_clips()
        send(
            f"<b>Told By Nova</b>\n\n"
            f"State: <b>{bot.state}</b>\n"
            f"Clips: <b>{clips}</b>",
            reply_markup=btn(
                [("Auto", "/auto"), ("Story", "/story")],
                [("Clips", "/clips"), ("Build", "/build")],
                [("Upload", "/upload"), ("Rebuild", "/rebuild")],
                [("Status", "/status"), ("Schedule", "/schedule")],
                [("History", "/history"), ("Resume", "/resume")],
                [("Stop", "/stop"), ("Reset", "/reset")],
                [("Duration", "/duration"), ("Stats", "/stats")],
            )
        )
        return

    if text_lower == "/resume":
        clips = count_clips()
        has_voice = bot.voice_mp3 and os.path.exists(bot.voice_mp3) if bot.voice_mp3 else False
        has_video = bot.video_path and os.path.exists(bot.video_path) if bot.video_path else False

        if bot.state == "IDLE" and not bot.current_script:
            send("Nothing to resume.",
                 reply_markup=btn(("Auto", "/auto"), ("Story", "/story")))
            return

        # Fix stale states (e.g. bot crashed mid-build)
        if bot.state == "BUILDING":
            bot.state = "CLIPS_READY" if clips > 0 else "STORY_APPROVED"
            bot.save()

        steps = []
        steps.append(f"Story: <b>{bot.current_story or 'None'}</b>")
        steps.append(f"Voice: {'Ready' if has_voice else 'Not generated'}")
        steps.append(f"Clips: {clips}")
        steps.append(f"Video: {'Ready' if has_video else 'Not built'}")

        if bot.state == "STORY_PENDING":
            pending = load_json(f"{DATA_DIR}/pending_stories.json", {})
            if pending.get("stories"):
                for i, s in enumerate(pending["stories"], 1):
                    send(f"<b>Pending Option {i}:</b> {s.get('title','')}",
                         reply_markup=btn((f"Pick #{i}", f"/{i}"), ("More", "/more")))
                next_step = "Pick a story (/1 or /2) or /auto for new options"
            else:
                next_step = "Use /auto or /story to generate stories"
        elif bot.state == "STORY_APPROVED":
            if not has_voice:
                send("Resuming: generating voice...")
                _generate_voice_for_current()
                has_voice = bot.voice_mp3 and os.path.exists(bot.voice_mp3) if bot.voice_mp3 else False
            if has_voice and clips > 0:
                next_step = "Use /build to create video"
            elif has_voice:
                next_step = "Use /clips to collect video clips"
            else:
                next_step = "Voice failed. /reset and start over"
        elif bot.state == "CLIPS_COLLECTING":
            next_step = f"Send more clips or /done ({clips} so far)"
        elif bot.state == "CLIPS_READY":
            next_step = "Use /build to create the video"
        elif bot.state == "PREVIEW_READY":
            if has_video:
                send("Sending preview again...")
                send_video(bot.video_path)
                next_step = "/ok to upload or /redo to rebuild"
            else:
                bot.state = "CLIPS_READY"
                bot.save()
                next_step = "Video file missing. Use /build again"
        elif bot.state == "UPLOADED":
            next_step = "/confirm to cleanup or /reset for new video"
        else:
            next_step = "Use /auto or /story to begin"

        send(
            f"<b>Resuming Pipeline</b>\n\n"
            + "\n".join(steps) +
            f"\n\nState: <b>{bot.state}</b>\n"
            f"Next: {next_step}"
        )
        return

    if text_lower == "/stop":
        global _stop_flag
        _stop_flag = True
        notify_admin("Sent /stop")
        if bot.state in ["BUILDING"]:
            send("Stopping... will halt after current segment.",
                 reply_markup=btn(("Resume", "/resume"), ("Menu", "/start")))
        elif bot.state in ["IDLE", "STORY_PENDING", "STORY_APPROVED",
                           "CLIPS_COLLECTING", "CLIPS_READY", "PREVIEW_READY", "UPLOADED"]:
            send("Stop signal sent. Nothing actively running right now.",
                 reply_markup=btn(("Resume", "/resume"), ("Menu", "/start")))
        else:
            send("Stop signal sent.",
                 reply_markup=btn(("Resume", "/resume"), ("Menu", "/start")))
        return

    if text_lower == "/status":
        clips = count_clips()

        info = (
            f"<b>Status</b>\n"
            f"State: {bot.state}\n"
            f"Story: {bot.current_story or 'None'}\n"
            f"Voice: {'Ready' if bot.voice_mp3 else 'Not generated'}\n"
            f"Clips: {clips}\n"
            f"Video: {'Ready' if bot.video_path else 'Not built'}\n"

        )

        if bot.video_details:
            info += f"\nShort details: {json.dumps(bot.video_details, indent=1)}"

        send(info)
        return

    if text_lower in ["/reset", "/clear"]:
        notify_admin("Sent /reset")
        # Clean all assets
        for f in os.listdir(ASSETS):
            fp = f"{ASSETS}/{f}"
            if f.startswith("auto_") and (f.endswith('.mp3') or f.endswith('.srt')):
                try: os.remove(fp)
                except: pass
            elif f.startswith("work_") and os.path.isdir(fp):
                try: shutil.rmtree(fp)
                except: pass
        # Clean user clips
        for f in os.listdir(CLIPS_DIR):
            fp = f"{CLIPS_DIR}/{f}"
            if os.path.isfile(fp) and not f.startswith('.'):
                try: os.remove(fp)
                except: pass
        # Clean ALL output files
        for f in os.listdir(OUTPUT):
            fp = f"{OUTPUT}/{f}"
            if os.path.isfile(fp):
                try: os.remove(fp)
                except: pass
        # Clear URL + hash history
        global url_history, hash_history
        url_history = {}
        save_url_history()
        hash_history = {}
        save_hash_history()
        bot._clip_status_msg = None

        bot.reset_for_new_video()
        send("All cleared! Assets, clips, output reset.",
             reply_markup=btn(("Auto", "/auto"), ("Story", "/story")))
        return

    # ---- USER MANAGEMENT (admin only) ----

    if text_lower.startswith("/add_user") or text_lower.startswith("/add-user") or text_lower.startswith("/adduser"):
        user_id = msg.get("from", {}).get("id")
        if not is_admin(user_id):
            send("Admin only.")
            return
        parts = text.split()
        if len(parts) < 2:
            send("Usage: /add_user chat_id\n\nExample: /add_user 123456789")
            return
        new_id = parts[1].strip()
        if not new_id.isdigit():
            send("Invalid chat ID. Must be a number.")
            return
        data = load_users()
        if new_id in data["users"]:
            info = data["users"][new_id]
            send(f"Already exists:\n{format_user_display(new_id, info)}")
            return
        entry = {"role": "user", "added": time.strftime("%Y-%m-%d")}
        info = fetch_user_info(new_id)
        if info:
            if info.get("first_name"): entry["first_name"] = info["first_name"]
            if info.get("last_name"): entry["last_name"] = info["last_name"]
            if info.get("username"): entry["username"] = info["username"]
        data["users"][new_id] = entry
        save_users(data)
        send(f"<b>User added</b>\n\n{format_user_display(new_id, entry)}",
             reply_markup=btn(("View Users", "/view_users")))
        return

    if text_lower.startswith("/remove_user") or text_lower.startswith("/remove-user") or text_lower.startswith("/removeuser"):
        user_id = msg.get("from", {}).get("id")
        if not is_admin(user_id):
            send("Admin only.")
            return
        parts = text.split()
        if len(parts) < 2:
            send("Usage: /remove_user chat_id\n\nExample: /remove_user 123456789")
            return
        rm_id = parts[1].strip()
        if rm_id == str(ADMIN_ID):
            send("Can't remove admin.")
            return
        data = load_users()
        if rm_id not in data["users"]:
            send(f"User {rm_id} not found.")
            return
        removed_info = data["users"].pop(rm_id)
        save_users(data)
        send(f"<b>User removed</b>\n\n{format_user_display(rm_id, removed_info)}",
             reply_markup=btn(("View Users", "/view_users")))
        return

    if text_lower in ["/view_users", "/view-users", "/viewusers", "/users"]:
        user_id = msg.get("from", {}).get("id")
        if not is_admin(user_id):
            send("Admin only.")
            return
        data = load_users()
        users = data.get("users", {})
        if not users:
            send("No users found.")
            return
        lines = [f"<b>Allowed Users ({len(users)})</b>\n"]
        for uid, info in users.items():
            lines.append(format_user_display(uid, info))
            lines.append("")
        send("\n".join(lines))
        return

    # ---- VOICE COMMANDS ----

    if text_lower.startswith("/voice"):
        send("Voice: Edge TTS (en-US-EmmaNeural)\nFree, unlimited, no API keys needed.")
        return

    # ---- INSTANCE LOCK + SYNC COMMANDS ----

    if text_lower in ["/auth_drive", "/authdrive"]:
        if not is_admin(user_id):
            send("Admin only.")
            return
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            client_file = f"{DATA_DIR}/yt_client_secret_1.json"
            if not os.path.exists(client_file):
                send("Missing yt_client_secret_1.json in data/ folder.")
                return
            flow = InstalledAppFlow.from_client_secrets_file(
                client_file,
                scopes=["https://www.googleapis.com/auth/drive.file"],
                redirect_uri="urn:ietf:wg:oauth:2.0:oob"
            )
            auth_url, _ = flow.authorization_url(prompt="consent")
            _gdrive_auth_flow = flow
            _gdrive_auth_pending = True
            send(
                f"<b>Google Drive Authorization</b>\n\n"
                f"1. Open this URL:\n{auth_url}\n\n"
                f"2. Sign in and allow access\n"
                f"3. Copy the code and send it here"
            )
        except Exception as e:
            send(f"Auth setup failed: {e}")
        return

    if text_lower in ["/bot_lock", "/botlock", "/lock"]:
        if not is_admin(user_id):
            send("Admin only.")
            return
        sys_name, local_ips = _detect_system_name()
        doc_status = _read_doc_status()
        drive_ok = os.path.exists(GDRIVE_TOKEN_FILE)
        lines = ["<b>Instance Lock + Sync Status</b>\n"]
        lines.append(f"This system: <b>{sys_name}</b>")
        lines.append(f"IPs: {', '.join(local_ips)}")
        if doc_status is None:
            lines.append(f"\nDoc: Could not read")
        elif doc_status:
            lines.append(f"\nDoc status:")
            for k, v in doc_status.items():
                icon = "ON" if v == "ON" else "OFF"
                lines.append(f"  {k}: {icon}")
            my = doc_status.get(sys_name, "?")
            lines.append(f"\nThis system: <b>{my}</b>")
        else:
            lines.append(f"\nDoc: Empty")
        lines.append(f"\nDrive sync: {'Active' if drive_ok else 'Not authorized (/auth_drive)'}")
        send("\n".join(lines))
        return

    if text_lower in ["/sync_now", "/syncnow", "/sync"]:
        if not is_admin(user_id):
            send("Admin only.")
            return
        if not os.path.exists(GDRIVE_TOKEN_FILE):
            send("Drive not authorized.\nUse /auth_drive first.")
            return
        send("Syncing to Drive...")
        try:
            _sync_to_drive(force=True)
            send("Sync complete!")
        except Exception as e:
            send(f"Sync failed: {e}")
        return

    if text_lower in ["/clear-clip", "/clearclip", "/clear-clips", "/clear_clip"]:
        existing = [f for f in os.listdir(CLIPS_DIR)
                    if f.endswith(('.mp4','.webm','.mov')) and not f.startswith('.')]
        if not existing:
            send("No clips to clear.")
            return
        deleted = 0
        for f in existing:
            try:
                os.remove(f"{CLIPS_DIR}/{f}")
                deleted += 1
            except: pass
        url_history.clear()
        save_url_history()
        hash_history.clear()
        save_hash_history()
        if getattr(bot, '_clip_status_msg', None):
            delete_msg(bot._clip_status_msg)
        bot._clip_status_msg = None
        if bot.state in ["CLIPS_COLLECTING", "CLIPS_READY"]:
            bot.state = "CLIPS_COLLECTING"
        bot.save()
        send(f"Cleared {deleted} clips. Send new clips.",
             reply_markup=btn(("Clips", "/clips")))
        return

    if text_lower == "/trim_off":
        bot.trim_clips = False
        bot.save()
        send("Auto-trim OFF. New clips will NOT be trimmed.")
        return

    if text_lower == "/trim_on":
        bot.trim_clips = True
        bot.save()
        existing = [f for f in os.listdir(CLIPS_DIR)
                    if f.endswith(('.mp4','.webm','.mov')) and not f.startswith('.')]
        if existing:
            send(f"Auto-trim ON. Trimming {len(existing)} existing clips (removing last 6s)...")
            for f in existing:
                trim_last_5s(f"{CLIPS_DIR}/{f}")
            send(f"Done! {len(existing)} clips trimmed.")
        else:
            send("Auto-trim ON. New clips will be trimmed (last 6s removed).")
        return

    if text_lower == "/history":
        history = load_history()
        if not history:
            send("No stories used yet.")
            return
        lines = []
        for h in history[-20:]:
            lines.append(f"• {h.get('title','')} ({h.get('date','')})")
        send("<b>Story History:</b>\n" + "\n".join(lines))
        return

    if text_lower == "/schedule":
        slot, publish_utc, next_date = get_next_upload_slot()

        schedule = load_json(SCHEDULE_FILE, {"used": []})
        used = schedule.get("used", [])
        recent = used[-5:] if used else []

        slots_text = "\n".join(f"  {slot_label(s)}" for s in UPLOAD_SLOTS_IST)
        history_text = ""
        if recent:
            history_text = "\n<b>Recent uploads:</b>\n"
            for u in recent:
                history_text += f"  {u.get('slot','')} on {u.get('scheduled_date','')}\n"
        send(
            f"<b>Upload Schedule (USA Optimized)</b>\n\n"
            f"<b>Shorts slots:</b>\n{slots_text}\n\n"
            f"Next: <b>{slot_label(slot, next_date)}</b>"
            f"{history_text}"
        )
        return


    if text_lower.startswith("/duration"):
        parts = text.split()
        if len(parts) > 1:
            if parts[1].lower() in ["auto", "random", "0"]:
                bot.max_duration = 0
                bot.save()
                send("Duration: AUTO (random 33-38s — viral sweet spot)\nYT Shorts max: 180s")
            else:
                try:
                    d = int(parts[1])
                    if 15 <= d <= 180:
                        bot.max_duration = d
                        bot.save()
                        words_min = int(d * 2.5)
                        words_max = int(d * 3)
                        send(
                            f"Duration fixed: {d}s (~{words_min}-{words_max} words)\n"
                            f"YT Shorts max: 180s | Optimal: 30-60s\n"
                            f"Use /duration auto for random length"
                        )
                    else:
                        send("Duration must be 15-180 seconds\nYT Shorts max: 180s")
                except:
                    send("Usage: /duration 45 or /duration auto")
        else:
            cur = f"{bot.max_duration}s" if bot.max_duration > 0 else "AUTO (33-38s viral sweet spot)"
            send(
                f"Current: {cur}\n\n"
                f"Optimal: 33-38s (highest completion rate)\n"
                f"Our viral videos: 33s (1.2K), 34s (1K)\n\n"
                f"/duration 40 — fixed 40s\n"
                f"/duration auto — random 33-38s each video"
            )
        return

    # ---- MONETIZATION STATS ----

    if text_lower == "/stats":
        send("Fetching channel stats...")
        try:
            youtube = _get_youtube_client()
            ch_resp = youtube.channels().list(part="statistics,snippet", mine=True).execute()
            ch = ch_resp["items"][0] if ch_resp.get("items") else None
            if not ch:
                send("Could not load channel data.")
                return
            stats = ch["statistics"]
            subs = int(stats.get("subscriberCount", 0))
            total_views = int(stats.get("viewCount", 0))
            total_vids = int(stats.get("videoCount", 0))

            subs_pct = min(100, round(subs / 10))
            subs_bar = "█" * (subs_pct // 5) + "░" * (20 - subs_pct // 5)

            send(
                f"<b>Channel Stats — {ch['snippet']['title']}</b>\n\n"
                f"Subscribers: <b>{subs:,}</b> / 1,000\n"
                f"[{subs_bar}] {subs_pct}%\n\n"
                f"Total Views: <b>{total_views:,}</b>\n"
                f"Videos: <b>{total_vids}</b>\n\n"
                f"<b>Monetization Paths:</b>\n"
                f"Path 1: 1K subs + 4K watch hours\n"
                f"Path 2: 1K subs + 10M Shorts views (90 days)\n"
                f"Early Access: 500 subs + 3M Shorts views\n\n"
                f"<b>Tip:</b> Shorts watch hours do NOT count toward 4K hours. "
                f"Focus on daily Shorts for the 10M views path — fastest for new channels."
            )
        except Exception as e:
            send(f"Stats error: {e}")
        return


    # ---- AUTO STORY GENERATION ----

    if text_lower == "/auto":
        if bot.state not in ["IDLE", "STORY_PENDING"]:
            send(f"Can't generate story in state: {bot.state}",
                 reply_markup=btn(("Reset", "/reset")))
            return

        notify_admin("Started /auto — generating stories")
        pb = ProgressBar("Generating stories with AI...")
        pb.start()
        watcher = StopWatcher()
        watcher.start()
        stories = generate_stories()
        was_stopped = _stop_flag
        watcher.stop()
        pb.stop()

        if was_stopped:
            send("Story generation stopped.",
                 reply_markup=btn(("Retry", "/auto"), ("Story", "/story")))
            return

        if not stories or "stories" not in stories:
            send(f"Story generation failed ({_last_ai_source}).",
                 reply_markup=btn(("Retry", "/auto"), ("Story", "/story")))
            return

        bot.state = "STORY_PENDING"
        bot.save()

        save_json(f"{DATA_DIR}/pending_stories.json", stories)

        send(f"Generated via <b>{_last_ai_source}</b>")
        s = stories["stories"][0]
        short_wc = len((s.get("script") or "").split())

        clips_text = ""
        if s.get("clip_suggestions"):
            terms = s["clip_suggestions"][:6]
            clips_text = "\n\n🎬 <b>Clips:</b> " + " | ".join(terms)
        seo_text = ""
        ss = s.get("short_seo") or {}

        if ss.get("yt_title"):
            seo_text += f"\n\n📊 <b>Short SEO:</b> {ss['yt_title']}"
        send(
            f"<b>{s['title']}</b>\n\n"
            f"<i>{s['hook']}</i>\n\n"
            f"{s['script'][:500]}{'...' if len(s['script'])>500 else ''}\n\n"
            f"📝 Short: {short_wc} words"
            f"{clips_text}{seo_text}",
            reply_markup=btn(
                ("Approve", "/ok"),
                [("New Story", "/more"), ("Skip", "/redo")],
            )
        )
        return

    # ---- MANUAL STORY ----

    if text_lower.startswith("/story"):
        raw = text[6:].strip()
        if not raw:
            send("Paste your story after /story command.\nExample: /story A woman got fired for being pregnant...")
            return

        if bot.state not in ["IDLE", "STORY_PENDING"]:
            send(f"Can't set story in state: {bot.state}",
                 reply_markup=btn(("Reset", "/reset")))
            return

        notify_admin("Started /story — refining story")
        pb = ProgressBar("Refining story with AI...")
        pb.start()
        watcher = StopWatcher()
        watcher.start()
        refined = refine_story(raw)
        was_stopped = _stop_flag
        watcher.stop()
        pb.stop()
        if was_stopped:
            send("Story refinement stopped.",
                 reply_markup=btn(("Retry", "/story"), ("Auto", "/auto")))
            return
        if not refined:
            send(f"Refinement failed ({_last_ai_source}). Try again or paste a different story.")
            return

        save_json(f"{DATA_DIR}/pending_stories.json", {"stories": [refined]})
        bot.state = "STORY_PENDING"
        bot.save()

        clips_text = ""
        if refined.get("clip_suggestions"):
            terms = refined["clip_suggestions"][:6]
            clips_text = "\n\n🎬 <b>Search clips:</b> " + " | ".join(terms)
        short_wc = len((refined.get("script") or "").split())
        send(
            f"<b>Refined Story</b> (via {_last_ai_source}):\n"
            f"<b>{refined['title']}</b>\n\n"
            f"{refined['script']}\n\n"
            f"📝 Short: {short_wc} words{clips_text}",
            reply_markup=btn(("Approve", "/ok"), ("Redo", "/redo"))
        )
        return

    # ---- CLIP COLLECTION ----

    if text_lower == "/clips":
        if bot.state not in ["STORY_APPROVED", "CLIPS_COLLECTING", "VOICE_DONE"]:
            if not bot.current_script:
                send("No story approved yet.",
                     reply_markup=btn(("Auto", "/auto"), ("Story", "/story")))
                return

        bot.state = "CLIPS_COLLECTING"
        bot._clip_status_msg = None
        bot._clips_sent = 0
        bot._clips_failed = 0
        bot.save()
        load_url_history()
        clips = count_clips()
        clip_hint = ""
        if bot.clip_suggestions:
            clip_hint = "\n\n🎬 <b>Search these for clips:</b>\n" + "\n".join(f"• {t}" for t in bot.clip_suggestions[:6])
        trim_status = "ON" if bot.trim_clips else "OFF"
        trim_btn_label = "Trim OFF" if bot.trim_clips else "Trim ON"
        trim_btn_cmd = "/trim_off" if bot.trim_clips else "/trim_on"
        send(
            f"<b>Clip Collection Mode</b>\n"
            f"Clips: {clips} (for video)\n"
            f"Auto-trim: <b>{trim_status}</b> (last 6s removed)\n\n"
            f"Send me:\n"
            f"1. Video FILE as document\n"
            f"2. Direct .mp4 URL (no size limit)\n"
            f"{clip_hint}\n\n"
            f"<i>Default clips: {count_clips(include_default=True) - clips}</i>",
            reply_markup=btn(
                [(trim_btn_label, trim_btn_cmd), ("Clear", "/clear-clip")],
                [("Done", "/done")],
            )
        )
        return

    # ---- BUILD ----

    if text_lower == "/build":
        if not bot.current_script:
            send("No story approved.",
                 reply_markup=btn(("Auto", "/auto"), ("Story", "/story")))
            return
        if not bot.voice_mp3 or not os.path.exists(bot.voice_mp3):
            send("Voice not generated. Generating now...")
            _generate_voice_for_current()
            if not bot.voice_mp3:
                send("Voice generation failed.")
                return

        user_clips = count_clips()
        total_clips = count_clips(include_default=True)
        if total_clips < 1:
            send("No clips available!",
                 reply_markup=btn(("Clips", "/clips")))
            return

        if getattr(bot, '_clip_status_msg', None):
            delete_msg(bot._clip_status_msg)
            bot._clip_status_msg = None

        notify_admin("Started /build — building video")
        bot.state = "BUILDING"
        bot.save()

        bot.video_id_counter += 1
        vid_id = bot.video_id_counter
        bot.save()

        # --- SHORT VIDEO BUILD ---
        label = f"{user_clips} clips" if user_clips else f"{total_clips} default clips"
        pb = ProgressBar(f"Building SHORT video ({label})...")
        pb.start()
        watcher = StopWatcher()
        watcher.start()
        ok, path, details = build_video(vid_id, progress_bar=pb)
        was_stopped = _stop_flag
        watcher.stop()
        pb.update(100, "Done!")
        pb.stop()

        if was_stopped:
            bot.state = "CLIPS_READY"
            bot.save()
            send("Build stopped.",
                 reply_markup=btn(("Resume", "/build"), ("Reset", "/reset")))
            return

        if not ok:
            bot.state = "CLIPS_READY"
            bot.save()
            send_and_notify(f"Build failed: {details.get('error','Unknown')}",
                 reply_markup=btn(("Retry", "/build"), ("Reset", "/reset")))
            return

        bot.video_path = path
        bot.video_details = details
        bot.save()

        send_and_notify(
            f"<b>Short Video Built!</b>\n"
            f"Size: {details['size_mb']}MB | Duration: {details['duration']}s\n"
            f"Build time: {details['build_time']}s"
        )
        send_video(path)

        bot.state = "PREVIEW_READY"
        bot.save()
        send("What next?",
             reply_markup=btn(("Upload", "/upload"), ("Rebuild", "/rebuild")))
        return

    # ---- REBUILD ----

    if text_lower == "/rebuild":
        if bot.state not in ["PREVIEW_READY", "CLIPS_READY"]:
            send(f"Can't rebuild in state: {bot.state}",
                 reply_markup=btn(("Build", "/build")))
            return
        if not bot.current_script:
            send("No story set.",
                 reply_markup=btn(("Auto", "/auto"), ("Story", "/story")))
            return
        if not bot.voice_mp3 or not os.path.exists(bot.voice_mp3):
            send("Voice file missing.",
                 reply_markup=btn(("Reset", "/reset")))
            return
        user_clips = count_clips()
        total_clips = count_clips(include_default=True)
        if total_clips < 1:
            send("No clips!",
                 reply_markup=btn(("Clips", "/clips")))
            return

        if getattr(bot, '_clip_status_msg', None):
            delete_msg(bot._clip_status_msg)
            bot._clip_status_msg = None

        bot.state = "BUILDING"
        bot.save()
        vid_id = bot.video_id_counter

        label = f"{user_clips} clips" if user_clips else f"{total_clips} default clips"
        pb = ProgressBar(f"Rebuilding video ({label})...")
        pb.start()
        watcher = StopWatcher()
        watcher.start()
        ok, path, details = build_video(vid_id, progress_bar=pb)
        was_stopped = _stop_flag
        watcher.stop()
        pb.update(100, "Done!")
        pb.stop()

        if was_stopped:
            bot.state = "CLIPS_READY"
            bot.save()
            send("Rebuild stopped.",
                 reply_markup=btn(("Resume", "/rebuild"), ("Reset", "/reset")))
        elif ok:
            bot.video_path = path
            bot.video_details = details
            bot.state = "PREVIEW_READY"
            bot.save()
            send_and_notify(
                f"<b>Video Rebuilt!</b>\n"
                f"Size: {details['size_mb']}MB | Duration: {details['duration']}s\n"
                f"Build time: {details['build_time']}s\n\n"
                f"Sending preview..."
            )
            send_video(path)
            send("What next?",
                 reply_markup=btn(("Upload", "/upload"), ("Rebuild", "/rebuild")))
        else:
            bot.state = "CLIPS_READY"
            bot.save()
            send_and_notify(f"Rebuild failed: {details.get('error','Unknown')}",
                 reply_markup=btn(("Retry", "/rebuild"), ("Reset", "/reset")))
        return

    # ---- UPLOAD ----

    if text_lower == "/upload":
        if bot.state != "PREVIEW_READY" or not bot.video_path:
            send("No video ready.",
                 reply_markup=btn(("Build", "/build")))
            return

        notify_admin("Started /upload — uploading to YouTube")

        # --- SHORT VIDEO UPLOAD ---
        seo = bot.short_seo
        seo_source = "pre-generated"
        if not seo or not seo.get("yt_title"):
            pb = ProgressBar("Generating Short video SEO...")
            pb.start()
            seo = generate_seo(bot.current_story, bot.current_script)
            pb.stop()
            seo_source = _last_ai_source
        else:
            send(f"Using pre-generated Short SEO: <b>{seo['yt_title']}</b>")
        if not seo:
            send(f"SEO generation failed ({_last_ai_source}).",
                 reply_markup=btn(("Retry", "/upload")))
            return


        bot.short_seo = seo
        bot.save()

        category = seo.get('category', 'People & Blogs')
        cat_lower = category.lower()
        cat_display = "Entertainment" if "entertainment" in cat_lower else "People & Blogs"

        slot, publish_at, short_date = get_next_upload_slot()
        send(
            f"<b>Short Upload Preview</b> (SEO: {seo_source}):\n"
            f"Title: {seo['yt_title']}\n"
            f"Category: {cat_display}\n"
            f"Tags: {', '.join(seo['tags']) if isinstance(seo['tags'], list) else seo['tags'][:100]}...\n"
            f"Scheduled: {slot_label(slot, short_date)}\n"
            f"\n"
            f"Uploading short to YouTube..."
        )

        pb = ProgressBar("Uploading SHORT video...")
        pb.start()
        watcher = StopWatcher()
        watcher.start()
        ok, vid_id, result = upload_to_youtube(
            bot.video_path, seo['yt_title'], seo['description'], seo['tags'], category, publish_at,
            progress_bar=pb
        )
        was_stopped = _stop_flag
        watcher.stop()
        pb.update(100, "Upload complete!")
        pb.stop()

        if was_stopped:
            send("Upload stopped. Video still ready.",
                 reply_markup=btn(("Upload", "/upload"), ("Reset", "/reset")))
            return

        if ok:
            record_upload_slot(slot, publish_at)
            record_story(bot.current_story, bot.current_script, vid_id)


            # --- PRO FEATURES: Short video (with progress) ---
            pro_mid = send("⏳ <b>Setting up PRO features...</b>\n<code>[ captions ]</code>")
            if bot.srt_file and os.path.exists(bot.srt_file):
                langs = upload_multilang_captions(vid_id, bot.srt_file)
                if langs:
                    edit_msg(pro_mid, f"⏳ <b>PRO features...</b>\n✅ Captions: {', '.join(langs)}\n<code>[ playlist ]</code>")
            else:
                edit_msg(pro_mid, "⏳ <b>PRO features...</b>\n⏭ Captions skipped\n<code>[ playlist ]</code>")
            if add_to_playlist(vid_id):
                edit_msg(pro_mid, f"⏳ <b>PRO features...</b>\n✅ Captions\n✅ Playlist\n<code>[ comment ]</code>")
            scomment = seo.get('pinned_comment', '') or "Was this justified? Type YES or NO below!"
            schedule_post_upload(vid_id, scomment, publish_at=publish_at)
            edit_msg(pro_mid, "✅ <b>All PRO features done!</b>\n✅ Captions\n✅ Playlist\n✅ Comment scheduled")

            bot.state = "UPLOADED"
            bot.save()

            pro_status = "multilang captions, comment, auto-reply, playlists"
            summary = (
                f"<b>Scheduled on YouTube!</b>\n"
                f"Short: {result}\n"
                f"Video ID: {vid_id}\n"
                f"Goes live: {slot_label(slot, short_date)}\n"
                f"PRO: {pro_status}"
            )
            send_and_notify(summary,
                reply_markup=btn(("Confirm", "/confirm"), ("Reset", "/reset")))

        else:
            send_and_notify(f"Upload failed: {result}",
                 reply_markup=btn(("Retry", "/upload")))
        return

    # ---- STATE-DEPENDENT MESSAGE HANDLING ----

    if bot.state == "STORY_PENDING":
        pending = load_json(f"{DATA_DIR}/pending_stories.json", {})
        stories = pending.get("stories", [])

        if text_lower == "/more":
            send("Generating more options...")
            bot.state = "IDLE"
            bot.save()
            handle_message({"from": msg.get("from", {}), "text": "/auto"})
            return

        def _approve_story(chosen):
            title = chosen.get("title", "Untitled")
            script = chosen.get("script", "")

            if is_story_used(title):
                send("This story was already used!",
                     reply_markup=btn(("New", "/auto"), ("More", "/more")))
                return

            bot.current_story = title
            bot.current_script = script
            bot.mood = chosen.get("mood", "dramatic")
            bot.clip_suggestions = chosen.get("clip_suggestions")
            if chosen.get("short_seo"):
                bot.short_seo = chosen["short_seo"]

            bot.state = "STORY_APPROVED"
            bot.save()

            send_and_notify(f"Story approved: <b>{title}</b>\nMood: {bot.mood}\n\nGenerating voice + subtitles...")

            _generate_voice_for_current()



            if bot.voice_mp3:
                clips = count_clips()
                clip_hint = ""
                if bot.clip_suggestions:
                    clip_hint = "\n\n🎬 <b>Search clips:</b>\n" + "\n".join(f"• {t}" for t in bot.clip_suggestions[:6])
                send_and_notify(
                    f"Voice ready!\nCurrent clips: {clips}{clip_hint}",
                    reply_markup=btn(("Clips", "/clips"), ("Build", "/build"))
                )
            else:
                send_and_notify("Voice generation failed.",
                     reply_markup=btn(("Reset", "/reset")))

        if text_lower in ["/1", "/ok"]:
            if stories:
                _approve_story(stories[0])
                return

        if text_lower == "/2":
            if len(stories) > 1:
                _approve_story(stories[1])
                return

        if text_lower in ["/redo", "/no"]:
            bot.state = "IDLE"
            bot.save()
            send("Skipped.",
                 reply_markup=btn(("Auto", "/auto"), ("Story", "/story")))
            return

    if bot.state == "CLIPS_COLLECTING":
        if text_lower == "/done":
            clips = count_clips()
            if clips < 1:
                clips_def = count_clips(include_default=True)
                if clips_def < 1:
                    send("No clips yet! Send at least 1 video.")
                    return
            if bot._clip_status_msg:
                delete_msg(bot._clip_status_msg)
                bot._clip_status_msg = None
            bot.state = "CLIPS_READY"
            bot.save()
            send(f"Clips ready: {clips} (ready for video)",
                 reply_markup=btn(("Build", "/build")))
            return

        if not hasattr(bot, '_clip_status_msg'):
            bot._clip_status_msg = None
        if not hasattr(bot, '_clips_sent'):
            bot._clips_sent = 0
        if not hasattr(bot, '_clips_failed'):
            bot._clips_failed = 0

        def _clip_bar(saved, total):
            BAR_LEN = 15
            pct = saved / max(total, 1) * 100
            filled = int(BAR_LEN * pct / 100)
            return "🟩" * filled + "⬜" * (BAR_LEN - filled)

        def _save_clip(file_id, fname, clip_path, msg_id):
            """Save a clip, check for duplicates by hash."""
            sz = save_telegram_file(file_id, fname)
            if is_duplicate_file(clip_path):
                os.remove(clip_path)
                _update_clip_status(msg_id, skip=True)
                return
            if bot.trim_clips:
                trim_last_5s(clip_path)
                sz = os.path.getsize(clip_path) / (1024*1024)
            record_file_hash(clip_path, fname)
            _update_clip_status(msg_id)

        def _update_clip_status(user_msg_id, skip=False):
            """Update or send single clip counter message with Build/Clear buttons."""
            clips = count_clips()
            total = max(getattr(bot, '_clips_sent', 0), clips)
            bar = _clip_bar(clips, total)
            trim_tag = " (trimmed)" if bot.trim_clips else ""
            failed = getattr(bot, '_clips_failed', 0)
            fail_tag = f" | {failed} failed" if failed > 0 else ""
            if skip:
                txt = f"<b>{clips}/{total} saved{fail_tag}</b> (duplicate skipped)\n<code>{bar}</code>"
            else:
                txt = f"<b>{clips}/{total} saved{fail_tag}</b>{trim_tag}\n<code>{bar}</code>"
            buttons = btn([("Build", "/done"), ("Clear", "/clear-clip")])
            if hasattr(bot, '_clip_status_msg') and bot._clip_status_msg:
                edit_msg(bot._clip_status_msg, txt, reply_markup=buttons)
            else:
                bot._clip_status_msg = send(txt, reply_markup=buttons)
            try:
                delete_msg(user_msg_id)
            except:
                pass

        user_msg_id = msg.get("message_id")
        fname = f"clip{count_clips() + 1:02d}.mp4"
        clip_path = f"{CLIPS_DIR}/{fname}"

        def _check_size(obj, label="File"):
            """Check file_size before download. Returns True if OK, False if too big."""
            fsize = obj.get("file_size", 0)
            if fsize > 20 * 1024 * 1024:
                mb = round(fsize / (1024*1024), 1)
                bot._clips_failed = getattr(bot, '_clips_failed', 0) + 1
                send(
                    f"<b>{mb}MB — too large for Telegram!</b>\n"
                    f"Telegram bot limit: 20MB.\n\n"
                    f"<b>Fix:</b> Send a direct download URL instead.\n"
                    f"URL downloads have no size limit (up to 500MB).",
                    reply_to=user_msg_id
                )
                clips = count_clips()
                total = max(getattr(bot, '_clips_sent', 0), clips)
                failed = getattr(bot, '_clips_failed', 0)
                bar = _clip_bar(clips, total)
                txt = f"<b>{clips}/{total} saved | {failed} failed</b>\n<code>{bar}</code>"
                if hasattr(bot, '_clip_status_msg') and bot._clip_status_msg:
                    edit_msg(bot._clip_status_msg, txt)
                else:
                    bot._clip_status_msg = send(txt)
                return False
            return True

        if "video" in msg:
            vid = msg["video"]
            if not _check_size(vid):
                return
            try:
                _save_clip(vid["file_id"], fname, clip_path, user_msg_id)
            except Exception as e:
                send(f"Error: {str(e)[:80]}")
            return

        if "animation" in msg:
            anim = msg["animation"]
            if not _check_size(anim):
                return
            try:
                _save_clip(anim["file_id"], fname, clip_path, user_msg_id)
            except Exception as e:
                send(f"Error: {str(e)[:80]}")
            return

        if "document" in msg:
            doc = msg["document"]
            mime = doc.get("mime_type", "")
            name = doc.get("file_name", "")
            if "video" in mime or name.endswith((".mp4", ".webm", ".mov")):
                if not _check_size(doc):
                    return
                try:
                    _save_clip(doc["file_id"], fname, clip_path, user_msg_id)
                except Exception as e:
                    send(f"Error: {str(e)[:80]}")
            return

        # Handle URLs
        urls = re.findall(r'https?://[^\s]+', text)
        if urls:
            for url in urls:
                url = url.strip(".,;:!?")
                if is_duplicate_url(url):
                    _update_clip_status(user_msg_id, skip=True)
                    continue

                if any(x in url for x in ['xhslink.com', 'xiaohongshu.com']):
                    send("RedNote links not supported.\nSave video from app → send as FILE (document).")
                    continue

                if any(x in url for x in ['tiktok.com', 'vm.tiktok']):
                    send("TikTok links not supported.\nSave video from app → send as FILE (document).")
                    continue

                is_direct = any(x in url.lower() for x in ['.mp4', '.webm', 'video'])
                sz = None
                if is_direct: sz = try_direct(url, fname)
                if not sz: sz = try_ytdlp(url, fname)
                if not sz and not is_direct: sz = try_direct(url, fname)
                if sz:
                    dl_path = f"{CLIPS_DIR}/{fname}"
                    if is_duplicate_file(dl_path):
                        os.remove(dl_path)
                        _update_clip_status(user_msg_id, skip=True)
                    else:
                        record_url(url, fname)
                        record_file_hash(dl_path, fname)
                        if bot.trim_clips and os.path.exists(dl_path):
                            trim_last_5s(dl_path)
                        _update_clip_status(user_msg_id)
                        fname = f"clip{count_clips() + 1:02d}.mp4"
                else:
                    send("Failed. Save video and send FILE.")
            try:
                delete_msg(user_msg_id)
            except:
                pass
            return

    if bot.state == "PREVIEW_READY":
        if text_lower in ["/ok", "/upload"]:
            handle_message({"from": msg.get("from", {}), "text": "/upload"})
            return
        if text_lower in ["/redo", "/rebuild"]:
            handle_message({"from": msg.get("from", {}), "text": "/rebuild"})
            return

    if bot.state == "UPLOADED":
        if text_lower in ["/confirm", "/done"]:
            yt_title = bot.current_story or "video"
            cleanup_assets(bot.video_id_counter, bot.video_path, yt_title)
            send("Assets cleaned up! Ready for next video.",
                 reply_markup=btn(("Auto", "/auto"), ("Story", "/story")))
            bot.reset_for_new_video()
            return

def _generate_voice_for_current():
    """Generate voice + SRT for current approved script"""
    global _stop_flag
    if not bot.current_script:
        return
    bot.video_id_counter += 1
    vid_id = bot.video_id_counter
    pb = ProgressBar("Generating voice + subtitles...")
    pb.start()
    watcher = StopWatcher()
    watcher.start()
    try:
        mp3, srt, n_words = generate_voice(bot.current_script, vid_id, mood=bot.mood)
        was_stopped = _stop_flag
        watcher.stop()
        if was_stopped:
            pb.stop()
            send("Voice generation stopped.",
                 reply_markup=btn(("Resume", "/resume"), ("Reset", "/reset")))
            bot.voice_mp3 = None
            bot.srt_file = None
            return
        bot.voice_mp3 = mp3
        bot.srt_file = srt
        bot.save()
        pb.stop()
        send(f"Voice ready! {n_words} words")
    except StopRequested:
        watcher.stop()
        pb.stop()
        send("Voice generation stopped.",
             reply_markup=btn(("Resume", "/resume"), ("Reset", "/reset")))
        bot.voice_mp3 = None
        bot.srt_file = None
    except Exception as e:
        watcher.stop()
        pb.stop()
        print(f"Voice error: {e}")
        bot.voice_mp3 = None
        bot.srt_file = None




# ============ MAIN ============

def main():
    global last_update

    print("=" * 50)
    print("  Told By Nova — Telegram Automation Bot")
    print("=" * 50)
    print(f"State: {bot.state}")
    print(f"Clips: {count_clips()}")
    print(f"Stories used: {len(load_history())}")

    init_users()
    flush_old()
    load_url_history()

    # ---- Instance Lock + Data Sync ----
    try:
        _sync_from_drive()
    except Exception as _sync_err:
        print(f"[WARN] Drive sync failed: {_sync_err}")
    bot.load()
    try:
        if not _check_instance_lock():
            raise SystemExit
    except SystemExit:
        raise
    except Exception as _lock_err:
        print(f"[WARN] Instance lock failed: {_lock_err} — starting without lock")
    try:
        _resume_pending_jobs()
    except Exception as _rj_err:
        print(f"[WARN] Resume jobs failed: {_rj_err}")
    threading.Thread(target=_lock_watcher_loop, daemon=True).start()
    print("[LOCK] Watcher thread started (5s interval)")
    if os.path.exists(GDRIVE_TOKEN_FILE):
        try:
            _sync_to_drive(force=True)
        except Exception as _isync_err:
            print(f"[SYNC] Initial upload failed: {_isync_err}")
        threading.Thread(target=_sync_loop, daemon=True).start()
        print("[SYNC] Sync thread started (10s interval)")

    # Clear all old commands (any scope), then set new ones
    try:
        api_call("deleteMyCommands", {}, timeout=10)
        api_call("deleteMyCommands", {"scope": json.dumps({"type": "all_private_chats"})}, timeout=10)
        api_call("deleteMyCommands", {"scope": json.dumps({"type": "all_group_chats"})}, timeout=10)
    except:
        print("[WARN] Could not clear old commands — continuing anyway")

    new_cmds = json.dumps([
        {"command": "auto", "description": "Generate 2 story options"},
        {"command": "story", "description": "Paste your own story"},
        {"command": "1", "description": "Pick story option 1"},
        {"command": "2", "description": "Pick story option 2"},
        {"command": "ok", "description": "Approve / upload"},
        {"command": "more", "description": "Generate new story options"},
        {"command": "redo", "description": "Skip story / rebuild video"},
        {"command": "clips", "description": "Collect video clips"},
        {"command": "trim", "description": "Trim last 5s (watermark)"},
        {"command": "clear_clip", "description": "Remove all uploaded clips"},
        {"command": "done", "description": "Finish collecting clips"},
        {"command": "build", "description": "Build video"},
        {"command": "rebuild", "description": "Rebuild video"},
        {"command": "upload", "description": "Upload to YouTube"},
        {"command": "confirm", "description": "Cleanup after upload"},
        {"command": "resume", "description": "Continue where you left off"},
        {"command": "schedule", "description": "View upload times"},
        {"command": "history", "description": "View used stories"},
        {"command": "status", "description": "Current state"},
        {"command": "reset", "description": "Reset to start fresh"},
        {"command": "clear", "description": "Reset everything"},
        {"command": "duration", "description": "Max video duration (sec)"},
        {"command": "stop", "description": "Stop running process"},
        {"command": "add_user", "description": "Add user (admin only)"},
        {"command": "remove_user", "description": "Remove user (admin only)"},
        {"command": "view_users", "description": "View allowed users (admin only)"},
        {"command": "voice", "description": "Voice engine info"},
        {"command": "auth_drive", "description": "Authorize Google Drive (one-time)"},
        {"command": "bot_lock", "description": "Instance lock & sync status"},
        {"command": "sync_now", "description": "Force sync data to Drive"},
        {"command": "start", "description": "Commands menu"},
    ])
    try:
        api_call("setMyCommands", {"commands": new_cmds}, timeout=10)
        api_call("setMyCommands", {
            "commands": new_cmds,
            "scope": json.dumps({"type": "chat", "chat_id": ADMIN_ID})
        }, timeout=10)
        print("Telegram menu: old commands deleted, new commands registered")
    except:
        print("[WARN] Could not set commands - continuing anyway")
    import sys; sys.stdout.flush(); sys.stderr.flush()

    ai_label = "Ollama"
    lock_label = f"Lock: {_lock_system_name or '?'}" if _lock_system_name else "Lock: disabled"
    sync_label = "Sync: ON" if os.path.exists(GDRIVE_TOKEN_FILE) else "Sync: OFF"
    for _retry in range(3):
        try:
            if bot.state != "IDLE":
                send(
                    f"<b>Told By Nova — Started!</b>\n"
                    f"State: {bot.state}\n"
                    f"AI: {ai_label}\n"
                    f"{lock_label} | {sync_label}\n"
                    f"Clips: {count_clips()}\n"
                    f"Stories used: {len(load_history())}\n\n"
                    f"<b>Pending work detected!</b>",
                    reply_markup=btn(("Resume", "/resume"), ("Menu", "/start"))
                )
            else:
                send(
                    f"<b>Told By Nova — Started!</b>\n"
                    f"State: {bot.state}\n"
                    f"AI: {ai_label}\n"
                    f"{lock_label} | {sync_label}\n"
                    f"Clips: {count_clips()}\n"
                    f"Stories used: {len(load_history())}",
                    reply_markup=btn(("Auto", "/auto"), ("Story", "/story"), ("Menu", "/start"))
                )
            break
        except Exception as e:
            print(f"[WARN] Startup message failed (attempt {_retry+1}): {e}")
            time.sleep(3)

    conflict_retries = 0
    while True:
        if _instance_lock_violated:
            _send_admin_msg(f"<b>Shutting down from {_lock_system_name}</b>\nTurned OFF via control doc.")
            try:
                _sync_to_drive(force=True)
            except:
                pass
            raise SystemExit
        try:
            updates = api_call("getUpdates", {"offset": last_update + 1, "timeout": 5}, timeout=10)
            conflict_retries = 0
            results = updates.get("result", [])

            if bot.state == "CLIPS_COLLECTING" and results:
                vid_count = 0
                for u in results:
                    m = u.get("message", {})
                    if "video" in m or "animation" in m:
                        vid_count += 1
                    elif "document" in m:
                        doc = m["document"]
                        mime = doc.get("mime_type", "")
                        name = doc.get("file_name", "")
                        if "video" in mime or name.endswith((".mp4", ".webm", ".mov")):
                            vid_count += 1
                    elif re.findall(r'https?://[^\s]+', m.get("text", "")):
                        vid_count += 1
                if vid_count > 0:
                    bot._clips_sent = getattr(bot, '_clips_sent', 0) + vid_count

            for update in results:
                last_update = update["update_id"]
                try:
                    msg = update.get("message")
                    cb = update.get("callback_query")
                    if cb:
                        answer_callback(cb["id"])
                        cmd = cb.get("data", "")
                        cb_user = cb.get("from", {})
                        cb_msg = cb.get("message", {})
                        cb_msg_id = cb_msg.get("message_id")
                        cb_chat_id = cb_msg.get("chat", {}).get("id")
                        if cb_chat_id:
                            _clear_all_buttons(cb_chat_id)
                        if cmd:
                            handle_message({"from": cb_user, "text": cmd, "message_id": cb_msg_id})
                    elif msg:
                        handle_message(msg)
                except Exception as _msg_err:
                    print(f"[ERR] Message handler crash: {_msg_err}")
                    import traceback; traceback.print_exc()

            try:
                check_slot_notifications()
            except Exception as _sn_err:
                print(f"[ERR] Slot notify: {_sn_err}")
            try:
                _periodic_job_check()
            except Exception as _jc_err:
                print(f"[ERR] Job check: {_jc_err}")
        except urllib.error.HTTPError as e:
            if e.code == 409:
                conflict_retries += 1
                wait = min(5 * conflict_retries, 30)
                print(f"409 Conflict (another bot instance?), retrying in {wait}s...")
                time.sleep(wait)
                flush_old()
            else:
                print(f"HTTP Error: {e.code} {e.reason}")
                time.sleep(2)
        except Exception as e:
            if "timed out" not in str(e).lower() and "timeout" not in str(e).lower():
                print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    import traceback as _tb
    while True:
        try:
            main()
        except KeyboardInterrupt:
            print("\n[BOT] Stopped by user (Ctrl+C)")
            try:
                _sync_to_drive(force=True)
            except:
                pass
            break
        except SystemExit:
            break
        except Exception as _e:
            print(f"[BOT] CRASH: {_e}")
            _tb.print_exc()
            print("[BOT] Restarting in 5 seconds...")
            time.sleep(5)
