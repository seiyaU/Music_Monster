import spotipy
from spotipy.oauth2 import SpotifyOAuth

def make_letter():
    # Spotify API 認証
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id="e79acc16b5884a6088adac46a61fc8f0",
        client_secret="72dcf2a487e64c46ab32b543b015a46f",
        redirect_uri="https://example.com/callback",
        scope="user-read-recently-played"
    ))

    # 直近の再生履歴を取得（最大50件）
    results = sp.current_user_recently_played(limit=10)  # limit=最大50

    for idx, item in enumerate(results['items']):
        track = item['track']
        played_at = item['played_at']
        print(f"{idx+1}. {track['name']} - {track['artists'][0]['name']} ({played_at})")

if __name__ == "__main__":
    make_letter()