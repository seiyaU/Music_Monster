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
    scope=SCOPE
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

    # 🎯 refresh_token を保存
    user_tokens["refresh_token"] = token_info["refresh_token"]
    user_tokens["access_token"] = token_info["access_token"]

    return {"status": "authorized"}

@app.get("/recent")
def recent_tracks():
    if "refresh_token" not in user_tokens:
        #return JSONResponse({"error": "User not authenticated"}, status_code=401)
        return RedirectResponse(url="/login")

    # 🎯 必要に応じてアクセストークンをリフレッシュ
    token_info = sp_oauth.refresh_access_token(user_tokens["refresh_token"])
    access_token = token_info["access_token"]
    user_tokens["access_token"] = access_token

    sp = spotipy.Spotify(auth=access_token)
    recently_played = sp.current_user_recently_played(limit=50)
    top_tracks = sp.current_user_top_tracks(limit=50)
    saved_albums = sp.current_user_saved_albums(limit=50)

    recently_played_tracks = [
        {
            "name": item["track"]["name"],
            "image": item["track"]["album"]["images"][0]["url"],
            "genre": item["track"]["album"]["genres"][0] if item["track"]["album"]["genres"] else None,
            "popularity": item["track"]["popularity"],
            "release_date": item["track"]["album"]["release_date"]
        }
        for item in recently_played["items"]
    ]

    return {"recently_played_tracks": recently_played_tracks}