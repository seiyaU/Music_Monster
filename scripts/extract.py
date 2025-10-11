from openai import OpenAI
import base64
import random
import requests
import time
import uuid
import yaml
import webbrowser

################# Spotify #################
BASE_URL = "https://music-cat-7r71.onrender.com"

def authenticate_user():
    # 一意なstateを作成（UUID）
    state = str(uuid.uuid4())

    print("🌐 Spotifyログインページを開きます...")
    webbrowser.open(f"{BASE_URL}/login?state={state}")

    print("⏳ Spotify認証を待機中...")
    for _ in range(60):
        try:
            res = requests.get(f"{BASE_URL}/auth-status?state={state}")
            if res.status_code == 200:
                data = res.json()
                if data.get("authenticated"):
                    print(f"✅ 認証成功: {data['user_id']}")
                    return data["user_id"]
        except requests.RequestException:
            pass
        time.sleep(2)

    raise TimeoutError("❌ Spotify認証が完了しませんでした。")

def get_recent_tracks(user_id):
    url = f"{BASE_URL}/recent/{user_id}"
    res = requests.get(url, allow_redirects=False)  # ← リダイレクトを追わない
    print(f"📡 Response status: {res.status_code}")

    # 🎯 リダイレクトが返ってきたら認証が必要
    if res.status_code in (301, 302):
        print("⚠️ ログインが必要です。Spotifyログインページを開きます。")
        print("🔗", res.headers.get("Location"))
        return None

    # 🎯 JSONが返ってきた場合のみパース
    content_type = res.headers.get("content-type", "")
    if "application/json" in content_type:
        return res.json()
    else:
        print("⚠️ JSON以外のレスポンスが返ってきました:")
        print(res.text[:500])  # HTMLなどを確認
        return None
    

################# 画像生成 #################


   
if __name__ == "__main__":
    user_id = authenticate_user()
    recent = get_recent_tracks(user_id)
    definition_score = 0
    character_animal = ""
    influenced_word = ""
    influenced_word_box = []

    with open("data/genre_weights.yaml", "r", encoding="utf-8") as f:
        genre_weights = yaml.safe_load(f)

    print("\n🎵 最近再生した曲:")
    for idx, track in enumerate(recent["recently_played"], 1):
        print(f"{idx}. {track['name']} / {track['artist']} ({', '.join(track['genres'])})")
        influenced_word_box.append(track['artist'])


        if track['artist'] == "The Beatles":
            definition_score += 50

        for i in track['genres']:
            weight = genre_weights.get(i, 0)  # デフォルト値0
            definition_score += weight
            influenced_word_box.append(i)
            print(f"   - {i}: {weight}")
    
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
    
    # 影響を受けるキーワードの確定
    influenced_word = random.choice(influenced_word_box)

    print(f"\n🏆 あなたの音楽定義スコア: {definition_score}")
    print(character_animal)
    print(influenced_word)

    


