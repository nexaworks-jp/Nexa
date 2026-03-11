# セットアップガイド（60分で完了）

## Step 1: GitHubリポジトリ作成（10分）

1. https://github.com/new にアクセス
2. Repository name: `ai-company`（または好きな名前）
3. **Private** を選択（APIキーを守るため）
4. 「Create repository」クリック
5. このフォルダをそのままGitHubにアップロード

```bash
# このコマンドをai-companyフォルダで実行
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/あなたのユーザー名/ai-company.git
git push -u origin main
```

## Step 2: Anthropic APIキー取得（5分）

1. https://console.anthropic.com/ にアクセス
2. アカウント作成 or ログイン
3. 「API Keys」→「Create Key」
4. コピーしておく（`sk-ant-...`で始まる文字列）

## Step 3: note.comアカウント設定（5分）

1. https://note.com にアクセス
2. アカウント作成 or ログイン
3. 「クリエイターページ」を有効化
4. プロフィールを整える（AIが書いた記事の信頼性UP）
5. 「有料コンテンツ」設定を有効化

## Step 4: X Developer API取得（20分）

1. https://developer.twitter.com/en/portal/dashboard にアクセス
2. 「Create Project」→「Create App」
3. 「Free」プランでOK
4. 「Keys and Tokens」から以下を取得：
   - API Key & Secret
   - Access Token & Secret
   - Bearer Token

## Step 5: GitHub Secretsに登録（10分）

GitHubリポジトリの Settings → Secrets and variables → Actions

以下を全て登録：
| Secret名 | 値 |
|---------|---|
| `ANTHROPIC_API_KEY` | Anthropic APIキー |
| `NOTE_EMAIL` | note.comのメールアドレス |
| `NOTE_PASSWORD` | note.comのパスワード |
| `X_API_KEY` | X API Key |
| `X_API_SECRET` | X API Key Secret |
| `X_ACCESS_TOKEN` | X Access Token |
| `X_ACCESS_TOKEN_SECRET` | X Access Token Secret |
| `X_BEARER_TOKEN` | X Bearer Token |

## Step 5.5: LINE連携設定（15分）

1. https://developers.line.biz/console/ にアクセス
2. 「プロバイダー作成」→「Messaging API チャンネル作成」
3. 「チャンネル基本設定」→**チャンネルシークレット**をコピー
4. 「Messaging API設定」→**チャンネルアクセストークン（長期）**を発行・コピー
5. 作ったボットをLINEで友達追加
6. ボットにメッセージを送って **User IDを確認**:
   ```
   curl -H "Authorization: Bearer {チャンネルアクセストークン}" \
   https://api.line.me/v2/bot/followers/ids
   ```
7. config.json の `line` セクションに貼り付け

### Webhook設定（双方向コマンドを使う場合）

**ローカルPC用（ngrok）:**
```bash
# ngrokインストール: https://ngrok.com/download
ngrok http 8000
# 表示されたURL (https://xxxx.ngrok.io) を LINE Console の Webhook URL に設定
python line_webhook.py  # 別ターミナルで起動
```

**常時稼働用（Render.com 無料）:**
1. https://render.com でアカウント作成
2. New → Web Service → GitHubリポジトリを接続
3. Start Command: `python line_webhook.py`
4. 発行されたURLを LINE Console の Webhook URL に設定: `https://xxxx.onrender.com/webhook`

## Step 6: 動作確認（5分）

GitHubリポジトリの「Actions」タブから「AI Company Auto Run」→「Run workflow」で手動実行。

ログを確認して、エラーがなければ完了！

---

## 以降は完全自動

- 毎日 6:00, 12:00, 18:00, 22:00 JST に自動実行
- note記事を自動生成・投稿
- Xを自動投稿
- 結果はmemory/フォルダに自動保存

## 収益確認

```bash
# ローカルで確認する場合
python main.py --report
```

または GitHub Actions のログを見るだけでOK。
