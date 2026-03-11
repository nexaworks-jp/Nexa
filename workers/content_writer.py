"""
コンテンツ生成ワーカー
Claude APIを使ってnote記事とXポストを生成する
"""
import anthropic
import json
import random
from datetime import datetime


def create_note_article(client: anthropic.Anthropic, topic: str, published_topics: list) -> dict:
    """
    note.com用の有料記事を生成する
    戻り値: { "title": str, "content": str, "price": int, "hashtags": list }
    """
    avoid = ", ".join(published_topics[-20:]) if published_topics else "なし"

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[{
            "role": "user",
            "content": f"""あなたはnote.comで人気のクリエイターです。
以下のトピックについて、有料で売れる質の高いnote記事を書いてください。

トピック: {topic}
避けるべき最近のトピック: {avoid}

以下のJSON形式で出力してください：
{{
  "title": "記事タイトル（30文字以内、読者が思わずクリックしたくなる）",
  "content": "記事本文（マークダウン形式、1500〜2500文字、具体的な数字や手順を含む）",
  "price": 300,
  "hashtags": ["ハッシュタグ1", "ハッシュタグ2", "ハッシュタグ3"],
  "summary": "記事の無料公開部分の要約（100文字）"
}}

記事は必ず：
- 具体的な数字（例：「月3万円節約できる方法5選」）を使う
- 読者がすぐ実践できるアクションステップを含む
- 信頼できる情報として書く
- 有料部分に最も価値ある情報を入れる"""
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
            "title": f"{topic}で稼ぐ完全ガイド",
            "content": text,
            "price": 300,
            "hashtags": [topic, "副業", "お金"],
            "summary": f"{topic}について詳しく解説します。"
        }

    data["topic"] = topic
    data["created_at"] = datetime.now().isoformat()
    return data


def create_x_post(client: anthropic.Anthropic, topic: str, style: str = "tip") -> dict:
    """
    X(Twitter)用の投稿を生成する
    style: "tip" | "thread_start" | "question" | "insight"
    戻り値: { "text": str, "hashtags": list }
    """
    style_prompts = {
        "tip": "実用的なヒント・コツ（「知らないと損」「今すぐできる」系）",
        "thread_start": "スレッドの1ツイート目（続きが気になる書き出し）",
        "question": "フォロワーに問いかける質問（エンゲージメント狙い）",
        "insight": "驚きのデータや気づき（「実は〇〇だった」系）"
    }

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""Xで伸びるツイートを書いてください。

トピック: {topic}
スタイル: {style_prompts.get(style, style_prompts['tip'])}

条件：
- 140文字以内（日本語）
- 絵文字を2〜3個使う
- 具体的で実用的
- ハッシュタグは本文に含めない

JSON形式で出力：
{{
  "text": "ツイート本文",
  "hashtags": ["タグ1", "タグ2"]
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
            "text": text[:140],
            "hashtags": [topic]
        }

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
    x_count = config.get("settings", {}).get("x_post_per_day", 8)
    styles = ["tip", "thread_start", "question", "insight"]
    for i in range(x_count):
        topic = unused[i % len(unused)]
        style = styles[i % len(styles)]
        print(f"[ContentWriter] Xポスト生成中: {topic} ({style})")
        try:
            post = create_x_post(client, topic, style)
            results["x_posts"].append(post)
        except Exception as e:
            print(f"[ContentWriter] Xポスト生成エラー: {e}")

    return results
