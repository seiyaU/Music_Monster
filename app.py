from flask import Flask, redirect, request, session, jsonify
import requests

app = Flask(__name__)
app.secret_key = "YOUR_SECRET_KEY"

SPOTIFY_CLIENT_ID = "YOUR_SPOTIFY_CLIENT_ID"
SPOTIFY_CLIENT_SECRET = "YOUR_SPOTIFY_CLIENT_SECRET"
REDIRECT_URI = "https://music-cat-7r71.onrender.com/callback"

@app.route("/login")
def login():
    scope = "user-read-recently-played"
    auth_url = (
        f"https://accounts.spotify.com/authorize"
        f"?response_type=code&client_id={SPOTIFY_CLIENT_ID}"
        f"&scope={scope}&redirect_uri={REDIRECT_URI}"
    )
    return redirect(auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "認証に失敗しました。", 400

    token_res = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": SPOTIFY_CLIENT_ID,
            "client_secret": SPOTIFY_CLIENT_SECRET,
        },
    )
    token_data = token_res.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return "アクセストークン取得に失敗しました。", 400

    user_res = requests.get(
        "https://api.spotify.com/v1/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    user_data = user_res.json()
    user_id = user_data.get("id")

    session["access_token"] = access_token
    session["user_id"] = user_id

    return f"""
    <html>
        <body>
            <h2>認証完了 ✅</h2>
            <p>User ID: {user_id}</p>
            <script>window.close();</script>
        </body>
    </html>
    """

@app.route("/auth-status")
def auth_status():
    user_id = session.get("user_id")
    if user_id:
        return jsonify({"authenticated": True, "user_id": user_id})
    return jsonify({"authenticated": False})

@app.route("/recent/<user_id>")
def recent_tracks(user_id):
    access_token = session.get("access_token")
    if not access_token:
        return jsonify({"error": "未認証"}), 401

    res = requests.get(
        "https://api.spotify.com/v1/me/player/recently-played?limit=10",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    items = res.json().get("items", [])

    artist_ids = {artist["id"] for item in items for artist in item.get("track", {}).get("artists", [])}
    artist_id_list = ",".join(artist_ids)

    # バッチでアーティスト情報取得
    artist_info = {}
    if artist_id_list:
        artist_res = requests.get(
            f"https://api.spotify.com/v1/artists?ids={artist_id_list}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        for artist in artist_res.json().get("artists", []):
            artist_info[artist["id"]] = artist.get("genres", [])

    tracks = []
    for item in items:
        track = item.get("track", {})
        artists = track.get("artists", [])
        genres = set()

        for artist in artists:
            genres.update(artist_info.get(artist["id"], []))

        tracks.append({
            "name": track.get("name"),
            "artist": ", ".join([a["name"] for a in artists]),
            "image": track.get("album", {}).get("images", [{}])[0].get("url", ""),
            "genres": list(genres)
        })

    return jsonify({"recently_played": tracks})

if __name__ == "__main__":
    app.run(debug=True)
