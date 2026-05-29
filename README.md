# X Reply Radar

Xで指定した投資系アカウントを1時間に1回監視し、伸びている投稿だけを抽出して、日本語のリプ案をLINEに送るPythonアプリです。

このアプリはXへの自動リプ、自動投稿、自動いいね、自動リポストを一切しません。LINEに届いたリプ案を自分で確認し、必要な場合だけ手動で投稿する前提です。

## できること

- `watchlist.txt` に書いたアカウントを優先して監視
- X API v2で直近投稿を取得
- 投稿後6時間以内の日本語・英語投稿を対象にスコアリング
- カテゴリ別の伸び条件と過去30投稿平均との差で判定
- 関連キーワードから `relevance_score` を計算
- 炎上リスクや投資助言っぽくなりやすい投稿を除外
- OpenAI APIでリプ案を3パターン生成
- S/A優先度だけをLINE Messaging APIで通知
- `DRY_RUN=true` でLINE送信せずコンソール確認

## 必要なAPIキー

- X API v2 Bearer Token
- OpenAI API Key
- LINE Messaging API Channel access token
- LINE User ID

## X Developer Portalで必要な設定

1. X Developer PortalでProject/Appを作成します。
2. Bearer Tokenを発行します。
3. Read権限でユーザー情報と投稿取得ができる状態にします。
4. 自分のX User IDを確認し、`X_USER_ID` に設定します。

この初期版は `watchlist.txt` 優先です。フォロー一覧取得が失敗しても、watchlistだけで動く設計にしています。

## LINE Developersの設定

1. LINE Developers ConsoleでProviderを作成します。
2. Messaging APIチャネルを作成します。
3. 作成されたLINE Official Accountを自分のLINEで友だち追加します。
4. Messaging API設定からChannel access tokenを発行します。
5. `LINE_CHANNEL_ACCESS_TOKEN` に設定します。

## LINE_USER_IDの取得方法

LINE Developersのチャネル設定で自分のUser IDを確認できる場合はそれを使います。表示されない場合はWebhook受信サーバーを一時的に用意し、自分がBotに送ったメッセージイベントの `source.userId` を確認してください。

## .envの作り方

```bash
cp .env.example .env
```

`.env` に以下を入れます。

```env
X_BEARER_TOKEN=your_x_bearer_token
X_USER_ID=your_x_user_id
OPENAI_API_KEY=your_openai_api_key
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
LINE_USER_ID=your_line_user_id
DRY_RUN=true
```

`DRY_RUN=false` の場合のみLINEに送信します。

## watchlist.txtの使い方

1行に1アカウントを書きます。`@` あり・なしの両方に対応しています。

```text
@xRINGx
@nicosokufx
@goto_finance
```

`@news9111` はtestアカウントに見えるため、初期版では登録していません。

## ローカル実行

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

Macで `python3.11` がない場合は、Python 3.11をインストールしてから実行してください。

## DRY_RUN=trueでのテスト

`.env` で以下にします。

```env
DRY_RUN=true
```

この状態で実行すると、LINE送信は行わず、通知予定の内容をコンソールに表示します。DRY_RUN中は `notified_tweets` に通知済みとして保存しないため、同じ候補を繰り返し確認できます。

## GitHub Actionsで動かす方法

`.github/workflows/run.yml` は設定済みです。

- 毎時17分に実行
- 手動実行 `workflow_dispatch` に対応
- Python 3.11で `python -m app.main` を実行
- 実行後に `data/x_reply_radar.db` を自動コミットし、通知済み履歴を保存

GitHubの `Settings > Secrets and variables > Actions > Repository secrets` に以下を登録します。

- `X_BEARER_TOKEN`
- `X_USER_ID`
- `OPENAI_API_KEY`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_USER_ID`

GitHub Actionsでは `DRY_RUN=false` で実行します。

重複通知防止のため、SQLite DBの `notified_tweets` を `data/x_reply_radar.db` に保存し、実行後にGitHub Actionsが自動コミットします。リポジトリの `Settings > Actions > General > Workflow permissions` は `Read and write permissions` にしてください。

PCを起動していなくても、GitHub ActionsがGitHub側のサーバーで実行します。Macがスリープ中・電源OFFでも、Secretsとworkflowが正しく設定されていれば動きます。

## 通知条件

通知対象は以下をすべて満たす投稿です。

1. カテゴリ別の伸び条件を満たす
2. `relevance_score >= 20`
3. リプまたは引用が1件以上ある
4. 炎上リスクが高くない
5. 既に通知済みではない

FAST_MARKETカテゴリのみ速報性を重視し、リプまたは引用が0件でも `relevance_score >= 40` なら通知対象にできます。

1回の実行で通知する投稿は最大5件です。優先順位は `reply_priority=S`、関連度、エンゲージメント、投稿時間の順です。

## テスト

```bash
pytest
```

最低限、以下を確認しています。

- `watchlist.txt` を読み込める
- `engagement_score` が正しく計算される
- カテゴリ別の伸び判定が正しい
- `relevance_score` が正しく計算される
- 通知済み `tweet_id` が再通知されない
- LINE通知フォーマットが崩れない

`DRY_RUN=true` のLINE未送信は、`LineClient` がコンソール出力だけを行う実装で担保しています。

## よくあるエラー

### X API 401

`X_BEARER_TOKEN` が間違っている、期限切れ、または別アプリのトークンの可能性があります。

### X API 403

X APIのプランや権限で対象エンドポイントが使えない可能性があります。`/2/users/by` と `/2/users/{id}/tweets` の利用可否を確認してください。

### X API 429

レート制限です。ログに出力し、短いリトライ後も失敗した場合はその実行を終了または対象アカウントをスキップします。

### LINE 401

`LINE_CHANNEL_ACCESS_TOKEN` が間違っている、期限切れ、またはMessaging APIチャネルのトークンではない可能性があります。

### LINE_USER_IDがわからない

Webhookイベントの `source.userId` を確認してください。Botを自分のLINEで友だち追加しておく必要があります。

### OpenAI APIエラー

`OPENAI_API_KEY`、モデル名、利用上限を確認してください。生成に失敗した投稿は安全側で `reply_priority=B` として扱います。

## 注意事項

- Xへの自動投稿はしません。
- リプ案は必ず自分で確認してから手動投稿してください。
- 未確認情報や投資助言になりそうな表現は避けてください。
- 「買い」「売り」を直接勧める使い方はしないでください。
