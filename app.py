import os
from flask import Flask, redirect, request, jsonify, session
from flask_cors import CORS
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

app = Flask(__name__)
CORS(app)

# Flask セッション暗号化キー（任意の文字列）
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# --- 環境変数から Spotify クレデンシャルを取得 ---
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "https://music-cat-7r71.onrender.com/callback")

SCOPE = "user-read-recently-played"

# --- SpotifyOAuth 設定 ---
def create_spotify_oauth():
    return SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope=SCOPE
    )

# -------------------------------
# 🌐 認証フロー
# -------------------------------

@app.route("/login")
def login():
    sp_oauth = create_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route("/callback")
def callback():
    sp_oauth = create_spotify_oauth()
    code = request.args.get("code")
    token_info = sp_oauth.get_access_token(code)
    session["token_info"] = token_info
    return jsonify({"status": "success", "access_token": token_info["access_token"]})

@app.route("/auth-status")
def auth_status():
    token_info = session.get("token_info")
    if token_info:
        return jsonify({"authenticated": True, "access_token": token_info.get("access_token")})
    return jsonify({"authenticated": False}), 404

# -------------------------------
# 🎵 最近再生した楽曲を取得
# -------------------------------

@app.route("/recent")
def recent_tracks():
    token_info = session.get("token_info")
    if not token_info:
        return jsonify({"error": "User not authenticated"}), 401

    sp = Spotify(auth=token_info["access_token"])
    items = sp.current_user_recently_played(limit=10)["items"]

    results = []
    for item in items:
        track = item["track"]
        artist = track["artists"][0]
        artist_info = sp.artist(artist["id"])
        genres = artist_info.get("genres", [])
        results.append({
            "name": track["name"],
            "artist": artist["name"],
            "genres": genres,
            "image": track["album"]["images"][0]["url"] if track["album"]["images"] else ""
        })

    return jsonify({"recently_played": results})

@app.route("/")
def home():
    return "✅ Spotify API Server is running."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
