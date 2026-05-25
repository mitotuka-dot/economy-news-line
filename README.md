# 重要経済ニュース LINE 通知 MVP

3時間ごとに経済・金融・株式市場ニュースを取得し、重要度4以上だけを日本語で要約して LINE Messaging API の Push Message で通知する Python MVP です。

## ファイル構成

```text
.
├── main.py
├── .github/workflows/economy-news-line.yml
├── data/news_notifications.db  # GitHub Actions用の重複防止DB
├── .env.example
├── requirements.txt
├── README.md
└── news_notifications.db  # 初回実行時に自動作成
```

## できること

- 無料運用では日本語RSSを優先してニュース取得
- Yahoo!ニュース経済、NHK経済、Google News RSSの日経・Reuters検索を利用
- Alpha Vantage / NewsAPI はフォールバックとして利用
- OpenAIは初期設定で使わず、無料のキーワードベース判定・要約で動作
- SQLite に送信済み・確認済みニュースを保存し、重複通知を防止
- `python main.py` で1時間ごとの常駐実行
- `python main.py --once` で1回だけ実行。cron、GitHub Actions、Render、Railway へ移しやすい構成
- GitHub Actions では3時間ごとに実行し、`data/news_notifications.db` を自動コミットして重複通知を防止

## 公式仕様に沿った利用 API

- Alpha Vantage: `https://www.alphavantage.co/query?function=NEWS_SENTIMENT`
- NewsAPI Everything: `https://newsapi.org/v2/everything`
- NewsAPI Top headlines: `https://newsapi.org/v2/top-headlines`
- LINE Push Message: `https://api.line.me/v2/bot/message/push`
- OpenAI Responses API: `https://api.openai.com/v1/responses`

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` に以下を設定します。

```env
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
LINE_USER_ID=your_line_user_id
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_api_key
NEWS_API_KEY=your_news_api_key
OPENAI_API_KEY=your_openai_api_key
USE_OPENAI=false
NEWS_SOURCE_PRIORITY=newsapi_jp
JAPANESE_RSS_ENABLED=true
```

無料で使う場合は `USE_OPENAI=false` のままで動かします。`LINE_CHANNEL_ACCESS_TOKEN` または `LINE_USER_ID` が空の場合、LINE送信はせずログにプレビューを出します。

## LINE Messaging API 側の設定

1. LINE Developers Console で Provider を作成します。
2. Messaging API チャネルを作成します。
3. LINE Official Account を自分の LINE で友だち追加します。
4. Messaging API 設定で Channel access token を発行し、`.env` の `LINE_CHANNEL_ACCESS_TOKEN` に設定します。
5. Basic settings タブで自分の User ID を確認し、`.env` の `LINE_USER_ID` に設定します。
6. Push Message が使えるプラン・権限であることを確認します。

## ローカル実行

1回だけ実行:

```bash
python main.py --once
```

Macで `python` コマンドがない場合は `python3 main.py --once` を使ってください。

1時間ごとに常駐実行:

```bash
python main.py
```

Macで `python` コマンドがない場合は `python3 main.py` を使ってください。

停止する場合は `Ctrl+C` を押します。

## GitHub Actionsで3時間ごとに実行する方法

このリポジトリをGitHubへpushし、GitHubの `Settings > Secrets and variables > Actions > Repository secrets` に以下を登録します。

```text
LINE_CHANNEL_ACCESS_TOKEN
LINE_USER_ID
ALPHA_VANTAGE_API_KEY
NEWS_API_KEY
OPENAI_API_KEY
```

`.github/workflows/economy-news-line.yml` は設定済みです。スケジュールはUTCで `0 */3 * * *`、日本時間では3時間ごとに動きます。手動実行したい場合はGitHubの `Actions > Economy News LINE > Run workflow` を押します。

重複防止のため、実行後に `data/news_notifications.db` をGitHub Actionsが自動コミットします。リポジトリの `Settings > Actions > General > Workflow permissions` は `Read and write permissions` にしてください。

## ローカルでの定期実行方法

### 方法1: アプリ内スケジューラ

```bash
python main.py
```

起動直後に1回実行し、その後1時間ごとに実行します。Macローカルや Render / Railway の常駐プロセス向きです。

### 方法2: cron

```cron
0 * * * * cd /path/to/project && /path/to/project/.venv/bin/python main.py --once >> news.log 2>&1
```

### 方法3: GitHub Actions

`.github/workflows/news.yml` の例:

```yaml
name: economy-news

on:
  schedule:
    - cron: "0 * * * *"
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python main.py --once
        env:
          LINE_CHANNEL_ACCESS_TOKEN: ${{ secrets.LINE_CHANNEL_ACCESS_TOKEN }}
          LINE_USER_ID: ${{ secrets.LINE_USER_ID }}
          ALPHA_VANTAGE_API_KEY: ${{ secrets.ALPHA_VANTAGE_API_KEY }}
          NEWS_API_KEY: ${{ secrets.NEWS_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

GitHub Actions の無料枠では SQLite ファイルが毎回消えるため、厳密な重複防止には外部DBや Google Sheets / Notion などへの保存が必要です。

## 通知フォーマット

```text
【重要経済ニュース】
重要度：★★★★☆
カテゴリ：米国金利 / 日本株 / AI / 半導体 / 個別株 / 為替 / 金利 / 地政学 など

タイトル：
...

要約：
・何が起きたか
・なぜ重要か
・市場や関連銘柄への影響
・投資家が次に見るべきポイント

関連銘柄：
- NVDA
- MSFT

URL：
https://...
```

## 重要度判定

- 5: 即通知。市場全体、AI・半導体関連株、保有・注目銘柄に大きな影響がありそう
- 4: 通知対象。投資判断に関係しそう
- 3: 記録のみ。重要だが緊急性は低い
- 2: 無視
- 1: 無視

通知対象は初期設定で `NOTIFY_MIN_SCORE=4` です。

## よくあるエラーと対処法

### LINE 401 Unauthorized

`LINE_CHANNEL_ACCESS_TOKEN` が間違っている、期限切れ、または Messaging API チャネルのトークンではない可能性があります。LINE Developers Console で再発行してください。

### LINE 400 Bad Request

`LINE_USER_ID` が間違っている、Botを友だち追加していない、Push Message の送信先として使えない可能性があります。

### Alpha Vantage の `Note` や `Information`

無料枠のレート制限やAPI利用条件に当たっている可能性があります。ログに内容を出し、NewsAPIへフォールバックします。

### NewsAPI `apiKeyInvalid`

`NEWS_API_KEY` が間違っています。NewsAPI のダッシュボードで確認してください。

### OpenAI が失敗する

`OPENAI_API_KEY`、モデル名、利用上限を確認してください。失敗時は自動でキーワードベース判定に切り替わります。

### 重複通知される

URLまたはタイトルから作る fingerprint を SQLite に保存しています。別環境で実行する場合、同じ `news_notifications.db` を共有しないと重複する可能性があります。

## デプロイ設計メモ

- Render / Railway: Start command を `python main.py` にすると常駐実行できます。
- GitHub Actions / cron: `python main.py --once` を1時間ごとに呼びます。
- 本番運用で複数インスタンスを立てる場合は SQLite ではなく PostgreSQL などの共有DB推奨です。

## 改善案

- 重要度5だけ即時通知し、重要度4は朝・昼・夕にまとめる
- 日本時間の市場時間、米国市場時間、重要指標発表時間に合わせて通知を調整する
- 保有銘柄・注目銘柄リストをCSVで管理し、スコアリングに反映する
- LINE通知を Flex Message 化し、「詳しく見る」リンクボタンを付ける
- Notion や Google スプレッドシートにニュース履歴を保存する
- 日本株と米国株で通知カテゴリや配信タイミングを分ける
- 半導体・AIインフラ関連ニュースだけ別枠で通知する
