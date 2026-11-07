# USD/JPY News Collector (prototype)

公開情報だけを使うドル円ニュース収集・整理の最小実装です。

対象:
- Reuters: Google News RSS の `site:reuters.com` 検索経由（試作アダプター。後で置換前提）
- 日本銀行: 「ニュース一覧」ページ
- 財務省: 公式 RSS
- FRB: Monetary Policy 公式 RSS
- BLS: 公式 Public Data API（雇用者数・失業率・CPI）

処理:
1. 新着取得
2. ドル円関連度スコアリング
3. 重複整理
4. 円高 / 円安 / 中立の簡易分類
5. Markdown + JSON レポート出力

## 実行

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python main.py
```

生成物:
- `output/usdjpy_report.md`
- `output/usdjpy_items.json`

## 注意

- Reuters は公式一般向けRSSではなく検索フィード経由です。本文の大量保存は行わず、見出し・概要・リンク中心に扱います。
- BLS はクラウド環境でRSSが403になる場合があるため、公式 Public Data API を使用します（APIキー不要の小規模取得）。
- 各サイトの利用規約やアクセス方針に従ってください。
- 現段階の方向判定はルールベースです。次段階でLLM要約・重要度判定を追加できます。

## Androidで見る簡易Web版

同じWi-Fiに接続したPCでサーバーを起動し、AndroidのChromeから開けます。

### 1. 初回だけ依存ライブラリをインストール

```bash
pip install -r requirements.txt
```

### 2. Web画面を起動

Windows:

```bat
start_web_windows.bat
```

macOS / Linux:

```bash
./start_web_mac_linux.sh
```

または共通で:

```bash
python web_app.py
```

起動すると次のように表示されます。

```text
PC:      http://127.0.0.1:8080
Android: http://192.168.x.x:8080  (same Wi-Fi)
```

Android Chromeで表示された `Android:` のURLを開いてください。

### 画面の使い方

- `更新` をタップ: 5ソースを再取得して分類
- 総合判定: 円高材料 / 円安材料 / 要確認 の件数から簡易判定
- ニュースカードをタップ: 元記事を開く
- 最終更新時刻を表示

※ Windowsファイアウォール等でPythonの通信許可を求められた場合は、信頼できる自宅/プライベートネットワーク内だけ許可してください。
※ 開発用の簡易サーバーです。インターネットへ直接公開する用途には使わないでください。
