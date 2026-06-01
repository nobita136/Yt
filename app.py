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


def parse_formats(info):
    combined = []
    video_only = []
    audio_only = []
    seen = set()

    best_audio_fmt = None
    best_audio_abr = 0

    for fmt in info.get("formats", []):
        if not fmt.get("url"):
            continue
        fid = fmt.get("format_id")
        if fid in seen:
            continue
        seen.add(fid)

        height = fmt.get("height")
        width = fmt.get("width")
        vcodec = fmt.get("vcodec") or "none"
        acodec = fmt.get("acodec") or "none"
        has_video = vcodec not in (None, "none")
        has_audio = acodec not in (None, "none")
        abr = fmt.get("abr") or 0

        entry = {
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
            "abr": abr,
            "vbr": fmt.get("vbr"),
            "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
            "filesize_human": format_filesize(fmt.get("filesize") or fmt.get("filesize_approx")),
            "url": fmt.get("url"),
            "has_video": has_video,
            "has_audio": has_audio,
            "format_note": fmt.get("format_note") or "",
            "tbr": fmt.get("tbr"),
        }

        if has_video and has_audio:
            combined.append(entry)
        elif has_video:
            video_only.append(entry)
        elif has_audio:
            audio_only.append(entry)
            if abr > best_audio_abr:
                best_audio_abr = abr
                best_audio_fmt = entry

    combined.sort(key=lambda x: x.get("height") or 0, reverse=True)
    video_only.sort(key=lambda x: x.get("height") or 0, reverse=True)
    audio_only.sort(key=lambda x: x.get("abr") or 0, reverse=True)

    for v in video_only:
        if best_audio_fmt:
            v["audio_url"] = best_audio_fmt["url"]
            v["audio_ext"] = best_audio_fmt["ext"]
            v["audio_format_id"] = best_audio_fmt["format_id"]

    return combined, video_only, audio_only, best_audio_fmt


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
            thumb = (
                thumbnails[-1]["url"]
                if thumbnails
                else f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"
            )
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

        _, _, audio_only, _ = parse_formats(info)

        return jsonify({
            "status": "ok",
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": format_duration(info.get("duration")),
            "channel": info.get("uploader"),
            "best_audio": {
                "ext": fmt.get("ext"),
                "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
                "filesize_human": format_filesize(fmt.get("filesize") or fmt.get("filesize_approx")),
                "url": fmt.get("url"),
                "acodec": fmt.get("acodec"),
                "abr": fmt.get("abr"),
                "format_id": fmt.get("format_id"),
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

        combined, video_only, audio_only, best_audio = parse_formats(info)

        all_formats = combined + video_only + audio_only

        return jsonify({
            "status": "ok",
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": format_duration(info.get("duration")),
            "channel": info.get("uploader"),
            "description": (info.get("description") or "")[:300],
            "best_audio": best_audio,
            "formats": {
                "combined": combined,
                "video_only": video_only,
                "audio_only": audio_only,
            },
            "formats_flat": all_formats,
            "formats_count": len(all_formats),
            "note": "video_only formats include audio_url field for the best matching audio stream. Use both video URL + audio_url for full quality with sound.",
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
