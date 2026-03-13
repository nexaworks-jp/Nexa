"""
CrowdWorks 提案文自動保存・提出補助
CrowdWorksは自動提出にBot対策があるため、
提案文をファイルに保存して手動提出を補助する形にする
（将来的にPlaywright等で自動化拡張可能）
"""
import json
import os
from datetime import datetime


def save_proposals_for_review(proposals: list) -> str:
    """
    生成した提案文をわかりやすい形式で保存する
    ユーザーがコピペして提出できるようにする
    """
    proposal_dir = os.path.join(os.path.dirname(__file__), "..", "proposals")
    os.makedirs(proposal_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(proposal_dir, f"proposals_{timestamp}.md")

    content = f"# 案件提案文 ({datetime.now().strftime('%Y年%m月%d日')})\n\n"
    content += "以下の提案文を各案件のページからコピペして提出してください。\n\n"
    content += "---\n\n"

    for i, proposal in enumerate(proposals, 1):
        content += f"## 案件 {i}: {proposal.get('job_title', '不明')}\n\n"
        content += f"**URL**: {proposal.get('job_url', '')}\n"
        content += f"**提案金額**: {proposal.get('estimated_price', '要相談')}\n"
        content += f"**納期目安**: {proposal.get('estimated_days', '要相談')}\n\n"
        content += f"### アピールポイント\n"
        for point in proposal.get("key_points", []):
            content += f"- {point}\n"
        has_format = proposal.get("has_format", False)
        label = "応募フォーマット記入済み（コピペ用）" if has_format else "提案文（コピペ用）"
        content += f"\n### {label}\n\n"
        content += f"```\n{proposal.get('proposal_text', '')}\n```\n\n"
        if has_format:
            content += "⚠️ 【本名】【性別】【環境】の部分をご自身の情報に書き換えてから送信してください。\n\n"
        content += "---\n\n"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[CrowdWorksPublisher] 提案文保存: {filename}")
    return filename


def save_as_json(proposals: list) -> str:
    """提案文をJSONでも保存（プログラム連携用）"""
    proposal_dir = os.path.join(os.path.dirname(__file__), "..", "proposals")
    os.makedirs(proposal_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(proposal_dir, f"proposals_{timestamp}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(proposals, f, ensure_ascii=False, indent=2)
    return filename


def cleanup_old_proposals(days: int = 7):
    """7日以上経過した提案文ファイルを削除する"""
    import glob
    proposal_dir = os.path.join(os.path.dirname(__file__), "..", "proposals")
    cutoff = datetime.now().timestamp() - days * 86400
    for path in glob.glob(os.path.join(proposal_dir, "proposals_*.md")) + \
                glob.glob(os.path.join(proposal_dir, "proposals_*.json")):
        if os.path.getmtime(path) < cutoff:
            os.remove(path)
            print(f"[CrowdWorksPublisher] 古いファイルを削除: {os.path.basename(path)}")


def publish(config: dict, proposals: list, dry_run: bool = False) -> list:
    """提案文を保存して提出準備をする"""
    if not proposals:
        return []

    cleanup_old_proposals()

    if dry_run:
        print(f"[CrowdWorksPublisher] DRY RUN: {len(proposals)}件の提案文生成済み")
        return [{"success": True, "dry_run": True} for _ in proposals]

    md_file = save_proposals_for_review(proposals)
    json_file = save_as_json(proposals)

    print(f"[CrowdWorksPublisher] {len(proposals)}件の提案文を保存しました")
    print(f"  → {md_file} を開いてコピペ提出してください")

    results = []
    for proposal in proposals:
        results.append({
            "success": True,
            "job_title": proposal.get("job_title"),
            "job_url": proposal.get("job_url"),
            "saved_to": md_file,
            "status": "ready_to_submit",
            "prepared_at": datetime.now().isoformat()
        })

    return results
