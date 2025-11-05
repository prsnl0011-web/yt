#!/usr/bin/env python3
import os, sys, json, uuid, shutil, subprocess, traceback, threading, time, glob
from urllib.parse import urlparse, parse_qs
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ───────────────────────────────────────────────────────────────
# Ensure required tools
# ───────────────────────────────────────────────────────────────
def ensure_tools():
    print("🔄 Ensuring yt-dlp and deps...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "requests"], check=False)
    return shutil.which("yt-dlp"), shutil.which("ffmpeg")

yt_path, ffmpeg_path = ensure_tools()

import requests

# ───────────────────────────────────────────────────────────────
# Config + constants
# ───────────────────────────────────────────────────────────────
CONFIG_FILE = "config.json"
COOKIES_FILE = "cookies.txt"
DOWNLOADS_DIR = "downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

def load_or_create_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    api_key = str(uuid.uuid4())
    conf = {
        "api_key": api_key,
        "endpoints": {"info": "/api/info", "download": "/api/download", "health": "/api/health"}
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(conf, f, indent=2)
    return conf

config = load_or_create_config()

app = Flask(__name__)
CORS(app)

# ───────────────────────────────────────────────────────────────
# Utility helpers
# ───────────────────────────────────────────────────────────────
def clean_youtube_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
        if "youtu.be" in parsed.netloc:
            vid = parsed.path.lstrip("/")
            return f"https://www.youtube.com/watch?v={vid}"
        if "youtube.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            vid = (qs.get("v") or [None])[0]
            if vid:
                return f"https://www.youtube.com/watch?v={vid}"
        return url
    except Exception:
        return url

def oembed_info(url: str):
    try:
        r = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code == 200:
            data = r.json()
            return {"title": data.get("title"), "thumbnail": data.get("thumbnail_url")}
    except Exception:
        pass
    return None

def safe_download(url: str, kind: str) -> str:
    cmd = [
        yt_path,
        "-o", os.path.join(DOWNLOADS_DIR, "%(title)s.%(ext)s"),
        "--no-warnings", "--geo-bypass", "--retries", "3", "--socket-timeout", "15"
    ]
    if os.path.exists(COOKIES_FILE):
        cmd += ["--cookies", COOKIES_FILE]
    if ffmpeg_path:
        cmd += ["--ffmpeg-location", ffmpeg_path]
    if kind == "mp4":
        cmd += ["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best", "--merge-output-format", "mp4"]
    else:
        cmd += ["-f", "bestaudio/best", "--extract-audio", "--audio-format", "mp3", "--audio-quality", "192K"]
    cmd.append(url)

    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or out.stdout.strip())

    files = [os.path.join(DOWNLOADS_DIR, f) for f in os.listdir(DOWNLOADS_DIR)]
    if not files:
        raise RuntimeError("No file found after download.")
    latest = max(files, key=os.path.getctime)
    return os.path.abspath(latest)

# ───────────────────────────────────────────────────────────────
# Auto cleanup every 60 seconds
# ───────────────────────────────────────────────────────────────
def auto_cleanup(interval=60):
    while True:
        try:
            for f in glob.glob(os.path.join(DOWNLOADS_DIR, "*")):
                try:
                    os.remove(f)
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(interval)

threading.Thread(target=auto_cleanup, daemon=True).start()

# ───────────────────────────────────────────────────────────────
# API endpoints
# ───────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/api/info", methods=["POST"])
def api_info():
    try:
        if request.headers.get("X-API-Key") != config["api_key"]:
            return jsonify({"error": "Unauthorized"}), 401

        body = request.get_json(force=True)
        url = clean_youtube_url(body.get("url", ""))
        if not url:
            return jsonify({"error": "Missing URL"}), 400

        meta = oembed_info(url) or {}
        return jsonify({
            "title": meta.get("title", "YouTube Video"),
            "thumbnail": meta.get("thumbnail"),
            "qualities": [
                {"label": "🎥 Highest MP4 (video + audio)", "type": "mp4", "url": url},
                {"label": "🎵 Highest MP3 (audio only)", "type": "mp3", "url": url}
            ]
        })
    except Exception as e:
        print("INFO ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route("/api/download", methods=["POST"])
def api_download():
    try:
        if request.headers.get("X-API-Key") != config["api_key"]:
            return jsonify({"error": "Unauthorized"}), 401

        body = request.get_json(force=True)
        url = clean_youtube_url(body.get("url", ""))
        kind = body.get("type")
        if kind not in ("mp4", "mp3"):
            return jsonify({"error": "Invalid type"}), 400

        file_path = safe_download(url, kind)
        file_name = os.path.basename(file_path)
        return jsonify({
            "status": "success",
            "download_url": f"/downloads/{file_name}"
        })
    except Exception as e:
        print("DOWNLOAD ERROR:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route("/downloads/<path:filename>")
def serve_download(filename):
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)

# ───────────────────────────────────────────────────────────────
# Run server
# ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n✅ Server ready!")
    print(f"API Key: {config['api_key']}")
    print(f"info: http://localhost:5000/api/info")
    print(f"download: http://localhost:5000/api/download\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
