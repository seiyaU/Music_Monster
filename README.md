# Music_Monster

Spotifyの再生履歴から、音楽性をモンスターカードとして生成するFlaskアプリです。

## Spotify履歴JSONインポート

トップページではSpotifyの **Extended Streaming History** JSONを選択できます。
JSONはブラウザ内で解析され、サーバーへ送るのは直近50件分のSpotify Track IDだけです。再生時刻、アカウント名、国、端末情報などの生データは送信・保存しません。

サーバーはTrack IDからSpotifyカタログの曲・アーティストを取得し、Spotifyが返すアーティストのジャンルを既存のスコア計算に使います。`SPOTIPY_CLIENT_ID` と `SPOTIPY_CLIENT_SECRET` はRenderなどのサーバー環境変数に設定し、ブラウザへ公開しないでください。

## ディレクトリ構成
- data/: データファイル
- scripts/: スクリプト
- outputs/: 出力ファイル

## セットアップ
1. 必要なパッケージをインストールします: `pip install -r requirements.txt`
2. Redisと以下の環境変数を設定します。
   - `REDIS_URL`
   - `FLASK_SECRET_KEY`
   - `SPOTIPY_CLIENT_ID`
   - `SPOTIPY_CLIENT_SECRET`
   - `SPOTIPY_REDIRECT_URI`（従来のSpotifyログインを使う場合）
   - `REPLICATE_API_TOKEN`
3. `gunicorn app:app` で起動します。

## ライセンス
MIT
