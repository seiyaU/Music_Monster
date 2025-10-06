import os
from flask import Flask, redirect, request, jsonify, session
from spotipy.oauth2 import SpotifyOAuth
import spotipy

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# 環境変数の設定（Renderの環境変数を使用）
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
SCOPE = "user-read-recently-played user-top-read user-read-private"

@app.route("/")
def index():
    return "Spotify Login API is running"

@app.route("/login")
def login():
    print("DEBUG ENV CLIENT_ID:", CLIENT_ID)
    print("DEBUG ENV REDIRECT_URI:", REDIRECT_URI)

    if not CLIENT_ID or not CLIENT_SECRET or not REDIRECT_URI:
        return jsonify({"error": "Missing Spotify credentials"}), 500

    sp_oauth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE
    )
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing authorization code"}), 400

    sp_oauth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE
    )

    token_info = sp_oauth.get_access_token(code, check_cache=False)
    if not token_info:
        return jsonify({"error": "Failed to get access token"}), 500

    # Flaskのセッションにトークン保存
    session["token_info"] = token_info

    # 認可完了後のレスポンス
    return jsonify({"status": "success", "access_token": token_info["access_token"]})

@app.route("/auth-status")
def auth_status():
    """ 認可状況を確認するためのエンドポイント """
    token_info = session.get("token_info")
    if token_info:
        return jsonify({"authenticated": True})
    else:
        return jsonify({"authenticated": False}), 401

@app.route("/user")
def get_user_info():
    """ Spotifyユーザー情報を返す """
    token_info = session.get("token_info")
    if not token_info:
        return jsonify({"error": "Not authenticated"}), 401

    sp = spotipy.Spotify(auth=token_info["access_token"])
    user_info = sp.current_user()
    return jsonify(user_info)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
