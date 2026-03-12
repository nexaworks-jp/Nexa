"""
トレンド分析ワーカー
Hacker News / Reddit / Zenn / Qiita / Google Trends から
AIトピックを収集し、Claudeがスコアリングして上位トピックを返す
"""
import json
import time
import urllib.request
import urllib.parse
import anthropic
from datetime import datetime, timezone


# ========== ソース別取得 ==========

def fetch_hackernews(limit: int = 15) -> list[dict]:
    """Hacker News APIからAI関連トップ記事を取得"""
    results = []
    try:
        url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        with urllib.request.urlopen(url, timeout=10) as r:
            ids = json.loads(r.read())[:50]

        ai_keywords = ["ai", "llm", "gpt", "claude", "gemini", "openai", "anthropic",
                       "machine learning", "neural", "stable diffusion", "midjourney",
                       "mistral", "llama", "deepseek", "sora", "copilot"]

        for item_id in ids:
            if len(results) >= limit:
                break
            try:
                item_url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
                with urllib.request.urlopen(item_url, timeout=5) as r:
                    item = json.loads(r.read())
                title = item.get("title", "").lower()
                if any(kw in title for kw in ai_keywords):
                    results.append({
                        "title": item.get("title", ""),
                        "score": item.get("score", 0),
                        "comments": item.get("descendants", 0),
                        "source": "hackernews",
                        "url": item.get("url", "")
                    })
                time.sleep(0.05)
            except Exception:
                continue
    except Exception as e:
        print(f"[TrendAnalyzer] HackerNews取得エラー: {e}")
    return results


def fetch_reddit_ai(limit: int = 10) -> list[dict]:
    """Reddit r/artificialintelligence からホット投稿を取得"""
    results = []
    try:
        url = "https://www.reddit.com/r/artificial/hot.json?limit=25"
        req = urllib.request.Request(url, headers={"User-Agent": "AINewsBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        for post in data.get("data", {}).get("children", [])[:limit]:
            pd = post.get("data", {})
            results.append({
                "title": pd.get("title", ""),
                "score": pd.get("score", 0),
                "comments": pd.get("num_comments", 0),
                "source": "reddit",
                "url": f"https://reddit.com{pd.get('permalink', '')}"
            })
    except Exception as e:
        print(f"[TrendAnalyzer] Reddit取得エラー: {e}")
    return results


def fetch_zenn_trending(limit: int = 10) -> list[dict]:
    """Zennのトレンド記事を取得"""
    results = []
    try:
        url = "https://zenn.dev/api/articles?order=trending&count=20"
        req = urllib.request.Request(url, headers={"User-Agent": "AINewsBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        ai_keywords = ["ai", "llm", "gpt", "claude", "gemini", "chatgpt",
                       "機械学習", "生成ai", "画像生成", "プロンプト", "langchain"]

        for article in data.get("articles", [])[:30]:
            title = article.get("title", "").lower()
            if any(kw in title for kw in ai_keywords):
                results.append({
                    "title": article.get("title", ""),
                    "score": article.get("liked_count", 0),
                    "comments": 0,
                    "source": "zenn",
                    "url": f"https://zenn.dev{article.get('path', '')}"
                })
                if len(results) >= limit:
                    break
    except Exception as e:
        print(f"[TrendAnalyzer] Zenn取得エラー: {e}")
    return results


def fetch_google_trends(limit: int = 10) -> list[dict]:
    """Google Trendsから日本のAI関連急上昇ワードを取得"""
    results = []
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl='ja-JP', tz=540, timeout=(10, 25))
        trending = pytrends.trending_searches(pn='japan')
        keywords = trending[0].tolist()[:30]

        ai_keywords = ["ai", "gpt", "claude", "gemini", "chatgpt", "生成ai", "人工知能",
                       "midjourney", "copilot", "llm", "画像生成", "deepseek", "sora"]

        for kw in keywords:
            if any(ak in kw.lower() for ak in ai_keywords):
                results.append({
                    "title": kw,
                    "score": 100,
                    "comments": 0,
                    "source": "google_trends",
                    "url": ""
                })
                if len(results) >= limit:
                    break
    except Exception as e:
        print(f"[TrendAnalyzer] Google Trends取得エラー: {e}")
    return results


# ========== スコアリング ==========

def score_and_select(client: anthropic.Anthropic, candidates: list[dict],
                     recent_titles: list[str], weights: dict, num_topics: int = 4) -> list[str]:
    """Claudeが候補トピックをスコアリングして上位を返す"""
    if not candidates:
        return []

    # ソース別重みを適用した候補リスト
    weighted = []
    for c in candidates:
        w = weights.get(c["source"], 1.0)
        weighted.append({
            **c,
            "weighted_score": (c["score"] + c["comments"] * 2) * w
        })

    # バズ度で事前ソート（上位30件に絞る）
    weighted.sort(key=lambda x: x["weighted_score"], reverse=True)
    top_candidates = weighted[:30]

    recent_str = "\n".join(f"- {t}" for t in recent_titles[-30:]) if recent_titles else "なし"
    candidates_str = "\n".join(
        f"{i+1}. [{c['source']}] {c['title']} (スコア:{c['score']}, コメント:{c['comments']})"
        for i, c in enumerate(top_candidates)
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""以下の候補から、日本語AI初心者向けサイトに最適な記事トピックを{num_topics}つ選んでください。

【選定基準（重要度順）】
1. 初心者向け度(30%): パソコン初心者でも「なるほど！」と思えるか
2. バズ度(30%): 今話題になっているか、関心が高いか
3. 新鮮さ(25%): 最近の話題か
4. AI関連度(15%): AIに関する内容か

【除外条件】
- 以下の過去記事と似ているタイトルは除外してください：
{recent_str}

【候補リスト】
{candidates_str}

出力形式（日本語の記事タイトル案で）：
{{"selected_topics": ["トピック1", "トピック2", "トピック3", "トピック4"]}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end])
            return data.get("selected_topics", [])
        except Exception:
            pass
    return [c["title"] for c in top_candidates[:num_topics]]


# ========== メイン ==========

def load_source_weights(memory_dir: str) -> dict:
    """memory/source_weights.json からソース重みを読み込む"""
    import os
    path = os.path.join(memory_dir, "source_weights.json")
    default = {
        "hackernews": 1.0,
        "reddit": 1.2,
        "zenn": 1.5,
        "qiita": 1.5,
        "google_trends": 0.8
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return {**default, **json.load(f)}
        except Exception:
            pass
    return default


def analyze(config: dict) -> dict:
    """
    トレンド分析メイン関数
    戻り値: { "topics": [...], "source": "multi", "analyzed_at": "..." }
    """
    import os
    api_key = config.get("anthropic_api_key", "")
    client = anthropic.Anthropic(api_key=api_key)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    memory_dir = os.path.join(base_dir, "memory")
    weights = load_source_weights(memory_dir)

    # 過去記事タイトルを読み込む（重複チェック用）
    topics_history_path = os.path.join(memory_dir, "topics_history.json")
    recent_titles = []
    if os.path.exists(topics_history_path):
        try:
            with open(topics_history_path, "r", encoding="utf-8") as f:
                recent_titles = json.load(f)
        except Exception:
            pass

    num_topics = config.get("settings", {}).get("note_post_per_day", 4)

    print("[TrendAnalyzer] 各ソースからトレンド取得中...")
    candidates = []

    hn = fetch_hackernews(15)
    print(f"[TrendAnalyzer] HackerNews: {len(hn)}件")
    candidates.extend(hn)

    rd = fetch_reddit_ai(10)
    print(f"[TrendAnalyzer] Reddit: {len(rd)}件")
    candidates.extend(rd)

    zn = fetch_zenn_trending(10)
    print(f"[TrendAnalyzer] Zenn: {len(zn)}件")
    candidates.extend(zn)

    gt = fetch_google_trends(5)
    print(f"[TrendAnalyzer] Google Trends: {len(gt)}件")
    candidates.extend(gt)

    if not candidates:
        print("[TrendAnalyzer] 全ソース失敗。Claudeのフォールバックを使用")
        # フォールバック: Claudeの知識ベース
        from workers.trend_analyzer_fallback import get_fallback_topics
        topics = get_fallback_topics(client)
    else:
        print(f"[TrendAnalyzer] 合計{len(candidates)}件の候補をスコアリング中...")
        topics = score_and_select(client, candidates, recent_titles, weights, num_topics)

    print(f"[TrendAnalyzer] 選定トピック: {topics}")

    # ソース使用履歴を記録（週次改善用）
    source_usage = {}
    for c in candidates:
        source_usage[c["source"]] = source_usage.get(c["source"], 0) + 1

    return {
        "topics": topics,
        "source": "multi",
        "source_counts": source_usage,
        "analyzed_at": datetime.now().isoformat()
    }
