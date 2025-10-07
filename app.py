import os
from flask import Flask, redirect, request, jsonify
from flask_cors import CORS
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

app = Flask(__name__)
CORS(app)

# --- ユーザーごとにトークンを保持 ---
TOKENS = {}

# --- Spotify OAuth 設定 ---
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "https://music-cat-7r71.onrender.com/callback")

SCOPE = "user-read-recently-played user-read-private user-read-email"

def create_spotify_oauth(state=None):
    return SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope=SCOPE,
        state=state
    )

# ------------------------------
# 🌐 認証フロー
# ------------------------------

@app.route("/login")
def login():
    """
    クライアントごとにユニークな state（例：UUIDやユーザーID）を指定してリダイレクト。
    ここでは簡易的にリクエストパラメータから受け取る形式。
    例: /login?state=noel1109.marble1101
    """
    state = request.args.get("state", "default_user")
    sp_oauth = create_spotify_oauth(state)
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)


@app.route("/callback")
def callback():
    """
    Spotify 認証後に呼ばれる。
    code と state を受け取り、アクセストークンを保存。
    """
    sp_oauth = create_spotify_oauth()
    code = request.args.get("code")
    state = request.args.get("state", "default_user")

    token_info = sp_oauth.get_access_token(code)
    if not token_info:
        return jsonify({"error": "Failed to retrieve token"}), 400

    access_token = token_info["access_token"]

    # state をキーに保存（ユーザーごとに独立）
    TOKENS[state] = access_token

    # トークンを返す
    return jsonify({"status": "success", "user_id": state, "access_token": access_token})


@app.route("/auth-status")
def auth_status():
    """
    クライアントが state を指定して認証状態を確認する。
    例: /auth-status?state=noel1109.marble1101
    """
    state = request.args.get("state", "default_user")
    if state in TOKENS:
        return jsonify({"authenticated": True, "user_id": state})
    return jsonify({"authenticated": False}), 404


# ------------------------------
# 🎵 最近再生した楽曲を取得（ユーザー別）
# ------------------------------

@app.route("/recent/<user_id>")
def recent_tracks(user_id):
    """
    特定ユーザー（user_id）の最近再生曲を取得。
    """
    access_token = TOKENS.get(user_id)
    if not access_token:
        return jsonify({"error": f"No authenticated user found for {user_id}"}), 401

    sp = Spotify(auth=access_token)
    try:
        items = sp.current_user_recently_played(limit=10)["items"]
    except Exception as e:
        return jsonify({"error": f"Spotify API error: {str(e)}"}), 500

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
    return "✅ Multi-user Spotify API Server running on Render"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
