from fastapi import FastAPI, Request
from spotipy.oauth2 import SpotifyOAuth
import spotipy
import os

app = FastAPI()

# Spotify API 用の設定（環境変数から読むのが安全）
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = "https://yourapp.onrender.com/callback"  # RenderのURLに合わせて修正

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
