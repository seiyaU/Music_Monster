from flask import Flask, request, redirect, jsonify, send_from_directory, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import os
import requests
import time
import base64

# ✅ 認証済みユーザー情報を保持
sessions = {}

app = Flask(__name__)

# ✅ Render環境変数から取得
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")


@app.route("/")
def home():
    return redirect("/login")


# ################# Spotify認証 #################
@app.route("/login")
def login():
    sp_oauth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope="user-read-recently-played user-read-email",
        cache_path=None
    )
    return redirect(sp_oauth.get_authorize_url())

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Spotify authorization failed.", 400

    sp_oauth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope="user-read-recently-played user-read-email",
        cache_path=None
    )

    token_info = sp_oauth.get_access_token(code, as_dict=True)
    access_token = token_info["access_token"]
    if not access_token:
        return f"Failed to obtain access token: {token_info}", 400

    # ✅ Spotify API でユーザー情報取得
    sp = Spotify(auth=access_token)
    user = sp.me()
    user_id = user["id"]

    # ✅ ユーザー情報を保存
    sessions[user_id] = {
        "access_token": access_token,
        "refresh_token": token_info["refresh_token"],
        "expires_at": token_info["expires_at"]
    }

    print(f"✅ 認証成功: {user_id}")
    return redirect(f"/generate/{user_id}")

# AI画像生成エンドポイント
@app.route("/generate_api/<user_id>", methods=["GET"])
def generate_image(user_id):

    session_data = sessions.get(user_id)
    if not session_data:
        return redirect("/login")

    access_token = session_data["access_token"]
    sp = Spotify(auth=access_token)

    # 🎵 最近再生曲を取得
    recent = sp.current_user_recently_played(limit=50)
    if "items" not in recent or len(recent["items"]) == 0:
        return "No recent tracks found.", 404

    track = recent["items"][0]["track"]
    song_name = track["name"]
    artist_name = track["artists"][0]["name"]

    print(f"🎵 Generating remix for: {song_name} by {artist_name}")

    # 🎨 ベースとなるテンプレート画像を選択
    character_animal = "cat"  # ← 実際はユーザー設定などで変えられる
    base_image_path = f"animal_templates/{character_animal}.png"

    if not os.path.exists(base_image_path):
        return f"Template not found: {base_image_path}", 404
    


    with open(base_image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
        image_data_uri = f"data:image/png;base64,{image_b64}"

    prompt = (
        f"A vivid artistic portrait of a {character_animal} inspired by the song "
        f"'{song_name}' by {artist_name}, in a fantasy vibrant style, cinematic lighting"
    )

    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    MODEL_VERSION = "232569243dacecab70a4475be391353ad9b42819617225848847f28752205acf"

    payload = {
        "version": MODEL_VERSION,
        "input": {
            "prompt": prompt,
            "image": image_data_uri,
            "strength": 0.6,
            "num_outputs": 1
        }
    }

    # ✅ 非同期でpredictionを作成
    res = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
    if res.status_code != 201:
        data = res.json()
        print("🚨 Replicate error:", data)
        return f"Image generation failed: {data}", 500

    prediction = res.json()
    prediction_id = prediction["id"]
    return jsonify({
        "prediction_id": prediction_id,
        "status_url": f"/result/{prediction_id}"
    })
    
@app.route("/generate/<user_id>")
def generate_page(user_id):
    return render_template("generate.html")


# =====================
# 生成結果ポーリング
# =====================
@app.route("/result/<prediction_id>", methods=["GET"])
def get_result(prediction_id):
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
    }
    res = requests.get(f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers)
    if res.status_code != 200:
        return f"Failed to fetch prediction: {res.text}", 500

    data = res.json()
    if data["status"] == "succeeded":
        # 出力URLを返す
        return jsonify({
            "status": data["status"],
            "image_url": data["output"][0]
        })
    else:
        return jsonify({
            "status": data["status"],
            "image_url": None
        })


# =====================
# PWA用ファイル・静的配信
# =====================
@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")

@app.route("/serviceWorker.js")
def service_worker():
    return send_from_directory("static", "serviceWorker.js")

@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)


# =====================
# サーバー起動
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
