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
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw, ImageFont
from io import BytesIO
import json
import numpy as np  # ✅ ノイズ生成に利用
from decimal import Decimal
import re
from uuid import uuid4

def add_glitter_effect(base_image, glitter_density=0.009, blur=0.9, alpha=225):
    """画像全体にグリッターを重ねる"""
    width, height = base_image.size
    glitter_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glitter_layer)

    num_glitters = int(width * height * glitter_density)

    for _ in range(num_glitters):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        size = random.choice([6, 5, 2, 3])
        color = random.choice([
            (255, 255, 255, random.randint(150, 220)),  # 白
            (255, 215, 0, random.randint(130, 200)),    # 金
            (173, 216, 230, random.randint(120, 180)),  # 水色
            (255, 182, 193, random.randint(120, 180)),  # ピンク
        ])
        draw.ellipse((x, y, x + size, y + size), fill=color)

    glitter_layer = glitter_layer.filter(ImageFilter.GaussianBlur(blur))
    combined = Image.alpha_composite(base_image.convert("RGBA"), glitter_layer)
    return combined


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")

# Redis + Flask-Session 設定
redis_client = redis.from_url(os.getenv("REDIS_URL"))
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_REDIS"] = redis_client
app.config["SESSION_KEY_PREFIX"] = "spotify_session:"  # ✅ ユーザー単位で独立
app.config["SESSION_COOKIE_NAME"] = "spotify_session_" + os.urandom(8).hex()
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 7 
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_COOKIE_DOMAIN"] = None  # ✅ サブドメイン間共有防止（Safari対策）
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True  # ✅ HTTPS環境で安全に送信

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

# SpotifyOAuth を動的生成（重要）
def get_spotify_oauth():
    """ユーザーごとに独立したSpotifyOAuthインスタンスを生成"""
    return SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope="user-read-recently-played user-read-email"
    )


def get_catalog_access_token():
    """Return a short-lived app token for public Spotify catalog metadata.

    Import mode never receives a user's Spotify token.  The client secret stays
    on the server and this token is used only for track/artist catalog lookups.
    """
    cache_key = "spotify:catalog_access_token"
    cached_token = redis_client.get(cache_key)
    if cached_token:
        return cached_token.decode("utf-8") if isinstance(cached_token, bytes) else cached_token

    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("Spotify catalog credentials are not configured")

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(CLIENT_ID, CLIENT_SECRET),
        timeout=15,
    )
    response.raise_for_status()
    token_data = response.json()
    access_token = token_data["access_token"]
    # Keep a small safety margin before Spotify's one-hour expiry.
    redis_client.setex(cache_key, max(int(token_data.get("expires_in", 3600)) - 60, 60), access_token)
    return access_token


def get_catalog_tracks(track_ids):
    """Fetch Spotify catalog tracks and preserve the supplied listening order."""
    access_token = get_catalog_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    tracks_by_id = {}

    # Spotify accepts up to 50 IDs per catalog request.
    unique_ids = list(dict.fromkeys(track_ids))
    for index in range(0, len(unique_ids), 50):
        batch = unique_ids[index:index + 50]
        response = requests.get(
            "https://api.spotify.com/v1/tracks",
            headers=headers,
            params={"ids": ",".join(batch)},
            timeout=15,
        )
        response.raise_for_status()
        for track in response.json().get("tracks", []):
            if track:
                tracks_by_id[track["id"]] = track

    return [tracks_by_id[track_id] for track_id in track_ids if track_id in tracks_by_id]

@app.route("/")
def home():
    return render_template("index.html")

# ################# Spotify認証 #################
@app.route("/login")
def login():
    sp_oauth = get_spotify_oauth()
    return redirect(sp_oauth.get_authorize_url())

@app.route("/callback")
def callback():
    code = request.args.get("code")
    sp_oauth = get_spotify_oauth()
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

# =====================
# セッション確認API（フロントの「Start with Spotify」用）
# =====================
@app.route("/session-check")
def session_check():
    user_id = session.get("user_id")
    if user_id:
        return jsonify({"logged_in": True, "user_id": user_id})
    return jsonify({"logged_in": False})


@app.route("/import-history", methods=["POST"])
def import_history():
    """Create a short-lived generation session from browser-parsed history.

    Only Spotify track IDs are accepted.  The raw JSON file, timestamps,
    country, device details, and account name never reach this endpoint.
    """
    payload = request.get_json(silent=True) or {}
    submitted_ids = payload.get("track_ids", [])
    if not isinstance(submitted_ids, list):
        return jsonify({"error": "track_ids must be a list"}), 400

    track_ids = []
    for track_id in submitted_ids:
        if isinstance(track_id, str) and re.fullmatch(r"[A-Za-z0-9]{22}", track_id):
            track_ids.append(track_id)
        if len(track_ids) == 50:
            break

    if not track_ids:
        return jsonify({"error": "No Spotify music track IDs were found in this file."}), 400

    try:
        catalog_tracks = get_catalog_tracks(track_ids)
    except requests.RequestException as exc:
        print("Spotify catalog lookup failed:", exc)
        return jsonify({"error": "Spotify catalog data could not be retrieved. Please try again later."}), 502
    except RuntimeError as exc:
        print("Spotify catalog configuration error:", exc)
        return jsonify({"error": "Spotify catalog lookup is not configured yet."}), 503

    if not catalog_tracks:
        return jsonify({"error": "The selected history did not contain available Spotify music tracks."}), 400

    import_id = uuid4().hex
    user_id = f"history-{import_id[:8]}"
    # Match Spotify's recently-played response shape so the existing scoring and
    # image-generation code can be reused unchanged.
    recent = {"items": [{"track": track} for track in catalog_tracks]}
    redis_client.setex(f"recently_played:{user_id}", 1800, json.dumps(recent))

    session.clear()
    session["user_id"] = user_id
    session["import_mode"] = True
    return jsonify({"generate_url": f"/generate/{user_id}", "tracks_found": len(catalog_tracks)})

# AI画像生成エンドポイント
@app.route("/generate_api/<user_id>", methods=["GET"])
def generate_image(user_id):
    try:
        # ✅ セッション検証（他人のデータを防ぐ）
        current_user = session.get("user_id")
        print("セッションからユーザーを取得できた")
        if not current_user or current_user != user_id:
            print("❌ セッション不一致: 他ユーザーアクセス検出")
            return jsonify({"status": "login_required"}), 401
        
        import_mode = session.get("import_mode", False)
        if import_mode:
            # JSON import mode uses only public catalog metadata; no Spotify user
            # login or user access token is needed.
            sp = Spotify(auth=get_catalog_access_token())
            print("Spotify catalog data is ready for imported history")
        else:
            # トークン有効期限チェック
            if time.time() > session.get("expires_at", 0):
                sp_oauth = get_spotify_oauth()
                refresh_token = session.get("refresh_token")
                new_token = sp_oauth.refresh_access_token(refresh_token)
                session["access_token"] = new_token["access_token"]
                session["expires_at"] = new_token["expires_at"]

            access_token = session.get("access_token")
            if not access_token:
                return jsonify({"error": "No valid access token"}), 401

            sp = Spotify(auth=access_token)
            print("Spotifyからデータ取得できた")

        # ===============================
        # 🟢 Spotify再生履歴のキャッシュ処理
        # ===============================
        cache_key = f"recently_played:{user_id}"
        cached_data = redis_client.get(cache_key)

        if cached_data:
            recent = json.loads(cached_data)
            print("🟢 Redisキャッシュから再生履歴を取得")
        elif not import_mode:
            print("🟠 Spotify APIから再生履歴を取得")
            try:
                recent = sp.current_user_recently_played(limit=50)
                redis_client.setex(cache_key, 1800, json.dumps(recent))  
            except Exception as e:
                print("🚨 Spotify API error:", e)
                return jsonify({"error": "Spotify data fetch failed"}), 500
        else:
            return jsonify({"error": "Imported history has expired. Please import the JSON file again."}), 410

        if not recent.get("items"):
            return "No recent tracks found.", 404
        
        # ✅ Redis に保存（10分キャッシュ）
        redis_client.setex(cache_key, 1800, json.dumps(recent))

        # 🎨 ベースとなるテンプレート画像を選択
        definition_score = 0
        influenced_word_box = []
        album_image_url_box = []
        creature_name = ""
        artist_ids = []
        artist_info_box = []

        
        print("\n🎵 最近再生した曲:")
        # 🎵 アーティストIDを抽出（重複除去）
        for item in recent["items"]:
            artist = item["track"]["artists"][0]
            artist_ids.append(artist["id"])
            track = item["track"]
            genre = artist.get("genres", [])

            album_image_url_box.append(track['album']['images'][0]['url'])
            influenced_word_box.append(track['name'])
            influenced_word_box.append(artist['name'])

            artist_ids = list(artist_ids)

            print(f"{track['name']} / {artist['name']} ({', '.join(genre)})")
            # ===============================
            # 🧠 アーティスト情報を一括取得＋キャッシュ
            # ===============================
            artist_info_box = []
            uncached_ids = []
            for aid in artist_ids:
                cached_artist = redis_client.get(f"artist_info:{aid}")
                if cached_artist:
                    artist_info_box.append(json.loads(cached_artist))
                else:
                    uncached_ids.append(aid)

            if uncached_ids:
                print(f"🕐 Spotify APIに問い合わせ（未キャッシュ）: {len(uncached_ids)}件")
                # 一括で取得（最大50件）
                try:
                    batch_info = sp.artists(uncached_ids)["artists"]
                    for info in batch_info:
                        redis_client.setex(f"artist_info:{info['id']}", 86400, json.dumps(info))  # 24hキャッシュ
                    artist_info_box.extend(batch_info)
                except Exception as e:
                    print("🚨 Spotify artist API batch error:", e)
                    time.sleep(0.1)  # rate-limit保護
            else:
                print("✅ 全てキャッシュから取得")

            print(f"🎨 アーティスト情報を{len(artist_info_box)}件読み込み完了")

        # ===============================
        # 🧮 定義スコア計算
        # ===============================
        for artist_info in artist_info_box:
            genres = artist_info.get("genres", [])
            for g in genres:
                definition_score += genre_weights.get(g, 0)
                influenced_word_box.append(g)
                print(f"{g}: {genre_weights.get(g)}")
            if artist_info["name"] == "The Beatles":
                definition_score += 50

        # 動物の確定
        if definition_score <= 2000:
            character_animal = "bug"
        elif definition_score <= 2200:
            character_animal = "grasshopper"
        elif definition_score <= 2400:
            character_animal = "saury"
        elif definition_score <= 2600:
            character_animal = "fish"
        elif definition_score <= 2800:
            character_animal = "squid"
        elif definition_score <= 3000:
            character_animal = "crab"    
        elif definition_score <= 3200:
            character_animal = "lobster"
        elif definition_score <= 3400:
            character_animal = "octopus"
        elif definition_score <= 3600:
            character_animal = "parrot-fish"
        elif definition_score <= 3800:
            character_animal = "fish-market"
        elif definition_score <= 4000:
            character_animal = "frog"
        elif definition_score <= 4200:
            character_animal = "snake"
        elif definition_score <= 4400:
            character_animal = "shark"
        elif definition_score <= 4600:
            character_animal = "horse"
        elif definition_score <= 4800:
            character_animal = "baby-cicada"
        elif definition_score <= 5000:
            character_animal = "giraffe"
        elif definition_score <= 5200:
            character_animal = "dog"
        elif definition_score <= 5400:
            character_animal = "orangutan"
        elif definition_score <= 5600:
            character_animal = "lion"
        elif definition_score <= 5800:
            character_animal = "eel"
        elif definition_score <= 6000:
            character_animal = "sloth"
        elif definition_score <= 6200:
            character_animal = "dolphin"
        elif definition_score <= 6400:
            character_animal = "seal"
        elif definition_score <= 6600:
            character_animal = "penguin"
        elif definition_score <= 6800:
            character_animal = "pelican"
        elif definition_score <= 7000:
            character_animal = "tuna"
        elif definition_score <= 7200:
            character_animal = "bear"
        elif definition_score <= 7400:
            character_animal = "goat"
        elif definition_score <= 7600:
            character_animal = "dogu"
        elif definition_score <= 7800:
            character_animal = "crocodile"
        elif definition_score <= 8500:
            character_animal = "cat"
        elif definition_score <= 9900:
            character_animal = "T-rex"
        elif definition_score <= 10500:
            character_animal = "parrot"
        elif definition_score <= 11000:
            character_animal = "cats"
        elif definition_score <= 11500:
            character_animal = "toy-dog"
        elif definition_score <= 12000:
            character_animal = "love-cat"
        else:
            character_animal = "dragon"

        #if user_id == "noel1109.marble1101":
        #    character_animal = "dolphin"

        base_image_path = f"animal_templates/{character_animal}.png"
        if not os.path.exists(base_image_path):
            return f"Template not found: {base_image_path}", 404
        
        influenced_word = random.choice(influenced_word_box)
        album_image_url = random.choice(album_image_url_box)

        print(f"\n🏆 あなたの音楽スコア: {definition_score}")
        print(f"動物: {character_animal}")
        print(f"キーワード: {influenced_word}")
        print(f"アルバム画像: {album_image_url}")
        atk = int(Decimal(definition_score).quantize(Decimal('1e2')))
        print(f"攻撃力: {atk}")
        if len(influenced_word.split())<=2:
            creature_name = f"{influenced_word} {character_animal}"
        else:  
            creature_name = f"The {character_animal} of {influenced_word}"
        creature_name = creature_name.title()
        # ✅ 正規表現で不要部分を削除
        creature_name = re.sub(r"[\-\(\[].*?(Remaster|Live|Remix|Version).*?[\)\]]", "", creature_name, flags=re.IGNORECASE)
        creature_name = re.sub(r"\s{2,}", " ", creature_name).strip()  # 余分なスペースを削除
        print(f"名前: {creature_name}")

        # 3:4 比率にリサイズ（幅768, 高さ1024など）
        img = Image.open(base_image_path).resize((768, 1024))
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        image_data_uri = f"data:image/png;base64,{image_b64}"

        prompt = (
            f"Legendary creature in {character_animal} of picture is a soldier or knight of alien has some weapons and from a dark and mysterious world."
            f"It has some factor relevant to the phrase of {influenced_word}. " #Background image is {album_image_url}
            f"It is also designed like creepy spooky monsters in SF or horror films but not cartoonish rather realistic."
        )
        print(prompt)

        headers = {
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json",
        }

        MODEL_VERSION = random.choice([
            "294de709b06655e61bb0149ec61ef8b5d3ca030517528ac34f8252b18b09b7ad",
            "294de709b06655e61bb0149ec61ef8b5d3ca030517528ac34f8252b18b09b7ad",
            "294de709b06655e61bb0149ec61ef8b5d3ca030517528ac34f8252b18b09b7ad",
            "294de709b06655e61bb0149ec61ef8b5d3ca030517528ac34f8252b18b09b7ad",
            "294de709b06655e61bb0149ec61ef8b5d3ca030517528ac34f8252b18b09b7ad",
            "294de709b06655e61bb0149ec61ef8b5d3ca030517528ac34f8252b18b09b7ad",
            "294de709b06655e61bb0149ec61ef8b5d3ca030517528ac34f8252b18b09b7ad",
            "294de709b06655e61bb0149ec61ef8b5d3ca030517528ac34f8252b18b09b7ad",
            "294de709b06655e61bb0149ec61ef8b5d3ca030517528ac34f8252b18b09b7ad",
            "17658fb151a7dd2fe9a0043990c24913d7b97a6b35dcd953a27a366fedc4e20a", 
            "535fdb4d34d13e899f8a61c3172ef1698230bed3c2faa0a17708abde760a5f64",
            "40ab9b32cc4584bc069e22027fffb97e79ed550d4e7c20ed6d5d7ef89e8f08f5",
            "e57c2dfbc48a476779abad3b6695839ecb779c18d0ec95f16d1f677a99cb3a42",
            "08ea3dfde168eed9cdc4956ba0e9a506f56c9f74f96c0809a3250d10a9c77986",
            "d53918f6a274da520ba36474408999d2f91ea9c2c5afb17abef15c6c42030963",
            "426affa4cca9beb69b34c92c54133196902a4bf72dba90718f0de3124418eedb",
            "426affa4cca9beb69b34c92c54133196902a4bf72dba90718f0de3124418eedb",
            "426affa4cca9beb69b34c92c54133196902a4bf72dba90718f0de3124418eedb",
            "15c6189d8a95836c3c296333aac9c416da4dfb0ae42650d4f10189441f29529f",
            "15c6189d8a95836c3c296333aac9c416da4dfb0ae42650d4f10189441f29529f",
            "bd2b772a22ecb2051cb1e08b58756fd2999781610ae618c52b5f4f76124c53d1",
            "262c44d38a47d71dc0168728963b5549666a5be21d1a04b87675d3f682ed7267"

        ])
        print(MODEL_VERSION)
        #MODEL_VERSION="262c44d38a47d71dc0168728963b5549666a5be21d1a04b87675d3f682ed7267"

        
        #chosen_img = random.choice([album_image_url, image_data_uri])
        chosen_img = image_data_uri

        payload = {
            "version": MODEL_VERSION,
            "input": {
                "prompt": prompt,
                "image": chosen_img,
                "strength": 0.9,
                "num_outputs": 1,
                "aspect_ratio": "3:4"
            }
        }

        # ✅ 非同期でpredictionを作成
        res = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload, timeout=120)
        if res.status_code != 201:
            return f"Image generation failed: {res.text}", 500

        prediction = res.json()

        # 🧠 creature_name をセッションに保存（後でタイトルに使う）
        session["creature_name"] = creature_name
        session["atk"] = atk

        return jsonify({
            "prediction_id": prediction["id"],
            "status_url": f"/result/{prediction["id"]}"
        })
    except Exception as e:
        print("🚨 /generate_api エラー発生:", e)
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
@app.route("/generate/<user_id>")
def generate_page(user_id):
    if session.get("user_id") != user_id:
        return redirect("/")
    return render_template("generate.html", user_id=user_id, import_mode=session.get("import_mode", False))

# =====================
# 生成結果ポーリング
# =====================
@app.route("/result/<prediction_id>", methods=["GET"])
def get_result(prediction_id):

    headers = {"Authorization": f"Token {REPLICATE_API_TOKEN}"}
    res = requests.get(f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers)
    if res.status_code != 200:
        return f"Failed to fetch prediction: {res.text}", 500

    data = res.json()
    
    if data["status"] != "succeeded":
        return jsonify({"status": data["status"], "image_url": None})
    
    # ✅ 生成された画像URLを取得
    image_url = data["output"][0]
    response = requests.get(image_url)
    img = Image.open(BytesIO(response.content)).convert("RGB")
    img = img.convert("RGBA")  # RGBAに戻す（透明合成OKにする）

    # =============================
    # ✨ ホログラム風エフェクト生成処理
    # =============================
    width, height = img.size

    # グラデーションレイヤー（虹色の光）
    gradient = Image.new("RGBA", img.size)
    for x in range(width):
        r = int(128 + 127 * np.sin(x / 20.0))
        g = int(128 + 127 * np.sin(x / 25.0 + 2))
        b = int(128 + 127 * np.sin(x / 30.0 + 4))
        for y in range(height):
            gradient.putpixel((x, y), (r, g, b, 40))

    # ノイズレイヤー
    noise = Image.effect_noise(img.size, 64).convert("L")
    noise = ImageEnhance.Contrast(noise).enhance(2.0)
    noise_colored = Image.merge("RGBA", (noise, noise, noise, noise))
    noise_colored.putalpha(40)

    # ✨ エフェクト合成
    holo = Image.alpha_composite(img, gradient)
    holo = Image.alpha_composite(holo, noise_colored)
    holo = holo.filter(ImageFilter.SMOOTH_MORE)
    holo = ImageEnhance.Brightness(holo).enhance(1.05)
    holo = ImageEnhance.Contrast(holo).enhance(1.1)
    # ✨ グリッター効果を全体に追加
    if random.random() < 0.01:
        holo = add_glitter_effect(holo, glitter_density=0.009, blur=0.3, alpha=225)
        print("✨ グリッターを付与しました！（10% 確率）")

    # =============================
    # 🏷️ タイトル・ユーザー名・カードID描画
    # =============================
    draw = ImageDraw.Draw(holo)

    # ✅ generate_api で作成した creature_name をそのままタイトルとして使用
    ai_title = session.get("creature_name", "Unknown Creature")
    atk = session.get("atk", "0")
    user_name = session.get("user_id", "UnknownUser")
    card_id = f"#{prediction_id[:8].upper()}"

    try:
        font_title = ImageFont.truetype("static/fonts/SuperBread-ywdRV.ttf", 50)
        font_info = ImageFont.truetype("static/fonts/Caprasimo-Regular.ttf", 10)
    except:
        font_title = ImageFont.load_default()
        font_info = ImageFont.load_default()

    # 🪄 タイトルを別レイヤーで生成
    title_layer = Image.new("RGBA", holo.size, (0, 0, 0, 0))
    title_draw = ImageDraw.Draw(title_layer)

    title_bbox = title_draw.textbbox((0, 0), ai_title, font=font_title)
    tw = title_bbox[2] - title_bbox[0]
    th = title_bbox[3] - title_bbox[1]
    x_pos = (width - tw) / 2
    y_pos = 5

    # 🌈 虹色グラデーション文字描画
    gradient_colors = [
        (255, 0, 0),     # 赤
        (255, 127, 70),   # オレンジ
        (200, 200, 70),   # 黄
        (100, 230, 70),     # 緑
        (0, 0, 255),     # 青
        (75, 0, 130),    # 藍
        (148, 0, 211)    # 紫
    ]

    # アウトラインの太さ（調整可能）
    outline_width = 4
    outline_color = (255, 255, 255, 255)  # 白
    shadow_offset = (6, 6)  # シャドウのずらし量
    shadow_color = (0, 0, 0, 180)  # 半透明の黒い影

    # 描画位置を最初に戻す
    x_pos = (holo.width - tw) / 2
    y_pos = 5

    # 各文字に色をつける
    for i, char in enumerate(ai_title):
        color = gradient_colors[i % len(gradient_colors)]
        # --- シャドウ ---
        title_draw.text(
            (x_pos + shadow_offset[0], y_pos + shadow_offset[1]),
            char,
            font=font_title,
            fill=shadow_color
        )

        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx**2 + dy**2 <= outline_width**2:  # 円形に近い外枠
                    title_draw.text(
                        (x_pos + dx, y_pos + dy),
                        char,
                        font=font_title,
                        fill=outline_color
                    )
        # --- 本体の文字を描画 ---
        title_draw.text((x_pos, y_pos), char, font=font_title, fill=color + (255,))
        # 次の文字の横位置を取得
        char_width = title_draw.textbbox((0,0), char, font=font_title)[2] - title_draw.textbbox((0,0), char, font=font_title)[0]
        x_pos += char_width

    # 🎛 タイトル専用フィルターを適用
    filtered_title = title_layer.copy()
    filtered_title = filtered_title.filter(ImageFilter.SMOOTH_MORE)
    filtered_title = ImageEnhance.Brightness(filtered_title).enhance(0.9)
    filtered_title = ImageEnhance.Contrast(filtered_title).enhance(0.9)
    
    # 💫 glowを生成
    glow = filtered_title.filter(ImageFilter.GaussianBlur(6))
    glow = ImageEnhance.Brightness(glow).enhance(1.6)

    # ✅ 背景（holo）には一切影響を与えず、ここで初めて合成
    final_image = holo.copy()
    final_image = Image.alpha_composite(final_image, glow)
    final_image = Image.alpha_composite(final_image, filtered_title)

    # -------------------------
    # ATKレイヤー（タイトルと同様の処理）を作成して合成
    # -------------------------
    atk_text = f"ATK: {atk}"
    try:
        font_atk = ImageFont.truetype("static/fonts/Caprasimo-Regular.ttf", 44)
    except Exception:
        font_atk = ImageFont.load_default()

    atk_layer = Image.new("RGBA", holo.size, (0,0,0,0))
    atk_draw = ImageDraw.Draw(atk_layer)
    atk_bbox = atk_draw.textbbox((0,0), atk_text, font=font_atk)
    atk_w = atk_bbox[2] - atk_bbox[0]
    atk_h = atk_bbox[3] - atk_bbox[1]

    # 位置：カードID の上に来るように調整（マージンで調整可）
    margin = 40
    x_atk = width - atk_w - margin
    y_atk = height - atk_h - margin - 30  # IDの上に配置（60px 上）

    # 描画（シャドウ・白枠・虹色）
    x_write = x_atk
    for i, char in enumerate(atk_text):
        color = gradient_colors[i % len(gradient_colors)]
        # shadow
        atk_draw.text((x_write + shadow_offset[0], y_atk + shadow_offset[1]), char, font=font_atk, fill=shadow_color)
        # outline
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx*dx + dy*dy <= outline_width*outline_width:
                    atk_draw.text((x_write + dx, y_atk + dy), char, font=font_atk, fill=outline_color)
        # main
        atk_draw.text((x_write, y_atk), char, font=font_atk, fill=color + (255,))
        cw = atk_draw.textbbox((0,0), char, font=font_atk)[2] - atk_draw.textbbox((0,0), char, font=font_atk)[0]
        x_write += cw

    # フィルタ・alpha・glow をタイトルと揃える
    filtered_atk = atk_layer.copy()
    filtered_atk = filtered_atk.filter(ImageFilter.SMOOTH_MORE)
    filtered_atk = ImageEnhance.Brightness(filtered_atk).enhance(0.95)
    filtered_atk = ImageEnhance.Contrast(filtered_atk).enhance(1.05)

    atk_glow = filtered_atk.filter(ImageFilter.GaussianBlur(6))
    atk_glow = ImageEnhance.Brightness(atk_glow).enhance(1.6)

    # 合成
    final_image = Image.alpha_composite(final_image, atk_glow)
    final_image = Image.alpha_composite(final_image, filtered_atk)


    # =============================
    # 🔠 カードIDを右下に寄せて描画
    # =============================
    draw_final = ImageDraw.Draw(final_image)
    info_text = f"{card_id}"
    info_bbox = draw_final.textbbox((0, 0), info_text, font=font_info)
    iw = info_bbox[2] - info_bbox[0]
    ih = info_bbox[3] - info_bbox[1]
    draw_final.text(
        (final_image.width - iw - 40, final_image.height - ih - 20),
        info_text,
        font=font_info,
        fill=(255, 255, 255, 230)
    )

    # =============================
    # 保存処理
    # =============================
    output_path = f"static/generated/hologram_{prediction_id}.png"
    os.makedirs("static/generated", exist_ok=True)
    final_image.save(output_path)
    print(f"✅ タイトル付きホログラム画像を生成: {output_path}")

    base_url = request.host_url.rstrip("/")
    full_image_url = f"{base_url}/{output_path}"

    return jsonify({
        "status": "succeeded",
        "image_url": full_image_url,
        "title": ai_title,
        "card_id": card_id,
        "user": user_name
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
