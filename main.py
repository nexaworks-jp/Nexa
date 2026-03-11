"""
自律型AIカンパニー - メインオーケストレーター
CEO Agentが複数の収益チャネルを横断して判断・実行する
"""
import json
import sys
import os
import argparse
from datetime import datetime, date
import anthropic

# Windows環境でのUTF-8出力設定
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))

from workers import trend_analyzer, content_writer, opportunity_scanner, proposal_writer, saas_ideator, self_improver
from publishers import note_publisher, x_publisher, crowdworks_publisher, gmail_outreach, line_notifier
import risk_manager


# ==================== 設定・メモリ管理 ====================

def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    template_path = os.path.join(os.path.dirname(__file__), "config.template.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    else:
        print(f"[Main] config.json が見つかりません。")
        print(f"  cp {template_path} {config_path}")
        sys.exit(1)


def load_memory(filename: str) -> dict:
    path = os.path.join(os.path.dirname(__file__), "memory", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_memory(filename: str, data: dict):
    path = os.path.join(os.path.dirname(__file__), "memory", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==================== CEO Agent ====================

def ceo_decide(client: anthropic.Anthropic, state: dict) -> dict:
    """
    CEO Agentが全チャネルのデータを見て今回の戦略を決定する
    """
    summary = json.dumps({
        "earnings": state["earnings"].get("by_channel", {}),
        "total": state["earnings"].get("total_earnings_jpy", 0),
        "iteration": state["strategy"].get("iteration", 0),
        "last_focus": state["strategy"].get("current_focus", ""),
        "applied_jobs": len(state["proposals"].get("applied", [])),
        "saas_ideas": len(state["saas"].get("saas_ideas", [])),
        "top_trends": state["trends"].get("topics", [])[:5]
    }, ensure_ascii=False)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""あなたは自律型AIカンパニーのCEOです。
以下の現状を見て、今回の実行で何を優先するか判断してください。

【現状】
{summary}

【選択肢】
- "content": note記事+Xポスト投稿（毎回の基本）
- "crowdworks": CrowdWorks案件スキャン + 提案文生成
- "saas": 新SaaSアイデア生成 + LP作成 + 営業メール準備
- "all": 全部やる（時間がかかるが最大効果）

判断基準：
- 初期（iteration 0-10）: contentとcrowdworksを交互に
- 中期（iteration 11-30）: saasも追加
- 収益が発生したらその手段を強化

JSON形式で：
{{
  "tasks": ["content", "crowdworks"],
  "reasoning": "理由（40文字以内）",
  "intensity": "light|normal|heavy"
}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])

    iteration = state["strategy"].get("iteration", 0)
    default_tasks = ["content"] if iteration % 2 == 0 else ["content", "crowdworks"]
    return {
        "tasks": default_tasks,
        "reasoning": "デフォルト判断",
        "intensity": "normal"
    }


# ==================== タスク実行 ====================

def run_content_task(config, trends, published, dry_run):
    """note + Xコンテンツ投稿"""
    print("\n[Task: Content] コンテンツ生成・投稿")
    generated = content_writer.generate_content_batch(config, trends, published)

    note_results = note_publisher.publish(
        config, generated.get("note_articles", []), dry_run
    )
    x_results = x_publisher.publish(
        config, generated.get("x_posts", []), dry_run
    )

    # トピック使用履歴を更新
    for a in generated.get("note_articles", []):
        t = a.get("topic", "")
        if t and t not in published.get("topics_used", []):
            published.setdefault("topics_used", []).append(t)

    return {
        "note": note_results,
        "x": x_results,
        "generated": generated
    }


def run_crowdworks_task(config, proposals_memory, dry_run):
    """CrowdWorks案件スキャン + 提案文生成"""
    print("\n[Task: CrowdWorks] 案件スキャン・提案文生成")
    already_applied = proposals_memory.get("applied", [])

    scan_result = opportunity_scanner.scan(config, already_applied)
    suitable_jobs = scan_result.get("suitable", [])

    if not suitable_jobs:
        print("[Task: CrowdWorks] 適合案件なし")
        return {"proposals": [], "scan": scan_result}

    proposals = proposal_writer.generate_proposals(config, suitable_jobs)
    pub_results = crowdworks_publisher.publish(config, proposals, dry_run)

    # 提案履歴を記録
    for p in proposals:
        proposals_memory.setdefault("applied", []).append({
            "job_id": p.get("job_id"),
            "job_title": p.get("job_title"),
            "platform": p.get("platform"),
            "applied_at": datetime.now().isoformat()
        })

    return {"proposals": proposals, "publish_results": pub_results, "scan": scan_result}


def run_saas_task(config, trends, saas_memory, dry_run):
    """SaaSアイデア生成 + LP + 営業メール"""
    print("\n[Task: SaaS] アイデア生成・LP作成・営業準備")

    result = saas_ideator.run(config, trends, saas_memory)

    # メモリに保存
    saas_memory.setdefault("saas_ideas", []).append(result.get("idea", {}))

    # 営業メール（ドラフト保存 or 送信）
    # ターゲットメールは実際の運用時にリストを用意する
    # 今は空リストで保存のみ
    email_results = gmail_outreach.send_outreach(
        config, result, target_emails=[], dry_run=dry_run
    )

    return {"saas_result": result, "email_results": email_results}


# ==================== レポート ====================

def print_report(earnings: dict, strategy: dict, proposals_memory: dict):
    width = 52
    print("\n" + "=" * width)
    print("  自律型AIカンパニー 収益レポート")
    print("=" * width)
    print(f"  総収益:       ¥{earnings.get('total_earnings_jpy', 0):>10,}")
    print(f"  実行回数:     {strategy.get('iteration', 0):>10}回")
    print()
    print("  チャネル別収益:")
    for ch, amount in earnings.get("by_channel", {}).items():
        print(f"    {ch:<15} ¥{amount:>8,}")
    print()
    print(f"  応募済み案件:  {len(proposals_memory.get('applied', []))}件")
    print()
    print(f"  現在の戦略:   {strategy.get('current_focus', '-')}")
    recent_logs = earnings.get("log", [])[-5:]
    if recent_logs:
        print()
        print("  直近の活動:")
        for log in recent_logs:
            print(f"    [{log.get('date', '')}] {log.get('channel', '')}: {log.get('title', log.get('type', ''))[:30]}")
    print("=" * width)


# ==================== メイン ====================

def run(dry_run: bool = False, report_only: bool = False, weekly: bool = False):
    print(f"\n{'='*52}")
    print(f"  自律型AIカンパニー 起動")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if dry_run:
        print("  [DRY RUNモード]")
    print(f"{'='*52}")

    config = load_config()
    earnings = load_memory("earnings.json") or {
        "total_earnings_jpy": 0, "monthly": {},
        "by_channel": {"note": 0, "affiliate": 0, "crowdworks": 0, "saas": 0},
        "log": []
    }
    published = load_memory("published.json") or {"note_articles": [], "x_posts": [], "topics_used": []}
    strategy = load_memory("strategy.json") or {"current_focus": "content", "reasoning": "初期", "iteration": 0}
    proposals_memory = load_memory("proposals.json") or {"applied": []}
    saas_memory = load_memory("saas.json") or {"saas_ideas": []}

    if report_only:
        print_report(earnings, strategy, proposals_memory)
        return

    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])

    # リスク状態ロード
    risk_state = risk_manager.load_state()
    risk_state = risk_manager.reset_daily_if_needed(risk_state)
    risk_state = risk_manager.increment_run(risk_state)

    # LINE: 起動通知
    if not dry_run:
        line_notifier.notify_startup(config)

    # Step 1: トレンド分析
    print("\n[Step 1] トレンド分析...")
    trends = trend_analyzer.analyze(config)
    print(f"  → {', '.join(trends['topics'][:4])}")

    # Step 2: CEO判断
    print("\n[Step 2] CEO判断...")
    state = {
        "earnings": earnings, "strategy": strategy,
        "trends": trends, "proposals": proposals_memory, "saas": saas_memory
    }
    decision = ceo_decide(client, state)
    tasks = decision.get("tasks", ["content"])
    print(f"  → タスク: {tasks}")
    print(f"  → 理由: {decision.get('reasoning', '')}")

    # Step 3: タスク実行
    all_results = {}

    if "content" in tasks or "all" in tasks:
        ok, reason = risk_manager.can_run("note", risk_state)
        if ok:
            try:
                all_results["content"] = run_content_task(config, trends, published, dry_run)
                risk_state = risk_manager.record_success(risk_state, "note")
            except Exception as e:
                risk_state = risk_manager.record_error(risk_state, "note", str(e))
                print(f"[Main] contentタスクエラー: {e}")
        else:
            print(f"[RiskManager] content スキップ: {reason}")

    if "crowdworks" in tasks or "all" in tasks:
        ok, reason = risk_manager.can_run("crowdworks", risk_state)
        if ok:
            try:
                all_results["crowdworks"] = run_crowdworks_task(config, proposals_memory, dry_run)
                cw_result = all_results["crowdworks"]
                proposals_count = len(cw_result.get("proposals", []))
                for _ in range(proposals_count):
                    risk_state = risk_manager.record_proposal(risk_state)
                risk_state = risk_manager.record_success(risk_state, "crowdworks")
                # LINE: 案件発見・提案文通知
                if not dry_run and cw_result.get("proposals"):
                    suitable = cw_result.get("scan", {}).get("suitable", [])
                    line_notifier.notify_jobs_found(config, suitable)
                    line_notifier.notify_proposals_ready(config, cw_result["proposals"])
            except Exception as e:
                risk_state = risk_manager.record_error(risk_state, "crowdworks", str(e))
                print(f"[Main] crowdworksタスクエラー: {e}")
                if not dry_run:
                    line_notifier.notify_risk_alert(config, "crowdworks", str(e)[:80])
        else:
            print(f"[RiskManager] crowdworks スキップ: {reason}")

    if "saas" in tasks or "all" in tasks:
        ok, reason = risk_manager.can_run("saas", risk_state)
        if ok:
            try:
                all_results["saas"] = run_saas_task(config, trends, saas_memory, dry_run)
                risk_state = risk_manager.record_success(risk_state, "saas")
                # LINE: SaaSアイデア通知
                if not dry_run:
                    idea = all_results["saas"].get("saas_result", {}).get("idea", {})
                    if idea:
                        line_notifier.notify_saas_idea(config, idea)
            except Exception as e:
                risk_state = risk_manager.record_error(risk_state, "saas", str(e))
                print(f"[Main] saasタスクエラー: {e}")
        else:
            print(f"[RiskManager] saas スキップ: {reason}")

    # Step 4: メモリ更新・保存
    strategy["current_focus"] = ", ".join(tasks)
    strategy["reasoning"] = decision.get("reasoning", "")
    strategy["last_updated"] = datetime.now().isoformat()
    strategy["iteration"] = strategy.get("iteration", 0) + 1

    # Step 5: 自己改善分析（戦略自動更新）
    print("\n[Step 5] 自己改善分析...")
    memory_snapshot = {
        "earnings": earnings, "risk_state": risk_state,
        "strategy": strategy, "proposals": proposals_memory
    }
    improve_result = self_improver.run(config, all_results, memory_snapshot, weekly=weekly)
    if improve_result.get("updated_strategy"):
        strategy.update(improve_result["updated_strategy"])

    save_memory("published.json", published)
    save_memory("strategy.json", strategy)
    save_memory("earnings.json", earnings)
    save_memory("proposals.json", proposals_memory)
    save_memory("saas.json", saas_memory)
    risk_manager.save_state(risk_state)

    # LINE: 22時の実行時のみ日次レポートを送信
    hour = datetime.now().hour
    if not dry_run and hour >= 21:
        proposals_today = sum(
            1 for r in all_results.get("crowdworks", {}).get("proposals", [])
        )
        line_notifier.notify_daily_report(config, earnings, risk_state, proposals_today)

    # サマリー
    print(f"\n{'='*52}")
    print(f"  完了 | 実行回数: {strategy['iteration']}回")
    if "content" in all_results:
        cr = all_results["content"]
        note_ok = sum(1 for r in cr.get("note", []) if r.get("success"))
        x_ok = sum(1 for r in cr.get("x", []) if r.get("success"))
        print(f"  コンテンツ: note {note_ok}本 / X {x_ok}件")
    if "crowdworks" in all_results:
        cw = all_results["crowdworks"]
        print(f"  CrowdWorks: 提案文 {len(cw.get('proposals', []))}件")
    if "saas" in all_results:
        s = all_results["saas"]
        idea_name = s.get("saas_result", {}).get("idea", {}).get("name", "")
        print(f"  SaaS: {idea_name} のLPを生成")
    print(f"  次の重点: {strategy['current_focus']}")
    print(f"{'='*52}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自律型AIカンパニー")
    parser.add_argument("--dry-run", action="store_true", help="実際には投稿・送信せずにテスト実行")
    parser.add_argument("--report", action="store_true", help="収益レポートを表示")
    parser.add_argument("--weekly", action="store_true", help="週次実行（新モジュール生成含む）")
    args = parser.parse_args()
    run(dry_run=args.dry_run, report_only=args.report, weekly=args.weekly)
