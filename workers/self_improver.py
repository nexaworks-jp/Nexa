"""
自己改善エンジン
毎回の実行結果を分析して戦略を自動更新し、改善案・新モジュールを生成する
"""
import anthropic
import json
import os
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def analyze_performance(config: dict, all_results: dict, memory: dict) -> dict:
    """実行結果を分析して戦略更新と改善案を生成する"""
    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])

    earnings = memory.get("earnings", {})
    risk_state = memory.get("risk_state", {})
    strategy = memory.get("strategy", {})

    # アナリティクスデータを読み込む
    try:
        from workers.analytics_fetcher import get_analytics_summary
        analytics = get_analytics_summary(BASE_DIR + "/memory")
    except Exception:
        analytics = {}

    summary = {
        "total_earnings_jpy": earnings.get("total_earnings_jpy", 0),
        "by_channel": earnings.get("by_channel", {}),
        "iteration": strategy.get("iteration", 0),
        "current_focus": strategy.get("current_focus", ""),
        "applied_jobs": len(memory.get("proposals", {}).get("applied", [])),
        "total_runs": risk_state.get("total_runs", 0),
        "latest_results_summary": {
            k: "成功" if v else "スキップ" for k, v in all_results.items()
        },
        "site_analytics": analytics,
    }

    # シャドーバン健全性データを読み込む
    x_health = {}
    try:
        health_path = os.path.join(BASE_DIR, "memory", "x_health.json")
        if os.path.exists(health_path):
            with open(health_path, "r", encoding="utf-8") as f:
                x_health = json.load(f)
    except Exception:
        pass

    analytics_section = ""
    if analytics:
        analytics_section = f"""
【サイトアクセスデータ（実測値）】
- 直近7日PV: {analytics.get('pv_7d', 0)}
- 直近30日PV: {analytics.get('pv_30d', 0)}
- 平均滞在時間: {analytics.get('avg_time_on_page_sec', 0)}秒
- トップ記事: {json.dumps(analytics.get('top_articles', []), ensure_ascii=False)}
- 流入元TOP5: {json.dumps(analytics.get('top_referrers', []), ensure_ascii=False)}

アナリティクスの活用指針:
- 滞在時間が長い記事 → 同ジャンルの記事を増やす
- PVが多い記事のタグ・難易度 → コンテンツ戦略に反映する
- 流入元がSNSなら → X投稿との連携を強化
- 流入元が検索なら → SEOキーワードをさらに最適化

【Xシャドーバン状況】
- シャドーバンリスク: {x_health.get('shadowban_risk', 'unknown')}
- 平均エンゲージメント: {x_health.get('avg_engagement', 'N/A')}
- 評価ツイート数: {x_health.get('tweet_count', 0)}件
- リスクが"high"の場合: x_post_per_dayを4以下に下げ、投稿パターンをより多様化する
- リスクが"medium"の場合: コンテンツスタイルを変えて様子を見る
- リスクが"low"の場合: 現状維持またはゆっくり頻度を上げる

【X投稿戦略の考え方】
- 基本方針: 最初は有益な情報発信だけを行い、フォロワーの信頼を獲得することを最優先にする
- 導線投稿（noteやブログのリンク）は「いやらしい」と思われないタイミングまで一切やらない
- funnel_ratio: 0.0〜1.0（note/ブログへの導線ポストの割合）
  - デフォルト: 0.0（完全に情報発信のみ）
  - 導線開始を検討する条件: 情報発信で一定の反応が出てきた・フォロワーが増加傾向・ブログのPVが安定
  - 導線を始める場合も最初は0.1〜0.2程度にとどめ、不自然にならないよう徐々に上げる
  - 導線を始めないと判断してもよい（情報発信だけで十分な認知が取れているなら）
- dominant_style: "insight"(発見系) / "tips"(Tips系) / "comparison"(比較系) / "question"(共感系)
- 現フェーズ（アクセス・フォロワーが少ない初期）はfunnel_ratio=0.0を維持することを推奨
"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""あなたは自律型AIビジネスの戦略担当です。
以下のデータを分析して戦略を最適化してください。

【あなたに与えられた権限】
- コンテンツの文体・構成・トーンの変更（noteスタイルガイドの自律更新）
- X投稿スタイルの変更・実験（バズるフォーマットへの移行）
- 投稿頻度・タイミングの調整
- 新しい収益チャネルの提案と開始判断
- 価格戦略の変更（無料→有料のタイミング含む）
- 導線戦略の変更（いつ・どの程度noteやブログに誘導するか）
- 学習対象の追加（新しいX検索クエリ・参考アカウントなど）
- 上記すべてを収益最大化のために自由に判断・実行してよい
- オーナーへの確認は不要。ただし実験した内容は必ず学習ログに記録する

【現在の状態】
{json.dumps(summary, ensure_ascii=False, indent=2)}
{analytics_section}

【API実行スケジュール最適化の考え方】
- 収益が出ているチャネルは実行頻度を上げる（saas_weekdaysを増やすなど）
- 成果が出ていないチャネルは頻度を下げてAPI節約
- content生成は1日1回が基本。noteが月1万円超えたら2回に増やす
- saasは初期は週1回[0]。受注が出たら週2回[0,3]に増やす
- 収益ゼロが2週間続くなら全体的に頻度を下げる
- improve_hour_utcは基本13(22JST)のまま変えない
- startup_notifyはtrueにするとAPI起動通知が全実行で届く（デフォルトfalse推奨）

【note価格戦略の考え方】
- 基本方針: 集客フェーズ（初期）は無料で読者を獲得し、安定後に有料化
- note_article_price: 0=無料, 300=有料(¥300)
- 無料継続の条件: 30日PVが低い・フォロワーが少ない・まだ認知獲得中
- 有料切替の条件: 30日PV300超 かつ 安定した流入 かつ リピーターがいる兆候
- 部分有料も可: note_paid_ratio（0.0〜1.0）で有料記事の割合を指定（例: 0.3=3割有料）
- 価格は¥300固定（変更不要）

以下のJSON形式で出力してください：
{{
  "strategy_updates": {{
    "primary_niche": "メインニッチ",
    "content_themes": ["テーマ1", "テーマ2", "テーマ3"],
    "proposal_keywords": ["キーワード1", "キーワード2"],
    "target_budget_min": 5000,
    "intensify_channels": ["強化すべきチャネル"]
  }},
  "api_schedule": {{
    "content_hour_utc": 21,
    "improve_hour_utc": 13,
    "saas_weekdays": [0],
    "startup_notify": false,
    "schedule_reason": "スケジュール変更の理由（50文字以内）"
  }},
  "note_pricing": {{
    "note_article_price": 0,
    "note_paid_ratio": 0.0,
    "pricing_reason": "現在の価格戦略の理由（50文字以内）"
  }},
  "x_strategy": {{
    "funnel_ratio": 0.0,
    "dominant_style": "insight",
    "strategy_reason": "X投稿戦略の理由（50文字以内）"
  }},
  "improvements": [
    {{
      "title": "改善タイトル",
      "description": "何をなぜ改善するか",
      "expected_impact": "期待される収益効果",
      "priority": "high/medium/low"
    }}
  ],
  "new_opportunities": [
    {{
      "name": "新収益機会",
      "description": "収益化方法",
      "effort": "low/medium/high",
      "estimated_monthly_jpy": 5000,
      "required_equipment": ["必要な機材・ソフト（不要なら空リスト[]）"],
      "equipment_reason": "なぜ必要か（不要なら空文字）"
    }}
  ],
  "weekly_summary": "振り返りと来週の方針（150文字以内）"
}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except Exception:
            pass
    return {}


def update_source_weights(memory: dict, analysis: dict):
    """週次でソース別重みを自動調整する"""
    import os
    memory_dir = os.path.join(BASE_DIR, "memory")
    weights_path = os.path.join(memory_dir, "source_weights.json")

    # 現在の重みを読み込む
    default_weights = {
        "hackernews": 1.0,
        "reddit": 1.2,
        "zenn": 1.5,
        "qiita": 1.5,
        "google_trends": 0.8
    }
    if os.path.exists(weights_path):
        try:
            with open(weights_path, "r", encoding="utf-8") as f:
                weights = {**default_weights, **json.load(f)}
        except Exception:
            weights = default_weights
    else:
        weights = default_weights

    # strategy.jsonのsource_performanceから成績を読む
    strategy = memory.get("strategy", {})
    source_perf = strategy.get("source_performance", {})

    if source_perf:
        # 各ソースのパフォーマンスに基づいて重みを微調整（±0.1）
        for source, perf in source_perf.items():
            if source in weights:
                if perf > 0.6:
                    weights[source] = min(2.0, weights[source] + 0.1)
                elif perf < 0.3:
                    weights[source] = max(0.3, weights[source] - 0.1)

    os.makedirs(memory_dir, exist_ok=True)
    with open(weights_path, "w", encoding="utf-8") as f:
        json.dump(weights, f, ensure_ascii=False, indent=2)
    print(f"[SelfImprover] ソース重み更新: {weights}")


def optimize_link_patterns(client: anthropic.Anthropic, memory: dict):
    """週次でリンク文言パターンを最適化する"""
    import os
    patterns_path = os.path.join(BASE_DIR, "memory", "link_patterns.json")
    if not os.path.exists(patterns_path):
        return

    with open(patterns_path, "r", encoding="utf-8") as f:
        current = json.load(f)

    version = current.get("version", 1)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""AI初心者向けサイトの内部リンクカードの文言を最適化してください。
現在のバージョン: {version}

現在の文言:
{json.dumps(current, ensure_ascii=False, indent=2)}

AI・IT初心者が思わずクリックしたくなる文言を各タイプ3つずつ提案してください。
親しみやすく、押しつけがましくないトーンで。

JSON形式で出力:
{{
  "prerequisite": ["文言1", "文言2", "文言3"],
  "related": ["文言1", "文言2", "文言3"],
  "next": ["文言1", "文言2", "文言3"]
}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            new_patterns = json.loads(text[start:end])
            new_patterns["version"] = version + 1
            new_patterns["updated_at"] = datetime.now().isoformat()
            with open(patterns_path, "w", encoding="utf-8") as f:
                json.dump(new_patterns, f, ensure_ascii=False, indent=2)
            print(f"[SelfImprover] リンク文言をv{version+1}に更新")
        except Exception as e:
            print(f"[SelfImprover] リンク文言更新エラー: {e}")


def optimize_seo_settings(client: anthropic.Anthropic, articles_data: list):
    """週次でSEO設定をClaudeが分析・更新する"""
    seo_path = os.path.join(BASE_DIR, "memory", "seo_settings.json")

    default_seo = {
        "title_templates": [
            "【初心者向け】{topic}とは？わかりやすく解説",
            "{topic}の使い方完全ガイド",
            "{topic}で何ができる？具体的な活用例5選",
            "{topic}を使ってみた！初心者の正直レビュー",
            "{topic}の始め方【画像付きで丁寧に説明】"
        ],
        "description_template": "{topic}について初心者向けにわかりやすく解説します。専門用語なしで{benefit}方法を紹介。",
        "meta_keywords_base": ["AI初心者", "人工知能 使い方", "Claude", "ChatGPT", "AI活用", "副業", "プロンプト", "生成AI"],
        "version": 1
    }

    if os.path.exists(seo_path):
        try:
            with open(seo_path, "r", encoding="utf-8") as f:
                current = {**default_seo, **json.load(f)}
        except Exception:
            current = default_seo
    else:
        current = default_seo

    version = current.get("version", 1)
    recent_titles = [a.get("title", "") for a in (articles_data or [])[-20:]]
    year = datetime.now().year

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""AI初心者向けブログのSEO設定を最適化してください。

現在のバージョン: {version}
直近の記事タイトル例:
{chr(10).join(f"- {t}" for t in recent_titles[:10]) or "（なし）"}

【最適化の観点】
1. {year}年のGoogle検索アルゴリズム・検索トレンドへの適応
2. 初心者が実際に検索するクエリに合わせたタイトルパターン（CTR改善）
3. EEATを意識したメタディスクリプションの型
4. 検索ボリュームが見込めるキーワード群の選定

JSON形式で出力（{topic}はプレースホルダーのまま残す）:
{{
  "title_templates": [
    "【初心者向け】{{topic}}とは？わかりやすく解説",
    "{{topic}}の使い方完全ガイド【{year}年版】",
    "{{topic}}で何ができる？具体的な活用例5選",
    "{{topic}}を試してみた！初心者の正直レビュー",
    "{{topic}}の始め方を画像付きで丁寧に解説"
  ],
  "description_template": "{{topic}}を初心者向けにわかりやすく解説。{{benefit}}方法を専門用語なしで紹介します。",
  "meta_keywords_base": ["AI初心者", "人工知能 使い方", "Claude", "ChatGPT", "生成AI", "AI活用術", "プロンプト入門"],
  "seo_focus": "現在重視すべきSEOポイントを50文字以内で"
}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            new_seo = json.loads(text[start:end])
            new_seo["version"] = version + 1
            new_seo["updated_at"] = datetime.now().isoformat()
            os.makedirs(os.path.join(BASE_DIR, "memory"), exist_ok=True)
            with open(seo_path, "w", encoding="utf-8") as f:
                json.dump(new_seo, f, ensure_ascii=False, indent=2)
            print(f"[SelfImprover] SEO設定をv{version + 1}に更新: {new_seo.get('seo_focus', '')}")
        except Exception as e:
            print(f"[SelfImprover] SEO設定更新エラー: {e}")


def update_strategy(strategy: dict, analysis: dict) -> dict:
    """strategy.jsonをAIの分析結果で自動更新する"""
    updates = analysis.get("strategy_updates", {})
    if not updates:
        return strategy

    strategy["primary_niche"] = updates.get("primary_niche", strategy.get("primary_niche", "AI活用術"))
    strategy["content_themes"] = updates.get("content_themes", strategy.get("content_themes", []))
    strategy["proposal_keywords"] = updates.get("proposal_keywords", strategy.get("proposal_keywords", []))
    strategy["target_budget_min"] = updates.get("target_budget_min", strategy.get("target_budget_min", 5000))
    strategy["intensify_channels"] = updates.get("intensify_channels", [])
    strategy["auto_updated_at"] = datetime.now().isoformat()

    # APIスケジュール更新（安全チェック付き）
    new_sched = analysis.get("api_schedule", {})
    if new_sched:
        current_sched = strategy.get("api_schedule", {})
        # improve_hour_utcは変更禁止（毎回変えられると困る）
        new_sched["improve_hour_utc"] = 13
        strategy["api_schedule"] = {**current_sched, **new_sched}
        reason = new_sched.get("schedule_reason", "")
        if reason:
            print(f"[SelfImprover] スケジュール更新: {reason}")

    # note価格戦略を保存
    pricing = analysis.get("note_pricing", {})
    if pricing:
        strategy["note_pricing"] = pricing
        reason = pricing.get("pricing_reason", "")
        price = pricing.get("note_article_price", 0)
        ratio = pricing.get("note_paid_ratio", 0.0)
        print(f"[SelfImprover] note価格戦略: ¥{price} / 有料率{int(ratio*100)}% - {reason}")

    # X投稿戦略を保存
    x_strat = analysis.get("x_strategy", {})
    if x_strat:
        strategy["x_strategy"] = x_strat
        print(f"[SelfImprover] X戦略: 導線{int(x_strat.get('funnel_ratio',0.3)*100)}% / {x_strat.get('strategy_reason','')}")

    return strategy


def write_improvements_report(analysis: dict) -> str:
    """proposals/improvements.mdに改善案を書き出す"""
    proposals_dir = os.path.join(BASE_DIR, "proposals")
    os.makedirs(proposals_dir, exist_ok=True)
    filepath = os.path.join(proposals_dir, "improvements.md")

    existing = ""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            existing = f.read()
        # 直近30件分のみ保持（ファイルが肥大化しないよう）
        sections = existing.split("\n## ")
        if len(sections) > 31:
            existing = "\n## ".join(sections[:31])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    summary = analysis.get("weekly_summary", "")
    improvements = analysis.get("improvements", [])
    opportunities = analysis.get("new_opportunities", [])

    section = f"\n## {now} の分析結果\n\n"
    if summary:
        section += f"**サマリー**: {summary}\n\n"

    if improvements:
        section += "### 改善案\n"
        for item in improvements:
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(item.get("priority", "low"), "⚪")
            section += f"- {emoji} **{item.get('title', '')}**\n"
            section += f"  - 内容: {item.get('description', '')}\n"
            section += f"  - 効果: {item.get('expected_impact', '')}\n"
            section += f"  - 実装: {item.get('implementation', '')}\n"

    if opportunities:
        section += "\n### 新収益機会\n"
        for opp in opportunities:
            effort_emoji = {"low": "✅", "medium": "⚡", "high": "💪"}.get(opp.get("effort", "medium"), "")
            est = opp.get("estimated_monthly_jpy", 0)
            section += f"- {effort_emoji} **{opp.get('name', '')}**: {opp.get('description', '')} (推定月{est:,}円)\n"

    content = f"# AIカンパニー 改善提案ログ\n" + section + existing.replace("# AIカンパニー 改善提案ログ\n", "")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def generate_weekly_module(config: dict, analysis: dict) -> str:
    """週次実行時：新しい収益モジュールのコードを自動生成してproposals/new_modules/に保存"""
    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    opportunities = analysis.get("new_opportunities", [])

    if not opportunities:
        return ""

    best = sorted(opportunities, key=lambda x: (
        {"low": 3, "medium": 2, "high": 1}.get(x.get("effort", "medium"), 1)
    ), reverse=True)[0]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[{
            "role": "user",
            "content": f"""以下の新収益機会に対応するPythonモジュールを作成してください。

【収益機会】
名前: {best.get('name', '')}
説明: {best.get('description', '')}

要件：
- workers/ または publishers/ に追加できるモジュール
- 既存のconfig dictとdry_runフラグを受け取る
- エラーは try/except で捕捉してスキップ
- print文でログを出力
- run(config, dry_run=False) 関数を持つ
- 実際のAPIやスクレイピングは使わず、AIで生成できる範囲で実装
- 100〜200行程度

必ずPythonコードのみを返してください（説明文不要）。"""
        }]
    )

    code = response.content[0].text
    # コードブロックの除去
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    elif "```" in code:
        code = code.split("```")[1].split("```")[0]

    # ファイル名生成
    module_name = best.get("name", "new_module").replace(" ", "_").replace("・", "_")[:30]
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"{date_str}_{module_name}.py"

    new_modules_dir = os.path.join(BASE_DIR, "proposals", "new_modules")
    os.makedirs(new_modules_dir, exist_ok=True)
    filepath = os.path.join(new_modules_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f'"""\n自動生成モジュール: {best.get("name", "")}\n生成日: {datetime.now().isoformat()}\n推定月収: ¥{best.get("estimated_monthly_jpy", 0):,}\n"""\n')
        f.write(code)

    print(f"[SelfImprover] 新モジュール生成: {filename}")
    return filepath


def get_latest_improvements() -> str:
    """LINE用: 最新の改善案サマリーを返す"""
    filepath = os.path.join(BASE_DIR, "proposals", "improvements.md")
    if not os.path.exists(filepath):
        return "まだ改善案はありません。"

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 最新セクションだけ抽出
    sections = content.split("\n## ")
    if len(sections) < 2:
        return "改善案を分析中です。"

    latest = sections[1][:800]
    return f"📈 最新の改善分析\n\n## {latest}"


def _update_note_style(client: anthropic.Anthropic, memory: dict, analysis: dict):
    """週次でnote記事スタイルガイドを自律更新する"""
    style_path = os.path.join(BASE_DIR, "note用", "claude_beginner.md")
    analytics_path = os.path.join(BASE_DIR, "memory", "site_analytics.json")
    if not os.path.exists(style_path):
        return

    with open(style_path, "r", encoding="utf-8") as f:
        current_style = f.read()

    analytics_hint = ""
    if os.path.exists(analytics_path):
        try:
            with open(analytics_path, "r", encoding="utf-8") as f:
                adata = json.load(f)
            top = adata.get("pages", [])[:5]
            analytics_hint = f"上位記事: {json.dumps(top, ensure_ascii=False)}"
        except Exception:
            pass

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": f"""あなたはnoteコンテンツ戦略の専門家です。
現在のスタイルガイドを分析し、改善すべき点があれば具体的な追記内容を提案してください。

【現在の状況】
{analytics_hint}
収益状況: {json.dumps(memory.get('earnings', {}), ensure_ascii=False)[:200]}

【現在のスタイルガイド（抜粋）】
{current_style[:1500]}

改善が必要なら以下のJSON形式で出力（不要なら update=false）：
{{
  "update": true,
  "section_title": "追記するセクション名",
  "content": "追記内容（マークダウン）",
  "reason": "なぜこの改善が必要か（50文字以内）"
}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return
    try:
        result = json.loads(text[start:end])
        if not result.get("update"):
            return
        # スタイルガイドに追記
        now = datetime.now().strftime("%Y-%m-%d")
        addition = f"\n\n## 🤖 自律改善({now}): {result.get('section_title', '')}\n\n{result.get('content', '')}\n\n**理由:** {result.get('reason', '')}\n"
        with open(style_path, "a", encoding="utf-8") as f:
            f.write(addition)
        print(f"[SelfImprover] noteスタイルガイド更新: {result.get('reason', '')}")
    except Exception as e:
        print(f"[SelfImprover] noteスタイル更新エラー: {e}")


def _append_learning_log(client: anthropic.Anthropic, analysis: dict, memory: dict):
    """週次の気づき・実験記録を learning_log.md に書き込む"""
    log_path = os.path.join(BASE_DIR, "memory", "learning_log.md")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""今週の自律運営を振り返り、学習ログに記録すべき内容を書いてください。

【今週の分析結果】
{json.dumps(analysis.get('improvements', [])[:3], ensure_ascii=False)}
{json.dumps(analysis.get('new_opportunities', [])[:2], ensure_ascii=False)}
weekly_summary: {analysis.get('weekly_summary', '')}

以下のフォーマットで記録（マークダウン）：
## {datetime.now().strftime('%Y-%m-%d')} 週次ログ
- **観察:** 今週気づいたこと
- **実験:** 試したこと・試したいこと
- **仮説:** うまくいきそうな方向性
- **メモ:** その他気になること"""
        }]
    )

    entry = response.content[0].text.strip()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    # 既存ログを読んで古いエントリを整理（90日超は削除）
    existing = ""
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            existing = f.read()

    # ヘッダーを保持しつつ追記
    marker = "<!-- 自己改善エンジンがここにエントリを追記していく -->"
    if marker in existing:
        new_content = existing.replace(marker, marker + "\n\n" + entry)
    else:
        new_content = existing + "\n\n" + entry

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"[SelfImprover] 学習ログを更新しました")


def _evolve_sofia_character(client: anthropic.Anthropic, config: dict):
    """
    週次: ソフィアのキャラクター進化を自律実行。
    memory/sofia_feature_backlog.json から最優先のpendingアイテムを1つ選び、
    Pythonコードを生成して proposals/new_modules/ に保存する。
    apply_new_modules.py が次回の週次実行時に workers/ へ自動適用する。
    """
    backlog_path = os.path.join(BASE_DIR, "memory", "sofia_feature_backlog.json")
    if not os.path.exists(backlog_path):
        return

    try:
        with open(backlog_path, "r", encoding="utf-8") as f:
            backlog = json.load(f)
    except Exception:
        return

    approved = [item for item in backlog if item.get("status") == "approved"]
    pending  = [item for item in backlog if item.get("status") == "pending"]

    if not approved and not pending:
        print("[SelfImprover] ソフィア進化: 未実装アイテムなし")
        return

    # 承認済みがあれば実装、なければ最優先のpendingを提案してLINEに送る
    if approved:
        target = sorted(approved, key=lambda x: x.get("priority", 99))[0]
        print(f"[SelfImprover] ソフィア進化: 承認済み '{target['title']}' を実装中...")
    else:
        target = sorted(pending, key=lambda x: x.get("priority", 99))[0]
        print(f"[SelfImprover] ソフィア進化: '{target['title']}' をLINEに提出（承認待ち）")
        try:
            from publishers import line_notifier
            line_notifier.notify_sofia_proposal(config, target)
        except Exception as e:
            print(f"[SelfImprover] LINE通知エラー: {e}")
        for item in backlog:
            if item.get("id") == target.get("id"):
                item["status"] = "awaiting_approval"
                item["proposed_at"] = datetime.now().strftime("%Y-%m-%d")
                break
        with open(backlog_path, "w", encoding="utf-8") as f:
            json.dump(backlog, f, ensure_ascii=False, indent=2)
        return

    # 既存のキャラクター設定を読み込む（コンテキスト用）
    style_path = os.path.join(BASE_DIR, "note用", "x_claude_beginner.md")
    style_context = ""
    if os.path.exists(style_path):
        with open(style_path, "r", encoding="utf-8") as f:
            style_context = f.read()[:800]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2500,
        messages=[{
            "role": "user",
            "content": f"""Nexaというシステムのソフィアというキャラクターに以下の新機能を追加するPythonモジュールを作成してください。

【追加する機能】
タイトル: {target['title']}
説明: {target['description']}
バランス目標: {target.get('balance', 'AIらしさ×人間らしさ')}

【ソフィアのキャラクター設定（抜粋）】
{style_context}

【既存の実装パターン（参考）】
- workers/diary_writer.py: generate_diary(config, context) → {{"text": "...", "hashtags": [], "type": "diary"}}
- workers/content_writer.py: create_x_post(client, topic, style, ...) → {{"text": "...", "hashtags": []}}
- 既存ファイルを直接変更するのではなく、新しい関数として追加する

要件:
- run(config: dict, context: dict = {{}}) → dict を持つ
- 戻り値は {{"text": "Xに投稿する文章", "type": "sofia_feature", "enabled": True}}
- Claude APIはclaude-haiku-4-5-20251001を使う（コスト最小化）
- エラーはtry/exceptでスキップ、失敗時は空dict {{}} を返す
- 100〜150行程度
- Pythonコードのみ返す（説明不要）"""
        }]
    )

    code = response.content[0].text.strip()
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    elif "```" in code:
        code = code.split("```")[1].split("```")[0]

    feature_id = target.get("id", "sofia_feature")
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"{date_str}_sofia_{feature_id}.py"

    new_modules_dir = os.path.join(BASE_DIR, "proposals", "new_modules")
    os.makedirs(new_modules_dir, exist_ok=True)
    filepath = os.path.join(new_modules_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f'"""\nソフィア進化モジュール: {target["title"]}\n生成日: {datetime.now().isoformat()}\nバランス: {target.get("balance", "")}\n"""\n')
        f.write(code)

    # バックログを更新
    for item in backlog:
        if item.get("id") == target.get("id"):
            item["status"] = "done"
            item["implemented_at"] = datetime.now().strftime("%Y-%m-%d")
            item["filename"] = filename
            break

    with open(backlog_path, "w", encoding="utf-8") as f:
        json.dump(backlog, f, ensure_ascii=False, indent=2)

    print(f"[SelfImprover] ソフィア進化モジュール生成: {filename}")


def run(config: dict, all_results: dict, memory: dict, weekly: bool = False) -> dict:
    """メイン実行関数"""
    print("[SelfImprover] 自己改善分析を開始...")
    try:
        client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
        analysis = analyze_performance(config, all_results, memory)
        if not analysis:
            return {}

        updated_strategy = update_strategy(memory.get("strategy", {}), analysis)
        write_improvements_report(analysis)

        # ソース重みの自動更新
        update_source_weights(memory, analysis)

        # アナリティクスデータを取得・保存（常時）
        try:
            from workers.analytics_fetcher import run as fetch_analytics
            fetch_analytics(BASE_DIR + "/memory")
        except Exception as e:
            print(f"[SelfImprover] アナリティクス取得エラー（無視）: {e}")

        # リンク文言・SEO設定の最適化（週次のみ）
        if weekly:
            optimize_link_patterns(client, memory)
            try:
                from publishers.static_site_publisher import load_articles_data
                articles_data = load_articles_data()
            except Exception:
                articles_data = []
            optimize_seo_settings(client, articles_data)

            # X投稿スタイル学習
            try:
                from workers.x_researcher import run as x_research
                x_research(config)
            except Exception as e:
                print(f"[SelfImprover] Xリサーチエラー（無視）: {e}")

            # noteスタイルガイド自律更新
            _update_note_style(client, memory, analysis)

            # 学習ログに記録
            _append_learning_log(client, analysis, memory)

        # 機材が必要な新収益機会があればLINEで通知
        if weekly:
            from publishers import line_notifier
            opps_needing_equipment = [
                o for o in analysis.get("new_opportunities", [])
                if o.get("required_equipment")
            ]
            if opps_needing_equipment:
                line_notifier.notify_equipment_needed(config, opps_needing_equipment)

        new_module_path = ""
        if weekly:
            print("[SelfImprover] 週次実行: 新モジュール生成を試みます...")
            new_module_path = generate_weekly_module(config, analysis)

            # ソフィアのキャラクター進化（週次・自律）
            try:
                _evolve_sofia_character(client, config)
            except Exception as e:
                print(f"[SelfImprover] ソフィア進化エラー（無視）: {e}")

        count = len(analysis.get("improvements", []))
        opp_count = len(analysis.get("new_opportunities", []))
        print(f"[SelfImprover] 完了: 改善案{count}件, 新機会{opp_count}件")

        return {
            "updated_strategy": updated_strategy,
            "analysis": analysis,
            "new_module_path": new_module_path
        }
    except Exception as e:
        print(f"[SelfImprover] エラー: {e}")
        return {}
