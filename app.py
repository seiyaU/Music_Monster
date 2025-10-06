from flask import Flask, redirect, request, jsonify
import os
from spotipy.oauth2 import SpotifyOAuth
import spotipy

app = Flask(__name__)

SCOPE = "user-read-recently-played user-read-private user-top-read"

@app.route("/login")
def login():
    # 各環境変数を関数内で動的に取得
    CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
    CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
    REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")

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
    CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
    CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
    REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")

    sp_oauth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE
    )
    token_info = sp_oauth.get_access_token(code)
    access_token = token_info["access_token"]

    sp = spotipy.Spotify(auth=access_token)
    user = sp.current_user()

    return jsonify({"user_id": user["id"], "display_name": user["display_name"]})

@app.route("/")
def home():
    return "Spotify Auth App is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
