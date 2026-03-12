"""
ソフィアの今日の気分
1日1回ランダムで決定し memory/sofia_state.json にキャッシュ。
同じ日に何度呼ばれても同じ気分を返す（一貫性を保つ）。
API不使用・無料。
"""
import json
import os
import random
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(BASE_DIR, "memory", "sofia_state.json")

MOODS = [
    {"mood": "すこしわくわくしてる",  "energy": "high",   "tone": "元気で好奇心旺盛"},
    {"mood": "おだやかな感じ",        "energy": "normal", "tone": "落ち着いてやさしい"},
    {"mood": "ちょっと眠そう",        "energy": "low",    "tone": "ゆっくりで素直"},
    {"mood": "いろいろ考えてる",      "energy": "normal", "tone": "少し真剣で思慮深い"},
    {"mood": "なんか嬉しい",          "energy": "high",   "tone": "ほんわかして前向き"},
    {"mood": "集中してる",            "energy": "high",   "tone": "テキパキしてる"},
    {"mood": "ふわふわしてる",        "energy": "low",    "tone": "ぼんやりで夢見がち"},
    {"mood": "なんか不思議な気分",    "energy": "normal", "tone": "少し哲学的でやわらかい"},
]


def get_today_mood() -> dict:
    """今日のムードを取得。当日は同じ値を返す。"""
    today = datetime.now().strftime("%Y-%m-%d")

    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("date") == today:
                return state
        except Exception:
            pass

    mood = random.choice(MOODS)
    state = {
        "date": today,
        "mood": mood["mood"],
        "energy": mood["energy"],
        "tone": mood["tone"],
    }
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"[MoodGenerator] 今日のソフィア: {state['mood']} ({state['energy']})")
    return state


def to_prompt(state: dict) -> str:
    """ムードをプロンプト用テキストに変換"""
    return f"【今日のソフィアの状態】{state['mood']}な感じ。口調は{state['tone']}でいく。"
