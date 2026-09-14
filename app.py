import os
import json
import secrets
from datetime import datetime, timedelta

import resend
import qrcode

from flask import (
    Flask, request, jsonify, send_from_directory,
    render_template_string, redirect, url_for,
    session, flash
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


app = Flask(__name__)

# =========================
# BASIC SETTINGS
# =========================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key-memoryqr"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MEMORIES_DIR = os.path.join(
    BASE_DIR,
    "memories"
)

QR_DIR = os.path.join(
    BASE_DIR,
    "static",
    "qr"
)

os.makedirs(MEMORIES_DIR, exist_ok=True)
os.makedirs(QR_DIR, exist_ok=True)


# =========================
# ADMIN SETTINGS
# =========================

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "MemoryQR@123"
)

ADMIN_AUTH_FILE = os.path.join(
    BASE_DIR,
    "admin_auth.json"
)


def get_admin_auth():

    if os.path.exists(ADMIN_AUTH_FILE):

        try:

            with open(
                ADMIN_AUTH_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                return json.load(f)

        except Exception:

            pass

    return {
        "username": ADMIN_USERNAME,
        "password_hash": generate_password_hash(
            ADMIN_PASSWORD
        )
    }


def save_admin_auth(username, password):

    data = {
        "username": username,
        "password_hash": generate_password_hash(
            password
        )
    }

    with open(
        ADMIN_AUTH_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(data, f)


# =========================
# RESEND EMAIL SETTINGS
# =========================

RESEND_API_KEY = os.environ.get(
    "RESEND_API_KEY",
    ""
)

RECOVERY_EMAIL = os.environ.get(
    "RECOVERY_EMAIL",
    ""
)

MAIL_FROM = os.environ.get(
    "MAIL_FROM",
    "onboarding@resend.dev"
)


def send_recovery_email(email, reset_url):

    if not RESEND_API_KEY:

        raise Exception(
            "RESEND_API_KEY is not configured."
        )

    if not RECOVERY_EMAIL:

        raise Exception(
            "RECOVERY_EMAIL is not configured."
        )

    resend.api_key = RESEND_API_KEY

    resend.Emails.send({

        "from": MAIL_FROM,

        "to": [email],

        "subject":
            "Memory QR - Admin Password Reset",

        "html": f"""
        <div style="
            font-family:Arial,sans-serif;
            max-width:600px;
            margin:auto;
            padding:30px;
            background:#111827;
            color:white;
            border-radius:20px;
        ">

        <h2>🔐 Memory QR</h2>

        <p>
        A password reset was requested
        for your Memory QR admin account.
        </p>

        <p>
        Click the button below to create
        a new password.
        </p>

        <a href="{reset_url}"
        style="
        display:inline-block;
        padding:14px 22px;
        background:#ffffff;
        color:#111111;
        text-decoration:none;
        border-radius:12px;
        font-weight:bold;
        ">
        Reset Password
        </a>

        <p style="margin-top:25px;">
        This link will expire in 30 minutes.
        </p>

        <p>
        If you did not request this,
        you can safely ignore this email.
        </p>

        </div>
        """
    })


# =========================
# HELPERS
# =========================

def create_memory_folder(memory_id):

    folder = os.path.join(
        MEMORIES_DIR,
        memory_id
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    return folder


def generate_memory_id():

    while True:

        memory_id = secrets.token_hex(4)

        folder = os.path.join(
            MEMORIES_DIR,
            memory_id
        )

        if not os.path.exists(folder):

            return memory_id


def admin_required():

    return session.get(
        "admin_logged_in"
    ) is True


# =========================
# HOME
# =========================

@app.route("/")
def home():

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# =========================
# CREATE MEMORY
# =========================

@app.route(
    "/create-memory",
    methods=["POST"]
)
def create_memory():

    memory_id = generate_memory_id()

    folder = create_memory_folder(
        memory_id
    )

    with open(
        os.path.join(
            folder,
            "message.txt"
        ),
        "w",
        encoding="utf-8"
    ) as f:

        f.write("")

    qr = qrcode.make(
        request.host_url.rstrip("/")
        + "/memory/"
        + memory_id
    )

    qr_path = os.path.join(
        QR_DIR,
        memory_id + ".png"
    )

    qr.save(qr_path)

    return jsonify({
        "success": True,
        "memory_id": memory_id,
        "qr":
            "/static/qr/"
            + memory_id
            + ".png"
    })


# =========================
# UPLOAD
# =========================

@app.route(
    "/upload/<memory_id>",
    methods=["POST"]
)
def upload_file(memory_id):

    folder = os.path.join(
        MEMORIES_DIR,
        memory_id
    )

    if not os.path.exists(folder):

        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404

    files = request.files.getlist(
        "file"
    )

    uploaded = []

    for file in files:

        if not file or not file.filename:

            continue

        filename = os.path.basename(
            file.filename
        )

        save_path = os.path.join(
            folder,
            filename
        )

        file.save(save_path)

        uploaded.append(filename)

    return jsonify({
        "success": True,
        "files": uploaded
    })


# =========================
# SAVE MESSAGE
# =========================

@app.route(
    "/save-message/<memory_id>",
    methods=["POST"]
)
def save_message(memory_id):

    folder = os.path.join(
        MEMORIES_DIR,
        memory_id
    )

    if not os.path.exists(folder):

        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404

    data = request.get_json(
        silent=True
    ) or {}

    message = data.get(
        "message",
        ""
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


# =========================
# MEMORY PAGE
# =========================

@app.route(
    "/memory/<memory_id>"
)
def memory_page(memory_id):

    folder = os.path.join(
        MEMORIES_DIR,
        memory_id
    )

    if not os.path.exists(folder):

        return "Memory not found", 404

    files = []

    for filename in os.listdir(folder):

        if filename == "message.txt":

            continue

        path = os.path.join(
            folder,
            filename
        )

        if os.path.isfile(path):

            files.append(filename)

    message_path = os.path.join(
        folder,
        "message.txt"
    )

    message = ""

    if os.path.exists(
        message_path
    ):

        with open(
            message_path,
            "r",
            encoding="utf-8"
        ) as f:

            message = f.read()

    html = """
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Memory QR</title>

<style>

body{
margin:0;
background:linear-gradient(
135deg,
#080b18,
#17152e,
#241238
);
color:white;
font-family:Arial,sans-serif;
padding:25px;
}

.container{
max-width:900px;
margin:auto;
}

h1{
text-align:center;
}

.message{
background:rgba(255,255,255,.08);
padding:20px;
border-radius:20px;
margin:20px 0;
white-space:pre-wrap;
overflow-wrap:anywhere;
line-height:1.7;
}

.gallery{
display:grid;
grid-template-columns:
repeat(auto-fit,minmax(250px,1fr));
gap:15px;
}

img,video{
width:100%;
border-radius:18px;
display:block;
}

.footer{
text-align:center;
margin-top:40px;
opacity:.7;
}

</style>

</head>

<body>

<div class="container">

<h1>❤️ Your Memory</h1>

{% if message %}

<div class="message">
{{ message }}
</div>

{% endif %}

<div class="gallery">

{% for file in files %}

{% set lower = file.lower() %}

{% if lower.endswith('.jpg')
or lower.endswith('.jpeg')
or lower.endswith('.png')
or lower.endswith('.webp') %}

<img
src="/memories/{{ memory_id }}/{{ file }}">

{% elif lower.endswith('.mp4')
or lower.endswith('.webm')
or lower.endswith('.mov') %}

<video controls>

<source
src="/memories/{{ memory_id }}/{{ file }}">

</video>

{% endif %}

{% endfor %}

</div>

<div class="footer">
This site is made by Aquib Khan ❤️
</div>

</div>

</body>

</html>
"""

    return render_template_string(
        html,
        memory_id=memory_id,
        files=files,
        message=message
    )


# =========================
# SERVE FILES
# =========================

@app.route(
    "/memories/<memory_id>/<filename>"
)
def serve_memory_file(
    memory_id,
    filename
):

    folder = os.path.join(
        MEMORIES_DIR,
        memory_id
    )

    return send_from_directory(
        folder,
        filename
    )


# =========================
# ADMIN LOGIN
# =========================

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

        auth = get_admin_auth()

        if (
            username == auth["username"]
            and check_password_hash(
                auth["password_hash"],
                password
            )
        ):

            session[
                "admin_logged_in"
            ] = True

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        flash(
            "Invalid username or password."
        )

    return """
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Memory QR Admin Login</title>

<style>

body{
margin:0;
min-height:100vh;
display:flex;
justify-content:center;
align-items:center;
background:
linear-gradient(
135deg,
#080b18,
#1b1235,
#32124b
);
color:white;
font-family:Arial,sans-serif;
}

.box{
width:90%;
max-width:400px;
background:rgba(255,255,255,.09);
backdrop-filter:blur(20px);
padding:30px;
border-radius:25px;
box-shadow:
0 20px 60px rgba(0,0,0,.5);
}

h1{
text-align:center;
}

input{
width:100%;
box-sizing:border-box;
padding:15px;
margin:8px 0;
border:none;
border-radius:12px;
background:rgba(255,255,255,.12);
color:white;
outline:none;
}

button{
width:100%;
padding:15px;
margin-top:10px;
border:none;
border-radius:12px;
background:#ffffff;
color:#111;
font-weight:bold;
cursor:pointer;
}

.password-box{
position:relative;
}

.toggle{
position:absolute;
right:12px;
top:18px;
cursor:pointer;
}

.error{
color:#ff8585;
text-align:center;
margin:10px 0;
}

.forgot{
text-align:center;
margin-top:18px;
}

a{
color:white;
}

</style>

</head>

<body>

<div class="box">

<h1>🔐 Admin Login</h1>

{% with messages =
get_flashed_messages() %}

{% if messages %}

<div class="error">
{{ messages[0] }}
</div>

{% endif %}

{% endwith %}

<form method="POST">

<input
type="text"
name="username"
placeholder="Username"
required
autocomplete="username">

<div class="password-box">

<input
id="password"
type="password"
name="password"
placeholder="Password"
required
autocomplete="current-password">

<span
class="toggle"
onclick="togglePassword()">
👁️
</span>

</div>

<button type="submit">
Login
</button>

</form>

<div class="forgot">

<a href="/admin/forgot">
Forgot Password?
</a>

</div>

</div>

<script>

function togglePassword(){

const input =
document.getElementById(
"password"
);

input.type =
input.type === "password"
? "text"
: "password";

}

</script>

</body>

</html>
"""


# =========================
# FORGOT PASSWORD
# =========================

@app.route(
    "/admin/forgot",
    methods=["GET", "POST"]
)
def admin_forgot():

    error = ""

    success = ""

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        if not RECOVERY_EMAIL:

            error = (
                "Recovery email is not configured."
            )

        elif (
            email !=
            RECOVERY_EMAIL.lower()
        ):

            error = (
                "Recovery email doesn't match."
            )

        else:

            token = secrets.token_urlsafe(
                32
            )

            expires = (
                datetime.utcnow()
                + timedelta(minutes=30)
            )

            session[
                "reset_token"
            ] = token

            session[
                "reset_expires"
            ] = expires.isoformat()

            reset_url = url_for(
                "admin_reset",
                token=token,
                _external=True
            )

            try:

                send_recovery_email(
                    email,
                    reset_url
                )

                success = (
                    "Recovery email sent. "
                    "Check your Gmail inbox."
                )

            except Exception as e:

                print(
                    "EMAIL ERROR:",
                    repr(e)
                )

                error = (
                    "Unable to send recovery email: "
                    + str(e)
                )

    return f"""
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Forgot Password</title>

<style>

body{{
margin:0;
min-height:100vh;
display:flex;
justify-content:center;
align-items:center;
background:
linear-gradient(
135deg,
#080b18,
#1b1235,
#32124b
);
color:white;
font-family:Arial,sans-serif;
}}

.box{{
width:90%;
max-width:420px;
padding:30px;
border-radius:25px;
background:rgba(255,255,255,.09);
}}

input{{
width:100%;
box-sizing:border-box;
padding:15px;
border:0;
border-radius:12px;
margin:10px 0;
}}

button{{
width:100%;
padding:15px;
border:0;
border-radius:12px;
font-weight:bold;
}}

.error{{
color:#ff7777;
margin:12px 0;
word-break:break-word;
}}

.success{{
color:#72ff9b;
margin:12px 0;
}}

a{{
color:white;
}}

</style>

</head>

<body>

<div class="box">

<h2>🔑 Forgot Password</h2>

<p>
Enter your recovery Gmail address.
</p>

{"<div class='error'>" + error + "</div>" if error else ""}

{"<div class='success'>" + success + "</div>" if success else ""}

<form method="POST">

<input
type="email"
name="email"
placeholder="Recovery Gmail"
required>

<button type="submit">
Send Recovery Email
</button>

</form>

<p>

<a href="/admin/login">
← Back to Login
</a>

</p>

</div>

</body>

</html>
"""


# =========================
# RESET PASSWORD
# =========================

@app.route(
    "/admin/reset/<token>",
    methods=["GET", "POST"]
)
def admin_reset(token):

    saved_token = session.get(
        "reset_token"
    )

    expires_text = session.get(
        "reset_expires"
    )

    if (
        not saved_token
        or token != saved_token
    ):

        return (
            "Invalid or expired reset link.",
            400
        )

    if not expires_text:

        return (
            "Invalid reset link.",
            400
        )

    try:

        expires = datetime.fromisoformat(
            expires_text
        )

    except Exception:

        return (
            "Invalid reset link.",
            400
        )

    if datetime.utcnow() > expires:

        session.pop(
            "reset_token",
            None
        )

        session.pop(
            "reset_expires",
            None
        )

        return (
            "Reset link has expired.",
            400
        )

    if request.method == "POST":

        password = request.form.get(
            "password",
            ""
        )

        confirm = request.form.get(
            "confirm_password",
            ""
        )

        if len(password) < 8:

            return (
                "Password must be at least 8 characters.",
                400
            )

        if password != confirm:

            return (
                "Passwords do not match.",
                400
            )

        auth = get_admin_auth()

        save_admin_auth(
            auth["username"],
            password
        )

        session.pop(
            "reset_token",
            None
        )

        session.pop(
            "reset_expires",
            None
        )

        return redirect(
            url_for(
                "admin_login"
            )
        )

    return """
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Reset Password</title>

<style>

body{
margin:0;
min-height:100vh;
display:flex;
justify-content:center;
align-items:center;
background:
linear-gradient(
135deg,
#080b18,
#1b1235,
#32124b
);
color:white;
font-family:Arial,sans-serif;
}

.box{
width:90%;
max-width:400px;
padding:30px;
border-radius:25px;
background:rgba(255,255,255,.09);
}

input{
width:100%;
box-sizing:border-box;
padding:15px;
margin:8px 0;
border:0;
border-radius:12px;
}

button{
width:100%;
padding:15px;
border:0;
border-radius:12px;
margin-top:10px;
font-weight:bold;
}

</style>

</head>

<body>

<div class="box">

<h2>🔐 Create New Password</h2>

<form method="POST">

<input
type="password"
name="password"
placeholder="New Password"
required>

<input
type="password"
name="confirm_password"
placeholder="Confirm Password"
required>

<button type="submit">
Reset Password
</button>

</form>

</div>

</body>

</html>
"""


# =========================
# ADMIN DASHBOARD
# =========================

@app.route("/admin")
def admin_dashboard():

    if not admin_required():

        return redirect(
            url_for(
                "admin_login"
            )
        )

    memories = []

    total_photos = 0
    total_videos = 0

    if os.path.exists(
        MEMORIES_DIR
    ):

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

            for filename in os.listdir(
                folder
            ):

                if filename == "message.txt":

                    continue

                path = os.path.join(
                    folder,
                    filename
                )

                if not os.path.isfile(path):

                    continue

                files.append(filename)

                lower = filename.lower()

                if lower.endswith(
                    (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp"
                    )
                ):

                    photos += 1

                elif lower.endswith(
                    (
                        ".mp4",
                        ".webm",
                        ".mov"
                    )
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

    html = """
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Memory QR Admin Dashboard</title>

<style>

body{
margin:0;
background:
linear-gradient(
135deg,
#080b18,
#17152e,
#241238
);
color:white;
font-family:Arial,sans-serif;
padding:20px;
}

.container{
max-width:1100px;
margin:auto;
}

.header{
display:flex;
justify-content:space-between;
align-items:center;
gap:10px;
flex-wrap:wrap;
}

.logout{
background:#ff5555;
color:white;
padding:10px 15px;
border-radius:10px;
text-decoration:none;
}

.stats{
display:grid;
grid-template-columns:
repeat(auto-fit,minmax(180px,1fr));
gap:15px;
margin:25px 0;
}

.stat{
background:rgba(255,255,255,.09);
padding:20px;
border-radius:20px;
text-align:center;
}

.stat h2{
margin:5px 0;
font-size:32px;
}

.memory{
background:rgba(255,255,255,.08);
padding:20px;
border-radius:20px;
margin-bottom:15px;
}

.memory-id{
font-size:20px;
font-weight:bold;
word-break:break-all;
}

.actions{
display:flex;
gap:10px;
flex-wrap:wrap;
margin-top:15px;
}

.btn{
display:inline-block;
padding:10px 14px;
background:white;
color:#111;
border-radius:10px;
text-decoration:none;
font-weight:bold;
}

.delete{
background:#ff5555;
color:white;
}

</style>

</head>

<body>

<div class="container">

<div class="header">

<h1>📊 Memory QR Admin</h1>

<a
class="logout"
href="/admin/logout">
Logout
</a>

</div>

<div class="stats">

<div class="stat">

<div>🗂️ Memories</div>

<h2>
{{ memories|length }}
</h2>

</div>

<div class="stat">

<div>📸 Photos</div>

<h2>
{{ total_photos }}
</h2>

</div>

<div class="stat">

<div>🎥 Videos</div>

<h2>
{{ total_videos }}
</h2>

</div>

<div class="stat">

<div>🔳 QR Memories</div>

<h2>
{{ memories|length }}
</h2>

</div>

</div>

<h2>Customer Memories</h2>

{% for memory in memories %}

<div class="memory">

<div class="memory-id">
Memory ID: {{ memory.id }}
</div>

<p>
📸 Photos: {{ memory.photos }}
</p>

<p>
🎥 Videos: {{ memory.videos }}
</p>

<div class="actions">

<a
class="btn"
href="/memory/{{ memory.id }}"
target="_blank">
Open Memory
</a>

<a
class="btn"
href="/static/qr/{{ memory.id }}.png"
target="_blank">
View QR
</a>

<a
class="btn delete"
href="/admin/delete/{{ memory.id }}"
onclick="return confirm('Delete this memory permanently?')">
Delete
</a>

</div>

</div>

{% else %}

<div class="memory">
No memories found.
</div>

{% endfor %}

</div>

</body>

</html>
"""

    return render_template_string(
        html,
        memories=memories,
        total_photos=total_photos,
        total_videos=total_videos
    )


# =========================
# DELETE MEMORY
# =========================

@app.route(
    "/admin/delete/<memory_id>"
)
def admin_delete(memory_id):

    if not admin_required():

        return redirect(
            url_for(
                "admin_login"
            )
        )

    folder = os.path.join(
        MEMORIES_DIR,
        memory_id
    )

    if os.path.exists(folder):

        import shutil

        shutil.rmtree(folder)

    qr_path = os.path.join(
        QR_DIR,
        memory_id + ".png"
    )

    if os.path.exists(qr_path):

        os.remove(qr_path)

    return redirect(
        url_for(
            "admin_dashboard"
        )
    )


# =========================
# LOGOUT
# =========================

@app.route(
    "/admin/logout"
)
def admin_logout():

    session.clear()

    return redirect(
        url_for(
            "admin_login"
        )
    )


# =========================
# RUN
# =========================

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
