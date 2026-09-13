from flask import Flask, request, jsonify, send_from_directory
import os
import qrcode
import uuid
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = "memories"
QR_FOLDER = "static/qr"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)


def get_memory_folder(memory_id):
    return os.path.join(UPLOAD_FOLDER, memory_id)


def get_message_file(memory_id):
    return os.path.join(get_memory_folder(memory_id), "message.json")


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/create-memory", methods=["POST"])
def create_memory():
    memory_id = str(uuid.uuid4())[:8]

    memory_folder = get_memory_folder(memory_id)
    os.makedirs(memory_folder, exist_ok=True)

    # Uses the address through which the website was opened.
    # This works on your phone/LAN instead of always forcing 127.0.0.1.
    base_url = request.host_url.rstrip("/")
    qr_url = f"{base_url}/memory/{memory_id}"

    qr = qrcode.make(qr_url)

    qr_path = os.path.join(QR_FOLDER, f"{memory_id}.png")
    qr.save(qr_path)

    return jsonify({
        "success": True,
        "memory_id": memory_id,
        "qr": f"/static/qr/{memory_id}.png",
        "memory_url": qr_url
    })


@app.route("/upload", methods=["POST"])
def upload():
    memory_id = request.form.get("memory_id")

    if not memory_id:
        return jsonify({
            "success": False,
            "error": "Memory ID missing"
        }), 400

    memory_folder = get_memory_folder(memory_id)
    os.makedirs(memory_folder, exist_ok=True)

    files = request.files.getlist("files")
    saved = []

    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)

            if not filename:
                continue

            file.save(os.path.join(memory_folder, filename))
            saved.append(filename)

    return jsonify({
        "success": True,
        "files": saved
    })


@app.route("/save-message", methods=["POST"])
def save_message():
    data = request.get_json(silent=True) or {}

    memory_id = data.get("memory_id")
    message = data.get("message", "").strip()

    if not memory_id:
        return jsonify({
            "success": False,
            "error": "Memory ID missing"
        }), 400

    memory_folder = get_memory_folder(memory_id)

    if not os.path.exists(memory_folder):
        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404

    with open(get_message_file(memory_id), "w", encoding="utf-8") as f:
        json.dump({
            "message": message
        }, f, ensure_ascii=False)

    return jsonify({
        "success": True
    })


@app.route("/memories/<memory_id>/<filename>")
def memory_file(memory_id, filename):
    folder = get_memory_folder(memory_id)

    if not os.path.exists(folder):
        return "Memory not found", 404

    return send_from_directory(folder, filename)


@app.route("/memory/<memory_id>")
def memory_page(memory_id):
    folder = get_memory_folder(memory_id)

    if not os.path.exists(folder):
        return "Memory not found", 404

    files = os.listdir(folder)

    photos = []
    videos = []

    for filename in files:
        lower = filename.lower()

        if lower.endswith((
            ".jpg", ".jpeg", ".png",
            ".webp", ".gif"
        )):
            photos.append(filename)

        elif lower.endswith((
            ".mp4", ".webm",
            ".mov", ".mkv"
        )):
            videos.append(filename)

    message = ""

    message_file = get_message_file(memory_id)

    if os.path.exists(message_file):
        try:
            with open(message_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                message = data.get("message", "")
        except:
            message = ""

    photo_html = ""

    for filename in photos:
        photo_html += f"""
        <div class="photo">
            <img src="/memories/{memory_id}/{filename}">
        </div>
        """

    video_html = ""

    for filename in videos:
        video_html += f"""
        <video controls>
            <source src="/memories/{memory_id}/{filename}">
        </video>
        """

    if not photo_html:
        photo_html = """
        <p class="empty">No photos added yet.</p>
        """

    if not video_html:
        video_html = """
        <p class="empty">No video added yet.</p>
        """

    if not message:
        message = "Your special message will appear here."

    return f"""
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width,initial-scale=1.0">

<title>Your Memory • Memory QR</title>

<style>

* {{
    box-sizing:border-box;
}}

body {{
    margin:0;
    padding:25px;
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
    padding:35px 15px;
}}

.logo {{
    color:#ff62c5;
    font-size:22px;
    font-weight:bold;
}}

h1 {{
    font-size:45px;
    margin:15px 0;
    background:
    linear-gradient(90deg,#ff72c8,#8b7aff);
    -webkit-background-clip:text;
    color:transparent;
}}

.memory-id {{
    color:#aaa;
    font-size:15px;
}}

.section {{
    margin:25px 0;
    padding:25px;
    border-radius:28px;
    background:#ffffff0d;
    border:1px solid #ffffff1c;
}}

h2 {{
    color:#ff82d2;
    margin-top:0;
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
    background:#151526;
}}

.photo img {{
    display:block;
    width:100%;
    height:220px;
    object-fit:cover;
}}

video {{
    width:100%;
    max-width:700px;
    display:block;
    margin:15px auto;
    border-radius:20px;
}}

.message {{
    padding:25px;
    border-radius:20px;
    background:
    linear-gradient(
        135deg,
        #522044,
        #34305d
    );
    line-height:1.8;
    font-size:18px;
    white-space:pre-wrap;
}}

.empty {{
    color:#999;
    text-align:center;
}}

.footer {{
    text-align:center;
    color:#777;
    padding:30px;
}}

@media(max-width:600px) {{

    body {{
        padding:15px;
    }}

    h1 {{
        font-size:35px;
    }}

    .section {{
        padding:20px;
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

<h1>Your Memories, Forever.</h1>

<div class="memory-id">
Memory ID: {memory_id}
</div>

</div>


<section class="section">

<h2>📸 Beautiful Moments</h2>

<div class="photos">
{photo_html}
</div>

</section>


<section class="section">

<h2>🎥 Memory Video</h2>

{video_html}

</section>


<section class="section">

<h2>💌 Special Message</h2>

<div class="message">
{message}
</div>

</section>


<div class="footer">
Memory QR • Made for memories that matter
</div>

</div>

</body>

</html>
"""


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8000,
        debug=False
    )
