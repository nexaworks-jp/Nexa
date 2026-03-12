"""
トレンド分析ワーカー
Claude APIを使って今日の旬なAIトピックを生成する
"""
import json
import anthropic
from datetime import datetime


def analyze(config: dict) -> dict:
    """
    AIトピックのリストを生成して返す
    戻り値: { "topics": [...], "source": "claude", "analyzed_at": "..." }
    """
    api_key = config.get("anthropic_api_key", "")
    client = anthropic.Anthropic(api_key=api_key)

    today = datetime.now().strftime("%Y年%m月%d日")

    print("[TrendAnalyzer] AIトピック生成中...")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""今日は{today}です。
AIに関する記事トピックを15個生成してください。

以下のカテゴリから満遍なく選んでください：
- Claude（機能・使い方・モデル・CLAUDE.md・Skillsなど）
- ChatGPT（最新機能・GPT-4o・プロンプト技法など）
- 画像生成AI（Midjourney・Stable Diffusion・DALL-Eなど）
- AI動画・音声（Sora・ElevenLabsなど）
- AIツール全般（Gemini・Copilot・Perplexityなど）
- AI初心者向けハウツー（登録方法・使い方入門・比較など）

条件：
- パソコン初心者でも興味を持ちそうなテーマ
- 最新・実用的・面白いもの
- 「〇〇とは？」「〇〇の使い方」「〇〇と〇〇の違い」「〇〇を使って〇〇する方法」形式

JSON形式で出力：
{{"topics": ["トピック1", "トピック2", ..., "トピック15"]}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        data = json.loads(text[start:end])
        topics = data.get("topics", [])
    else:
        topics = [
            "Claude 3.5 Sonnetの使い方【初心者向け】",
            "ChatGPTとClaudeの違いを徹底比較",
            "CLAUDE.mdとは？設定方法を解説",
            "Gemini 2.0の新機能まとめ",
            "AIで画像生成する方法【無料ツール5選】",
        ]

    print(f"[TrendAnalyzer] {len(topics)}件のトピックを生成")

    return {
        "topics": topics,
        "source": "claude",
        "analyzed_at": datetime.now().isoformat()
    }
