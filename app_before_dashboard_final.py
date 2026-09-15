from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, render_template_string
import os
import json
import uuid
import shutil
import qrcode
from werkzeug.utils import secure_filename
from markupsafe import escape

try:
    from analytics import init_db, track_request, get_stats
    ANALYTICS_ENABLED = True
except Exception:
    ANALYTICS_ENABLED = False

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
    "memoryqr-change-this-secret-key"
)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "MemoryQR@123")

UPLOAD_FOLDER = "memories"
QR_FOLDER = os.path.join("static", "qr")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

ALLOWED_IMAGES = {
    "jpg", "jpeg", "png", "webp", "gif", "bmp", "heic", "heif"
}

ALLOWED_VIDEOS = {
    "mp4", "mov", "avi", "mkv", "webm", "3gp", "m4v"
}


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


def is_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGES


def is_video(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_VIDEOS


def memory_folder(memory_id):
    return os.path.join(UPLOAD_FOLDER, memory_id)


def memory_exists(memory_id):
    return os.path.isdir(memory_folder(memory_id))


def get_memory_files(memory_id):
    folder = memory_folder(memory_id)

    if not os.path.isdir(folder):
        return [], []

    photos = []
    videos = []

    for filename in sorted(os.listdir(folder)):
        path = os.path.join(folder, filename)

        if not os.path.isfile(path):
            continue

        if is_image(filename):
            photos.append(filename)

        elif is_video(filename):
            videos.append(filename)

    return photos, videos


@app.route("/")
def home():
    if os.path.exists("index.html"):
        return send_from_directory(".", "index.html")

    return "Memory QR"


@app.route("/create-memory", methods=["POST"])
def create_memory():
    memory_id = uuid.uuid4().hex[:12]

    folder = memory_folder(memory_id)
    os.makedirs(folder, exist_ok=True)

    public_url = url_for(
        "view_memory",
        memory_id=memory_id,
        _external=True
    )

    qr_filename = f"{memory_id}.png"
    qr_path = os.path.join(QR_FOLDER, qr_filename)

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4
    )

    qr.add_data(public_url)
    qr.make(fit=True)

    qr_img = qr.make_image()
    qr_img.save(qr_path)

    return jsonify({
        "success": True,
        "memory_id": memory_id,
        "memory_url": public_url,
        "qr": url_for(
            "static",
            filename=f"qr/{qr_filename}"
        ),
        "qr_url": url_for(
            "static",
            filename=f"qr/{qr_filename}"
        )
    })


@app.route("/upload", methods=["POST"])
def upload_files():
    memory_id = request.form.get("memory_id", "").strip()

    if not memory_id:
        return jsonify({
            "success": False,
            "error": "Memory ID missing"
        }), 400

    if not memory_exists(memory_id):
        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404

    files = request.files.getlist("file")

    if not files:
        files = request.files.getlist("files")

    uploaded = []

    folder = memory_folder(memory_id)

    for file in files:

        if not file or not file.filename:
            continue

        original_name = secure_filename(file.filename)

        if not original_name:
            continue

        extension = ""
        if "." in original_name:
            extension = original_name.rsplit(".", 1)[1].lower()

        if extension not in ALLOWED_IMAGES and extension not in ALLOWED_VIDEOS:
            continue

        unique_name = f"{uuid.uuid4().hex[:10]}_{original_name}"

        save_path = os.path.join(folder, unique_name)

        file.save(save_path)

        uploaded.append(unique_name)

    return jsonify({
        "success": True,
        "uploaded": uploaded,
        "count": len(uploaded)
    })


@app.route("/save-message", methods=["POST"])
def save_message():

    data = request.get_json(silent=True)

    if data is None:
        data = request.form

    memory_id = str(data.get("memory_id", "")).strip()
    message = str(data.get("message", ""))

    if not memory_id:
        return jsonify({
            "success": False,
            "error": "Memory ID missing"
        }), 400

    if not memory_exists(memory_id):
        return jsonify({
            "success": False,
            "error": "Memory not found"
        }), 404

    with open(
        os.path.join(memory_folder(memory_id), "message.json"),
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
        "success": True
    })


@app.route("/download-qr/<memory_id>")
def download_qr(memory_id):

    filename = f"{memory_id}.png"

    path = os.path.join(QR_FOLDER, filename)

    if not os.path.exists(path):
        return "QR not found", 404

    return send_from_directory(
        QR_FOLDER,
        filename,
        as_attachment=True
    )


@app.route("/memories/<memory_id>/<filename>")
def memory_file(memory_id, filename):

    if not memory_exists(memory_id):
        return "Memory not found", 404

    return send_from_directory(
        memory_folder(memory_id),
        filename
    )


@app.route("/memory/<memory_id>")
def view_memory(memory_id):

    if not memory_exists(memory_id):
        return """
        <html>
        <body style="background:#080b12;color:white;font-family:Arial;text-align:center;padding:60px">
        <h1>Memory Not Found</h1>
        <p>This memory may have been deleted or is no longer available.</p>
        </body>
        </html>
        """, 404

    photos, videos = get_memory_files(memory_id)

    photo_urls = [
        url_for(
            "memory_file",
            memory_id=memory_id,
            filename=filename
        )
        for filename in photos
    ]

    video_urls = [
        url_for(
            "memory_file",
            memory_id=memory_id,
            filename=filename
        )
        for filename in videos
    ]

    message = ""

    message_path = os.path.join(
        memory_folder(memory_id),
        "message.json"
    )

    if os.path.exists(message_path):

        try:
            with open(
                message_path,
                "r",
                encoding="utf-8"
            ) as f:
                message_data = json.load(f)

            message = message_data.get(
                "message",
                ""
            )

        except Exception:
            message = ""

    template = """
<!DOCTYPE html>
<html lang="en">
<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1.0,user-scalable=no"
>

<meta
name="robots"
content="noindex,nofollow,noarchive"
>

<title>Memory QR ❤️</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
font-family:Arial,sans-serif;
background:
radial-gradient(circle at top,#18213d 0%,#090b14 45%,#05060a 100%);
color:white;
min-height:100vh;
}

.container{
width:min(1100px,94%);
margin:auto;
padding:30px 0 50px;
}

.header{
text-align:center;
margin-bottom:35px;
}

.logo{
font-size:32px;
font-weight:900;
letter-spacing:1px;
}

.subtitle{
color:#aab3c8;
margin-top:8px;
}

.section{
background:rgba(255,255,255,.055);
border:1px solid rgba(255,255,255,.09);
border-radius:24px;
padding:22px;
margin-bottom:25px;
box-shadow:0 15px 50px rgba(0,0,0,.2);
}

.section h2{
margin-top:0;
}

.gallery{
display:grid;
grid-template-columns:repeat(auto-fill,minmax(170px,1fr));
gap:12px;
align-items:start;
}

.photo{
overflow:hidden;
border-radius:16px;
background:#111827;
cursor:pointer;
}

.photo img{
display:block;
width:100%;
height:auto;
max-height:500px;
object-fit:contain;
transition:.25s;
}

.photo img:hover{
transform:scale(1.02);
}

.video-grid{
display:grid;
grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
gap:15px;
}

.video-box{
background:#0b0f19;
border-radius:16px;
overflow:hidden;
}

.video-box video{
width:100%;
display:block;
max-height:550px;
}

.message{
font-size:18px;
line-height:1.7;
white-space:pre-wrap;
color:#e8ecf5;
}

.empty{
color:#8e98ae;
text-align:center;
padding:20px;
}

.footer{
text-align:center;
color:#8e98ae;
padding-top:25px;
font-size:14px;
}

/* VIEWER */

.viewer{
position:fixed;
inset:0;
background:rgba(0,0,0,.96);
z-index:9999;
display:none;
align-items:center;
justify-content:center;
overflow:hidden;
touch-action:none;
}

.viewer.show{
display:flex;
}

.viewer img{
max-width:94vw;
max-height:90vh;
object-fit:contain;
user-select:none;
-webkit-user-drag:none;
transform-origin:center center;
transition:transform .18s ease;
}

.viewer-top{
position:absolute;
top:15px;
left:15px;
right:15px;
display:flex;
justify-content:space-between;
z-index:3;
}

.viewer-btn{
width:45px;
height:45px;
border:none;
border-radius:50%;
background:rgba(255,255,255,.12);
color:white;
font-size:23px;
cursor:pointer;
backdrop-filter:blur(10px);
}

.viewer-controls{
position:absolute;
bottom:22px;
left:50%;
transform:translateX(-50%);
display:flex;
gap:10px;
z-index:3;
}

.viewer-count{
position:absolute;
bottom:25px;
right:20px;
color:white;
background:rgba(0,0,0,.5);
padding:8px 13px;
border-radius:20px;
font-size:13px;
}

@media(max-width:600px){

.container{
width:94%;
padding-top:20px;
}

.gallery{
grid-template-columns:repeat(2,1fr);
}

.section{
padding:16px;
border-radius:19px;
}

.logo{
font-size:27px;
}

.viewer img{
max-width:96vw;
max-height:84vh;
}

}

</style>

</head>

<body>

<div class="container">

<div class="header">

<div class="logo">
Memory QR ❤️
</div>

<div class="subtitle">
A special memory, preserved forever.
</div>

</div>


{% if photos %}

<div class="section">

<h2>📸 Photos</h2>

<div class="gallery">

{% for photo in photos %}

<div class="photo"
onclick="openPhoto({{ loop.index0 }})">

<img
src="{{ url_for('memory_file',memory_id=memory_id,filename=photo) }}"
alt="Memory Photo"
loading="lazy"
>

</div>

{% endfor %}

</div>

</div>

{% endif %}


{% if videos %}

<div class="section">

<h2>🎥 Videos</h2>

<div class="video-grid">

{% for video in videos %}

<div class="video-box">

<video
controls
playsinline
preload="metadata"
src="{{ url_for('memory_file',memory_id=memory_id,filename=video) }}"
></video>

</div>

{% endfor %}

</div>

</div>

{% endif %}


{% if message %}

<div class="section">

<h2>💌 Message</h2>

<div class="message">
{{ message }}
</div>

</div>

{% endif %}


{% if not photos and not videos and not message %}

<div class="section empty">

This memory is waiting for its special moments ❤️

</div>

{% endif %}


<div class="footer">
This site is made by Aquib Khan ❤️
</div>

</div>


<!-- PHOTO VIEWER -->

<div
class="viewer"
id="viewer"
onclick="viewerBackground(event)"
>

<div class="viewer-top">

<button
class="viewer-btn"
onclick="closeViewer(event)"
>
✕
</button>

</div>


<button
class="viewer-btn"
style="position:absolute;left:15px;top:50%;transform:translateY(-50%);z-index:3"
onclick="previousPhoto(event)"
>
‹
</button>


<img
id="viewerImage"
src=""
alt="Full Memory"
>


<button
class="viewer-btn"
style="position:absolute;right:15px;top:50%;transform:translateY(-50%);z-index:3"
onclick="nextPhoto(event)"
>
›
</button>


<div class="viewer-controls">

<button
class="viewer-btn"
onclick="zoomOut(event)"
>
−
</button>

<button
class="viewer-btn"
onclick="resetZoom(event)"
>
⟳
</button>

<button
class="viewer-btn"
onclick="zoomIn(event)"
>
+
</button>

</div>


<div
class="viewer-count"
id="viewerCount"
>
</div>

</div>


<script>

const photoSources = {{ photo_urls_json | safe }};

let currentPhoto = 0;
let zoomLevel = 1;

const viewer =
document.getElementById("viewer");

const viewerImage =
document.getElementById("viewerImage");

const viewerCount =
document.getElementById("viewerCount");


function updateViewer(){

if(!photoSources.length){
return;
}

viewerImage.src =
photoSources[currentPhoto];

viewerCount.textContent =
(currentPhoto + 1) +
" / " +
photoSources.length;

resetZoom();

}


function openPhoto(index){

currentPhoto = index;

viewer.classList.add("show");

document.body.style.overflow="hidden";

updateViewer();

}


function closeViewer(event){

if(event){
event.stopPropagation();
}

viewer.classList.remove("show");

document.body.style.overflow="";

}


function viewerBackground(event){

if(event.target === viewer){
closeViewer();
}

}


function previousPhoto(event){

if(event){
event.stopPropagation();
}

if(!photoSources.length){
return;
}

currentPhoto--;

if(currentPhoto < 0){
currentPhoto =
photoSources.length - 1;
}

updateViewer();

}


function nextPhoto(event){

if(event){
event.stopPropagation();
}

if(!photoSources.length){
return;
}

currentPhoto++;

if(currentPhoto >= photoSources.length){
currentPhoto = 0;
}

updateViewer();

}


function applyZoom(){

viewerImage.style.transform =
"scale(" + zoomLevel + ")";

}


function zoomIn(event){

if(event){
event.stopPropagation();
}

zoomLevel =
Math.min(zoomLevel + .5, 4);

applyZoom();

}


function zoomOut(event){

if(event){
event.stopPropagation();
}

zoomLevel =
Math.max(zoomLevel - .5, 1);

applyZoom();

}


function resetZoom(event){

if(event){
event.stopPropagation();
}

zoomLevel = 1;

applyZoom();

}


document.addEventListener(
"keydown",
function(e){

if(!viewer.classList.contains("show")){
return;
}

if(e.key === "Escape"){
closeViewer();
}

if(e.key === "ArrowLeft"){
previousPhoto();
}

if(e.key === "ArrowRight"){
nextPhoto();
}

if(e.key === "+" || e.key === "="){
zoomIn();
}

if(e.key === "-"){
zoomOut();
}

}
);


/* SWIPE + PINCH */

let touchStartX = 0;
let touchStartY = 0;
let initialDistance = 0;
let initialZoom = 1;
let lastTap = 0;


function distance(t1,t2){

const dx =
t1.clientX - t2.clientX;

const dy =
t1.clientY - t2.clientY;

return Math.sqrt(
dx*dx + dy*dy
);

}


viewerImage.addEventListener(
"touchstart",
function(e){

if(e.touches.length === 1){

touchStartX =
e.touches[0].clientX;

touchStartY =
e.touches[0].clientY;

const now =
Date.now();

if(now-lastTap < 300){

if(zoomLevel === 1){
zoomLevel = 2.5;
}else{
zoomLevel = 1;
}

applyZoom();

}

lastTap = now;

}


if(e.touches.length === 2){

initialDistance =
distance(
e.touches[0],
e.touches[1]
);

initialZoom = zoomLevel;

}

},
{passive:false}
);


viewerImage.addEventListener(
"touchmove",
function(e){

if(e.touches.length === 2){

e.preventDefault();

const newDistance =
distance(
e.touches[0],
e.touches[1]
);

if(initialDistance > 0){

zoomLevel =
initialZoom *
(newDistance / initialDistance);

zoomLevel =
Math.max(
1,
Math.min(zoomLevel,4)
);

applyZoom();

}

}

},
{passive:false}
);


viewerImage.addEventListener(
"touchend",
function(e){

if(e.changedTouches.length !== 1){
return;
}

if(zoomLevel > 1){
return;
}

const endX =
e.changedTouches[0].clientX;

const endY =
e.changedTouches[0].clientY;

const diffX =
endX-touchStartX;

const diffY =
endY-touchStartY;

if(
Math.abs(diffX) > 60 &&
Math.abs(diffX) > Math.abs(diffY)
){

if(diffX < 0){
nextPhoto();
}else{
previousPhoto();
}

}

}
);


</script>

</body>
</html>
"""

    return render_template_string(
        template,
        memory_id=memory_id,
        photos=photos,
        videos=videos,
        message=message,
        photo_urls_json=json.dumps(photo_urls)
    )


# =========================
# ADMIN LOGIN
# =========================

@app.route("/admin/login", methods=["GET", "POST"])
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


ADMIN_LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1"
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
radial-gradient(circle at top,#1b2748,#070910 65%);
color:white;
}

.login{
width:min(420px,92%);
background:rgba(255,255,255,.07);
border:1px solid rgba(255,255,255,.1);
border-radius:25px;
padding:30px;
box-shadow:0 25px 70px rgba(0,0,0,.4);
}

.logo{
text-align:center;
font-size:30px;
font-weight:900;
margin-bottom:8px;
}

.sub{
text-align:center;
color:#9da8bd;
margin-bottom:28px;
}

label{
display:block;
margin:15px 0 7px;
color:#cbd3e3;
}

input{
width:100%;
padding:14px;
border-radius:12px;
border:1px solid #30384c;
background:#0c111c;
color:white;
outline:none;
}

button{
width:100%;
margin-top:20px;
padding:14px;
border:0;
border-radius:12px;
background:linear-gradient(135deg,#7c5cff,#b76cff);
color:white;
font-size:16px;
font-weight:800;
cursor:pointer;
}

.error{
background:rgba(255,70,70,.12);
border:1px solid rgba(255,70,70,.25);
color:#ffb5b5;
padding:12px;
border-radius:12px;
margin-bottom:15px;
text-align:center;
}

</style>

</head>

<body>

<div class="login">

<div class="logo">
Memory QR ❤️
</div>

<div class="sub">
Private Admin Dashboard
</div>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}

<form method="POST">

<label>Username</label>

<input
type="text"
name="username"
autocomplete="username"
required
>

<label>Password</label>

<input
type="password"
name="password"
autocomplete="current-password"
required
>

<button type="submit">
Login to Dashboard
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

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    memories = []

    if os.path.isdir(UPLOAD_FOLDER):

        for memory_id in sorted(
            os.listdir(UPLOAD_FOLDER),
            reverse=True
        ):

            folder = memory_folder(memory_id)

            if not os.path.isdir(folder):
                continue

            photos, videos = get_memory_files(
                memory_id
            )

            message_exists = os.path.exists(
                os.path.join(
                    folder,
                    "message.json"
                )
            )

            memory_url = url_for(
                "view_memory",
                memory_id=memory_id,
                _external=True
            )

            qr_url = url_for(
                "static",
                filename=f"qr/{memory_id}.png"
            )

            memories.append({
                "id": memory_id,
                "photos": len(photos),
                "videos": len(videos),
                "message": message_exists,
                "url": memory_url,
                "qr": qr_url
            })

    total_memories = len(memories)
    total_photos = sum(
        x["photos"] for x in memories
    )
    total_videos = sum(
        x["videos"] for x in memories
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

    return render_template_string(
        ADMIN_DASHBOARD_HTML,
        memories=memories,
        total_memories=total_memories,
        total_photos=total_photos,
        total_videos=total_videos,
        stats=stats
    )


ADMIN_DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1"
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
radial-gradient(circle at top,#18233f,#060810 55%);
color:white;
}

.container{
width:min(1250px,94%);
margin:auto;
padding:25px 0 50px;
}

.topbar{
display:flex;
justify-content:space-between;
align-items:center;
gap:15px;
margin-bottom:25px;
}

.logo{
font-size:27px;
font-weight:900;
}

.logout{
text-decoration:none;
color:white;
background:rgba(255,255,255,.08);
border:1px solid rgba(255,255,255,.12);
padding:10px 15px;
border-radius:11px;
}

.stats{
display:grid;
grid-template-columns:repeat(4,1fr);
gap:15px;
margin-bottom:25px;
}

.stat{
background:rgba(255,255,255,.055);
border:1px solid rgba(255,255,255,.08);
border-radius:20px;
padding:20px;
}

.stat-title{
color:#9ba6bb;
font-size:13px;
}

.stat-number{
font-size:30px;
font-weight:900;
margin-top:7px;
}

.analytics{
display:grid;
grid-template-columns:repeat(4,1fr);
gap:15px;
margin-bottom:30px;
}

.card{
background:rgba(255,255,255,.055);
border:1px solid rgba(255,255,255,.08);
border-radius:20px;
padding:18px;
}

.card-title{
color:#9ba6bb;
font-size:13px;
}

.card-number{
font-size:24px;
font-weight:900;
margin-top:6px;
}

.memory{
background:rgba(255,255,255,.055);
border:1px solid rgba(255,255,255,.08);
border-radius:22px;
padding:18px;
margin-bottom:15px;
}

.memory-head{
display:flex;
justify-content:space-between;
gap:15px;
align-items:center;
}

.memory-id{
font-size:18px;
font-weight:900;
}

.badges{
display:flex;
gap:7px;
flex-wrap:wrap;
margin-top:10px;
}

.badge{
padding:6px 9px;
border-radius:20px;
background:rgba(255,255,255,.08);
color:#c9d1e1;
font-size:12px;
}

.actions{
display:flex;
gap:8px;
flex-wrap:wrap;
margin-top:16px;
}

.action{
display:inline-block;
text-decoration:none;
border:0;
padding:10px 13px;
border-radius:10px;
font-weight:700;
font-size:13px;
cursor:pointer;
background:#20283b;
color:white;
}

.open{
background:linear-gradient(135deg,#7658ff,#a85cff);
}

.qr{
background:#182e2a;
}

.delete{
background:#3a1d25;
color:#ffb7c0;
}

.qr-box{
margin-top:15px;
display:none;
padding:15px;
background:#080b12;
border-radius:15px;
text-align:center;
}

.qr-box img{
width:180px;
max-width:100%;
background:white;
padding:8px;
border-radius:12px;
}

.link-box{
margin-top:12px;
padding:11px;
border-radius:10px;
background:#090d16;
word-break:break-all;
font-size:12px;
color:#aeb9cf;
}

@media(max-width:800px){

.stats,
.analytics{
grid-template-columns:repeat(2,1fr);
}

.memory-head{
display:block;
}

}

@media(max-width:500px){

.stats,
.analytics{
grid-template-columns:1fr 1fr;
gap:9px;
}

.stat,
.card{
padding:14px;
}

.stat-number{
font-size:23px;
}

}

</style>

</head>

<body>

<div class="container">

<div class="topbar">

<div class="logo">
Memory QR ❤️ Admin
</div>

<a
class="logout"
href="{{ url_for('admin_logout') }}"
>
Logout
</a>

</div>


<div class="stats">

<div class="stat">
<div class="stat-title">Total Memories</div>
<div class="stat-number">
{{ total_memories }}
</div>
</div>

<div class="stat">
<div class="stat-title">Total Photos</div>
<div class="stat-number">
{{ total_photos }}
</div>
</div>

<div class="stat">
<div class="stat-title">Total Videos</div>
<div class="stat-number">
{{ total_videos }}
</div>
</div>

<div class="stat">
<div class="stat-title">Memory Views</div>
<div class="stat-number">
{{ stats.memory_views }}
</div>
</div>

</div>


<h2>📊 Analytics</h2>

<div class="analytics">

<div class="card">
<div class="card-title">All Visits</div>
<div class="card-number">
{{ stats.total_visits }}
</div>
</div>

<div class="card">
<div class="card-title">Today</div>
<div class="card-number">
{{ stats.today_visits }}
</div>
</div>

<div class="card">
<div class="card-title">Last 7 Days</div>
<div class="card-number">
{{ stats.seven_day_visits }}
</div>
</div>

<div class="card">
<div class="card-title">Public Memory Views</div>
<div class="card-number">
{{ stats.memory_views }}
</div>
</div>

</div>


<h2>🗂️ All Memories</h2>

{% if memories %}

{% for memory in memories %}

<div class="memory">

<div class="memory-head">

<div>

<div class="memory-id">
Memory #{{ memory.id }}
</div>

<div class="badges">

<span class="badge">
📸 {{ memory.photos }} Photos
</span>

<span class="badge">
🎥 {{ memory.videos }} Videos
</span>

{% if memory.message %}
<span class="badge">
💌 Message
</span>
{% endif %}

</div>

</div>

</div>


<div class="link-box">
{{ memory.url }}
</div>


<div class="actions">

<a
class="action open"
href="{{ memory.url }}"
target="_blank"
>
🔗 Open Memory
</a>

<button
class="action qr"
onclick="toggleQR('{{ memory.id }}')"
>
📱 View QR
</button>

<a
class="action"
href="{{ url_for('download_qr',memory_id=memory.id) }}"
>
⬇️ Download QR
</a>

<form
method="POST"
action="{{ url_for('admin_delete',memory_id=memory.id) }}"
onsubmit="return confirm('Delete this memory permanently?')"
style="display:inline"
>

<button
class="action delete"
type="submit"
>
🗑️ Delete
</button>

</form>

</div>


<div
class="qr-box"
id="qr-{{ memory.id }}"
>

<img
src="{{ memory.qr }}"
alt="QR Code"
>

<div style="margin-top:10px;color:#aab3c5;font-size:13px">
Scan this QR to open the memory
</div>

</div>

</div>

{% endfor %}

{% else %}

<div class="memory">
No memories created yet.
</div>

{% endif %}


<div
style="text-align:center;color:#778198;margin-top:35px"
>
This site is made by Aquib Khan ❤️
</div>

</div>


<script>

function toggleQR(id){

const box =
document.getElementById("qr-"+id);

if(box.style.display === "block"){
box.style.display = "none";
}else{
box.style.display = "block";
}

}

</script>

</body>
</html>
"""


@app.route("/admin/delete/<memory_id>", methods=["POST"])
def admin_delete(memory_id):

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )

    folder = memory_folder(memory_id)

    if os.path.isdir(folder):
        shutil.rmtree(folder)

    qr_path = os.path.join(
        QR_FOLDER,
        f"{memory_id}.png"
    )

    if os.path.exists(qr_path):
        os.remove(qr_path)

    return redirect(
        url_for("admin_dashboard")
    )


@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


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
