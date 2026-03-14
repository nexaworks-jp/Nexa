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
    """Reddit AIサブレからRSS経由でホット投稿を取得（403回避）"""
    import xml.etree.ElementTree as ET
    results = []
    rss_urls = [
        "https://www.reddit.com/r/artificial/hot/.rss?limit=25",
        "https://www.reddit.com/r/LocalLLaMA/hot/.rss?limit=25",
    ]
    for url in rss_urls:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; RSS reader)",
                "Accept": "application/rss+xml, application/xml"
            })
            with urllib.request.urlopen(req, timeout=10) as r:
                root = ET.fromstring(r.read())
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//atom:entry", ns)[:limit]:
                title_el = entry.find("atom:title", ns)
                link_el = entry.find("atom:link", ns)
                if title_el is not None and title_el.text:
                    results.append({
                        "title": title_el.text.strip(),
                        "score": 50,
                        "comments": 0,
                        "source": "reddit",
                        "url": link_el.get("href", "") if link_el is not None else ""
                    })
        except Exception:
            continue
    if not results:
        print(f"[TrendAnalyzer] Reddit RSS取得エラー: 全URLが失敗")
    return results[:limit]


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
    """Google Trends RSS（日本）からAI関連急上昇ワードを取得"""
    import xml.etree.ElementTree as ET
    results = []
    try:
        url = "https://trends.google.co.jp/trending/rss?geo=JP"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            root = ET.fromstring(r.read())

        ai_keywords = ["ai", "gpt", "claude", "gemini", "chatgpt", "生成ai", "人工知能",
                       "copilot", "llm", "画像生成", "deepseek", "sora", "anthropic"]

        for item in root.findall(".//item"):
            title_el = item.find("title")
            if title_el is None or not title_el.text:
                continue
            kw = title_el.text.strip()
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


def fetch_qiita_trending(limit: int = 10) -> list[dict]:
    """QiitaのトレンドAI記事をAPIで取得"""
    results = []
    try:
        query = urllib.parse.urlencode({"query": "AI OR LLM OR Claude OR ChatGPT OR 生成AI", "per_page": 20})
        url = f"https://qiita.com/api/v2/items?{query}"
        req = urllib.request.Request(url, headers={"User-Agent": "AINewsBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            articles = json.loads(r.read())

        for a in articles[:limit]:
            results.append({
                "title": a.get("title", ""),
                "score": a.get("likes_count", 0),
                "comments": a.get("comments_count", 0),
                "source": "qiita",
                "url": a.get("url", "")
            })
    except Exception as e:
        print(f"[TrendAnalyzer] Qiita取得エラー: {e}")
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
            "content": f"""以下の候補から、AI解説サイトに最適な記事トピックを{num_topics}つ選んでください。

【サイトのコンセプト】
- メイン: Claude・AIの使い方を初心者向けに解説
- 実践系: Claude Code（Skills/CLAUDE.md/MCP/スラッシュコマンド）の実用Tipsも扱う

【選定基準（重要度順）】
1. バズ度・需要(35%): 今話題か、検索需要が高いか
2. 実用性(30%): 読んで「すぐ試せる」「役に立つ」内容か
3. 新鮮さ(20%): 過去記事と重複しないか
4. AI関連度(15%): AIに関する内容か

【トピックバランス（{num_topics}本中）】
- AI初心者向け記事: {num_topics - 1}本（登録・使い方・比較など）
- Claude Code実践系記事: 1本（Skills/CLAUDE.md/MCPなど開発者向け実用Tips）

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

    qi = fetch_qiita_trending(10)
    print(f"[TrendAnalyzer] Qiita: {len(qi)}件")
    candidates.extend(qi)

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
