import os
import json
import uuid
import subprocess
import threading
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("API_KEY", "420679f1-73e2-42a0-bbea-a10b99bd5fde")
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- automatic cleanup every 5 min ---
def auto_clean():
    while True:
        now = time.time()
        for f in os.listdir(DOWNLOAD_DIR):
            path = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(path) and now - os.path.getmtime(path) > 300:
                os.remove(path)
        time.sleep(300)

threading.Thread(target=auto_clean, daemon=True).start()

# --- health check ---
@app.route("/api/health")
def health():
    return jsonify({"status": "ok"}), 200


# --- fast info fetch ---
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
            "--youtube-skip-dash-manifest",
            "-j", url,
        ]

        # shorter timeout so it always finishes before Render limit
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        raw_line = result.stdout.strip().split("\n")[0]
        info = json.loads(raw_line)

        return jsonify({
            "title": info.get("title", "Unknown Title"),
            "thumbnail": info.get("thumbnail", ""),
            "qualities": [
                {"label": "🎥 Highest Quality (MP4)", "type": "mp4", "url": url},
                {"label": "🎵 Highest Quality (MP3)", "type": "mp3", "url": url}
            ]
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout fetching video info (YouTube may be slow)"}), 504
    except Exception as e:
        print("INFO ERROR:", e)
        return jsonify({"error": str(e)}), 500


# --- download handler ---
@app.route("/api/download", methods=["POST"])
def api_download():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403

    data = request.get_json() or {}
    url = data.get("url")
    kind = data.get("type")
    if not url or kind not in ["mp4", "mp3"]:
        return jsonify({"error": "Missing or invalid download type"}), 400

    try:
        file_id = str(uuid.uuid4())
        base_output = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")

        if kind == "mp4":
            cmd = [
                "yt-dlp",
                "--cookies", "cookies.txt",
                "--extractor-args", "youtubetab:skip=authcheck",
                "-f", "bv*+ba/b",
                "--merge-output-format", "mp4",
                "-o", base_output,
                url,
            ]
        else:
            cmd = [
                "yt-dlp",
                "--cookies", "cookies.txt",
                "--extractor-args", "youtubetab:skip=authcheck",
                "-f", "bestaudio/b",
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", base_output,
                url,
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())

        # find the resulting file
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id.split('-')[0]) or f.startswith(file_id):
                return jsonify({"download_url": f"/downloads/{f}"})
        return jsonify({"error": "File not found after download"}), 500

    except Exception as e:
        print("DOWNLOAD ERROR:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/downloads/<path:filename>")
def serve_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    print("\n✅ Server ready!")
    print(f"API Key: {API_KEY}")
    print(f"  info: http://localhost:5000/api/info")
    print(f"  download: http://localhost:5000/api/download\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
