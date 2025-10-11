from flask import Flask, request, jsonify, redirect, render_template, send_from_directory, url_for
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import os
import uuid
from time import time
import base64
from io import BytesIO
from flask import send_file
from PIL import Image, ImageDraw, ImageFont
import requests



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
    sp_oauth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope="user-read-recently-played user-read-email",
        cache_path=None
    )
    # ✅ 認可URLを自分で構築
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

    print(f"✅ 認証成功: {user_id}")

    # 🎯 ログイン後に画像生成ページにリダイレクト
    return redirect(f"/generate/{user_id}")

@app.route("/generate/<user_id>")
def generate_image(user_id):
    """
    仮の画像生成ページ。
    実際はここでAI画像生成を行ってURLを返す。
    """
    session = sessions.get(user_id)
    if not session:
        return redirect("/login")

    # 🎨 ここにAI画像生成または既存画像編集の処理を実装
    # 例: CloudinaryやStableDiffusion APIなどを使う
    image_url = f"https://dummyimage.com/512x512/000/fff.png&text={user_id}"

    # 🎯 自動的に画像URLにリダイレクト
    return redirect(image_url)

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


# ################# 画像生成 #################
@app.route("/generate-image", methods=["POST"])
def generate_image():
    """
    クライアントから `character_animal` と `influenced_word` を受け取り、
    既存の画像（例：animal_templates/{animal}.png）をもとに
    AI的な合成風の画像を生成（ここでは擬似的にPILで文字追加）
    """

    data = request.get_json()
    character_animal = data.get("character_animal")
    influenced_word = data.get("influenced_word")

    # 🐾 ベース画像を取得
    base_path = f"animal_templates/{character_animal}.png"
    if not os.path.exists(base_path):
        return jsonify({"error": "Base image not found"}), 404

    img = Image.open(base_path).convert("RGBA")

    # 🎨 文字を描画（簡易AI風合成）
    draw = ImageDraw.Draw(img)
    text = f"Inspired by {influenced_word}"
    draw.text((30, 30), text, fill=(255, 255, 255, 255))

    # 🔄 画像を一時保存して返す
    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)

    return send_file(output, mimetype="image/png")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)