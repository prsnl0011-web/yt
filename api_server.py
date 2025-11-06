import os
import subprocess
import json
import re
import time
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# === CONFIG ===
API_KEY = os.getenv("API_KEY", "420679f1-73e2-42a0-bbea-a10b99bd5fde")
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)

# === AUTO CLEANUP (delete files older than 5 minutes) ===
def auto_cleanup():
    while True:
        now = time.time()
        for f in os.listdir(DOWNLOAD_DIR):
            path = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(path) and now - os.path.getmtime(path) > 300:
                os.remove(path)
        time.sleep(300)

threading.Thread(target=auto_cleanup, daemon=True).start()


# === CLEAN TITLE FOR SAFE FILENAME ===
def clean_filename(name: str) -> str:
    # Remove unsafe characters
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    # Trim and limit length
    name = name.strip()[:180]
    return name or "video"


# === HEALTH CHECK ===
@app.route("/api/health")
def health():
    return jsonify({"status": "ok"}), 200


# === GET VIDEO INFO ===
@app.route("/api/info", methods=["POST"])
def api_info():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403

    data = request.get_json() or {}
    url = data.get("url")

    if not url:
        return jsonify({"error": "Missing URL"}), 400

    try:
        cmd = [
            "yt-dlp",
            "--no-warnings",
            "--skip-download",
            "--no-check-certificates",
            "--geo-bypass",
            "--extractor-args", "youtubetab:skip=authcheck",
            "--cookies", "cookies.txt",
            "-j", url,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        info = json.loads(result.stdout.strip().split("\n")[0])

        title = info.get("title", "Unknown Title")
        thumbnail = info.get("thumbnail", "")

        response = {
            "title": title,
            "thumbnail": thumbnail,
            "qualities": [
                {
                    "label": "🎥 Download Best Quality (MP4)",
                    "type": "mp4",
                    "url": url
                }
            ]
        }
        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# === DOWNLOAD BEST QUALITY VIDEO (WITH AUDIO) ===
@app.route("/api/download", methods=["POST"])
def api_download():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403

    data = request.get_json() or {}
    url = data.get("url")

    if not url:
        return jsonify({"error": "Missing URL"}), 400

    try:
        # Get the video title first
        info_cmd = [
            "yt-dlp",
            "--no-warnings",
            "--skip-download",
            "--no-check-certificates",
            "--cookies", "cookies.txt",
            "-j", url,
        ]
        info_proc = subprocess.run(info_cmd, capture_output=True, text=True, timeout=60)
        info = json.loads(info_proc.stdout.strip().split("\n")[0])
        title = clean_filename(info.get("title", "video"))
        filename = f"{title}.mp4"
        output_path = os.path.join(DOWNLOAD_DIR, filename)

        # Download the best quality with audio
        cmd = [
            "yt-dlp",
            "--cookies", "cookies.txt",
            "--extractor-args", "youtubetab:skip=authcheck",
            "-f", "bv*+ba/best",
            "--merge-output-format", "mp4",
            "-o", output_path,
            url,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())

        if not os.path.exists(output_path):
            raise FileNotFoundError("Download failed or file not found")

        return jsonify({
            "download_url": f"/downloads/{filename}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# === SERVE DOWNLOADED FILES ===
@app.route("/downloads/<path:filename>")
def serve_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


# === MAIN APP ===
if __name__ == "__main__":
    print("\n✅ Server ready!")
    print(f"API Key: {API_KEY}")
    print(f"  info: http://localhost:5000/api/info")
    print(f"  download: http://localhost:5000/api/download\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
