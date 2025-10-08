from flask import Flask, request, jsonify, redirect
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import os

app = Flask(__name__)

# ✅ Render環境変数から取得
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "https://music-cat-7r71.onrender.com/callback")

# 認証済みユーザー情報を保持（stateごと）
sessions = {}

@app.route("/")
def home():
    return "✅ Spotify OAuth Server Running"


@app.route("/login")
def login():
    import uuid
    state = request.args.get("state") or str(uuid.uuid4())  # ← クライアントが指定したstateを尊重

    sp_oauth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope="user-read-recently-played user-read-email",
        cache_path=None
    )

    # ✅ SpotifyOAuthの内部stateを上書きしないように、自分でURLを構築
    auth_url = (
        f"https://accounts.spotify.com/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&scope=user-read-recently-played%20user-read-email"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={state}"
    )

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
        cache_path=None,
        state=state
    )

    token_info = sp_oauth.get_access_token(code, as_dict=True)
    access_token = token_info["access_token"]

    # ✅ ここでSpotify APIからユーザー情報を取得
    sp = Spotify(auth=access_token)
    user_profile = sp.me()
    user_id = user_profile["id"]

    # ✅ 保存（stateごとにユーザーIDとトークン）
    sessions[state] = {
        "user_id": user_id,
        "access_token": access_token,
        "authenticated": True
    }

    sessions[user_id] = {
    "access_token": token_info["access_token"],
    "refresh_token": token_info["refresh_token"],
    "expires_at": token_info["expires_at"],
}


    return jsonify({
        "status": "success",
        "user_id": user_id,
        "access_token": access_token
    })


@app.route("/auth-status")
def auth_status():
    state = request.args.get("state")
    if state in sessions and sessions[state]["authenticated"]:
        return jsonify({
            "authenticated": True,
            "user_id": sessions[state]["user_id"]
        })
    return jsonify({"authenticated": False}), 404


@app.route("/recent/<user_id>")
def recent_tracks(user_id):
    session_data = next((v for v in sessions.values() if v.get("user_id") == user_id), None)

    # 🔸 トークンが存在しない → 自動で /login にリダイレクト
    if not session_data or "access_token" not in session_data:
        print(f"⚠️ トークン未登録: {user_id} → /login にリダイレクトします")
        return redirect("/login")

    access_token = session_data["access_token"]

    # 🎯 トークンの有効期限が切れていたらリフレッシュ（自動更新）
    if "expires_at" in session_data:
        from time import time
        if time() > session_data["expires_at"]:
            print(f"🔁 トークン期限切れ、リフレッシュ中: {user_id}")
            sp_oauth = SpotifyOAuth(
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                redirect_uri=REDIRECT_URI,
                scope="user-read-recently-played user-read-email"
            )
            try:
                token_info = sp_oauth.refresh_access_token(session_data["refresh_token"])
                session_data["access_token"] = token_info["access_token"]
                session_data["expires_at"] = token_info["expires_at"]
                sessions[user_id] = session_data  # 更新を保存
                access_token = token_info["access_token"]
                print("✅ トークン更新成功")
            except Exception as e:
                print(f"❌ トークン更新失敗: {e}")
                return redirect("/login")

    # 🎯 Spotify API 呼び出し
    sp = Spotify(auth=access_token)
    try:
        recent = sp.current_user_recently_played(limit=50)
    except Exception as e:
        print(f"❌ Spotify API エラー: {e}")
        return redirect("/login")

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
