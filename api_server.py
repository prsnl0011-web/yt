import os
import json
import uuid
import threading
import subprocess
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# === CONFIG ===
API_KEY = os.environ.get("API_KEY", "420679f1-73e2-42a0-bbea-a10b99bd5fde")
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)

# === CLEANUP THREAD ===
def cleanup():
    while True:
        now = time.time()
        for f in os.listdir(DOWNLOAD_DIR):
            path = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(path) and now - os.path.getmtime(path) > 60:
                os.remove(path)
        time.sleep(30)

threading.Thread(target=cleanup, daemon=True).start()

# === UTILS ===
def sanitize_filename(name):
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, "")
    name = "".join(c for c in name if c.isprintable())
    return name[:180]

def run_yt_dlp(url, format_code, outname):
    cmd = [
        "yt-dlp",
        "--cookies", "cookies.txt",
        "-f", format_code,
        "--merge-output-format", "mp4",
        "-o", os.path.join(DOWNLOAD_DIR, outname),
        url
    ]
    return subprocess.run(cmd, capture_output=True, text=True)

def safe_download(url, kind):
    # get info to name file
    info_cmd = ["yt-dlp", "-j", url]
    info = subprocess.run(info_cmd, capture_output=True, text=True)
    video_data = json.loads(info.stdout)
    title = sanitize_filename(video_data.get("title", "video"))
    
    file_ext = "mp4" if kind == "mp4" else "mp3"
    file_name = f"{title}.{file_ext}"
    file_path = os.path.join(DOWNLOAD_DIR, file_name)

    fmt = "bv*+ba/b" if kind == "mp4" else "bestaudio/b"
    if kind == "mp3":
        cmd = [
            "yt-dlp", "--cookies", "cookies.txt",
            "-f", "bestaudio",
            "--extract-audio", "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", file_path, url
        ]
    else:
        cmd = [
            "yt-dlp", "--cookies", "cookies.txt",
            "-f", fmt,
            "--merge-output-format", "mp4",
            "-o", file_path, url
        ]

    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or out.stdout.strip())
    return file_path

# === ROUTES ===
@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/info", methods=["POST"])
def api_info():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "Missing URL"}), 400
    try:
        info = subprocess.run(
            ["yt-dlp", "-j", "--cookies", "cookies.txt", url],
            capture_output=True, text=True, timeout=25
        )
        if info.returncode != 0:
            raise RuntimeError(info.stderr.strip())
        meta = json.loads(info.stdout)
        return jsonify({
            "title": meta.get("title"),
            "thumbnail": meta.get("thumbnail"),
            "qualities": [
                {"label": "🎥 Highest MP4 (Video + Audio)", "type": "mp4", "url": url},
                {"label": "🎵 Highest MP3 (Audio Only)", "type": "mp3", "url": url}
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/download", methods=["POST"])
def api_download():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    data = request.get_json()
    url = data.get("url")
    kind = data.get("type")
    if not url or kind not in ["mp4", "mp3"]:
        return jsonify({"error": "Invalid parameters"}), 400

    try:
        file_path = safe_download(url, kind)
        file_name = os.path.basename(file_path)
        return jsonify({
            "download_url": f"/downloads/{file_name}"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/downloads/<path:filename>")
def serve_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

# === MAIN ===
if __name__ == "__main__":
    print("\n✅ Server ready!")
    print(f"API Key: {API_KEY}")
    print("  info: http://localhost:5000/api/info")
    print("  download: http://localhost:5000/api/download\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
