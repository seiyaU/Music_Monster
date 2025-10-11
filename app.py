from flask import Flask, request, redirect, jsonify, send_file, send_from_directory
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from PIL import Image, ImageDraw, ImageFont
import os
import io
import requests

# ✅ 認証済みユーザー情報を保持
sessions = {}

app = Flask(__name__)

# ✅ Render環境変数から取得
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
HF_API_KEY = os.getenv("HF_API_KEY")


@app.route("/")
def home():
    return redirect("/login")

# PWA用のファイルを提供
@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")

@app.route("/serviceWorker.js")
def service_worker():
    return send_from_directory("static", "serviceWorker.js")



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

    # ✅ アクセストークン取得
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

    # 🎯 ログイン後に画像生成ページにリダイレクト
    return redirect(f"/generate/{user_id}")

# AI画像生成エンドポイント
@app.route("/generate/<user_id>")
def generate_image(user_id):
    """Spotify履歴&ベース画像を使ってHugging FaceでAI画像を生成"""

    # セッション確認
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

    # 🎨 ベースとなるテンプレート画像を選択
    character_animal = "cat"  # ← 実際はユーザー設定などで変えられる
    base_image_path = f"animal_templates/{character_animal}.png"

    if not os.path.exists(base_image_path):
        return f"Template not found: {base_image_path}", 404

    # 画像をバイナリで読み込み
    with open(base_image_path, "rb") as f:
        init_image = f.read()

    # ======================
    # 🎨 Hugging Face 画像生成（img2img）
    # ======================
    model_id = "stabilityai/stable-diffusion-img2img"
    prompt = f"A fantasy creature inspired by the song '{song_name}' by {artist_name}, artistic, vivid style"

    headers = {
        "Authorization": f"Bearer {HF_API_KEY}"
    }

    # multipart/form-data形式で送信
    response = requests.post(
        f"https://api-inference.huggingface.co/models/{model_id}",
        headers=headers,
        files={
            "image": ("base.png", init_image, "image/png")
        },
        data={
            "inputs": prompt
        }
    )

    if response.status_code != 200:
        return f"Image generation failed: {response.text}", 500

    # Hugging Faceのレスポンスは画像バイナリ
    image_bytes = response.content

    os.makedirs("static/generated", exist_ok=True)
    output_path = f"static/generated/{user_id}.png"
    with open(output_path, "wb") as f:
        f.write(image_bytes)

    print(f"🎨 画像生成完了: {output_path}")

    # ✅ 自動的に生成画像を表示
    return redirect(f"/{output_path}")



# ======================
# static画像配信
# ======================
@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)


# ======================
# サーバー起動
# ======================
if __name__ == "__main__":
    os.makedirs("static/generated", exist_ok=True)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))