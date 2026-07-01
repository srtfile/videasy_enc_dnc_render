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
TMDB_API_KEY = "6fad3f86b8452ee232deb7977d7dcf58"

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


def build_url(server_key, media_type, title, year, tmdb_id, imdb_id, season="1", episode="1"):
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
        url += "&" + extra.lstrip("?&")
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
        seasons = data.get("number_of_seasons", 1) if media_type == "tv" else None
        return {"title": title, "year": year, "imdb_id": imdb, "poster": poster, "seasons": seasons}
    except Exception:
        return {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/resolve", methods=["POST"])
def api_resolve():
    body = request.get_json(force=True)
    tmdb_id    = str(body.get("tmdb_id", "")).strip()
    media_type = body.get("media_type", "movie")
    season     = str(body.get("season", "1")).strip()
    episode    = str(body.get("episode", "1")).strip()

    if not tmdb_id:
        return jsonify({"success": False, "error": "TMDB ID required"}), 400

    meta = lookup_tmdb(tmdb_id, media_type)
    if not meta.get("title"):
        return jsonify({"success": False, "error": "TMDB lookup failed — invalid ID?"}), 400

    title   = meta["title"]
    year    = meta["year"]
    imdb_id = meta.get("imdb_id", "")

    results = {}
    for key, server in SERVERS.items():
        if server["type"] == "movie" and media_type == "tv":
            results[key] = {"success": False, "error": "Movie-only server",
                            "server": server["label"], "lang": server["lang"]}
            continue
        url = build_url(key, media_type, title, year, tmdb_id, imdb_id, season, episode)
        r = fetch_and_decrypt(url, tmdb_id)
        r["source_url"] = url
        r["server"] = server["label"]
        r["lang"]   = server["lang"]
        results[key] = r

    return jsonify({
        "success": True,
        "meta": {"title": title, "year": year, "poster": meta.get("poster",""), "imdb_id": imdb_id},
        "results": results
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
