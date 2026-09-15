import os
import io
import shutil
import secrets
from datetime import datetime

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    send_from_directory,
    render_template_string,
    jsonify
)

import qrcode


# =========================================================
# BASIC CONFIG
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MEMORIES_DIR = os.path.join(BASE_DIR, "memories")
TRASH_DIR = os.path.join(BASE_DIR, "trash")
QR_DIR = os.path.join(BASE_DIR, "static", "qr")

os.makedirs(MEMORIES_DIR, exist_ok=True)
os.makedirs(TRASH_DIR, exist_ok=True)
os.makedirs(QR_DIR, exist_ok=True)


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "memoryqr-local-secret-change-this"
)


# =========================================================
# ADMIN LOGIN
# =========================================================

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "MemoryQR@123"
)


# =========================================================
# OPTIONAL ANALYTICS
# =========================================================

try:
    from analytics import init_db, track_request, get_stats

    try:
        init_db()
    except Exception:
        pass

    @app.before_request
    def analytics_middleware():
        try:
            track_request(request)
        except Exception:
            pass

except Exception:

    def get_stats():
        return {
            "total_visits": 0,
            "today_visits": 0,
            "seven_day_visits": 0,
            "memory_views": 0,
            "most_viewed": None,
            "devices": [],
            "browsers": []
        }


# =========================================================
# HELPERS
# =========================================================

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif"
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".webm",
    ".mov",
    ".m4v",
    ".avi"
}


def is_logged_in():
    return session.get("admin_logged_in") is True


def require_admin():
    if not is_logged_in():
        return redirect(url_for("admin_login"))
    return None


def get_memory_folder(memory_id):
    return os.path.join(MEMORIES_DIR, memory_id)


def get_trash_folder(memory_id):
    return os.path.join(TRASH_DIR, memory_id)


def get_qr_path(memory_id):
    return os.path.join(QR_DIR, memory_id + ".png")


def safe_memory_id(memory_id):
    if not memory_id:
        return False

    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"

    return all(c in allowed for c in memory_id)


def create_memory_id():
    while True:
        memory_id = secrets.token_urlsafe(9)

        if safe_memory_id(memory_id):
            if not os.path.exists(get_memory_folder(memory_id)):
                return memory_id


def get_files(folder):
    if not os.path.isdir(folder):
        return []

    result = []

    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)

        if os.path.isfile(path):
            result.append(filename)

    return sorted(result)


def count_media(folder):
    photos = 0
    videos = 0

    for filename in get_files(folder):
        ext = os.path.splitext(filename)[1].lower()

        if ext in IMAGE_EXTENSIONS:
            photos += 1

        elif ext in VIDEO_EXTENSIONS:
            videos += 1

    return photos, videos


def message_exists(folder):
    message_file = os.path.join(folder, "message.txt")
    return os.path.isfile(message_file)


def read_message(folder):
    message_file = os.path.join(folder, "message.txt")

    if not os.path.isfile(message_file):
        return ""

    try:
        with open(
            message_file,
            "r",
            encoding="utf-8"
        ) as f:
            return f.read()
    except Exception:
        return ""


def folder_created_time(folder):
    try:
        return datetime.fromtimestamp(
            os.path.getctime(folder)
        ).strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return "Unknown"


def get_memory_info(memory_id, trash=False):

    folder = (
        get_trash_folder(memory_id)
        if trash
        else get_memory_folder(memory_id)
    )

    if not os.path.isdir(folder):
        return None

    photos, videos = count_media(folder)

    return {
        "id": memory_id,
        "folder": folder,
        "photos": photos,
        "videos": videos,
        "message": message_exists(folder),
        "created": folder_created_time(folder),
        "message_text": read_message(folder),
        "qr": os.path.exists(get_qr_path(memory_id))
    }


def get_all_memories():

    memories = []

    if not os.path.isdir(MEMORIES_DIR):
        return memories

    for memory_id in os.listdir(MEMORIES_DIR):

        folder = os.path.join(
            MEMORIES_DIR,
            memory_id
        )

        if not os.path.isdir(folder):
            continue

        if not safe_memory_id(memory_id):
            continue

        info = get_memory_info(memory_id)

        if info:
            memories.append(info)

    memories.sort(
        key=lambda x: os.path.getctime(x["folder"]),
        reverse=True
    )

    return memories


def get_all_trash():

    trash = []

    if not os.path.isdir(TRASH_DIR):
        return trash

    for memory_id in os.listdir(TRASH_DIR):

        folder = os.path.join(
            TRASH_DIR,
            memory_id
        )

        if not os.path.isdir(folder):
            continue

        if not safe_memory_id(memory_id):
            continue

        info = get_memory_info(
            memory_id,
            trash=True
        )

        if info:
            trash.append(info)

    trash.sort(
        key=lambda x: os.path.getctime(x["folder"]),
        reverse=True
    )

    return trash


def generate_qr(memory_id):

    qr_path = get_qr_path(memory_id)

    os.makedirs(
        os.path.dirname(qr_path),
        exist_ok=True
    )

    memory_url = url_for(
        "view_memory",
        memory_id=memory_id,
        _external=True
    )

    img = qrcode.make(memory_url)

    img.save(qr_path)

    return qr_path


def ensure_qr(memory_id):

    qr_path = get_qr_path(memory_id)

    if not os.path.isfile(qr_path):
        try:
            generate_qr(memory_id)
        except Exception:
            return False

    return True


def move_to_trash(memory_id):

    source = get_memory_folder(memory_id)
    destination = get_trash_folder(memory_id)

    if not os.path.isdir(source):
        return False

    os.makedirs(TRASH_DIR, exist_ok=True)

    if os.path.exists(destination):
        shutil.rmtree(destination)

    shutil.move(
        source,
        destination
    )

    qr_path = get_qr_path(memory_id)

    if os.path.exists(qr_path):
        os.remove(qr_path)

    return True


def restore_from_trash(memory_id):

    source = get_trash_folder(memory_id)
    destination = get_memory_folder(memory_id)

    if not os.path.isdir(source):
        return False

    if os.path.exists(destination):
        return False

    shutil.move(
        source,
        destination
    )

    ensure_qr(memory_id)

    return True


def permanent_delete(memory_id):

    trash_folder = get_trash_folder(memory_id)

    if os.path.isdir(trash_folder):
        shutil.rmtree(trash_folder)

    qr_path = get_qr_path(memory_id)

    if os.path.exists(qr_path):
        os.remove(qr_path)

    return True


# =========================================================
# CUSTOMER HOME
# =========================================================

@app.route("/")
def home():

    index_file = os.path.join(
        BASE_DIR,
        "index.html"
    )

    if os.path.isfile(index_file):

        return send_from_directory(
            BASE_DIR,
            "index.html"
        )

    return """
    <h1>Memory QR</h1>
    <p>Customer website is ready.</p>
    """


# =========================================================
# CREATE MEMORY
# =========================================================

@app.route(
    "/create-memory",
    methods=["POST"]
)
def create_memory():

    try:

        memory_id = create_memory_id()

        folder = get_memory_folder(memory_id)

        os.makedirs(folder, exist_ok=True)

        uploaded_files = request.files.getlist("files")

        for uploaded in uploaded_files:

            if not uploaded:
                continue

            filename = os.path.basename(
                uploaded.filename or ""
            )

            if not filename:
                continue

            destination = os.path.join(
                folder,
                filename
            )

            uploaded.save(destination)

        message = request.form.get(
            "message",
            ""
        )

        if message:

            with open(
                os.path.join(
                    folder,
                    "message.txt"
                ),
                "w",
                encoding="utf-8"
            ) as f:

                f.write(message)

        ensure_qr(memory_id)

        memory_url = url_for(
            "view_memory",
            memory_id=memory_id,
            _external=True
        )

        return jsonify({
            "success": True,
            "memory_id": memory_id,
            "memory_url": memory_url,
            "qr_url": url_for(
                "download_qr",
                memory_id=memory_id,
                _external=True
            )
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================================================
# UPLOAD COMPATIBILITY ROUTE
# =========================================================

@app.route(
    "/upload",
    methods=["POST"]
)
def upload():

    try:

        memory_id = request.form.get(
            "memory_id"
        )

        if not memory_id:
            memory_id = request.args.get(
                "memory_id"
            )

        if not memory_id:
            return jsonify({
                "success": False,
                "error": "Memory ID missing"
            }), 400

        if not safe_memory_id(memory_id):
            return jsonify({
                "success": False,
                "error": "Invalid memory ID"
            }), 400

        folder = get_memory_folder(memory_id)

        os.makedirs(
            folder,
            exist_ok=True
        )

        files = request.files.getlist(
            "files"
        )

        if not files:
            files = request.files.getlist(
                "photos"
            ) + request.files.getlist(
                "videos"
            )

        saved = 0

        for uploaded in files:

            if not uploaded:
                continue

            filename = os.path.basename(
                uploaded.filename or ""
            )

            if not filename:
                continue

            uploaded.save(
                os.path.join(
                    folder,
                    filename
                )
            )

            saved += 1

        ensure_qr(memory_id)

        return jsonify({
            "success": True,
            "saved": saved,
            "memory_id": memory_id
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================================================
# SAVE MESSAGE
# =========================================================

@app.route(
    "/save-message",
    methods=["POST"]
)
def save_message():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        memory_id = (
            data.get("memory_id")
            or request.form.get("memory_id")
        )

        message = (
            data.get("message")
            if "message" in data
            else request.form.get(
                "message",
                ""
            )
        )

        if not memory_id:
            return jsonify({
                "success": False,
                "error": "Memory ID missing"
            }), 400

        if not safe_memory_id(memory_id):
            return jsonify({
                "success": False,
                "error": "Invalid memory ID"
            }), 400

        folder = get_memory_folder(
            memory_id
        )

        if not os.path.isdir(folder):
            return jsonify({
                "success": False,
                "error": "Memory not found"
            }), 404

        with open(
            os.path.join(
                folder,
                "message.txt"
            ),
            "w",
            encoding="utf-8"
        ) as f:

            f.write(message or "")

        return jsonify({
            "success": True
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================================================
# MEMORY FILES
# =========================================================

@app.route(
    "/memories/<memory_id>/<path:filename>"
)
def memory_file(
    memory_id,
    filename
):

    if not safe_memory_id(memory_id):
        return "Invalid memory", 400

    folder = get_memory_folder(
        memory_id
    )

    if not os.path.isdir(folder):
        return "Memory not found", 404

    return send_from_directory(
        folder,
        filename
    )


# =========================================================
# PUBLIC MEMORY PAGE
# =========================================================

MEMORY_PAGE = """
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1.0"
>

<meta
name="robots"
content="noindex,nofollow,noarchive"
>

<title>Memory QR</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
font-family:Arial,sans-serif;
background:
linear-gradient(
135deg,
#080b18,
#10162d,
#081b22
);
color:white;
min-height:100vh;
}

.container{
width:min(1000px,94%);
margin:auto;
padding:30px 0 60px;
}

.header{
text-align:center;
padding:30px 15px;
}

.header h1{
font-size:38px;
margin:0 0 10px;
}

.header p{
color:#b8c2d9;
}

.card{
background:rgba(255,255,255,.07);
border:1px solid rgba(255,255,255,.12);
border-radius:24px;
padding:22px;
margin:20px 0;
box-shadow:0 15px 40px rgba(0,0,0,.25);
}

.message{
font-size:19px;
line-height:1.7;
white-space:pre-wrap;
}

.gallery{
display:grid;
grid-template-columns:
repeat(auto-fit,minmax(220px,1fr));
gap:15px;
}

.gallery img,
.gallery video{
width:100%;
border-radius:18px;
display:block;
background:#05070c;
}

.footer{
text-align:center;
color:#9ba7c2;
margin-top:35px;
font-size:14px;
}

</style>

</head>

<body>

<div class="container">

<div class="header">

<h1>💖 Memory QR</h1>

<p>A special memory, saved forever.</p>

</div>

{% if message %}

<div class="card">

<h2>💌 Message</h2>

<div class="message">
{{ message }}
</div>

</div>

{% endif %}


{% if media %}

<div class="card">

<h2>📸 Memories</h2>

<div class="gallery">

{% for item in media %}

{% if item.type == "image" %}

<img
src="{{ item.url }}"
loading="lazy"
>

{% elif item.type == "video" %}

<video
controls
preload="metadata"
src="{{ item.url }}"
></video>

{% endif %}

{% endfor %}

</div>

</div>

{% endif %}


<div class="footer">

This site is made by Aquib Khan ❤️

</div>

</div>

</body>

</html>
"""


@app.route(
    "/memory/<memory_id>"
)
def view_memory(memory_id):

    if not safe_memory_id(memory_id):
        return "Invalid memory", 400

    folder = get_memory_folder(
        memory_id
    )

    if not os.path.isdir(folder):
        return """
        <h2 style="font-family:Arial;text-align:center;margin-top:80px">
        Memory not found
        </h2>
        """, 404

    message = read_message(folder)

    media = []

    for filename in get_files(folder):

        if filename == "message.txt":
            continue

        ext = os.path.splitext(
            filename
        )[1].lower()

        if ext in IMAGE_EXTENSIONS:

            media.append({
                "type": "image",
                "url": url_for(
                    "memory_file",
                    memory_id=memory_id,
                    filename=filename
                )
            })

        elif ext in VIDEO_EXTENSIONS:

            media.append({
                "type": "video",
                "url": url_for(
                    "memory_file",
                    memory_id=memory_id,
                    filename=filename
                )
            })

    template_file = os.path.join(
        BASE_DIR,
        "templates",
        "memory.html"
    )

    if os.path.isfile(template_file):

        try:

            from flask import render_template

            return render_template(
                "memory.html",
                memory_id=memory_id,
                message=message,
                media=media
            )

        except Exception:
            pass

    return render_template_string(
        MEMORY_PAGE,
        memory_id=memory_id,
        message=message,
        media=media
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        )

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):

            session.clear()

            session["admin_logged_in"] = True

            return redirect(
                url_for("admin_dashboard")
            )

        error = "Invalid username or password."

    else:

        error = ""

    return render_template_string(
        """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1.0"
>

<title>Memory QR Admin Login</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
min-height:100vh;
display:flex;
align-items:center;
justify-content:center;
font-family:Arial,sans-serif;
background:
radial-gradient(
circle at top,
#202b58,
#080b18 60%
);
color:white;
padding:20px;
}

.login{
width:min(430px,100%);
background:rgba(255,255,255,.08);
border:1px solid rgba(255,255,255,.14);
border-radius:26px;
padding:32px;
box-shadow:0 25px 70px rgba(0,0,0,.45);
}

.logo{
width:72px;
height:72px;
margin:auto;
border-radius:22px;
display:flex;
align-items:center;
justify-content:center;
font-size:38px;
background:
linear-gradient(
135deg,
#ff4d8d,
#7c5cff
);
}

h1{
text-align:center;
margin:18px 0 7px;
}

.sub{
text-align:center;
color:#aeb8d0;
margin-bottom:25px;
}

label{
display:block;
margin:14px 0 7px;
color:#dce3f5;
font-size:14px;
}

.inputbox{
display:flex;
align-items:center;
background:#0c1122;
border:1px solid #293453;
border-radius:14px;
overflow:hidden;
}

input{
width:100%;
border:0;
outline:0;
background:transparent;
color:white;
padding:14px;
font-size:16px;
}

.eye{
padding:0 14px;
cursor:pointer;
font-size:20px;
}

button{
width:100%;
margin-top:22px;
border:0;
border-radius:14px;
padding:15px;
font-size:16px;
font-weight:bold;
color:white;
cursor:pointer;
background:
linear-gradient(
135deg,
#ff4d8d,
#7657ff
);
}

.error{
background:rgba(255,70,100,.13);
border:1px solid rgba(255,70,100,.35);
padding:12px;
border-radius:12px;
color:#ffb5c5;
margin-bottom:15px;
text-align:center;
}

.back{
display:block;
text-align:center;
margin-top:20px;
color:#aeb8d0;
text-decoration:none;
}

</style>

</head>

<body>

<div class="login">

<div class="logo">💖</div>

<h1>Memory QR</h1>

<div class="sub">
Admin Dashboard
</div>

{% if error %}

<div class="error">
{{ error }}
</div>

{% endif %}

<form method="POST">

<label>Username</label>

<div class="inputbox">

<input
type="text"
name="username"
autocomplete="username"
required
>

</div>


<label>Password</label>

<div class="inputbox">

<input
id="password"
type="password"
name="password"
autocomplete="current-password"
required
>

<div
class="eye"
onclick="togglePassword()"
>
👁️
</div>

</div>


<button type="submit">
Login to Dashboard
</button>

</form>

<a
class="back"
href="/"
>
← Back to Website
</a>

</div>


<script>

function togglePassword(){

const input =
document.getElementById("password");

if(input.type === "password"){
input.type = "text";
}else{
input.type = "password";
}

}

</script>

</body>

</html>
""",
        error=error
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin_dashboard():

    login_check = require_admin()

    if login_check:
        return login_check

    memories = get_all_memories()

    trash = get_all_trash()

    stats = get_stats()

    query = request.args.get(
        "q",
        ""
    ).strip().lower()

    if query:

        memories = [
            m for m in memories
            if (
                query in m["id"].lower()
                or query in m["created"].lower()
                or query in m["message_text"].lower()
            )
        ]

        trash = [
            m for m in trash
            if (
                query in m["id"].lower()
                or query in m["created"].lower()
                or query in m["message_text"].lower()
            )
        ]

    for memory in memories:
        ensure_qr(memory["id"])
        memory["qr"] = True

    return render_template_string(
        ADMIN_DASHBOARD,
        memories=memories,
        trash=trash,
        stats=stats,
        query=query
    )


# =========================================================
# ADMIN TRASH ONE
# =========================================================

@app.route(
    "/admin/trash/<memory_id>",
    methods=["POST"]
)
def admin_trash(memory_id):

    login_check = require_admin()

    if login_check:
        return login_check

    if safe_memory_id(memory_id):
        move_to_trash(memory_id)

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# ADMIN TRASH SELECTED
# =========================================================

@app.route(
    "/admin/trash-selected",
    methods=["POST"]
)
def admin_trash_selected():

    login_check = require_admin()

    if login_check:
        return login_check

    selected = request.form.getlist(
        "selected"
    )

    for memory_id in selected:

        if safe_memory_id(memory_id):
            try:
                move_to_trash(memory_id)
            except Exception:
                pass

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# RESTORE
# =========================================================

@app.route(
    "/admin/restore/<memory_id>",
    methods=["POST"]
)
def admin_restore(memory_id):

    login_check = require_admin()

    if login_check:
        return login_check

    if safe_memory_id(memory_id):

        try:
            restore_from_trash(
                memory_id
            )
        except Exception:
            pass

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# PERMANENT DELETE
# =========================================================

@app.route(
    "/admin/permanent-delete/<memory_id>",
    methods=["POST"]
)
def admin_permanent_delete(memory_id):

    login_check = require_admin()

    if login_check:
        return login_check

    if safe_memory_id(memory_id):

        try:
            permanent_delete(
                memory_id
            )
        except Exception:
            pass

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# PERMANENT DELETE SELECTED
# =========================================================

@app.route(
    "/admin/permanent-delete-selected",
    methods=["POST"]
)
def admin_permanent_delete_selected():

    login_check = require_admin()

    if login_check:
        return login_check

    selected = request.form.getlist(
        "selected"
    )

    for memory_id in selected:

        if safe_memory_id(memory_id):

            try:
                permanent_delete(
                    memory_id
                )
            except Exception:
                pass

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# DELETE QR ONLY
# =========================================================

@app.route(
    "/admin/trash-qr/<memory_id>",
    methods=["POST"]
)
def admin_trash_qr(memory_id):

    login_check = require_admin()

    if login_check:
        return login_check

    if safe_memory_id(memory_id):

        qr_path = get_qr_path(
            memory_id
        )

        if os.path.exists(qr_path):
            os.remove(qr_path)

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# DOWNLOAD / GENERATE QR
# =========================================================

@app.route(
    "/admin/download-qr/<memory_id>"
)
def admin_download_qr(memory_id):

    login_check = require_admin()

    if login_check:
        return login_check

    if not safe_memory_id(memory_id):
        return "Invalid memory", 400

    if not os.path.isdir(
        get_memory_folder(memory_id)
    ):
        return "Memory not found", 404

    ensure_qr(memory_id)

    qr_path = get_qr_path(
        memory_id
    )

    if not os.path.isfile(qr_path):
        return "QR generation failed", 500

    return send_from_directory(
        QR_DIR,
        memory_id + ".png",
        as_attachment=True
    )


# =========================================================
# QR VIEW
# =========================================================

@app.route(
    "/admin/view-qr/<memory_id>"
)
def admin_view_qr(memory_id):

    login_check = require_admin()

    if login_check:
        return login_check

    if not safe_memory_id(memory_id):
        return "Invalid memory", 400

    if not os.path.isdir(
        get_memory_folder(memory_id)
    ):
        return "Memory not found", 404

    ensure_qr(memory_id)

    qr_path = get_qr_path(
        memory_id
    )

    if not os.path.isfile(qr_path):
        return "QR unavailable", 500

    return send_from_directory(
        QR_DIR,
        memory_id + ".png"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route(
    "/admin/logout"
)
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# =========================================================
# ADMIN HTML
# =========================================================

ADMIN_DASHBOARD = """

<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1.0"
>

<meta
name="robots"
content="noindex,nofollow"
>

<title>Memory QR Dashboard</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
font-family:Arial,sans-serif;
background:
linear-gradient(
135deg,
#070a15,
#0d1225,
#081c22
);
color:white;
min-height:100vh;
}

a{
color:inherit;
}

.topbar{
position:sticky;
top:0;
z-index:20;
background:rgba(7,10,21,.88);
backdrop-filter:blur(18px);
border-bottom:1px solid rgba(255,255,255,.09);
}

.topbar-inner{
width:min(1250px,94%);
margin:auto;
min-height:76px;
display:flex;
align-items:center;
justify-content:space-between;
gap:15px;
}

.brand{
display:flex;
align-items:center;
gap:12px;
font-weight:bold;
font-size:20px;
}

.brand-icon{
width:44px;
height:44px;
border-radius:14px;
display:flex;
align-items:center;
justify-content:center;
background:
linear-gradient(
135deg,
#ff4d8d,
#7657ff
);
}

.logout{
text-decoration:none;
padding:11px 16px;
border-radius:12px;
background:rgba(255,255,255,.08);
border:1px solid rgba(255,255,255,.1);
}

.container{
width:min(1250px,94%);
margin:auto;
padding:28px 0 60px;
}

.hero{
margin-bottom:24px;
}

.hero h1{
font-size:36px;
margin:0 0 8px;
}

.hero p{
color:#aeb8d0;
margin:0;
}

.stats{
display:grid;
grid-template-columns:
repeat(4,1fr);
gap:15px;
margin:25px 0;
}

.stat{
padding:20px;
border-radius:20px;
background:rgba(255,255,255,.065);
border:1px solid rgba(255,255,255,.1);
}

.stat-icon{
font-size:25px;
}

.stat-number{
font-size:30px;
font-weight:bold;
margin-top:8px;
}

.stat-label{
color:#9eabc6;
font-size:14px;
margin-top:4px;
}

.tools{
display:flex;
gap:10px;
align-items:center;
flex-wrap:wrap;
margin:22px 0;
}

.search{
flex:1;
min-width:230px;
display:flex;
background:#0d1327;
border:1px solid #263351;
border-radius:14px;
overflow:hidden;
}

.search input{
flex:1;
background:transparent;
border:0;
outline:0;
color:white;
padding:13px 15px;
font-size:15px;
}

.search button{
border:0;
background:#1b2540;
color:white;
padding:0 18px;
cursor:pointer;
}

.bulk{
border:0;
border-radius:13px;
padding:13px 16px;
font-weight:bold;
cursor:pointer;
}

.bulk-trash{
background:#ff426e;
color:white;
}

.bulk-delete{
background:#b72846;
color:white;
}

.tabs{
display:flex;
gap:8px;
margin-bottom:20px;
}

.tab{
padding:11px 18px;
border-radius:12px;
background:rgba(255,255,255,.06);
border:1px solid rgba(255,255,255,.09);
text-decoration:none;
cursor:pointer;
}

.tab.active{
background:
linear-gradient(
135deg,
#6f56ff,
#a43cff
);
}

.section{
display:none;
}

.section.active{
display:block;
}

.memory-card{
position:relative;
display:grid;
grid-template-columns:
auto 1fr auto;
gap:16px;
align-items:center;
padding:18px;
margin-bottom:13px;
border-radius:20px;
background:rgba(255,255,255,.06);
border:1px solid rgba(255,255,255,.09);
}

.checkbox{
width:20px;
height:20px;
}

.memory-main{
min-width:0;
}

.memory-id{
font-size:17px;
font-weight:bold;
word-break:break-all;
}

.meta{
display:flex;
flex-wrap:wrap;
gap:7px;
margin-top:9px;
}

.badge{
padding:6px 9px;
border-radius:9px;
background:rgba(255,255,255,.07);
color:#b9c4dd;
font-size:12px;
}

.memory-date{
color:#8e9bb7;
font-size:13px;
margin-top:8px;
}

.actions{
display:flex;
gap:7px;
flex-wrap:wrap;
justify-content:flex-end;
}

.action{
text-decoration:none;
border:0;
cursor:pointer;
padding:9px 11px;
border-radius:10px;
font-size:12px;
font-weight:bold;
background:#18223a;
color:white;
}

.action.open{
background:#3566ff;
}

.action.qr{
background:#7b4dff;
}

.action.download{
background:#168c69;
}

.action.trash{
background:#d83d5d;
}

.action.restore{
background:#178b69;
}

.action.delete{
background:#9e243e;
}

.action-form{
display:inline;
}

.empty{
padding:45px 20px;
text-align:center;
border-radius:20px;
background:rgba(255,255,255,.04);
border:1px dashed rgba(255,255,255,.15);
color:#9eabc6;
}

.trash-head{
padding:16px;
margin-bottom:18px;
border-radius:18px;
background:rgba(255,70,100,.08);
border:1px solid rgba(255,70,100,.15);
color:#ffb2c1;
}

@media(max-width:900px){

.stats{
grid-template-columns:
repeat(2,1fr);
}

.memory-card{
grid-template-columns:auto 1fr;
}

.actions{
grid-column:2;
justify-content:flex-start;
}

}

@media(max-width:600px){

.container{
width:92%;
}

.hero h1{
font-size:29px;
}

.stats{
grid-template-columns:1fr 1fr;
gap:10px;
}

.stat{
padding:15px;
}

.stat-number{
font-size:24px;
}

.memory-card{
padding:14px;
}

.actions{
grid-column:1 / -1;
}

.action{
flex:1;
text-align:center;
}

}

</style>

</head>

<body>


<div class="topbar">

<div class="topbar-inner">

<div class="brand">

<div class="brand-icon">
💖
</div>

<div>
Memory QR
<br>
<span
style="font-size:12px;color:#8e9bb7;font-weight:normal"
>
Admin Dashboard
</span>
</div>

</div>

<a
class="logout"
href="/admin/logout"
>
Logout
</a>

</div>

</div>


<div class="container">


<div class="hero">

<h1>Memory Dashboard</h1>

<p>
Manage every memory created on your website.
</p>

</div>


<div class="stats">

<div class="stat">

<div class="stat-icon">
💾
</div>

<div class="stat-number">
{{ memories|length }}
</div>

<div class="stat-label">
Active Memories
</div>

</div>


<div class="stat">

<div class="stat-icon">
🗑️
</div>

<div class="stat-number">
{{ trash|length }}
</div>

<div class="stat-label">
Trash
</div>

</div>


<div class="stat">

<div class="stat-icon">
👀
</div>

<div class="stat-number">
{{ stats.get("memory_views",0) }}
</div>

<div class="stat-label">
Memory Views
</div>

</div>


<div class="stat">

<div class="stat-icon">
📊
</div>

<div class="stat-number">
{{ stats.get("total_visits",0) }}
</div>

<div class="stat-label">
Total Visits
</div>

</div>

</div>


<div class="tools">

<form
class="search"
method="GET"
action="/admin"
>

<input
type="text"
name="q"
value="{{ query }}"
placeholder="Search memory ID, date or message..."
>

<button type="submit">
🔎
</button>

</form>

</div>


<div class="tabs">

<button
class="tab active"
id="activeTabButton"
onclick="showTab('active')"
>
💾 Memories
<span>
({{ memories|length }})
</span>
</button>

<button
class="tab"
id="trashTabButton"
onclick="showTab('trash')"
>
🗑️ Trash
<span>
({{ trash|length }})
</span>
</button>

</div>


<!-- ================================================= -->
<!-- ACTIVE MEMORIES -->
<!-- ================================================= -->

<div
id="active"
class="section active"
>

<form
method="POST"
action="/admin/trash-selected"
id="activeForm"
>

<div
style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap"
>

<button
type="button"
class="bulk"
onclick="selectAllActive()"
>
☑ Select All
</button>

<button
type="button"
class="bulk bulk-trash"
onclick="submitActiveTrash()"
>
🗑 Move Selected to Trash
</button>

</div>


{% if memories %}

{% for m in memories %}

<div class="memory-card">

<input
class="checkbox active-check"
type="checkbox"
name="selected"
value="{{ m.id }}"
>


<div class="memory-main">

<div class="memory-id">
{{ m.id }}
</div>

<div class="meta">

<span class="badge">
📸 {{ m.photos }} Photos
</span>

<span class="badge">
🎬 {{ m.videos }} Videos
</span>

{% if m.message %}

<span class="badge">
💌 Message
</span>

{% endif %}

<span class="badge">
🔗 QR Saved
</span>

</div>

<div class="memory-date">
Created: {{ m.created }}
</div>

</div>


<div class="actions">

<a
class="action open"
href="/memory/{{ m.id }}"
target="_blank"
>
Open
</a>

<a
class="action qr"
href="/admin/view-qr/{{ m.id }}"
target="_blank"
>
View QR
</a>

<a
class="action download"
href="/admin/download-qr/{{ m.id }}"
>
Download QR
</a>

<form
class="action-form"
method="POST"
action="/admin/trash/{{ m.id }}"
>

<button
class="action trash"
type="submit"
onclick="return confirm('Move this memory to Trash?')"
>
Trash
</button>

</form>

</div>

</div>

{% endfor %}

{% else %}

<div class="empty">

<h2>No memories found</h2>

<p>
New customer memories will appear here automatically.
</p>

</div>

{% endif %}

</form>

</div>


<!-- ================================================= -->
<!-- TRASH -->
<!-- ================================================= -->

<div
id="trash"
class="section"
>

<div class="trash-head">

<strong>🗑️ Trash</strong>

<br>

Memories moved here are not permanently deleted yet.
You can restore them or permanently delete them.

</div>


{% if trash %}

<div
style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap"
>

<button
type="button"
class="bulk"
onclick="selectAllTrash()"
>
☑ Select All
</button>

<button
type="button"
class="bulk bulk-delete"
onclick="permanentDeleteSelected()"
>
⚠️ Permanently Delete Selected
</button>

</div>


{% for m in trash %}

<div class="memory-card">

<input
class="checkbox trash-check"
type="checkbox"
value="{{ m.id }}"
>


<div class="memory-main">

<div class="memory-id">
{{ m.id }}
</div>

<div class="meta">

<span class="badge">
📸 {{ m.photos }} Photos
</span>

<span class="badge">
🎬 {{ m.videos }} Videos
</span>

{% if m.message %}

<span class="badge">
💌 Message
</span>

{% endif %}

</div>

<div class="memory-date">
Moved/Created: {{ m.created }}
</div>

</div>


<div class="actions">

<form
class="action-form"
method="POST"
action="/admin/restore/{{ m.id }}"
>

<button
class="action restore"
type="submit"
>
↩ Restore
</button>

</form>


<form
class="action-form"
method="POST"
action="/admin/permanent-delete/{{ m.id }}"
>

<button
class="action delete"
type="submit"
onclick="return confirm('Permanently delete this memory? This cannot be undone.')"
>
Delete Forever
</button>

</form>

</div>

</div>

{% endfor %}

{% else %}

<div class="empty">

<h2>Trash is empty</h2>

<p>
Deleted memories will appear here before permanent deletion.
</p>

</div>

{% endif %}

</div>


</div>


<script>

function showTab(tab){

document
.getElementById("active")
.classList.remove("active");

document
.getElementById("trash")
.classList.remove("active");

document
.getElementById("activeTabButton")
.classList.remove("active");

document
.getElementById("trashTabButton")
.classList.remove("active");


if(tab === "active"){

document
.getElementById("active")
.classList.add("active");

document
.getElementById("activeTabButton")
.classList.add("active");

}else{

document
.getElementById("trash")
.classList.add("active");

document
.getElementById("trashTabButton")
.classList.add("active");

}

}


function selectAllActive(){

const boxes =
document.querySelectorAll(
".active-check"
);

let allChecked = true;

boxes.forEach(function(box){

if(!box.checked){
allChecked = false;
}

});

boxes.forEach(function(box){

box.checked = !allChecked;

});

}


function submitActiveTrash(){

const boxes =
document.querySelectorAll(
".active-check:checked"
);

if(boxes.length === 0){

alert(
"Please select at least one memory."
);

return;

}

if(!confirm(
"Move selected memories to Trash?"
)){

return;

}

document
.getElementById("activeForm")
.submit();

}


function selectAllTrash(){

const boxes =
document.querySelectorAll(
".trash-check"
);

let allChecked = true;

boxes.forEach(function(box){

if(!box.checked){
allChecked = false;
}

});

boxes.forEach(function(box){

box.checked = !allChecked;

});

}


function permanentDeleteSelected(){

const boxes =
document.querySelectorAll(
".trash-check:checked"
);

if(boxes.length === 0){

alert(
"Please select at least one memory."
);

return;

}

if(!confirm(
"Permanently delete selected memories? This cannot be undone."
)){

return;

}

const form =
document.createElement("form");

form.method = "POST";

form.action =
"/admin/permanent-delete-selected";


boxes.forEach(function(box){

const input =
document.createElement("input");

input.type = "hidden";

input.name = "selected";

input.value = box.value;

form.appendChild(input);

});

document.body.appendChild(form);

form.submit();

}

</script>


</body>

</html>

"""


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "8000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
