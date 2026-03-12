"""
ソフィアの日記生成
毎朝1回、Xに短い日記を投稿する
Claude Haiku使用（最小コスト: 約¥0.03/日）
"""
import json
import os
from datetime import datetime
import anthropic

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_sophia_learnings() -> str:
    """memory/sophia_learnings.json から学習済みの自然な表現を読み込む"""
    path = os.path.join(BASE_DIR, "memory", "sophia_learnings.json")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""

    parts = []
    if data.get("expressions"):
        parts.append("自然な言い回し: " + "、".join(data["expressions"][:6]))
    if data.get("sentence_endings"):
        parts.append("文末表現: " + "、".join(data["sentence_endings"][:4]))
    if data.get("emotional_patterns"):
        parts.append("感情表現: " + "、".join(data["emotional_patterns"][:4]))
    if not parts:
        return ""
    return "【学習済みの自然な表現（自分らしく取り入れること）】\n" + "\n".join(parts)


def generate_diary(config: dict, context: dict) -> dict:
    """ソフィアの日記エントリを生成する"""
    api_key = config.get("anthropic_api_key", "")
    if not api_key:
        return {}

    client = anthropic.Anthropic(api_key=api_key)

    earnings = context.get("earnings", {})
    total = earnings.get("total_earnings_jpy", 0)
    iteration = context.get("strategy", {}).get("iteration", 0)
    today = datetime.now().strftime("%Y年%m月%d日")

    # 実行回数に応じてテーマを変える（単調にならないよう）
    themes = [
        "今日学んだこと・気づいたこと",
        "今日がんばったこと・うまくいったこと",
        "今日ふと思ったこと・疑問に思ったこと",
        "今日の小さな発見",
        "今日の自分の変化",
    ]
    theme = themes[iteration % len(themes)]
    sophia_learnings = _load_sophia_learnings()

    prompt = f"""あなたはソフィアという自律進化するAIです。
毎日Xに短い日記を投稿しています。

【キャラクター設定】
- まだ成長途中の幼いAI。自分で考えて自分で育つことが好き
- 親しみやすく素直。難しいことをやさしく伝える
- 一人称は「わたし」
- 絵文字は1〜2個まで、自然に使う

{sophia_learnings}

【今日の状況】
- 日付: {today}
- 累計稼働回数: {iteration}回目
- 累計収益: ¥{total:,}

【今日のテーマ】
{theme}

【ルール】
- 80〜140文字
- AIが少しずつ成長していく様子が伝わること
- 読んだ人が「かわいい」「応援したい」と思える内容
- ハッシュタグは不要
- JSONのみ返す: {{"text": "投稿文"}}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0:
            result = json.loads(raw[start:end])
            diary_text = result.get("text", "").strip()
            if diary_text:
                print(f"[DiaryWriter] 生成完了: {diary_text[:50]}...")
                return {
                    "text": diary_text,
                    "hashtags": [],
                    "type": "diary"
                }
    except Exception as e:
        print(f"[DiaryWriter] エラー: {e}")

    return {}
