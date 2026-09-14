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

# ==================================================
# SECURITY
# ==================================================

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


# ==================================================
# FOLDERS
# ==================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

MEMORIES_DIR = os.path.join(
    BASE_DIR,
    "memories"
)

QR_DIR = os.path.join(
    BASE_DIR,
    "static",
    "qr"
)

os.makedirs(
    MEMORIES_DIR,
    exist_ok=True
)

os.makedirs(
    QR_DIR,
    exist_ok=True
)


# ==================================================
# MEMORY FUNCTIONS
# ==================================================

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

    os.makedirs(
        folder,
        exist_ok=True
    )

    return folder


# ==================================================
# HOME
# ==================================================

@app.route("/")
def home():

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# ==================================================
# CREATE MEMORY + QR
# ==================================================

@app.route(
    "/create-memory",
    methods=["POST"]
)
def create_memory():

    try:

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

        qr = qrcode.make(
            memory_url
        )

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

        print(
            "CREATE MEMORY ERROR:",
            repr(e)
        )

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================================================
# UPLOAD FILES
# ==================================================

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

            if not file:
                continue

            if not file.filename:
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

            file.save(
                save_path
            )

            uploaded.append(
                filename
            )

        return jsonify({
            "success": True,
            "files": uploaded
        })

    except Exception as e:

        print(
            "UPLOAD ERROR:",
            repr(e)
        )

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================================================
# SAVE PERSONAL DIARY
# ==================================================

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

        if not os.path.exists(folder):

            return jsonify({
                "success": False,
                "error": "Memory not found"
            }), 404

        data = request.get_json(
            silent=True
        )

        if not isinstance(data, dict):

            data = {}

        message = data.get(
            "message",
            ""
        )

        if not isinstance(
            message,
            str
        ):

            message = str(message)

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

    except Exception as e:

        print(
            "SAVE MESSAGE ERROR:",
            repr(e)
        )

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================================================
# VIEW MEMORY
# ==================================================

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

    for filename in os.listdir(
        folder
    ):

        if filename == "message.txt":
            continue

        path = os.path.join(
            folder,
