"""
note.comのセッションクッキーをキャプチャするツール。

使い方:
  python tools/capture_note_cookies.py

ブラウザが開くので手動でログインし、Enterを押してください。
note_cookies.json が生成されるので、その内容を GitHub Secret 'NOTE_COOKIES' に登録してください。
"""
import json
import os
import sys

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwrightが必要です: pip install playwright && playwright install chromium")
        sys.exit(1)

    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "note_cookies.json")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()

        print("[1] ブラウザを開いています...")
        page.goto("https://note.com/login")

        print("[2] ブラウザでnote.comにログインしてください。")
        print("    ログイン完了後、このターミナルでEnterを押してください...")
        input("    → Enterで続行: ")

        # ログイン確認
        if "/login" in page.url:
            print("⚠ まだログインページにいます。ログインしてからEnterを押してください。")
            input("    → Enterで続行: ")

        cookies = context.cookies()
        browser.close()

    # note.com関連のクッキーのみ絞り込む
    note_cookies = [c for c in cookies if "note.com" in c.get("domain", "")]
    if not note_cookies:
        note_cookies = cookies  # フォールバック: 全クッキー

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(note_cookies, f, ensure_ascii=False, indent=2)

    print(f"\n✅ クッキーを保存しました: {output_path} ({len(note_cookies)}件)")
    print("\n次のステップ:")
    print("  1. note_cookies.json の内容をすべてコピー")
    print("  2. GitHub → Settings → Secrets → Actions → New repository secret")
    print("  3. Name: NOTE_COOKIES")
    print("  4. Value: コピーした内容を貼り付けて保存")
    print("\n⚠ note_cookies.json はGitにコミットしないでください（.gitignoreに追加済み）")

if __name__ == "__main__":
    main()
