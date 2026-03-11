"""
LINE Webhook サーバー
LINEからのメッセージを受信してシステムを操作する

起動方法:
  python line_webhook.py

外部公開 (ngrok使用):
  ngrok http 8000
  → LINE Developers Console の Webhook URL に設定

デプロイ版 (Render.com / Railway):
  このファイルをそのままデプロイ可能
"""
import json
import os
import sys
import hashlib
import hmac
import base64
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# Windows UTF-8対応
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))

from publishers import line_notifier
import risk_manager

PORT = 8000
BASE_DIR = os.path.dirname(__file__)


def load_config() -> dict:
    with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8-sig") as f:
        return json.load(f)


def verify_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    """LINE署名検証"""
    hash_val = hmac.new(
        channel_secret.encode("utf-8"), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(hash_val).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def handle_command(command: str, config: dict) -> str:
    """
    LINEからのコマンドを処理して返答を返す
    """
    cmd = command.strip().lower()
    line = config.get("line", {})

    # ==================== コマンド一覧 ====================

    if cmd in ("レポート", "report", "r"):
        import json as j
        earnings_path = os.path.join(BASE_DIR, "memory", "earnings.json")
        risk_path = os.path.join(BASE_DIR, "memory", "risk_state.json")
        with open(earnings_path, encoding="utf-8") as f:
            earnings = j.load(f)
        with open(risk_path, encoding="utf-8") as f:
            risk_state = j.load(f)
        total = earnings.get("total_earnings_jpy", 0)
        by_ch = earnings.get("by_channel", {})
        api_cost = risk_state.get("api_cost_month_usd", 0) * 150
        paused = risk_state.get("paused_modules", {})
        status = "✅ 正常稼働" if not paused else f"⚠️ {list(paused.keys())} 停止中"
        return (
            f"📊 現在のレポート\n\n"
            f"💰 累計収益: ¥{total:,}\n"
            f"  note: ¥{by_ch.get('note',0):,}\n"
            f"  CW: ¥{by_ch.get('crowdworks',0):,}\n\n"
            f"⚙️ 今月のAPI費用: ¥{api_cost:.0f}\n"
            f"🔄 総実行回数: {risk_state.get('total_runs',0)}回\n"
            f"状態: {status}"
        )

    elif cmd in ("リスク", "risk"):
        import json as j
        risk_path = os.path.join(BASE_DIR, "memory", "risk_state.json")
        with open(risk_path, encoding="utf-8") as f:
            risk_state = j.load(f)
        paused = risk_state.get("paused_modules", {})
        errors = {k: v for k, v in risk_state.get("consecutive_errors", {}).items() if v > 0}
        cost_today = risk_state.get("api_cost_today_usd", 0) * 150
        cost_month = risk_state.get("api_cost_month_usd", 0) * 150
        lines = [
            "🛡️ リスク状態\n",
            f"本日のAPI費用: ¥{cost_today:.0f} / ¥{0.30*150:.0f}上限",
            f"今月のAPI費用: ¥{cost_month:.0f} / ¥{5.00*150:.0f}上限",
        ]
        if paused:
            lines.append(f"\n⏸️ 停止中: {', '.join(paused.keys())}")
        if errors:
            lines.append(f"⚠️ エラー中: {errors}")
        if not paused and not errors:
            lines.append("\n✅ 全モジュール正常")
        return "\n".join(lines)

    elif cmd in ("停止", "stop", "pause"):
        risk_state = risk_manager.load_state()
        for mod in ["note", "x", "crowdworks", "saas"]:
            risk_state = risk_manager.record_error(risk_state, mod, "手動停止")
            risk_state = risk_manager.record_error(risk_state, mod, "手動停止")
            risk_state = risk_manager.record_error(risk_state, mod, "手動停止")
        risk_manager.save_state(risk_state)
        return "⏸️ 全モジュールを停止しました。\n再開: 「再開」と送ってください。"

    elif cmd in ("再開", "resume", "start"):
        risk_state = risk_manager.load_state()
        risk_state["paused_modules"] = {}
        risk_state["consecutive_errors"] = {}
        risk_manager.save_state(risk_state)
        return "▶️ 全モジュールを再開しました。\n次の定時実行から動き始めます。"

    elif cmd in ("提案", "proposals"):
        proposals_dir = os.path.join(BASE_DIR, "proposals")
        if not os.path.exists(proposals_dir):
            return "📋 まだ提案文はありません。"
        files = sorted(os.listdir(proposals_dir), reverse=True)
        md_files = [f for f in files if f.endswith(".md")]
        if not md_files:
            return "📋 まだ提案文はありません。"
        latest = md_files[0]
        return f"📋 最新の提案文:\n{latest}\n\npropsals/ フォルダを確認してください。"

    elif cmd in ("ヘルプ", "help", "h", "?"):
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
    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # 署名検証
        config = load_config()
        channel_secret = config.get("line", {}).get("channel_secret", "")
        signature = self.headers.get("X-Line-Signature", "")

        if channel_secret and not verify_signature(body, signature, channel_secret):
            self.send_response(403)
            self.end_headers()
            return

        self.send_response(200)
        self.end_headers()

        # イベント処理
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

                # 返信
                line_cfg = config.get("line", {})
                reply_url = "https://api.line.me/v2/bot/message/reply"
                import requests
                requests.post(
                    reply_url,
                    headers={
                        "Authorization": f"Bearer {line_cfg.get('channel_access_token','')}",
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
    print(f"[Webhook] ngrokで公開: ngrok http {PORT}")
    print(f"[Webhook] Webhook URL: https://xxxx.ngrok.io/webhook")
    server = HTTPServer(("0.0.0.0", PORT), LineWebhookHandler)
    server.serve_forever()


if __name__ == "__main__":
    run_server()
