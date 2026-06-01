import os
import yt_dlp
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")


def get_ydl_opts_base():
    return {
        "cookiefile": COOKIES_FILE,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
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
        opts["playlistend"] = limit

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

        videos = []
        for entry in info.get("entries", []):
            if not entry:
                continue
            vid_id = entry.get("id", "")
            thumbnails = entry.get("thumbnails") or []
            thumb = thumbnails[-1]["url"] if thumbnails else f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"
            videos.append({
                "id": vid_id,
                "title": entry.get("title", ""),
                "thumbnail": thumb,
                "duration": format_duration(entry.get("duration")),
                "channel": entry.get("channel") or entry.get("uploader") or "",
                "views": entry.get("view_count"),
                "url": entry.get("url") or f"https://www.youtube.com/watch?v={vid_id}",
            })

        return jsonify({"results": videos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download/audio/<path:link>")
def download_audio(link):
    url = link if link.startswith("http") else f"https://{link}"
    try:
        opts = get_ydl_opts_base()
        opts["format"] = "bestaudio/best"

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        fmts = info.get("requested_formats") or [info]
        fmt = fmts[0]

        return jsonify({
            "status": "ok",
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": format_duration(info.get("duration")),
            "channel": info.get("uploader"),
            "ext": fmt.get("ext"),
            "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
            "filesize_human": format_filesize(fmt.get("filesize") or fmt.get("filesize_approx")),
            "url": fmt.get("url"),
            "acodec": fmt.get("acodec"),
            "abr": fmt.get("abr"),
            "format_id": fmt.get("format_id"),
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

        all_formats = []
        seen = set()
        for fmt in info.get("formats", []):
            if not fmt.get("url"):
                continue
            fid = fmt.get("format_id")
            if fid in seen:
                continue
            seen.add(fid)

            height = fmt.get("height")
            width = fmt.get("width")
            vcodec = fmt.get("vcodec", "none")
            acodec = fmt.get("acodec", "none")

            all_formats.append({
                "format_id": fid,
                "ext": fmt.get("ext"),
                "resolution": fmt.get("resolution") or (
                    f"{width}x{height}" if width and height else "audio only"
                ),
                "height": height,
                "width": width,
                "fps": fmt.get("fps"),
                "vcodec": vcodec,
                "acodec": acodec,
                "abr": fmt.get("abr"),
                "vbr": fmt.get("vbr"),
                "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
                "filesize_human": format_filesize(
                    fmt.get("filesize") or fmt.get("filesize_approx")
                ),
                "url": fmt.get("url"),
                "has_video": vcodec not in (None, "none"),
                "has_audio": acodec not in (None, "none"),
                "format_note": fmt.get("format_note", ""),
                "tbr": fmt.get("tbr"),
            })

        all_formats.sort(
            key=lambda x: (x.get("height") or 0, x.get("abr") or 0),
            reverse=True,
        )

        return jsonify({
            "status": "ok",
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": format_duration(info.get("duration")),
            "channel": info.get("uploader"),
            "description": (info.get("description") or "")[:300],
            "formats": all_formats,
            "formats_count": len(all_formats),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
