from fastapi import FastAPI, Request
from spotipy.oauth2 import SpotifyOAuth
import spotipy
import os

app = FastAPI()

# Spotify API 用の設定
CLIENT_ID = "e79acc16b5884a6088adac46a61fc8f0"
CLIENT_SECRET = "72dcf2a487e64c46ab32b543b015a46f"
REDIRECT_URI = "https://music-cat-7r71.onrender.com/callback"

SCOPE = "user-read-email user-read-recently-played"

sp_oauth = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE
)

@app.get("/")
def root():
    return {"message": "Hello Spotify App!"}

# ① 認証URLを発行する
@app.get("/login")
def login():
    auth_url = sp_oauth.get_authorize_url()
    return {"auth_url": auth_url}

# ② Spotifyから返されるcodeを受け取ってアクセストークンに交換
@app.get("/callback")
def callback(request: Request):
    code = request.query_params.get("code")
    if code is None:
        return {"error": "No code provided"}

    token_info = sp_oauth.get_access_token(code)
    access_token = token_info["access_token"]
    refresh_token = token_info["refresh_token"]

    # APIアクセス確認用にユーザー情報を取得
    sp = spotipy.Spotify(auth=access_token)
    user_profile = sp.current_user()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_profile": user_profile
    }
