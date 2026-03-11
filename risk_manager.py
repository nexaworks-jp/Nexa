"""
リスク管理モジュール
サーキットブレーカー・コスト監視・自動停止を担う
"""
import json
import os
import sys
import argparse
from datetime import datetime, date, timedelta

RISK_FILE = os.path.join(os.path.dirname(__file__), "memory", "risk_state.json")


def _ensure_utf8_stdout():
    """スタンドアロン実行時のみUTF-8設定（main.pyからインポート時は不要）"""
    if sys.platform == "win32" and not isinstance(sys.stdout, type(sys.stdout)):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ==================== ハードリミット ====================
LIMITS = {
    "max_proposals_per_day":      3,      # CrowdWorks 1日最大提案数
    "max_api_cost_per_day_usd":   0.30,   # Claude API 1日上限
    "max_api_cost_per_month_usd": 5.00,   # Claude API 月上限
    "max_consecutive_errors":     3,      # 連続エラーで停止
    "module_pause_hours": {
        "crowdworks": 48,   # CrowdWorksエラー時の停止時間
        "note":       24,
        "x":          24,
        "saas":       48,
    }
}

# ==================== 状態管理 ====================

def load_state() -> dict:
    if os.path.exists(RISK_FILE):
        with open(RISK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "api_cost_today_usd": 0.0,
        "api_cost_month_usd": 0.0,
        "proposals_today": 0,
        "date": str(date.today()),
        "month": datetime.now().strftime("%Y-%m"),
        "consecutive_errors": {},
        "paused_modules": {},
        "total_runs": 0,
        "last_run": None,
        "error_log": []
    }


def save_state(state: dict):
    os.makedirs(os.path.dirname(RISK_FILE), exist_ok=True)
    with open(RISK_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def reset_daily_if_needed(state: dict) -> dict:
    """日付が変わったら日次カウンターをリセット"""
    today = str(date.today())
    this_month = datetime.now().strftime("%Y-%m")

    if state.get("date") != today:
        state["api_cost_today_usd"] = 0.0
        state["proposals_today"] = 0
        state["date"] = today
        # エラーカウントも日次リセット
        state["consecutive_errors"] = {}

    if state.get("month") != this_month:
        state["api_cost_month_usd"] = 0.0
        state["month"] = this_month

    return state

# ==================== チェック関数 ====================

def is_module_paused(state: dict, module: str) -> tuple[bool, str]:
    """モジュールが停止中かチェック"""
    paused = state.get("paused_modules", {})
    if module in paused:
        resume_at = datetime.fromisoformat(paused[module])
        if datetime.now() < resume_at:
            remaining = resume_at - datetime.now()
            hours = int(remaining.total_seconds() / 3600)
            return True, f"{module}は停止中（あと{hours}時間）"
        else:
            # 停止期間終了
            del state["paused_modules"][module]
    return False, ""


def can_run(module: str, state: dict) -> tuple[bool, str]:
    """モジュールが実行可能かチェック"""
    state = reset_daily_if_needed(state)

    # モジュール停止チェック
    paused, reason = is_module_paused(state, module)
    if paused:
        return False, reason

    # APIコストチェック
    if state["api_cost_today_usd"] >= LIMITS["max_api_cost_per_day_usd"]:
        return False, f"本日のAPI費用上限到達 (${state['api_cost_today_usd']:.3f})"

    if state["api_cost_month_usd"] >= LIMITS["max_api_cost_per_month_usd"]:
        return False, f"月間API費用上限到達 (${state['api_cost_month_usd']:.3f})"

    # 提案数チェック
    if module == "crowdworks":
        if state["proposals_today"] >= LIMITS["max_proposals_per_day"]:
            return False, f"本日の提案数上限到達 ({state['proposals_today']}件)"

    return True, "OK"


def record_api_usage(state: dict, input_tokens: int, output_tokens: int) -> dict:
    """API使用量を記録してコストを計算"""
    # Claude Haiku 4.5 価格
    input_cost  = (input_tokens  / 1_000_000) * 0.80
    output_cost = (output_tokens / 1_000_000) * 4.00
    total_cost = input_cost + output_cost

    state["api_cost_today_usd"]  = round(state.get("api_cost_today_usd", 0) + total_cost, 6)
    state["api_cost_month_usd"]  = round(state.get("api_cost_month_usd", 0) + total_cost, 6)
    return state


def record_error(state: dict, module: str, error: str) -> dict:
    """エラーを記録し、連続エラーが多ければモジュールを停止"""
    errors = state.setdefault("consecutive_errors", {})
    errors[module] = errors.get(module, 0) + 1

    # エラーログ
    state.setdefault("error_log", []).append({
        "module": module,
        "error": str(error)[:200],
        "at": datetime.now().isoformat()
    })
    # ログは最新50件のみ保持
    state["error_log"] = state["error_log"][-50:]

    # 連続エラー上限 → モジュール停止
    if errors[module] >= LIMITS["max_consecutive_errors"]:
        pause_hours = LIMITS["module_pause_hours"].get(module, 24)
        resume_at = datetime.now() + timedelta(hours=pause_hours)
        state.setdefault("paused_modules", {})[module] = resume_at.isoformat()
        errors[module] = 0
        print(f"[RiskManager] ⚠️  {module} を {pause_hours}時間停止 (連続エラー{LIMITS['max_consecutive_errors']}回)")

    return state


def record_success(state: dict, module: str) -> dict:
    """成功時はエラーカウントをリセット"""
    state.setdefault("consecutive_errors", {})[module] = 0
    return state


def record_proposal(state: dict) -> dict:
    """提案送信を記録"""
    state["proposals_today"] = state.get("proposals_today", 0) + 1
    return state


def increment_run(state: dict) -> dict:
    state["total_runs"] = state.get("total_runs", 0) + 1
    state["last_run"] = datetime.now().isoformat()
    return state

# ==================== ステータス表示 ====================

def print_status(state: dict):
    state = reset_daily_if_needed(state)
    jpy_today = state["api_cost_today_usd"] * 150
    jpy_month = state["api_cost_month_usd"] * 150

    print("\n" + "="*50)
    print("  リスク管理ステータス")
    print("="*50)
    print(f"  本日のAPI費用:  ${state['api_cost_today_usd']:.4f} (≈¥{jpy_today:.0f})")
    print(f"  今月のAPI費用:  ${state['api_cost_month_usd']:.4f} (≈¥{jpy_month:.0f})")
    print(f"  本日の提案数:   {state.get('proposals_today', 0)}/{LIMITS['max_proposals_per_day']}件")
    print(f"  総実行回数:     {state.get('total_runs', 0)}回")
    print(f"  最終実行:       {state.get('last_run', 'なし')}")

    paused = state.get("paused_modules", {})
    if paused:
        print("\n  停止中モジュール:")
        for mod, resume in paused.items():
            print(f"    {mod}: {resume} まで停止")
    else:
        print("\n  停止中モジュール: なし")

    errors = state.get("consecutive_errors", {})
    active_errors = {k: v for k, v in errors.items() if v > 0}
    if active_errors:
        print(f"\n  連続エラー: {active_errors}")

    recent_errors = state.get("error_log", [])[-3:]
    if recent_errors:
        print("\n  最近のエラー:")
        for e in recent_errors:
            print(f"    [{e['at'][:16]}] {e['module']}: {e['error'][:50]}")
    print("="*50)


# ==================== メイン ====================

if __name__ == "__main__":
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="リスク管理")
    parser.add_argument("--status", action="store_true", help="現在のリスク状態を表示")
    parser.add_argument("--reset", metavar="MODULE", help="モジュールの停止を解除")
    parser.add_argument("--reset-all", action="store_true", help="全停止を解除")
    args = parser.parse_args()

    state = load_state()

    if args.status:
        print_status(state)
    elif args.reset:
        mod = args.reset
        if mod in state.get("paused_modules", {}):
            del state["paused_modules"][mod]
            save_state(state)
            print(f"[RiskManager] {mod} の停止を解除しました")
        else:
            print(f"[RiskManager] {mod} は停止していません")
    elif args.reset_all:
        state["paused_modules"] = {}
        state["consecutive_errors"] = {}
        save_state(state)
        print("[RiskManager] 全モジュールの停止を解除しました")
    else:
        print_status(state)
