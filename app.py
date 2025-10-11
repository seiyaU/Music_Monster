from flask import Flask, request, jsonify, redirect, render_template, send_from_directory
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import os
import uuid
from time import time

app = Flask(__name__)

# ✅ Render環境変数から取得
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "https://music-cat-7r71.onrender.com/callback")

# ✅ 認証済みユーザー情報を保持（stateとuser_idの両方で参照できるように）
sessions = {}

@app.route("/")
def home():
    return render_template("index.html")  # PWAのメイン画面を返す

# PWA用のファイルを提供
@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")

@app.route("/serviceWorker.js")
def service_worker():
    return send_from_directory("static", "serviceWorker.js")

@app.route("/login")
def login():
    state = request.args.get("state") or str(uuid.uuid4())  
    # ✅ 認可URLを自分で構築
    auth_url = (
        f"https://accounts.spotify.com/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&scope=user-read-recently-played%20user-read-email"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={state}"
    )

    print(f"🌐 Redirecting user to Spotify login (state={state})")
    return redirect(auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")

    sp_oauth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope="user-read-recently-played user-read-email",
        cache_path=None
    )

    # ✅ アクセストークン取得
    token_info = sp_oauth.get_access_token(code, as_dict=True)
    access_token = token_info["access_token"]

    # ✅ Spotify API でユーザー情報取得
    sp = Spotify(auth=access_token)
    user = sp.me()
    user_id = user["id"]

    # ✅ ユーザー情報を state / user_id 両方に保存
    sessions[user_id] = {
        "access_token": token_info["access_token"],
        "refresh_token": token_info["refresh_token"],
        "expires_at": token_info["expires_at"]
    }

    return jsonify({
        "status": "success",
        "user_id": user_id,
        "access_token": access_token 
  })

@app.route("/auth-status")
def auth_status():
    state = request.args.get("state")
    if state and state in sessions:
        return jsonify({"authenticated": True, "user_id": sessions[state]["user_id"]})
    return jsonify({"authenticated": False}), 404

@app.route("/recent/<user_id>")
def recent_tracks(user_id):
    # ✅ user_idキーでセッションを取得
    session_data = sessions.get(user_id)
    if not session_data:
        return redirect("/login")

    access_token = session_data["access_token"]
    sp = Spotify(auth=access_token)
    recent = sp.current_user_recently_played(limit=50)

    # 🎵 結果を構築
    results = []
    for item in recent["items"]:
        track = item["track"]
        artist = track["artists"][0]
        artist_info = sp.artist(artist["id"])
        results.append({
            "name": track["name"],
            "artist": artist["name"],
            "genres": artist_info.get("genres", []),
            "image": track["album"]["images"][0]["url"] if track["album"]["images"] else None
        })

    return jsonify({"recently_played": results})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)