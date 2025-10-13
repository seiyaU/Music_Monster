import base64
import io
import os
import random
import replicate
import requests
from flask import Flask, request, redirect, jsonify, send_from_directory, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import time
import yaml

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

    # 🎨 ベースとなるテンプレート画像を選択
    definition_score = 0
    character_animal = ""
    influenced_word = ""
    influenced_word_box = []

    with open("data/genre_weights.yaml", "r", encoding="utf-8") as f:
        genre_weights = yaml.safe_load(f)

    print("\n🎵 最近再生した曲:")
    for idx, item in enumerate(recent["items"], 1):
        track = item["track"]
        artist = item["track"]["artists"][0]
        artist_info = sp.artist(artist["id"])
        genre = artist_info.get("genres", [])

        print(f"{idx}. {track['name']} / {artist['name']} ({', '.join(genre)})")
        print({track["album"]["images"][0]["url"]})

        influenced_word_box.append(track['name'])
        influenced_word_box.append(artist['name'])
        for i in genre:
            weight = genre_weights.get(i, 0)  # デフォルト値0
            definition_score += weight
            influenced_word_box.append(i)
            print(f"   - {i}: {weight}")

        if artist["name"] == "The Beatles":
            definition_score += 50

    # 動物の確定
    if definition_score <= 500:
        character_animal = "bug"
    elif definition_score <= 1000:
        character_animal = "fish"
    elif definition_score <= 1500:
        character_animal = "octopus"    
    elif definition_score <= 2000:
        character_animal = "crab"
    elif definition_score <= 3000:
        character_animal = "frog"
    elif definition_score <= 4000:
        character_animal = "snake"
    elif definition_score <= 8000:
        character_animal = "horse"
    elif definition_score <= 9000:
        character_animal = "dog"
    elif definition_score <= 13000:
        character_animal = "cat"
    else:
        character_animal = "dragon"

    base_image_path = f"static/animal_templates/{character_animal}.png"
    influenced_word = random.choice(influenced_word_box)

    print(f"\n🏆 あなたの音楽定義スコア: {definition_score}")
    print(character_animal)
    print(influenced_word)

    prompt = (
        f"The creature in {base_image_path} is standing by their two legs and grabs a sword in its hands."
        f"This has dark atmosphere and has information relevant to the word of {influenced_word}, "
        f"designed like monsters in SF or horror films."
    )
    print(f"🧠 Prompt: {prompt}")

    if not os.path.exists(base_image_path):
        return f"Template not found: {base_image_path}", 404
    
    # ✅ Render上のURLに変換（Replicateからアクセス可能にする）
    base_url = request.url_root.rstrip("/")
    image_url = f"{base_url}/{base_image_path}"

    print(f"🧩 Using image URL for Replicate: {image_url}")

    replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)

    try:
        print("🚀 画像生成リクエスト送信中...")
        prediction = replicate_client.predictions.create(
            version="6a52feace43ce1f6bbc2cdabfc68423cb2319d7444a1a1dae529c5e88b976382",  
            input={
                "prompt": prompt,
                "image": image_url,
                "num_outputs": 1,
                "width": 512,
                "height": 512,
                "strength": 0.6
            },
        )
    except Exception as e:
        print("❌ Replicate API request failed:", e)
        return jsonify({"status": "failed", "image_url": None}), 500

    prediction_id = prediction.id
    print(f"🕒 Prediction ID: {prediction_id}")



    # 🔁 Pollingして結果待ち（最大60秒）
    timeout = time.time() + 60
    while time.time() < timeout:
        prediction = replicate_client.predictions.get(prediction_id)
        status = prediction.status
        if status == "succeeded":
            output_url = prediction.output[0]
            print(f"✅ 生成成功: {output_url}")
            return jsonify({
                "status": "succeeded",
                "image_url": output_url
            })
        elif status == "failed":
            print(f"❌ Replicate側で失敗: {prediction.error}")
            return jsonify({
                "status": "failed",
                "error": prediction.error,
                "image_url": None
            })
        time.sleep(3)

    # ⏰ タイムアウト
    print("⚠️ タイムアウト: 60秒経過")
    return jsonify({"status": "timeout", "image_url": None})

    
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
