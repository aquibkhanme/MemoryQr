from flask import Flask, request, jsonify, send_from_directory, session, redirect
import os
import qrcode
import uuid
import json
import shutil
from functools import wraps
from werkzeug.utils import secure_filename
from markupsafe import escape

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "memoryqr-secret-change-this"
)

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "MemoryQR@123"
)

UPLOAD_FOLDER = "memories"
QR_FOLDER = "static/qr"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)


def memory_folder(memory_id):
    return os.path.join(
        UPLOAD_FOLDER,
        memory_id
    )


def message_file(memory_id):
    return os.path.join(
        memory_folder(memory_id),
        "message.json"
    )


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect("/admin/login")
        return func(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/create-memory", methods=["POST"])
def create_memory():

    memory_id = str(uuid.uuid4())[:8]

    folder = memory_folder(memory_id)
    os.makedirs(folder, exist_ok=True)

    url = request.host_url.rstrip("/") + \
        "/memory/" + memory_id

    qr = qrcode.make(url)

    qr.save(
        os.path.join(
            QR_FOLDER,
            memory_id + ".png"
        )
    )

    return jsonify({
        "success": True,
        "memory_id": memory_id,
        "qr": "/static/qr/" + memory_id + ".png",
        "memory_url": url
    })


@app.route("/upload", methods=["POST"])
def upload():

    memory_id = request.form.get("memory_id")

    if not memory_id:
        return jsonify({
            "success": False,
            "error": "Memory ID missing"
        }), 400

    folder = memory_folder(memory_id)

    if not os.path.exists(folder):
        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404

    files = request.files.getlist("file")

    if not files:
        files = request.files.getlist("files")

    saved = []

    for file in files:

        if not file or not file.filename:
            continue

        filename = secure_filename(
            file.filename
        )

        if not filename:
            continue

        name, ext = os.path.splitext(filename)
        original = filename
        count = 1

        while os.path.exists(
            os.path.join(folder, filename)
        ):
            filename = (
                name +
                "_" +
                str(count) +
                ext
            )
            count += 1

        file.save(
            os.path.join(folder, filename)
        )

        saved.append(filename)

    if not saved:
        return jsonify({
            "success": False,
            "error": "No file saved"
        }), 400

    return jsonify({
        "success": True,
        "files": saved
    })


@app.route("/save-message", methods=["POST"])
def save_message():

    data = request.get_json(
        silent=True
    ) or {}

    memory_id = data.get("memory_id")
    message = str(
        data.get("message", "")
    )

    if not memory_id:
        return jsonify({
            "success": False,
            "error": "Memory ID missing"
        }), 400

    folder = memory_folder(memory_id)

    if not os.path.exists(folder):
        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404

    message = message[:70000]

    with open(
        message_file(memory_id),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {"message": message},
            f,
            ensure_ascii=False,
            indent=2
        )

    return jsonify({
        "success": True,
        "characters": len(message)
    })


@app.route(
    "/memories/<memory_id>/<path:filename>"
)
def memory_file(memory_id, filename):

    folder = memory_folder(memory_id)

    if not os.path.exists(folder):
        return "Memory not found", 404

    return send_from_directory(
        folder,
        filename
    )


@app.route("/memory/<memory_id>")
def memory_page(memory_id):

    folder = memory_folder(memory_id)

    if not os.path.exists(folder):
        return "Memory not found", 404

    photos = []
    videos = []

    for filename in os.listdir(folder):

        lower = filename.lower()

        if lower.endswith((
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif"
        )):
            photos.append(filename)

        elif lower.endswith((
            ".mp4",
            ".webm",
            ".mov",
            ".mkv",
            ".avi",
            ".m4v"
        )):
            videos.append(filename)

    message = ""

    mf = message_file(memory_id)

    if os.path.exists(mf):

        try:

            with open(
                mf,
                "r",
                encoding="utf-8"
            ) as f:

                message = json.load(
                    f
                ).get(
                    "message",
                    ""
                )

        except Exception:
            message = ""

    photo_html = ""

    for filename in photos:

        photo_html += f"""
        <div class="photo">
            <img src="/memories/{memory_id}/{escape(filename)}">
        </div>
        """

    video_html = ""

    for filename in videos:

        video_html += f"""
        <video controls playsinline>
            <source src="/memories/{memory_id}/{escape(filename)}">
        </video>
        """

    if not photo_html:
        photo_html = "<p>No photos added yet.</p>"

    if not video_html:
        video_html = "<p>No videos added yet.</p>"

    if not message:
        message = "Your special message will appear here."

    return f"""
<!DOCTYPE html>
<html>
<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1.0">

<title>Your Memory • Memory QR</title>

<style>

* {{
    box-sizing:border-box;
}}

body {{
    margin:0;
    padding:20px;
    font-family:Arial,sans-serif;
    color:white;
    background:
    linear-gradient(
        135deg,
        #090b18,
        #1b1030,
        #071d27
    );
}}

.container {{
    max-width:1000px;
    margin:auto;
}}

.header {{
    text-align:center;
    padding:35px 10px;
}}

.logo {{
    color:#ff62c5;
    font-size:22px;
    font-weight:bold;
}}

h1 {{
    font-size:42px;
    margin:15px 0;
}}

.section {{
    margin:25px 0;
    padding:25px;
    border-radius:25px;
    background:#ffffff0d;
    border:1px solid #ffffff1c;
}}

h2 {{
    color:#ff82d2;
}}

.photos {{
    display:grid;
    grid-template-columns:
    repeat(auto-fit,minmax(180px,1fr));
    gap:15px;
}}

.photo {{
    overflow:hidden;
    border-radius:20px;
}}

.photo img {{
    width:100%;
    height:220px;
    object-fit:cover;
    display:block;
}}

video {{
    width:100%;
    max-width:700px;
    display:block;
    margin:15px auto;
    border-radius:20px;
}}

.message {{
    width:100%;
    padding:25px;
    border-radius:20px;
    background:
    linear-gradient(
        135deg,
        #522044,
        #34305d
    );
    font-size:18px;
    line-height:1.8;

    white-space:pre-wrap;
    overflow-wrap:anywhere;
    word-break:break-word;
    text-align:left;
}}

.footer {{
    text-align:center;
    color:#777;
    padding:30px;
}}

</style>

</head>

<body>

<div class="container">

<div class="header">

<div class="logo">
♥ MEMORY QR
</div>

<h1>
Your Memories, Forever.
</h1>

</div>

<div class="section">

<h2>
📸 Beautiful Moments
</h2>

<div class="photos">
{photo_html}
</div>

</div>

<div class="section">

<h2>
🎥 Memory Videos
</h2>

{video_html}

</div>

<div class="section">

<h2>
💌 Personal Diary
</h2>

<div class="message">
{escape(message)}
</div>

</div>

<div class="footer">
This site is made by Aquib Khan ❤️
</div>

</div>

</body>
</html>
"""


# ==================================================
# ADMIN LOGIN
# ==================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    error = ""

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
            and
            password == ADMIN_PASSWORD
        ):

            session["admin_logged_in"] = True

            return redirect("/admin")

        error = "Invalid username or password."

    return f"""
<!DOCTYPE html>
<html>
<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1.0">

<title>Memory QR Admin Login</title>

<style>

* {{
    box-sizing:border-box;
}}

body {{
    margin:0;
    min-height:100vh;
    display:flex;
    align-items:center;
    justify-content:center;
    padding:20px;
    font-family:Arial,sans-serif;
    color:white;
    background:
    linear-gradient(
        135deg,
        #090b18,
        #1d1030,
        #061d27
    );
}}

.login {{
    width:100%;
    max-width:420px;
    padding:35px;
    border-radius:28px;
    background:#ffffff0d;
    border:1px solid #ffffff1c;
}}

.logo {{
    text-align:center;
    color:#ff68c9;
    font-size:22px;
    font-weight:bold;
}}

h1 {{
    text-align:center;
}}

input {{
    width:100%;
    padding:16px;
    margin:8px 0;
    border:1px solid #ffffff20;
    border-radius:14px;
    background:#080a15;
    color:white;
    font-size:16px;
    outline:none;
}}

button {{
    width:100%;
    padding:16px;
    margin-top:12px;
    border:0;
    border-radius:15px;
    color:white;
    font-size:16px;
    font-weight:bold;
    background:
    linear-gradient(
        90deg,
        #ff4fb8,
        #755cff
    );
}}

.error {{
    color:#ff8b9e;
    text-align:center;
}}

</style>

</head>

<body>

<div class="login">

<div class="logo">
♥ MEMORY QR
</div>

<h1>
Admin Login 🔐
</h1>

<div class="error">
{escape(error)}
</div>

<form method="POST">

<input
type="text"
name="username"
placeholder="Username"
required>

<input
type="password"
name="password"
placeholder="Password"
required>

<button type="submit">
Login
</button>

</form>

</div>

</body>
</html>
"""


# ==================================================
# ADMIN DASHBOARD
# ==================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    memories = []

    if os.path.exists(
        UPLOAD_FOLDER
    ):

        for memory_id in os.listdir(
            UPLOAD_FOLDER
        ):

            folder = memory_folder(
                memory_id
            )

            if not os.path.isdir(folder):
                continue

            photos = 0
            videos = 0

            for filename in os.listdir(folder):

                lower = filename.lower()

                if lower.endswith((
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".gif"
                )):
                    photos += 1

                elif lower.endswith((
                    ".mp4",
                    ".webm",
                    ".mov",
                    ".mkv",
                    ".avi",
                    ".m4v"
                )):
                    videos += 1

            memories.append({
                "id": memory_id,
                "photos": photos,
                "videos": videos
            })

    memories.sort(
        key=lambda x: x["id"],
        reverse=True
    )

    total_memories = len(memories)

    total_photos = sum(
        x["photos"]
        for x in memories
    )

    total_videos = sum(
        x["videos"]
        for x in memories
    )

    rows = ""

    for item in memories:

        mid = escape(
            item["id"]
        )

        rows += f"""
        <div class="memory">

            <div>

                <strong>
                    Memory ID: {mid}
                </strong>

                <div class="stats">
                    📸 {item["photos"]}
                    &nbsp;&nbsp;
                    🎥 {item["videos"]}
                </div>

            </div>

            <div class="actions">

                <a
                href="/memory/{mid}"
                target="_blank">
                Open
                </a>

                <a
                class="delete"
                href="/admin/delete/{mid}"
                onclick="return confirm('Delete this memory permanently?')">
                Delete
                </a>

            </div>

        </div>
        """

    if not rows:

        rows = """
        <div class="empty">
            No memories created yet.
        </div>
        """

    return f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1.0">

<title>Memory QR Admin</title>

<style>

* {{
    box-sizing:border-box;
}}

body {{
    margin:0;
    padding:20px;
    font-family:Arial,sans-serif;
    color:white;
    background:
    linear-gradient(
        135deg,
        #080a16,
        #1b1030,
        #061c26
    );
}}

.container {{
    max-width:1100px;
    margin:auto;
}}

.top {{
    display:flex;
    justify-content:space-between;
    align-items:center;
    margin-bottom:30px;
}}

.logo {{
    color:#ff68c9;
    font-size:22px;
    font-weight:bold;
}}

.logout {{
    color:white;
    text-decoration:none;
    padding:10px 15px;
    border-radius:12px;
    background:#ffffff12;
}}

h1 {{
    font-size:35px;
}}

.subtitle {{
    color:#999;
}}

.stats-grid {{
    display:grid;
    grid-template-columns:
    repeat(auto-fit,minmax(200px,1fr));
    gap:15px;
    margin:25px 0;
}}

.stat {{
    padding:25px;
    border-radius:22px;
    background:#ffffff0d;
    border:1px solid #ffffff1c;
}}

.number {{
    font-size:35px;
    font-weight:bold;
}}

.label {{
    color:#999;
    margin-top:8px;
}}

.section {{
    padding:25px;
    border-radius:25px;
    background:#ffffff0d;
    border:1px solid #ffffff1c;
}}

.memory {{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:15px;
    padding:18px;
    margin:12px 0;
    border-radius:18px;
    background:#080a15;
}}

.stats {{
    color:#999;
    margin-top:8px;
}}

.actions {{
    display:flex;
    gap:8px;
}}

.actions a {{
    color:white;
    text-decoration:none;
    padding:10px 14px;
    border-radius:10px;
    background:#513a91;
}}

.actions .delete {{
    background:#7d2942;
}}

.empty {{
    text-align:center;
    color:#888;
    padding:30px;
}}

@media(max-width:600px) {{

    .memory {{
        flex-direction:column;
        align-items:flex-start;
    }}

    .top {{
        align-items:flex-start;
    }}

}}

</style>

</head>

<body>

<div class="container">

<div class="top">

<div class="logo">
♥ MEMORY QR ADMIN
</div>

<a
class="logout"
href="/admin/logout">
Logout
</a>

</div>

<h1>
Admin Dashboard
</h1>

<div class="subtitle">
Manage your Memory QR memories
</div>


<div class="stats-grid">

<div class="stat">

<div class="number">
{total_memories}
</div>

<div class="label">
Total Memories
</div>

</div>


<div class="stat">

<div class="number">
{total_photos}
</div>

<div class="label">
Total Photos
</div>

</div>


<div class="stat">

<div class="number">
{total_videos}
</div>

<div class="label">
Total Videos
</div>

</div>

</div>


<div class="section">

<h2>
📋 Memory Management
</h2>

{rows}

</div>

</div>

</body>

</html>
"""


# ==================================================
# DELETE
# ==================================================

@app.route(
    "/admin/delete/<memory_id>"
)
@admin_required
def delete_memory(memory_id):

    folder = memory_folder(
        memory_id
    )

    if os.path.exists(folder):

        shutil.rmtree(folder)

    qr = os.path.join(
        QR_FOLDER,
        memory_id + ".png"
    )

    if os.path.exists(qr):
        os.remove(qr)

    return redirect("/admin")


# ==================================================
# LOGOUT
# ==================================================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        "/admin/login"
    )


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=8000,
        debug=False
    )
