"""フォールバック: 全APIが失敗した場合にClaudeの知識でトピックを生成"""
import json
from datetime import datetime
import anthropic


def get_fallback_topics(client: anthropic.Anthropic, num: int = 4) -> list[str]:
    today = datetime.now().strftime("%Y年%m月%d日")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""今日は{today}です。
今話題のAI関連トピックを{num}つ、日本語AI初心者向け記事タイトルとして提案してください。
Claude・ChatGPT・Gemini・画像生成AI・AI活用術などから選んでください。

JSON: {{"topics": ["タイトル1", "タイトル2", "タイトル3", "タイトル4"]}}"""
        }]
    )
    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end]).get("topics", [])
        except Exception:
            pass
    return ["ChatGPTとClaudeの違いを徹底比較", "AI画像生成の始め方", "Gemini 2.0の使い方", "AIで副業を始める方法"]
