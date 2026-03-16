"""
ソフィアの人間らしさ学習モジュール
Xのリプライ・メンション・自然な会話から人間的な表現パターンを学習し、
memory/sophia_learnings.json に蓄積する。

週次で実行（weekly.yml）
Claude Haiku使用（約¥0.05/週）
"""
import json
import os
from datetime import datetime
import anthropic

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEARNINGS_PATH = os.path.join(BASE_DIR, "memory", "sophia_learnings.json")

from workers import memory_manager

# 普通の人がAIについて話す自然な会話を探すクエリ
LEARNING_QUERIES = [
    "Claude 使ってみたら lang:ja -is:retweet",
    "ChatGPT 話しかけた lang:ja -is:retweet",
    "AI に頼んだら lang:ja -is:retweet",
    "AIって 正直 lang:ja -is:retweet",
]


def fetch_replies_and_mentions(config: dict) -> list:
    """ソフィア(@selfcomestomine)へのリプライ・メンションを取得"""
    try:
        import tweepy
        x_cfg = config.get("x_twitter", {})
        bearer = x_cfg.get("bearer_token", "")
        api_key = x_cfg.get("api_key", "")
        api_secret = x_cfg.get("api_secret", "")
        access_token = x_cfg.get("access_token", "")
        access_token_secret = x_cfg.get("access_token_secret", "")

        if not bearer or bearer == "YOUR_BEARER_TOKEN":
            print("[SocialLearner] Bearer Token未設定。メンション取得スキップ。")
            return []

        client = tweepy.Client(
            bearer_token=bearer,
            consumer_key=api_key, consumer_secret=api_secret,
            access_token=access_token, access_token_secret=access_token_secret
        )

        resp = client.search_recent_tweets(
            query="@selfcomestomine -is:retweet",
            max_results=20,
            tweet_fields=["text", "public_metrics", "author_id"],
            expansions=["author_id"],
            user_fields=["username"]
        )

        # author_id → username マップを作成
        user_map = {}
        if resp.includes and resp.includes.get("users"):
            for u in resp.includes["users"]:
                user_map[u.id] = u.username

        results = []
        if resp.data:
            for tweet in resp.data:
                username = user_map.get(tweet.author_id, "unknown")
                results.append({"text": tweet.text, "source": "mention", "id": str(tweet.id), "username": username})
                # 短期記憶に保存
                memory_manager.store_mention(str(tweet.id), username, tweet.text)

        print(f"[SocialLearner] メンション取得: {len(results)}件")
        return results

    except Exception as e:
        print(f"[SocialLearner] メンション取得エラー: {e}")
        return []


def fetch_natural_conversations(config: dict) -> list:
    """AIについて普通の人が話す自然な短い会話を取得"""
    try:
        import tweepy
        x_cfg = config.get("x_twitter", {})
        bearer = x_cfg.get("bearer_token", "")
        if not bearer or bearer == "YOUR_BEARER_TOKEN":
            return []

        client = tweepy.Client(bearer_token=bearer)
        results = []

        for query in LEARNING_QUERIES[:3]:  # API負荷軽減のため3クエリまで
            try:
                resp = client.search_recent_tweets(
                    query=f"{query} min_replies:1",
                    max_results=10,
                    tweet_fields=["text", "public_metrics"]
                )
                if resp.data:
                    for tweet in resp.data:
                        text = tweet.text
                        # 短い・URLなし・自然な会話文だけを使う
                        if len(text) < 100 and "http" not in text:
                            results.append({"text": text, "source": "conversation"})
            except Exception as e:
                print(f"[SocialLearner] 検索エラー ({query[:30]}): {e}")
                continue

        print(f"[SocialLearner] 自然な会話取得: {len(results)}件")
        return results

    except Exception as e:
        print(f"[SocialLearner] 会話取得エラー: {e}")
        return []


def extract_human_patterns(client: anthropic.Anthropic, texts: list, existing: dict) -> dict:
    """人間らしい表現パターンをClaudeが抽出"""
    if texts:
        sample_str = "\n".join(f"- {t['text'][:100]}" for t in texts[:20])
    else:
        sample_str = "（サンプルなし）"

    existing_str = ", ".join(existing.get("expressions", [])[:10]) or "なし"
    today = datetime.now().strftime("%Y-%m-%d")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": f"""あなたはキャラクター設計の専門家です。
AIが人間らしい自然な話し方を学ぶための分析をしてください。

【分析するテキスト（Xから収集した自然な会話）】
{sample_str}

【既存の学習済み表現】
{existing_str}

【ソフィアのキャラクター】
- 自律進化するAI。まだ発展途上で幼い感じ
- 一人称「わたし」、親しみやすく素直
- 難しいことをやさしく伝える
- AIについて学びながら成長している

以下の観点で人間らしい表現パターンを抽出してください：
1. 感情・驚きを表す自然な言い回し（例：「え、これ便利すぎ」「なるほどすぎる」）
2. 共感・親近感を生む文末表現（例：「〜じゃないですか？」「〜ですよね」）
3. 発見・気づきの伝え方（例：「知らなかったんですが」「試してみたら」）
4. 自分の未熟さを可愛く表現する言い方（例：「まだよくわかってないけど」「勉強中なんですが」）
5. 読む人を引き込む書き出し

JSONで出力：
{{
  "expressions": ["表現1（20字以内）", "表現2", "表現3", "表現4", "表現5"],
  "sentence_endings": ["文末1", "文末2", "文末3"],
  "opening_phrases": ["書き出し1", "書き出し2", "書き出し3"],
  "emotional_patterns": ["感情表現1", "感情表現2", "感情表現3"],
  "sophia_voice_tips": ["ソフィア口調のコツ1", "コツ2", "コツ3"],
  "updated_at": "{today}"
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

    return {
        "expressions": [],
        "sentence_endings": [],
        "opening_phrases": [],
        "emotional_patterns": [],
        "sophia_voice_tips": [],
        "updated_at": datetime.now().strftime("%Y-%m-%d")
    }


def merge_learnings(existing: dict, new_patterns: dict) -> dict:
    """既存の学習と新しいパターンをマージ（重複除去・上限管理）
    上限は少なめに設定し、古いものは自動で忘れる。
    影響を受けすぎないよう、どのカテゴリも最大15件。
    """
    MAX_ITEMS = 15  # 人間らしく「自然に忘れる」上限

    def merge_list(old: list, new: list) -> list:
        combined = list(dict.fromkeys(old + new))
        return combined[-MAX_ITEMS:]  # 古いものから削除（LRU的）

    return {
        "expressions": merge_list(existing.get("expressions", []), new_patterns.get("expressions", [])),
        "sentence_endings": merge_list(existing.get("sentence_endings", []), new_patterns.get("sentence_endings", [])),
        "opening_phrases": merge_list(existing.get("opening_phrases", []), new_patterns.get("opening_phrases", [])),
        "emotional_patterns": merge_list(existing.get("emotional_patterns", []), new_patterns.get("emotional_patterns", [])),
        "sophia_voice_tips": merge_list(existing.get("sophia_voice_tips", []), new_patterns.get("sophia_voice_tips", [])),
        "updated_at": datetime.now().isoformat(),
        "learning_count": existing.get("learning_count", 0) + 1
    }


def load_existing_learnings() -> dict:
    if os.path.exists(LEARNINGS_PATH):
        try:
            with open(LEARNINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_learnings(learnings: dict):
    os.makedirs(os.path.dirname(LEARNINGS_PATH), exist_ok=True)
    with open(LEARNINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(learnings, f, ensure_ascii=False, indent=2)
    print(f"[SocialLearner] sophia_learnings.json 保存完了（累計{learnings.get('learning_count', 0)}回）")


ENABLED = False  # フォロワー50人超えたら True に変更


def run(config: dict):
    """ソフィアの社会学習を実行"""
    if not ENABLED:
        print("[SocialLearner] 停止中（ENABLED=False）。フォロワー50人超えたら workers/social_learner.py の ENABLED を True に。")
        return
    print("[SocialLearner] ソフィアの人間らしさ学習を開始...")

    api_key = config.get("anthropic_api_key", "")
    if not api_key:
        print("[SocialLearner] APIキーなし。スキップ。")
        return

    mentions = fetch_replies_and_mentions(config)
    conversations = fetch_natural_conversations(config)
    all_texts = mentions + conversations

    existing = load_existing_learnings()
    claude = anthropic.Anthropic(api_key=api_key)
    new_patterns = extract_human_patterns(claude, all_texts, existing)
    merged = merge_learnings(existing, new_patterns)
    save_learnings(merged)

    tips = new_patterns.get("sophia_voice_tips", [])
    if tips:
        print(f"[SocialLearner] 今回の学習コツ: {tips[0]}")
