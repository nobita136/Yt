import os
import uuid
import threading
import yt_dlp
from flask import Flask, request, jsonify, render_template, send_file, after_this_request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
FFMPEG_PATH  = "/nix/store/bl78f0v8yq8nqn3kp98lbk79kp5k62a0-replit-runtime-path/bin/ffmpeg"
TMP_DIR      = "/tmp/ytdl"
os.makedirs(TMP_DIR, exist_ok=True)


def get_ydl_opts_base():
    return {
        "cookiefile": COOKIES_FILE,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ffmpeg_location": FFMPEG_PATH,
    }


def format_duration(seconds):
    if not seconds:
        return "N/A"
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_filesize(size):
    if not size:
        return None
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"


def parse_formats(info):
    combined   = []
    video_only = []
    audio_only = []
    seen       = set()

    for fmt in info.get("formats", []):
        if not fmt.get("url"):
            continue
        fid = fmt.get("format_id")
        if fid in seen:
            continue
        seen.add(fid)

        vcodec    = fmt.get("vcodec") or "none"
        acodec    = fmt.get("acodec") or "none"
        has_video = vcodec not in (None, "none")
        has_audio = acodec not in (None, "none")
        height    = fmt.get("height")
        width     = fmt.get("width")

        entry = {
            "format_id":    fid,
            "ext":          fmt.get("ext"),
            "resolution":   fmt.get("resolution") or (
                f"{width}x{height}" if width and height else "audio only"
            ),
            "height":       height,
            "width":        width,
            "fps":          fmt.get("fps"),
            "vcodec":       vcodec,
            "acodec":       acodec,
            "abr":          fmt.get("abr") or 0,
            "vbr":          fmt.get("vbr"),
            "filesize":     fmt.get("filesize") or fmt.get("filesize_approx"),
            "filesize_human": format_filesize(fmt.get("filesize") or fmt.get("filesize_approx")),
            "url":          fmt.get("url"),
            "has_video":    has_video,
            "has_audio":    has_audio,
            "format_note":  fmt.get("format_note") or "",
            "tbr":          fmt.get("tbr"),
        }

        if has_video and has_audio:
            combined.append(entry)
        elif has_video:
            video_only.append(entry)
        elif has_audio:
            audio_only.append(entry)

    combined.sort(key=lambda x: x.get("height") or 0, reverse=True)
    video_only.sort(key=lambda x: x.get("height") or 0, reverse=True)
    audio_only.sort(key=lambda x: x.get("abr") or 0, reverse=True)

    return combined, video_only, audio_only


# ── Unique heights available for merge ─────────────────────────────────
def get_quality_options(combined, video_only):
    heights = {}
    for f in combined + video_only:
        h = f.get("height")
        if h and h not in heights:
            heights[h] = f.get("fps")
    return sorted(heights.items(), reverse=True)   # [(1080,24),(720,30),...]


# ═══════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", 12))
    if not query:
        return jsonify({"error": "Query is required"}), 400
    try:
        opts = get_ydl_opts_base()
        opts["extract_flat"] = True
        opts["playlistend"]  = limit
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        videos = []
        for entry in info.get("entries", []):
            if not entry:
                continue
            vid_id     = entry.get("id", "")
            thumbnails = entry.get("thumbnails") or []
            thumb = (thumbnails[-1]["url"] if thumbnails
                     else f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg")
            videos.append({
                "id":        vid_id,
                "title":     entry.get("title", ""),
                "thumbnail": thumb,
                "duration":  format_duration(entry.get("duration")),
                "channel":   entry.get("channel") or entry.get("uploader") or "",
                "views":     entry.get("view_count"),
                "url":       entry.get("url") or f"https://www.youtube.com/watch?v={vid_id}",
            })
        return jsonify({"results": videos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download/audio/<path:link>")
def download_audio(link):
    url = link if link.startswith("http") else f"https://{link}"
    try:
        opts          = get_ydl_opts_base()
        opts["format"] = "bestaudio/best"
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        fmts = info.get("requested_formats") or [info]
        fmt  = fmts[0]
        _, _, audio_only = parse_formats(info)
        return jsonify({
            "status":   "ok",
            "title":    info.get("title"),
            "thumbnail":info.get("thumbnail"),
            "duration": format_duration(info.get("duration")),
            "channel":  info.get("uploader"),
            "best_audio": {
                "format_id":     fmt.get("format_id"),
                "ext":           fmt.get("ext"),
                "acodec":        fmt.get("acodec"),
                "abr":           fmt.get("abr"),
                "filesize":      fmt.get("filesize") or fmt.get("filesize_approx"),
                "filesize_human":format_filesize(fmt.get("filesize") or fmt.get("filesize_approx")),
                "url":           fmt.get("url"),
            },
            "all_audio_formats": audio_only,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/download/video/<path:link>")
def download_video(link):
    url = link if link.startswith("http") else f"https://{link}"
    try:
        opts = get_ydl_opts_base()
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        combined, video_only, audio_only = parse_formats(info)
        quality_options = get_quality_options(combined, video_only)
        return jsonify({
            "status":         "ok",
            "title":          info.get("title"),
            "thumbnail":      info.get("thumbnail"),
            "duration":       format_duration(info.get("duration")),
            "channel":        info.get("uploader"),
            "description":    (info.get("description") or "")[:300],
            "quality_options": [{"height": h, "fps": f} for h, f in quality_options],
            "formats": {
                "combined":   combined,
                "video_only": video_only,
                "audio_only": audio_only,
            },
            "formats_flat":   combined + video_only + audio_only,
            "formats_count":  len(combined) + len(video_only) + len(audio_only),
            "note": "Use /download/merge/<url>?height=1080 to get a merged video+audio file.",
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/download/merge/<path:link>")
def download_merge(link):
    """
    Downloads best video at given height + best audio,
    merges with ffmpeg, streams merged MP4 back to client.
    """
    url    = link if link.startswith("http") else f"https://{link}"
    height = request.args.get("height", "best")

    if height == "best":
        fmt_selector = "bestvideo+bestaudio/best"
    else:
        fmt_selector = f"bestvideo[height<={height}]+bestaudio/best"

    session_id = uuid.uuid4().hex
    out_tmpl   = os.path.join(TMP_DIR, f"{session_id}.%(ext)s")
    out_mp4    = os.path.join(TMP_DIR, f"{session_id}.mp4")

    try:
        opts = {
            "cookiefile":      COOKIES_FILE,
            "quiet":           True,
            "no_warnings":     True,
            "format":          fmt_selector,
            "outtmpl":         out_tmpl,
            "ffmpeg_location": FFMPEG_PATH,
            "postprocessors":  [{
                "key":             "FFmpegVideoConvertor",
                "preferedformat":  "mp4",
            }],
            "merge_output_format": "mp4",
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        title    = info.get("title", "video")
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:60].strip() or "video"
        dl_name  = f"{safe_title}_{height}p.mp4"

        if not os.path.exists(out_mp4):
            possible = [f for f in os.listdir(TMP_DIR) if f.startswith(session_id)]
            if possible:
                out_mp4 = os.path.join(TMP_DIR, possible[0])
            else:
                return jsonify({"status": "error", "error": "Merge failed — output file not found"}), 500

        def cleanup(path):
            try:
                os.remove(path)
            except Exception:
                pass

        @after_this_request
        def remove_file(response):
            t = threading.Thread(target=cleanup, args=(out_mp4,))
            t.daemon = True
            t.start()
            return response

        return send_file(
            out_mp4,
            as_attachment=True,
            download_name=dl_name,
            mimetype="video/mp4",
        )

    except Exception as e:
        for f in os.listdir(TMP_DIR):
            if f.startswith(session_id):
                try: os.remove(os.path.join(TMP_DIR, f))
                except: pass
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
