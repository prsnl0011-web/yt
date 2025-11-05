import os
import json
import subprocess
import uuid
import threading
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# === Setup ===
app = Flask(__name__)
CORS(app)
API_KEY = os.environ.get("API_KEY", "420679f1-73e2-42a0-bbea-a10b99bd5fde")
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# === Background cleanup thread ===
def auto_cleanup(interval=300):
    while True:
        time.sleep(interval)
        for f in os.listdir(DOWNLOAD_DIR):
            try:
                os.remove(os.path.join(DOWNLOAD_DIR, f))
            except:
                pass
        print("🧹 Cleaned up old downloads")

threading.Thread(target=auto_cleanup, daemon=True).start()

# === Helper: run yt-dlp safely ===
def safe_download(url, kind):
    file_id = str(uuid.uuid4())[:8]
    out_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    try:
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
            "--retries", "3",
            "--fragment-retries", "3",
            "-f", fmt,
            "--merge-output-format", ext,
            "-o", out_path,
            url,
        ]

        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip() or out.stdout.strip())

        # Find the actual file name yt-dlp saved
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id):
                return os.path.join(DOWNLOAD_DIR, f)

        raise RuntimeError("File not created")

    except Exception as e:
        raise RuntimeError(str(e))

# === Routes ===
@app.route("/")
def home():
    return jsonify({"status": "ok", "message": "YouTube Downloader Backend running."})

@app.route("/api/info", methods=["POST"])
def api_info():
    try:
        data = request.get_json(force=True)
        if data.get("api_key") != API_KEY:
            return jsonify({"status": "error", "error": "Invalid API key"}), 403

        url = data.get("url")
        if not url:
            return jsonify({"status": "error", "error": "Missing URL"}), 400

        cmd = [
            "yt-dlp",
            "-j",
            "--cookies", "cookies.txt",
            "--extractor-args", "youtubetab:skip=authcheck",
            "--retries", "3",
            "--fragment-retries", "3",
            url,
        ]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if out.returncode != 0:
            return jsonify({"status": "error", "error": out.stderr.strip() or "yt-dlp failed"}), 500

        info = json.loads(out.stdout)
        title = info.get("title")
        thumb = info.get("thumbnail")

        return jsonify({
            "status": "ok",
            "title": title,
            "thumbnail": thumb,
            "url": url
        })

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/download", methods=["POST"])
def api_download():
    try:
        data = request.get_json(force=True)
        if data.get("api_key") != API_KEY:
            return jsonify({"status": "error", "error": "Invalid API key"}), 403

        url = data.get("url")
        kind = data.get("type", "mp4")

        file_path = safe_download(url, kind)
        file_name = os.path.basename(file_path)
        file_url = f"{request.url_root}downloads/{file_name}"
        return jsonify({"status": "ok", "url": file_url})

    except Exception as e:
        print(f"❌ Download error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/downloads/<path:filename>")
def serve_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("\n✅ Server ready!")
    print(f"API Key: {API_KEY}")
    print("Endpoints:")
    print("  info: http://localhost:5000/api/info")
    print("  download: http://localhost:5000/api/download\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
