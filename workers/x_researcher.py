"""
X(Twitter)リサーチモジュール
人気AIアカウントの投稿スタイルを学習し、memory/x_insights.json に保存する。
週次で自動実行され、学習結果はx_claude_beginner.md と自己改善に反映される。
"""
import json
import os
import re
from datetime import datetime

import anthropic

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 学習対象アカウント（日本語AI系の人気アカウント）
# 自己改善によって自動的に追加・入れ替えされる
DEFAULT_TARGET_ACCOUNTS = [
    "piboblockchain",    # AIビジネス系
    "masahirochaen",     # AI活用系
    "kajikent",         # テック系
    "isodaakira",       # AI解説系
]

# 学習対象の検索クエリ
SEARCH_QUERIES = [
    "Claude AI 使い方 lang:ja",
    "ChatGPT 活用 初心者 lang:ja",
    "生成AI 便利 lang:ja",
    "AI ツール おすすめ lang:ja",
]


def fetch_popular_tweets_via_api(config: dict, queries: list, max_per_query: int = 10) -> list:
    """Twitter API v2 でバズっているAI系ツイートを取得"""
    try:
        import tweepy
        x_cfg = config.get("x_twitter", {})
        bearer = x_cfg.get("bearer_token", "")
        if not bearer or bearer == "YOUR_BEARER_TOKEN":
            print("[XResearcher] Bearer Token未設定。スキップ。")
            return []

        client = tweepy.Client(bearer_token=bearer)
        results = []

        for query in queries:
            try:
                # min_replies=2 以上のツイートを取得（反応があるものだけ）
                resp = client.search_recent_tweets(
                    query=f"{query} -is:retweet min_replies:2",
                    max_results=max_per_query,
                    tweet_fields=["public_metrics", "created_at", "text"],
                    sort_order="relevancy"
                )
                if resp.data:
                    for tweet in resp.data:
                        metrics = tweet.public_metrics or {}
                        results.append({
                            "text": tweet.text,
                            "likes": metrics.get("like_count", 0),
                            "retweets": metrics.get("retweet_count", 0),
                            "replies": metrics.get("reply_count", 0),
                            "engagement": metrics.get("like_count", 0) + metrics.get("retweet_count", 0) * 3,
                            "query": query,
                        })
            except Exception as e:
                print(f"[XResearcher] 検索エラー ({query}): {e}")
                continue

        # エンゲージメント順にソート
        results.sort(key=lambda x: x["engagement"], reverse=True)
        print(f"[XResearcher] API経由で{len(results)}件取得")
        return results

    except ImportError:
        print("[XResearcher] tweepy未インストール")
        return []
    except Exception as e:
        print(f"[XResearcher] API取得エラー: {e}")
        return []


def check_engagement_health(config: dict) -> dict:
    """
    直近の自分のツイートのエンゲージメントを確認し、シャドーバンの可能性を評価する。
    エンゲージメント率が急落していればシャドーバンを疑う。
    戻り値: { "shadowban_risk": "low/medium/high", "avg_engagement": float, "tweet_count": int }
    """
    try:
        import tweepy
        x_cfg = config.get("x_twitter", {})
        bearer = x_cfg.get("bearer_token", "")
        access_token = x_cfg.get("access_token", "")
        access_token_secret = x_cfg.get("access_token_secret", "")
        api_key = x_cfg.get("api_key", "")
        api_secret = x_cfg.get("api_secret", "")
        if not all([bearer, access_token, api_key]):
            return {"shadowban_risk": "unknown", "reason": "API未設定"}

        client_tw = tweepy.Client(
            bearer_token=bearer,
            consumer_key=api_key, consumer_secret=api_secret,
            access_token=access_token, access_token_secret=access_token_secret
        )

        # tweet_history.json から直近のtweetIDを取得
        history_path = os.path.join(BASE_DIR, "memory", "tweet_history.json")
        if not os.path.exists(history_path):
            return {"shadowban_risk": "unknown", "reason": "投稿履歴なし"}

        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)

        recent_ids = [h["tweet_id"] for h in history[-20:]]
        if not recent_ids:
            return {"shadowban_risk": "unknown", "reason": "投稿履歴なし"}

        # APIでエンゲージメント取得
        tweets_data = client_tw.get_tweets(
            ids=recent_ids,
            tweet_fields=["public_metrics"]
        )
        if not tweets_data or not tweets_data.data:
            return {"shadowban_risk": "unknown", "reason": "API取得失敗"}

        engagements = []
        for t in tweets_data.data:
            m = t.public_metrics or {}
            eng = m.get("like_count", 0) + m.get("retweet_count", 0) * 2 + m.get("reply_count", 0)
            engagements.append(eng)

        avg_eng = sum(engagements) / len(engagements) if engagements else 0
        tweet_count = len(engagements)

        # リスク評価（平均エンゲージメントが著しく低い場合）
        # 新アカウント初期は低くて当然なので緩めの基準
        if avg_eng < 0.1 and tweet_count >= 10:
            risk = "high"
        elif avg_eng < 0.5 and tweet_count >= 10:
            risk = "medium"
        else:
            risk = "low"

        result = {
            "shadowban_risk": risk,
            "avg_engagement": round(avg_eng, 2),
            "tweet_count": tweet_count,
            "checked_at": datetime.now().isoformat()
        }

        # memory に保存
        health_path = os.path.join(BASE_DIR, "memory", "x_health.json")
        with open(health_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"[XResearcher] エンゲージメント健全性: リスク={risk} 平均={avg_eng:.2f} ({tweet_count}件)")
        return result

    except Exception as e:
        print(f"[XResearcher] エンゲージメントチェックエラー: {e}")
        return {"shadowban_risk": "unknown", "reason": str(e)}


def analyze_tweet_patterns(client: anthropic.Anthropic, tweets: list, current_style: str) -> dict:
    """バズったツイートをClaudeが分析し、学習ポイントを抽出する"""
    if not tweets:
        # ツイートが取れなくてもClaudeの知識から学習できる
        top_tweets_str = "（API取得なし）"
    else:
        top = tweets[:15]
        top_tweets_str = "\n\n".join([
            f"[エンゲージメント:{t['engagement']}] {t['text'][:200]}"
            for t in top
        ])

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""あなたはXのコンテンツ戦略の専門家です。
日本語AI系アカウントのバズツイートを分析し、学習ポイントを抽出してください。

【バズったツイート（エンゲージメント順）】
{top_tweets_str}

【現在の投稿スタイルガイド概要】
{current_style[:500]}

以下の観点で分析してください：
1. バズる投稿に共通するフォーマット・構造
2. 読者が反応しやすい切り口・言い回し
3. 文字数・改行・絵文字の使い方の傾向
4. 現在のスタイルガイドに取り入れるべき改善点
5. シャドーバンリスクになる避けるべきパターン（ハッシュタグ過多・外部リンク多用・エンゲージメント誘導・同一パターン繰り返しなど）

【シャドーバン回避の重要知識（2025年版）】
- ハッシュタグは1〜2個が最適。3個以上でエンゲージメント17%低下
- 外部リンクを毎ポストに入れるとリーチが下がる（X内コンテンツを優遇するアルゴリズム）
- 「RTして」「いいねして」等のエンゲージメント誘導はスパム判定リスク
- 同じ投稿パターンの繰り返しがBot判定されやすい
- 投稿後15分の初動エンゲージメントがアルゴリズム評価で最重要

JSON形式で出力：
{{
  "key_patterns": ["パターン1", "パターン2", "パターン3"],
  "high_engagement_formats": ["フォーマット1", "フォーマット2"],
  "style_improvements": ["改善点1", "改善点2"],
  "avoid_patterns": ["避けるべき1（シャドーバンリスク含む）", "避けるべき2"],
  "shadowban_avoidance_tips": ["シャドーバン対策1", "シャドーバン対策2"],
  "new_post_examples": ["例文1（140字以内）", "例文2（140字以内）"],
  "summary": "学習まとめ（100文字以内）",
  "update_style_guide": true
}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except Exception:
            pass
    return {"summary": "分析失敗", "update_style_guide": False}


def update_x_style_guide(insights: dict):
    """x_claude_beginner.md の学習セクションを自動更新する"""
    path = os.path.join(BASE_DIR, "note用", "x_claude_beginner.md")
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    now = datetime.now().strftime("%Y-%m-%d")
    patterns = "\n".join(f"- {p}" for p in insights.get("key_patterns", []))
    formats = "\n".join(f"- {f}" for f in insights.get("high_engagement_formats", []))
    improvements = "\n".join(f"- {i}" for i in insights.get("style_improvements", []))
    examples = "\n\n".join([f"```\n{e}\n```" for e in insights.get("new_post_examples", [])])

    new_section = f"""
## 📊 自動学習セクション（{now} 更新）

### バズる投稿の共通パターン
{patterns}

### 高エンゲージメントフォーマット
{formats}

### 取り入れるべき改善点
{improvements}

### 学習から生成した投稿例
{examples}

**学習まとめ:** {insights.get('summary', '')}

---
"""

    # 既存の自動学習セクションを置き換え or 末尾に追加
    marker = "## 📊 自動学習セクション"
    if marker in content:
        # 既存セクションを削除して更新
        idx = content.find(marker)
        # 次のセクションまたは末尾を探す
        next_section = content.find("\n## ", idx + 1)
        if next_section > 0:
            content = content[:idx] + new_section + content[next_section:]
        else:
            content = content[:idx] + new_section
    else:
        content = content.rstrip() + "\n" + new_section

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[XResearcher] x_claude_beginner.md を更新しました")


def save_insights(insights: dict, tweets: list):
    """学習結果を memory/x_insights.json に保存"""
    path = os.path.join(BASE_DIR, "memory", "x_insights.json")
    data = {
        "updated_at": datetime.now().isoformat(),
        "analysis": insights,
        "sample_count": len(tweets),
        "top_tweets": tweets[:5],
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[XResearcher] x_insights.json 保存完了")


def run(config: dict):
    """Xリサーチ・学習を実行"""
    print("[XResearcher] X投稿スタイル学習を開始...")
    api_key = config.get("anthropic_api_key", "")
    if not api_key:
        return

    claude = anthropic.Anthropic(api_key=api_key)

    # エンゲージメント健全性チェック（シャドーバン検知）
    health = check_engagement_health(config)
    if health.get("shadowban_risk") == "high":
        print("[XResearcher] ⚠️ シャドーバンの可能性が高いです！投稿頻度を下げることを推奨。")
    elif health.get("shadowban_risk") == "medium":
        print("[XResearcher] ⚠️ エンゲージメントが低め。コンテンツパターンを多様化してください。")

    # 学習対象クエリを memory から読み込む（自己改善で追加可能）
    insights_path = os.path.join(BASE_DIR, "memory", "x_insights.json")
    queries = SEARCH_QUERIES.copy()
    if os.path.exists(insights_path):
        try:
            with open(insights_path, "r", encoding="utf-8") as f:
                prev = json.load(f)
            extra = prev.get("extra_queries", [])
            queries = list(set(queries + extra))
        except Exception:
            pass

    # Twitter APIで人気ツイート取得
    tweets = fetch_popular_tweets_via_api(config, queries, max_per_query=8)

    # 現在のスタイルガイドを読み込む
    style_path = os.path.join(BASE_DIR, "note用", "x_claude_beginner.md")
    current_style = ""
    if os.path.exists(style_path):
        with open(style_path, "r", encoding="utf-8") as f:
            current_style = f.read()

    # Claudeで分析
    insights = analyze_tweet_patterns(claude, tweets, current_style)
    print(f"[XResearcher] 学習まとめ: {insights.get('summary', '')}")

    # スタイルガイドを更新
    if insights.get("update_style_guide", False):
        update_x_style_guide(insights)

    # 結果を保存
    save_insights(insights, tweets)
