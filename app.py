from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.responses import RedirectResponse, JSONResponse
from spotipy.oauth2 import SpotifyOAuth
import spotipy
import os

app = FastAPI()
user_tokens = {}

# Spotify API 用の設定
CLIENT_ID = "e79acc16b5884a6088adac46a61fc8f0"
CLIENT_SECRET = "72dcf2a487e64c46ab32b543b015a46f"
REDIRECT_URI = "https://music-cat-7r71.onrender.com/callback"
SCOPE = "user-read-email user-read-recently-played user-top-read user-library-read"

sp_oauth = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE,
    cache_path=".spotify_cache"
)

@app.get("/")
def root():
    return {"message": "Hello Spotify App!"}

@app.get("/login")
def login():
    auth_url = sp_oauth.get_authorize_url()
    return RedirectResponse(auth_url)

@app.get("/callback")
def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return JSONResponse({"error": "No code provided"}, status_code=400)

    token_info = sp_oauth.get_access_token(code)
    sp = spotipy.Spotify(auth=token_info["access_token"])
    user_info = sp.current_user()  # 👈 ユーザー情報を取得
    user_id = user_info["id"]

    # ユーザーごとにトークンを保存
    user_tokens[user_id] = token_info

    return {"status": "authorized", "user_id": user_id}

@app.get("/recent/{user_id}")
def recent_tracks(user_id: str):
    if user_id not in user_tokens:
        return JSONResponse({"error": "User not authenticated"}, status_code=401)

    # トークン更新
    token_info = sp_oauth.refresh_access_token(user_tokens[user_id]["refresh_token"])
    user_tokens[user_id] = token_info
    access_token = token_info["access_token"]

    sp = spotipy.Spotify(auth=access_token)
    recently_played = sp.current_user_recently_played(limit=50)

    tracks = [
        {
            "name": item["track"]["name"],
            "artist": item["track"]["artists"][0]["name"],
            "image": item["track"]["album"]["images"][0]["url"] if item["track"]["album"]["images"] else None,
            "played_at": item["played_at"]
        }
        for item in recently_played["items"]
    ]

    return {"user_id": user_id, "recently_played": tracks}