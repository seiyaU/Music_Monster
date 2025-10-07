import os
import requests
import uuid
from flask import Flask, jsonify, redirect, request

app = Flask(__name__)

# 環境変数から読み込み
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")

BASE_URL = "https://music-cat-7r71.onrender.com"

auth_sessions = {}  # state → {access_token, refresh_token, user_id}


@app.route("/login")
def login():
    state = str(uuid.uuid4())
    auth_sessions[state] = {}

    scope = "user-read-recently-played user-read-private"
    auth_url = (
        "https://accounts.spotify.com/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={scope}"
        f"&state={state}"
    )
    return redirect(auth_url)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state or state not in auth_sessions:
        return "Invalid request", 400

    token_res = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
    )

    if token_res.status_code != 200:
        return jsonify(token_res.json()), token_res.status_code

    tokens = token_res.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    user_res = requests.get(
        "https://api.spotify.com/v1/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    if user_res.status_code != 200:
        return jsonify(user_res.json()), user_res.status_code

    user_id = user_res.json().get("id")
    auth_sessions[state] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user_id,
        "authenticated": True
    }

    return jsonify({"status": "success", "user_id": user_id})


@app.route("/auth-status")
def auth_status():
    for state, data in auth_sessions.items():
        if data.get("authenticated"):
            return jsonify({"authenticated": True, "user_id": data["user_id"]})
    return jsonify({"authenticated": False})


@app.route("/recent/<state>")
def recent_tracks(state):
    if state not in auth_sessions:
        return jsonify({"error": "無効なstate"}), 400

    info = auth_sessions[state]
    access_token = info.get("access_token")
    if not access_token:
        return jsonify({"error": "アクセストークンがありません"}), 400

    # 最近再生した曲取得
    res = requests.get(
        "https://api.spotify.com/v1/me/player/recently-played?limit=50",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if res.status_code != 200:
        return jsonify({"error": res.text}), res.status_code

    items = res.json().get("items", [])
    recent = []
    artist_genre_cache = {}  # アーティストごとのジャンルをキャッシュ

    for item in items:
        track = item.get("track", {})
        artist_objs = track.get("artists", [])
        artist_names = [a.get("name", "") for a in artist_objs]
        artist_ids = [a.get("id") for a in artist_objs if a.get("id")]

        genres = []
        for artist_id in artist_ids:
            if artist_id in artist_genre_cache:
                genres.extend(artist_genre_cache[artist_id])
            else:
                art_res = requests.get(
                    f"https://api.spotify.com/v1/artists/{artist_id}",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                if art_res.status_code == 200:
                    artist_info = art_res.json()
                    artist_genre_cache[artist_id] = artist_info.get("genres", [])
                    genres.extend(artist_info.get("genres", []))

        recent.append({
            "name": track.get("name"),
            "artist": ", ".join(artist_names),
            "genres": list(set(genres)),  # 重複除去
            "image": track.get("album", {}).get("images", [{}])[0].get("url", "")
        })

    return jsonify({"recently_played": recent})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
