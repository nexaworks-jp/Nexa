"""
note.com 自動投稿パブリッシャー
note.comの非公式APIを使って記事を自動投稿する
"""
import requests
import json
import time
from datetime import datetime


class NotePublisher:
    BASE_URL = "https://note.com"
    API_URL = "https://note.com/api/v1"

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Content-Type": "application/json"
        })
        self.logged_in = False
        self.user_id = None

    def login(self) -> bool:
        """note.comにログイン"""
        try:
            # まずトップページを取得してCSRFトークンを取得
            resp = self.session.get(self.BASE_URL)
            resp.raise_for_status()

            # ログインAPIを呼ぶ
            login_data = {
                "login": self.email,
                "password": self.password
            }
            resp = self.session.post(
                f"{self.API_URL}/sessions",
                json=login_data
            )

            if resp.status_code == 200:
                data = resp.json()
                self.user_id = data.get("data", {}).get("id")
                self.logged_in = True
                print(f"[NotePublisher] ログイン成功: user_id={self.user_id}")
                return True
            else:
                print(f"[NotePublisher] ログイン失敗: {resp.status_code} {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"[NotePublisher] ログインエラー: {e}")
            return False

    def publish_article(self, article: dict, dry_run: bool = False) -> dict:
        """
        記事を投稿する
        article: { "title": str, "content": str, "price": int, "hashtags": list }
        """
        if dry_run:
            print(f"[NotePublisher] DRY RUN: '{article['title']}' (¥{article.get('price', 0)})")
            return {"success": True, "dry_run": True, "title": article["title"]}

        if not self.logged_in:
            if not self.login():
                return {"success": False, "error": "ログイン失敗"}

        try:
            # ハッシュタグをnote形式に変換
            hashtags = article.get("hashtags", [])
            tag_string = " ".join([f"#{tag}" for tag in hashtags])

            # コンテンツにハッシュタグを追加
            full_content = article["content"] + f"\n\n{tag_string}"

            payload = {
                "note": {
                    "name": article["title"],
                    "body": full_content,
                    "status": "published",
                    "price": article.get("price", 0),
                    "limited_check": article.get("price", 0) > 0,
                    "free_body_limit_rate": 30 if article.get("price", 0) > 0 else 100
                }
            }

            resp = self.session.post(
                f"{self.API_URL}/text_notes",
                json=payload
            )

            if resp.status_code in (200, 201):
                data = resp.json()
                note_data = data.get("data", {})
                result = {
                    "success": True,
                    "note_id": note_data.get("id"),
                    "url": note_data.get("noteUrl", ""),
                    "title": article["title"],
                    "price": article.get("price", 0),
                    "published_at": datetime.now().isoformat()
                }
                print(f"[NotePublisher] 投稿成功: {result['url']}")
                return result
            else:
                error_msg = f"HTTP {resp.status_code}: {resp.text[:300]}"
                print(f"[NotePublisher] 投稿失敗: {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            print(f"[NotePublisher] 投稿エラー: {e}")
            return {"success": False, "error": str(e)}

    def save_as_draft(self, article: dict) -> dict:
        """記事をローカルにMarkdownとして保存（フォールバック）"""
        import os
        drafts_dir = "drafts"
        os.makedirs(drafts_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{drafts_dir}/note_{timestamp}.md"

        content = f"""---
title: {article['title']}
price: {article.get('price', 0)}
hashtags: {', '.join(article.get('hashtags', []))}
created_at: {article.get('created_at', '')}
---

# {article['title']}

{article['content']}
"""
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"[NotePublisher] ドラフト保存: {filename}")
        return {"success": True, "saved_to": filename, "title": article["title"]}


def publish(config: dict, articles: list, dry_run: bool = False) -> list:
    """記事リストを投稿する"""
    note_config = config.get("note", {})
    publisher = NotePublisher(
        email=note_config.get("email", ""),
        password=note_config.get("password", "")
    )

    results = []
    for article in articles:
        if note_config.get("email") and note_config.get("email") != "YOUR_NOTE_EMAIL":
            result = publisher.publish_article(article, dry_run=dry_run)
            if not result.get("success") and not dry_run:
                # APIが失敗したらドラフト保存
                result = publisher.save_as_draft(article)
        else:
            # 認証情報未設定 → ドラフト保存
            result = publisher.save_as_draft(article)

        results.append(result)
        time.sleep(2)  # レート制限対策

    return results
