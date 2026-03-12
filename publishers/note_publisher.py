"""
note.com パブリッシャー
Playwrightでnote.comに自動投稿する。
失敗時は drafts/ に下書き保存してオーナーに手動投稿を依頼する。
"""
import os
from datetime import datetime


# ==================== 下書き保存（フォールバック） ====================

def save_as_draft(article: dict) -> dict:
    """記事をdrafts/に保存する（X導線ポストも一緒に出力）"""
    drafts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "drafts")
    os.makedirs(drafts_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(drafts_dir, f"note_{timestamp}.md")

    hashtags_str = ", ".join(article.get("hashtags", []))
    hashtag_text = " ".join([f"#{t}" for t in article.get("hashtags", [])])
    price = article.get("price", 0)
    x_funnel = article.get("x_funnel_post", "")

    x_section = ""
    if x_funnel:
        x_section = f"""
---

## X導線ポスト（記事投稿後にURLを差し替えてXに投稿）

```
{x_funnel}
```

※ `[noteリンク]` を実際の記事URLに差し替えてください
"""

    content = f"""---
title: {article.get('title', '')}
price: {price}
hashtags: {hashtags_str}
created_at: {article.get('created_at', '')}
---

# {article.get('title', '')}

{article.get('content', '')}

---
※ ハッシュタグ: {hashtag_text}
※ 価格設定: ¥{price}（有料部分は本文60〜70%地点に設定）
※ 画像を挿入してからnoteに投稿してください
{x_section}"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[NotePublisher] 下書き保存: {filename}")
    return {
        "success": True,
        "saved_to": filename,
        "title": article.get("title", ""),
        "price": price,
        "is_draft": True
    }


# ==================== Playwright自動投稿 ====================

def auto_post_with_playwright(article: dict, note_email: str, note_password: str) -> dict:
    """
    PlaywrightでNote.comに記事を自動投稿する。
    戻り値: { "success": bool, "url": str, "title": str }
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[NotePublisher] playwright未インストール。pip install playwright && playwright install chromium")
        return {"success": False, "reason": "playwright not installed"}

    title = article.get("title", "")
    content = article.get("content", "")
    price = article.get("price", 300)
    hashtags = article.get("hashtags", [])

    print(f"[NotePublisher] Playwright投稿開始: '{title}'")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            # ログイン
            page.goto("https://note.com/login", timeout=30000)
            page.wait_for_selector('input[name="email"]', timeout=10000)
            page.fill('input[name="email"]', note_email)
            page.fill('input[name="password"]', note_password)
            page.click('button[type="submit"]')
            page.wait_for_url("https://note.com/**", timeout=15000)
            print("[NotePublisher] ログイン成功")

            # 新規記事作成ページへ
            page.goto("https://note.com/notes/new", timeout=30000)
            page.wait_for_selector(".editor-title", timeout=15000)

            # タイトル入力
            page.click(".editor-title")
            page.fill(".editor-title", title)

            # 本文入力（note.comはcontenteditable）
            page.click(".editor-body [contenteditable]")
            page.keyboard.type(content, delay=10)

            # ハッシュタグ
            for tag in hashtags[:5]:
                # ハッシュタグ入力エリアを探す
                try:
                    hashtag_input = page.locator('input[placeholder*="タグ"], input[placeholder*="ハッシュタグ"]').first
                    hashtag_input.fill(f"#{tag}")
                    page.keyboard.press("Enter")
                except Exception:
                    pass

            # 有料設定（¥300）
            if price > 0:
                try:
                    # 「有料」ボタンまたは価格設定を探す
                    page.locator('text=有料').first.click(timeout=5000)
                    price_input = page.locator('input[type="number"]').first
                    price_input.fill(str(price))
                except Exception:
                    print("[NotePublisher] 有料設定スキップ（要素が見つからず）")

            # 公開ボタン
            page.locator('button:has-text("公開"), button:has-text("投稿")').first.click(timeout=10000)
            page.wait_for_timeout(3000)

            # 公開完了後URLを取得
            current_url = page.url
            print(f"[NotePublisher] 投稿完了: {current_url}")
            browser.close()
            return {"success": True, "url": current_url, "title": title}

        except Exception as e:
            print(f"[NotePublisher] Playwright投稿エラー: {e}")
            # スクリーンショットを保存（デバッグ用）
            try:
                debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "drafts", "debug")
                os.makedirs(debug_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                page.screenshot(path=os.path.join(debug_dir, f"error_{timestamp}.png"))
            except Exception:
                pass
            browser.close()
            return {"success": False, "reason": str(e), "title": title}


# ==================== メイン投稿関数 ====================

def publish(config: dict, articles: list, dry_run: bool = False) -> list:
    """
    記事リストをnote.comに投稿する。
    Playwright自動投稿を試み、失敗したら下書き保存にフォールバック。
    """
    results = []
    note_cfg = config.get("note", {})
    email = note_cfg.get("email", "")
    password = note_cfg.get("password", "")
    use_playwright = config.get("settings", {}).get("note_auto_post", False)

    for article in articles:
        if dry_run:
            print(f"[NotePublisher] DRY RUN: '{article.get('title')}' (¥{article.get('price', 0)})")
            results.append({"success": True, "dry_run": True, "title": article.get("title")})
            continue

        # Playwright自動投稿（設定で有効化されている場合）
        if use_playwright and email and password:
            result = auto_post_with_playwright(article, email, password)
            if result.get("success"):
                results.append(result)
                continue
            else:
                print(f"[NotePublisher] 自動投稿失敗。下書き保存にフォールバック。")

        # 下書き保存（フォールバック）
        result = save_as_draft(article)
        results.append(result)

    return results
