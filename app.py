import os
import requests
from urllib.parse import quote
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

HEADERS = {
    "Accept": "*/*",
    "Origin": "https://player.videasy.to",
    "Referer": "https://player.videasy.to/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
}

ENC_DEC_API = "https://enc-dec.app/api"
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

SERVERS = {
    "neon":    {"path": "mb-flix",      "label": "Neon",        "lang": "Original",   "type": "both"},
    "yoru":    {"path": "cdn",          "label": "Yoru",        "lang": "Original",   "type": "movie"},
    "cypher":  {"path": "downloader2",  "label": "Cypher",      "lang": "Original",   "type": "both"},
    "sage":    {"path": "1movies",      "label": "Sage",        "lang": "Original",   "type": "both"},
    "breach":  {"path": "m4uhd",        "label": "Breach",      "lang": "Original",   "type": "both"},
    "vyse":    {"path": "hdmovie",      "label": "Vyse",        "lang": "English",    "type": "both"},
    "killjoy": {"path": "meine",        "label": "Killjoy",     "lang": "German",     "type": "both", "extra": "?language=german"},
    "fade":    {"path": "hdmovie",      "label": "Fade",        "lang": "Hindi",      "type": "both"},
    "omen":    {"path": "lamovie",      "label": "Omen",        "lang": "Spanish",    "type": "both"},
    "raze":    {"path": "superflix",    "label": "Raze",        "lang": "Portuguese", "type": "both"},
}


def double_encode(title: str) -> str:
    return quote(quote(title, safe=""), safe="")


def build_url(server_key, media_type, title, year, tmdb_id, imdb_id, season="", episode=""):
    server = SERVERS[server_key]
    path = server["path"]
    enc_title = double_encode(title)
    extra = server.get("extra", "")
    base = f"https://api.videasy.to/{path}/sources-with-title"
    if media_type == "movie":
        url = (f"{base}?title={enc_title}&mediaType=movie&year={year}"
               f"&tmdbId={tmdb_id}&imdbId={imdb_id}")
    else:
        url = (f"{base}?title={enc_title}&mediaType=tv&year={year}"
               f"&episodeId={episode}&seasonId={season}"
               f"&tmdbId={tmdb_id}&imdbId={imdb_id}")
    if extra:
        sep = "&" if "?" in url else "?"
        url += sep + extra.lstrip("?&")
    return url


def fetch_and_decrypt(url, tmdb_id):
    try:
        enc_data = requests.get(url, headers=HEADERS, timeout=15).text
    except Exception as e:
        return {"success": False, "error": f"Fetch failed: {e}"}
    try:
        resp = requests.post(
            f"{ENC_DEC_API}/dec-videasy",
            json={"text": enc_data, "id": tmdb_id},
            timeout=15
        ).json()
        if resp.get("status") != 200:
            return {"success": False, "error": resp.get("error", "Decryption failed")}
        return {"success": True, "data": resp["result"]}
    except Exception as e:
        return {"success": False, "error": f"Decrypt failed: {e}"}


def lookup_tmdb(tmdb_id, media_type):
    if not TMDB_API_KEY:
        return {}
    try:
        kind = "movie" if media_type == "movie" else "tv"
        data = requests.get(
            f"https://api.themoviedb.org/3/{kind}/{tmdb_id}?api_key={TMDB_API_KEY}",
            timeout=10
        ).json()
        title = data.get("title") or data.get("name", "")
        year_raw = data.get("release_date") or data.get("first_air_date", "")
        year = year_raw[:4] if year_raw else ""
        imdb = data.get("imdb_id", "")
        poster = f"https://image.tmdb.org/t/p/w200{data['poster_path']}" if data.get("poster_path") else ""
        return {"title": title, "year": year, "imdb_id": imdb, "poster": poster}
    except Exception:
        return {}


@app.route("/")
def index():
    return render_template("index.html", servers=SERVERS)


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    body = request.get_json(force=True)
    media_type = body.get("media_type", "movie")
    tmdb_id    = body.get("tmdb_id", "").strip()
    imdb_id    = body.get("imdb_id", "").strip()
    title      = body.get("title", "").strip()
    year       = body.get("year", "").strip()
    season     = body.get("season", "1").strip()
    episode    = body.get("episode", "1").strip()
    server_key = body.get("server", "neon")

    if not tmdb_id:
        return jsonify({"success": False, "error": "TMDB ID is required"}), 400

    if not title or not year:
        meta = lookup_tmdb(tmdb_id, media_type)
        title   = title   or meta.get("title", "")
        year    = year    or meta.get("year", "")
        imdb_id = imdb_id or meta.get("imdb_id", "")

    if not title:
        return jsonify({"success": False, "error": "Title is required (or set TMDB_API_KEY for auto-lookup)"}), 400

    if server_key not in SERVERS:
        return jsonify({"success": False, "error": "Unknown server"}), 400

    server = SERVERS[server_key]
    if server["type"] == "movie" and media_type == "tv":
        return jsonify({"success": False, "error": f"Server '{server['label']}' only supports movies"}), 400

    url = build_url(server_key, media_type, title, year, tmdb_id, imdb_id, season, episode)
    result = fetch_and_decrypt(url, tmdb_id)
    result["source_url"] = url
    result["server"] = server["label"]
    result["lang"]   = server["lang"]
    return jsonify(result)


@app.route("/api/fetch-all", methods=["POST"])
def api_fetch_all():
    body = request.get_json(force=True)
    media_type = body.get("media_type", "movie")
    tmdb_id    = body.get("tmdb_id", "").strip()
    imdb_id    = body.get("imdb_id", "").strip()
    title      = body.get("title", "").strip()
    year       = body.get("year", "").strip()
    season     = body.get("season", "1").strip()
    episode    = body.get("episode", "1").strip()

    if not tmdb_id:
        return jsonify({"success": False, "error": "TMDB ID is required"}), 400

    if not title or not year:
        meta = lookup_tmdb(tmdb_id, media_type)
        title   = title   or meta.get("title", "")
        year    = year    or meta.get("year", "")
        imdb_id = imdb_id or meta.get("imdb_id", "")

    if not title:
        return jsonify({"success": False, "error": "Title is required (or set TMDB_API_KEY for auto-lookup)"}), 400

    results = {}
    for key, server in SERVERS.items():
        if server["type"] == "movie" and media_type == "tv":
            results[key] = {"success": False, "error": "Movie-only server", "server": server["label"], "lang": server["lang"]}
            continue
        url = build_url(key, media_type, title, year, tmdb_id, imdb_id, season, episode)
        r = fetch_and_decrypt(url, tmdb_id)
        r["source_url"] = url
        r["server"] = server["label"]
        r["lang"]   = server["lang"]
        results[key] = r

    return jsonify({"success": True, "results": results})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
