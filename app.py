import os
import uuid
import threading
import yt_dlp
from flask import Flask, request, jsonify, render_template, send_file, after_this_request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

FFMPEG  = "/nix/store/b11ycf80cxi2iyrga8rkq1wzdinmax18-replit-runtime-path/bin/ffmpeg"
TMP_DIR = "/tmp/ytdl"
os.makedirs(TMP_DIR, exist_ok=True)

TARGET_HEIGHTS = [1080, 720, 360]

# ── Read cookies.txt → build Cookie header string at startup ──
def _load_cookie_header():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
    jar = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    jar[parts[5]] = parts[6]
    except Exception:
        pass
    return "; ".join(f"{k}={v}" for k, v in jar.items())

_COOKIE_HDR = _load_cookie_header()
_HEADERS = {
    "Cookie":     _COOKIE_HDR,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


# ── Helpers ────────────────────────────────────────────────────

def normalize_url(link):
    link = link.strip()
    if link.startswith("https:/") and not link.startswith("https://"):
        link = "https://" + link[7:]
    elif link.startswith("http:/") and not link.startswith("http://"):
        link = "http://" + link[6:]
    elif not link.startswith("http"):
        link = "https://" + link
    return link


def base_opts(download=False):
    return {
        "quiet":        True,
        "no_warnings":  True,
        "noplaylist":   True,
        "skip_download": not download,
        "http_headers": _HEADERS,
    }


def extract_info(url):
    with yt_dlp.YoutubeDL(base_opts()) as ydl:
        return ydl.extract_info(url, download=False)


def format_duration(sec):
    if not sec:
        return "N/A"
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def safe_title(info, fallback="file"):
    t = info.get("title", fallback)
    return "".join(c for c in t if c.isalnum() or c in " _-")[:60].strip() or fallback


def serve_and_clean(path, name, mime):
    def _del(p):
        try: os.remove(p)
        except: pass

    @after_this_request
    def _after(resp):
        threading.Thread(target=_del, args=(path,), daemon=True).start()
        return resp

    return send_file(path, as_attachment=True, download_name=name, mimetype=mime)


def available_heights(info):
    heights = set()
    for f in info.get("formats", []):
        h  = f.get("height")
        vc = f.get("vcodec") or "none"
        if h and vc not in (None, "none"):
            heights.add(h)
    result = []
    for t in TARGET_HEIGHTS:
        if any(abs(h - t) <= 30 for h in heights):
            result.append(t)
    return result


# ══════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ── Search ─────────────────────────────────────────────
@app.route("/search")
def search():
    q     = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", 12))
    if not q:
        return jsonify({"error": "Query is required"}), 400
    try:
        opts = base_opts()
        opts["extract_flat"] = True
        opts["playlistend"]  = limit
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{q}", download=False)
        videos = []
        for e in info.get("entries", []) or []:
            if not e:
                continue
            vid  = e.get("id", "")
            tnls = e.get("thumbnails") or []
            thumb = (tnls[-1]["url"] if tnls
                     else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg")
            videos.append({
                "id":        vid,
                "title":     e.get("title", ""),
                "thumbnail": thumb,
                "duration":  format_duration(e.get("duration")),
                "channel":   e.get("channel") or e.get("uploader") or "",
                "views":     e.get("view_count"),
                "url":       e.get("url") or f"https://www.youtube.com/watch?v={vid}",
            })
        return jsonify({"results": videos})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


# ── Audio info ─────────────────────────────────────────
# GET /download/audio?url=...  →  JSON (title, thumbnail, etc.)
@app.route("/download/audio")
@app.route("/download/audio/<path:link>")
def audio_info(link=None):
    raw = request.args.get("url") or link or ""
    if not raw:
        return jsonify({"status": "error", "error": "url required"}), 400
    try:
        info = extract_info(normalize_url(raw))
        return jsonify({
            "status":    "ok",
            "title":     info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration":  format_duration(info.get("duration")),
            "channel":   info.get("uploader"),
        })
    except Exception as ex:
        return jsonify({"status": "error", "error": str(ex)}), 500


# ── Audio download ──────────────────────────────────────
# GET /dl/audio?url=...  →  MP3 file (low quality)
@app.route("/dl/audio")
def audio_download():
    raw = request.args.get("url", "").strip()
    if not raw:
        return jsonify({"status": "error", "error": "url required"}), 400
    url = normalize_url(raw)
    sid = uuid.uuid4().hex
    out = os.path.join(TMP_DIR, f"{sid}.%(ext)s")
    mp3 = os.path.join(TMP_DIR, f"{sid}.mp3")
    try:
        opts = base_opts(download=True)
        opts.update({
            "format":          "worstaudio/worst",
            "outtmpl":         out,
            "ffmpeg_location": FFMPEG,
            "postprocessors":  [{
                "key":              "FFmpegExtractAudio",
                "preferredcodec":   "mp3",
                "preferredquality": "96",
            }],
        })
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        return serve_and_clean(mp3, f"{safe_title(info, 'audio')}.mp3", "audio/mpeg")
    except Exception as ex:
        for f in os.listdir(TMP_DIR):
            if f.startswith(sid):
                try: os.remove(os.path.join(TMP_DIR, f))
                except: pass
        return jsonify({"status": "error", "error": str(ex)}), 500


# ── Video info ─────────────────────────────────────────
# GET /download/video?url=...         →  JSON (qualities: 1080/720/360 available)
# GET /download/video?url=...&height=N → MP4 with audio (merged)
@app.route("/download/video")
@app.route("/download/video/<path:link>")
def video(link=None):
    raw    = request.args.get("url") or link or ""
    height = request.args.get("height", "").strip()
    if not raw:
        return jsonify({"status": "error", "error": "url required"}), 400
    url = normalize_url(raw)

    # ── Download mode ──────────────────────────────────
    if height:
        h   = int(height) if height.isdigit() else 1080
        sid = uuid.uuid4().hex
        out = os.path.join(TMP_DIR, f"{sid}.%(ext)s")
        mp4 = os.path.join(TMP_DIR, f"{sid}.mp4")
        try:
            opts = base_opts(download=True)
            opts.update({
                "format": (
                    f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]"
                    f"/bestvideo[height<={h}]+bestaudio"
                    f"/best[height<={h}]"
                ),
                "outtmpl":             out,
                "ffmpeg_location":     FFMPEG,
                "merge_output_format": "mp4",
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if not os.path.exists(mp4):
                files = [f for f in os.listdir(TMP_DIR) if f.startswith(sid)]
                mp4   = os.path.join(TMP_DIR, files[0]) if files else None
            if not mp4:
                return jsonify({"status": "error", "error": "Merged file not found"}), 500

            return serve_and_clean(mp4, f"{safe_title(info, 'video')}_{h}p.mp4", "video/mp4")
        except Exception as ex:
            for f in os.listdir(TMP_DIR):
                if f.startswith(sid):
                    try: os.remove(os.path.join(TMP_DIR, f))
                    except: pass
            return jsonify({"status": "error", "error": str(ex)}), 500

    # ── Info mode ──────────────────────────────────────
    try:
        info    = extract_info(url)
        heights = available_heights(info)
        labels  = {1080: "Full HD", 720: "HD", 360: "SD"}
        return jsonify({
            "status":    "ok",
            "title":     info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration":  format_duration(info.get("duration")),
            "channel":   info.get("uploader"),
            "qualities": [
                {"height": h, "label": labels.get(h, f"{h}p")}
                for h in heights
            ],
        })
    except Exception as ex:
        return jsonify({"status": "error", "error": str(ex)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
