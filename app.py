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

SCOPE = "user-read-email user-read-recently-played user-top-read"

sp_oauth = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE
)

@app.get("/")
def root():
    return {"message": "Hello Spotify App!"}

@app.get("/callback")
def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return JSONResponse({"error": "No code provided"}, status_code=400)

    token_info = sp_oauth.get_access_token(code)

    # 🎯 refresh_token を保存
    user_tokens["refresh_token"] = token_info["refresh_token"]
    user_tokens["access_token"] = token_info["access_token"]

    return {"status": "authorized"}

@app.get("/recent")
def recent_tracks():
    if "refresh_token" not in user_tokens:
        return JSONResponse({"error": "User not authenticated"}, status_code=401)

    # 🎯 必要に応じてアクセストークンをリフレッシュ
    token_info = sp_oauth.refresh_access_token(user_tokens["refresh_token"])
    access_token = token_info["access_token"]
    user_tokens["access_token"] = access_token

    sp = spotipy.Spotify(auth=access_token)
    results = sp.current_user_recently_played(limit=10)

    tracks = [
        {
            "name": item["track"]["name"],
            "artist": item["track"]["artists"][0]["name"],
            "played_at": item["played_at"]
        }
        for item in results["items"]
    ]

    return {"tracks": tracks}