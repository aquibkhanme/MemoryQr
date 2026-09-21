import os
import re
import io
import json
import uuid
import shutil
import secrets
from datetime import datetime, timezone
from functools import wraps

import qrcode
from flask import (
    Flask, request, jsonify, redirect, url_for, session,
    send_from_directory, render_template_string, send_file
)
from markupsafe import escape
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'memories')
QR_FOLDER = os.path.join(BASE_DIR, 'static', 'qr')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 24 * 7

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'MemoryQR@123')
MAX_MESSAGE = 70000

try:
    from cloud_storage import (
        save_memory_to_supabase,
        update_memory_in_supabase,
        get_memory_from_supabase,
        list_memories_from_supabase,
        upload_to_cloudinary,
        delete_cloudinary_asset,
    )
    CLOUD_READY = all([
        os.getenv('SUPABASE_URL'),
        os.getenv('SUPABASE_KEY'),
        os.getenv('CLOUDINARY_CLOUD_NAME'),
        os.getenv('CLOUDINARY_API_KEY'),
        os.getenv('CLOUDINARY_API_SECRET'),
    ])
except Exception:
    CLOUD_READY = False

try:
    from analytics import init_db, track_request, get_stats
    init_db()
    ANALYTICS_READY = True
except Exception:
    ANALYTICS_READY = False

IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.heic', '.heif'}
VIDEO_EXT = {'.mp4', '.mov', '.webm', '.m4v', '.mkv', '.avi'}


def safe_memory_id(value):
    return bool(value and re.fullmatch(r'[A-Za-z0-9]{12,32}', value))


def local_folder(mid):
    return os.path.join(UPLOAD_FOLDER, mid)


def local_data(mid):
    return os.path.join(local_folder(mid), 'data.json')


def local_read(mid):
    try:
        with open(local_data(mid), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def local_write(mid, row):
    os.makedirs(local_folder(mid), exist_ok=True)
    with open(local_data(mid), 'w', encoding='utf-8') as f:
        json.dump(row, f, ensure_ascii=False, indent=2)


def make_id():
    return secrets.token_urlsafe(18).replace('-', '').replace('_', '')[:18]


def memory_url(mid):
    return request.host_url.rstrip('/') + '/memory/' + mid


def qr_url(mid):
    return request.host_url.rstrip('/') + '/qr/' + mid


def normalize(row):
    row = dict(row or {})

    def as_url(x):
        if isinstance(x, str):
            return {'url': x, 'public_id': '', 'resource_type': 'image'}
        if isinstance(x, dict):
            return {
                'url': x.get('url') or x.get('secure_url') or '',
                'public_id': x.get('public_id', ''),
                'resource_type': x.get('resource_type', 'image'),
            }
        return {'url': '', 'public_id': '', 'resource_type': 'image'}

    row['id'] = str(row.get('id') or row.get('memory_id') or '')
    row['message'] = str(row.get('message') or '')
    row['photos'] = [as_url(x) for x in (row.get('photos') or []) if as_url(x)['url']]
    row['videos'] = [as_url(x) for x in (row.get('videos') or []) if as_url(x)['url']]
    row['status'] = str(row.get('status') or 'active')
    row['ready'] = bool(row.get('ready', False))
    return row


def get_memory(mid, include_trash=False):
    if not safe_memory_id(mid):
        return None

    if CLOUD_READY:
        try:
            row = get_memory_from_supabase(mid)
            if row:
                row = normalize(row)
                if not include_trash and row.get('status') != 'active':
                    return None
                return row
        except Exception:
            pass

    row = local_read(mid)
    if row:
        row = normalize(row)
        if not include_trash and row.get('status') != 'active':
            return None
        return row
    return None


def save_new(mid):
    row = {
        'id': mid,
        'message': '',
        'photos': [],
        'videos': [],
        'status': 'active',
        'ready': False,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    if CLOUD_READY:
        save_memory_to_supabase(mid, '', [], [], ready=False)
    else:
        # Local mode is kept only for development. Render production should
        # always have the Supabase + Cloudinary variables configured.
        local_write(mid, row)
    return row


def update_memory(mid, message=None, photos=None, videos=None, status=None, deleted_at=None, ready=None):
    if CLOUD_READY:
        update_memory_in_supabase(
            mid,
            message=message,
            photos=photos,
            videos=videos,
            status=status,
            deleted_at=deleted_at,
            ready=ready,
        )

    row = get_memory(mid, include_trash=True) or {
        'id': mid, 'message': '', 'photos': [], 'videos': [], 'status': 'active', 'ready': False
    }
    if message is not None:
        row['message'] = message
    if photos is not None:
        row['photos'] = photos
    if videos is not None:
        row['videos'] = videos
    if status is not None:
        row['status'] = status
    if deleted_at is not None:
        row['deleted_at'] = deleted_at
    if ready is not None:
        row['ready'] = bool(ready)
    local_write(mid, row)
    return row


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return fn(*args, **kwargs)
    return wrapped


def incoming_files():
    out = []
    seen = set()
    for key in ('file', 'files', 'photos', 'videos', 'photoFiles', 'videoFiles'):
        for f in request.files.getlist(key):
            if f and f.filename and id(f) not in seen:
                out.append(f)
                seen.add(id(f))
    return out


def kind_of(f):
    ext = os.path.splitext(f.filename.lower())[1]
    mime = (f.mimetype or '').lower()
    if ext in IMAGE_EXT or mime.startswith('image/'):
        return 'photo'
    if ext in VIDEO_EXT or mime.startswith('video/'):
        return 'video'
    return None


def all_memories():
    rows = []
    if CLOUD_READY:
        try:
            rows = list_memories_from_supabase(include_trash=True)
        except Exception:
            rows = []
    else:
        for mid in os.listdir(UPLOAD_FOLDER):
            r = local_read(mid)
            if r:
                rows.append(r)
    return [normalize(x) for x in rows]


def pretty_date(value):
    if not value:
        return '—'
    try:
        s = str(value).replace('Z', '+00:00')
        dt = datetime.fromisoformat(s)
        if dt.tzinfo:
            dt = dt.astimezone()
        return dt.strftime('%d %b %Y, %I:%M %p')
    except Exception:
        return str(value)


@app.before_request
def analytics_hook():
    if ANALYTICS_READY:
        try:
            track_request(request)
        except Exception:
            pass


@app.route('/')
def home():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/create-memory', methods=['POST'])
def create_memory():
    if not CLOUD_READY:
        return jsonify(
            success=False,
            error='Cloud storage is not configured. Add Supabase and Cloudinary environment variables first.'
        ), 503

    mid = make_id()
    try:
        save_new(mid)
        return jsonify(success=True, memory_id=mid, ready=False)
    except Exception as exc:
        return jsonify(success=False, error='Memory creation failed: ' + str(exc)), 500


@app.route('/finalize-memory', methods=['POST'])
def finalize_memory():
    data = request.get_json(silent=True) or {}
    mid = (data.get('memory_id') or '').strip()
    if not safe_memory_id(mid):
        return jsonify(success=False, error='Invalid memory ID'), 400

    try:
        expected_photos = int(data.get('expected_photo_count', 0))
        expected_videos = int(data.get('expected_video_count', 0))
    except (TypeError, ValueError):
        return jsonify(success=False, error='Invalid media count'), 400

    if expected_photos < 0 or expected_videos < 0:
        return jsonify(success=False, error='Invalid media count'), 400

    row = get_memory(mid, include_trash=True)
    if not row or row.get('status') != 'active':
        return jsonify(success=False, error='Memory not found'), 404

    # The QR is NOT published until the exact number of selected photos and
    # videos has reached cloud storage and the message has been saved.
    actual_photos = len(row.get('photos', []))
    actual_videos = len(row.get('videos', []))
    if actual_photos != expected_photos or actual_videos != expected_videos:
        return jsonify(
            success=False,
            error=(
                f'Not all files are saved yet. Photos: {actual_photos}/{expected_photos}, '
                f'Videos: {actual_videos}/{expected_videos}.'
            )
        ), 409

    try:
        update_memory(mid, ready=True)
        final_row = get_memory(mid, include_trash=True) or row
        return jsonify(
            success=True,
            memory_id=mid,
            memory_url=memory_url(mid),
            url=memory_url(mid),
            qr=qr_url(mid),
            qr_url=qr_url(mid),
            photo_count=len(final_row.get('photos', [])),
            video_count=len(final_row.get('videos', [])),
        )
    except Exception as exc:
        return jsonify(success=False, error='Memory finalization failed: ' + str(exc)), 500


@app.route('/upload', methods=['POST'])
def upload():
    mid = (request.form.get('memory_id') or '').strip()
    if not safe_memory_id(mid):
        return jsonify(success=False, error='Invalid memory ID'), 400

    row = get_memory(mid)
    if not row:
        return jsonify(success=False, error='Memory not found'), 404

    files = incoming_files()
    if not files:
        return jsonify(success=False, error='No files received'), 400

    photos = list(row['photos'])
    videos = list(row['videos'])
    uploaded_items = []

    try:
        for f in files:
            kind = kind_of(f)
            if not kind:
                continue
            if not CLOUD_READY:
                return jsonify(success=False, error='Cloud storage is not configured'), 503

            result = upload_to_cloudinary(
                f,
                resource_type='image' if kind == 'photo' else 'video'
            )
            item = result
            (photos if kind == 'photo' else videos).append(item)
            uploaded_items.append(item)

        if not uploaded_items:
            return jsonify(success=False, error='No supported photo/video file received'), 400

        update_memory(mid, photos=photos, videos=videos)
        return jsonify(
            success=True,
            files=[x['url'] for x in uploaded_items],
            photos=[x['url'] for x in photos],
            videos=[x['url'] for x in videos],
        )
    except Exception as exc:
        # If the DB update fails after a Cloudinary upload, remove those newly
        # uploaded assets so the cloud does not collect orphaned files.
        for item in uploaded_items:
            try:
                delete_cloudinary_asset(item.get('public_id', ''), item.get('resource_type', 'image'))
            except Exception:
                pass
        return jsonify(success=False, error='Upload failed: ' + str(exc)), 500


@app.route('/save-message', methods=['POST'])
def save_message():
    data = request.get_json(silent=True) or {}
    mid = (data.get('memory_id') or '').strip()
    message = str(data.get('message') or '')

    if not safe_memory_id(mid):
        return jsonify(success=False, error='Invalid memory ID'), 400
    if len(message) > MAX_MESSAGE:
        return jsonify(success=False, error='Message is too long'), 400
    if not get_memory(mid):
        return jsonify(success=False, error='Memory not found'), 404

    try:
        update_memory(mid, message=message)
        return jsonify(success=True)
    except Exception as exc:
        return jsonify(success=False, error='Message save failed: ' + str(exc)), 500


@app.route('/qr/<mid>')
def qr(mid):
    row = get_memory(mid)
    if not row or not row.get('ready'):
        return 'Memory is not ready yet', 404
    try:
        image = qrcode.make(memory_url(mid))
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        buf.seek(0)
        return send_file(buf, mimetype='image/png', download_name=f'{mid}.png')
    except Exception:
        return 'QR unavailable', 500


@app.route('/memories/<mid>/<path:filename>')
def memory_file(mid, filename):
    if not safe_memory_id(mid):
        return 'Not found', 404
    return send_from_directory(local_folder(mid), filename)


@app.route('/memory/<mid>')
def memory_page(mid):
    row = get_memory(mid)
    if not row or not row.get('ready'):
        return render_template_string(NOT_FOUND), 404
    return render_template_string(
        MEMORY_HTML,
        memory_id=escape(mid),
        photos=row['photos'],
        videos=row['videos'],
        message=row['message'],
    )


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = ''
    if request.method == 'POST':
        u = request.form.get('username', '')
        p = request.form.get('password', '')
        if secrets.compare_digest(u, ADMIN_USERNAME) and secrets.compare_digest(p, ADMIN_PASSWORD):
            session.clear()
            session['admin_logged_in'] = True
            session.permanent = True
            return redirect(url_for('admin_dashboard'))
        error = 'Invalid username or password.'
    return render_template_string(LOGIN_HTML, error=error)


@app.route('/admin')
@admin_required
def admin_dashboard():
    memories = all_memories()
    active = [m for m in memories if m.get('status') == 'active']
    trash = [m for m in memories if m.get('status') == 'trash']

    stats = {'total_visits': 0, 'today_visits': 0, 'seven_day_visits': 0, 'memory_views': 0}
    if ANALYTICS_READY:
        try:
            stats.update(get_stats())
        except Exception:
            pass

    return render_template_string(
        ADMIN_HTML,
        memories=active,
        trash=trash,
        stats=stats,
        cloud_ready=CLOUD_READY,
        pretty_date=pretty_date,
    )


@app.route('/admin/trash-selected', methods=['POST'])
@admin_required
def trash_selected():
    for mid in request.form.getlist('selected'):
        move_to_trash(mid)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete-selected', methods=['POST'])
@admin_required
def delete_selected():
    for mid in request.form.getlist('selected'):
        delete_permanent(mid)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/restore-selected', methods=['POST'])
@admin_required
def restore_selected():
    for mid in request.form.getlist('selected'):
        restore_memory(mid)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/permanent-delete-selected', methods=['POST'])
@admin_required
def permanent_delete_selected():
    for mid in request.form.getlist('selected'):
        delete_permanent(mid)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/trash/<mid>', methods=['POST'])
@admin_required
def trash_one(mid):
    move_to_trash(mid)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/restore/<mid>', methods=['POST'])
@admin_required
def restore_one(mid):
    restore_memory(mid)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete/<mid>', methods=['POST'])
@admin_required
def delete_one(mid):
    delete_permanent(mid)
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))


def move_to_trash(mid):
    row = get_memory(mid, include_trash=True)
    if not row or row.get('status') == 'trash':
        return
    now = datetime.now(timezone.utc).isoformat()
    try:
        update_memory(mid, status='trash', deleted_at=now)
    except Exception:
        pass


def restore_memory(mid):
    row = get_memory(mid, include_trash=True)
    if not row or row.get('status') != 'trash':
        return
    try:
        update_memory(mid, status='active')
    except Exception:
        pass


def delete_permanent(mid):
    if not safe_memory_id(mid):
        return
    row = get_memory(mid, include_trash=True)
    if not row:
        return

    if CLOUD_READY:
        for item in row.get('photos', []) + row.get('videos', []):
            try:
                delete_cloudinary_asset(
                    item.get('public_id', ''),
                    item.get('resource_type', 'image')
                )
            except Exception:
                pass
        try:
            # Delete the Supabase row through REST. We keep this here rather
            # than requiring a separate database client on Termux.
            import requests
            base = os.getenv('SUPABASE_URL', '').rstrip('/')
            key = os.getenv('SUPABASE_KEY', '')
            requests.delete(
                f'{base}/rest/v1/memories',
                headers={
                    'apikey': key,
                    'Authorization': f'Bearer {key}',
                },
                params={'id': f'eq.{mid}'},
                timeout=30,
            ).raise_for_status()
        except Exception:
            pass

    shutil.rmtree(local_folder(mid), ignore_errors=True)


NOT_FOUND = '''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow,noarchive"><title>Memory Not Found</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#070b16;color:white;font-family:Arial}.box{width:min(440px,90%);padding:38px;border:1px solid #ffffff18;border-radius:28px;background:#ffffff08;text-align:center;box-shadow:0 30px 100px #0008}.i{font-size:60px}p{color:#9da4b8;line-height:1.6}</style></head><body><div class="box"><div class="i">💔</div><h1>Memory Not Found</h1><p>This memory link is invalid or has been removed.</p></div></body></html>'''

MEMORY_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow,noarchive"><title>Your Memory • Memory QR</title><style>*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0%,#49215c,#101225 42%,#06171f);color:#fff;font-family:Inter,Arial,sans-serif}.wrap{width:min(1080px,92%);margin:auto;padding:28px 0 55px}.top{text-align:center;padding:35px 10px}.brand{font-weight:900;letter-spacing:3px;color:#ff7bd1}.top h1{font-size:clamp(35px,7vw,68px);margin:12px 0;background:linear-gradient(90deg,#ff77cb,#9b85ff,#5ee7ff);-webkit-background-clip:text;color:transparent}.sub{color:#aeb5c9}.section{margin:22px 0;padding:25px;border-radius:28px;background:#ffffff09;border:1px solid #ffffff16;box-shadow:0 22px 80px #0004}.section h2{margin:0 0 18px}.photos{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}.photo{overflow:hidden;border-radius:20px;background:#111525;cursor:pointer}.photo img{width:100%;height:235px;display:block;object-fit:cover;transition:.25s}.photo:hover img{transform:scale(1.03)}video{width:100%;max-height:650px;display:block;margin:14px 0;border-radius:20px;background:#000}.message{white-space:pre-wrap;line-height:1.85;font-size:18px;padding:25px;border-radius:21px;background:linear-gradient(135deg,#4b204a,#252b5b)}.empty{text-align:center;color:#8991a7;padding:30px}.footer{text-align:center;color:#72798c;padding-top:28px}.viewer{display:none;position:fixed;inset:0;background:#000e;z-index:50;align-items:center;justify-content:center;padding:20px}.viewer img{max-width:96%;max-height:92%;border-radius:15px;object-fit:contain}.viewer button{position:absolute;top:16px;right:16px;width:44px;height:44px;border:0;border-radius:50%;background:#ffffff22;color:#fff;font-size:28px}</style></head><body><main class="wrap"><header class="top"><div class="brand">♥ MEMORY QR</div><h1>Your Memories, Forever.</h1><div class="sub">A special collection of moments • {{ memory_id }}</div></header><section class="section"><h2>📸 Photos</h2><div class="photos">{% for p in photos %}<div class="photo"><img src="{{ p.url }}" loading="lazy" onclick="openViewer(this.src)"></div>{% else %}<div class="empty">No photos added yet.</div>{% endfor %}</div></section><section class="section"><h2>🎥 Videos</h2>{% for v in videos %}<video controls playsinline preload="metadata" src="{{ v.url }}"></video>{% else %}<div class="empty">No videos added yet.</div>{% endfor %}</section><section class="section"><h2>💌 Special Message</h2><div class="message">{{ message or 'Your special message will appear here.' }}</div></section><div class="footer">This site is made by Aquib Khan ❤️</div></main><div class="viewer" id="viewer" onclick="closeViewer()"><button onclick="closeViewer();event.stopPropagation()">×</button><img id="viewerImg"></div><script>function openViewer(s){viewer.style.display='flex';viewerImg.src=s}function closeViewer(){viewer.style.display='none';viewerImg.src=''}</script></body></html>'''

LOGIN_HTML = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Memory QR Admin Login</title><style>*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at top,#34204e,#080b15 62%);color:#fff;font-family:Inter,Arial,sans-serif}.box{width:min(630px,90%);padding:48px 62px;border-radius:38px;background:linear-gradient(145deg,#ffffff0d,#ffffff05);border:1px solid #ffffff20;box-shadow:0 35px 120px #0009}.brand{text-align:center;font-weight:900;letter-spacing:2px;font-size:30px}.logo{width:140px;height:140px;margin:0 auto 28px;border-radius:36px;display:grid;place-items:center;background:linear-gradient(135deg,#ff1d9d,#9a4dff);font-size:68px;box-shadow:0 20px 55px #7b31ff44}.subtitle{text-align:center;color:#aeb5c9;font-size:28px;margin:8px 0 38px}label{display:block;color:#dce0ec;font-size:20px;margin:20px 0 9px}input{width:100%;padding:18px 20px;border-radius:20px;border:1px solid #38507d;background:#070d1f;color:#fff;font-size:18px;outline:none}input:focus{border-color:#8f65ff;box-shadow:0 0 0 3px #8f65ff22}button{width:100%;margin-top:26px;padding:18px;border:0;border-radius:20px;color:#fff;font-weight:800;background:linear-gradient(90deg,#ff249f,#974fff);font-size:19px;cursor:pointer}.back{display:block;text-align:center;margin-top:28px;color:#aeb5c9;text-decoration:none;font-size:18px}.err{color:#ff8f9f;text-align:center;margin-top:15px}@media(max-width:600px){.box{padding:35px 24px}.logo{width:140px;height:140px}.subtitle{font-size:24px}}</style></head><body><form class="box" method="post"><div class="logo">💖✨</div><div class="brand">Memory QR</div><div class="subtitle">Admin Dashboard</div><label>Username</label><input name="username" autocomplete="username" required><label>Password</label><input id="password" type="password" name="password" autocomplete="current-password" required><button>Login to Dashboard</button><a class="back" href="/">← Back to Website</a>{% if error %}<div class="err">{{ error }}</div>{% endif %}</form></body></html>'''

ADMIN_HTML = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Memory QR • Admin Dashboard</title><style>*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0%,#101d44 0,#070b18 38%,#02141e 100%);color:#f5f7ff;font-family:Inter,Arial,sans-serif;min-height:100vh}.wrap{width:min(1200px,94%);margin:auto;padding:22px 0 70px}.nav{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:4px 0 26px;border-bottom:1px solid #ffffff13}.brandrow{display:flex;align-items:center;gap:16px}.brandlogo{width:86px;height:86px;border-radius:26px;display:grid;place-items:center;background:linear-gradient(135deg,#ff1d9d,#934dff);font-size:43px}.brand{font-weight:900;font-size:30px}.brand small{display:block;color:#9da6bd;font-size:18px;font-weight:500;margin-top:6px}.logout{padding:15px 24px;border-radius:18px;border:1px solid #ffffff1b;background:#ffffff08;color:#fff;text-decoration:none;font-size:18px}.hero{padding:45px 0 30px}.hero h1{font-size:clamp(40px,7vw,64px);margin:0 0 12px}.hero p{font-size:22px;color:#aeb6ca;margin:0;line-height:1.45}.stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.stat{min-height:165px;padding:26px;border-radius:28px;background:linear-gradient(145deg,#ffffff0d,#ffffff05);border:1px solid #ffffff15;box-shadow:0 25px 70px #0003}.stat .icon{font-size:42px}.stat b{display:block;font-size:43px;margin-top:7px}.stat span{color:#9ea7bb;font-size:20px}.search{display:flex;margin:34px 0 22px;border:1px solid #28436f;border-radius:23px;overflow:hidden;background:#071022}.search input{flex:1;min-width:0;padding:18px 25px;background:transparent;border:0;outline:0;color:#fff;font-size:19px}.search button{width:90px;border:0;background:#162748;color:#fff;font-size:25px}.tabs{display:flex;gap:14px;margin-bottom:20px}.tab{border:1px solid #ffffff18;background:#ffffff08;color:#fff;padding:15px 25px;border-radius:20px;font-size:18px;cursor:pointer}.tab.active{background:linear-gradient(90deg,#874cff,#be2bff);border-color:#a45bff}.bulkbar{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0 28px}.bulk{border:0;border-radius:20px;padding:16px 26px;color:#fff;font-size:18px;font-weight:800;background:#162546;cursor:pointer}.bulk-trash{background:linear-gradient(90deg,#ff315e,#ff0d73)}.bulk-delete{background:#e51643}.bulk-restore{background:#079b72}.hidden{display:none}.list{display:grid;grid-template-columns:1fr;gap:16px}.card{padding:25px;border-radius:28px;background:linear-gradient(145deg,#132237,#0d1929);border:1px solid #ffffff16;box-shadow:0 22px 70px #0004}.cardtop{display:flex;align-items:center;gap:18px}.check{width:24px;height:24px}.card h3{margin:0;font-size:27px;word-break:break-all}.pills{display:flex;gap:9px;flex-wrap:wrap;margin:20px 0}.pill{padding:9px 13px;border-radius:999px;background:#203248;color:#bfc8da;font-size:15px}.actions{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.actions a,.actions button{border:0;border-radius:15px;padding:14px 10px;text-align:center;color:#fff;text-decoration:none;font-size:16px;font-weight:700;cursor:pointer}.open{background:#2166ff}.view{background:#8448ff}.download{background:#009e73}.trash{background:#ef2460}.restore{background:#008f6b}.delete{background:#d90f3f}.date{color:#9ba5ba;font-size:16px;margin-top:5px}.empty{text-align:center;color:#8c95aa;padding:55px 20px;border:1px dashed #ffffff18;border-radius:25px}.footer{text-align:center;color:#68738a;margin-top:45px}.storage{margin:18px 0;color:#8fdac1;font-size:14px}@media(max-width:650px){.stats{grid-template-columns:1fr 1fr}.actions{grid-template-columns:repeat(2,1fr)}.brand{font-size:25px}.brandlogo{width:72px;height:72px;font-size:34px}.logout{padding:13px 18px}.hero p{font-size:18px}.bulk{width:auto;font-size:16px;padding:14px 18px}}@media(max-width:420px){.stats{gap:12px}.stat{padding:20px;min-height:145px}.stat b{font-size:35px}.stat span{font-size:16px}.actions{grid-template-columns:1fr 1fr}.card{padding:20px}}
</style></head><body><main class="wrap"><header class="nav"><div class="brandrow"><div class="brandlogo">💖✨</div><div class="brand">Memory QR<small>Admin Dashboard</small></div></div><a class="logout" href="/admin/logout">Logout</a></header><section class="hero"><h1>Memory Dashboard</h1><p>Manage every memory created on your website.</p></section><section class="stats"><div class="stat"><div class="icon">💾</div><b>{{ memories|length }}</b><span>Active Memories</span></div><div class="stat"><div class="icon">🗑️</div><b>{{ trash|length }}</b><span>Trash</span></div><div class="stat"><div class="icon">👀</div><b>{{ stats.memory_views }}</b><span>Memory Views</span></div><div class="stat"><div class="icon">📊</div><b>{{ stats.total_visits }}</b><span>Total Visits</span></div></section><div class="storage">☁️ Storage: {{ 'Supabase + Cloudinary connected' if cloud_ready else 'Cloud storage not configured' }}</div><div class="search"><input id="search" placeholder="Search memory ID, date or message..." oninput="filterCards()"><button type="button">🔎</button></div><div class="tabs"><button id="tabMem" class="tab active" onclick="showTab('mem')">💾 Memories ({{ memories|length }})</button><button id="tabTrash" class="tab" onclick="showTab('trash')">🗑️ Trash ({{ trash|length }})</button></div><form id="memForm" method="post"><div id="memBulk" class="bulkbar"><button type="button" class="bulk" onclick="selectAll('.active-check',true)">☑ Select All</button><button type="button" class="bulk bulk-trash" onclick="submitSelected('/admin/trash-selected','.active-check','Move selected memories to trash?')">🗑️ Move Selected to Trash</button><button type="button" class="bulk bulk-delete" onclick="submitSelected('/admin/delete-selected','.active-check','Delete selected memories permanently? This cannot be undone.')">❌ Delete Selected</button></div><div id="memoryList" class="list">{% for m in memories %}<article class="card searchable" data-search="{{ (m.id ~ ' ' ~ m.message ~ ' ' ~ (m.created_at or ''))|lower }}"><div class="cardtop"><input class="check active-check" type="checkbox" name="selected" value="{{ m.id }}"><div><h3>{{ m.id }}</h3><div class="date">Created: {{ pretty_date(m.created_at) }}</div></div></div><div class="pills"><span class="pill">📸 {{ m.photos_count if m.photos_count is defined else m.photos|length }} Photos</span><span class="pill">🎬 {{ m.videos_count if m.videos_count is defined else m.videos|length }} Videos</span><span class="pill">💌 {{ 'Message' if m.message else 'No Message' }}</span><span class="pill">🔗 QR Saved</span></div><div class="actions"><a class="open" target="_blank" href="/memory/{{ m.id }}">Open</a><a class="view" target="_blank" href="/qr/{{ m.id }}">View QR</a><a class="download" download="{{ m.id }}.png" href="/qr/{{ m.id }}">Download QR</a><button type="button" class="trash" onclick="oneAction('/admin/trash/{{ m.id }}','Move this memory to trash?')">Trash</button></div></article>{% else %}<div class="empty">No active memories.</div>{% endfor %}</div></form><form id="trashForm" method="post"><div id="trashBulk" class="bulkbar hidden"><button type="button" class="bulk bulk-restore" onclick="submitSelected('/admin/restore-selected','.trash-check','Restore selected memories?')">♻ Restore Selected</button><button type="button" class="bulk bulk-delete" onclick="submitSelected('/admin/permanent-delete-selected','.trash-check','Permanently delete selected memories? This cannot be undone.')">❌ Permanently Delete</button></div><div id="trashList" class="list hidden">{% for m in trash %}<article class="card searchable" data-search="{{ (m.id ~ ' ' ~ m.message ~ ' ' ~ (m.created_at or ''))|lower }}"><div class="cardtop"><input class="check trash-check" type="checkbox" name="selected" value="{{ m.id }}"><div><h3>{{ m.id }}</h3><div class="date">Created: {{ pretty_date(m.created_at) }}</div></div></div><div class="pills"><span class="pill">📸 {{ m.photos|length }} Photos</span><span class="pill">🎬 {{ m.videos|length }} Videos</span><span class="pill">🗑️ In Trash</span></div><div class="actions"><button type="button" class="restore" onclick="oneAction('/admin/restore/{{ m.id }}','Restore this memory?')">Restore</button><button type="button" class="delete" onclick="oneAction('/admin/delete/{{ m.id }}','Permanently delete this memory? This cannot be undone.')">Delete Forever</button></div></article>{% else %}<div class="empty">Trash is empty.</div>{% endfor %}</div></form><div class="footer">Memory QR • Admin Control Center</div><script>function selectAll(sel,v){document.querySelectorAll(sel).forEach(x=>x.checked=v)}function submitSelected(action,sel,msg){const boxes=[...document.querySelectorAll(sel+':checked')];if(!boxes.length){alert('Please select at least one memory.');return}if(!confirm(msg))return;const f=document.createElement('form');f.method='POST';f.action=action;boxes.forEach(b=>{const i=document.createElement('input');i.type='hidden';i.name='selected';i.value=b.value;f.appendChild(i)});document.body.appendChild(f);f.submit()}function oneAction(action,msg){if(!confirm(msg))return;const f=document.createElement('form');f.method='POST';f.action=action;document.body.appendChild(f);f.submit()}function showTab(tab){const m=tab==='mem';document.getElementById('memoryList').classList.toggle('hidden',!m);document.getElementById('memBulk').classList.toggle('hidden',!m);document.getElementById('trashList').classList.toggle('hidden',m);document.getElementById('trashBulk').classList.toggle('hidden',m);document.getElementById('tabMem').classList.toggle('active',m);document.getElementById('tabTrash').classList.toggle('active',!m);filterCards()}function filterCards(){const q=document.getElementById('search').value.toLowerCase().trim();document.querySelectorAll('.searchable').forEach(c=>c.style.display=!q||c.dataset.search.includes(q)?'block':'none')}</script></main></body></html>'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8000')), debug=False)
