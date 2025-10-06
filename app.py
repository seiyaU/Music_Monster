from flask import Flask, redirect, request, jsonify
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os

app = Flask(__name__)

# Spotify API credentials（環境変数に設定）
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = "https://music-cat-7r71.onrender.com/callback"

# 認証スコープ
SCOPE = "user-read-recently-played user-top-read user-library-read"

# グローバルに認証状態を保持（簡易セッション管理）
auth_state = {
    "authenticated": False,
    "user_id": None,
    "token_info": None
}

# 🔹 Spotify 認証開始
@app.route("/login")
def login():
    sp_oauth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE
    )
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)


# 🔹 Spotify コールバック処お理
@app.route("/callback")
def callback():
    sp_oauth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE
    )

    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing authorization code"}), 400

    try:
        token_info = sp_oauth.get_access_token(code)
        sp = spotipy.Spotify(auth=token_info["access_token"])
        user_profile = sp.current_user()

        # ユーザー情報を保持
        auth_state["authenticated"] = True
        auth_state["user_id"] = user_profile["id"]
        auth_state["token_info"] = token_info

        return jsonify({
            "status": "success",
            "user_id": user_profile["id"],
            "display_name": user_profile.get("display_name"),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 🔹 認証状態を返す
@app.route("/auth-status")
def auth_status():
    return jsonify({
        "authenticated": auth_state["authenticated"],
        "user_id": auth_state["user_id"]
    })


# 🔹 最近再生した楽曲を取得
@app.route("/recent/<user_id>")
def recent_tracks(user_id):
    if not auth_state["authenticated"] or auth_state["user_id"] != user_id:
        return jsonify({"error": "User not authenticated"}), 401

    try:
        token_info = auth_state["token_info"]
        sp = spotipy.Spotify(auth=token_info["access_token"])
        results = sp.current_user_recently_played(limit=10)

        tracks = []
        for item in results["items"]:
            track = item["track"]
            artist_id = track["artists"][0]["id"]
            artist_info = sp.artist(artist_id)

            tracks.append({
                "name": track["name"],
                "artist": track["artists"][0]["name"],
                "genres": artist_info.get("genres", []),
                "image": track["album"]["images"][0]["url"] if track["album"]["images"] else None
            })

        return jsonify({"recently_played": tracks})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 🔹 Renderデフォルトの起動設定
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
