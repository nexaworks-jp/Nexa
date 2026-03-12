"""
LINE Messaging API 通知モジュール
システム → LINEへの各種通知を送信する

セットアップ:
1. https://developers.line.biz/console/ でプロバイダー作成
2. Messaging API チャンネル作成
3. チャンネルアクセストークン取得（長期）
4. ボットをLINE友達追加
5. https://api.line.me/v2/bot/profile でUser ID確認
"""
import requests
import json
from datetime import datetime


LINE_API_URL = "https://api.line.me/v2/bot/message/push"


def send(token: str, user_id: str, messages: list[dict]) -> bool:
    """LINEにメッセージを送信する基本関数"""
    if not token or token == "YOUR_LINE_CHANNEL_ACCESS_TOKEN":
        print("[LINE] トークン未設定。通知スキップ。")
        return False

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": messages[:5]  # 1回最大5件
    }
    try:
        resp = requests.post(LINE_API_URL, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        else:
            print(f"[LINE] 送信失敗: {resp.status_code} {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"[LINE] 送信エラー: {e}")
        return False


def text(token: str, user_id: str, message: str) -> bool:
    """テキストメッセージを送信"""
    return send(token, user_id, [{"type": "text", "text": message}])


# ==================== 通知テンプレート ====================

def notify_startup(config: dict):
    """システム起動通知"""
    line = config.get("line", {})
    now = datetime.now().strftime("%m/%d %H:%M")
    text(
        line.get("channel_access_token", ""),
        line.get("user_id", ""),
        f"🤖 AIカンパニー起動\n{now}\n\n本日のタスクを開始します。"
    )


def notify_jobs_found(config: dict, jobs: list[dict]):
    """新着案件発見通知"""
    if not jobs:
        return
    line = config.get("line", {})
    lines = [f"📋 新着案件 {len(jobs)}件を発見しました\n"]
    for i, job in enumerate(jobs[:3], 1):
        lines.append(f"{i}. {job.get('title', '不明')[:30]}")
        lines.append(f"   {job.get('url', '')}")
    lines.append("\n提案文を proposals/ に生成しました。\n確認してコピペ提出をお願いします！")
    text(
        line.get("channel_access_token", ""),
        line.get("user_id", ""),
        "\n".join(lines)
    )


def notify_proposals_ready(config: dict, proposals: list[dict]):
    """提案文生成完了通知"""
    if not proposals:
        return
    line = config.get("line", {})
    lines = [f"✍️ 提案文 {len(proposals)}件を生成しました\n"]
    for p in proposals[:3]:
        title = p.get("job_title", "")[:25]
        price = p.get("estimated_price", "要相談")
        lines.append(f"・{title}")
        lines.append(f"  提案額: {price}")
    lines.append(f"\n📁 proposals/ フォルダを確認してください")
    lines.append("⏱️ 所要時間: 約5分（コピペのみ）")
    text(
        line.get("channel_access_token", ""),
        line.get("user_id", ""),
        "\n".join(lines)
    )


def notify_risk_alert(config: dict, module: str, reason: str, severity: str = "warning"):
    """リスク警告通知"""
    line = config.get("line", {})
    icon = "🚨" if severity == "critical" else "⚠️"
    text(
        line.get("channel_access_token", ""),
        line.get("user_id", ""),
        f"{icon} リスクアラート\n\nモジュール: {module}\n理由: {reason}\n\n自動で対処しました。確認が必要な場合はご連絡します。"
    )


def notify_module_paused(config: dict, module: str, hours: int, error: str):
    """モジュール停止通知"""
    line = config.get("line", {})
    text(
        line.get("channel_access_token", ""),
        line.get("user_id", ""),
        f"⏸️ {module} を一時停止\n\n理由: {error[:80]}\n停止時間: {hours}時間\n\n自動復旧します。手動で解除: python risk_manager.py --reset {module}"
    )


def notify_daily_report(config: dict, earnings: dict, risk_state: dict, proposals_count: int):
    """日次レポート通知"""
    line = config.get("line", {})
    total = earnings.get("total_earnings_jpy", 0)
    by_ch = earnings.get("by_channel", {})
    api_cost_jpy = risk_state.get("api_cost_today_usd", 0) * 150
    runs = risk_state.get("total_runs", 0)

    msg = f"""📊 AIカンパニー 日次レポート
{datetime.now().strftime('%m月%d日')}

💰 累計収益: ¥{total:,}
  note: ¥{by_ch.get('note', 0):,}
  CrowdWorks: ¥{by_ch.get('crowdworks', 0):,}
  その他: ¥{by_ch.get('affiliate', 0) + by_ch.get('saas', 0):,}

📋 本日の提案文: {proposals_count}件生成
⚙️ 本日の実行: {runs}回
💸 本日のAPI費用: ¥{api_cost_jpy:.0f}

{"✅ 正常稼働中" if not risk_state.get('paused_modules') else "⚠️ 一部停止中"}"""

    text(
        line.get("channel_access_token", ""),
        line.get("user_id", ""),
        msg
    )


def notify_saas_idea(config: dict, idea: dict):
    """新SaaSアイデア通知"""
    line = config.get("line", {})
    text(
        line.get("channel_access_token", ""),
        line.get("user_id", ""),
        f"💡 新SaaSアイデアを生成しました\n\n【{idea.get('name', '')}】\n{idea.get('tagline', '')}\n\nターゲット: {idea.get('target', '')}\n月額: ¥{idea.get('price_monthly', 0):,}\n\nLPを saas_products/ に保存しました。"
    )


def notify_weekly_improvement(config: dict, improvements: dict, new_modules: list):
    """週次改善完了通知"""
    line = config.get("line", {})
    summary = improvements.get("weekly_summary", "")
    items = improvements.get("improvements", [])
    opportunities = improvements.get("new_opportunities", [])

    lines = [f"🔧 週次自動改善が完了しました\n{datetime.now().strftime('%m月%d日')}\n"]
    if summary:
        lines.append(f"📝 {summary}\n")
    if items:
        lines.append(f"✅ 改善案 {len(items)}件を適用")
    if opportunities:
        best = opportunities[0]
        lines.append(f"💡 新機会: {best.get('name', '')} (推定¥{best.get('estimated_monthly_jpy', 0):,}/月)")
    if new_modules:
        lines.append(f"🆕 新モジュール {len(new_modules)}個を自動追加")
    lines.append("\n次回の改善: 来週日曜 9:00")
    text(
        line.get("channel_access_token", ""),
        line.get("user_id", ""),
        "\n".join(lines)
    )


def notify_draft_ready(config: dict, drafts: list[dict]):
    """note下書き完成通知（画像挿入・投稿はオーナーが実施）"""
    if not drafts:
        return
    line = config.get("line", {})
    lines = [f"📝 note下書きが完成しました（{len(drafts)}本）\n"]
    for i, d in enumerate(drafts[:3], 1):
        title = d.get("title", "不明")[:30]
        price = d.get("price", 0)
        lines.append(f"{i}. {title}")
        lines.append(f"   価格: ¥{price}")
    lines.append(f"\n📁 drafts/ フォルダを確認してください")
    lines.append("🖼️ 画像を挿入して投稿をお願いします（5分程度）")
    text(
        line.get("channel_access_token", ""),
        line.get("user_id", ""),
        "\n".join(lines)
    )


def notify_equipment_needed(config: dict, opportunities: list):
    """新収益チャネル開始に必要な機材・購入物をLINEで通知する"""
    if not opportunities:
        return
    line = config.get("line", {})
    lines = ["🛒 新しい収益チャネルに必要なものがあります\n"]
    for opp in opportunities:
        name = opp.get("name", "")
        items = opp.get("required_equipment", [])
        reason = opp.get("equipment_reason", "")
        if not items:
            continue
        lines.append(f"【{name}】")
        for item in items:
            lines.append(f"  • {item}")
        if reason:
            lines.append(f"  理由: {reason}")
        lines.append("")
    lines.append("買えそうなら教えてください。準備ができたら自動でスタートします。")
    if len(lines) <= 3:
        return
    text(
        line.get("channel_access_token", ""),
        line.get("user_id", ""),
        "\n".join(lines)
    )


def notify_cost_warning(config: dict, cost_usd: float, limit_usd: float):
    """API費用警告"""
    line = config.get("line", {})
    cost_jpy = cost_usd * 150
    limit_jpy = limit_usd * 150
    percent = int(cost_usd / limit_usd * 100)
    text(
        line.get("channel_access_token", ""),
        line.get("user_id", ""),
        f"💸 API費用アラート\n\n本日の費用: ¥{cost_jpy:.0f} ({percent}%)\n上限: ¥{limit_jpy:.0f}\n\n上限に近づいています。本日の残りの実行を制限します。"
    )
