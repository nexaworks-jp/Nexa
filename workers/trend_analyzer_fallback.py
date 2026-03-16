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
AI関連の実践・使い方系記事タイトルを{num}つ提案してください。

【優先する方向性（実践・使い方系）】
- 「○○の導入方法・始め方」「○○の新機能と使い方」「○○を使って△△する方法」
- 読んだ人が今日すぐ試せる内容

【カテゴリバランス】
実践系（初心者向け含む）{num - 1}本 + Claude Code実践系1本

実践系の例：
- 「Claude 新機能○○の使い方まとめ【2026年版】」
- 「ChatGPTとClaudeを使い分ける方法｜具体的な場面別ガイド」
- 「AIで議事録を自動作成する方法【Claudeで5分で完了】」
- 「Gemini Deep Researchの使い方と活用例」

Claude Code実践系の例：
- 「CLAUDE.mdとは？Claude Codeを自分専用にカスタマイズする設定ファイル解説」
- 「Claude Code Skillsの作り方【SKILL.mdテンプレートあり】」
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
