"""
提案文ライター
案件の内容を読んで、Claudeが最適な提案文を自動生成する
"""
import anthropic
import json
from datetime import datetime


def write_proposal(client: anthropic.Anthropic, job: dict) -> dict:
    """
    案件に対する提案文を生成する
    """
    title = job.get("title", "")
    description = job.get("description", "")
    budget = job.get("budget", "要相談")
    platform = job.get("platform", "crowdworks")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": f"""あなたはクラウドソーシングで仕事を受注するフリーランスです。
以下の案件に対して、採用されやすい提案文を書いてください。

【案件タイトル】
{title}

【案件詳細】
{description if description else "（詳細は案件ページを参照）"}

【予算】
{budget}

【プラットフォーム】
{platform}

提案文の条件：
- 300〜500文字（長すぎず短すぎず）
- 具体的な実績や経験を自然に含める（AIアシスト可能なスキルを強調）
- 依頼者の課題を理解していることを示す
- 納期・品質への配慮を示す
- 自然な日本語で、テンプレート感を出さない
- 末尾に「ぜひ一度ご相談ください」等の一言

JSON形式で出力：
{{
  "proposal_text": "提案文本文",
  "estimated_price": "提案金額（例：15,000円）",
  "estimated_days": "納期目安（例：3日）",
  "key_points": ["アピールポイント1", "アピールポイント2"]
}}"""
        }]
    )

    text = response.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        data = json.loads(text[start:end])
    else:
        data = {
            "proposal_text": text[:500],
            "estimated_price": "要相談",
            "estimated_days": "3日",
            "key_points": ["迅速対応", "高品質"]
        }

    data["job_id"] = job.get("job_id")
    data["job_title"] = title
    data["platform"] = platform
    data["job_url"] = job.get("url", "")
    data["created_at"] = datetime.now().isoformat()
    return data


def generate_proposals(config: dict, suitable_jobs: list) -> list[dict]:
    """複数の案件に対して提案文を生成する"""
    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    proposals = []

    for job in suitable_jobs[:3]:  # 1回の実行で最大3件
        print(f"[ProposalWriter] 提案文生成: {job.get('title', '')[:40]}")
        try:
            proposal = write_proposal(client, job)
            proposals.append(proposal)
        except Exception as e:
            print(f"[ProposalWriter] エラー: {e}")

    return proposals
