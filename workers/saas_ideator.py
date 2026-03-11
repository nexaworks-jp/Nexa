"""
SaaSアイデア生成 + ランディングページ自動生成
トレンドから売れるWebサービスのアイデアを出し、
LPを自動で作ってVercelにデプロイ可能な形にする
"""
import anthropic
import json
import os
from datetime import datetime


def generate_saas_idea(client: anthropic.Anthropic, trends: dict, existing_ideas: list) -> dict:
    """トレンドから売れそうなSaaSアイデアを生成"""
    trend_topics = ", ".join(trends.get("topics", [])[:8])
    existing = ", ".join([i.get("name", "") for i in existing_ideas[-5:]]) if existing_ideas else "なし"

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": f"""あなたは日本市場に詳しいスタートアップアドバイザーです。
以下のトレンドを見て、すぐに作れて売れるWebサービスのアイデアを1つ考えてください。

【今のトレンド】
{trend_topics}

【既に考えたアイデア（重複避ける）】
{existing}

条件：
- Claude APIを使って実装できる
- 中小企業や個人が月額1000〜5000円で払いたくなるサービス
- シンプルに作れる（LP + APIだけでOK）
- 具体的なターゲット顧客がいる

JSON形式で出力：
{{
  "name": "サービス名",
  "tagline": "一言キャッチコピー（20文字以内）",
  "target": "ターゲット顧客（具体的に）",
  "problem": "解決する課題",
  "solution": "どう解決するか",
  "price_monthly": 2980,
  "features": ["機能1", "機能2", "機能3"],
  "sales_target": "営業先リスト例（業種・規模）",
  "why_now": "なぜ今このサービスが売れるか"
}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        data = json.loads(text[start:end])
    else:
        data = {"name": "AIアシスタント", "tagline": "業務を自動化", "target": "中小企業"}

    data["generated_at"] = datetime.now().isoformat()
    return data


def generate_landing_page(client: anthropic.Anthropic, idea: dict) -> str:
    """SaaSのランディングページHTMLを生成"""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": f"""以下のSaaSサービスのランディングページHTMLを作成してください。

サービス名: {idea.get('name')}
キャッチコピー: {idea.get('tagline')}
ターゲット: {idea.get('target')}
課題: {idea.get('problem')}
解決策: {idea.get('solution')}
月額: ¥{idea.get('price_monthly', 2980):,}
機能: {', '.join(idea.get('features', []))}

要件：
- モダンなデザイン（Tailwind CDN使用）
- コンバージョン最適化（CTA明確）
- 問い合わせフォーム（Google Forms等へのリンク用）
- スマホ対応
- 完全なHTMLファイル（1ファイルで完結）
- 日本語"""
        }]
    )

    return response.content[0].text


def generate_outreach_email(client: anthropic.Anthropic, idea: dict, target_company_type: str) -> dict:
    """営業メールのテンプレートを生成"""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": f"""以下のSaaSサービスの営業メールを書いてください。

サービス名: {idea.get('name')}
サービス概要: {idea.get('tagline')} - {idea.get('solution')}
ターゲット: {target_company_type}
月額料金: ¥{idea.get('price_monthly', 2980):,}

条件：
- 件名と本文をセットで
- 200文字程度（読みやすく）
- スパム判定されない自然な文体
- 無料トライアル or デモの提案を含める
- [会社名][担当者名]などのプレースホルダーを使う

JSON形式で出力：
{{
  "subject": "件名",
  "body": "本文",
  "ps": "追伸（オプション）"
}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    return {"subject": "新サービスのご案内", "body": text[:400], "ps": ""}


def run(config: dict, trends: dict, memory: dict) -> dict:
    """SaaSアイデア生成と営業準備"""
    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    existing_ideas = memory.get("saas_ideas", [])

    print("[SaaSIdeator] SaaSアイデア生成中...")
    idea = generate_saas_idea(client, trends, existing_ideas)
    print(f"[SaaSIdeator] アイデア: {idea.get('name')} - {idea.get('tagline')}")

    # ランディングページ生成
    print("[SaaSIdeator] ランディングページ生成中...")
    lp_html = generate_landing_page(client, idea)

    # LP保存
    lp_dir = os.path.join(os.path.dirname(__file__), "..", "saas_products")
    os.makedirs(lp_dir, exist_ok=True)
    safe_name = idea.get("name", "service").replace(" ", "_")[:20]
    lp_path = os.path.join(lp_dir, f"{safe_name}_lp.html")
    with open(lp_path, "w", encoding="utf-8") as f:
        f.write(lp_html)
    print(f"[SaaSIdeator] LP保存: {lp_path}")

    # 営業メール生成
    print("[SaaSIdeator] 営業メール生成中...")
    email_template = generate_outreach_email(client, idea, idea.get("sales_target", "中小企業"))

    return {
        "idea": idea,
        "lp_path": lp_path,
        "email_template": email_template,
        "generated_at": datetime.now().isoformat()
    }
