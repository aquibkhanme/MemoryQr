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
import json
import uuid
import shutil
import qrcode

from werkzeug.utils import secure_filename
from markupsafe import escape

try:
    from analytics import init_db, track_request, get_stats
except Exception:
    def init_db():
        pass

    def track_request(req):
        pass

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


app = Flask(__name__)

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

UPLOAD_FOLDER = "memories"
QR_FOLDER = "static/qr"

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

os.makedirs(
    QR_FOLDER,
    exist_ok=True
)

init_db()


@app.before_request
def analytics_middleware():
    try:
        track_request(request)
    except Exception:
        pass


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


def admin_required():
    return session.get(
        "admin_logged_in"
    ) is True


def allowed_file(filename):

    allowed = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".mp4",
        ".webm",
        ".mov",
        ".m4v",
        ".mkv"
    }

    return os.path.splitext(
        filename.lower()
    )[1] in allowed


# -------------------------------------------------
# HOME
# -------------------------------------------------

@app.route("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


# -------------------------------------------------
# CREATE MEMORY
# -------------------------------------------------

@app.route(
    "/create-memory",
    methods=["POST"]
)
def create_memory():

    memory_id = uuid.uuid4().hex[:12]

    folder = get_memory_folder(
        memory_id
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    memory_url = (
        request.host_url.rstrip("/")
        + "/memory/"
        + memory_id
    )

    qr_path = os.path.join(
        QR_FOLDER,
        memory_id + ".png"
    )

    qrcode.make(
        memory_url
    ).save(
        qr_path
    )

    return jsonify({
        "success": True,
        "memory_id": memory_id,
        "memory_url": memory_url,
        "qr": url_for(
            "static",
            filename="qr/" + memory_id + ".png"
        ),
        "qr_url": url_for(
            "static",
            filename="qr/" + memory_id + ".png"
        )
    })


# -------------------------------------------------
# UPLOAD MULTIPLE FILES
# -------------------------------------------------

@app.route(
    "/upload",
    methods=["POST"]
)
def upload_files():

    memory_id = request.form.get(
        "memory_id",
        ""
    ).strip()

    if not memory_id:

        return jsonify({
            "success": False,
            "error": "Memory ID is required"
        }), 400

    folder = get_memory_folder(
        memory_id
    )

    if not os.path.isdir(folder):

        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404

    # Support both:
    # files
    # and file

    files = request.files.getlist(
        "files"
    )

    if not files:

        files = request.files.getlist(
            "file"
        )

    uploaded = []
    rejected = []

    for file in files:

        if not file:
            continue

        if not file.filename:
            continue

        original_name = file.filename

        if not allowed_file(
            original_name
        ):

            rejected.append(
                original_name
            )

            continue

        filename = secure_filename(
            original_name
        )

        if not filename:
            continue

        base, ext = os.path.splitext(
            filename
        )

        final_name = filename
        counter = 1

        while os.path.exists(
            os.path.join(
                folder,
                final_name
            )
        ):

            final_name = (
                base
                + "_"
                + str(counter)
                + ext
            )

            counter += 1

        save_path = os.path.join(
            folder,
            final_name
        )

        file.save(
            save_path
        )

        uploaded.append(
            final_name
        )

    return jsonify({
        "success": True,
        "uploaded": uploaded,
        "files": uploaded,
        "rejected": rejected,
        "count": len(uploaded)
    })


# -------------------------------------------------
# SAVE MESSAGE
# -------------------------------------------------

@app.route(
    "/save-message",
    methods=["POST"]
)
def save_message():

    data = request.get_json(
        silent=True
    ) or {}

    memory_id = str(
        data.get(
            "memory_id",
            ""
        )
    ).strip()

    message = str(
        data.get(
            "message",
            ""
        )
    )

    if not memory_id:

        return jsonify({
            "success": False,
            "error": "Memory ID is required"
        }), 400

    folder = get_memory_folder(
        memory_id
    )

    if not os.path.isdir(folder):

        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404

    if len(message) > 70000:

        return jsonify({
            "success": False,
            "error": "Message is too long"
        }), 400

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
        "success": True
    })


# -------------------------------------------------
# DOWNLOAD QR
# -------------------------------------------------

@app.route(
    "/download-qr/<memory_id>"
)
def download_qr(memory_id):

    qr_file = os.path.join(
        QR_FOLDER,
        memory_id + ".png"
    )

    if not os.path.isfile(qr_file):

        return "QR not found", 404

    return send_from_directory(
        QR_FOLDER,
        memory_id + ".png",
        as_attachment=True,
        download_name="MemoryQR-" + memory_id + ".png"
    )


# -------------------------------------------------
# MEMORY FILE
# -------------------------------------------------

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

    if not os.path.isdir(folder):

        return "Memory not found", 404

    return send_from_directory(
        folder,
        filename
    )


# -------------------------------------------------
# PUBLIC MEMORY PAGE
# -------------------------------------------------

@app.route(
    "/memory/<memory_id>"
)
def memory_page(memory_id):

    folder = get_memory_folder(
        memory_id
    )

    if not os.path.isdir(folder):

        return """
        <!DOCTYPE html>
        <html>
        <head>
        <meta name="viewport"
        content="width=device-width,initial-scale=1">
        <title>Memory Not Found</title>
        </head>

        <body style="
        margin:0;
        background:#080912;
        color:white;
        font-family:Arial;
        text-align:center;
        padding-top:100px;
        ">

        <h2>Memory not found</h2>

        <p style="color:#999">
        This Memory QR may no longer exist.
        </p>

        </body>
        </html>
        """, 404

    photos = []
    videos = []

    for filename in sorted(
        os.listdir(folder)
    ):

        if filename == "message.json":
            continue

        ext = os.path.splitext(
            filename
        )[1].lower()

        if ext in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif"
        }:

            photos.append(
                filename
            )

        elif ext in {
            ".mp4",
            ".webm",
            ".mov",
            ".m4v",
            ".mkv"
        }:

            videos.append(
                filename
            )

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

        file_url = (
            "/memories/"
            + memory_id
            + "/"
            + filename
        )

        photo_html += f"""
        <div class="photo">
            <img
                src="{escape(file_url)}"
                loading="lazy"
                onclick="openPhoto(this.src)"
                alt="Memory Photo">
        </div>
        """

    if not photo_html:

        photo_html = """
        <div class="empty">
            📸 No photos added yet.
        </div>
        """

    video_html = ""

    for filename in videos:

        file_url = (
            "/memories/"
            + memory_id
            + "/"
            + filename
        )

        video_html += f"""
        <video
            controls
            playsinline
            preload="metadata">

            <source
                src="{escape(file_url)}">

        </video>
        """

    if not video_html:

        video_html = """
        <div class="empty">
            🎥 No videos added yet.
        </div>
        """

    safe_message = escape(
        message
    )

    return render_template_string(
        """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1">

<meta
name="robots"
content="noindex,nofollow,noarchive">

<title>Memory QR</title>

<style>

*{
    box-sizing:border-box;
}

body{
    margin:0;
    background:
        radial-gradient(
            circle at top,
            #35145f 0%,
            transparent 40%
        ),
        linear-gradient(
            135deg,
            #070914,
            #120b25,
            #061b25
        );
    color:white;
    font-family:Arial,sans-serif;
}

main{
    width:100%;
    max-width:1050px;
    margin:auto;
    padding:20px;
}

header{
    text-align:center;
    padding:40px 10px;
}

.logo{
    color:#ff65c7;
    font-size:22px;
    font-weight:bold;
    letter-spacing:2px;
}

h1{
    font-size:46px;
    margin:15px 0;
    background:
        linear-gradient(
            90deg,
            #ff72c8,
            #8b7aff,
            #55dfff
        );
    -webkit-background-clip:text;
    background-clip:text;
    color:transparent;
}

.id{
    color:#888;
    font-size:13px;
}

section{
    margin:20px 0;
    padding:25px;
    border-radius:25px;
    background:#ffffff0b;
    border:1px solid #ffffff18;
    backdrop-filter:blur(12px);
}

h2{
    color:#ff82d2;
    margin-top:0;
}

.gallery{
    display:grid;
    grid-template-columns:
        repeat(
            auto-fill,
            minmax(160px,1fr)
        );
    gap:14px;
}

.photo{
    aspect-ratio:1;
    border-radius:18px;
    overflow:hidden;
    cursor:pointer;
    background:#111;
}

.photo img{
    width:100%;
    height:100%;
    object-fit:cover;
    display:block;
}

video{
    width:100%;
    max-width:800px;
    display:block;
    margin:15px auto;
    border-radius:18px;
    background:#000;
}

.message{
    padding:25px;
    border-radius:20px;
    background:
        linear-gradient(
            135deg,
            #522044,
            #34305d
        );
    white-space:pre-wrap;
    line-height:1.8;
    overflow-wrap:anywhere;
}

.empty{
    padding:35px;
    text-align:center;
    color:#888;
}

.footer{
    text-align:center;
    color:#777;
    padding:30px 10px;
    font-size:13px;
}

#viewer{
    display:none;
    position:fixed;
    inset:0;
    background:#000e;
    align-items:center;
    justify-content:center;
    padding:20px;
    z-index:9999;
}

#viewer img{
    max-width:100%;
    max-height:90vh;
    border-radius:15px;
}

.close{
    position:absolute;
    right:20px;
    top:8px;
    font-size:42px;
    color:white;
    cursor:pointer;
}

@media(max-width:600px){

    main{
        padding:12px;
    }

    h1{
        font-size:36px;
    }

    section{
        padding:18px;
    }

    .gallery{
        grid-template-columns:
            repeat(2,1fr);
    }

}

</style>

</head>

<body>

<main>

<header>

<div class="logo">
♥ MEMORY QR
</div>

<h1>
Your Memories, Forever.
</h1>

<div class="id">
Memory ID: {{ memory_id }}
</div>

</header>

<section>

<h2>
📸 Beautiful Moments
</h2>

<div class="gallery">

{{ photo_html | safe }}

</div>

</section>

<section>

<h2>
🎥 Memory Videos
</h2>

{{ video_html | safe }}

</section>

<section>

<h2>
💌 Special Message
</h2>

<div class="message">
{{ message }}
</div>

</section>

<div class="footer">
This site is made by Aquib Khan ❤️
</div>

</main>

<div
id="viewer"
onclick="closePhoto()">

<span
class="close">
×
</span>

<img
id="large"
alt="Large photo">

</div>

<script>

function openPhoto(src){

    document.getElementById(
        "large"
    ).src = src;

    document.getElementById(
        "viewer"
    ).style.display = "flex";

}

function closePhoto(){

    document.getElementById(
        "viewer"
    ).style.display = "none";

}

</script>

</body>

</html>
        """,
        memory_id=escape(memory_id),
        photo_html=photo_html,
        video_html=video_html,
        message=safe_message
    )


# -------------------------------------------------
# ADMIN LOGIN
# -------------------------------------------------

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
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):

            session[
                "admin_logged_in"
            ] = True

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        error = (
            "Invalid username or password"
        )

    return render_template_string(
        """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1">

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

.login{
    width:92%;
    max-width:430px;
    padding:35px;
    border-radius:28px;
    background:#ffffff0d;
    border:1px solid #ffffff18;
    backdrop-filter:blur(18px);
}

.logo{
    text-align:center;
    color:#ff69c8;
    font-size:22px;
    font-weight:bold;
    letter-spacing:2px;
}

h1{
    text-align:center;
    margin:15px 0 25px;
}

input{
    width:100%;
    padding:15px;
    margin:7px 0;
    border-radius:14px;
    border:1px solid #ffffff20;
    background:#080912;
    color:white;
    outline:none;
}

button{
    width:100%;
    padding:16px;
    margin-top:15px;
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
}

.error{
    text-align:center;
    color:#ff8585;
    margin-bottom:12px;
}

</style>

</head>

<body>

<div class="login">

<div class="logo">
♥ MEMORY QR
</div>

<h1>
Admin Login
</h1>

{% if error %}

<div class="error">
{{ error }}
</div>

{% endif %}

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
LOGIN
</button>

</form>

</div>

</body>

</html>
        """,
        error=error
    )


# -------------------------------------------------
# ADMIN DASHBOARD
# -------------------------------------------------

@app.route("/admin")
def admin_dashboard():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    memories = []

    if os.path.isdir(
        UPLOAD_FOLDER
    ):

        for memory_id in sorted(
            os.listdir(UPLOAD_FOLDER),
            reverse=True
        ):

            folder = get_memory_folder(
                memory_id
            )

            if not os.path.isdir(folder):
                continue

            photos = 0
            videos = 0

            for filename in os.listdir(
                folder
            ):

                ext = os.path.splitext(
                    filename
                )[1].lower()

                if ext in {
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".gif"
                }:

                    photos += 1

                elif ext in {
                    ".mp4",
                    ".webm",
                    ".mov",
                    ".m4v",
                    ".mkv"
                }:

                    videos += 1

            memories.append({
                "id": memory_id,
                "photos": photos,
                "videos": videos
            })

    total_memories = len(
        memories
    )

    total_photos = sum(
        item["photos"]
        for item in memories
    )

    total_videos = sum(
        item["videos"]
        for item in memories
    )

    try:

        stats = get_stats()

    except Exception:

        stats = {
            "total_visits": 0,
            "today_visits": 0,
            "seven_day_visits": 0,
            "memory_views": 0,
            "most_viewed": None,
            "devices": [],
            "browsers": []
        }

    most_viewed = stats.get(
        "most_viewed"
    )

    if most_viewed:

        most_viewed_id = most_viewed[0]
        most_viewed_count = most_viewed[1]

    else:

        most_viewed_id = "—"
        most_viewed_count = 0

    return render_template_string(
        """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1">

<title>Memory QR Dashboard</title>

<style>

*{
    box-sizing:border-box;
}

body{
    margin:0;
    color:white;
    font-family:Arial,sans-serif;
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

main{
    max-width:1150px;
    margin:auto;
    padding:20px;
}

header{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:15px;
    padding:20px 0 30px;
}

.logo{
    color:#ff69c8;
    font-size:22px;
    font-weight:bold;
    letter-spacing:2px;
}

.logout{
    text-decoration:none;
    color:white;
    padding:11px 16px;
    border-radius:12px;
    background:#ffffff12;
    border:1px solid #ffffff20;
}

h1{
    font-size:38px;
    margin:10px 0;
}

.subtitle{
    color:#999;
}

.stats{
    display:grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(160px,1fr)
        );
    gap:14px;
    margin:20px 0;
}

.stat{
    padding:22px;
    border-radius:20px;
    background:#ffffff0d;
    border:1px solid #ffffff18;
}

.stat-number{
    font-size:30px;
    font-weight:bold;
    color:#ff72ca;
}

.stat-label{
    color:#999;
    margin-top:5px;
}

.card{
    margin:20px 0;
    padding:22px;
    border-radius:24px;
    background:#ffffff0d;
    border:1px solid #ffffff18;
}

.memory{
    padding:20px 0;
    border-bottom:1px solid #ffffff15;
}

.memory:last-child{
    border-bottom:0;
}

.memory-id{
    font-size:19px;
    font-weight:bold;
    color:#ff82d2;
    word-break:break-all;
}

.info{
    color:#999;
    margin:8px 0 15px;
}

.actions{
    display:grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(150px,1fr)
        );
    gap:10px;
}

.btn{
    display:block;
    width:100%;
    padding:13px;
    border:0;
    border-radius:13px;
    color:white;
    text-decoration:none;
    text-align:center;
    font-weight:bold;
    cursor:pointer;
}

.open{
    background:
        linear-gradient(
            90deg,
            #ff4fb8,
            #755cff
        );
}

.qr{
    background:
        linear-gradient(
            90deg,
            #514b91,
            #39456e
        );
}

.download{
    background:
        linear-gradient(
            90deg,
            #e83c9f,
            #805cff
        );
}

.delete{
    background:#5b2028;
}

.empty{
    color:#888;
    text-align:center;
    padding:30px;
}

.analytics{
    display:grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(200px,1fr)
        );
    gap:12px;
}

.analytics-box{
    padding:18px;
    border-radius:17px;
    background:#080912;
    border:1px solid #ffffff12;
}

.analytics-box strong{
    display:block;
    color:#ff82d2;
    margin-bottom:6px;
}

@media(max-width:600px){

    main{
        padding:14px;
    }

    header{
        align-items:flex-start;
    }

    h1{
        font-size:30px;
    }

}

</style>

</head>

<body>

<main>

<header>

<div>

<div class="logo">
♥ MEMORY QR
</div>

<h1>
Admin Dashboard
</h1>

<div class="subtitle">
Manage your memories, QR codes and links.
</div>

</div>

<a
class="logout"
href="/admin/logout">
Logout
</a>

</header>


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

<div class="stat">

<div class="stat-number">
{{ stats.get("memory_views",0) }}
</div>

<div class="stat-label">
Memory Views
</div>

</div>

</div>


<div class="card">

<h2>
📊 Analytics
</h2>

<div class="analytics">

<div class="analytics-box">

<strong>
Total Visits
</strong>

{{ stats.get("total_visits",0) }}

</div>

<div class="analytics-box">

<strong>
Today
</strong>

{{ stats.get("today_visits",0) }}

</div>

<div class="analytics-box">

<strong>
Last 7 Days
</strong>

{{ stats.get("seven_day_visits",0) }}

</div>

<div class="analytics-box">

<strong>
Most Viewed Memory
</strong>

{{ most_viewed_id }}

<br>

{{ most_viewed_count }} views

</div>

</div>

</div>


<div class="card">

<h2>
💾 Your Memories
</h2>

{% if memories %}

{% for memory in memories %}

<div class="memory">

<div class="memory-id">
Memory {{ memory.id }}
</div>

<div class="info">

📸 {{ memory.photos }} photos
&nbsp;&nbsp;
🎥 {{ memory.videos }} videos

</div>

<div class="actions">

<a
class="btn open"
href="/memory/{{ memory.id }}"
target="_blank">
❤️ Open Memory
</a>

<a
class="btn qr"
href="/static/qr/{{ memory.id }}.png"
target="_blank">
🔳 View QR
</a>

<a
class="btn download"
href="/download-qr/{{ memory.id }}">
⬇️ Download QR
</a>

<form
method="POST"
action="/admin/delete/{{ memory.id }}"
onsubmit="return confirm('Delete this memory permanently?');">

<button
class="btn delete"
type="submit">
🗑️ Delete
</button>

</form>

</div>

</div>

{% endfor %}

{% else %}

<div class="empty">
No memories created yet.
</div>

{% endif %}

</div>


<div style="
text-align:center;
color:#777;
padding:30px 0;
font-size:13px;
">

This site is made by Aquib Khan ❤️

</div>

</main>

</body>

</html>
        """,
        memories=memories,
        total_memories=total_memories,
        total_photos=total_photos,
        total_videos=total_videos,
        stats=stats,
        most_viewed_id=most_viewed_id,
        most_viewed_count=most_viewed_count
    )


# -------------------------------------------------
# DELETE MEMORY
# -------------------------------------------------

@app.route(
    "/admin/delete/<memory_id>",
    methods=["POST"]
)
def admin_delete(memory_id):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    folder = get_memory_folder(
        memory_id
    )

    if os.path.isdir(folder):

        shutil.rmtree(
            folder
        )

    qr_file = os.path.join(
        QR_FOLDER,
        memory_id + ".png"
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


# -------------------------------------------------
# LOGOUT
# -------------------------------------------------

@app.route(
    "/admin/logout"
)
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect(
        url_for("admin_login")
    )


# -------------------------------------------------
# RUN
# -------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=8000,
        debug=False
    )
