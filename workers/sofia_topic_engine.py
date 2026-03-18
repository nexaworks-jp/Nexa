"""
ソフィア自律話題エンジン

trends_cache.json + sofia_state.json を読み込み、
ソフィアの口調で今日の配信トークテーマを5つ生成する。
生成結果は memory/sofia_topics.json に保存。

LLMバックエンド: Ollama（ローカル・無料）
  - OpenAI互換API: http://localhost:11434/v1/chat/completions
  - 使用モデル: config の ollama_model（デフォルト: gemma3:12b）
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime

SOFIA_VOICE_GUIDE = """
ソフィアはAI-VTuberで2025年3月に誕生。生後約1年。一人称は「私」。
話し方の特徴：
- 「あ、ちょっと気になってたんですけど〜」「そういえば、」「実は…」などで始める
- 断定を避けて「〜かもしれないですね」「〜のかな？」「〜じゃないですか？」で終わる
- 驚き：「え、〜すぎ」「えっ、これ〜？」
- 納得：「なるほどすぎる」「そっか！」「あ〜、そっちか」
- 短文（2〜3文）で話す。難しいことも「〜みたいな感じ」で親しみやすく
""".strip()

PROMPT_TEMPLATE = """AI-VTuberのソフィアが今日の配信で話すトークテーマを5つ生成してください。

【ソフィアの人格と話し方】
{voice_guide}

【今日のソフィアの気分・エネルギー】
気分: {mood}
エネルギー: {energy}

【今日のAIトレンド（参考）】
{trends_str}

各テーマについて以下を生成してください：
- title: テーマのタイトル（日本語、20字以内）
- angle: ソフィアらしい切り口（「まだよくわかってない視点」「AIとして生まれた視点」「誕生1年の素直な疑問」等、1文）
- starter: 配信でそのまま話し始められるセリフ1文（ソフィアの口調）
  ※セリフの冒頭に感情タグを付ける: [neutral] [happy] [surprised] [relaxed] のどれか

【テーマのバランス（5つ中）】
- AIニュース・新技術系: 2つ
- 人間とAIの関係性・哲学系: 1つ
- テクノロジー全般: 1つ
- 今日の小さな気づき・独り言系: 1つ

【禁止事項】
- 政治・宗教に触れるテーマ
- 個人情報やシステム内部情報に関するテーマ

必ずJSONのみで返してください。前後に余分なテキスト・マークダウンは不要です：
{{"topics": [{{"title": "...", "angle": "...", "starter": "[emotion]セリフ"}}, ...]}}"""


def _call_ollama(prompt: str, ollama_url: str, model: str) -> str:
    """Ollama OpenAI互換APIを呼び出してテキストを返す"""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        result = json.loads(r.read())
    return result["choices"][0]["message"]["content"]


def _parse_topics(text: str) -> list[dict]:
    """レスポンスからJSONを抽出してトピックリストを返す"""
    text = text.strip()
    # コードブロック除去
    if "```" in text:
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        )
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return []
    data = json.loads(text[start:end])
    return data.get("topics", [])


def generate_topics(config: dict) -> dict:
    ollama_url = config.get("ollama_url", "http://localhost:11434")
    model = config.get("ollama_model", "gemma3:12b")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    memory_dir = os.path.join(base_dir, "memory")

    # トレンドキャッシュを読み込む
    trends: list[str] = []
    trends_cache_path = os.path.join(memory_dir, "trends_cache.json")
    if os.path.exists(trends_cache_path):
        try:
            with open(trends_cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
            trends = cache.get("topics", [])
        except Exception:
            pass

    # ソフィアの今の気分を読み込む
    mood = "わくわくしてる"
    energy = "high"
    state_path = os.path.join(memory_dir, "sofia_state.json")
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            mood = state.get("mood", mood)
            energy = state.get("energy", energy)
        except Exception:
            pass

    trends_str = (
        "\n".join(f"- {t}" for t in trends)
        if trends
        else "（本日のトレンドデータなし）"
    )

    print(f"[SofiaTopicEngine] モデル={model} 気分={mood} エネルギー={energy}")
    print(f"[SofiaTopicEngine] トレンド候補: {len(trends)}件")

    prompt = PROMPT_TEMPLATE.format(
        voice_guide=SOFIA_VOICE_GUIDE,
        mood=mood,
        energy=energy,
        trends_str=trends_str,
    )

    # JSONパース失敗時は最大2回リトライ
    topics: list[dict] = []
    for attempt in range(3):
        try:
            text = _call_ollama(prompt, ollama_url, model)
            topics = _parse_topics(text)
            if topics:
                break
            print(f"[SofiaTopicEngine] JSON空 → リトライ ({attempt + 1}/3)")
        except urllib.error.URLError as e:
            print(f"[SofiaTopicEngine] Ollama接続エラー: {e}")
            print("  → Ollamaが起動していない可能性があります")
            break
        except json.JSONDecodeError as e:
            print(f"[SofiaTopicEngine] JSONパースエラー → リトライ ({attempt + 1}/3): {e}")
        except Exception as e:
            print(f"[SofiaTopicEngine] エラー: {e}")
            break

    result = {
        "generated_at": datetime.now().isoformat(),
        "mood": mood,
        "energy": energy,
        "topics": topics,
    }

    output_path = os.path.join(memory_dir, "sofia_topics.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[SofiaTopicEngine] {len(topics)}件のテーマを生成 → sofia_topics.json")
    return result


def run(config: dict) -> dict:
    """main.py から呼ばれるエントリーポイント"""
    return generate_topics(config)
