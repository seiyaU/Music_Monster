from flask import Flask, request, jsonify, session
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"  # セッション用

# 環境変数で管理（Renderの設定で追加）
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.environ.get("SPOTIPY_REDIRECT_URI")

SCOPE = "user-read-recently-played"

@app.route("/recent", methods=["GET"])
def recent_tracks():
    auth_header = request.headers.get("Authorization", None)
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    access_token = auth_header.split(" ")[1]

    sp = spotipy.Spotify(auth=access_token)

    try:
        results = sp.current_user_recently_played(limit=10)
    except spotipy.SpotifyException as e:
        return jsonify({"error": str(e)}), 400

    tracks_info = []
    for item in results.get("items", []):
        track = item["track"]
        artist_id = track["artists"][0]["id"]
        artist_info = sp.artist(artist_id)

        tracks_info.append({
            "name": track["name"],
            "artist": track["artists"][0]["name"],
            "genres": artist_info.get("genres", []),
            "image": track["album"]["images"][0]["url"] if track["album"]["images"] else ""
        })

    return jsonify({"recently_played": tracks_info})


@app.route("/login")
def login():
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope=SCOPE
    )
    auth_url = sp_oauth.get_authorize_url()
    return jsonify({"url": auth_url})


@app.route("/auth-status")
def auth_status():
    token_info = session.get("token_info")
    if token_info:
        return jsonify({"authenticated": True, "access_token": token_info.get("access_token")})
    return jsonify({"authenticated": False}), 200  # ここを200に変更



@app.route("/auth-callback")
def auth_callback():
    code = request.args.get("code")
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope=SCOPE
    )
    token_info = sp_oauth.get_access_token(code)
    session["token_info"] = token_info
    return jsonify({"authenticated": True, "access_token": token_info["access_token"]})

