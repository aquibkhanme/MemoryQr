import os
import secrets
import shutil

import qrcode

from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    render_template_string,
    redirect,
    url_for,
    session,
    flash
)

from werkzeug.utils import secure_filename


app = Flask(__name__)

# =========================
# SECURITY
# =========================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "MemoryQR@123"
)

# =========================
# FOLDERS
# =========================

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
# MEMORY FUNCTIONS
# =========================

def generate_memory_id():

    while True:

        memory_id = secrets.token_hex(4)

        folder = os.path.join(
            MEMORIES_DIR,
            memory_id
        )

        if not os.path.exists(folder):
            return memory_id


def create_memory_folder(memory_id):

    folder = os.path.join(
        MEMORIES_DIR,
        memory_id
    )

    os.makedirs(folder, exist_ok=True)

    return folder


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

    message_file = os.path.join(
        folder,
        "message.txt"
    )

    with open(
        message_file,
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
        "qr": "/static/qr/" + memory_id + ".png"
    })


# =========================
# UPLOAD FILES
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
# SAVE PERSONAL MESSAGE
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

    message_file = os.path.join(
        folder,
        "message.txt"
    )

    with open(
        message_file,
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

    message_file = os.path.join(
        folder,
        "message.txt"
    )

    message = ""

    if os.path.exists(message_file):

        with open(
            message_file,
            "r",
            encoding="utf-8"
        ) as f:

            message = f.read()

    html = """
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1.0"
>

<title>Your Memory ❤️</title>

<style>

*{
    box-sizing:border-box;
}

body{

    margin:0;

    font-family:
    Arial,
    sans-serif;

    background:
    linear-gradient(
        135deg,
        #090b18,
        #17102c,
        #0b1830
    );

    color:white;

    min-height:100vh;
}

.container{

    width:92%;

    max-width:900px;

    margin:auto;

    padding:30px 0 50px;
}

.card{

    background:
    rgba(255,255,255,0.08);

    border:
    1px solid
    rgba(255,255,255,0.15);

    border-radius:25px;

    padding:25px;

    margin-bottom:25px;

    backdrop-filter:blur(12px);

    box-shadow:
    0 20px 60px
    rgba(0,0,0,0.35);
}

h1{

    text-align:center;

    font-size:35px;

    margin-bottom:25px;
}

.message{

    white-space:pre-wrap;

    overflow-wrap:anywhere;

    line-height:1.7;

    font-size:17px;
}

.gallery{

    display:grid;

    grid-template-columns:
    repeat(auto-fit,minmax(150px,1fr));

    gap:15px;
}

.gallery img,
.gallery video{

    width:100%;

    border-radius:18px;

    display:block;

    background:#000;
}

.empty{

    text-align:center;

    opacity:.7;

    padding:30px;
}

.footer{

    text-align:center;

    opacity:.7;

    margin-top:30px;

    font-size:14px;
}

</style>

</head>

<body>

<div class="container">

    <div class="card">

        <h1>
            ❤️ Your Memory
        </h1>

        {% if message %}

        <div class="message">
            {{ message }}
        </div>

        {% else %}

        <div class="empty">
            No personal message added.
        </div>

        {% endif %}

    </div>


    <div class="card">

        <h2>
            📸 Memories
        </h2>

        {% if files %}

        <div class="gallery">

            {% for file in files %}

                {% if file.lower().endswith(
                    ('.jpg','.jpeg','.png','.webp')
                ) %}

                    <img
                    src="/memories/{{ memory_id }}/{{ file }}"
                    loading="lazy"
                    >

                {% elif file.lower().endswith(
                    ('.mp4','.webm','.mov')
                ) %}

                    <video
                    controls
                    playsinline
                    preload="metadata"
                    >

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
"""

    return render_template_string(
        html,
        memory_id=memory_id,
        files=files,
        message=message
    )


# =========================
# SERVE MEMORY FILE
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

    if session.get(
        "admin_logged_in"
    ) is True:

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

    return render_template_string("""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1.0"
>

<title>Admin Login - Memory QR</title>

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

.login-box{

    width:100%;

    max-width:420px;

    padding:32px;

    border-radius:25px;

    background:
    rgba(255,255,255,.08);

    border:
    1px solid
    rgba(255,255,255,.16);

    box-shadow:
    0 25px 70px
    rgba(0,0,0,.45);

    backdrop-filter:blur(15px);
}

.logo{

    text-align:center;

    font-size:42px;

    margin-bottom:8px;
}

h1{

    text-align:center;

    margin:0 0 8px;

    font-size:28px;
}

.subtitle{

    text-align:center;

    opacity:.7;

    margin-bottom:28px;
}

label{

    display:block;

    margin-bottom:8px;

    font-weight:bold;
}

input{

    width:100%;

    padding:14px;

    border:none;

    outline:none;

    border-radius:12px;

    margin-bottom:18px;

    background:
    rgba(255,255,255,.1);

    color:white;

    border:
    1px solid
    rgba(255,255,255,.15);

    font-size:16px;
}

.password-box{

    position:relative;
}

.password-box input{

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

    border:none;

    border-radius:12px;

    background:
    linear-gradient(
        135deg,
        #7c3aed,
        #2563eb
    );

    color:white;

    font-size:16px;

    font-weight:bold;

    cursor:pointer;
}

.error{

    padding:12px;

    margin-bottom:18px;

    border-radius:10px;

    background:
    rgba(255,60,60,.15);

    color:#ffb4b4;

    text-align:center;
}

.security{

    text-align:center;

    margin-top:22px;

    font-size:13px;

    opacity:.55;
}

</style>

</head>

<body>

<div class="login-box">

    <div class="logo">
        🔐
    </div>

    <h1>
        Admin Login
    </h1>

    <div class="subtitle">
        Memory QR Management
    </div>

    {% with messages = get_flashed_messages() %}

        {% if messages %}

            <div class="error">
                {{ messages[0] }}
            </div>

        {% endif %}

    {% endwith %}

    <form
    method="POST"
    >

        <label>
            Username
        </label>

        <input
        type="text"
        name="username"
        placeholder="Enter username"
        autocomplete="username"
        required
        >

        <label>
            Password
        </label>

        <div class="password-box">

            <input
            id="password"
            type="password"
            name="password"
            placeholder="Enter password"
            autocomplete="current-password"
            required
            >

            <span
            class="eye"
            onclick="togglePassword()"
            >
                👁️
            </span>

        </div>

        <button
        type="submit"
        >
            Login
        </button>

    </form>

    <div class="security">
        🔒 Secure Admin Area
    </div>

</div>

<script>

function togglePassword(){

    const password =
        document.getElementById(
            "password"
        );

    if(
        password.type === "password"
    ){

        password.type = "text";

    }else{

        password.type = "password";

    }

}

</script>

</body>

</html>
""")


# =========================
# ADMIN DASHBOARD
# =========================

@app.route("/admin")
def admin_dashboard():

    if session.get(
        "admin_logged_in"
    ) is not True:

        return redirect(
            url_for("admin_login")
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
                    (".jpg",".jpeg",".png",".webp")
                ):

                    photos += 1

                elif lower.endswith(
                    (".mp4",".webm",".mov")
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

    html = """

<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1.0"
>

<title>Memory QR Admin</title>

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
        #070914,
        #11152b,
        #081b2d
    );

    color:white;

    min-height:100vh;
}

.header{

    padding:25px;

    display:flex;

    justify-content:
    space-between;

    align-items:center;

    gap:15px;

    flex-wrap:wrap;

    border-bottom:
    1px solid
    rgba(255,255,255,.1);
}

.brand{

    font-size:24px;

    font-weight:bold;
}

.logout{

    text-decoration:none;

    color:white;

    padding:10px 16px;

    border-radius:10px;

    background:
    rgba(255,255,255,.1);
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

    background:
    rgba(255,255,255,.07);

    border:
    1px solid
    rgba(255,255,255,.12);
}

.stat-icon{

    font-size:28px;

    margin-bottom:10px;
}

.stat-number{

    font-size:30px;

    font-weight:bold;
}

.stat-name{

    opacity:.65;

    margin-top:5px;
}

h1{

    margin-bottom:20px;
}

.memory{

    padding:20px;

    margin-bottom:18px;

    border-radius:20px;

    background:
    rgba(255,255,255,.07);

    border:
    1px solid
    rgba(255,255,255,.12);
}

.memory-top{

    display:flex;

    justify-content:
    space-between;

    align-items:center;

    gap:15px;

    flex-wrap:wrap;
}

.memory-id{

    font-size:20px;

    font-weight:bold;
}

.badges{

    display:flex;

    gap:8px;

    flex-wrap:wrap;
}

.badge{

    padding:7px 10px;

    border-radius:20px;

    background:
    rgba(255,255,255,.1);

    font-size:13px;
}

.actions{

    display:flex;

    gap:10px;

    flex-wrap:wrap;

    margin-top:18px;
}

.actions a{

    text-decoration:none;

    color:white;

    padding:10px 14px;

    border-radius:10px;

    background:
    rgba(59,130,246,.35);
}

.actions a.delete{

    background:
    rgba(239,68,68,.35);
}

.empty{

    text-align:center;

    padding:40px;

    opacity:.6;
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

            <div class="stat-icon">
                💾
            </div>

            <div class="stat-number">
                {{ memories|length }}
            </div>

            <div class="stat-name">
                Total Memories
            </div>

        </div>


        <div class="stat">

            <div class="stat-icon">
                📸
            </div>

            <div class="stat-number">
                {{ total_photos }}
            </div>

            <div class="stat-name">
                Total Photos
            </div>

        </div>


        <div class="stat">

            <div class="stat-icon">
                🎥
            </div>

            <div class="stat-number">
                {{ total_videos }}
            </div>

            <div class="stat-name">
                Total Videos
            </div>

        </div>


        <div class="stat">

            <div class="stat-icon">
                🔗
            </div>

            <div class="stat-number">
                {{ memories|length }}
            </div>

            <div class="stat-name">
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

            <div class="memory-top">

                <div class="memory-id">
                    🆔 {{ memory.id }}
                </div>

                <div class="badges">

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

"""

    return render_template_string(
        html,
        memories=memories,
        total_photos=total_photos,
        total_videos=total_videos
    )


# =========================
# ADMIN DELETE
# =========================

@app.route(
    "/admin/delete/<memory_id>"
)
def admin_delete(memory_id):

    if session.get(
        "admin_logged_in"
    ) is not True:

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


# =========================
# ADMIN LOGOUT
# =========================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# =========================
# START SERVER
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
