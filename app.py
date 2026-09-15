from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    session,
    redirect,
    url_for,
    render_template_string
)

import os
import qrcode
import uuid
import json
import shutil

from werkzeug.utils import secure_filename
from markupsafe import escape


app = Flask(__name__)

# ==============================
# SECURITY / ADMIN SETTINGS
# ==============================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "memoryqr-change-this-secret"
)

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "MemoryQR@123"
)


# ==============================
# FOLDERS
# ==============================

UPLOAD_FOLDER = "memories"
QR_FOLDER = "static/qr"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)


# ==============================
# MEMORY HELPERS
# ==============================

def get_memory_folder(memory_id):
    return os.path.join(
        UPLOAD_FOLDER,
        memory_id
    )


def get_message_file(memory_id):
    return os.path.join(
        get_memory_folder(memory_id),
        "message.json"
    )


# ==============================
# HOME
# ==============================

@app.route("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


# ==============================
# CREATE MEMORY
# ==============================

@app.route(
    "/create-memory",
    methods=["POST"]
)
def create_memory():

    memory_id = str(
        uuid.uuid4()
    )[:8]

    memory_folder = get_memory_folder(
        memory_id
    )

    os.makedirs(
        memory_folder,
        exist_ok=True
    )

    base_url = request.host_url.rstrip("/")

    qr_url = (
        f"{base_url}/memory/{memory_id}"
    )

    qr = qrcode.make(qr_url)

    qr_path = os.path.join(
        QR_FOLDER,
        f"{memory_id}.png"
    )

    qr.save(qr_path)

    return jsonify({
        "success": True,
        "memory_id": memory_id,
        "qr": f"/static/qr/{memory_id}.png",
        "memory_url": qr_url
    })


# ==============================
# UPLOAD
# ==============================

@app.route(
    "/upload",
    methods=["POST"]
)
def upload():

    memory_id = request.form.get(
        "memory_id"
    )

    if not memory_id:

        return jsonify({
            "success": False,
            "error": "Memory ID missing"
        }), 400


    memory_folder = get_memory_folder(
        memory_id
    )


    if not os.path.exists(
        memory_folder
    ):

        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404


    files = request.files.getlist(
        "file"
    )


    if not files:

        files = request.files.getlist(
            "files"
        )


    if not files:

        return jsonify({
            "success": False,
            "error": "No file received"
        }), 400


    saved = []


    for file in files:

        if not file or not file.filename:
            continue


        filename = secure_filename(
            file.filename
        )


        if not filename:
            continue


        original_name = filename


        name, ext = os.path.splitext(
            original_name
        )


        counter = 1


        while os.path.exists(
            os.path.join(
                memory_folder,
                filename
            )
        ):

            filename = (
                f"{name}_{counter}{ext}"
            )

            counter += 1


        file.save(
            os.path.join(
                memory_folder,
                filename
            )
        )


        saved.append(filename)


    if not saved:

        return jsonify({
            "success": False,
            "error": "File could not be saved"
        }), 400


    return jsonify({
        "success": True,
        "files": saved
    })


# ==============================
# SAVE MESSAGE
# ==============================

@app.route(
    "/save-message",
    methods=["POST"]
)
def save_message():

    data = request.get_json(
        silent=True
    ) or {}


    memory_id = data.get(
        "memory_id"
    )


    message = data.get(
        "message",
        ""
    )


    if not memory_id:

        return jsonify({
            "success": False,
            "error": "Memory ID missing"
        }), 400


    memory_folder = get_memory_folder(
        memory_id
    )


    if not os.path.exists(
        memory_folder
    ):

        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404


    message = str(message)[:10000]


    with open(
        get_message_file(memory_id),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "message": message
            },
            f,
            ensure_ascii=False,
            indent=2
        )


    return jsonify({
        "success": True,
        "characters": len(message)
    })


# ==============================
# MEMORY FILE
# ==============================

@app.route(
    "/memories/<memory_id>/<path:filename>"
)
def memory_file(
    memory_id,
    filename
):

    folder = get_memory_folder(
        memory_id
    )


    if not os.path.exists(folder):

        return "Memory not found", 404


    return send_from_directory(
        folder,
        filename
    )


# ==============================
# MEMORY PAGE
# ==============================

@app.route(
    "/memory/<memory_id>"
)
def memory_page(
    memory_id
):

    folder = get_memory_folder(
        memory_id
    )


    if not os.path.exists(folder):

        return "Memory not found", 404


    files = os.listdir(folder)


    photos = []
    videos = []


    for filename in files:

        lower = filename.lower()


        if lower.endswith(
            (
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif"
            )
        ):

            photos.append(filename)


        elif lower.endswith(
            (
                ".mp4",
                ".webm",
                ".mov",
                ".mkv",
                ".avi",
                ".m4v"
            )
        ):

            videos.append(filename)


    message = ""


    message_file = get_message_file(
        memory_id
    )


    if os.path.exists(
        message_file
    ):

        try:

            with open(
                message_file,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

                message = data.get(
                    "message",
                    ""
                )

        except Exception:

            message = ""


    photo_html = ""


    for filename in photos:

        safe_filename = escape(
            filename
        )


        photo_html += f"""
        <div class="photo">
            <img
                src="/memories/{memory_id}/{safe_filename}"
                alt="Memory Photo">
        </div>
        """


    video_html = ""


    for filename in videos:

        safe_filename = escape(
            filename
        )


        video_html += f"""
        <video
            controls
            playsinline
            preload="metadata">

            <source
                src="/memories/{memory_id}/{safe_filename}">

        </video>
        """


    if not photo_html:

        photo_html = """
        <p class="empty">
            No photos added yet.
        </p>
        """


    if not video_html:

        video_html = """
        <p class="empty">
            No video added yet.
        </p>
        """


    if not message:

        message = (
            "Your special message "
            "will appear here."
        )


    safe_message = escape(
        message
    )


    return f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1.0">

<title>
Your Memory • Memory QR
</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{

    margin: 0;

    padding: 25px;

    font-family:
        Arial,
        sans-serif;

    color: white;

    background:
        linear-gradient(
            135deg,
            #090b18,
            #1b1030,
            #071d27
        );
}}

.container {{

    max-width: 1000px;

    margin: auto;
}}

.header {{

    text-align: center;

    padding: 35px 15px;
}}

.logo {{

    color: #ff62c5;

    font-size: 22px;

    font-weight: bold;
}}

h1 {{

    font-size: 45px;

    margin: 15px 0;

    background:
        linear-gradient(
            90deg,
            #ff72c8,
            #8b7aff
        );

    -webkit-background-clip: text;

    color: transparent;
}}

.memory-id {{

    color: #aaa;

    font-size: 15px;

    word-break: break-all;
}}

.section {{

    margin: 25px 0;

    padding: 25px;

    border-radius: 28px;

    background: #ffffff0d;

    border: 1px solid #ffffff1c;
}}

h2 {{

    color: #ff82d2;

    margin-top: 0;
}}

.photos {{

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(180px, 1fr)
        );

    gap: 15px;
}}

.photo {{

    overflow: hidden;

    border-radius: 20px;

    background: #151526;
}}

.photo img {{

    display: block;

    width: 100%;

    height: 220px;

    object-fit: cover;
}}

video {{

    width: 100%;

    max-width: 700px;

    display: block;

    margin: 15px auto;

    border-radius: 20px;
}}

.message {{

    width: 100%;

    padding: 25px;

    border-radius: 20px;

    background:
        linear-gradient(
            135deg,
            #522044,
            #34305d
        );

    font-size: 18px;

    line-height: 1.8;

    white-space: pre-wrap;

    overflow-wrap: anywhere;

    word-break: break-word;

    overflow: hidden;

    text-align: left;
}}

.empty {{

    color: #999;

    text-align: center;
}}

.footer {{

    text-align: center;

    color: #777;

    padding: 30px;
}}

@media(max-width:600px) {{

    body {{
        padding: 15px;
    }}

    h1 {{
        font-size: 35px;
    }}

    .section {{
        padding: 20px;
    }}

    .message {{

        font-size: 16px;

        padding: 20px;

        line-height: 1.8;

    }}

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

<div class="memory-id">
Memory ID: {memory_id}
</div>

</div>


<section class="section">

<h2>
📸 Beautiful Moments
</h2>

<div class="photos">

{photo_html}

</div>

</section>


<section class="section">

<h2>
🎥 Memory Videos
</h2>

{video_html}

</section>


<section class="section">

<h2>
💌 Personal Diary
</h2>

<div class="message">

{safe_message}

</div>

</section>


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

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )


        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):

            session["admin_logged_in"] = True

            return redirect(
                url_for("admin_dashboard")
            )


        return render_template_string(
            ADMIN_LOGIN_HTML,
            error="Invalid username or password."
        )


    return render_template_string(
        ADMIN_LOGIN_HTML,
        error=""
    )


# ==================================================
# ADMIN LOGIN PAGE
# ==================================================

ADMIN_LOGIN_HTML = """
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0">

<title>Admin Login • Memory QR</title>

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

    padding:20px;

    font-family:Arial,sans-serif;

    color:white;

    background:
        radial-gradient(
            circle at top,
            #35145f,
            transparent 45%
        ),
        linear-gradient(
            135deg,
            #070914,
            #120b25,
            #061b25
        );
}

.login-box{

    width:100%;

    max-width:420px;

    padding:35px;

    border-radius:28px;

    background:#ffffff0d;

    border:1px solid #ffffff1c;

    backdrop-filter:blur(20px);

    box-shadow:
        0 20px 70px #0008;
}

.logo{

    text-align:center;

    color:#ff69c7;

    font-size:20px;

    font-weight:bold;

    letter-spacing:2px;
}

h1{

    text-align:center;

    margin:18px 0 8px;

    font-size:32px;

    background:
        linear-gradient(
            90deg,
            #ff73ca,
            #8c7bff
        );

    -webkit-background-clip:text;

    color:transparent;
}

.subtitle{

    text-align:center;

    color:#999;

    margin-bottom:28px;
}

input{

    width:100%;

    padding:16px;

    margin-top:12px;

    border-radius:15px;

    border:1px solid #ffffff20;

    background:#090b18;

    color:white;

    outline:none;

    font-size:15px;
}

button{

    width:100%;

    padding:16px;

    margin-top:20px;

    border:0;

    border-radius:15px;

    color:white;

    font-size:16px;

    font-weight:bold;

    cursor:pointer;

    background:
        linear-gradient(
            90deg,
            #ff4fb8,
            #755cff
        );
}

.error{

    margin-top:15px;

    padding:12px;

    border-radius:12px;

    text-align:center;

    color:#ff9f9f;

    background:#ff000015;
}

.footer{

    text-align:center;

    color:#666;

    margin-top:25px;

    font-size:13px;
}

</style>

</head>

<body>

<div class="login-box">

<div class="logo">
♥ MEMORY QR
</div>

<h1>
Admin Login
</h1>

<div class="subtitle">
Private dashboard
</div>

<form method="POST">

<input
    type="text"
    name="username"
    placeholder="Username"
    autocomplete="username"
    required>

<input
    type="password"
    name="password"
    placeholder="Password"
    autocomplete="current-password"
    required>

<button type="submit">
🔐 Login to Dashboard
</button>

</form>

{% if error %}

<div class="error">
{{ error }}
</div>

{% endif %}

<div class="footer">
Memory QR Admin
</div>

</div>

</body>

</html>
"""


# ==================================================
# ADMIN PROTECTION
# ==================================================

def admin_required():

    return session.get(
        "admin_logged_in",
        False
    )


# ==================================================
# ADMIN DASHBOARD
# ==================================================

@app.route("/admin")
def admin_dashboard():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )


    memories = []


    if os.path.exists(
        UPLOAD_FOLDER
    ):

        for memory_id in os.listdir(
            UPLOAD_FOLDER
        ):

            folder = get_memory_folder(
                memory_id
            )


            if not os.path.isdir(
                folder
            ):

                continue


            files = os.listdir(
                folder
            )


            photos = 0
            videos = 0


            for filename in files:

                lower = filename.lower()


                if lower.endswith(
                    (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".gif"
                    )
                ):

                    photos += 1


                elif lower.endswith(
                    (
                        ".mp4",
                        ".webm",
                        ".mov",
                        ".mkv",
                        ".avi",
                        ".m4v"
                    )
                ):

                    videos += 1


            has_message = os.path.exists(
                get_message_file(
                    memory_id
                )
            )


            memories.append({
                "id": memory_id,
                "photos": photos,
                "videos": videos,
                "message": has_message
            })


    memories.sort(
        key=lambda x: x["id"],
        reverse=True
    )


    total_memories = len(
        memories
    )

    total_photos = sum(
        x["photos"]
        for x in memories
    )

    total_videos = sum(
        x["videos"]
        for x in memories
    )


    return render_template_string(
        ADMIN_DASHBOARD_HTML,
        memories=memories,
        total_memories=total_memories,
        total_photos=total_photos,
        total_videos=total_videos
    )


# ==================================================
# DELETE MEMORY
# ==================================================

@app.route(
    "/admin/delete/<memory_id>",
    methods=["POST"]
)
def admin_delete_memory(
    memory_id
):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )


    folder = get_memory_folder(
        memory_id
    )


    if os.path.exists(folder):

        shutil.rmtree(
            folder
        )


    qr_file = os.path.join(
        QR_FOLDER,
        f"{memory_id}.png"
    )


    if os.path.exists(
        qr_file
    ):

        os.remove(
            qr_file
        )


    return redirect(
        url_for("admin_dashboard")
    )


# ==================================================
# ADMIN LOGOUT
# ==================================================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# ==================================================
# ADMIN DASHBOARD HTML
# ==================================================

ADMIN_DASHBOARD_HTML = """
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0">

<title>Admin Dashboard • Memory QR</title>

<style>

*{
    box-sizing:border-box;
}

body{

    margin:0;

    min-height:100vh;

    font-family:Arial,sans-serif;

    color:white;

    background:
        radial-gradient(
            circle at top,
            #35145f,
            transparent 40%
        ),
        linear-gradient(
            135deg,
            #070914,
            #120b25,
            #061b25
        );
}

.container{

    width:100%;

    max-width:1100px;

    margin:auto;

    padding:25px 18px 45px;
}

.topbar{

    display:flex;

    justify-content:space-between;

    align-items:center;

    gap:15px;

    margin-bottom:30px;
}

.logo{

    color:#ff69c7;

    font-size:20px;

    font-weight:bold;

    letter-spacing:1px;
}

.logout{

    padding:11px 17px;

    border-radius:12px;

    text-decoration:none;

    color:white;

    background:#ffffff12;

    border:1px solid #ffffff20;
}

h1{

    font-size:38px;

    margin:10px 0;

    background:
        linear-gradient(
            90deg,
            #ff73ca,
            #8c7bff
        );

    -webkit-background-clip:text;

    color:transparent;
}

.subtitle{

    color:#999;

    margin-bottom:25px;
}

.stats{

    display:grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(180px,1fr)
        );

    gap:15px;

    margin-bottom:25px;
}

.stat{

    padding:22px;

    border-radius:22px;

    background:#ffffff0d;

    border:1px solid #ffffff1c;
}

.stat-number{

    font-size:32px;

    font-weight:bold;

    color:#ff75ca;
}

.stat-label{

    margin-top:5px;

    color:#999;
}

.memory{

    padding:22px;

    margin-top:15px;

    border-radius:22px;

    background:#ffffff0d;

    border:1px solid #ffffff1c;
}

.memory-top{

    display:flex;

    justify-content:space-between;

    align-items:center;

    gap:15px;

    flex-wrap:wrap;
}

.memory-id{

    font-size:20px;

    font-weight:bold;

    color:#fff;
}

.badges{

    display:flex;

    gap:8px;

    flex-wrap:wrap;

    margin-top:15px;
}

.badge{

    padding:8px 12px;

    border-radius:10px;

    background:#ffffff10;

    color:#bbb;

    font-size:13px;
}

.actions{

    display:flex;

    gap:10px;

    flex-wrap:wrap;

    margin-top:18px;
}

.action{

    padding:11px 15px;

    border-radius:12px;

    text-decoration:none;

    color:white;

    background:
        linear-gradient(
            90deg,
            #6840a0,
            #453b87
        );

    border:0;

    cursor:pointer;

    font-size:14px;
}

.delete{

    background:
        linear-gradient(
            90deg,
            #a82f59,
            #74325e
        );
}

.empty{

    text-align:center;

    padding:50px 20px;

    color:#888;

    border-radius:22px;

    background:#ffffff08;

    border:1px solid #ffffff12;
}

@media(max-width:600px){

    .topbar{

        align-items:flex-start;
    }

    h1{

        font-size:31px;
    }

    .memory-top{

        display:block;
    }

}

</style>

</head>

<body>

<div class="container">

<div class="topbar">

<div class="logo">
♥ MEMORY QR • ADMIN
</div>

<a
    class="logout"
    href="/admin/logout">
🚪 Logout
</a>

</div>


<h1>
Admin Dashboard
</h1>

<div class="subtitle">
Manage your Memory QR customers and memories.
</div>


<div class="stats">

<div class="stat">

<div class="stat-number">
{{ total_memories }}
</div>

<div class="stat-label">
Total Memories
</div>

</div>


<div class="stat">

<div class="stat-number">
{{ total_photos }}
</div>

<div class="stat-label">
Total Photos
</div>

</div>


<div class="stat">

<div class="stat-number">
{{ total_videos }}
</div>

<div class="stat-label">
Total Videos
</div>

</div>

</div>


{% if memories %}

{% for memory in memories %}

<div class="memory">

<div class="memory-top">

<div class="memory-id">
Memory #{{ memory.id }}
</div>

</div>


<div class="badges">

<div class="badge">
📸 {{ memory.photos }} Photos
</div>

<div class="badge">
🎥 {{ memory.videos }} Videos
</div>

<div class="badge">
💌
{% if memory.message %}
Diary Added
{% else %}
No Diary
{% endif %}
</div>

</div>


<div class="actions">

<a
    class="action"
    href="/memory/{{ memory.id }}"
    target="_blank">
❤️ Open Memory
</a>


<form
    method="POST"
    action="/admin/delete/{{ memory.id }}"
    onsubmit="return confirm('Delete this memory permanently?');">

<button
    type="submit"
    class="action delete">
🗑️ Delete
</button>

</form>

</div>

</div>

{% endfor %}

{% else %}

<div class="empty">

<h2>
No Memories Yet
</h2>

<p>
Create your first Memory QR from the homepage.
</p>

</div>

{% endif %}

</div>

</body>

</html>
"""


# ==================================================
# START SERVER
# ==================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=8000,
        debug=False
    )
