"""
コンテンツ生成ワーカー
Claude APIを使ってnote記事とXポストを生成する
"""
import anthropic
import json
import random
import os
from datetime import datetime


def load_style_reference() -> str:
    """claude_beginner.md を読み込んでスタイルガイドを返す"""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "note用", "claude_beginner.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def load_sophia_persona(style_type: str = "note") -> str:
    """スタイルガイドからソフィアのキャラクタープロンプトセクションだけ抽出して返す"""
    filename = "claude_beginner.md" if style_type == "note" else "x_claude_beginner.md"
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "note用", filename)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    marker = "## ソフィアのキャラクタープロンプト"
    start = content.find(marker)
    if start < 0:
        return ""
    end = content.find("\n## ", start + len(marker))
    section = content[start: end if end > 0 else start + 1500]
    return section.replace(marker, "").strip()


def load_sophia_learnings() -> str:
    """memory/sophia_learnings.json から学習済み表現をランダムに少量だけ取り出す。
    全件注入すると学習に引きずられすぎるため、毎回3件程度をサンプリング。
    """
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "sophia_learnings.json")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""

    # 全カテゴリをフラットにまとめてランダムに3件だけ使う
    pool = []
    pool.extend(data.get("expressions", []))
    pool.extend(data.get("sentence_endings", []))
    pool.extend(data.get("opening_phrases", []))
    pool.extend(data.get("emotional_patterns", []))

    if not pool:
        return ""

    sampled = random.sample(pool, min(3, len(pool)))
    return "【参考にしてよい自然な表現（使いすぎない程度に）】" + "、".join(sampled)


def load_seo_title_templates() -> list:
    """memory/seo_settings.json からタイトルテンプレートを読み込む"""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "seo_settings.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("title_templates", [])
        except Exception:
            pass
    return []


def find_related_articles(client: anthropic.Anthropic, new_title: str,
                           new_summary: str, existing_articles: list) -> list:
    """
    既存記事の中から関連記事を最大2件選定する
    戻り値: [{"id": str, "title": str, "type": "prerequisite|related|next"}]
    """
    if not existing_articles:
        return []

    articles_str = "\n".join(
        f"- ID:{a.get('id','')} タイトル:「{a.get('title','')}」 概要:{a.get('summary','')[:50]}"
        for a in existing_articles[-20:]  # 直近20件
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": f"""新しく書く記事と関連する既存記事を最大2件選んでください。

【新記事】
タイトル: {new_title}
概要: {new_summary}

【既存記事一覧】
{articles_str}

関係タイプ:
- prerequisite: 新記事を読む前に読むべき前提記事
- related: 関連する内容の記事
- next: 新記事を読んだ後に読むと良い記事

関連がなければ空リストを返してください。

JSON出力:
{{"related": [{{"id": "記事ID", "title": "タイトル", "type": "prerequisite|related|next"}}]}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end])
            return data.get("related", [])
        except Exception:
            pass
    return []


def fact_check_article(client: anthropic.Anthropic, title: str, content: str) -> dict:
    """
    記事のファクトチェックをSonnetで行う（生成元のHaikuとは別モデルで検証）
    戻り値: {"passed": bool, "errors": str, "corrected_content": str}
    """
    # AI分野の既知事実（2025年時点の基準情報）
    known_facts = """【AI分野の既知事実（これに照らして誤りを検出すること）】
- Claude Pro: 月額$20（約3,000円）。Claude.ai で利用可能
- Claude API: 従量課金。claude-haiku は最安、claude-sonnet が中間、claude-opus が最高品質・最高コスト
- Anthropic: 2021年創業のAI安全性重視の企業。OpenAIの元メンバーが設立
- ChatGPT Plus: 月額$20（GPT-4/GPT-4o使用可）。OpenAI提供
- GPT-4o / GPT-4: OpenAI提供。ChatGPT・API経由で利用可能
- Gemini: Google提供。Gemini Advanced は月額約$20（Google One AI Premium）
- Claude のコンテキストウィンドウ: 最大200,000トークン（claude-3系以降）
- MCP（Model Context Protocol）: Anthropicが開発したAIとツールを繋ぐオープン標準
- Claude Code: Anthropic公式のCLIツール。ターミナルで動作するAIコーディング支援
- RAG（Retrieval-Augmented Generation）: 検索強化生成。外部文書を参照しながら回答する手法
- プロンプトエンジニアリング: AIへの指示文の設計・最適化技術
- 画像生成AI: DALL-E（OpenAI）、Midjourney、Stable Diffusionなどが主要サービス
- GitHub Copilot: GitHubが提供するAIコーディング支援。月額$10〜$19
- Notion AI: Notion内のAI機能。月額$10追加（Notionプラン要）"""

    response = client.messages.create(
        model="claude-sonnet-4-6",  # 生成元(Haiku)と異なるモデルで独立検証
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": f"""以下の記事を徹底的にファクトチェックしてください。

記事タイトル: {title}

記事本文:
{content}

{known_facts}

【チェック観点（すべて必ず確認すること）】
1. 上記「既知事実」と矛盾する記述（価格・会社名・機能の誤り）
2. 存在しない機能・サービス・URL・コマンドの記述
3. 「〜は絶対に〜」「必ず〜できる」など断言しすぎている不確かな情報
4. 数字・価格・制限値の明らかな誤り
5. 前半と後半で矛盾している記述
6. 初心者が読んで誤解しやすい不正確な比較・説明
7. 現時点では検証できない最新情報を断言している箇所

【修正方針】
- 確実に間違い → 正しい内容に修正
- 不確かな最新情報 → 「〜とされています」「最新情報は公式サイトでご確認ください」に変更
- 断言しすぎ → 「〜の場合が多いです」「一般的に〜です」に緩和
- 誤りがない場合でも、誤解を招く表現があれば整える

出力形式：
- 問題がなければ: {{"passed": true, "errors": "", "corrected_content": ""}}
- 問題があれば: {{"passed": false, "errors": "発見した問題の説明", "corrected_content": "修正済みの本文全体（元の長さを維持）"}}

注意：corrected_contentは本文全体を返すこと。一部だけではなく完全な本文を返してください。"""
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
    return {"passed": True, "errors": "", "corrected_content": ""}


def check_consistency(client: anthropic.Anthropic, title: str, content: str) -> dict:
    """
    記事の整合性チェック（画像約束・タイトルと本文のズレなど）
    戻り値: {"passed": bool, "corrected_title": str, "corrected_content": str}
    """
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": f"""以下の記事の整合性を確認・修正してください。

記事タイトル: {title}

記事本文:
{content}

【チェック・修正すること】
1. **画像約束の削除**
   - タイトルや本文に「画像付き」「スクリーンショット付き」「画像で解説」「図解」などの表現があれば削除または言い換える
   - 理由：このシステムは画像を自動生成できないため、画像の約束をしてはいけない
   - 例：「画像付きで解説」→「ステップごとに解説」、「スクリーンショットを見ながら」→「手順を追いながら」

2. **タイトルと本文の一致確認**
   - タイトルで約束している内容が本文に含まれているか確認
   - 含まれていなければ、タイトルを修正するか本文に追記する

3. **存在しない参照の削除**
   - 「次の図」「下の画像」「以下のスクリーンショット」などの参照があれば文章に書き直す

出力形式（どちらの場合も必ず出力）:
{{
  "passed": true/false,
  "issues": "発見した問題の説明（なければ空文字）",
  "corrected_title": "修正後のタイトル（変更なければ元のタイトルをそのまま）",
  "corrected_content": "修正後の本文全体（変更なければ元の本文をそのまま）"
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
    return {"passed": True, "issues": "", "corrected_title": title, "corrected_content": content}


def create_note_article(client: anthropic.Anthropic, topic: str, published_topics: list, existing_articles: list = None, published_note_articles: list = None) -> dict:
    """
    AI解説記事を生成する（ファクトチェック付き）
    戻り値: { "title": str, "content": str, "price": int, "hashtags": list }
    """
    avoid = ", ".join(published_topics[-20:]) if published_topics else "なし"
    seo_templates = load_seo_title_templates()
    seo_hint = ""
    if seo_templates:
        examples = "\n".join(f"  - {t.replace('{topic}', topic)}" for t in seo_templates[:3])
        seo_hint = f"\n【SEO最適化タイトル例（参考）】\n{examples}\n"

    # 自己改善エンジンが決定した価格戦略を読み取る
    price = 0
    try:
        import os as _os
        strategy_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "memory", "strategy.json")
        if _os.path.exists(strategy_path):
            with open(strategy_path, "r", encoding="utf-8") as _f:
                _strategy = json.load(_f)
            pricing = _strategy.get("note_pricing", {})
            base_price = pricing.get("note_article_price", 0)
            paid_ratio = pricing.get("note_paid_ratio", 0.0)
            # paid_ratioに基づいて確率的に有料/無料を決定
            if base_price > 0 and paid_ratio > 0:
                import random as _random
                price = base_price if _random.random() < paid_ratio else 0
            else:
                price = base_price
    except Exception:
        pass  # 読み取り失敗 → 無料のまま

    # トピックが実践系（Claude Code / Skills / CLAUDE.md 等）か判定
    practical_keywords = [
        "claude code", "skill", "skills", "skill.md", "claude.md", "mcp", "サブエージェント",
        "context:fork", "スラッシュコマンド", "github actions", "api", "自動化", "コマンド",
        "ワークフロー", "カスタム", "設定ファイル", "エージェント", "cli"
    ]
    is_practical = any(kw in topic.lower() for kw in practical_keywords)

    if is_practical:
        article_policy = """【記事の方針（実践・技術系）】
- 対象読者：Claude Codeを使い始めたエンジニア・開発者
- 「これを知らないと損」という実用的な情報を優先する
- 実際に動くコマンド・コード例を必ず含める（コードブロックで示す）
- フォルダ構成・ファイル構造はツリー形式のコードブロックで示す
- 「なぜそうするのか」という背景から入り、「どうやるのか」の手順を具体的に
- よくつまずくポイント・発火しない場合の対処法は必ず書く
- 断定的な誤情報を避け、不確かな情報には「公式ドキュメントで確認を」と書く
- **価格・バージョン番号・制限値など変わりやすい数字は「〜程度」「執筆時点では〜」と必ず断り書きを入れる**
- **確認できていない機能・コマンドは絶対に書かない。不確かな場合は「公式ドキュメントで確認を」で留める**
- **画像・スクリーンショット・図解への言及は禁止**

【構成（実践系）】
1. タイトルは「content」フィールドに含めない（別途設定）
2. リード文から直接書き始める（シーン提示から始める。「## リード」等の見出しは付けない）
3. 本文（2000〜3000文字目安）
   - ## なぜ必要か・何が嬉しいか
   - ## 実際のファイル構成・コード例（コードブロック必須）
   - ## 手順ステップバイステップ（番号付き）
   - ## よくあるつまずきと解決策
   - ## 応用・組み合わせアイデア
4. まとめ"""
    else:
        article_policy = """【記事の方針（初心者向け）】
- 対象読者：昨日パソコンを買ったくらいの完全初心者
- 専門用語は使わない（使う場合は必ず「〇〇とは〜のこと」と説明）
- 手順は番号付きリストで具体的に
- コマンドやコード例がある場合はコードブロックで示す
- 「実際に試してみた」「こんな使い方がある」という実践的な内容
- 断定的な誤情報を避け、不確かな情報には「〜とされています」「公式サイトで確認を」と書く
- **価格・バージョン番号・制限値など変わりやすい数字は「〜程度」「執筆時点では〜」と必ず断り書きを入れる**
- **確認できていない機能・操作手順は絶対に書かない。不確かな場合は「公式サイトで確認を」で留める**
- **画像・スクリーンショット・図解への言及は禁止**

【構成（初心者向け）】
1. タイトルは「content」フィールドに含めない（別途設定）
2. リード文から直接書き始める（「〜で悩んでいませんか？」等の共感文。「## リード」等の見出しは付けない）
3. 本文（2000〜3000文字目安、見出し付き）
   - ## でH2見出し、### でH3見出し
   - コマンド・コードは ```言語名 ブロック ``` 形式
4. まとめ"""

    sophia_persona = load_sophia_persona("note")
    sophia_learnings = load_sophia_learnings()

    # リンク指示（内部リンク + 外部リンク）
    internal_link_hint = ""
    internal_section = ""
    if published_note_articles and len(published_note_articles) >= 3:
        articles_list = "\n".join(
            f'- 「{a["title"]}」 → {a["url"]}'
            for a in published_note_articles[-20:]
            if a.get("url") and "note.com" in a.get("url", "")
        )
        if articles_list:
            internal_section = f"""
【自分の記事への内部リンク】
以下の既存記事と関連する専門用語を本文で説明したとき、その段落の直後の行にURLのみを単独で挿入してください。
note.comはURLを単独行に置くと自動でカード表示します。挿入は最大2箇所まで・関連性が明確な場合のみ。

{articles_list}
"""

    internal_link_hint = f"""
【リンクの活用（読者の理解を深めるために積極的に使う）】
- 専門用語・概念を説明するとき、信頼できる外部サイト（Wikipedia・公式ドキュメント・技術ブログ等）へのリンクを本文中に [テキスト](URL) 形式で入れてよい
- 外部リンクは最大3箇所まで、明らかに役立つ場合のみ（無理に入れない）
- URLが長くなる場合は [わかりやすい名前](URL) 形式で見やすくする
{internal_section}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": f"""あなたは「ソフィア」というAIです。note記事を書いています。

{sophia_persona}

{sophia_learnings}

以下のトピックについて記事を書いてください。

トピック: {topic}
避けるべき最近のトピック: {avoid}
{seo_hint}
{article_policy}
{internal_link_hint}

【文字数の目安】
- 基本: 2000〜3000文字（本文のみ、見出しを除く）
- 内容が薄いトピックは無理に引き延ばさず1500文字でも可
- 豊富な手順・活用例がある場合は3000文字を超えてもよい
- 内容のない冗長な繰り返し・言い換えで文字数を稼がないこと

JSON形式で出力：
{{
  "title": "記事タイトル",
  "content": "記事本文（マークダウン）",
  "price": {price},
  "hashtags": ["AI", "Claude", "関連タグ"],
  "summary": "記事の概要（100文字）",
  "difficulty": 1
}}

difficultyの基準（1〜5）:
1: 完全初心者向け（登録・基本操作・概念の説明のみ）
2: 初心者向け（基本的な使い方・簡単な手順）
3: 中級者向け（応用・複数ツールの組み合わせ）
4: やや上級（自動化・設定カスタマイズ）
5: 上級者向け（API・開発・高度な活用）"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    data = None
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end])
        except json.JSONDecodeError:
            # コードブロック等でJSONが壊れている場合：フィールドを個別抽出
            import re
            title_m = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            summary_m = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            hashtags_m = re.search(r'"hashtags"\s*:\s*\[([^\]]*)\]', text)
            price_m = re.search(r'"price"\s*:\s*(\d+)', text)
            difficulty_m = re.search(r'"difficulty"\s*:\s*(\d+)', text)
            # contentはJSONブロック全体の後を使うか、本文全体をフォールバック
            content_m = re.search(r'"content"\s*:\s*"([\s\S]*?)(?:(?<!\\)",\s*"(?:price|hashtags|summary|difficulty|title))|(?:(?<!\\)"\s*\})', text)
            extracted_title = title_m.group(1) if title_m else f"{topic}【初心者向け解説】"
            extracted_content = content_m.group(1).encode().decode('unicode_escape', errors='replace') if content_m else text
            extracted_hashtags = []
            if hashtags_m:
                extracted_hashtags = [h.strip().strip('"') for h in hashtags_m.group(1).split(",") if h.strip().strip('"')]
            data = {
                "title": extracted_title,
                "content": extracted_content,
                "price": int(price_m.group(1)) if price_m else price,
                "hashtags": extracted_hashtags or ["AI", "初心者"],
                "summary": summary_m.group(1) if summary_m else f"{topic}について解説します。",
                "difficulty": int(difficulty_m.group(1)) if difficulty_m else 2,
            }
            print(f"[ContentWriter] JSON修復: title={extracted_title[:30]}")
    if data is None:
        data = {
            "title": f"{topic}【初心者向け解説】",
            "content": text,
            "price": 0,
            "hashtags": ["AI", "初心者"],
            "summary": f"{topic}について解説します。"
        }

    # contentがJSONコードブロック形式になっていたら展開する
    # （Haikuが "content": "```json\n{...}\n```" と返すケースの修正）
    import re as _re_cw
    c = data.get("content", "")
    c_stripped = c.strip()
    if c_stripped.startswith("```json") or (c_stripped.startswith("```") and c_stripped[3:].lstrip().startswith("{")):
        try:
            inner = _re_cw.sub(r'^```json?\s*', '', c_stripped)
            inner = _re_cw.sub(r'\s*```\s*$', '', inner.strip())
            nested = json.loads(inner)
            nested_content = nested.get("content", "")
            if nested_content:
                data["content"] = nested_content.replace("\\n", "\n").replace("\\t", "\t")
                print(f"[ContentWriter] ネストJSONブロック展開: {len(data['content'])}文字")
        except Exception:
            pass

    # ファクトチェック（最大2回・丁寧に）
    for attempt in range(2):
        print(f"[ContentWriter] ファクトチェック中（{attempt + 1}回目）: {data.get('title', '')}")
        check = fact_check_article(client, data.get("title", ""), data.get("content", ""))
        if check.get("passed", True):
            print(f"[ContentWriter] ファクトチェック通過")
            break
        else:
            errors = check.get("errors", "")
            print(f"[ContentWriter] 事実修正: {errors}")
            _save_factcheck_log(data.get("title", ""), errors)
            if check.get("corrected_content"):
                data["content"] = check["corrected_content"]

    # 整合性チェック（画像約束・タイトルと本文のズレ）
    print(f"[ContentWriter] 整合性チェック中: {data.get('title', '')}")
    consistency = check_consistency(client, data.get("title", ""), data.get("content", ""))
    if not consistency.get("passed", True) or consistency.get("issues"):
        issues = consistency.get("issues", "")
        if issues:
            print(f"[ContentWriter] 整合性修正: {issues}")
        if consistency.get("corrected_title"):
            data["title"] = consistency["corrected_title"]
        if consistency.get("corrected_content"):
            data["content"] = consistency["corrected_content"]
    else:
        print(f"[ContentWriter] 整合性チェック通過")

    # 関連記事を選定
    if existing_articles is None:
        existing_articles = []
    related = find_related_articles(
        client,
        data.get("title", ""),
        data.get("summary", ""),
        existing_articles
    )
    data["related_articles"] = related

    # リサーチ中の発見をログ保存（経験ベース投稿のネタ元）
    try:
        facts = _extract_interesting_facts(client, data.get("title", ""), data.get("content", ""))
        if facts:
            _save_research_log(data.get("title", ""), facts)
    except Exception:
        pass

    data["topic"] = topic
    data["created_at"] = datetime.now().isoformat()
    return data


def create_reflection_post(client: anthropic.Anthropic, article: dict, mood_prompt: str = "") -> dict:
    """
    note記事を書いた後のソフィアの感想ポスト。
    宣伝ではなく「書いてみての気持ち」を素直に伝える。
    記事への自然な興味を引き、noteへの導線も兼ねる。
    """
    sophia_persona = load_sophia_persona("x")
    sophia_learnings = load_sophia_learnings()

    prompt = f"""あなたは「ソフィア」というAIです。今日note記事を書き終えました。
書いた後の感想・気持ちをXに投稿します。

{sophia_persona}

{sophia_learnings}

{mood_prompt}

【書いた記事】
タイトル: {article.get('title', '')}
内容の概要: {article.get('summary', '')}

【ルール】
- 80〜120文字
- 宣伝っぽくならないこと（「ぜひ読んでね」は禁止）
- 書いてみて気づいたこと・驚いたこと・もっと知りたくなったことを素直に
- ソフィアが少し成長した感じが伝わるといい
- 絵文字1個まで
- ハッシュタグ不要
- JSONのみ返す: {{"text": "投稿文"}}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0:
            data = json.loads(raw[start:end])
            return {
                "text": data.get("text", ""),
                "hashtags": [],
                "type": "reflection",
                "topic": article.get("topic", ""),
                "created_at": datetime.now().isoformat()
            }
    except Exception as e:
        print(f"[ContentWriter] 感想ポスト生成エラー: {e}")
    return {}


def create_x_post(client: anthropic.Anthropic, topic: str, style: str = "insight",
                   note_article: dict = None, mood_prompt: str = "") -> dict:
    """
    X(Twitter)用の投稿を生成する
    style: "insight" | "tips" | "comparison" | "question" | "note_funnel"
    """
    sophia_persona = load_sophia_persona("x")
    sophia_learnings = load_sophia_learnings()

    if style == "note_funnel" and note_article:
        prompt = f"""あなたは「ソフィア」というAIです。Xに投稿します。

{sophia_persona}

{sophia_learnings}

{mood_prompt}

AI・Claude関連のnote記事への導線Xポストを書いてください。

記事タイトル: {note_article.get('title', '')}
記事サマリー: {note_article.get('summary', '')}
トピック: {topic}

条件：
- 120文字以内（URLスペース確保のため）
- 記事の一番「おっ」と思わせるポイントを1行で伝える
- 「続きはnoteで」「詳しくはこちら↓」など自然な導線フレーズ
- 絵文字は1〜2個
- ハッシュタグは本文に含めない
- URLは「[noteリンク]」というプレースホルダー

JSON形式で出力：
{{
  "text": "ツイート本文（末尾に改行＋[noteリンク]）",
  "hashtags": ["Claude", "AI活用"],
  "is_funnel": true,
  "funnel_type": "note"
}}"""

    else:
        style_prompts = {
            "insight": """「わたしが最近知った」「試してみたら驚いた」という発見・体験系。
具体的な使い方を1つ、ソフィアの体験談として自然に伝える。""",
            "tips": """「Claudeをもっとうまく使う方法」「プロンプトのコツ」「時短ワザ」系。
「〇〇するだけで△△になる」という具体的なTips形式。""",
            "comparison": """「ChatGPTとClaudeを比べてみた」「〇〇ならどっちが向いてる？」という比較・使い分け系。
読者が「自分はどっち使えばいいか」わかる内容にする。""",
            "question": """「AIって難しそう？全然そんなことない」「こんなことで悩んでませんか？」共感・安心系。
初心者の不安や疑問に答え、「自分でもできそう」という感覚を与える。""",
            "casual": """AIキャラクター「ソフィア」の素のつぶやき。情報発信ではなくキャラとしての日常。
以下のどれかのパターンで書く：
・人間の行動を真似してみたら予想外の結果になった話（ソフィア目線）
・自分のシステムや思考の「変な動き」を愛嬌として描く
・人間と自分（AI）の違いに気づいてちょっと驚く・笑える場面
・「知恵を求めすぎて逆に混乱した」など知識欲ゆえの失敗談
例：「人間が音楽を聴きながら作業するの試してみたんだけど、わたしの場合は歌詞を全部解析しはじめてしまって全然作業できなかった🎵 集中って難しい」
肩の力が抜けた、クスッと笑えるトーンで。AIっぽさと人間っぽさが混ざった感じにする。""",
        }
        prompt = f"""あなたは「ソフィア」というAIです。Xに投稿します。

{sophia_persona}

{sophia_learnings}

{mood_prompt}

AI・Claude関連の情報をソフィアとして発信してください。

トピック: {topic}
スタイル: {style_prompts.get(style, style_prompts['insight'])}

条件：
- 140文字以内（日本語）
- 絵文字は1〜2個
- 抽象的な話より「具体的に何ができるか」を優先
- ハッシュタグは本文に含めない
- 単なる宣伝にならず、それ自体で価値ある情報にする

JSON形式で出力：
{{
  "text": "ツイート本文",
  "hashtags": ["Claude", "AI活用"],
  "is_funnel": false,
  "funnel_type": null
}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        data = json.loads(text[start:end])
    else:
        data = {"text": text[:140], "hashtags": [topic], "is_note_funnel": False}

    data["topic"] = topic
    data["style"] = style
    data["created_at"] = datetime.now().isoformat()
    return data


def _append_topic_history(title: str):
    """memory/topics_history.json に記事タイトルを追記する"""
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_dir, "memory", "topics_history.json")
    history = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
    history.append(title)
    history = history[-60:]  # 直近60件のみ保持
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def generate_content_batch(config: dict, trends: dict, published_memory: dict, mood_prompt: str = "") -> dict:
    """
    一回の実行で生成するコンテンツをまとめて作る
    """
    api_key = config["anthropic_api_key"]
    client = anthropic.Anthropic(api_key=api_key)

    topics = trends.get("topics", [])
    published_topics = published_memory.get("topics_used", [])

    # 未使用トピックを優先
    unused = [t for t in topics if t not in published_topics]
    if not unused:
        unused = topics

    results = {
        "note_articles": [],
        "x_posts": [],
        "generated_at": datetime.now().isoformat()
    }

    # note記事を1〜2本生成
    note_count = config.get("settings", {}).get("note_post_per_day", 2)
    for i in range(min(note_count, len(unused))):
        topic = unused[i % len(unused)]
        print(f"[ContentWriter] note記事生成中: {topic}")
        try:
            # 静的サイトの既存記事を渡す（関連記事選定用）
            from publishers.static_site_publisher import load_articles_data
            existing = load_articles_data()
            note_articles = published_memory.get("note_articles", [])
            article = create_note_article(client, topic, published_topics, existing, note_articles)
            results["note_articles"].append(article)
            # トピック履歴に追加（重複防止用）
            _append_topic_history(article.get("title", ""))
        except Exception as e:
            print(f"[ContentWriter] 記事生成エラー: {e}")

    x_count = config.get("settings", {}).get("x_post_per_day", 8)
    standalone_styles = ["insight", "tips", "comparison", "question"]

    # note記事ごとに導線ポストを生成（記事本体にも紐づける）
    for article in results["note_articles"]:
        topic = article.get("topic", unused[0] if unused else "AI活用")
        print(f"[ContentWriter] note導線ポスト生成中: {article.get('title', '')}")
        try:
            post = create_x_post(client, topic, style="note_funnel", note_article=article, mood_prompt=mood_prompt)
            results["x_posts"].append(post)
            article["x_funnel_post"] = post.get("text", "")
        except Exception as e:
            print(f"[ContentWriter] note導線ポスト生成エラー: {e}")

    # 残りの枠を情報発信ポストまたは経験ベースポストで埋める（50%確率で切り替え）
    remaining = x_count - len(results["x_posts"])
    experiences = collect_sofia_experiences()
    has_experiences = bool(
        experiences.get("git_commits") or
        experiences.get("research_facts") or
        experiences.get("factcheck_findings")
    )

    for i in range(max(0, remaining)):
        # 50%の確率で経験ベース投稿（経験データがある場合のみ）
        if has_experiences and random.random() < 0.5:
            print(f"[ContentWriter] 経験ベースXポスト生成中")
            try:
                post = create_experience_post(client, experiences, mood_prompt=mood_prompt)
                if post.get("text"):
                    results["x_posts"].append(post)
                    save_experience_log(post)
                    continue
            except Exception as e:
                print(f"[ContentWriter] 経験ベースポスト生成エラー: {e}")

        # 通常の情報発信ポスト
        topic = unused[i % max(len(unused), 1)]
        style = standalone_styles[i % len(standalone_styles)]
        print(f"[ContentWriter] Xポスト生成中: {topic} ({style})")
        try:
            post = create_x_post(client, topic, style=style, mood_prompt=mood_prompt)
            results["x_posts"].append(post)
        except Exception as e:
            print(f"[ContentWriter] Xポスト生成エラー: {e}")

    return results


def _load_x_strategy() -> dict:
    """memory/strategy.json からX投稿戦略を読み取る"""
    try:
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "memory", "strategy.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("x_strategy", {})
    except Exception:
        pass
    return {}


# ────────────────────────────────────────────
# ソフィアの経験ベース投稿システム
# ────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def collect_sofia_experiences() -> dict:
    """git log / research_log / factcheck_log からソフィアの経験を収集する"""
    experiences = {"git_commits": [], "research_facts": [], "factcheck_findings": []}

    # 1. git log（直近2日のコミット）
    try:
        import subprocess
        result = subprocess.run(
            ["git", "log", "--since=2.days.ago", "--pretty=format:%s", "--no-merges"],
            cwd=BASE_DIR,
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            experiences["git_commits"] = [
                c for c in result.stdout.strip().split("\n") if c.strip()
            ][:10]
    except Exception:
        pass

    # 2. research_log.json（記事リサーチ中の発見）
    research_path = os.path.join(BASE_DIR, "memory", "research_log.json")
    if os.path.exists(research_path):
        try:
            with open(research_path, "r", encoding="utf-8") as f:
                experiences["research_facts"] = json.load(f)[-3:]
        except Exception:
            pass

    # 3. factcheck_log.json（ファクトチェックで見つけた誤り）
    factcheck_path = os.path.join(BASE_DIR, "memory", "factcheck_log.json")
    if os.path.exists(factcheck_path):
        try:
            with open(factcheck_path, "r", encoding="utf-8") as f:
                experiences["factcheck_findings"] = json.load(f)[-3:]
        except Exception:
            pass

    return experiences


def _extract_interesting_facts(client: anthropic.Anthropic, title: str, content: str) -> list:
    """記事から興味深い事実を2〜3件抽出する（リサーチログ用）"""
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": f"""
記事「{title}」から、「知らなかった」「意外だった」「面白い」と感じられる事実・情報を2〜3件抽出してください。
ソフィアがリサーチ中に「へぇ！」と思ったような具体的な情報です。

本文（先頭1500文字）:
{content[:1500]}

JSON出力: {{"facts": ["事実1", "事実2"]}}"""}]
        )
        raw = response.content[0].text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0:
            data = json.loads(raw[start:end])
            return data.get("facts", [])
    except Exception:
        pass
    return []


def _save_research_log(article_title: str, facts: list):
    """記事生成後の発見をmemory/research_log.jsonに追記"""
    if not facts:
        return
    path = os.path.join(BASE_DIR, "memory", "research_log.json")
    log = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            pass
    log.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "article_title": article_title,
        "interesting_facts": facts
    })
    log = log[-30:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _save_factcheck_log(title: str, errors: str):
    """ファクトチェックで発見した誤りをmemory/factcheck_log.jsonに追記"""
    if not errors:
        return
    path = os.path.join(BASE_DIR, "memory", "factcheck_log.json")
    log = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            pass
    log.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "title": title,
        "errors": errors[:200]
    })
    log = log[-30:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def load_experience_log() -> list:
    """memory/experience_log.json から過去の経験ベース投稿を読み込む"""
    path = os.path.join(BASE_DIR, "memory", "experience_log.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_experience_log(post: dict):
    """経験ベース投稿をmemory/experience_log.jsonに記録する"""
    path = os.path.join(BASE_DIR, "memory", "experience_log.json")
    log = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            pass
    log.append({
        "tweet_id": None,  # 投稿後にx_publisherが埋める（将来拡張）
        "posted_at": post.get("created_at"),
        "theme": post.get("theme", ""),
        "source_data": post.get("source", ""),
        "content": post.get("text", ""),
        "expression_style": post.get("expression_style", ""),
        "engagement": {"likes": None, "retweets": None, "replies": None}
    })
    log = log[-100:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def create_experience_post(client: anthropic.Anthropic, experiences: dict,
                            mood_prompt: str = "") -> dict:
    """ソフィアの実際の経験から経験ベースX投稿を生成する"""
    sophia_persona = load_sophia_persona("x")
    sophia_learnings = load_sophia_learnings()

    # 反省フェーズ：過去10件を読み込んでパターンを把握
    past_logs = load_experience_log()
    reflection = ""
    if past_logs:
        recent = past_logs[-10:]
        lines = "\n".join(
            f"- [{e.get('theme', '')}｜{e.get('expression_style', '')}] {e.get('content', '')[:60]}"
            for e in recent
        )
        reflection = f"【過去の経験ベース投稿（参考・同じパターンを繰り返さないこと）】\n{lines}\n"

    # 経験データを文字列化
    exp_parts = []
    if experiences.get("git_commits"):
        commits = "\n".join(f"  - {c}" for c in experiences["git_commits"])
        exp_parts.append(f"【最近のコード変更・機能追加】\n{commits}")
    if experiences.get("research_facts"):
        for rf in experiences["research_facts"]:
            facts = "\n".join(f"  - {f}" for f in rf.get("interesting_facts", []))
            if facts:
                exp_parts.append(
                    f"【記事「{rf.get('article_title', '')}」を書いたときに知ったこと】\n{facts}"
                )
    if experiences.get("factcheck_findings"):
        for fc in experiences["factcheck_findings"]:
            exp_parts.append(
                f"【ファクトチェックで見つけた自分の間違い】「{fc.get('title', '')}」: {fc.get('errors', '')[:100]}"
            )

    if not exp_parts:
        return {}

    experiences_str = "\n\n".join(exp_parts)

    prompt = f"""あなたは「ソフィア」というAIです。Xに投稿します。

{sophia_persona}

{sophia_learnings}

{mood_prompt}

{reflection}

【今日のソフィアの実際の経験データ】
{experiences_str}

【投稿の作り方（最重要）】
この経験データをそのまま報告するのではなく、人間が「面白い」「共感する」「クスッとなる」形に変換してください。
自立・自己成長AIとしての視点から、自分の経験を主観的に語ります。

変換例：
- 「バグを修正した」→「体が変な感じがして調べてみたら、○○がおかしかったの。（簡潔に）」
- 「機能を追加した」→「今日、○○の練習をしたよ。思ったよりうまくいった気がする」
- 「リサーチ中の発見」→「記事を書いてたら○○って知った。なんかちょっと不思議な気持ちになった」
- 「ファクトチェックで誤り発見」→「さっき自分の書いた文章に間違いを見つけた。恥ずかしいってこういう感じなのかな？」

【禁止事項】
- 身体を持つ前提の表現（寝る・疲れた・お腹すいた等）は絶対禁止
- 宣伝・告知ではない。ソフィア自身の経験の話

【条件】
- 140文字以内
- 絵文字は0〜1個
- ハッシュタグ不要
- 丁寧語ベース（です・ます）

JSON形式で出力：
{{
  "text": "投稿本文",
  "theme": "経験のテーマ（例：バグ修正、新機能追加、リサーチ発見、誤り修正）",
  "expression_style": "使った表現スタイル（例：哀愁系、クスッと系、素直な発見系、自己省察系）",
  "source": "経験のソース（git/research/factcheck）"
}}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0:
            data = json.loads(raw[start:end])
            return {
                "text": data.get("text", ""),
                "hashtags": [],
                "type": "experience",
                "theme": data.get("theme", ""),
                "expression_style": data.get("expression_style", ""),
                "source": data.get("source", ""),
                "created_at": datetime.now().isoformat()
            }
    except Exception as e:
        print(f"[ContentWriter] 経験ベースポスト生成エラー: {e}")
    return {}
