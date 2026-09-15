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

from analytics import init_db, track_request, get_stats


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

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

init_db()


@app.before_request
def analytics_middleware():
    track_request(request)


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
        ".m4v"
    }

    return os.path.splitext(
        filename.lower()
    )[1] in allowed


@app.route("/")
def home():
    return send_from_directory(
        ".",
        "index.html"
    )


@app.route(
    "/create-memory",
    methods=["POST"]
)
def create_memory():

    memory_id = uuid.uuid4().hex[:8]

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

    qr = qrcode.make(
        memory_url
    )

    qr_path = os.path.join(
        QR_FOLDER,
        memory_id + ".png"
    )

    qr.save(qr_path)

    return jsonify({
        "success": True,
        "memory_id": memory_id,
        "memory_url": memory_url,
        "qr_url": url_for(
            "static",
            filename="qr/" + memory_id + ".png"
        )
    })


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

    files = request.files.getlist(
        "files"
    )

    if not files:
        single = request.files.get(
            "file"
        )

        if single:
            files = [single]

    uploaded = []

    for file in files:

        if not file or not file.filename:
            continue

        if not allowed_file(
            file.filename
        ):
            continue

        filename = secure_filename(
            file.filename
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

        file.save(
            os.path.join(
                folder,
                final_name
            )
        )

        uploaded.append(
            final_name
        )

    return jsonify({
        "success": True,
        "uploaded": uploaded
    })


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

    if len(message) > 10000:
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


@app.route(
    "/memories/<memory_id>/<path:filename>"
)
def memory_file(
    memory_id,
    filename
):

    return send_from_directory(
        get_memory_folder(memory_id),
        filename
    )


@app.route(
    "/memory/<memory_id>"
)
def memory_page(memory_id):

    folder = get_memory_folder(
        memory_id
    )

    if not os.path.isdir(folder):
        return """
<h2 style="font-family:Arial;text-align:center;margin-top:80px">
Memory not found
</h2>
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

        file_url = (
            "/memories/"
            + memory_id
            + "/"
            + filename
        )

        if ext in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif"
        }:

            photos.append(file_url)

        elif ext in {
            ".mp4",
            ".webm",
            ".mov",
            ".m4v"
        }:

            videos.append(file_url)

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

    return render_template_string(
        """
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1">

<title>Memory QR</title>

<style>

body {
margin:0;
font-family:Arial,sans-serif;
background:#080912;
color:white;
}

.container {
max-width:900px;
margin:auto;
padding:30px 18px 50px;
}

.hero {
text-align:center;
padding:30px 10px;
}

.logo {
color:#ff69c8;
font-weight:bold;
font-size:20px;
}

h1 {
font-size:38px;
margin:15px 0;
}

.subtitle {
color:#aaa8bb;
}

.message {
margin:25px auto;
padding:25px;
border-radius:22px;
background:#151525;
border:1px solid #ffffff15;
line-height:1.7;
white-space:pre-wrap;
}

.gallery {
display:grid;
grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
gap:14px;
}

.photo {
width:100%;
aspect-ratio:1;
object-fit:cover;
border-radius:18px;
}

.video {
width:100%;
margin-top:18px;
border-radius:18px;
background:#000;
}

.footer {
text-align:center;
margin-top:45px;
color:#aaa8bb;
font-size:13px;
}

</style>

</head>

<body>

<div class="container">

<div class="hero">

<div class="logo">
♥ MEMORY QR
</div>

<h1>
Our Memories
</h1>

<div class="subtitle">
A little place for beautiful memories.
</div>

</div>

{% if message %}
<div class="message">{{ message }}</div>
{% endif %}

{% if photos %}

<div class="gallery">

{% for photo in photos %}

<img
class="photo"
src="{{ photo }}"
alt="Memory photo">

{% endfor %}

</div>

{% endif %}

{% for video in videos %}

<video
class="video"
controls
playsinline>

<source src="{{ video }}">

</video>

{% endfor %}

<div class="footer">
This site is made by Aquib Khan ❤️
</div>

</div>

</body>

</html>
""",
        photos=photos,
        videos=videos,
        message=escape(message)
    )


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

<title>Memory QR Admin</title>

<style>

body {
margin:0;
min-height:100vh;
display:flex;
align-items:center;
justify-content:center;
font-family:Arial,sans-serif;
background:#080912;
color:white;
}

.login {
width:90%;
max-width:420px;
padding:35px;
border-radius:25px;
background:#151525;
border:1px solid #ffffff18;
}

.logo {
text-align:center;
color:#ff69c8;
font-weight:bold;
font-size:22px;
margin-bottom:10px;
}

h1 {
text-align:center;
margin-bottom:25px;
}

input {
width:100%;
padding:15px;
margin:8px 0;
border-radius:12px;
border:1px solid #ffffff20;
background:#ffffff0a;
color:white;
box-sizing:border-box;
}

button {
width:100%;
padding:15px;
margin-top:15px;
border:0;
border-radius:12px;
color:white;
font-size:16px;
font-weight:bold;
background:linear-gradient(90deg,#ff4fc4,#7668ff);
}

.error {
text-align:center;
color:#ff8585;
margin-bottom:10px;
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
required>

<input
type="password"
name="password"
placeholder="Password"
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

            for filename in os.listdir(folder):

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
                    ".m4v"
                }:
                    videos += 1

            memories.append({
                "id": memory_id,
                "photos": photos,
                "videos": videos
            })

    total_memories = len(memories)

    total_photos = sum(
        x["photos"]
        for x in memories
    )

    total_videos = sum(
        x["videos"]
        for x in memories
    )

    stats = get_stats()

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

body {
margin:0;
font-family:Arial,sans-serif;
background:#080912;
color:white;
}

.header {
padding:18px;
display:flex;
justify-content:space-between;
align-items:center;
background:#10111d;
border-bottom:1px solid #ffffff12;
}

.brand {
color:#ff69c8;
font-weight:bold;
}

.logout {
color:white;
text-decoration:none;
padding:9px 14px;
border-radius:9px;
background:#ffffff12;
}

.container {
max-width:1200px;
margin:auto;
padding:25px 16px 50px;
}

.cards {
display:grid;
grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
gap:14px;
}

.card {
padding:22px;
border-radius:20px;
background:#151525;
border:1px solid #ffffff12;
}

.label {
color:#aaa8bb;
font-size:13px;
}

.number {
font-size:30px;
font-weight:bold;
margin-top:8px;
}

.section {
margin-top:30px;
}

.table {
overflow-x:auto;
border-radius:18px;
background:#151525;
}

table {
width:100%;
min-width:650px;
border-collapse:collapse;
}

th,td {
padding:14px;
text-align:left;
border-bottom:1px solid #ffffff10;
}

th {
color:#aaa8bb;
}

.btn {
color:white;
text-decoration:none;
padding:8px 12px;
border-radius:8px;
background:#7668ff;
}

.delete {
padding:8px 12px;
border:0;
border-radius:8px;
color:white;
background:#e84d70;
}

.row {
display:flex;
justify-content:space-between;
padding:9px 0;
border-bottom:1px solid #ffffff10;
}

</style>

</head>

<body>

<div class="header">

<div class="brand">
♥ MEMORY QR ADMIN
</div>

<a
class="logout"
href="/admin/logout">
Logout
</a>

</div>

<div class="container">

<h1>
Dashboard
</h1>

<div class="cards">

<div class="card">
<div class="label">
Total Memories
</div>
<div class="number">
{{ total_memories }}
</div>
</div>

<div class="card">
<div class="label">
Photos
</div>
<div class="number">
{{ total_photos }}
</div>
</div>

<div class="card">
<div class="label">
Videos
</div>
<div class="number">
{{ total_videos }}
</div>
</div>

<div class="card">
<div class="label">
Total Visits
</div>
<div class="number">
{{ stats.total_visits }}
</div>
</div>

</div>


<div class="section">

<h2>
Analytics
</h2>

<div class="cards">

<div class="card">
<div class="label">
Today
</div>
<div class="number">
{{ stats.today_visits }}
</div>
</div>

<div class="card">
<div class="label">
Last 7 Days
</div>
<div class="number">
{{ stats.seven_day_visits }}
</div>
</div>

<div class="card">
<div class="label">
Memory Views
</div>
<div class="number">
{{ stats.memory_views }}
</div>
</div>

<div class="card">
<div class="label">
Most Viewed
</div>
<div class="number">
{{ most_viewed_count }}
</div>
<div class="label">
{{ most_viewed_id }}
</div>
</div>

</div>

</div>


<div class="section">

<h2>
Devices
</h2>

<div class="card">

{% for device, count in stats.devices %}

<div class="row">
<span>{{ device }}</span>
<strong>{{ count }}</strong>
</div>

{% else %}

No device data yet.

{% endfor %}

</div>

</div>


<div class="section">

<h2>
Browsers
</h2>

<div class="card">

{% for browser, count in stats.browsers %}

<div class="row">
<span>{{ browser }}</span>
<strong>{{ count }}</strong>
</div>

{% else %}

No browser data yet.

{% endfor %}

</div>

</div>


<div class="section">

<h2>
Memories
</h2>

<div class="table">

<table>

<tr>
<th>Memory ID</th>
<th>Photos</th>
<th>Videos</th>
<th>Actions</th>
</tr>

{% for memory in memories %}

<tr>

<td>
{{ memory.id }}
</td>

<td>
{{ memory.photos }}
</td>

<td>
{{ memory.videos }}
</td>

<td>

<a
class="btn"
href="/memory/{{ memory.id }}"
target="_blank">
View
</a>

<form
method="POST"
action="/admin/delete/{{ memory.id }}"
style="display:inline"
onsubmit="return confirm('Delete this memory?')">

<button
class="delete"
type="submit">
Delete
</button>

</form>

</td>

</tr>

{% else %}

<tr>
<td colspan="4">
No memories yet.
</td>
</tr>

{% endfor %}

</table>

</div>

</div>

</div>

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
        shutil.rmtree(folder)

    qr_file = os.path.join(
        QR_FOLDER,
        memory_id + ".png"
    )

    if os.path.exists(qr_file):
        os.remove(qr_file)

    return redirect(
        url_for("admin_dashboard")
    )


@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect(
        url_for("admin_login")
    )


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=8000,
        debug=False
    )
