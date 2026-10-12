# Renderでクラウド版を試す手順

この版は、PCをつけっぱなしにしなくてもAndroidのChromeから固定URLで確認するためのテスト版です。

## 0. 先に知っておくこと

- RenderのFree Web Serviceを使います。
- 無料版は15分アクセスがないと休止します。次回アクセス時は起動に少し時間がかかります。
- 無料版のローカル保存領域は永続ではありません。この試作は、再起動後に最初に開いたときニュースを再取得する設計です。
- 売買推奨ではなく、ニュース整理用の試作です。

## 1. GitHubアカウントを作る

すでにGitHubアカウントがあれば飛ばしてください。

1. https://github.com/ を開く
2. Sign up から無料アカウントを作る
3. ログインする

## 2. GitHubにこのフォルダをアップロードする

1. GitHub右上の + → New repository
2. Repository name を `usdjpy-news-prototype` にする
3. Public または Private を選ぶ（どちらでも可）
4. Create repository
5. 作成後の画面で `uploading an existing file` を選ぶ
6. このZIPを解凍して、`app` フォルダの「中身」をすべてドラッグ&ドロップする
   - `main.py`
   - `web_app.py`
   - `config.json`
   - `requirements.txt`
   - `render.yaml`
   - `.gitignore`
   - `README.md`
   - `CLOUD_SETUP.md`
7. 下の Commit changes を押す

## 3. Renderに登録する

1. https://render.com/ を開く
2. Get Started から登録する
3. GitHubで登録/接続すると後が簡単

## 4. Web Serviceを作る

1. Render Dashboardで New → Web Service
2. GitHubを接続し、`usdjpy-news-prototype` を選ぶ
3. 設定画面で次を確認

- Language / Runtime: Python
- Build Command: `pip install -r requirements.txt`
- Start Command: `python web_app.py`
- Instance Type / Plan: Free

`render.yaml` を認識して自動入力される場合は、その内容で進めて構いません。

4. Create Web Service を押す
5. デプロイが完了し `Live` になったら、画面上部の `https://...onrender.com` を開く

## 5. Androidで開く

1. Renderが発行した `https://...onrender.com` をAndroidのChromeで開く
2. 必要ならChromeメニュー → ホーム画面に追加
3. 以後、PCの電源や自宅IPを気にせず同じURLで開ける

## 6. 画面が最初だけ遅い場合

Free版は15分アクセスがないと休止します。久しぶりに開くと再起動が入り、その後ニュースの初回取得も行うため、通常時より遅くなります。画面が出れば以後は「更新」ボタンで再取得できます。

## 7. エラーになったら

Render Dashboard → 対象サービス → Logs を開き、最後の20〜30行をコピーしてChatGPTに貼ってください。そこから原因を一緒に確認できます。
