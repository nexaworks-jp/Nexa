"""
コンテンツ生成ワーカー
Claude APIを使ってnote記事とXポストを生成する
"""
import anthropic
import json
import random
import os
from datetime import datetime


def load_style_reference() -> str:
    """claude_beginner.md を読み込んでスタイルガイドを返す"""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "note用", "claude_beginner.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def find_related_articles(client: anthropic.Anthropic, new_title: str,
                           new_summary: str, existing_articles: list) -> list:
    """
    既存記事の中から関連記事を最大2件選定する
    戻り値: [{"id": str, "title": str, "type": "prerequisite|related|next"}]
    """
    if not existing_articles:
        return []

    articles_str = "\n".join(
        f"- ID:{a.get('id','')} タイトル:「{a.get('title','')}」 概要:{a.get('summary','')[:50]}"
        for a in existing_articles[-20:]  # 直近20件
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": f"""新しく書く記事と関連する既存記事を最大2件選んでください。

【新記事】
タイトル: {new_title}
概要: {new_summary}

【既存記事一覧】
{articles_str}

関係タイプ:
- prerequisite: 新記事を読む前に読むべき前提記事
- related: 関連する内容の記事
- next: 新記事を読んだ後に読むと良い記事

関連がなければ空リストを返してください。

JSON出力:
{{"related": [{{"id": "記事ID", "title": "タイトル", "type": "prerequisite|related|next"}}]}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end])
            return data.get("related", [])
        except Exception:
            pass
    return []


def fact_check_article(client: anthropic.Anthropic, title: str, content: str) -> dict:
    """
    記事のファクトチェックを行う
    戻り値: {"passed": bool, "errors": str, "corrected_content": str}
    """
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""以下の記事のファクトチェックをしてください。

記事タイトル: {title}

記事本文:
{content}

チェック観点：
1. AIツールの機能・仕様に関する明らかな誤り
2. 存在しないURLやサービス名
3. 数字・価格・日付の明らかな誤り
4. 「〜は絶対に〜」など断言しすぎている誤情報

出力形式：
- 問題がなければ: {{"passed": true, "errors": "", "corrected_content": ""}}
- 問題があれば: {{"passed": false, "errors": "エラーの説明", "corrected_content": "修正済みの本文全体"}}

注意：AIの知識カットオフ以降の最新情報については「最新情報は公式サイトをご確認ください」という形で対応してください。
確実に間違いと言える場合のみ修正してください。"""
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
    return {"passed": True, "errors": "", "corrected_content": ""}


def create_note_article(client: anthropic.Anthropic, topic: str, published_topics: list, existing_articles: list = None) -> dict:
    """
    AI解説記事を生成する（ファクトチェック付き）
    戻り値: { "title": str, "content": str, "price": int, "hashtags": list }
    """
    avoid = ", ".join(published_topics[-20:]) if published_topics else "なし"

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": f"""あなたはAI初心者向け解説サイトのライターです。
以下のトピックについて、誰でもわかりやすい解説記事を書いてください。

トピック: {topic}
避けるべき最近のトピック: {avoid}

【記事の方針】
- 対象読者：昨日パソコンを買ったくらいの完全初心者
- 専門用語は使わない（使う場合は必ず「〇〇とは〜のこと」と説明）
- 手順は番号付きリストで具体的に
- コマンドやコード例がある場合はコードブロックで示す
- 「実際に試してみた」「こんな使い方がある」という実践的な内容
- 断定的な誤情報を避け、不確かな情報には「〜とされています」「公式サイトで確認を」と書く

【構成】
1. タイトル（30文字以内、初心者が「これ知りたい！」と思うもの）
2. リード文（「〜で悩んでいませんか？」という共感から始める）
3. 本文（1500〜2500文字、見出し付き）
   - ## でH2見出し、### でH3見出し
   - コマンド・コードは ```言語名 ブロック ``` 形式
4. まとめ

JSON形式で出力：
{{
  "title": "記事タイトル",
  "content": "記事本文（マークダウン）",
  "price": 0,
  "hashtags": ["AI", "初心者", "関連タグ"],
  "summary": "記事の概要（100文字）"
}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        data = json.loads(text[start:end])
    else:
        data = {
            "title": f"{topic}【初心者向け解説】",
            "content": text,
            "price": 0,
            "hashtags": ["AI", "初心者"],
            "summary": f"{topic}について解説します。"
        }

    # ファクトチェック（最大2回）
    for attempt in range(2):
        print(f"[ContentWriter] ファクトチェック中（{attempt + 1}回目）: {data.get('title', '')}")
        check = fact_check_article(client, data.get("title", ""), data.get("content", ""))
        if check.get("passed", True):
            print(f"[ContentWriter] ファクトチェック通過")
            break
        else:
            print(f"[ContentWriter] 修正が必要: {check.get('errors', '')}")
            if check.get("corrected_content"):
                data["content"] = check["corrected_content"]

    # 関連記事を選定
    if existing_articles is None:
        existing_articles = []
    related = find_related_articles(
        client,
        data.get("title", ""),
        data.get("summary", ""),
        existing_articles
    )
    data["related_articles"] = related

    data["topic"] = topic
    data["created_at"] = datetime.now().isoformat()
    return data


def create_x_post(client: anthropic.Anthropic, topic: str, style: str = "insight",
                   note_article: dict = None) -> dict:
    """
    X(Twitter)用の投稿を生成する
    style: "insight" | "thread_start" | "question" | "note_funnel"
    note_funnel: noteへの導線ポスト（記事公開時にURLを差し込む）
    """
    if style == "note_funnel" and note_article:
        # note記事への導線ポスト
        prompt = f"""Claude初心者向けnote記事への導線Xポストを書いてください。

記事タイトル: {note_article.get('title', '')}
記事サマリー: {note_article.get('summary', '')}
トピック: {topic}

条件：
- 120文字以内（URLスペース確保のため）
- 「これ知らないと損」「こんなことができる」という発見・驚きを伝える
- 絵文字は1〜2個
- 「詳しくはnoteで」「↓で解説しています」など導線フレーズを入れる
- ハッシュタグは本文に含めない
- URLは「[noteリンク]」というプレースホルダーにする（オーナーが差し替える）

JSON形式で出力：
{{
  "text": "ツイート本文（末尾に改行＋[noteリンク]を含む）",
  "hashtags": ["Claude", "AI活用"],
  "is_note_funnel": true
}}"""
    else:
        style_prompts = {
            "insight": "「実はClaudeで〇〇できる」という驚きの発見系",
            "thread_start": "「〇〇分でできる」「知らないと損なAI活用」ヒント系",
            "question": "「AIって難しそう？全然そんなことない」という安心・共感系",
        }
        prompt = f"""Claude・AIを初心者に届けるXポストを書いてください。

トピック: {topic}
スタイル: {style_prompts.get(style, style_prompts['insight'])}

条件：
- 140文字以内（日本語）
- 絵文字は1〜2個（親しみやすさのため）
- 「難しそう」という先入観を払拭する言葉を使う
- ハッシュタグは本文に含めない

JSON形式で出力：
{{
  "text": "ツイート本文",
  "hashtags": ["Claude", "AI活用"],
  "is_note_funnel": false
}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        data = json.loads(text[start:end])
    else:
        data = {"text": text[:140], "hashtags": [topic], "is_note_funnel": False}

    data["topic"] = topic
    data["style"] = style
    data["created_at"] = datetime.now().isoformat()
    return data


def _append_topic_history(title: str):
    """memory/topics_history.json に記事タイトルを追記する"""
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_dir, "memory", "topics_history.json")
    history = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
    history.append(title)
    history = history[-60:]  # 直近60件のみ保持
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def generate_content_batch(config: dict, trends: dict, published_memory: dict) -> dict:
    """
    一回の実行で生成するコンテンツをまとめて作る
    """
    api_key = config["anthropic_api_key"]
    client = anthropic.Anthropic(api_key=api_key)

    topics = trends.get("topics", [])
    published_topics = published_memory.get("topics_used", [])

    # 未使用トピックを優先
    unused = [t for t in topics if t not in published_topics]
    if not unused:
        unused = topics

    results = {
        "note_articles": [],
        "x_posts": [],
        "generated_at": datetime.now().isoformat()
    }

    # note記事を1〜2本生成
    note_count = config.get("settings", {}).get("note_post_per_day", 2)
    for i in range(min(note_count, len(unused))):
        topic = unused[i % len(unused)]
        print(f"[ContentWriter] note記事生成中: {topic}")
        try:
            # 静的サイトの既存記事を渡す（関連記事選定用）
            from publishers.static_site_publisher import load_articles_data
            existing = load_articles_data()
            article = create_note_article(client, topic, published_topics, existing)
            results["note_articles"].append(article)
            # トピック履歴に追加（重複防止用）
            _append_topic_history(article.get("title", ""))
        except Exception as e:
            print(f"[ContentWriter] 記事生成エラー: {e}")

    # Xポストを複数生成
    # note記事ごとに導線ポスト（note_funnel）を1本、残りは独立インサイト
    x_count = config.get("settings", {}).get("x_post_per_day", 8)
    standalone_styles = ["insight", "thread_start", "question"]

    # note記事への導線ポストを先に生成し、記事本体にも紐づける
    for article in results["note_articles"]:
        topic = article.get("topic", unused[0] if unused else "進化心理学")
        print(f"[ContentWriter] note導線ポスト生成中: {article.get('title', '')}")
        try:
            post = create_x_post(client, topic, style="note_funnel", note_article=article)
            results["x_posts"].append(post)
            # 下書きファイルに一緒に書き出せるよう記事に紐づける
            article["x_funnel_post"] = post.get("text", "")
        except Exception as e:
            print(f"[ContentWriter] note導線ポスト生成エラー: {e}")

    # 残りをスタンドアロンインサイトで埋める
    remaining = x_count - len(results["x_posts"])
    for i in range(max(0, remaining)):
        topic = unused[i % len(unused)]
        style = standalone_styles[i % len(standalone_styles)]
        print(f"[ContentWriter] Xポスト生成中: {topic} ({style})")
        try:
            post = create_x_post(client, topic, style)
            results["x_posts"].append(post)
        except Exception as e:
            print(f"[ContentWriter] Xポスト生成エラー: {e}")

    return results
