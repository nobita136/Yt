import os
import yt_dlp
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── Hardcoded YouTube cookies (passed via HTTP header — avoids TV-player downgrade) ──
_YT_COOKIE = (
    "LOGIN_INFO=AFmmF2swRQIgFyjPUFLb8f4VIyvVK5sroURcwRlEtHk5LAtINMiICuwCIQDWxRnn5gPpr8uP88h_oV3p3CnG213VoFdxn3IkyeL4ug"
    ":QUQ3MjNmd1paQjZfSWtmbEotMlJHLWVjSWptdExwaUM4aUJmd25yenlVbzR5UHdzYzFBdGVGTXJ6UEQtMFZEak5CSURCS2F2QklCU09fUE1nTzFY"
    "THpmb2t2bC00SFZzZEotVVpnYVU5dE9lRlVOeXN5WVprVWRSLVRabnlsVElURUgtOFRiQWk1bkN6ZXdNak15aWllZFJBTHR5aVNIZjhB; "
    "HSID=A2tXT98POOHO7yo4s; "
    "SSID=ApzcjnJs6s7VV2L7V; "
    "APISID=Oa3SOSdRa4H_ODSf/Az5e6YdwibvjR1Lr-; "
    "SAPISID=jj62wAPusEtJ5EtO/Agnw_lZ494nyLPq0G; "
    "__Secure-1PAPISID=jj62wAPusEtJ5EtO/Agnw_lZ494nyLPq0G; "
    "__Secure-3PAPISID=jj62wAPusEtJ5EtO/Agnw_lZ494nyLPq0G; "
    "PREF=f6=40000000&tz=UTC&f4=4000000&f7=100&hl=en; "
    "SID=g.a000-giVPCs33Ht5-uPC3eTCs1l7XAp5phrcHqRd0NCtddv5t2FEl8a4vL4fPBntY8rsvBnpvAACgYKAS4SARMSFQHGX2Mim8rvhTXVEVOVz8aP3_6u7RoVAUF8yKr2ICYJU-nQOEP7BhYrCOxa0076; "
    "__Secure-1PSID=g.a000-giVPCs33Ht5-uPC3eTCs1l7XAp5phrcHqRd0NCtddv5t2FEBjBEDT02rHAo-mVGoQsjvAACgYKAdASARMSFQHGX2MiDeuaD50tQYC33tS0iSBcQRoVAUF8yKpyeRuBq6l6-wR_bILajzhg0076; "
    "__Secure-3PSID=g.a000-giVPCs33Ht5-uPC3eTCs1l7XAp5phrcHqRd0NCtddv5t2FEy2Zb9ToYSDVHneIDUSurcQACgYKAa8SARMSFQHGX2MiDqdllsTHRkBNdsEaXenIUBoVAUF8yKo-UphSBg4dr9iUUiwcFSy40076; "
    "__Secure-1PSIDTS=sidts-CjUBhkeRdxgkkUnrtwMBUEroeu-foOo2EjBZvZmOBu7BG9TP2TUqz7xcAR0uVT18YiKtdaFbkRAA; "
    "__Secure-3PSIDTS=sidts-CjUBhkeRdxgkkUnrtwMBUEroeu-foOo2EjBZvZmOBu7BG9TP2TUqz7xcAR0uVT18YiKtdaFbkRAA; "
    "SIDCC=AKEyXzUga5l0YVl2eJk8Sip9jGicjUVDK7O10SPuicesU0fxQaBaHPh_Pkt8g9dBHluG6ZVJ; "
    "__Secure-1PSIDCC=AKEyXzXHXyV_EoiAjwwRPQiXlmT4Tg2X9lXh_Br7R33RRwYu9n_SLmObXCGFb_tUDvrKv0mW; "
    "__Secure-3PSIDCC=AKEyXzWFmp-jAH7GnuecuisT6cDKXkgeBLOOFNEfXNLCDak3d_Nbe7fdBAuwNud6PcBL85w1DYc; "
    "VISITOR_INFO1_LIVE=g5BHFS17MIA; "
    "VISITOR_PRIVACY_METADATA=CgJQSxIEGgAgEg%3D%3D; "
    "__Secure-ROLLOUT_TOKEN=CIn9odmM0viHpwEQppqq2eDJkAMYx-b0uM7mlAM%3D; "
    "__Secure-YNID=18.YT=My--KUsK9skM1Me935C-dc5rKjx06HsQjHA6XyHzUUODvY_-jZxnTTbtCca9qnxT75eRoU9IyQY3slohaAkHTz4Di0OOisBjGvuJi5ffbel5u29on5eGy_6ynKP2npp561odRJP1_823Hw9dfoY2c5sOdyt5O99Jf0Lup-bau5JUgxCN27jATL_C38UnWw55UGa3gD6qnPtkCY8vB4GggrcjcrXXHs8mTEbx1w97y8Ux6shHNC3vwNvxGOaIqt7QpcxDobVL2VP0veMvBAq-dNRU5M0AVulzwAkpABlnBirNL9yRVlbfzNs9IjyAdIOV3Q4biNiYs3rC1YnBsz6c9Q; "
    "YSC=qYN3PUEMEOY"
)

_YDL_HEADERS = {
    "Cookie":     _YT_COOKIE,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def normalize_url(link):
    """Fix https:/ → https:// (double slash stripped by URL routing)."""
    link = link.strip()
    if link.startswith("https:/") and not link.startswith("https://"):
        link = "https://" + link[7:]
    elif link.startswith("http:/") and not link.startswith("http://"):
        link = "http://" + link[6:]
    elif not link.startswith("http"):
        link = "https://" + link
    return link


def get_ydl_opts():
    return {
        "quiet":        True,
        "no_warnings":  True,
        "skip_download": True,
        "http_headers": _YDL_HEADERS,
    }


def extract_info(url):
    with yt_dlp.YoutubeDL(get_ydl_opts()) as ydl:
        return ydl.extract_info(url, download=False)


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


def build_format_entry(fmt):
    vcodec   = fmt.get("vcodec") or "none"
    acodec   = fmt.get("acodec") or "none"
    has_video = vcodec not in (None, "none")
    has_audio = acodec not in (None, "none")
    height   = fmt.get("height")
    width    = fmt.get("width")
    size     = fmt.get("filesize") or fmt.get("filesize_approx")
    return {
        "format_id":      fmt.get("format_id"),
        "ext":            fmt.get("ext"),
        "resolution":     fmt.get("resolution") or (
                          f"{width}x{height}" if width and height else "audio only"),
        "height":         height,
        "width":          width,
        "fps":            fmt.get("fps"),
        "vcodec":         vcodec,
        "acodec":         acodec,
        "abr":            fmt.get("abr") or 0,
        "vbr":            fmt.get("vbr"),
        "tbr":            fmt.get("tbr"),
        "filesize":       size,
        "filesize_human": format_filesize(size),
        "format_note":    fmt.get("format_note") or "",
        "has_video":      has_video,
        "has_audio":      has_audio,
        "url":            fmt.get("url"),
    }


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
        entry     = build_format_entry(fmt)
        has_video = entry["has_video"]
        has_audio = entry["has_audio"]
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


# ══════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════

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
        opts = get_ydl_opts()
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


# ── /download/audio?url=<youtube_url>
#    Returns JSON: best_audio + all_audio_formats with direct download URLs
@app.route("/download/audio")
@app.route("/download/audio/<path:link>")
def download_audio(link=None):
    raw = request.args.get("url") or link or ""
    if not raw:
        return jsonify({"status": "error", "error": "url parameter required"}), 400
    url = normalize_url(raw)
    try:
        info = extract_info(url)
        _, _, audio_only = parse_formats(info)
        best = audio_only[0] if audio_only else None

        return jsonify({
            "status":            "ok",
            "title":             info.get("title"),
            "thumbnail":         info.get("thumbnail"),
            "duration":          format_duration(info.get("duration")),
            "channel":           info.get("uploader"),
            "best_audio":        best,
            "all_audio_formats": audio_only,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ── /download/video?url=<youtube_url>
#    Returns JSON: all formats (combined / video_only / audio_only) with direct download URLs
@app.route("/download/video")
@app.route("/download/video/<path:link>")
def download_video(link=None):
    raw = request.args.get("url") or link or ""
    if not raw:
        return jsonify({"status": "error", "error": "url parameter required"}), 400
    url = normalize_url(raw)
    try:
        info = extract_info(url)
        combined, video_only, audio_only = parse_formats(info)

        return jsonify({
            "status":         "ok",
            "title":          info.get("title"),
            "thumbnail":      info.get("thumbnail"),
            "duration":       format_duration(info.get("duration")),
            "channel":        info.get("uploader"),
            "description":    (info.get("description") or "")[:300],
            "formats": {
                "combined":   combined,
                "video_only": video_only,
                "audio_only": audio_only,
            },
            "formats_flat":   combined + video_only + audio_only,
            "formats_count":  len(combined) + len(video_only) + len(audio_only),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
