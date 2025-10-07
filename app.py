import os
import json
import uuid
from flask import Flask, request, redirect, jsonify
import requests

app = Flask(__name__)

# 環境変数から取得
CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("SPOTIPY_REDIRECT_URI")

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

# 認証ステータス保存
auth_sessions = {}

@app.route("/login")
def login():
    state = str(uuid.uuid4())
    auth_sessions[state] = {"authenticated": False}

    scope = "user-read-recently-played"
    auth_query = (
        f"{AUTH_URL}?response_type=code&client_id={CLIENT_ID}"
        f"&scope={scope}&redirect_uri={REDIRECT_URI}&state={state}"
    )
    return redirect(auth_query)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")

    if not code or not state or state not in auth_sessions:
        return "認証エラー", 400

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    res = requests.post(TOKEN_URL, data=data, headers=headers)
    if res.status_code != 200:
        return f"トークン取得エラー: {res.text}", 400

    tokens = res.json()
    access_token = tokens.get("access_token")
    if not access_token:
        return "アクセストークンが取得できませんでした", 400

    # ユーザー情報取得
    profile_res = requests.get(
        "https://api.spotify.com/v1/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if profile_res.status_code != 200:
        return "ユーザー情報取得エラー", 400

    profile = profile_res.json()
    user_id = profile.get("id")

    # 認証状態保存
    auth_sessions[state] = {
        "authenticated": True,
        "user_id": user_id,
        "access_token": access_token
    }

    return """
    <html>
    <body>
    <h2>認証成功！</h2>
    <p>このウィンドウを閉じて extraction.py を続けてください。</p>
    </body>
    </html>
    """

@app.route("/auth-status")
def auth_status():
    for state, info in auth_sessions.items():
        if info["authenticated"]:
            return jsonify({"authenticated": True, "user_id": info["user_id"]})
    return jsonify({"authenticated": False})

@app.route("/recent/<user_id>")
def recent_tracks(user_id):
    access_token = None
    for info in auth_sessions.values():
        if info.get("user_id") == user_id:
            access_token = info.get("access_token")
            break

    if not access_token:
        return jsonify({"error": "アクセストークンが見つかりません"}), 400

    res = requests.get(
        "https://api.spotify.com/v1/me/player/recently-played?limit=10",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if res.status_code != 200:
        return jsonify({"error": res.text}), res.status_code

    items = res.json().get("items", [])
    recent = []
    for item in items:
        track = item.get("track", {})
        recent.append({
            "name": track.get("name"),
            "artist": ", ".join([a.get("name", "") for a in track.get("artists", [])]),
            "genres": [],  
            "image": track.get("album", {}).get("images", [{}])[0].get("url", "")
        })

    return jsonify({"recently_played": recent})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
