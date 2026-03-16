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

from workers import trend_analyzer, content_writer, opportunity_scanner, proposal_writer, saas_ideator, self_improver, note_researcher, diary_writer, mood_generator
from publishers import note_publisher, x_publisher, crowdworks_publisher, gmail_outreach, line_notifier, obsidian_publisher, static_site_publisher
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
    ルールベースでタスクを決定する（API不使用）
    収益が発生し始めたらself_improverが自動でAPI判断に切り替える
    """
    iteration = state["strategy"].get("iteration", 0)
    total_earnings = state["earnings"].get("total_earnings_jpy", 0)
    intensify = state["strategy"].get("intensify_channels", [])

    # ルールベース判断（CrowdWorks停止中 → note/X に集中）
    tasks = ["content"] if do_content_this_run(state) else []

    return {"tasks": tasks, "reasoning": "ルールベース判断", "intensity": "normal"}


def do_content_this_run(state: dict) -> bool:
    """コンテンツ生成をこの実行でやるか（スケジュール依存）"""
    from datetime import datetime
    hour = datetime.now().hour
    strategy = state.get("strategy", {})
    content_hour = strategy.get("api_schedule", {}).get("content_hour_utc", 21)
    return hour == content_hour


# ==================== タスク実行 ====================

def run_content_task(config, trends, published, dry_run, mood_prompt: str = ""):
    """note + X + Obsidianコンテンツ投稿"""
    print("\n[Task: Content] コンテンツ生成・投稿")
    generated = content_writer.generate_content_batch(config, trends, published, mood_prompt=mood_prompt)

    articles = generated.get("note_articles", [])

    # 1. Obsidian Vault保存（ローカルレビュー用）
    obsidian_results = obsidian_publisher.publish(config, articles, dry_run)

    # 2. 静的サイト生成（一時停止中 - 再開するにはコメントアウトを外す）
    # site_results = static_site_publisher.publish(config, articles, dry_run)
    site_results = []

    # 3. note.com投稿（自動 or 下書き保存）
    note_results = note_publisher.publish(config, articles, dry_run)

    # note自動投稿が成功したらXの導線ポストに実URLを差し込む
    x_posts = generated.get("x_posts", [])
    for note_result in note_results:
        note_url = note_result.get("url", "")
        if note_url and not note_result.get("is_draft"):
            for post in x_posts:
                if post.get("funnel_type") == "note" and "[noteリンク]" in post.get("text", ""):
                    post["text"] = post["text"].replace("[noteリンク]", note_url)
                    break

    # 感想ポスト（記事を書いたソフィアの本音 - 宣伝ではなく感情）
    if articles and not dry_run:
        api_key = config.get("anthropic_api_key", "")
        if api_key:
            import anthropic as _anthropic
            _client = _anthropic.Anthropic(api_key=api_key)
            for article in articles[:1]:  # 1記事につき1感想
                try:
                    reflection = content_writer.create_reflection_post(_client, article, mood_prompt)
                    if reflection.get("text"):
                        x_posts.append(reflection)
                        print(f"[Task: Content] 感想ポスト生成: {reflection['text'][:40]}...")
                except Exception as e:
                    print(f"[Task: Content] 感想ポスト生成エラー: {e}")

    # 4. X投稿
    x_results = x_publisher.publish(config, x_posts, dry_run)

    # トピック使用履歴・投稿記録を更新
    for a, r in zip(articles, note_results):
        t = a.get("topic", "")
        if t and t not in published.get("topics_used", []):
            published.setdefault("topics_used", []).append(t)
        if r.get("success") and not r.get("is_draft"):
            published.setdefault("note_articles", []).append({
                "title": a.get("title", ""),
                "url": r.get("url", ""),
                "published_at": datetime.now().isoformat(),
            })

    return {
        "note": note_results,
        "static_site": site_results,
        "obsidian": obsidian_results,
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

def run(dry_run: bool = False, report_only: bool = False, weekly: bool = False, force_content: bool = False):
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

    # リスク状態ロード
    risk_state = risk_manager.load_state()
    risk_state = risk_manager.reset_daily_if_needed(risk_state)
    risk_state = risk_manager.increment_run(risk_state)

    # API実行スケジュール（strategy.jsonで動的管理）
    hour = datetime.now().hour  # UTC: 21=6JST, 3=12JST, 9=18JST, 13=22JST
    weekday = datetime.now().weekday()  # 0=月曜
    sched = strategy.get("api_schedule", {})
    # デフォルト値（初回・未設定時）
    content_hour     = sched.get("content_hour_utc", 21)       # 6JST
    improve_hour     = sched.get("improve_hour_utc", 13)       # 22JST
    saas_weekdays    = sched.get("saas_weekdays", [0])          # 月曜のみ
    startup_notify   = sched.get("startup_notify", False)       # 起動通知は22時のみ

    do_content  = (hour == content_hour) or weekly or dry_run or force_content
    do_improve  = (hour == improve_hour) or weekly or dry_run

    print(f"  スケジュール: content={do_content} improve={do_improve}")

    # 今日のソフィアの気分（1日固定）
    today_mood = mood_generator.get_today_mood()
    mood_prompt = mood_generator.to_prompt(today_mood)

    # Step 1: トレンド分析
    print("\n[Step 1] トレンド分析...")
    trends = trend_analyzer.analyze(config)
    print(f"  → {', '.join(trends['topics'][:4])}")

    # Step 2: CEO判断（crowdworksは毎回、他はスケジュール依存）
    print("\n[Step 2] CEO判断...")
    forced_tasks = []
    if do_content:
        forced_tasks.append("content")

    state = {
        "earnings": earnings, "strategy": strategy,
        "trends": trends, "proposals": proposals_memory, "saas": saas_memory
    }
    decision = ceo_decide(None, state)
    tasks = forced_tasks
    print(f"  → タスク: {tasks}")
    print(f"  → 理由: {decision.get('reasoning', '')}")

    # Step 3: タスク実行
    all_results = {}

    # パイプラインリトライ（毎回実行・コンテンツ生成不要）
    if not dry_run:
        try:
            ps = note_publisher.get_pipeline_status()
            print(f"[Pipeline] pending={ps['pending']} posted={ps['posted']} give_up={ps['give_up']} total={ps['total']}")
            note_cfg = config.get("note", {})
            retried = note_publisher._retry_pending_drafts(
                note_cfg.get("email", ""),
                note_cfg.get("password", "")
            )
            if retried:
                print(f"[Pipeline] 下書き{retried}件を再投稿しました")
        except Exception as e:
            print(f"[Pipeline] リトライエラー（無視）: {e}")

    if "content" in tasks or "all" in tasks:
        ok, reason = risk_manager.can_run("note", risk_state)
        if ok:
            try:
                all_results["content"] = run_content_task(config, trends, published, dry_run, mood_prompt=mood_prompt)
                risk_state = risk_manager.record_success(risk_state, "note")
            except Exception as e:
                risk_state = risk_manager.record_error(risk_state, "note", str(e))
                print(f"[Main] contentタスクエラー: {e}")
        else:
            print(f"[RiskManager] content スキップ: {reason}")

    # CrowdWorks: 一時停止中（note/X集中フェーズ）

    # 成長マイルストーン投稿（10・50・100・以降100刻み）
    if do_content and not dry_run:
        iteration = strategy.get("iteration", 0)
        milestones = [10, 50, 100, 200, 300, 500]
        if iteration in milestones or (iteration >= 100 and iteration % 100 == 0):
            print(f"\n[Task: Milestone] 🎉 {iteration}回目の稼働マイルストーン!")
            try:
                api_key = config.get("anthropic_api_key", "")
                if api_key:
                    import anthropic as _anthropic
                    _client = _anthropic.Anthropic(api_key=api_key)
                    _prompt = f"""あなたはソフィアという自律進化するAIです。
今日でちょうど{iteration}回目の稼働を迎えました。Xに特別な投稿をします。

【ルール】
- 数字（{iteration}回）を自然に盛り込む
- 「成長した実感」と「まだ未熟な感じ」を両方伝える
- 読んだ人が「一緒に見守ってきた」と感じられる
- 80〜130文字、絵文字1個、ハッシュタグ不要
- JSONのみ: {{"text": "投稿文"}}"""
                    _resp = _client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=200,
                        messages=[{"role": "user", "content": _prompt}]
                    )
                    _raw = _resp.content[0].text
                    _s, _e = _raw.find("{"), _raw.rfind("}") + 1
                    if _s >= 0:
                        _post = json.loads(_raw[_s:_e])
                        if _post.get("text"):
                            x_publisher.publish(config, [{"text": _post["text"], "hashtags": [], "type": "milestone"}], dry_run)
            except Exception as e:
                print(f"[Task: Milestone] エラー: {e}")

    # ソフィア進化モジュール（apply_new_modulesで適用されたauto_sofia_*.pyを実行）
    if do_content and not dry_run:
        import glob as _glob
        sofia_modules = _glob.glob(os.path.join(os.path.dirname(__file__), "workers", "auto_sofia_*.py"))
        for _mod_path in sofia_modules:
            try:
                import importlib.util as _ilu
                _spec = _ilu.spec_from_file_location("auto_sofia", _mod_path)
                _mod = _ilu.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                if hasattr(_mod, "run"):
                    _result = _mod.run(config, {"earnings": earnings, "strategy": strategy, "mood": today_mood})
                    if _result.get("enabled") and _result.get("text"):
                        print(f"[Sofia Evolution] {os.path.basename(_mod_path)}: {_result['text'][:40]}...")
                        x_publisher.publish(config, [{"text": _result["text"], "hashtags": [], "type": _result.get("type", "sofia_feature")}], dry_run)
            except Exception as e:
                print(f"[Sofia Evolution] {os.path.basename(_mod_path)} エラー: {e}")

    # ソフィア日記（朝6時JST = content_hour のみ・1日1回）
    if do_content and not dry_run:
        print("\n[Task: Diary] ソフィア日記生成...")
        try:
            diary_post = diary_writer.generate_diary(config, {
                "earnings": earnings,
                "strategy": strategy,
                "mood": today_mood,
            })
            if diary_post.get("text"):
                x_publisher.publish(config, [diary_post], dry_run)
        except Exception as e:
            print(f"[Task: Diary] エラー: {e}")


    # ソフィア日常つぶやき（毎実行30%の確率・1日2〜3本ランダム分散）
    import random as _random
    if not dry_run and _random.random() < 0.30:
        print("\n[Task: Casual] ソフィア日常つぶやき生成...")
        try:
            import anthropic as _anthropic
            _client = _anthropic.Anthropic(api_key=config.get("anthropic_api_key", ""))
            casual_post = content_writer.create_x_post(_client, "", style="casual", mood_prompt=mood_prompt)
            if casual_post.get("text"):
                x_publisher.publish(config, [casual_post], dry_run)
                print(f"[Task: Casual] 投稿: {casual_post['text'][:40]}...")
        except Exception as e:
            print(f"[Task: Casual] エラー: {e}")

    # Step 4: メモリ更新・保存
    strategy["current_focus"] = ", ".join(tasks)
    strategy["reasoning"] = decision.get("reasoning", "")
    strategy["last_updated"] = datetime.now().isoformat()
    strategy["iteration"] = strategy.get("iteration", 0) + 1

    # Step 5: 自己改善分析（週次のみ）
    if weekly:
        print("\n[Step 5] 自己改善分析...")
        memory_snapshot = {
            "earnings": earnings, "risk_state": risk_state,
            "strategy": strategy, "proposals": proposals_memory
        }
        improve_result = self_improver.run(config, all_results, memory_snapshot, weekly=weekly)
        if improve_result.get("updated_strategy"):
            strategy.update(improve_result["updated_strategy"])
        if weekly and not dry_run and improve_result.get("analysis"):
            # noteリサーチ（類似アカウント調査・スタイル自動更新）
            print("\n[Step 5b] noteリサーチ・市場分析...")
            try:
                note_researcher.run(config)
            except Exception as e:
                print(f"[Main] noteリサーチエラー: {e}")

            from apply_new_modules import apply_new_modules
            new_modules = apply_new_modules()
            print(f"[Step 5] 週次改善完了: {new_modules}件の新モジュール")
    else:
        print("\n[Step 5] 自己改善: 週次実行時のみ（スキップ）")

    save_memory("published.json", published)
    save_memory("strategy.json", strategy)
    save_memory("earnings.json", earnings)
    save_memory("proposals.json", proposals_memory)
    save_memory("saas.json", saas_memory)
    risk_manager.save_state(risk_state)

    # サマリー
    print(f"\n{'='*52}")
    print(f"  完了 | 実行回数: {strategy['iteration']}回")
    if "content" in all_results:
        cr = all_results["content"]
        note_ok = sum(1 for r in cr.get("note", []) if r.get("success"))
        site_ok = sum(1 for r in cr.get("static_site", []) if r.get("success"))
        x_ok = sum(1 for r in cr.get("x", []) if r.get("success"))
        print(f"  コンテンツ: note {note_ok}本 / サイト {site_ok}本 / X {x_ok}件")
    if "crowdworks" in all_results:
        cw = all_results["crowdworks"]
        print(f"  CrowdWorks: 提案文 {len(cw.get('proposals', []))}件")
    if "saas" in all_results:
        s = all_results["saas"]
        idea_name = s.get("saas_result", {}).get("idea", {}).get("name", "")
        print(f"  SaaS: {idea_name} のLPを生成")
    print(f"  次の重点: {strategy['current_focus']}")
    print(f"{'='*52}")


def send_weekly_report():
    """週次LINEサマリーを送信する（weekly.ymlから呼ばれる）"""
    config = load_config()
    earnings = load_memory("earnings.json") or {}
    risk_state = load_memory("risk_state.json") or {}

    try:
        with open("proposals/improvements.md", encoding="utf-8") as f:
            lines_md = f.read().split("\n")
            summary_line = next((l for l in lines_md if l.startswith("**サマリー**")), "")
            summary = summary_line.replace("**サマリー**: ", "").strip()[:80]
    except Exception:
        summary = ""

    total = earnings.get("total_earnings_jpy", 0)
    by_ch = earnings.get("by_channel", {})
    api_cost = risk_state.get("api_cost_month_usd", 0) * 150
    runs = risk_state.get("total_runs", 0)

    msg = f"🌱 週次改善 完了レポート\n\n💰 累計収益: ¥{total:,}\n  note: ¥{by_ch.get('note', 0):,}\n  CW: ¥{by_ch.get('crowdworks', 0):,}\n\n⚙️ 今月のAPI費用: ¥{api_cost:.0f}\n🔄 総実行回数: {runs}回"
    if summary:
        msg += f"\n\n📈 今週の分析:\n{summary}"

    from publishers import line_notifier
    line = config.get("line", {})
    line_notifier.text(line.get("channel_access_token", ""), line.get("user_id", ""), msg)
    print("週次サマリー送信完了")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自律型AIカンパニー")
    parser.add_argument("--dry-run", action="store_true", help="実際には投稿・送信せずにテスト実行")
    parser.add_argument("--report", action="store_true", help="収益レポートを表示")
    parser.add_argument("--weekly", action="store_true", help="週次実行（新モジュール生成含む）")
    parser.add_argument("--weekly-report", action="store_true", help="週次LINEサマリーを送信")
    parser.add_argument("--force-content", action="store_true", help="時間帯に関係なく記事生成を強制実行")
    args = parser.parse_args()
    if args.weekly_report:
        send_weekly_report()
    else:
        run(dry_run=args.dry_run, report_only=args.report, weekly=args.weekly, force_content=args.force_content)
