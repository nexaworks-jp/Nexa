"""
LINE Webhook サーバー (Render.com対応版)

config.jsonがある場合はそこから設定を読む。
ない場合（Render.com等）は環境変数から読む。
メモリファイルはGitHub APIから取得する。
"""
import json
import os
import sys
import hashlib
import hmac
import base64
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# Windows UTF-8対応
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PORT = int(os.environ.get("PORT", 8000))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "nexaworks/ai-company")


def load_config() -> dict:
    """config.jsonまたは環境変数から設定を読む"""
    config_path = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    # 環境変数から構築（Render.com用）
    return {
        "line": {
            "channel_access_token": os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", ""),
            "channel_secret": os.environ.get("LINE_CHANNEL_SECRET", ""),
            "user_id": os.environ.get("LINE_USER_ID", ""),
        },
        "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
    }


def load_memory_file(filename: str) -> dict:
    """メモリファイルをローカルまたはGitHub APIから読む"""
    local_path = os.path.join(BASE_DIR, "memory", filename)
    if os.path.exists(local_path):
        try:
            with open(local_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # GitHub APIから取得（Render.com用）
    if GITHUB_TOKEN and GITHUB_REPO:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/memory/{filename}"
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"token {GITHUB_TOKEN}"},
                timeout=10
            )
            if resp.status_code == 200:
                content = base64.b64decode(resp.json()["content"]).decode("utf-8")
                return json.loads(content)
        except Exception as e:
            print(f"[Webhook] GitHub API読み込みエラー: {e}")
    return {}


def save_memory_to_github(filename: str, data: dict) -> bool:
    """GitHub APIでメモリファイルを更新する（停止/再開コマンド用）"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        # ローカルに直接書き込み
        local_path = os.path.join(BASE_DIR, "memory", filename)
        try:
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/memory/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    # 現在のSHAを取得
    get_resp = requests.get(url, headers=headers, timeout=10)
    sha = get_resp.json().get("sha", "") if get_resp.status_code == 200 else ""

    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("ascii")
    payload = {
        "message": f"🤖 webhook: update {filename}",
        "content": content,
    }
    if sha:
        payload["sha"] = sha
    try:
        resp = requests.put(url, headers=headers, json=payload, timeout=15)
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"[Webhook] GitHub API書き込みエラー: {e}")
        return False


def verify_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    """LINE署名検証"""
    hash_val = hmac.new(
        channel_secret.encode("utf-8"), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(hash_val).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def handle_command(command: str, config: dict) -> str:
    """LINEからのコマンドを処理して返答を返す"""
    cmd = command.strip()
    cmd_lower = cmd.lower()

    if cmd_lower in ("レポート", "report", "r"):
        earnings = load_memory_file("earnings.json")
        risk_state = load_memory_file("risk_state.json")
        total = earnings.get("total_earnings_jpy", 0)
        by_ch = earnings.get("by_channel", {})
        api_cost = risk_state.get("api_cost_month_usd", 0) * 150
        paused = risk_state.get("paused_modules", {})
        status = "✅ 正常稼働" if not paused else f"⚠️ {list(paused.keys())} 停止中"
        return (
            f"📊 現在のレポート\n\n"
            f"💰 累計収益: ¥{total:,}\n"
            f"  note: ¥{by_ch.get('note', 0):,}\n"
            f"  CW: ¥{by_ch.get('crowdworks', 0):,}\n\n"
            f"⚙️ 今月のAPI費用: ¥{api_cost:.0f}\n"
            f"🔄 総実行回数: {risk_state.get('total_runs', 0)}回\n"
            f"状態: {status}"
        )

    elif cmd_lower in ("リスク", "risk"):
        risk_state = load_memory_file("risk_state.json")
        paused = risk_state.get("paused_modules", {})
        errors = {k: v for k, v in risk_state.get("consecutive_errors", {}).items() if v > 0}
        cost_today = risk_state.get("api_cost_today_usd", 0) * 150
        cost_month = risk_state.get("api_cost_month_usd", 0) * 150
        lines = [
            "🛡️ リスク状態\n",
            f"本日のAPI費用: ¥{cost_today:.0f} / ¥45上限",
            f"今月のAPI費用: ¥{cost_month:.0f} / ¥750上限",
        ]
        if paused:
            lines.append(f"\n⏸️ 停止中: {', '.join(paused.keys())}")
        if errors:
            lines.append(f"⚠️ エラー中: {errors}")
        if not paused and not errors:
            lines.append("\n✅ 全モジュール正常")
        return "\n".join(lines)

    elif cmd_lower in ("停止", "stop", "pause"):
        risk_state = load_memory_file("risk_state.json")
        now = datetime.now().isoformat()
        if "paused_modules" not in risk_state:
            risk_state["paused_modules"] = {}
        for mod in ["note", "x", "crowdworks", "saas"]:
            risk_state["paused_modules"][mod] = now
        if save_memory_to_github("risk_state.json", risk_state):
            return "⏸️ 全モジュールを停止しました。\n次の定時実行から反映されます。\n再開: 「再開」と送ってください。"
        return "⚠️ 停止に失敗しました。\nGitHubトークンを確認してください。"

    elif cmd_lower in ("再開", "resume", "start"):
        risk_state = load_memory_file("risk_state.json")
        risk_state["paused_modules"] = {}
        risk_state["consecutive_errors"] = {}
        if save_memory_to_github("risk_state.json", risk_state):
            return "▶️ 全モジュールを再開しました。\n次の定時実行から動き始めます。"
        return "⚠️ 再開に失敗しました。\nGitHubトークンを確認してください。"

    elif cmd_lower in ("提案", "proposals"):
        proposals = load_memory_file("proposals.json")
        items = proposals.get("applied", []) if isinstance(proposals, dict) else []
        if not items:
            return "📋 まだ提案文はありません。\n次の定時実行で生成されます。"
        latest = items[-1]
        title = latest.get("job_title", "不明")
        text = latest.get("proposal_text", "（本文なし）")
        url = latest.get("job_url", "")
        price = latest.get("estimated_price", "")
        days = latest.get("estimated_days", "")
        msg = f"📋 最新の提案文（全{len(items)}件）\n\n"
        msg += f"【案件】{title}\n"
        if price:
            msg += f"【金額】{price}　【納期】{days}\n"
        if url:
            msg += f"【URL】{url}\n"
        msg += f"\n{text[:1000]}"
        return msg

    elif cmd_lower in ("ヘルプ", "help", "h", "?"):
        return (
            "🤖 AIカンパニー コマンド一覧\n\n"
            "📊 レポート - 収益・状態を表示\n"
            "🛡️ リスク - リスク状態を表示\n"
            "📋 提案 - 最新の提案文を確認\n"
            "⏸️ 停止 - 全モジュールを停止\n"
            "▶️ 再開 - 全モジュールを再開\n"
            "❓ ヘルプ - このメッセージ"
        )

    else:
        return (
            f"「{command[:20]}」は認識できないコマンドです。\n"
            "「ヘルプ」で使えるコマンドを確認できます。"
        )


class LineWebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """UptimeRobotのヘルスチェック用"""
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("OK - Nexa AI Company Webhook".encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        config = load_config()
        channel_secret = config.get("line", {}).get("channel_secret", "")
        signature = self.headers.get("X-Line-Signature", "")

        if channel_secret and not verify_signature(body, signature, channel_secret):
            self.send_response(403)
            self.end_headers()
            return

        self.send_response(200)
        self.end_headers()

        try:
            data = json.loads(body.decode("utf-8"))
            for event in data.get("events", []):
                if event.get("type") != "message":
                    continue
                msg = event.get("message", {})
                if msg.get("type") != "text":
                    continue
                text_input = msg.get("text", "")
                reply_token = event.get("replyToken", "")

                print(f"[Webhook] 受信: {text_input}")
                response_text = handle_command(text_input, config)

                line_cfg = config.get("line", {})
                requests.post(
                    "https://api.line.me/v2/bot/message/reply",
                    headers={
                        "Authorization": f"Bearer {line_cfg.get('channel_access_token', '')}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "replyToken": reply_token,
                        "messages": [{"type": "text", "text": response_text}]
                    },
                    timeout=10
                )
        except Exception as e:
            print(f"[Webhook] エラー: {e}")

    def log_message(self, format, *args):
        pass  # アクセスログを抑制


def run_server():
    print(f"[Webhook] LINEウェブフックサーバー起動 port={PORT}")
    server = HTTPServer(("0.0.0.0", PORT), LineWebhookHandler)
    server.serve_forever()


if __name__ == "__main__":
    run_server()
