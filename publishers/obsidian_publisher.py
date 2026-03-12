"""
Obsidian パブリッシャー
生成された記事をObsidian Vaultフォルダに保存する
ObsidianはAPIなし。指定フォルダにmdファイルを書くだけで自動的に反映される。
"""
import os
from datetime import datetime


def publish(config: dict, articles: list, dry_run: bool = False) -> list:
    """記事リストをObsidian Vaultに保存する"""
    vault_path = config.get("obsidian", {}).get("vault_path", "")

    if not vault_path:
        print("[Obsidian] vault_path が未設定。スキップ。")
        return [{"success": False, "reason": "vault_path not set", "title": a.get("title")} for a in articles]

    # Obsidian内の保存フォルダ（デフォルト: Vault直下の "note記事" フォルダ）
    folder = config.get("obsidian", {}).get("folder", "note記事")
    save_dir = os.path.join(vault_path, folder)

    if not dry_run:
        os.makedirs(save_dir, exist_ok=True)

    results = []
    for article in articles:
        title = article.get("title", "untitled")
        # ファイル名に使えない文字を除去
        safe_title = "".join(c for c in title if c not in r'\/:*?"<>|')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_title}.md"
        filepath = os.path.join(save_dir, filename)

        hashtags = article.get("hashtags", [])
        tags_yaml = "\n".join([f"  - {t}" for t in hashtags])
        price = article.get("price", 300)
        topic = article.get("topic", "")
        summary = article.get("summary", "")
        content = article.get("content", "")

        # Obsidian用フロントマター付きMarkdown
        md_content = f"""---
title: "{title}"
tags:
{tags_yaml}
price: {price}
topic: "{topic}"
summary: "{summary}"
created: {datetime.now().strftime("%Y-%m-%d %H:%M")}
published_to: []
---

# {title}

{content}
"""

        if dry_run:
            print(f"[Obsidian] DRY RUN: '{title}' → {filepath}")
            results.append({"success": True, "dry_run": True, "title": title, "path": filepath})
            continue

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)
            print(f"[Obsidian] 保存完了: {filepath}")
            results.append({"success": True, "title": title, "path": filepath})
        except Exception as e:
            print(f"[Obsidian] 保存エラー: {e}")
            results.append({"success": False, "title": title, "error": str(e)})

    return results
