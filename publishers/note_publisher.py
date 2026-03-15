"""
note.com パブリッシャー
1. requests APIで投稿（Bot検知なし・Playwright不要）
2. 失敗時はPlaywright（クッキー認証 → フォームログイン）にフォールバック
3. それも失敗したら drafts/ に下書き保存
"""
import os
import json
import random
import time
from datetime import datetime


# ==================== 下書きパイプライン（cc-secretaryのinbox概念） ====================

def _pipeline_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "drafts", "pipeline.json")


def _load_pipeline() -> list:
    path = _pipeline_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_pipeline(pipeline: list):
    path = _pipeline_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pipeline, f, ensure_ascii=False, indent=2)


def _register_draft(article: dict, draft_path: str):
    """下書きをpipeline.jsonに登録する"""
    pipeline = _load_pipeline()
    if any(p.get("title") == article.get("title") for p in pipeline):
        return  # 重複スキップ
    pipeline.append({
        "title": article.get("title", ""),
        "hashtags": article.get("hashtags", []),
        "price": article.get("price", 0),
        "draft_path": draft_path,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "retry_count": 0,
    })
    _save_pipeline(pipeline)
    pending = sum(1 for p in pipeline if p.get("status") == "pending")
    print(f"[NotePublisher] パイプライン登録 (未投稿{pending}件)")


def _retry_pending_drafts(email: str, password: str) -> int:
    """pipeline.jsonのpending記事を1件だけAPI再投稿試行"""
    pipeline = _load_pipeline()
    success = 0
    updated = False

    for item in pipeline:
        if item.get("status") not in ("pending", "give_up"):
            continue
        if item.get("retry_count", 0) >= 10:
            # 10回超えたら完全諦め（以前は5回だったが延長）
            if item.get("status") != "give_up":
                item["status"] = "give_up"
                updated = True
            continue
        # give_up → pending に復活させて再試行（ログイン修正後のリカバリー用）
        if item.get("status") == "give_up" and item.get("retry_count", 0) < 10:
            item["status"] = "pending"
            updated = True

        draft_path = item.get("draft_path", "")
        if not os.path.exists(draft_path):
            item["status"] = "missing"
            updated = True
            continue

        # mdファイルから本文を再構築
        try:
            with open(draft_path, "r", encoding="utf-8") as f:
                md = f.read()
            lines = md.split("\n")
            # frontmatter(---)を除いたタイトル行以降を本文とする
            in_front = False
            content_lines = []
            skip_front = True
            for line in lines:
                if skip_front and line.strip() == "---":
                    in_front = not in_front
                    if not in_front:
                        skip_front = False
                    continue
                if not skip_front:
                    content_lines.append(line)
            # 先頭の # タイトル行を除く
            if content_lines and content_lines[0].startswith("# "):
                content_lines = content_lines[1:]
            # X導線セクション(---)以降を除く
            sep = next((i for i, l in enumerate(content_lines) if l.strip() == "---"), len(content_lines))
            body = "\n".join(content_lines[:sep]).strip()
        except Exception:
            item["retry_count"] = item.get("retry_count", 0) + 1
            updated = True
            break

        article = {
            "title": item["title"],
            "content": body,
            "hashtags": item.get("hashtags", []),
            "price": item.get("price", 0),
        }

        result = api_post(article, email, password)
        item["retry_count"] = item.get("retry_count", 0) + 1
        updated = True

        if result.get("success"):
            item["status"] = "posted"
            item["posted_at"] = datetime.now().isoformat()
            item["url"] = result.get("url", "")
            print(f"[NotePublisher] 下書き再投稿成功: {item['title'][:30]}")
            success += 1
        else:
            print(f"[NotePublisher] 下書き再投稿失敗({item['retry_count']}回目): {item['title'][:30]}")
        break  # 1実行1件のみ

    if updated:
        _save_pipeline(pipeline)
    return success


def get_pipeline_status() -> dict:
    """パイプライン状況サマリーを返す"""
    pipeline = _load_pipeline()
    return {
        "pending": sum(1 for p in pipeline if p.get("status") == "pending"),
        "posted": sum(1 for p in pipeline if p.get("status") == "posted"),
        "give_up": sum(1 for p in pipeline if p.get("status") == "give_up"),
        "total": len(pipeline),
    }


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
    _register_draft(article, filename)
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


# ==================== requests APIによる投稿（メイン手段） ====================

def api_post(article: dict, email: str, password: str) -> dict:
    """
    requestsライブラリでnote.comの内部APIを直接叩いて投稿する。
    Playwright不要・Bot検知なし。
    """
    import requests

    title = article.get("title", "")
    content = article.get("content", "")
    hashtags = article.get("hashtags", [])
    price = article.get("price", 0)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://note.com/",
        "Origin": "https://note.com",
    })

    try:
        import re as _re
        import json as _json
        # ========== ログイン ==========
        # まずルートページを訪問してセッション・Cookieを初期化（Next.js SPA対応）
        session.get("https://note.com/", timeout=15)

        # CSRFトークン取得（SPAのため複数手段で試みる）
        login_page = session.get("https://note.com/login", timeout=15)
        csrf_token = ""

        # Method 1: <meta name="csrf-token"> タグ（従来型Rails）
        for line in login_page.text.splitlines():
            if 'csrf-token' in line and 'content=' in line:
                m = _re.search(r'content="([^"]+)"', line)
                if m:
                    csrf_token = m.group(1)
                    break

        # Method 2: __NEXT_DATA__ JSONからCSRFを取得（Next.js SPA）
        if not csrf_token:
            nd_match = _re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', login_page.text, _re.DOTALL)
            if nd_match:
                try:
                    nd = _json.loads(nd_match.group(1))
                    csrf_token = (
                        nd.get("props", {}).get("csrfToken") or
                        nd.get("props", {}).get("pageProps", {}).get("csrfToken") or
                        nd.get("query", {}).get("csrfToken") or ""
                    )
                except Exception:
                    pass

        # Method 3: CookieからCSRFを取得（XSRF-TOKEN等）
        if not csrf_token:
            for c in session.cookies:
                if "csrf" in c.name.lower() or "xsrf" in c.name.lower():
                    csrf_token = c.value
                    break

        # Method 4: Cookieにtokenが含まれる場合（広めに探す）
        if not csrf_token:
            for c in session.cookies:
                if "token" in c.name.lower() and len(c.value) > 10:
                    csrf_token = c.value
                    break

        if csrf_token:
            session.headers.update({"X-CSRF-Token": csrf_token, "X-XSRF-TOKEN": csrf_token})
        print(f"[NoteAPI] CSRFトークン: {'取得済み' if csrf_token else '未取得'} ({csrf_token[:20] if csrf_token else ''})")

        # ログインAPI（エンドポイント × ペイロード形式を総当たり）
        login_resp = None
        login_endpoints = [
            "https://note.com/api/v1/sessions",          # 元々動いていたエンドポイント（/sign_inなし）
            "https://note.com/api/v1/sessions/sign_in",  # 3月14日から試みているエンドポイント
            "https://note.com/api/v2/sessions/sign_in",
            "https://note.com/api/v1/users/sign_in",
        ]
        login_payloads = [
            {"user": {"email": email, "password": password}},   # Devise標準形式
            {"email_or_nickname": email, "password": password},
            {"login": email, "password": password},
            {"email": email, "password": password},
        ]
        logged_in = False
        for endpoint in login_endpoints:
            for login_payload in login_payloads:
                r = session.post(endpoint, json=login_payload, timeout=15)
                key = list(login_payload.keys())[0]
                print(f"[NoteAPI] ログイン試行 endpoint={endpoint.split('/')[-2]+'/'+endpoint.split('/')[-1]} payload={key}: {r.status_code}")
                if r.status_code in (200, 201):
                    login_resp = r
                    logged_in = True
                    break
                login_resp = r
            if logged_in:
                break

        if not logged_in or login_resp.status_code not in (200, 201):
            print(f"[NoteAPI] ログイン失敗: {login_resp.status_code} body={login_resp.text[:200]}")
            return {"success": False, "reason": f"login failed: {login_resp.status_code}"}

        login_data = login_resp.json()
        if login_data.get("error"):
            err_msg = login_data["error"].get("message", str(login_data["error"]))
            print(f"[NoteAPI] ログイン失敗: {err_msg}")
            return {"success": False, "reason": f"login error: {err_msg}"}
        # urlname または id で識別（APIバージョンによって異なる）
        user_key = (
            login_data.get("data", {}).get("urlname") or
            login_data.get("data", {}).get("id") or
            login_data.get("data", {}).get("user", {}).get("urlname") or
            ""
        )
        if not user_key:
            print(f"[NoteAPI] ログイン失敗: user_key取得できず。レスポンス={str(login_data)[:200]}")
            return {"success": False, "reason": "login failed: no user_key"}
        print(f"[NoteAPI] ログイン成功: {user_key}")

        # CSRFトークン更新（ログイン後に変わる場合あり）
        me_resp = session.get("https://note.com/api/v1/stats/pv?filter=all", timeout=10)
        for c in login_resp.cookies:
            if "csrf" in c.name.lower() or "token" in c.name.lower():
                session.headers.update({"X-CSRF-Token": c.value})

        # ========== 下書き作成 ==========
        tag_list = [{"name": t} for t in hashtags[:10]]
        draft_payload = {
            "title": title,
            "body": content,
            "hashtag_notes_attributes": tag_list,
            "price": price,
            "is_paid_only_body": False,
        }
        draft_resp = session.post(
            "https://note.com/api/v3/drafts",
            json=draft_payload,
            timeout=30
        )
        if draft_resp.status_code not in (200, 201):
            print(f"[NoteAPI] 下書き作成失敗: {draft_resp.status_code} {draft_resp.text[:200]}")
            return {"success": False, "reason": f"draft failed: {draft_resp.status_code}"}

        draft_data = draft_resp.json()
        note_key = draft_data.get("data", {}).get("key", "") or draft_data.get("key", "")
        print(f"[NoteAPI] 下書き作成成功: key={note_key}")

        # ========== 公開 ==========
        publish_resp = session.post(
            f"https://note.com/api/v2/notes/{note_key}/publish",
            json={"visibility": "public"},
            timeout=15
        )
        if publish_resp.status_code not in (200, 201):
            print(f"[NoteAPI] 公開失敗: {publish_resp.status_code} {publish_resp.text[:200]}")
            return {"success": False, "reason": f"publish failed: {publish_resp.status_code}"}

        note_url = f"https://note.com/{user_key}/n/{note_key}"
        pub_data = publish_resp.json()
        if pub_data.get("data", {}).get("noteUrl"):
            note_url = pub_data["data"]["noteUrl"]

        print(f"[NoteAPI] 投稿成功: {note_url}")
        return {"success": True, "url": note_url, "title": title, "is_draft": False}

    except Exception as e:
        print(f"[NoteAPI] エラー: {e}")
        return {"success": False, "reason": str(e)}


def _load_cookies() -> list:
    """note_cookies.jsonからクッキーを読み込む"""
    cookies_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "note_cookies.json")
    if os.path.exists(cookies_path):
        with open(cookies_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def auto_post_with_playwright(article: dict, note_email: str, note_password: str) -> dict:
    """
    PlaywrightでNote.comに記事を自動投稿する。
    クッキー認証を優先し、失敗時はフォームログインにフォールバック。
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

    cookies = _load_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP"
        )

        # クッキー認証（優先）
        if cookies:
            context.add_cookies(cookies)
            print(f"[NotePublisher] クッキー認証を試みます ({len(cookies)}件)")

        page = context.new_page()

        try:
            # ========== 認証 ==========
            editor_sel = '[contenteditable="true"]'

            if cookies:
                # クッキーがある場合: 直接投稿ページへ
                page.goto("https://note.com/notes/new", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)

                if "/login" in page.url:
                    # URLが/loginに変わった場合のみフォームログインへ
                    print("[NotePublisher] クッキー期限切れ (URLリダイレクト) → フォームログインへ")
                    cookies = []
                else:
                    # エディター読み込みを40秒待機（note.com SPA は初回ロードに時間がかかる）
                    try:
                        page.wait_for_selector(editor_sel, state='visible', timeout=40000)
                        print("[NotePublisher] クッキー認証成功 + エディター確認OK")
                    except Exception:
                        # まだ出ない場合はリロードして再試行
                        print("[NotePublisher] エディター未ロード → ページリロードして再試行")
                        page.reload()
                        page.wait_for_load_state("networkidle", timeout=20000)
                        try:
                            page.wait_for_selector(editor_sel, state='visible', timeout=30000)
                            print("[NotePublisher] リロード後エディター確認OK")
                        except Exception:
                            print("[NotePublisher] リロード後もエディター未ロード → 続行")

            if not cookies:
                # フォームログイン
                page.goto("https://note.com/login", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)
                page.wait_for_timeout(3000)  # SPA描画待機

                email_sel = (
                    'input[name="email"], input[name="email_or_nickname"], '
                    'input[type="email"], input[autocomplete="email"], '
                    'input[placeholder*="メール"], input[placeholder*="アドレス"], '
                    'input[placeholder="メールアドレス"], '
                    'input[placeholder*="mail"], input[placeholder*="note ID"], '
                    'input[placeholder*="ID"]'
                )
                page.wait_for_selector(email_sel, timeout=20000)
                page.fill(email_sel, note_email)

                pwd_sel = 'input[name="password"], input[type="password"]'
                page.fill(pwd_sel, note_password)

                page.click('button[type="submit"]')
                page.wait_for_url(lambda url: "note.com" in url and "/login" not in url, timeout=20000)
                page.wait_for_load_state("networkidle", timeout=15000)
                print("[NotePublisher] フォームログイン成功")

                page.goto("https://note.com/notes/new", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)
                # フォームログイン後もエディター出現を待機
                try:
                    page.wait_for_selector(editor_sel, state='visible', timeout=30000)
                    print("[NotePublisher] フォームログイン後エディター確認OK")
                except Exception:
                    print("[NotePublisher] フォームログイン後もエディター未ロード → 続行")

            # ========== 投稿ページ確認 ==========
            if "notes/new" not in page.url:
                page.goto("https://note.com/notes/new", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)
                try:
                    page.wait_for_selector(editor_sel, state='visible', timeout=20000)
                except Exception:
                    pass
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

            # 入力後に再度エディターが安定するまで待機
            page.wait_for_timeout(3000)

            # ========== 公開ボタンクリック ==========
            # 公開ボタン前にスクリーンショット（デバッグ用）
            _save_debug_screenshot(page, prefix="before_publish")

            # ページ上のボタン・クリッカブル要素を全てログ出力（デバッグ）
            try:
                btns = page.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll('button, [role="button"], a[href="#"]'));
                    return els.map(b => ({
                        tag: b.tagName,
                        text: b.innerText.trim().slice(0, 30),
                        cls: b.className.slice(0, 60),
                        disabled: b.disabled || false
                    }));
                }""")
                print(f"[NotePublisher] クリッカブル要素: {btns[:15]}")
            except Exception:
                pass

            publish_btn_selectors = [
                'button:has-text("公開する")',
                'button:has-text("投稿する")',
                'button:has-text("公開設定")',
                'button:has-text("公開")',
                '[role="button"]:has-text("公開する")',
                '[role="button"]:has-text("公開")',
                '[role="button"]:has-text("投稿")',
                'button:has-text("Publish")',
                '[class*="publish"]:has-text("公開")',
                '[data-testid*="publish"]',
                '[data-testid*="submit"]',
                'header button:last-child',
                'header [role="button"]:last-child',
            ]
            publish_clicked = False
            for sel in publish_btn_selectors:
                try:
                    page.locator(sel).first.click(timeout=5000)
                    publish_clicked = True
                    print(f"[NotePublisher] 公開ボタンクリック ({sel})")
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


def _save_debug_screenshot(page, prefix="error"):
    """デバッグ用スクリーンショットを保存"""
    try:
        debug_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "drafts", "debug"
        )
        os.makedirs(debug_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(debug_dir, f"{prefix}_{ts}.png")
        page.screenshot(path=path)
        print(f"[NotePublisher] スクリーンショット: {path}")
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

        if email and password:
            # 1. requestsでAPIを直接呼び出す（Bot検知なし）
            result = api_post(article, email, password)
            if result.get("success"):
                results.append(result)
                continue
            print("[NotePublisher] API投稿失敗 → Playwrightにフォールバック")

            # 2. Playwright（クッキー or フォームログイン）
            if use_playwright:
                wait = random.randint(0, 120)
                print(f"[NotePublisher] 投稿まで {wait//60}分{wait%60}秒 待機（ランダム）")
                time.sleep(wait)
                result = auto_post_with_playwright(article, email, password)
                if result.get("success"):
                    results.append(result)
                    continue
            print("[NotePublisher] 自動投稿失敗 → 下書き保存にフォールバック")

        result = save_as_draft(article)
        results.append(result)

    return results
