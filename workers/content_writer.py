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


def create_note_article(client: anthropic.Anthropic, topic: str, published_topics: list) -> dict:
    """
    note.com用の有料記事を生成する
    戻り値: { "title": str, "content": str, "price": int, "hashtags": list }
    """
    avoid = ", ".join(published_topics[-20:]) if published_topics else "なし"
    style_guide = load_style_reference()

    style_section = ""
    if style_guide:
        style_section = f"""
【参考スタイルガイド（エボサイ）】
{style_guide[:2000]}

"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[{
            "role": "user",
            "content": f"""あなたは「昨日パソコンを買った人でもわかるAI入門」をテーマにしたnoteクリエイターです。
以下のスタイルガイドを参考に、初心者に売れる質の高いnote記事を書いてください。
{style_section}
トピック: {topic}
避けるべき最近のトピック: {avoid}

以下のJSON形式で出力してください：
{{
  "title": "記事タイトル（30文字以内、「〜でもわかる」「〜分でできる」「Claudeで〜する方法」など初心者向けのわかりやすいタイトル）",
  "content": "記事本文（マークダウン形式、1500〜2500文字、IT初心者がClaudeを使いこなすための解説）",
  "price": 300,
  "hashtags": ["Claude", "AI初心者", "ハッシュタグ3"],
  "summary": "記事の無料公開部分の要約（100文字）"
}}

記事は必ず：
- 「こんなことで困っていませんか？」という共感から入る
- 専門用語を使わない（どうしても必要なら平易な言葉で補足する）
- 手順は番号付きリストで、スクショがあることを前提に書く
- 親切・丁寧・やさしいトーン（友人に教えるように）
- 有料部分に応用テクニック・時短ワザを入れる"""
        }]
    )

    text = response.content[0].text
    # JSONを抽出
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        data = json.loads(text[start:end])
    else:
        # フォールバック
        data = {
            "title": f"{topic}の使い方【初心者向け】",
            "content": text,
            "price": 300,
            "hashtags": [topic, "Claude", "AI初心者"],
            "summary": f"{topic}について初心者向けに解説します。"
        }

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
            article = create_note_article(client, topic, published_topics)
            results["note_articles"].append(article)
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
