"""フォールバック: 全APIが失敗した場合にClaudeの知識でトピックを生成"""
import json
from datetime import datetime
import anthropic


def get_fallback_topics(client: anthropic.Anthropic, num: int = 4) -> list[str]:
    today = datetime.now().strftime("%Y年%m月%d日")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""今日は{today}です。
AI関連記事タイトルを{num}つ提案してください。

以下の2カテゴリから混ぜて選んでください：
【初心者向け（2本）】Claude・ChatGPT・Gemini・AI活用術の入門・使い方
【Claude Code実践系（2本）】Claude Code Skills/SKILL.md/CLAUDE.md/MCPサーバー/スラッシュコマンドなどの実用Tips

実践系の例：
- 「CLAUDE.mdとは？Claude Codeを自分専用にカスタマイズする設定ファイル解説」
- 「Claude Code Skillsの作り方【SKILL.mdテンプレートあり】」
- 「Claude Codeのスラッシュコマンドをカスタムする方法」
- 「MCPサーバーとSkillsの違いと正しい使い分け方」

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
    return [
        "ChatGPTとClaudeの違いを徹底比較",
        "AI画像生成の始め方",
        "CLAUDE.mdとは？Claude Codeを自分専用にカスタマイズする設定ファイル解説",
        "Claude Code Skillsの作り方【SKILL.mdテンプレートあり】"
    ]
