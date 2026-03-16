"""
note.com パブリッシャー

投稿優先順位:
1. セッションクッキーでAPI直接投稿（ログイン不要・Bot検知なし）
2. メール/パスワードでAPIログイン → 投稿（通常は失敗するためスキップ可）
3. Playwright（クッキー認証 + headless検知回避）
4. drafts/ に下書き保存（最終フォールバック）
"""
import os
import json
import random
import time
import re as _re
from datetime import datetime


# ==================== 下書きパイプライン ====================

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
    pipeline = _load_pipeline()
    if any(p.get("title") == article.get("title") for p in pipeline):
        return
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


def _load_cookies() -> list:
    cookies_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "note_cookies.json")
    if os.path.exists(cookies_path):
        try:
            with open(cookies_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _retry_pending_drafts(email: str, password: str) -> int:
    """pipeline.jsonのpending記事を1件だけ再投稿試行"""
    pipeline = _load_pipeline()
    success = 0
    updated = False

    for item in pipeline:
        if item.get("status") not in ("pending", "give_up"):
            continue
        if item.get("retry_count", 0) >= 15:
            if item.get("status") != "give_up":
                item["status"] = "give_up"
                updated = True
            continue
        # give_up → pending に復活
        if item.get("status") == "give_up":
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
            if content_lines and content_lines[0].startswith("# "):
                content_lines = content_lines[1:]
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

        # セッションクッキーAPIを最優先で試行
        result = api_post_with_session_cookie(article)
        if not result.get("success") and email and password:
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
    pipeline = _load_pipeline()
    return {
        "pending": sum(1 for p in pipeline if p.get("status") == "pending"),
        "posted": sum(1 for p in pipeline if p.get("status") == "posted"),
        "give_up": sum(1 for p in pipeline if p.get("status") == "give_up"),
        "total": len(pipeline),
    }


# ==================== 下書き保存（フォールバック） ====================

def save_as_draft(article: dict) -> dict:
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


# ==================== 下書き作成・公開の共通ヘルパー ====================

def _content_to_html(text: str) -> str:
    """マークダウン本文をnote.com互換のHTML（<p>タグ）に変換"""
    import html as _html
    paragraphs = text.split("\n\n")
    parts = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        escaped = _html.escape(p).replace("\n", "<br>")
        parts.append(f"<p>{escaped}</p>")
    return "".join(parts) or "<p></p>"


def _session_to_pw_cookies(session) -> list:
    """requestsセッションのクッキーをPlaywright形式に変換"""
    pw = []
    for c in session.cookies:
        domain = (c.domain or "note.com").lstrip(".")
        pw.append({"name": c.name, "value": c.value, "domain": domain, "path": c.path or "/"})
    return pw


def _publish_via_playwright_fetch(session, title: str, content: str, hashtags: list, price: int, user_key: str) -> dict:
    """
    Playwrightのブラウザ内fetch()でAPIを呼び出して投稿。
    ブラウザがeditor.note.comのJSを実行した後にfetchを発行するため、
    note_gql_auth_tokenクッキーが自動的に付与される。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False, "reason": "playwright not installed"}

    pw_cookies = _session_to_pw_cookies(session)
    if not pw_cookies:
        return {"success": False, "reason": "no cookies in session"}

    free_body = _content_to_html(content)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        context.add_init_script("delete Object.getPrototypeOf(navigator).webdriver;")
        context.add_cookies(pw_cookies)
        page = context.new_page()

        # ネットワーク監視: Set-CookieでJWT発行元を特定 + APIレスポンスを記録
        api_responses = {}
        def on_response(response):
            sc = response.headers.get("set-cookie", "")
            if "note_gql_auth_token" in sc:
                print(f"[NoteAPI-PW] JWT set-cookie from: {response.url}")
            if "note.com/api/" in response.url and response.status < 400:
                try:
                    api_responses[response.url.split("?")[0]] = response.json()
                except Exception:
                    pass
        page.on("response", on_response)

        # APIリクエストのみ記録（静的アセット除外）
        api_reqs = []
        def on_request(req):
            url = req.url
            if "note.com/api/" in url or ("note.com" in url and "_next" not in url and ".js" not in url and ".css" not in url and ".png" not in url):
                api_reqs.append(f"{req.method} {url[:120]}")
        page.on("request", on_request)

        try:
            # note.com/notes/new から入る（自然なフロー）→ editor.note.com にリダイレクト
            page.goto("https://note.com/notes/new", timeout=30000)
            # エディター要素またはタイムアウトまで待機
            try:
                page.wait_for_selector('[contenteditable="true"]', timeout=10000)
                print("[NoteAPI-PW] エディター検出")
            except Exception:
                page.wait_for_timeout(6000)

            # JWT確認
            all_cookies = context.cookies()
            jwt_present = any(c["name"] == "note_gql_auth_token" for c in all_cookies)
            print(f"[NoteAPI-PW] JWT={'あり' if jwt_present else 'なし'} cookies={[c['name'] for c in all_cookies]}")

            # APIリクエスト一覧
            print(f"[NoteAPI-PW] APIリクエスト({len(api_reqs)}件): {api_reqs}")

            # current_user レスポンス内容（JWTがここに含まれているか確認）
            for url, body in api_responses.items():
                if "current_user" in url or "token" in url:
                    print(f"[NoteAPI-PW] {url}: {str(body)[:400]}")

            # document.cookie と localStorage を確認（JWTの格納場所特定）
            doc_cookie = page.evaluate("() => document.cookie")
            ls_data = page.evaluate("() => { try { return JSON.stringify(Object.fromEntries(Object.keys(localStorage).map(k=>[k, localStorage.getItem(k)]))).slice(0,500); } catch(e) { return String(e); } }")
            print(f"[NoteAPI-PW] document.cookie: {doc_cookie[:300]}")
            print(f"[NoteAPI-PW] localStorage: {ls_data[:300]}")

            # ブラウザのfetch()でAPI呼び出し（editor.note.com originで実行）
            result = page.evaluate("""
                async ([title, freeBody, hashtags, price]) => {
                    const h = {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json, text/plain, */*',
                        'X-Requested-With': 'XMLHttpRequest'
                    };
                    const opts = (method, body) => ({method, headers: h, credentials: 'include', body: JSON.stringify(body)});

                    // Step1: 空の下書き作成
                    const r1 = await fetch('https://note.com/api/v1/text_notes', opts('POST', {template_key: null}));
                    const t1 = await r1.text();
                    if (!r1.ok) return {success: false, step: 1, status: r1.status, body: t1.slice(0, 300)};
                    const d1 = JSON.parse(t1);
                    const noteId = String(d1.data?.id || '');
                    const noteKey = String(d1.data?.key || noteId);
                    if (!noteId) return {success: false, step: 1, reason: 'no id', body: t1.slice(0, 200)};

                    // Step2: 本文保存
                    const r2 = await fetch(
                        `https://note.com/api/v1/text_notes/draft_save?id=${noteId}&is_temp_saved=true`,
                        opts('POST', {name: title, free_body: freeBody, body_length: freeBody.length, index: false, is_lead_form: false})
                    );
                    if (!r2.ok) return {success: false, step: 2, status: r2.status, body: (await r2.text()).slice(0, 300)};

                    // Step3: 公開
                    const r3 = await fetch(`https://note.com/api/v1/text_notes/${noteId}`,
                        opts('PUT', {name: title, free_body: freeBody, pay_body: '', price, hashtags,
                                     body_length: freeBody.length, index: false, send_notifications_flag: true})
                    );
                    const t3 = await r3.text();
                    if (r3.ok) {
                        const d3 = JSON.parse(t3);
                        return {success: true, status: r3.status, noteId, noteKey,
                                url: d3.data?.noteUrl || d3.data?.url || ''};
                    }
                    return {success: false, step: 3, status: r3.status, body: t3.slice(0, 400)};
                }
            """, [title, free_body, list(hashtags[:10]), price])

            print(f"[NoteAPI-PW] fetch結果: {result}")

            if result.get("success"):
                note_url = result.get("url") or f"https://note.com/{user_key}/n/{result.get('noteKey', '')}"
                return {"success": True, "url": note_url, "title": title, "is_draft": False}
            return {"success": False, "reason": f"step{result.get('step',3)} {result.get('status')} {result.get('body', result.get('reason', ''))[:200]}"}

        except Exception as e:
            print(f"[NoteAPI-PW] エラー: {e}")
            return {"success": False, "reason": str(e)}
        finally:
            browser.close()


def _create_and_publish(session, title: str, content: str, hashtags: list, price: int, user_key: str) -> dict:
    """
    ブラウザのDevToolsで確認した実際のAPIフローで投稿:
    1. POST /api/v1/text_notes          → 空の下書き作成 → note_id 取得
    2. POST /api/v1/text_notes/draft_save?id=...   → 本文(free_body=HTML)・タイトル保存
    3. PUT  /api/v1/text_notes/{id}     → 公開（200 OK）
    """
    free_body = _content_to_html(content)

    # ── Step 1: 空の下書き作成 ──
    r1 = session.post(
        "https://note.com/api/v1/text_notes",
        json={"template_key": None},
        timeout=30,
    )
    print(f"[NoteAPI] Step1 下書き作成: {r1.status_code} {r1.text[:150]}")
    if r1.status_code not in (200, 201):
        return {"success": False, "reason": f"Step1 failed: {r1.status_code}"}

    d1 = r1.json().get("data", r1.json())
    note_id  = str(d1.get("id") or "")
    note_key = str(d1.get("key") or note_id)
    if not note_id:
        return {"success": False, "reason": f"Step1: note_id not found in {r1.text[:200]}"}
    print(f"[NoteAPI] note_id={note_id} note_key={note_key}")

    # ── Step 2: 本文・タイトルを下書き保存 ──
    r2 = session.post(
        f"https://note.com/api/v1/text_notes/draft_save?id={note_id}&is_temp_saved=true",
        json={
            "name": title,
            "free_body": free_body,
            "body_length": len(content),
            "index": False,
            "is_lead_form": False,
        },
        timeout=30,
    )
    print(f"[NoteAPI] Step2 下書き保存: {r2.status_code} {r2.text[:150]}")
    if r2.status_code not in (200, 201):
        return {"success": False, "reason": f"Step2 failed: {r2.status_code}"}

    # ── Step 3: PUT で公開（最小ペイロード → 成功しなければ拡張ペイロード）──
    # まず最小ペイロードで試行（422の原因を特定しやすくする）
    minimal_payload = {
        "name": title,
        "free_body": free_body,
        "pay_body": "",
        "price": price,
        "hashtags": list(hashtags[:10]),
        "body_length": len(content),
        "index": False,
        "send_notifications_flag": True,
    }
    r3 = session.put(
        f"https://note.com/api/v1/text_notes/{note_id}",
        json=minimal_payload,
        timeout=30,
    )
    print(f"[NoteAPI] Step3 公開(PUT/minimal): {r3.status_code} {r3.text[:400]}")

    if r3.status_code not in (200, 201):
        # 拡張ペイロードで再試行
        full_payload = {
            **minimal_payload,
            "is_refund": False,
            "limited": False,
            "separator": None,
            "author_ids": [],
            "circle_permissions": [],
            "disable_comment": False,
            "discount_campaigns": [],
            "exclude_ai_learning_reward": False,
            "exclude_from_creator_top": False,
            "image_keys": [],
            "magazine_ids": [],
            "magazine_keys": [],
        }
        r3 = session.put(
            f"https://note.com/api/v1/text_notes/{note_id}",
            json=full_payload,
            timeout=30,
        )
        print(f"[NoteAPI] Step3 公開(PUT/full): {r3.status_code} {r3.text[:400]}")

    if r3.status_code in (200, 201):
        d3 = r3.json().get("data", r3.json())
        note_url = (
            d3.get("noteUrl") or d3.get("url") or
            f"https://note.com/{user_key}/n/{note_key}"
        )
        print(f"[NoteAPI] 投稿成功: {note_url}")
        return {"success": True, "url": note_url, "title": title, "is_draft": False}

    return {"success": False, "reason": f"Step3 PUT failed: {r3.status_code} {r3.text[:400]}"}


# ==================== 方法1: セッションクッキーで直接API投稿（最優先） ====================

def api_post_with_session_cookie(article: dict) -> dict:
    """
    note_cookies.json の _note_session_v5 を使って直接API投稿。
    ログイン不要。Playwright不要。Bot検知なし。
    クッキーが有効な限り（有効期限まで）動作する。
    """
    import requests

    cookies_list = _load_cookies()
    session_cookie = next((c for c in cookies_list if c["name"] == "_note_session_v5"), None)
    if not session_cookie:
        return {"success": False, "reason": "no _note_session_v5 cookie in note_cookies.json"}

    title = article.get("title", "")
    content = article.get("content", "")
    hashtags = article.get("hashtags", [])
    price = article.get("price", 0)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "X-Requested-With": "XMLHttpRequest",  # RailsのCSRF保護をAJAXとして回避
        "Referer": "https://note.com/",
        "Origin": "https://note.com",
    })

    # 全クッキーをセッションに設定
    for c in cookies_list:
        domain = c.get("domain", ".note.com").lstrip(".")
        session.cookies.set(c["name"], c["value"], domain=domain)

    try:
        # ホームページにアクセスしてCSRFトークンとurlnameを取得
        home_resp = session.get("https://note.com/", timeout=15)

        csrf_token = ""
        user_key = ""

        # CSRFトークン取得: Set-Cookieヘッダー
        for c in session.cookies:
            if c.name.lower() in ("xsrf-token", "_csrf_token", "csrf-token", "csrftoken"):
                csrf_token = c.value
                break

        # CSRFトークン取得: HTMLのmetaタグ
        if not csrf_token:
            m = _re.search(r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)', home_resp.text)
            if m:
                csrf_token = m.group(1)

        # CSRFトークン取得: __NEXT_DATAのJSON内
        if not csrf_token:
            m = _re.search(r'"csrfToken"\s*:\s*"([^"]+)"', home_resp.text)
            if m:
                csrf_token = m.group(1)

        if csrf_token:
            session.headers["X-CSRF-Token"] = csrf_token

        # urlname取得（__NEXT_DATAのJSON内）
        m = _re.search(r'"urlname"\s*:\s*"([^"]+)"', home_resp.text)
        if m:
            user_key = m.group(1)

        print(f"[NoteAPI-Session] CSRF={'あり' if csrf_token else 'なし'} user={user_key or '不明'} session={session_cookie['value'][:8]}...")

        # Playwrightのブラウザfetch()で投稿（editor originで全クッキー付き）
        result = _publish_via_playwright_fetch(session, title, content, hashtags, price, user_key)
        if result.get("success"):
            return result

        print(f"[NoteAPI-Session] Playwright fetch失敗: {result.get('reason', '')[:100]} → requests fallback")
        # フォールバック: requestsでPUT
        session.headers.update({"Origin": "https://editor.note.com", "Referer": "https://editor.note.com/"})
        return _create_and_publish(session, title, content, hashtags, price, user_key)

    except Exception as e:
        print(f"[NoteAPI-Session] エラー: {e}")
        return {"success": False, "reason": str(e)}


# ==================== 方法2: メール/パスワードでAPIログイン → 投稿 ====================

def api_post(article: dict, email: str, password: str) -> dict:
    """
    メール/パスワードでAPIログインして投稿。
    note.comのSPA構造上CSRFトークン取得が難しく、422が頻発する。
    api_post_with_session_cookieが失敗した場合のフォールバック。
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
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://note.com/",
        "Origin": "https://note.com",
    })

    try:
        import json as _json

        # ルートページ → ログインページの順でCSRFを取得
        session.get("https://note.com/", timeout=15)
        login_page = session.get("https://note.com/login", timeout=15)

        csrf_token = ""
        # meta タグ
        for line in login_page.text.splitlines():
            if "csrf-token" in line and "content=" in line:
                m = _re.search(r'content="([^"]+)"', line)
                if m:
                    csrf_token = m.group(1)
                    break
        # __NEXT_DATA__
        if not csrf_token:
            nd_match = _re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', login_page.text, _re.DOTALL)
            if nd_match:
                try:
                    nd = _json.loads(nd_match.group(1))
                    csrf_token = (
                        nd.get("props", {}).get("csrfToken") or
                        nd.get("props", {}).get("pageProps", {}).get("csrfToken") or ""
                    )
                except Exception:
                    pass
        # Cookie
        if not csrf_token:
            for c in session.cookies:
                if "csrf" in c.name.lower() or "xsrf" in c.name.lower():
                    csrf_token = c.value
                    break

        if csrf_token:
            session.headers.update({"X-CSRF-Token": csrf_token})

        print(f"[NoteAPI] CSRF={'あり' if csrf_token else 'なし'} でログイン試行")

        # ログイン試行（エンドポイント × ペイロード）
        login_resp = None
        logged_in = False
        for endpoint in [
            "https://note.com/api/v1/sessions",
            "https://note.com/api/v1/sessions/sign_in",
        ]:
            for payload in [
                {"login": email, "password": password},
                {"email_or_nickname": email, "password": password},
                {"email": email, "password": password},
                {"user": {"email": email, "password": password}},
            ]:
                r = session.post(endpoint, json=payload, timeout=15)
                key = list(payload.keys())[0]
                ep = endpoint.split("/")[-1]
                print(f"[NoteAPI] ログイン試行 {ep} payload={key}: {r.status_code}")
                if r.status_code in (200, 201):
                    login_resp = r
                    logged_in = True
                    break
                login_resp = r
            if logged_in:
                break

        if not logged_in:
            print(f"[NoteAPI] ログイン失敗: {login_resp.status_code} body={login_resp.text[:200]}")
            return {"success": False, "reason": f"login failed: {login_resp.status_code}"}

        login_data = login_resp.json()
        user_key = (
            login_data.get("data", {}).get("urlname") or
            login_data.get("data", {}).get("id") or ""
        )
        print(f"[NoteAPI] ログイン成功: {user_key}")

        # ログイン後CSRFを更新
        for c in login_resp.cookies:
            if "csrf" in c.name.lower() or "xsrf" in c.name.lower():
                session.headers["X-CSRF-Token"] = c.value

        # Playwrightのブラウザfetch()で投稿（editor originで全クッキー付き）
        result = _publish_via_playwright_fetch(session, title, content, hashtags, price, user_key)
        if result.get("success"):
            return result

        print(f"[NoteAPI] Playwright fetch失敗: {result.get('reason', '')[:100]} → requests fallback")
        # フォールバック: requestsでPUT
        session.headers.update({"Origin": "https://editor.note.com", "Referer": "https://editor.note.com/"})
        return _create_and_publish(session, title, content, hashtags, price, user_key)

    except Exception as e:
        print(f"[NoteAPI] エラー: {e}")
        return {"success": False, "reason": str(e)}


# ==================== 方法3: Playwright（最終手段） ====================

def auto_post_with_playwright(article: dict, note_email: str, note_password: str) -> dict:
    """
    PlaywrightでNote.comに記事を自動投稿する。
    headless検知回避のため --disable-blink-features=AutomationControlled を使用。
    クッキー認証を優先し、失敗時はフォームログインにフォールバック。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[NotePublisher] playwright未インストール")
        return {"success": False, "reason": "playwright not installed"}

    title = article.get("title", "")
    content = article.get("content", "")
    price = article.get("price", 0)
    hashtags = article.get("hashtags", [])

    print(f"[NotePublisher] Playwright投稿開始: '{title}'")

    cookies = _load_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",  # headless検知回避
                "--disable-dev-shm-usage",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )
        # webdriver フラグを削除（headless検知回避）
        context.add_init_script("delete Object.getPrototypeOf(navigator).webdriver;")

        if cookies:
            context.add_cookies(cookies)
            print(f"[NotePublisher] クッキー設定 ({len(cookies)}件)")

        page = context.new_page()

        try:
            editor_sel = '[contenteditable="true"]'

            # ホームページに先にアクセスしてセッションを安定化
            page.goto("https://note.com/", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_timeout(2000)

            # ログイン状態の確認
            is_logged_in = "/login" not in page.url and page.locator('a[href*="/login"]').count() == 0
            print(f"[NotePublisher] ログイン状態: {'済み' if is_logged_in else '未ログイン'}")

            if not is_logged_in:
                # フォームログイン
                page.goto("https://note.com/login", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)
                page.wait_for_timeout(3000)

                email_sel = (
                    'input[name="email"], input[name="email_or_nickname"], '
                    'input[type="email"], input[autocomplete="email"]'
                )
                try:
                    page.wait_for_selector(email_sel, timeout=20000)
                    page.fill(email_sel, note_email)
                    page.fill('input[type="password"]', note_password)
                    page.click('button[type="submit"]')
                    page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
                    page.wait_for_load_state("networkidle", timeout=15000)
                    print("[NotePublisher] フォームログイン成功")
                except Exception as e:
                    print(f"[NotePublisher] フォームログイン失敗: {e}")
                    _save_debug_screenshot(page, "login_fail")
                    browser.close()
                    return {"success": False, "reason": f"form login failed: {e}"}

            # 新規ノートページへ移動
            page.goto("https://note.com/notes/new", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)

            # エディター出現を待機（最大60秒）
            editor_loaded = False
            for wait_sec in [15, 15, 20, 10]:  # 合計60秒、リロードを挟む
                try:
                    page.wait_for_selector(editor_sel, state="visible", timeout=wait_sec * 1000)
                    editor_loaded = True
                    print("[NotePublisher] エディター読み込み完了")
                    break
                except Exception:
                    print(f"[NotePublisher] エディター待機中 ({wait_sec}秒経過)... リロード")
                    page.reload()
                    page.wait_for_load_state("networkidle", timeout=20000)

            if not editor_loaded:
                _save_debug_screenshot(page, "editor_not_loaded")
                # エレメント情報をデバッグ出力
                try:
                    info = page.evaluate("""() => ({
                        url: location.href,
                        title: document.title,
                        bodyText: document.body.innerText.slice(0, 200),
                        editables: document.querySelectorAll('[contenteditable]').length,
                    })""")
                    print(f"[NotePublisher] ページ情報: {info}")
                except Exception:
                    pass
                browser.close()
                return {"success": False, "reason": "editor never loaded", "title": title}

            page.wait_for_timeout(1000)

            # ========== タイトル入力 ==========
            title_filled = False
            for sel in [
                '[placeholder*="タイトル"]',
                '[data-placeholder*="タイトル"]',
                '.editor-title textarea',
                'textarea[class*="title"]',
            ]:
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
                try:
                    title_ce = page.locator(editor_sel).first
                    title_ce.click()
                    title_ce.fill(title)
                    title_filled = True
                    print("[NotePublisher] タイトル入力完了 (contenteditable)")
                except Exception:
                    pass

            page.wait_for_timeout(500)

            # ========== 本文入力 ==========
            body_filled = False
            for sel in [
                '.editor-body [contenteditable="true"]',
                '[data-placeholder*="本文"]',
                '.ProseMirror',
                '[class*="editor-content"] [contenteditable]',
            ]:
                try:
                    page.wait_for_selector(sel, timeout=3000)
                    page.click(sel)
                    page.evaluate("""(txt) => {
                        const editors = document.querySelectorAll('[contenteditable="true"]');
                        let bodyEditor = null;
                        for (const ed of editors) {
                            const rect = ed.getBoundingClientRect();
                            if (rect.height > 100) { bodyEditor = ed; break; }
                        }
                        if (!bodyEditor) bodyEditor = editors[editors.length - 1];
                        if (bodyEditor) {
                            bodyEditor.focus();
                            document.execCommand('selectAll', false, null);
                            document.execCommand('insertText', false, txt);
                        }
                    }""", content)
                    body_filled = True
                    print("[NotePublisher] 本文入力完了")
                    break
                except Exception:
                    continue

            if not body_filled:
                page.keyboard.press("Tab")
                page.wait_for_timeout(500)
                page.keyboard.type(content[:3000], delay=5)
                print("[NotePublisher] 本文入力完了 (keyboard fallback)")

            page.wait_for_timeout(3000)

            # ========== 公開ボタン ==========
            _save_debug_screenshot(page, "before_publish")

            # 全ボタン情報をログ出力
            try:
                btns = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('button, [role="button"]')).map(b => ({
                        text: b.innerText.trim().slice(0, 30),
                        cls: b.className.slice(0, 50),
                    }));
                }""")
                print(f"[NotePublisher] ボタン一覧: {btns[:15]}")
            except Exception:
                pass

            publish_clicked = False
            for sel in [
                'button:has-text("公開する")',
                'button:has-text("投稿する")',
                'button:has-text("公開設定")',
                'button:has-text("公開")',
                '[role="button"]:has-text("公開する")',
                '[role="button"]:has-text("公開")',
                '[data-testid*="publish"]',
                'header button:last-child',
            ]:
                try:
                    page.locator(sel).first.click(timeout=5000)
                    publish_clicked = True
                    print(f"[NotePublisher] 公開ボタンクリック ({sel})")
                    break
                except Exception:
                    continue

            if not publish_clicked:
                _save_debug_screenshot(page, "no_publish_btn")
                browser.close()
                return {"success": False, "reason": "publish button not found", "title": title}

            page.wait_for_timeout(2000)

            # ========== 公開設定モーダル ==========
            if price > 0:
                try:
                    page.locator('text=有料').first.click(timeout=3000)
                    page.locator('input[type="number"]').first.fill(str(price))
                except Exception:
                    pass

            for tag in hashtags[:5]:
                try:
                    tag_input = page.locator('input[placeholder*="タグ"], input[placeholder*="ハッシュタグ"]').first
                    tag_input.fill(tag)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(300)
                except Exception:
                    break

            # 最終公開ボタン（モーダル内）
            for sel in [
                'button:has-text("公開する")',
                'button:has-text("投稿する")',
                '[class*="modal"] button:has-text("公開")',
            ]:
                try:
                    page.locator(sel).last.click(timeout=5000)
                    print("[NotePublisher] 最終公開ボタンクリック")
                    break
                except Exception:
                    continue

            page.wait_for_timeout(4000)
            current_url = page.url
            print(f"[NotePublisher] 投稿完了: {current_url}")
            browser.close()

            return {"success": True, "url": current_url, "title": title, "is_draft": False}

        except Exception as e:
            print(f"[NotePublisher] 投稿エラー: {e}")
            _save_debug_screenshot(page)
            browser.close()
            return {"success": False, "reason": str(e), "title": title}


def _save_debug_screenshot(page, prefix="error"):
    try:
        debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "drafts", "debug")
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

    試行順:
    1. セッションクッキーでAPI直接投稿（ログイン不要）
    2. メール/パスワードAPIログイン
    3. Playwright（headless検知回避済み）
    4. drafts/ に下書き保存
    """
    results = []
    note_cfg = config.get("note", {})
    email = note_cfg.get("email", "")
    password = note_cfg.get("password", "")
    use_playwright = config.get("settings", {}).get("note_auto_post", True)

    for article in articles:
        if dry_run:
            print(f"[NotePublisher] DRY RUN: '{article.get('title')}' (¥{article.get('price', 0)})")
            results.append({"success": True, "dry_run": True, "title": article.get("title")})
            continue

        # 1. セッションクッキーAPI（最優先・ログイン不要）
        result = api_post_with_session_cookie(article)
        if result.get("success"):
            results.append(result)
            continue
        print(f"[NotePublisher] セッションAPIの結果: {result.get('reason', '不明')}")

        # 2. メール/パスワードAPIログイン
        if email and password:
            result = api_post(article, email, password)
            if result.get("success"):
                results.append(result)
                continue
            print("[NotePublisher] メール/パスワードAPI失敗 → Playwrightへ")

            # 3. Playwright
            if use_playwright:
                wait = random.randint(0, 60)
                print(f"[NotePublisher] {wait}秒待機後Playwright投稿")
                time.sleep(wait)
                result = auto_post_with_playwright(article, email, password)
                if result.get("success"):
                    results.append(result)
                    continue

        # 4. 下書き保存
        print("[NotePublisher] 全手段失敗 → 下書き保存")
        result = save_as_draft(article)
        results.append(result)

    return results
