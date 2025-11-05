import os
import json
import subprocess
import uuid
import threading
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 🔐 API key (use same one your frontend has)
API_KEY = os.environ.get("API_KEY", "420679f1-73e2-42a0-bbea-a10b99bd5fde")

# Folder for temporary downloads
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# 🧹 Auto cleanup every 5 minutes
def cleanup(interval=300):
    while True:
        time.sleep(interval)
        for f in os.listdir(DOWNLOAD_DIR):
            try:
                os.remove(os.path.join(DOWNLOAD_DIR, f))
            except:
                pass
        print("🧹 Cleanup done.")


threading.Thread(target=cleanup, daemon=True).start()


@app.route("/")
def home():
    return jsonify({
        "message": "YouTube Downloader API active ✅",
        "info": "/api/info",
        "download": "/api/download"
    })


@app.route("/api/info", methods=["POST"])
def get_info():
    try:
        data = request.get_json() or {}
        # ✅ Accept API key from header or body
        client_key = request.headers.get("X-API-Key") or data.get("api_key")
        if client_key != API_KEY:
            return jsonify({"error": "Invalid API key"}), 403

        url = data.get("url")
        if not url:
            return jsonify({"error": "Missing URL"}), 400

        # Fetch video metadata
        cmd = [
            "yt-dlp",
            "-j",
            "--cookies", "cookies.txt",
            "--extractor-args", "youtubetab:skip=authcheck",
            "--no-playlist",
            "--retries", "3",
            url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)

        info = json.loads(result.stdout)
        title = info.get("title", "Unknown Title")
        thumbnail = info.get("thumbnail")

        # Return only top 3 quality options
        qualities = [
            {"type": "mp4", "label": "🎥 Best MP4 (Video + Audio)", "url": url},
            {"type": "mp3", "label": "🎵 Best MP3 (Audio Only)", "url": url},
            {"type": "p3", "label": "🔊 320kbps Audio (High Quality)", "url": url},
        ]

        return jsonify({
            "title": title,
            "thumbnail": thumbnail,
            "qualities": qualities
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download", methods=["POST"])
def download():
    try:
        data = request.get_json() or {}
        # ✅ Accept API key from header or body
        client_key = request.headers.get("X-API-Key") or data.get("api_key")
        if client_key != API_KEY:
            return jsonify({"error": "Invalid API key"}), 403

        url = data.get("url")
        kind = data.get("type", "mp4")

        file_id = str(uuid.uuid4())[:8]
        out_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")

        if kind == "mp4":
            fmt = "bv*+ba/b"
            ext = "mp4"
        else:
            fmt = "bestaudio/b"
            ext = "mp3"

        cmd = [
            "yt-dlp",
            "--cookies", "cookies.txt",
            "--extractor-args", "youtubetab:skip=authcheck",
            "-f", fmt,
            "--merge-output-format", ext,
            "-o", out_path,
            url,
        ]

        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip() or out.stdout.strip())

        # Find downloaded file
        file_name = next((f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(file_id)), None)
        if not file_name:
            raise RuntimeError("File not found after download")

        return jsonify({
            "download_url": f"/downloads/{file_name}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/downloads/<path:filename>")
def serve_download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    print(f"✅ Backend running | API Key: {API_KEY}")
    app.run(host="0.0.0.0", port=5000, debug=True)
