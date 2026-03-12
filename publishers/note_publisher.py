"""
note.com パブリッシャー
Playwrightでnote.comに自動投稿する。
失敗時は drafts/ に下書き保存してオーナーに手動投稿を依頼する。
"""
import os
import json
from datetime import datetime


# ==================== 下書き保存（フォールバック） ====================

def save_as_draft(article: dict) -> dict:
    """記事をdrafts/に保存する（自動投稿失敗時のフォールバック）"""
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
※ 価格設定: ¥{price}
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

def _inject_text(page, selector: str, text: str):
    """contenteditable要素にテキストを確実に入力する"""
    page.evaluate(f"""(sel, txt) => {{
        const el = document.querySelector(sel);
        if (!el) return;
        el.focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('insertText', false, txt);
    }}""", selector, text)


def auto_post_with_playwright(article: dict, note_email: str, note_password: str) -> dict:
    """
    PlaywrightでNote.comに記事を自動投稿する。
    戻り値: { "success": bool, "url": str, "title": str }
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("[NotePublisher] playwright未インストール")
        return {"success": False, "reason": "playwright not installed"}

    title = article.get("title", "")
    content = article.get("content", "")
    price = article.get("price", 0)
    hashtags = article.get("hashtags", [])

    print(f"[NotePublisher] 自動投稿開始: '{title}'")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP"
        )
        page = context.new_page()

        try:
            # ========== ログイン ==========
            page.goto("https://note.com/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)

            # メール入力
            email_sel = 'input[name="email"], input[type="email"], input[placeholder*="メール"]'
            page.wait_for_selector(email_sel, timeout=10000)
            page.fill(email_sel, note_email)

            # パスワード入力
            pwd_sel = 'input[name="password"], input[type="password"]'
            page.fill(pwd_sel, note_password)

            # ログインボタン
            page.click('button[type="submit"]')
            page.wait_for_url("**/note.com/**", timeout=20000)
            page.wait_for_load_state("networkidle", timeout=15000)
            print("[NotePublisher] ログイン成功")

            # ========== 新規記事作成 ==========
            page.goto("https://note.com/notes/new", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_timeout(2000)

            # ========== タイトル入力 ==========
            title_selectors = [
                '.editor-title textarea',
                '[placeholder*="タイトル"]',
                '[data-placeholder*="タイトル"]',
                'textarea[class*="title"]',
                '.note-title textarea',
            ]
            title_filled = False
            for sel in title_selectors:
                try:
                    page.wait_for_selector(sel, timeout=3000)
                    page.click(sel)
                    page.fill(sel, title)
                    title_filled = True
                    print(f"[NotePublisher] タイトル入力完了 ({sel})")
                    break
                except Exception:
                    continue

            if not title_filled:
                # contenteditable の場合
                try:
                    title_ce = page.locator('[contenteditable="true"]').first
                    title_ce.click()
                    title_ce.fill(title)
                    title_filled = True
                    print("[NotePublisher] タイトル入力完了 (contenteditable)")
                except Exception:
                    pass

            page.wait_for_timeout(500)

            # ========== 本文入力 ==========
            # Tabキーで本文エリアへ移動するか、直接クリック
            body_selectors = [
                '.editor-body [contenteditable="true"]',
                '[data-placeholder*="本文"]',
                '[placeholder*="本文"]',
                '.ProseMirror',
                '[class*="editor-content"] [contenteditable]',
                '[class*="body"] [contenteditable]',
            ]
            body_filled = False
            for sel in body_selectors:
                try:
                    page.wait_for_selector(sel, timeout=3000)
                    page.click(sel)
                    # execCommandで高速入力
                    page.evaluate("""(txt) => {
                        const editors = document.querySelectorAll('[contenteditable="true"]');
                        let bodyEditor = null;
                        for (const ed of editors) {
                            const ph = ed.getAttribute('data-placeholder') || '';
                            if (ph.includes('本文') || ph.includes('テキスト') || ph === '') {
                                const rect = ed.getBoundingClientRect();
                                if (rect.height > 100) {
                                    bodyEditor = ed;
                                    break;
                                }
                            }
                        }
                        if (!bodyEditor) bodyEditor = editors[editors.length - 1];
                        if (bodyEditor) {
                            bodyEditor.focus();
                            document.execCommand('selectAll', false, null);
                            document.execCommand('insertText', false, txt);
                        }
                    }""", content)
                    body_filled = True
                    print(f"[NotePublisher] 本文入力完了")
                    break
                except Exception:
                    continue

            if not body_filled:
                # キーボード入力にフォールバック
                page.keyboard.press("Tab")
                page.wait_for_timeout(500)
                page.keyboard.type(content[:3000], delay=5)
                print("[NotePublisher] 本文入力完了 (keyboard fallback)")

            page.wait_for_timeout(1000)

            # ========== 公開ボタンクリック ==========
            publish_btn_selectors = [
                'button:has-text("公開する")',
                'button:has-text("投稿する")',
                'button:has-text("公開")',
                '[class*="publish"]:has-text("公開")',
            ]
            publish_clicked = False
            for sel in publish_btn_selectors:
                try:
                    page.locator(sel).first.click(timeout=5000)
                    publish_clicked = True
                    print("[NotePublisher] 公開ボタンクリック")
                    break
                except Exception:
                    continue

            if not publish_clicked:
                print("[NotePublisher] 公開ボタンが見つからず投稿失敗")
                _save_debug_screenshot(page)
                browser.close()
                return {"success": False, "reason": "publish button not found", "title": title}

            page.wait_for_timeout(2000)

            # ========== 公開設定モーダル ==========
            # 価格設定（有料記事の場合）
            if price > 0:
                try:
                    # 有料ボタンを探してクリック
                    page.locator('text=有料, label:has-text("有料")').first.click(timeout=5000)
                    page.wait_for_timeout(500)
                    price_input = page.locator('input[type="number"], input[placeholder*="価格"]').first
                    price_input.fill(str(price))
                    print(f"[NotePublisher] 価格設定: ¥{price}")
                except Exception:
                    print("[NotePublisher] 価格設定スキップ")

            # ハッシュタグ設定
            for tag in hashtags[:5]:
                try:
                    tag_input = page.locator(
                        'input[placeholder*="タグ"], input[placeholder*="ハッシュタグ"]'
                    ).first
                    tag_input.fill(tag)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(300)
                except Exception:
                    break

            # 最終公開ボタン（モーダル内）
            final_btn_selectors = [
                'button:has-text("公開する")',
                'button:has-text("投稿する")',
                '[class*="modal"] button:has-text("公開")',
                '[class*="dialog"] button:has-text("公開")',
            ]
            for sel in final_btn_selectors:
                try:
                    page.locator(sel).last.click(timeout=5000)
                    print("[NotePublisher] 最終公開ボタンクリック")
                    break
                except Exception:
                    continue

            # 完了待機・URL取得
            page.wait_for_timeout(4000)
            current_url = page.url
            print(f"[NotePublisher] 投稿完了: {current_url}")
            browser.close()

            return {
                "success": True,
                "url": current_url,
                "title": title,
                "is_draft": False
            }

        except Exception as e:
            print(f"[NotePublisher] 投稿エラー: {e}")
            _save_debug_screenshot(page)
            browser.close()
            return {"success": False, "reason": str(e), "title": title}


def _save_debug_screenshot(page):
    """エラー時のデバッグ用スクリーンショットを保存"""
    try:
        debug_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "drafts", "debug"
        )
        os.makedirs(debug_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(debug_dir, f"error_{ts}.png")
        page.screenshot(path=path)
        print(f"[NotePublisher] デバッグスクリーンショット: {path}")
    except Exception:
        pass


# ==================== メイン投稿関数 ====================

def publish(config: dict, articles: list, dry_run: bool = False) -> list:
    """
    記事リストをnote.comに投稿する。
    自動投稿を試み、失敗したら下書き保存にフォールバック。
    """
    results = []
    note_cfg = config.get("note", {})
    email = note_cfg.get("email", "")
    password = note_cfg.get("password", "")
    # デフォルトtrue（メール・パスワードが設定されていれば自動投稿）
    use_playwright = config.get("settings", {}).get("note_auto_post", True)

    for article in articles:
        if dry_run:
            print(f"[NotePublisher] DRY RUN: '{article.get('title')}' (¥{article.get('price', 0)})")
            results.append({"success": True, "dry_run": True, "title": article.get("title")})
            continue

        if use_playwright and email and password:
            result = auto_post_with_playwright(article, email, password)
            if result.get("success"):
                results.append(result)
                continue
            print("[NotePublisher] 自動投稿失敗 → 下書き保存にフォールバック")

        result = save_as_draft(article)
        results.append(result)

    return results
