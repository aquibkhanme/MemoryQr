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
import sqlite3
from datetime import datetime

from werkzeug.utils import secure_filename
from markupsafe import escape


app = Flask(__name__)

# ==================================================
# SECURITY / ADMIN SETTINGS
# ==================================================

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


# ==================================================
# FOLDERS
# ==================================================

UPLOAD_FOLDER = "memories"
QR_FOLDER = "static/qr"
DATABASE = "analytics.db"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)


# ==================================================
# DATABASE / ANALYTICS
# ==================================================

def init_database():

    conn = sqlite3.connect(DATABASE)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_date TEXT NOT NULL,
            memory_id TEXT,
            visit_type TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_database()


def record_visit(memory_id=None, visit_type="visitor"):

    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DATABASE)

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO visits
        (visit_date, memory_id, visit_type)
        VALUES (?, ?, ?)
        """,
        (
            today,
            memory_id,
            visit_type
        )
    )

    conn.commit()
    conn.close()


def get_analytics():

    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DATABASE)

    cursor = conn.cursor()

    # Total website visits
    cursor.execute("""
        SELECT COUNT(*)
        FROM visits
        WHERE visit_type = 'visitor'
    """)

    total_visits = cursor.fetchone()[0]


    # Today's website visits
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM visits
        WHERE visit_type = 'visitor'
        AND visit_date = ?
        """,
        (today,)
    )

    today_visits = cursor.fetchone()[0]


    # Total memory views
    cursor.execute("""
        SELECT COUNT(*)
        FROM visits
        WHERE visit_type = 'memory'
    """)

    total_memory_views = cursor.fetchone()[0]


    # Most viewed memory
    cursor.execute("""
        SELECT memory_id, COUNT(*) AS views
        FROM visits
        WHERE visit_type = 'memory'
        AND memory_id IS NOT NULL
        GROUP BY memory_id
        ORDER BY views DESC
        LIMIT 1
    """)

    most_viewed = cursor.fetchone()

    if most_viewed:

        most_viewed_memory = most_viewed[0]
        most_viewed_count = most_viewed[1]

    else:

        most_viewed_memory = "-"
        most_viewed_count = 0


    conn.close()


    return {
        "total_visits": total_visits,
        "today_visits": today_visits,
        "total_memory_views": total_memory_views,
        "most_viewed_memory": most_viewed_memory,
        "most_viewed_count": most_viewed_count
    }


def get_memory_views(memory_id):

    conn = sqlite3.connect(DATABASE)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM visits
        WHERE visit_type = 'memory'
        AND memory_id = ?
        """,
        (memory_id,)
    )

    views = cursor.fetchone()[0]

    conn.close()

    return views


# ==================================================
# MEMORY HELPERS
# ==================================================

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


# ==================================================
# HOME
# ==================================================

@app.route("/")
def home():

    record_visit(
        visit_type="visitor"
    )

    return send_from_directory(
        ".",
        "index.html"
    )


# ==================================================
# CREATE MEMORY
# ==================================================

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


# ==================================================
# UPLOAD
# ==================================================

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


# ==================================================
# SAVE MESSAGE
# ==================================================

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


# ==================================================
# MEMORY FILE
# ==================================================

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


# ==================================================
# MEMORY PAGE
# ==================================================

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


    # Record memory page view
    record_visit(
        memory_id=memory_id,
        visit_type="memory"
    )


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
        </
