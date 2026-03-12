"""
ソフィアの記憶管理システム
人間らしい3層構造で「覚えている・忘れる」を再現。

短期記憶: 7日TTL・上限50件（誰が何を言ったか）
長期記憶: 3回以上の繰り返しで昇格・decayで徐々に忘却
忘却:     週次でdecay適用・閾値以下を削除

Claude API不使用・コスト0。
"""
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHORT_TERM_PATH = os.path.join(BASE_DIR, "memory", "short_term.json")
LONG_TERM_PATH  = os.path.join(BASE_DIR, "memory", "long_term.json")

SHORT_TERM_TTL_DAYS  = 7
SHORT_TERM_MAX       = 50
LONG_TERM_MAX        = 20
PROMOTION_THRESHOLD  = 3    # 3回以上で長期記憶に昇格
DECAY_RATE           = 0.12 # 週ごとの減衰（1.0 → 0.2 = 約7週で忘却）
FORGET_THRESHOLD     = 0.2

# ルールベースのトピック検出（API不使用）
TOPIC_KEYWORDS = {
    "毎日投稿してるの":    ["毎日", "投稿頻度", "頻繁"],
    "AI学習・成長":        ["学習", "勉強", "覚え", "成長"],
    "Claude/AI使い方":     ["claude", "クロード", "chatgpt", "使い方", "使える"],
    "自律進化の仕組み":    ["自律", "進化", "仕組み", "どうやって"],
    "初心者向けAI":        ["初心者", "難しい", "わからない", "始め方"],
    "ソフィアへの共感":    ["かわいい", "応援", "好き", "面白い", "すごい"],
}


# ── ロード・セーブ ──────────────────────────────────

def _load(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _save(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_short_term() -> list:
    return _load(SHORT_TERM_PATH, [])


def load_long_term() -> list:
    return _load(LONG_TERM_PATH, [])


# ── 短期記憶 ────────────────────────────────────────

def store_mention(tweet_id: str, username: str, text: str):
    """メンションを短期記憶に保存（重複スキップ）"""
    entries = load_short_term()
    if any(e.get("id") == tweet_id for e in entries):
        return

    now = datetime.now()
    entries.append({
        "id": tweet_id,
        "username": username,
        "text": text[:200],
        "stored_at": now.isoformat(),
        "expires_at": (now + timedelta(days=SHORT_TERM_TTL_DAYS)).isoformat(),
    })

    if len(entries) > SHORT_TERM_MAX:
        entries = entries[-SHORT_TERM_MAX:]

    _save(SHORT_TERM_PATH, entries)


def get_user_history(username: str) -> list:
    """特定ユーザーの短期記憶を返す（返信コンテキスト用）"""
    entries = load_short_term()
    now = datetime.now()
    return [
        e for e in entries
        if e.get("username") == username
        and datetime.fromisoformat(e["expires_at"]) > now
    ]


def cleanup_expired() -> int:
    """期限切れの短期記憶を削除"""
    entries = load_short_term()
    now = datetime.now()
    before = len(entries)
    entries = [e for e in entries if datetime.fromisoformat(e["expires_at"]) > now]
    _save(SHORT_TERM_PATH, entries)
    removed = before - len(entries)
    if removed:
        print(f"[MemoryManager] 短期記憶: {removed}件削除（期限切れ）")
    return removed


# ── 長期記憶への昇格 ────────────────────────────────

def promote_to_long_term():
    """短期記憶を分析し、繰り返し現れたトピックを長期記憶に昇格"""
    entries = load_short_term()
    long_term = load_long_term()
    now = datetime.now()

    topic_hits = defaultdict(list)
    for entry in entries:
        text = entry.get("text", "").lower()
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                topic_hits[topic].append(entry)

    existing = {lt["topic"]: lt for lt in long_term}
    promoted = 0

    for topic, hits in topic_hits.items():
        if topic in existing:
            # 既存の長期記憶を強化（スコアをリフレッシュ）
            existing[topic]["count"] = existing[topic].get("count", 0) + len(hits)
            existing[topic]["last_seen"] = now.strftime("%Y-%m-%d")
            existing[topic]["decay_score"] = min(1.0, existing[topic].get("decay_score", 0.5) + 0.2)
        elif len(hits) >= PROMOTION_THRESHOLD:
            long_term.append({
                "topic": topic,
                "summary": f"{len(hits)}件のメンションから昇格",
                "count": len(hits),
                "first_seen": hits[0].get("stored_at", now.isoformat())[:10],
                "last_seen": now.strftime("%Y-%m-%d"),
                "decay_score": 1.0,
            })
            promoted += 1

    # 上限管理（decay_scoreが低いものを優先削除）
    long_term = sorted(long_term, key=lambda x: x.get("decay_score", 0), reverse=True)
    long_term = long_term[:LONG_TERM_MAX]
    _save(LONG_TERM_PATH, long_term)

    if promoted:
        print(f"[MemoryManager] 長期記憶に昇格: {promoted}件")


# ── 忘却（週次decay）──────────────────────────────────

def apply_decay():
    """週次: 長期記憶のdecayを進め、閾値以下を削除"""
    long_term = load_long_term()
    before = len(long_term)

    for lt in long_term:
        lt["decay_score"] = round(lt.get("decay_score", 1.0) - DECAY_RATE, 3)

    long_term = [lt for lt in long_term if lt.get("decay_score", 0) >= FORGET_THRESHOLD]
    forgotten = before - len(long_term)
    _save(LONG_TERM_PATH, long_term)

    if forgotten:
        print(f"[MemoryManager] 長期記憶: {forgotten}件を忘却")
    print(f"[MemoryManager] 長期記憶残: {len(long_term)}件")


# ── 週次メンテナンス ────────────────────────────────

def run_weekly_maintenance():
    """weekly.yml から呼ぶ: 期限切れ削除 → 昇格判定 → 忘却"""
    print("[MemoryManager] 週次メモリメンテナンス開始...")
    cleanup_expired()
    promote_to_long_term()
    apply_decay()
    print("[MemoryManager] 完了")


# ── 返信コンテキスト生成 ────────────────────────────

def build_reply_context(username: str) -> str:
    """
    Cloudflare Worker の返信生成プロンプト用に
    このユーザーの過去発言をテキスト化して返す。
    """
    history = get_user_history(username)
    if not history:
        return ""

    lines = []
    for e in history[-3:]:  # 直近3件まで
        stored = e.get("stored_at", "")[:10]
        lines.append(f"  - ({stored}) {e['text'][:80]}")

    return "【このユーザーの過去の発言（短期記憶）】\n" + "\n".join(lines)
