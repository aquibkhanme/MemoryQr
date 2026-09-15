import os
import json
import uuid
import shutil
import qrcode

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

from werkzeug.utils import secure_filename


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "memoryqr-secret-change-me"
)

UPLOAD_FOLDER = "memories"
QR_FOLDER = "static/qr"

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "MemoryQR@123"
)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)


# ==================================================
# HOME
# ==================================================

@app.route("/")
def home():
    return send_from_directory(".", "index.html")


# ==================================================
# CREATE MEMORY
# ==================================================

@app.route("/create-memory", methods=["POST"])
def create_memory():

    memory_id = uuid.uuid4().hex[:8]

    folder = os.path.join(
        UPLOAD_FOLDER,
        memory_id
    )

    os.makedirs(folder, exist_ok=True)

    data = {
        "memory_id": memory_id,
        "photos": [],
        "videos": [],
        "message": ""
    }

    data_file = os.path.join(
        folder,
        "data.json"
    )

    with open(
        data_file,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    memory_url = (
        request.host_url.rstrip("/")
        + "/memory/"
        + memory_id
    )

    qr = qrcode.make(memory_url)

    qr_file = os.path.join(
        QR_FOLDER,
        memory_id + ".png"
    )

    qr.save(qr_file)

    return jsonify({
        "success": True,
        "memory_id": memory_id,
        "url": memory_url,
        "qr": "/static/qr/" + memory_id + ".png"
    })


# ==================================================
# UPLOAD PHOTOS / VIDEOS
# ==================================================

@app.route("/upload", methods=["POST"])
def upload():

    memory_id = request.form.get(
        "memory_id",
        ""
    ).strip()

    if not memory_id:
        return jsonify({
            "success": False,
            "error": "Memory ID missing"
        }), 400

    folder = os.path.join(
        UPLOAD_FOLDER,
        memory_id
    )

    if not os.path.isdir(folder):
        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404

    data_file = os.path.join(
        folder,
        "data.json"
    )

    if os.path.exists(data_file):

        with open(
            data_file,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

    else:

        data = {
            "memory_id": memory_id,
            "photos": [],
            "videos": [],
            "message": ""
        }

    files = request.files.getlist("file")

    uploaded = []

    image_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".bmp"
    }

    video_extensions = {
        ".mp4",
        ".mov",
        ".webm",
        ".mkv",
        ".avi",
        ".m4v"
    }

    for file in files:

        if not file or not file.filename:
            continue

        original_name = secure_filename(
            file.filename
        )

        if not original_name:
            continue

        extension = os.path.splitext(
            original_name
        )[1].lower()

        unique_name = (
            uuid.uuid4().hex[:8]
            + "_"
            + original_name
        )

        save_path = os.path.join(
            folder,
            unique_name
        )

        file.save(save_path)

        if extension in image_extensions:

            data["photos"].append(
                unique_name
            )

        elif extension in video_extensions:

            data["videos"].append(
                unique_name
            )

        else:

            try:
                os.remove(save_path)
            except Exception:
                pass

            continue

        uploaded.append(
            unique_name
        )

    with open(
        data_file,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    return jsonify({
        "success": True,
        "uploaded": uploaded
    })


# ==================================================
# SAVE PERSONAL MESSAGE
# ==================================================

@app.route("/save-message", methods=["POST"])
def save_message():

    memory_id = request.form.get(
        "memory_id",
        ""
    ).strip()

    message = request.form.get(
        "message",
        ""
    )

    if not memory_id:
        return jsonify({
            "success": False,
            "error": "Memory ID missing"
        }), 400

    folder = os.path.join(
        UPLOAD_FOLDER,
        memory_id
    )

    if not os.path.isdir(folder):
        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404

    data_file = os.path.join(
        folder,
        "data.json"
    )

    if os.path.exists(data_file):

        with open(
            data_file,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

    else:

        data = {
            "memory_id": memory_id,
            "photos": [],
            "videos": [],
            "message": ""
        }

    data["message"] = message

    with open(
        data_file,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    return jsonify({
        "success": True
    })


# ==================================================
# SERVE MEMORY FILES
# ==================================================

@app.route(
    "/memories/<memory_id>/<path:filename>"
)
def memory_file(
    memory_id,
    filename
):

    folder = os.path.join(
        UPLOAD_FOLDER,
        memory_id
    )

    return send_from_directory(
        folder,
        filename
    )


# ==================================================
# MEMORY PAGE
# ==================================================

@app.route("/memory/<memory_id>")
def memory_page(memory_id):

    folder = os.path.join(
        UPLOAD_FOLDER,
        memory_id
    )

    data_file = os.path.join(
        folder,
        "data.json"
    )

    if not os.path.exists(data_file):
        return "Memory not found", 404

    with open(
        data_file,
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    photos = data.get(
        "photos",
        []
    )

    videos = data.get(
        "videos",
        []
    )

    message = data.get(
        "message",
        ""
    )

    photo_html = ""

    for filename in photos:

        file_url = (
            "/memories/"
            + memory_id
            + "/"
            + filename
        )

        photo_html += (
            '<div class="photo-card">'
            '<img src="'
            + file_url
            + '" loading="lazy">'
            '</div>'
        )

    video_html = ""

    for filename in videos:

        file_url = (
            "/memories/"
            + memory_id
            + "/"
            + filename
        )

        video_html += (
            '<div class="video-card">'
            '<video controls playsinline>'
            '<source src="'
            + file_url
            + '">'
            '</video>'
            '</div>'
        )

    message_html = ""

    if message.strip():

        safe_message = (
            message
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

        message_html = (
            '<section class="message-box">'
            '<div class="message-icon">💌</div>'
            '<h2>Personal Message</h2>'
            '<div class="message-text">'
            + safe_message
            + '</div>'
            '</section>'
        )

    if not photo_html:

        photo_html = (
            '<div class="empty">'
            'No photos available.'
            '</div>'
        )

    if not video_html:

        video_html = (
            '<div class="empty">'
            'No videos available.'
            '</div>'
        )

    page = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width,initial-scale=1.0">

<title>Your Memories ❤️</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
font-family:Arial,Helvetica,sans-serif;
background:
radial-gradient(circle at top,#302060,#111426 45%,#070912);
color:white;
min-height:100vh;
padding:20px 14px 40px;
}

.container{
max-width:950px;
margin:auto;
}

.hero{
text-align:center;
padding:35px 10px;
}

.hero h1{
font-size:clamp(34px,8vw,55px);
margin:8px 0;
}

.hero p{
color:#bfc1d2;
}

.section-title{
font-size:25px;
margin:28px 0 15px;
}

.photos{
display:grid;
grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
gap:14px;
}

.photo-card{
background:rgba(255,255,255,.07);
border:1px solid rgba(255,255,255,.12);
border-radius:20px;
padding:7px;
overflow:hidden;
}

.photo-card img{
width:100%;
display:block;
border-radius:15px;
}

.videos{
display:grid;
grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
gap:14px;
}

.video-card{
background:rgba(255,255,255,.07);
border:1px solid rgba(255,255,255,.12);
border-radius:20px;
padding:7px;
overflow:hidden;
}

.video-card video{
width:100%;
display:block;
border-radius:15px;
background:#000;
}

.message-box{
margin-top:30px;
padding:28px 22px;
border-radius:24px;
background:rgba(255,255,255,.075);
border:1px solid rgba(255,255,255,.13);
}

.message-icon{
font-size:30px;
}

.message-box h2{
margin:8px 0 18px;
}

.message-text{
white-space:pre-wrap;
overflow-wrap:anywhere;
word-break:break-word;
line-height:1.8;
font-size:17px;
color:#eee;
}

.empty{
padding:25px;
border-radius:18px;
background:rgba(255,255,255,.05);
color:#999;
text-align:center;
}

footer{
text-align:center;
padding:45px 10px 10px;
color:#999;
font-size:14px;
}

</style>

</head>

<body>

<div class="container">

<div class="hero">

<div>💝</div>

<h1>Your Memories ❤️</h1>

<p>
Photos, videos and your special message
</p>

</div>

<h2 class="section-title">
📸 Photos
</h2>

<div class="photos">
""" + photo_html + """
</div>

<h2 class="section-title">
🎥 Videos
</h2>

<div class="videos">
""" + video_html + """
</div>

""" + message_html + """

<footer>
This site is made by Aquib Khan ❤️
</footer>

</div>

</body>

</html>
"""

    return page# ==================================================
# ADMIN LOGIN PAGE
# ==================================================

ADMIN_LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width,initial-scale=1">

<title>Memory QR Admin</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
font-family:Arial,sans-serif;
min-height:100vh;
display:flex;
align-items:center;
justify-content:center;
padding:20px;
background:
radial-gradient(circle at top,#302060,#101321 55%,#070912);
color:white;
}

.login-box{
width:100%;
max-width:410px;
padding:30px;
border-radius:25px;
background:rgba(255,255,255,.08);
border:1px solid rgba(255,255,255,.13);
box-shadow:0 25px 80px rgba(0,0,0,.45);
}

.logo{
text-align:center;
font-size:42px;
}

h1{
text-align:center;
margin:10px 0 5px;
}

.subtitle{
text-align:center;
color:#aaa;
margin-bottom:25px;
}

label{
display:block;
margin:12px 0 7px;
color:#ddd;
}

input{
width:100%;
padding:14px;
border-radius:12px;
border:1px solid rgba(255,255,255,.15);
background:rgba(0,0,0,.25);
color:white;
font-size:16px;
outline:none;
}

.password-box{
position:relative;
}

.password-box input{
padding-right:55px;
}

.eye{
position:absolute;
right:16px;
top:14px;
cursor:pointer;
}

.login-btn{
width:100%;
margin-top:20px;
padding:14px;
border:0;
border-radius:12px;
background:white;
color:#111;
font-size:16px;
font-weight:bold;
cursor:pointer;
}

.error{
padding:12px;
border-radius:12px;
background:rgba(255,60,60,.15);
border:1px solid rgba(255,60,60,.3);
color:#ffb0b0;
text-align:center;
margin-bottom:15px;
}

</style>

</head>

<body>

<div class="login-box">

<div class="logo">
🔐
</div>

<h1>Admin Login</h1>

<div class="subtitle">
Memory QR Dashboard
</div>

__ERROR__

<form method="POST">

<label>Username</label>

<input
type="text"
name="username"
placeholder="Enter admin username"
autocomplete="username"
required>

<label>Password</label>

<div class="password-box">

<input
id="password"
type="password"
name="password"
placeholder="Enter admin password"
autocomplete="current-password"
required>

<span
class="eye"
onclick="togglePassword()">
👁️
</span>

</div>

<button
class="login-btn"
type="submit">
Login to Dashboard
</button>

</form>

</div>

<script>

function togglePassword(){

var password =
document.getElementById("password");

if(password.type === "password"){
password.type = "text";
}else{
password.type = "password";
}

}

</script>

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
        )

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

        error_html = (
            '<div class="error">'
            'Invalid username or password'
            '</div>'
        )

        page = ADMIN_LOGIN_PAGE.replace(
            "__ERROR__",
            error_html
        )

        return render_template_string(page)

    page = ADMIN_LOGIN_PAGE.replace(
        "__ERROR__",
        ""
    )

    return render_template_string(page)


# ==================================================
# ADMIN DASHBOARD
# ==================================================

@app.route("/admin")
def admin_dashboard():

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("admin_login")
        )

    memories = []

    total_photos = 0
    total_videos = 0

    if os.path.exists(
        UPLOAD_FOLDER
    ):

        for memory_id in os.listdir(
            UPLOAD_FOLDER
        ):

            folder = os.path.join(
                UPLOAD_FOLDER,
                memory_id
            )

            if not os.path.isdir(folder):
                continue

            data_file = os.path.join(
                folder,
                "data.json"
            )

            data = {
                "memory_id": memory_id,
                "photos": [],
                "videos": [],
                "message": ""
            }

            if os.path.exists(
                data_file
            ):

                try:

                    with open(
                        data_file,
                        "r",
                        encoding="utf-8"
                    ) as f:
                        data = json.load(f)

                except Exception:
                    pass

            photos = data.get(
                "photos",
                []
            )

            videos = data.get(
                "videos",
                []
            )

            total_photos += len(photos)
            total_videos += len(videos)

            memories.append({
                "id": memory_id,
                "photos": photos,
                "videos": videos,
                "message": data.get(
                    "message",
                    ""
                )
            })

    memories.sort(
        key=lambda item: item["id"],
        reverse=True
    )

    cards = ""

    for memory in memories:

        preview = ""

        for photo in memory["photos"][:5]:

            photo_url = (
                "/memories/"
                + memory["id"]
                + "/"
                + photo
            )

            preview += (
                '<img class="thumb" src="'
                + photo_url
                + '" loading="lazy">'
            )

        if memory["message"].strip():

            message_status = "💌 Message"

        else:

            message_status = "No message"

        open_url = (
            "/memory/"
            + memory["id"]
        )

        cards += (
            '<div class="memory-card">'

            '<div class="memory-top">'

            '<div>'

            '<div class="memory-id">'
            'Memory #'
            + memory["id"]
            + '</div>'

            '<div class="details">'
            + str(len(memory["photos"]))
            + ' Photos • '
            + str(len(memory["videos"]))
            + ' Videos • '
            + message_status
            + '</div>'

            '</div>'

            '<div class="buttons">'

            '<a class="open-btn" '
            'href="'
            + open_url
            + '" '
            'target="_blank">'
            'Open'
            '</a>'

            '<form method="POST" '
            'action="/admin/delete/'
            + memory["id"]
            + '" '
            'onsubmit="return confirm(\'Delete this memory permanently?\')">'

            '<button '
            'class="delete-btn" '
            'type="submit">'
            'Delete'
            '</button>'

            '</form>'

            '</div>'

            '</div>'

            '<div class="thumbs">'
            + preview
            + '</div>'

            '</div>'
        )

    if not cards:

        cards = (
            '<div class="empty">'
            'No memories created yet.'
            '</div>'
        )

    dashboard = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width,initial-scale=1">

<title>Memory QR Dashboard</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
font-family:Arial,sans-serif;
background:
radial-gradient(circle at top,#302060,#101321 55%,#070912);
color:white;
min-height:100vh;
padding:20px;
}

.container{
max-width:1150px;
margin:auto;
}

.header{
display:flex;
justify-content:space-between;
align-items:center;
gap:15px;
margin-bottom:30px;
}

.header h1{
margin:0;
font-size:28px;
}

.logout{
text-decoration:none;
color:white;
padding:10px 15px;
border-radius:10px;
background:rgba(255,255,255,.08);
border:1px solid rgba(255,255,255,.13);
}

.stats{
display:grid;
grid-template-columns:
repeat(auto-fit,minmax(190px,1fr));
gap:15px;
margin-bottom:35px;
}

.stat{
padding:22px;
border-radius:20px;
background:rgba(255,255,255,.07);
border:1px solid rgba(255,255,255,.12);
}

.stat-title{
color:#aaa;
font-size:14px;
}

.stat-number{
font-size:34px;
font-weight:bold;
margin-top:8px;
}

.memory-card{
padding:20px;
border-radius:20px;
background:rgba(255,255,255,.07);
border:1px solid rgba(255,255,255,.12);
margin-bottom:15px;
}

.memory-top{
display:flex;
justify-content:space-between;
align-items:center;
gap:15px;
}

.memory-id{
font-size:18px;
font-weight:bold;
}

.details{
color:#aaa;
font-size:14px;
margin-top:7px;
}

.buttons{
display:flex;
gap:8px;
align-items:center;
}

.open-btn,
.delete-btn{
padding:9px 13px;
border-radius:9px;
font-weight:bold;
border:0;
text-decoration:none;
cursor:pointer;
}

.open-btn{
background:white;
color:#111;
}

.delete-btn{
background:#ff4f5e;
color:white;
}

.thumbs{
display:flex;
flex-wrap:wrap;
gap:8px;
margin-top:16px;
}

.thumb{
width:75px;
height:75px;
object-fit:cover;
border-radius:10px;
}

.empty{
padding:35px;
text-align:center;
color:#999;
background:rgba(255,255,255,.05);
border-radius:18px;
}

@media(max-width:650px){

.header{
align-items:flex-start;
}

.memory-top{
flex-direction:column;
align-items:flex-start;
}

.buttons{
width:100%;
}

}

</style>

</head>

<body>

<div class="container">

<div class="header">

<h1>
📊 Memory QR Admin
</h1>

<a
class="logout"
href="/admin/logout">
Logout
</a>

</div>

<div class="stats">

<div class="stat">

<div class="stat-title">
Total Memories
</div>

<div class="stat-number">
""" + str(len(memories)) + """
</div>

</div>

<div class="stat">

<div class="stat-title">
Total Photos
</div>

<div class="stat-number">
""" + str(total_photos) + """
</div>

</div>

<div class="stat">

<div class="stat-title">
Total Videos
</div>

<div class="stat-number">
""" + str(total_videos) + """
</div>

</div>

<div class="stat">

<div class="stat-title">
Total Files
</div>

<div class="stat-number">
""" + str(
        total_photos + total_videos
    ) + """
</div>

</div>

</div>

<h2>
🗂️ Customer Memories
</h2>

""" + cards + """

</div>

</body>

</html>
"""

    return render_template_string(
        dashboard
    )


# ==================================================
# DELETE MEMORY
# ==================================================

@app.route(
    "/admin/delete/<memory_id>",
    methods=["POST"]
)
def admin_delete(memory_id):

    if not session.get(
        "admin_logged_in"
    ):
        return redirect(
            url_for("admin_login")
        )

    folder = os.path.join(
        UPLOAD_FOLDER,
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

    if os.path.exists(qr_file):

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

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect(
        url_for("admin_login")
    )


# ==================================================
# START SERVER
# ==================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            8000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
