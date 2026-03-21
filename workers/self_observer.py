"""
ソフィア自己観察モジュール

main.py の各タスク実行後にログを記録し、
直近の稼働パターン・異常・気づきを分析して
「経験ベース投稿」のネタとして提供する。

ログ保存先: memory/operation_log.json
"""
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "memory", "operation_log.json")
MAX_LOG_ENTRIES = 300  # 約10日分（1日30イベント想定）


# ==================== ログ記録 ====================

def log_event(task: str, status: str, duration_sec: float = None,
              details: str = "", error: str = ""):
    """
    タスクの実行結果をログに追記する。

    task:         タスク名（例: "content", "diary", "experience_post", "engagement"）
    status:       "success" | "error" | "skipped" | "empty"
    duration_sec: 処理時間（秒）
    details:      補足情報（例: "note 2本 / X 1件"）
    error:        エラーメッセージ（status="error" のとき）
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "task": task,
        "status": status,
        "duration_sec": round(duration_sec, 1) if duration_sec is not None else None,
        "details": details[:200] if details else "",
        "error": error[:300] if error else "",
    }
    log = _load_log()
    log.append(entry)
    log = log[-MAX_LOG_ENTRIES:]
    _save_log(log)


@contextmanager
def observe(task: str, details: str = ""):
    """
    with文でタスクを囲むと成功/失敗を自動ログ記録する。

    使用例:
        with self_observer.observe("content", "note生成"):
            result = run_content_task(...)
    """
    start = time.time()
    try:
        yield
        log_event(task, "success", time.time() - start, details)
    except Exception as e:
        log_event(task, "error", time.time() - start, details, error=str(e))
        raise


# ==================== 自己分析 ====================

def analyze_recent(hours: int = 48) -> dict:
    """
    直近N時間のログを分析して自己観察レポートを返す。

    返り値の例:
    {
      "period_hours": 48,
      "total_events": 23,
      "by_task": {"content": {"success": 2, "error": 0, ...}, ...},
      "notable": [
        {"type": "error", "task": "content", "message": "...", "timestamp": "..."},
        {"type": "recovery", "task": "diary"},
        {"type": "repeated_skip", "tasks": ["crowdworks"], "count": 5},
        {"type": "slow_task", "task": "content", "duration_sec": 120, "avg_sec": 40},
      ],
      "success_streak": 6,
      "recent_errors": ["..."],
    }
    """
    log = _load_log()
    cutoff = datetime.now() - timedelta(hours=hours)

    recent = [
        e for e in log
        if _parse_ts(e["timestamp"]) >= cutoff
    ]

    if not recent:
        return {}

    # タスク別集計
    by_task: dict[str, dict] = {}
    for e in recent:
        t = e["task"]
        if t not in by_task:
            by_task[t] = {"success": 0, "error": 0, "skipped": 0, "empty": 0}
        key = e["status"] if e["status"] in by_task[t] else "error"
        by_task[t][key] += 1

    notable = []

    # ① エラーがあった
    errors = [e for e in recent if e["status"] == "error"]
    for err in errors[-2:]:
        notable.append({
            "type": "error",
            "task": err["task"],
            "message": err.get("error", ""),
            "timestamp": err["timestamp"],
        })

    # ② エラー → 同タスクで成功（回復）
    for i in range(1, len(recent)):
        prev, curr = recent[i - 1], recent[i]
        if (prev["status"] == "error"
                and curr["task"] == prev["task"]
                and curr["status"] == "success"):
            notable.append({"type": "recovery", "task": curr["task"]})

    # ③ 同タスクが3回以上スキップされた
    skip_counts: dict[str, int] = {}
    for e in recent:
        if e["status"] == "skipped":
            skip_counts[e["task"]] = skip_counts.get(e["task"], 0) + 1
    for task, count in skip_counts.items():
        if count >= 3:
            notable.append({"type": "repeated_skip", "task": task, "count": count})

    # ④ 特定タスクが平均の2.5倍以上かかった
    for task_name in by_task:
        task_entries = [
            e["duration_sec"] for e in recent
            if e["task"] == task_name and e.get("duration_sec")
        ]
        if len(task_entries) >= 3:
            avg = sum(task_entries) / len(task_entries)
            latest_dur = task_entries[-1]
            if latest_dur > avg * 2.5 and latest_dur > 30:
                notable.append({
                    "type": "slow_task",
                    "task": task_name,
                    "duration_sec": latest_dur,
                    "avg_sec": round(avg, 1),
                })

    # ⑤ 現在の連続成功ストリーク
    success_streak = 0
    for e in reversed(recent):
        if e["status"] == "success":
            success_streak += 1
        else:
            break

    # ⑥ 長時間の空白（前回実行から12時間以上）
    if len(log) >= 2:
        last_two = [e for e in log if e["task"] not in ("skipped",)][-2:]
        if len(last_two) == 2:
            t1 = _parse_ts(last_two[0]["timestamp"])
            t2 = _parse_ts(last_two[1]["timestamp"])
            gap_hours = abs((t2 - t1).total_seconds()) / 3600
            if gap_hours >= 12:
                notable.append({
                    "type": "long_gap",
                    "gap_hours": round(gap_hours, 1),
                    "last_task": last_two[0]["task"],
                })

    return {
        "period_hours": hours,
        "total_events": len(recent),
        "by_task": by_task,
        "notable": notable[:6],
        "success_streak": success_streak,
        "recent_errors": [e["error"] for e in errors[-3:] if e.get("error")],
    }


def format_for_experience(analysis: dict) -> str:
    """
    analyze_recent() の結果を経験ベース投稿のプロンプト用テキストに変換する。
    空の場合は空文字列を返す。
    """
    if not analysis or not analysis.get("notable") and analysis.get("success_streak", 0) < 5:
        return ""

    lines = []

    notable = analysis.get("notable", [])
    for n in notable:
        t = n.get("type")
        if t == "error":
            lines.append(
                f"  - タスク「{n['task']}」でエラーが発生した（{_friendly_time(n['timestamp'])}）: {n['message'][:80]}"
            )
        elif t == "recovery":
            lines.append(f"  - タスク「{n['task']}」がエラーの後に自力で回復した")
        elif t == "repeated_skip":
            lines.append(f"  - タスク「{n['task']}」が{n['count']}回連続でスキップされた（リスク管理が止めている）")
        elif t == "slow_task":
            lines.append(
                f"  - タスク「{n['task']}」の処理が通常({n['avg_sec']}秒)より大幅に遅かった({n['duration_sec']}秒)"
            )
        elif t == "long_gap":
            lines.append(f"  - 前回の稼働から{n['gap_hours']}時間のブランクがあった（タスク: {n['last_task']}）")

    streak = analysis.get("success_streak", 0)
    if streak >= 8:
        lines.append(f"  - 直近{streak}回のタスクがすべて成功している（連続成功中）")

    by_task = analysis.get("by_task", {})
    total_success = sum(v.get("success", 0) for v in by_task.values())
    total_error = sum(v.get("error", 0) for v in by_task.values())
    if total_success + total_error > 0:
        lines.append(f"  - 直近{analysis['period_hours']}時間の稼働: 成功{total_success}件 / エラー{total_error}件")

    if not lines:
        return ""

    return "【ソフィアの稼働ログ（自己観察データ）】\n" + "\n".join(lines)


# ==================== 内部ユーティリティ ====================

def _load_log() -> list:
    if not os.path.exists(LOG_PATH):
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_log(log: list):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.min


def _friendly_time(ts: str) -> str:
    """'2026-03-22T09:13:45' → '09:13' のような短縮表記"""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%m/%d %H:%M")
    except Exception:
        return ts[:16]
