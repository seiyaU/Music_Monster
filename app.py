import base64
import os
import random
import requests
from flask import Flask, request, redirect, jsonify, send_from_directory, render_template, session
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from flask_session import Session
import redis
import time
import yaml
from PIL import Image
from io import BytesIO

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")

# Redis + Flask-Session 設定
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_REDIS"] = redis.from_url(os.getenv("REDIS_URL"))
app.config["SESSION_KEY_PREFIX"] = "spotify_session:"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True

Session(app)

try:
    with open("data/genre_weights.yaml", "r", encoding="utf-8") as f:
        genre_weights = yaml.safe_load(f)
except Exception as e:
    genre_weights = {}
    print("⚠️ genre_weights.yaml の読み込みに失敗:", e)

# ✅ Render環境変数から取得
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

sp_oauth = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope="user-read-recently-played user-read-email"
)


@app.route("/")
def home():
    return redirect("/login")

# ################# Spotify認証 #################
@app.route("/login")
def login():
    return redirect(sp_oauth.get_authorize_url())

@app.route("/callback")
def callback():
    code = request.args.get("code")
    token_info = sp_oauth.get_access_token(code, as_dict=True)
    access_token = token_info.get("access_token")
    if not access_token:
        return f"Failed to obtain access token: {token_info}", 400

    # ✅ Spotify API でユーザー情報取得
    sp = Spotify(auth=access_token)
    user = sp.me()
    user_id = user["id"]

    # ✅ Redis-backed session に保存
    session["user_id"] = user_id
    session["access_token"] = access_token
    session["refresh_token"] = token_info.get("refresh_token")
    session["expires_at"] = token_info.get("expires_at")

    print(f"✅ 認証成功: {user_id}")
    return redirect(f"/generate/{user_id}")

# AI画像生成エンドポイント
@app.route("/generate_api/<user_id>", methods=["GET"])
def generate_image(user_id):

    if session.get("user_id") != user_id:
        return jsonify({"status": "login_required"}), 401

    
    # トークン有効期限チェック
    if time.time() > session.get("expires_at", 0):
        refresh_token = session.get("refresh_token")
        new_token = sp_oauth.refresh_access_token(refresh_token)
        session["access_token"] = new_token["access_token"]
        session["expires_at"] = new_token["expires_at"]

    access_token = session.get("access_token")
    sp = Spotify(auth=access_token)

    # 🎵 最近再生曲を取得
    recent = sp.current_user_recently_played(limit=50)

    if not recent.get("items"):
        return "No recent tracks found.", 404

    # 🎨 ベースとなるテンプレート画像を選択
    definition_score = 0
    character_animal = ""
    influenced_word = ""
    influenced_word_box = []
    album_image_url = ""
    album_image_url_box = []

    
    print("\n🎵 最近再生した曲:")
    for idx, item in enumerate(recent["items"], 1):
        track = item["track"]
        artist = item["track"]["artists"][0]
        artist_info = sp.artist(artist["id"])
        genre = artist_info.get("genres", [])
        album_image_url_box.append(track['album']['images'][0]['url'])
        influenced_word_box.append(track['name'])
        influenced_word_box.append(artist['name'])
        print(f"{idx}. {track['name']} / {artist['name']} ({', '.join(genre)})")

        for i in genre:
            definition_score += genre_weights.get(i, 0)  # デフォルト値0
            influenced_word_box.append(i)
            print(f"   - {i}: {genre_weights.get(i, 0)}")

        if artist["name"] == "The Beatles":
            definition_score += 30

    # 動物の確定
    if definition_score <= 1000:
        character_animal = "bug"
    elif definition_score <= 2000:
        character_animal = "seal"
    elif definition_score <= 3000:
        character_animal = "octopus"    
    elif definition_score <= 4000:
        character_animal = "crab"
    elif definition_score <= 5000:
        character_animal = "frog"
    elif definition_score <= 6000:
        character_animal = "snake"
    elif definition_score <= 7000:
        character_animal = "horse"
    elif definition_score <= 8000:
        character_animal = "seal"
    elif definition_score <= 9000:
        character_animal = "dog"
    elif definition_score <= 10000:
        character_animal = "T-rex"
    elif definition_score <= 11000:
        character_animal = "cat"
    else:
        character_animal = "dragon"

    if user_id == "noel1109.marble1101":
        character_animal = "fish"

    base_image_path = f"animal_templates/{character_animal}.png"
    if not os.path.exists(base_image_path):
        return f"Template not found: {base_image_path}", 404
    
    influenced_word = random.choice(influenced_word_box)
    album_image_url = random.choice(album_image_url_box)

    print(f"\n🏆 あなたの音楽定義スコア: {definition_score}")
    print(character_animal)
    print(influenced_word)
    print(album_image_url)

    # 3:4 比率にリサイズ（幅768, 高さ1024など）
    img = Image.open(base_image_path)
    new_img = img.resize((768, 1024))
    buffer = BytesIO()
    new_img.save(buffer, format="PNG")
    image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    image_data_uri = f"data:image/png;base64,{image_b64}"

    prompt = (
        f"Legendary creature in {character_animal} of picture is a soldier or knight of alien with some weapons from a dark and mysterious world."
        f"It like {influenced_word} and background image is {album_image_url} "
        f"and designed like creepy spooky monsters in SF or horror films but not cartoonish rather realistic."
    )
    print(prompt)

    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    MODEL_VERSION = random.choice([
        "17658fb151a7dd2fe9a0043990c24913d7b97a6b35dcd953a27a366fedc4e20a",
        "294de709b06655e61bb0149ec61ef8b5d3ca030517528ac34f8252b18b09b7ad",
        "535fdb4d34d13e899f8a61c3172ef1698230bed3c2faa0a17708abde760a5f64",
        "40ab9b32cc4584bc069e22027fffb97e79ed550d4e7c20ed6d5d7ef89e8f08f5",
        "e57c2dfbc48a476779abad3b6695839ecb779c18d0ec95f16d1f677a99cb3a42",
        "08ea3dfde168eed9cdc4956ba0e9a506f56c9f74f96c0809a3250d10a9c77986",

        "fdc7a34e44fd97c0a6a1f1ef72b68bcf2e2eb3be0c0246f036f298a363ea256c",
        "d53918f6a274da520ba36474408999d2f91ea9c2c5afb17abef15c6c42030963",
        "262c44d38a47d71dc0168728963b5549666a5be21d1a04b87675d3f682ed7267"
    ])
    MODEL_VERSION = "fdc7a34e44fd97c0a6a1f1ef72b68bcf2e2eb3be0c0246f036f298a363ea256c"

    payload = {
        "version": MODEL_VERSION,
        "input": {
            "prompt": prompt,
            "image": image_data_uri,
            "strength": 0.6,
            "num_outputs": 1,
            "aspect_ratio": "3:4"
        }
    }

    # ✅ 非同期でpredictionを作成
    res = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload, timeout=120)
    if res.status_code != 201:
        return f"Image generation failed: {res.text}", 500

    prediction = res.json()
    return jsonify({
        "prediction_id": prediction["id"],
        "status_url": f"/result/{prediction["id"]}"
    })
    
@app.route("/generate/<user_id>")
def generate_page(user_id):
    return render_template("generate.html", user_id=user_id)

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
# Render用 Health Check
# =====================
@app.route("/health")
def health_check():
    return jsonify({"status": "ok"}), 200



# =====================
# サーバー起動
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
