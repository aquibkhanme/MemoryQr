import os
import secrets
import shutil
import qrcode

from flask import (
    Flask, request, jsonify, send_from_directory,
    render_template_string, redirect, url_for,
    session, flash
)

from werkzeug.utils import secure_filename


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "memoryqr-secret-key"
)

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "MemoryQR@123"
)

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

MEMORIES_DIR = os.path.join(
    BASE_DIR, "memories"
)

QR_DIR = os.path.join(
    BASE_DIR, "static", "qr"
)

os.makedirs(MEMORIES_DIR, exist_ok=True)
os.makedirs(QR_DIR, exist_ok=True)


# ==============================
# HOME
# ==============================

@app.route("/")
def home():
    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# ==============================
# CREATE MEMORY + QR
# ==============================

@app.route(
    "/create-memory",
    methods=["POST"]
)
def create_memory():

    try:

        while True:

            memory_id = secrets.token_hex(4)

            folder = os.path.join(
                MEMORIES_DIR,
                memory_id
            )

            if not os.path.exists(folder):
                break

        os.makedirs(
            folder,
            exist_ok=True
        )

        with open(
            os.path.join(folder, "message.txt"),
            "w",
            encoding="utf-8"
        ) as f:
            f.write("")

        memory_url = (
            request.host_url.rstrip("/")
            + "/memory/"
            + memory_id
        )

        qr = qrcode.make(memory_url)

        qr_path = os.path.join(
            QR_DIR,
            memory_id + ".png"
        )

        qr.save(qr_path)

        return jsonify({
            "success": True,
            "memory_id": memory_id,
            "qr": "/static/qr/"
                  + memory_id
                  + ".png",
            "memory_url": memory_url
        })

    except Exception as e:

        print("CREATE ERROR:", repr(e))

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==============================
# UPLOAD FILES
# ==============================

@app.route(
    "/upload/<memory_id>",
    methods=["POST"]
)
def upload_file(memory_id):

    try:

        folder = os.path.join(
            MEMORIES_DIR,
            memory_id
        )

        if not os.path.isdir(folder):

            return jsonify({
                "success": False,
                "error": "Memory not found"
            }), 404

        files = request.files.getlist("file")

        uploaded = []

        for file in files:

            if not file or not file.filename:
                continue

            filename = secure_filename(
                file.filename
            )

            if not filename:
                continue

            file.save(
                os.path.join(
                    folder,
                    filename
                )
            )

            uploaded.append(filename)

        return jsonify({
            "success": True,
            "files": uploaded
        })

    except Exception as e:

        print("UPLOAD ERROR:", repr(e))

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==============================
# SAVE DIARY
# ==============================

@app.route(
    "/save-message/<memory_id>",
    methods=["POST"]
)
def save_message(memory_id):

    try:

        folder = os.path.join(
            MEMORIES_DIR,
            memory_id
        )

        if not os.path.isdir(folder):

            return jsonify({
                "success": False,
                "error": "Memory not found"
            }), 404

        data = request.get_json(
            silent=True
        ) or {}

        message = str(
            data.get("message", "")
        )

        if len(message) > 70000:

            return jsonify({
                "success": False,
                "error": "Message is too long"
            }), 400

        with open(
            os.path.join(
                folder,
                "message.txt"
            ),
            "w",
            encoding="utf-8"
        ) as f:

            f.write(message)

        return jsonify({
            "success": True
        })

    except Exception as e:

        print("MESSAGE ERROR:", repr(e))

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==============================
# MEMORY PAGE
# ==============================

@app.route("/memory/<memory_id>")
def memory_page(memory_id):

    folder = os.path.join(
        MEMORIES_DIR,
        memory_id
    )

    if not os.path.isdir(folder):
        return "Memory not found", 404

    files = []

    for name in os.listdir(folder):

        if name == "message.txt":
            continue

        path = os.path.join(
            folder,
            name
        )

        if os.path.isfile(path):
            files.append(name)

    message = ""

    message_path = os.path.join(
        folder,
        "message.txt"
    )

    if os.path.exists(message_path):

        with open(
            message_path,
            "r",
            encoding="utf-8"
        ) as f:

            message = f.read()

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

<title>Your Memory ❤️</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
font-family:Arial,sans-serif;
color:white;
background:
linear-gradient(
135deg,
#080914,
#17102d,
#071c2c
);
min-height:100vh;
}

.container{
width:92%;
max-width:950px;
margin:auto;
padding:30px 0 50px;
}

.card{
padding:25px;
margin-bottom:22px;
border-radius:24px;
background:rgba(255,255,255,.07);
border:1px solid rgba(255,255,255,.14);
box-shadow:0 20px 60px rgba(0,0,0,.3);
}

h1{
text-align:center;
font-size:35px;
}

.message{
white-space:pre-wrap;
overflow-wrap:anywhere;
line-height:1.8;
font-size:17px;
}

.gallery{
display:grid;
grid-template-columns:
repeat(auto-fit,minmax(160px,1fr));
gap:15px;
}

.gallery img,
.gallery video{
width:100%;
border-radius:18px;
background:#000;
}

.empty{
text-align:center;
opacity:.6;
padding:30px;
}

.footer{
text-align:center;
opacity:.65;
margin-top:30px;
}

</style>

</head>

<body>

<div class="container">

<div class="card">

<h1>❤️ Your Memory</h1>

{% if message %}

<div class="message">{{ message }}</div>

{% else %}

<div class="empty">
No personal message added.
</div>

{% endif %}

</div>

<div class="card">

<h2>📸 Memories</h2>

{% if files %}

<div class="gallery">

{% for file in files %}

{% if file.lower().endswith(
('.jpg','.jpeg','.png','.webp','.gif')
) %}

<img
src="/memories/{{ memory_id }}/{{ file }}"
loading="lazy"
>

{% elif file.lower().endswith(
('.mp4','.webm','.mov','.m4v')
) %}

<video controls playsinline>

<source
src="/memories/{{ memory_id }}/{{ file }}"
>

</video>

{% endif %}

{% endfor %}

</div>

{% else %}

<div class="empty">
No photos or videos yet.
</div>

{% endif %}

</div>

<div class="footer">
This site is made by Aquib Khan ❤️
</div>

</div>

</body>
</html>
        """,
        memory_id=memory_id,
        files=files,
        message=message
    )


# ==============================
# MEMORY FILES
# ==============================

@app.route(
    "/memories/<memory_id>/<filename>"
)
def memory_file(memory_id, filename):

    folder = os.path.join(
        MEMORIES_DIR,
        memory_id
    )

    return send_from_directory(
        folder,
        filename
    )


# ==============================
# ADMIN LOGIN
# ==============================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if session.get("admin_logged_in"):

        return redirect(
            url_for("admin_dashboard")
        )

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
            secrets.compare_digest(
                username,
                ADMIN_USERNAME
            )
            and
            secrets.compare_digest(
                password,
                ADMIN_PASSWORD
            )
        ):

            session.clear()

            session["admin_logged_in"] = True

            return redirect(
                url_for("admin_dashboard")
            )

        flash(
            "Invalid username or password."
        )

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

<title>Memory QR Admin</title>

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
linear-gradient(
135deg,
#070914,
#17102e,
#091d35
);
}

.box{
width:100%;
max-width:420px;
padding:32px;
border-radius:25px;
background:rgba(255,255,255,.08);
border:1px solid rgba(255,255,255,.15);
box-shadow:0 25px 70px rgba(0,0,0,.45);
}

.logo{
text-align:center;
font-size:42px;
}

h1{
text-align:center;
}

.sub{
text-align:center;
opacity:.6;
margin-bottom:25px;
}

label{
display:block;
margin:12px 0 7px;
}

input{
width:100%;
padding:14px;
border-radius:12px;
border:1px solid rgba(255,255,255,.15);
background:rgba(255,255,255,.08);
color:white;
font-size:16px;
outline:none;
}

.password{
position:relative;
}

.password input{
padding-right:50px;
}

.eye{
position:absolute;
right:15px;
top:13px;
cursor:pointer;
font-size:20px;
}

button{
width:100%;
padding:14px;
margin-top:20px;
border:0;
border-radius:12px;
background:
linear-gradient(
135deg,
#ff2bb5,
#7048ff
);
color:white;
font-size:16px;
font-weight:bold;
}

.error{
padding:12px;
border-radius:10px;
background:rgba(255,50,50,.15);
color:#ffb5b5;
text-align:center;
}

.secure{
text-align:center;
opacity:.5;
font-size:13px;
margin-top:20px;
}

</style>

</head>

<body>

<div class="box">

<div class="logo">🔐</div>

<h1>Admin Login</h1>

<div class="sub">
Memory QR Management
</div>

{% with messages = get_flashed_messages() %}

{% if messages %}

<div class="error">
{{ messages[0] }}
</div>

{% endif %}

{% endwith %}

<form method="POST">

<label>Username</label>

<input
type="text"
name="username"
placeholder="Enter username"
required
>

<label>Password</label>

<div class="password">

<input
id="password"
type="password"
name="password"
placeholder="Enter password"
required
>

<span
class="eye"
onclick="togglePassword()"
>
👁️
</span>

</div>

<button type="submit">
Login
</button>

</form>

<div class="secure">
🔒 Secure Admin Area
</div>

</div>

<script>

function togglePassword(){

const p =
document.getElementById("password");

p.type =
p.type === "password"
? "text"
: "password";

}

</script>

</body>

</html>
        """
    )


# ==============================
# ADMIN DASHBOARD
# ==============================

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

    if os.path.exists(MEMORIES_DIR):

        for memory_id in os.listdir(
            MEMORIES_DIR
        ):

            folder = os.path.join(
                MEMORIES_DIR,
                memory_id
            )

            if not os.path.isdir(folder):
                continue

            files = []
            photos = 0
            videos = 0

            for name in os.listdir(folder):

                if name == "message.txt":
                    continue

                path = os.path.join(
                    folder,
                    name
                )

                if not os.path.isfile(path):
                    continue

                files.append(name)

                lower = name.lower()

                if lower.endswith(
                    (".jpg",".jpeg",".png",".webp",".gif")
                ):

                    photos += 1

                elif lower.endswith(
                    (".mp4",".webm",".mov",".m4v")
                ):

                    videos += 1

            total_photos += photos
            total_videos += videos

            memories.append({
                "id": memory_id,
                "files": files,
                "photos": photos,
                "videos": videos
            })

    memories.reverse()

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

<title>Memory QR Admin</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
font-family:Arial,sans-serif;
color:white;
background:
linear-gradient(
135deg,
#070914,
#11152b,
#081b2d
);
min-height:100vh;
}

.header{
padding:22px;
display:flex;
justify-content:space-between;
align-items:center;
flex-wrap:wrap;
gap:15px;
border-bottom:1px solid rgba(255,255,255,.1);
}

.brand{
font-size:24px;
font-weight:bold;
}

.logout{
color:white;
text-decoration:none;
padding:10px 16px;
border-radius:10px;
background:rgba(255,255,255,.1);
}

.container{
width:94%;
max-width:1100px;
margin:auto;
padding:30px 0 50px;
}

.stats{
display:grid;
grid-template-columns:
repeat(auto-fit,minmax(180px,1fr));
gap:16px;
margin-bottom:30px;
}

.stat{
padding:22px;
border-radius:20px;
background:rgba(255,255,255,.07);
border:1px solid rgba(255,255,255,.12);
}

.number{
font-size:30px;
font-weight:bold;
}

.name{
opacity:.6;
margin-top:5px;
}

.memory{
padding:20px;
margin-bottom:18px;
border-radius:20px;
background:rgba(255,255,255,.07);
border:1px solid rgba(255,255,255,.12);
}

.top{
display:flex;
justify-content:space-between;
align-items:center;
flex-wrap:wrap;
gap:15px;
}

.id{
font-size:20px;
font-weight:bold;
}

.badge{
display:inline-block;
padding:7px 10px;
margin:3px;
border-radius:20px;
background:rgba(255,255,255,.1);
font-size:13px;
}

.actions{
display:flex;
gap:10px;
flex-wrap:wrap;
margin-top:18px;
}

.actions a{
color:white;
text-decoration:none;
padding:10px 14px;
border-radius:10px;
background:rgba(59,130,246,.35);
}

.actions .delete{
background:rgba(239,68,68,.35);
}

.empty{
text-align:center;
padding:40px;
opacity:.5;
}

</style>

</head>

<body>

<div class="header">

<div class="brand">
🔐 Memory QR Admin
</div>

<a
class="logout"
href="/admin/logout"
>
Logout 🚪
</a>

</div>

<div class="container">

<div class="stats">

<div class="stat">
<div>💾</div>
<div class="number">
{{ memories|length }}
</div>
<div class="name">
Total Memories
</div>
</div>

<div class="stat">
<div>📸</div>
<div class="number">
{{ total_photos }}
</div>
<div class="name">
Total Photos
</div>
</div>

<div class="stat">
<div>🎥</div>
<div class="number">
{{ total_videos }}
</div>
<div class="name">
Total Videos
</div>
</div>

<div class="stat">
<div>🔗</div>
<div class="number">
{{ memories|length }}
</div>
<div class="name">
QR Memories
</div>
</div>

</div>

<h1>
Customer Memories
</h1>

{% if memories %}

{% for memory in memories %}

<div class="memory">

<div class="top">

<div class="id">
🆔 {{ memory.id }}
</div>

<div>

<span class="badge">
📸 {{ memory.photos }}
</span>

<span class="badge">
🎥 {{ memory.videos }}
</span>

<span class="badge">
📁 {{ memory.files|length }}
</span>

</div>

</div>

<div class="actions">

<a
href="/memory/{{ memory.id }}"
target="_blank"
>
👁️ Open Memory
</a>

<a
href="/static/qr/{{ memory.id }}.png"
target="_blank"
>
🔳 View QR
</a>

<a
class="delete"
href="/admin/delete/{{ memory.id }}"
onclick="return confirm('Delete this memory permanently?')"
>
🗑️ Delete
</a>

</div>

</div>

{% endfor %}

{% else %}

<div class="empty">
No memories created yet.
</div>

{% endif %}

</div>

</body>

</html>
        """,
        memories=memories,
        total_photos=total_photos,
        total_videos=total_videos
    )


# ==============================
# DELETE
# ==============================

@app.route(
    "/admin/delete/<memory_id>"
)
def admin_delete(memory_id):

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            url_for("admin_login")
        )

    folder = os.path.join(
        MEMORIES_DIR,
        memory_id
    )

    if os.path.exists(folder):

        shutil.rmtree(folder)

    qr_path = os.path.join(
        QR_DIR,
        memory_id + ".png"
    )

    if os.path.exists(qr_path):

        os.remove(qr_path)

    return redirect(
        url_for("admin_dashboard")
    )


# ==============================
# LOGOUT
# ==============================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# ==============================
# START
# ==============================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                8000
            )
        ),
        debug=False
    )
