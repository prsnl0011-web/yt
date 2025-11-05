# YouTube Downloader API

Simple Flask API that provides:
- `/api/info` → returns title, thumbnail, and quality options
- `/api/download` → downloads MP4/MP3 using yt-dlp

## Deployment on Render
1. Push this repo to GitHub
2. Create new Web Service → “Deploy from GitHub”
3. Build Command: *(leave empty)*
4. Start Command:
   ```bash
   python api_server.py
