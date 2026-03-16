"""
noteリサーチワーカー
毎週エボサイの記事データと類似アカウントを取得・分析して
note用/evopsy.md と note用/market_insights.md を自動更新する
"""
import json
import os
import requests
import anthropic
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE_DIR = os.path.join(BASE_DIR, "note用")

# 調査対象の参考クリエイター
TARGET_CREATORS = ["youth_waster"]

# 類似ジャンルの検索キーワード
RESEARCH_KEYWORDS = [
    "進化心理学", "人間行動 進化", "サピエンス 心理",
    "行動経済学 人間", "進化論 現代"
]

# 類似ジャンルの候補クリエイター（手動で追加していく）
CANDIDATE_CREATORS = [
    "youth_waster",
    # 週次実行で自動追加される
]


def fetch_creator_articles(username: str, pages: int = 3) -> list:
    """noteのAPIからクリエイターの記事一覧を取得"""
    articles = []
    for page in range(1, pages + 1):
        try:
            resp = requests.get(
                f"https://note.com/api/v2/creators/{username}/contents",
                params={"kind": "note", "page": page, "per": 20},
                timeout=10
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            notes = data.get("data", {}).get("contents", [])
            if not notes:
                break
            for n in notes:
                articles.append({
                    "key": n.get("key", ""),
                    "title": n.get("name", ""),
                    "likes": n.get("likeCount", 0),
                    "price": n.get("price", 0),
                    "published_at": n.get("publishAt", ""),
                    "creator": username,
                })
        except Exception as e:
            print(f"[NoteResearcher] {username} ページ{page} 取得エラー: {e}")
            break
    return articles


def fetch_article_body(key: str) -> str:
    """記事の本文テキストを取得（無料部分のみ）"""
    try:
        resp = requests.get(
            f"https://note.com/api/v3/notes/{key}",
            timeout=10
        )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        note_data = data.get("data", {})
        # body または body_plain_text
        body = note_data.get("body", "") or ""
        if isinstance(body, list):
            # ブロック形式の場合はテキスト抽出
            texts = []
            for block in body:
                if isinstance(block, dict):
                    text = block.get("text", "") or block.get("body", "")
                    if text:
                        texts.append(str(text))
            return "\n".join(texts)[:3000]
        return str(body)[:3000]
    except Exception as e:
        print(f"[NoteResearcher] 記事本文取得エラー {key}: {e}")
        return ""


def discover_similar_creators(keyword: str) -> list:
    """noteの検索APIで類似クリエイターを探す"""
    creators = []
    try:
        resp = requests.get(
            "https://note.com/api/v1/searches",
            params={"context": "note", "q": keyword, "order": "like", "per": 20},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            notes = data.get("data", {}).get("notes", []) or data.get("notes", [])
            for n in notes:
                creator = n.get("user", {}) or {}
                urlname = creator.get("urlname", "")
                if urlname and urlname not in creators and urlname != "youth_waster":
                    creators.append(urlname)
    except Exception as e:
        print(f"[NoteResearcher] クリエイター探索エラー: {e}")
    return creators[:5]


def analyze_with_claude(config: dict, articles_data: dict, similar_creators_data: dict) -> dict:
    """Claude Haikuで記事データを分析して戦略的インサイトを生成"""
    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])

    # 上位記事のサマリーを作成
    top_articles = sorted(
        articles_data.get("youth_waster", []),
        key=lambda x: x.get("likes", 0),
        reverse=True
    )[:10]

    similar_summary = []
    for creator, arts in similar_creators_data.items():
        top = sorted(arts, key=lambda x: x.get("likes", 0), reverse=True)[:3]
        similar_summary.append({
            "creator": creator,
            "top_titles": [a["title"] for a in top],
            "avg_likes": sum(a["likes"] for a in top) // max(len(top), 1)
        })

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""進化心理学ジャンルのnote市場を分析してください。

【エボサイ（参考クリエイター）の人気記事TOP10】
{json.dumps(top_articles, ensure_ascii=False, indent=2)}

【類似クリエイターのデータ】
{json.dumps(similar_summary, ensure_ascii=False, indent=2)}

以下のJSON形式で分析を出力してください：
{{
  "top_performing_themes": ["最もいいねが多いテーマ1", "テーマ2", "テーマ3"],
  "title_patterns": ["効果的なタイトルパターン1", "パターン2"],
  "pricing_insight": "価格設定の傾向と推奨",
  "content_strategy": "収益最大化のためのコンテンツ戦略（150文字以内）",
  "recommended_topics": ["今週書くべきトピック1", "トピック2", "トピック3", "トピック4", "トピック5"],
  "style_updates": "文体・構成の改善点（100文字以内）",
  "competitive_gaps": "競合が手薄なニッチ（100文字以内）"
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
    return {}


def update_evopsy_md(articles: list, analysis: dict):
    """note用/evopsy.md の人気記事データと推奨トピックを更新"""
    os.makedirs(NOTE_DIR, exist_ok=True)
    filepath = os.path.join(NOTE_DIR, "evopsy.md")

    existing = ""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            existing = f.read()

    # 動的データセクションを更新
    top_articles = sorted(articles, key=lambda x: x.get("likes", 0), reverse=True)[:15]
    top_list = "\n".join([
        f"- {a['title']} (❤️{a['likes']} / ¥{a['price']})"
        for a in top_articles
    ])

    now = datetime.now().strftime("%Y-%m-%d")
    recommended = "\n".join([f"- {t}" for t in analysis.get("recommended_topics", [])])
    competitive_gaps = analysis.get("competitive_gaps", "")
    content_strategy = analysis.get("content_strategy", "")
    style_updates = analysis.get("style_updates", "")

    dynamic_section = f"""
---

## 📊 最新分析データ（{now}更新）

### いいね数TOP記事
{top_list}

### 今週の推奨トピック
{recommended}

### 競合が手薄なニッチ
{competitive_gaps}

### コンテンツ戦略
{content_strategy}

### 文体改善メモ
{style_updates}
"""

    # 既存の動的セクションを削除して更新
    if "## 📊 最新分析データ" in existing:
        existing = existing[:existing.index("## 📊 最新分析データ") - 4]

    updated = existing.rstrip() + "\n" + dynamic_section

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(updated)

    print(f"[NoteResearcher] evopsy.md 更新完了")


def update_market_insights(similar_creators_data: dict, analysis: dict):
    """note用/market_insights.md を更新"""
    os.makedirs(NOTE_DIR, exist_ok=True)
    filepath = os.path.join(NOTE_DIR, "market_insights.md")

    now = datetime.now().strftime("%Y-%m-%d")
    lines = [f"# note市場インサイト（{now}更新）\n"]

    lines.append("## 類似クリエイター分析\n")
    for creator, arts in similar_creators_data.items():
        if not arts:
            continue
        top = sorted(arts, key=lambda x: x.get("likes", 0), reverse=True)[:5]
        avg_likes = sum(a["likes"] for a in top) // max(len(top), 1)
        lines.append(f"### @{creator} (平均いいね: {avg_likes})\n")
        for a in top:
            lines.append(f"- {a['title']} (❤️{a['likes']})\n")
        lines.append("")

    if analysis:
        lines.append("## AI分析サマリー\n")
        lines.append(f"**人気テーマ**: {', '.join(analysis.get('top_performing_themes', []))}\n")
        lines.append(f"**タイトルパターン**: {', '.join(analysis.get('title_patterns', []))}\n")
        lines.append(f"**価格戦略**: {analysis.get('pricing_insight', '')}\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[NoteResearcher] market_insights.md 更新完了")


def update_candidates_file(new_creators: list):
    """note用/similar_creators.txt に類似クリエイターリストを保存"""
    os.makedirs(NOTE_DIR, exist_ok=True)
    filepath = os.path.join(NOTE_DIR, "similar_creators.txt")

    existing = set()
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            existing = set(f.read().strip().splitlines())

    existing.update(new_creators)
    existing.add("youth_waster")  # 常に含める

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(existing)))


def load_candidate_creators() -> list:
    """note用/similar_creators.txt からクリエイターリストを読む"""
    filepath = os.path.join(NOTE_DIR, "similar_creators.txt")
    if not os.path.exists(filepath):
        return ["youth_waster"]
    with open(filepath, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


AI_BEGINNER_KEYWORDS = [
    "Claude 使い方 初心者",
    "ChatGPT 初心者 始め方",
    "AI活用 初心者",
    "生成AI 使い方",
]


def fetch_popular_ai_articles(keywords: list, per_keyword: int = 10) -> list:
    """noteの検索APIでAI初心者向け人気記事を取得"""
    articles = []
    seen_keys = set()
    for keyword in keywords:
        try:
            resp = requests.get(
                "https://note.com/api/v1/searches",
                params={"context": "note", "q": keyword, "order": "like", "per": per_keyword},
                timeout=10
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            notes = data.get("data", {}).get("notes", []) or data.get("notes", [])
            for n in notes:
                key = n.get("key", "")
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    articles.append({
                        "key": key,
                        "title": n.get("name", ""),
                        "likes": n.get("likeCount", 0),
                        "price": n.get("price", 0),
                        "creator": (n.get("user") or {}).get("urlname", ""),
                        "keyword": keyword,
                    })
        except Exception as e:
            print(f"[NoteResearcher] AI記事検索エラー ({keyword}): {e}")
    return sorted(articles, key=lambda x: x.get("likes", 0), reverse=True)


def analyze_ai_beginner_trends(client: anthropic.Anthropic, articles: list) -> dict:
    """人気AI初心者記事をClaudeで分析してclaude_beginner.mdへの反映内容を生成"""
    top = articles[:20]
    titles_str = "\n".join([
        f"- 「{a['title']}」 (❤️{a['likes']} / ¥{a['price']})"
        for a in top
    ])

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": f"""noteで実際によく読まれているAI初心者向け記事のタイトルデータです。
このデータを分析して、記事執筆ガイドラインへの反映内容を出力してください。

【人気記事タイトル（いいね数順）】
{titles_str}

分析観点：
1. よくいいねされているタイトルのパターン・キーワード
2. 読者が特に求めているトピック・テーマ
3. 無料 vs 有料の傾向
4. 今すぐ書くべき推奨トピック（まだ自分が書いていない可能性が高いもの）

JSON形式で出力：
{{
  "hot_title_patterns": ["パターン1", "パターン2", "パターン3"],
  "top_topics": ["トピック1", "トピック2", "トピック3", "トピック4", "トピック5"],
  "pricing_trend": "無料/有料の傾向（50文字以内）",
  "recommended_next_articles": ["今すぐ書くべき記事タイトル案1", "案2", "案3"],
  "style_insight": "タイトル・構成から読み取れる読者ニーズ（100文字以内）"
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
    return {}


def update_claude_beginner_md(articles: list, analysis: dict):
    """note用/claude_beginner.md の動的データセクションを更新"""
    os.makedirs(NOTE_DIR, exist_ok=True)
    filepath = os.path.join(NOTE_DIR, "claude_beginner.md")

    if not os.path.exists(filepath):
        return

    with open(filepath, "r", encoding="utf-8") as f:
        existing = f.read()

    now = datetime.now().strftime("%Y-%m-%d")
    top5 = articles[:5]
    top_list = "\n".join([
        f"- 「{a['title']}」 (❤️{a['likes']} / ¥{a['price']})"
        for a in top5
    ])
    recommended = "\n".join([f"- {t}" for t in analysis.get("recommended_next_articles", [])])
    hot_patterns = "\n".join([f"- {p}" for p in analysis.get("hot_title_patterns", [])])
    top_topics = "\n".join([f"- {t}" for t in analysis.get("top_topics", [])])
    pricing = analysis.get("pricing_trend", "")
    style_insight = analysis.get("style_insight", "")

    dynamic_section = f"""
---

## 📊 note市場リサーチ（{now}更新・自動）

### いいね数TOP記事
{top_list}

### 今ホットなタイトルパターン
{hot_patterns}

### 読者が求めているトピック
{top_topics}

### 価格傾向
{pricing}

### 読者ニーズのインサイト
{style_insight}

### 今すぐ書くべき推奨記事
{recommended}
"""

    # 既存の動的セクションを削除して更新
    if "## 📊 note市場リサーチ" in existing:
        existing = existing[:existing.index("## 📊 note市場リサーチ") - 4]

    updated = existing.rstrip() + "\n" + dynamic_section

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(updated)

    print(f"[NoteResearcher] claude_beginner.md 市場データ更新完了")


def run(config: dict) -> dict:
    """メイン実行関数（週次で呼ぶ）"""
    print("[NoteResearcher] noteリサーチ開始...")

    # 1. 参考クリエイターの記事を取得
    all_articles = {}
    creators = load_candidate_creators()

    for creator in creators[:5]:  # API節約のため最大5クリエイター
        print(f"[NoteResearcher] @{creator} の記事取得中...")
        articles = fetch_creator_articles(creator, pages=2)
        all_articles[creator] = articles
        print(f"[NoteResearcher] → {len(articles)}件取得")

    # 2. 類似クリエイターを探す
    new_creators = []
    for keyword in RESEARCH_KEYWORDS[:2]:  # API節約のため2キーワードのみ
        found = discover_similar_creators(keyword)
        new_creators.extend(found)
    new_creators = list(set(new_creators))
    if new_creators:
        update_candidates_file(new_creators)
        print(f"[NoteResearcher] 新クリエイター発見: {new_creators}")

    # 3. 類似クリエイターの記事も取得
    similar_data = {}
    for creator in new_creators[:3]:  # API節約のため最大3件
        arts = fetch_creator_articles(creator, pages=1)
        if arts:
            similar_data[creator] = arts

    # 4. Claude で分析
    main_articles = all_articles.get("youth_waster", [])
    analysis = {}
    if main_articles:
        print("[NoteResearcher] AI分析中...")
        analysis = analyze_with_claude(config, all_articles, similar_data)

    # 5. ファイル更新（evopsy.mdは廃止済みのため呼び出しを削除）
    update_market_insights(similar_data, analysis)

    # 6. AI初心者ジャンルのリサーチ（claude_beginner.md 更新用）
    print("[NoteResearcher] AI初心者記事リサーチ中...")
    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    ai_articles = fetch_popular_ai_articles(AI_BEGINNER_KEYWORDS)
    print(f"[NoteResearcher] AI初心者記事 {len(ai_articles)}件取得")
    ai_analysis = {}
    if ai_articles:
        ai_analysis = analyze_ai_beginner_trends(client, ai_articles)
        update_claude_beginner_md(ai_articles, ai_analysis)

    total = sum(len(v) for v in all_articles.values())
    print(f"[NoteResearcher] 完了: {total}記事分析, 類似クリエイター{len(new_creators)}件発見")

    return {
        "articles_analyzed": total,
        "new_creators": new_creators,
        "analysis": analysis,
        "ai_beginner_analysis": ai_analysis
    }
