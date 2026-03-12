"""
静的サイト生成パブリッシャー
記事から静的HTMLを生成し docs/ フォルダに保存する。
GitHub Pages で無料公開できる。
"""
import os
import json
import re
from datetime import datetime


DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
ARTICLES_DIR = os.path.join(DOCS_DIR, "articles")
DATA_FILE = os.path.join(DOCS_DIR, "articles.json")


# ==================== CSS ====================

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "Hiragino Sans", "Noto Sans JP", sans-serif;
  font-size: 16px;
  line-height: 1.8;
  color: #333;
  background: #fafafa;
}
.container { max-width: 800px; margin: 0 auto; padding: 0 16px; }
header {
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  padding: 16px 0;
  position: sticky;
  top: 0;
  z-index: 10;
}
header .container { display: flex; align-items: center; gap: 16px; }
header h1 { font-size: 18px; }
header a { text-decoration: none; color: #333; }
main { padding: 40px 0 80px; }
footer { text-align: center; padding: 32px 0; color: #999; font-size: 13px; border-top: 1px solid #e8e8e8; }

/* 記事一覧 */
.article-list { display: flex; flex-direction: column; gap: 0; }
.article-card {
  background: #fff;
  border-bottom: 1px solid #eeeeee;
  padding: 24px 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}
.article-card h2 { font-size: 18px; margin-bottom: 8px; line-height: 1.5; }
.article-card h2 a { text-decoration: none; color: #222; }
.article-card h2 a:hover { color: #4a90e2; }
.article-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 8px; }
.article-summary { color: #666; font-size: 14px; margin-top: 6px; }
.tag {
  font-size: 11px;
  background: #f0f8ff;
  color: #4a90e2;
  padding: 2px 8px;
  border-radius: 99px;
}
.date { font-size: 12px; color: #aaa; }
.price-badge {
  background: #ff6b35;
  color: #fff;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
  white-space: nowrap;
  flex-shrink: 0;
}
.free-badge {
  background: #41c9b4;
  color: #fff;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
  white-space: nowrap;
  flex-shrink: 0;
}

/* 記事詳細 */
.article-header { margin-bottom: 32px; }
.article-header h1 { font-size: 26px; line-height: 1.5; margin-bottom: 16px; }
.article-body { background: #fff; padding: 32px; border-radius: 8px; }
.article-body h2 { font-size: 20px; margin: 32px 0 12px; padding-bottom: 8px; border-bottom: 2px solid #f0f0f0; }
.article-body h3 { font-size: 17px; margin: 24px 0 8px; }
.article-body p { margin-bottom: 16px; }
.article-body ul, .article-body ol { padding-left: 24px; margin-bottom: 16px; }
.article-body li { margin-bottom: 6px; }
.article-body strong { font-weight: bold; }
.article-body code {
  background: #f4f4f4;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 14px;
}
.paid-wall {
  background: #f9f9f9;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 40px 32px;
  text-align: center;
  margin-top: 48px;
}
.paid-wall h3 { font-size: 18px; margin-bottom: 12px; }
.paid-wall p { color: #666; font-size: 14px; margin-bottom: 24px; }
.btn-note {
  display: inline-block;
  background: #41c9b4;
  color: #fff;
  padding: 12px 32px;
  border-radius: 4px;
  text-decoration: none;
  font-weight: bold;
  font-size: 15px;
}
.btn-note:hover { opacity: 0.85; }
.breadcrumb { font-size: 13px; color: #999; margin-bottom: 24px; }
.breadcrumb a { color: #4a90e2; text-decoration: none; }
.back-link { margin-top: 48px; }
.back-link a { color: #4a90e2; text-decoration: none; font-size: 14px; }
"""


# ==================== HTML変換 ====================

def markdown_to_html(text: str) -> str:
    """最小限のMarkdown→HTML変換"""
    # コードブロック
    text = re.sub(r'```[\w]*\n(.*?)```', lambda m: f'<pre><code>{m.group(1)}</code></pre>', text, flags=re.DOTALL)
    # 見出し
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    # 太字
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # インラインコード
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    # 番号付きリスト
    text = re.sub(r'(?:^\d+\. .+$\n?)+', lambda m: '<ol>' + re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', m.group(0), flags=re.MULTILINE) + '</ol>', text, flags=re.MULTILINE)
    # 箇条書き
    text = re.sub(r'(?:^[-*] .+$\n?)+', lambda m: '<ul>' + re.sub(r'^[-*] (.+)$', r'<li>\1</li>', m.group(0), flags=re.MULTILINE) + '</ul>', text, flags=re.MULTILINE)
    # 段落（連続する通常テキスト）
    paragraphs = text.split('\n\n')
    result = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith('<'):
            result.append(p)
        else:
            p = p.replace('\n', '<br>')
            result.append(f'<p>{p}</p>')
    return '\n'.join(result)


# ==================== ページ生成 ====================

def generate_article_page(article: dict) -> str:
    """記事詳細ページのHTMLを生成"""
    title = article.get("title", "")
    content = article.get("content", "")
    price = article.get("price", 0)
    hashtags = article.get("hashtags", [])
    date_str = article.get("created_at", "")
    note_url = article.get("note_url", "https://note.com/youth_waster")
    article_id = article.get("id", "")

    try:
        date_display = datetime.fromisoformat(date_str).strftime("%Y年%m月%d日")
    except Exception:
        date_display = ""

    # 有料ラインで分割（最初の "---" を境界とする簡易実装）
    free_html = markdown_to_html(content)
    paid_wall_html = ""
    if price > 0:
        # 全体の60%あたりで分割（段落単位）
        paragraphs = [p for p in content.split('\n\n') if p.strip()]
        split_idx = max(1, int(len(paragraphs) * 0.6))
        free_part = '\n\n'.join(paragraphs[:split_idx])
        free_html = markdown_to_html(free_part)
        paid_wall_html = f"""
<div class="paid-wall">
  <h3>続きはnoteで読めます</h3>
  <p>応用テクニック・実践的な使い方は有料部分（¥{price}）に収録されています。</p>
  <a class="btn-note" href="{note_url}" target="_blank" rel="noopener">noteで続きを読む →</a>
</div>"""

    tags_html = "".join([f'<span class="tag">#{t}</span>' for t in hashtags])
    price_badge = f'<span class="price-badge">¥{price}</span>' if price > 0 else '<span class="free-badge">無料</span>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | Claudeの使い方</title>
  <meta name="description" content="{article.get('summary', title)}">
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <header>
    <div class="container">
      <h1><a href="../index.html">Claudeの使い方 | AI初心者ガイド</a></h1>
    </div>
  </header>
  <main>
    <div class="container">
      <div class="breadcrumb">
        <a href="../index.html">トップ</a> &gt; {title}
      </div>
      <div class="article-header">
        <h1>{title}</h1>
        <div class="article-meta">
          <span class="date">{date_display}</span>
          {tags_html}
          {price_badge}
        </div>
      </div>
      <div class="article-body">
        {free_html}
        {paid_wall_html}
      </div>
      <div class="back-link">
        <a href="../index.html">← 記事一覧に戻る</a>
      </div>
    </div>
  </main>
  <footer>
    <p>© 2026 Claudeの使い方 | AI初心者ガイド</p>
  </footer>
</body>
</html>"""


def generate_index_page(articles: list) -> str:
    """記事一覧ページのHTMLを生成"""
    cards_html = ""
    for article in sorted(articles, key=lambda a: a.get("created_at", ""), reverse=True):
        title = article.get("title", "")
        article_id = article.get("id", "")
        summary = article.get("summary", "")
        price = article.get("price", 0)
        hashtags = article.get("hashtags", [])
        date_str = article.get("created_at", "")

        try:
            date_display = datetime.fromisoformat(date_str).strftime("%Y年%m月%d日")
        except Exception:
            date_display = ""

        tags_html = "".join([f'<span class="tag">#{t}</span>' for t in hashtags[:3]])
        price_badge = f'<span class="price-badge">¥{price}</span>' if price > 0 else '<span class="free-badge">無料</span>'
        summary_html = f'<p class="article-summary">{summary}</p>' if summary else ""

        cards_html += f"""
<div class="article-card">
  <div>
    <h2><a href="articles/{article_id}.html">{title}</a></h2>
    {summary_html}
    <div class="article-meta">
      <span class="date">{date_display}</span>
      {tags_html}
    </div>
  </div>
  {price_badge}
</div>"""

    if not cards_html:
        cards_html = '<p style="text-align:center;padding:64px 0;color:#aaa;">記事を準備中です。</p>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Claudeの使い方 | AI初心者ガイド</title>
  <meta name="description" content="昨日パソコンを買った人でもわかる、ClaudeとAIの使い方を解説します。">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <div class="container">
      <h1><a href="index.html">Claudeの使い方 | AI初心者ガイド</a></h1>
    </div>
  </header>
  <main>
    <div class="container">
      <p style="color:#555;margin-bottom:32px;">
        パソコンを買ったばかりの方でも大丈夫。ClaudeなどAIツールの使い方をわかりやすく解説します。
      </p>
      <div class="article-list">
        {cards_html}
      </div>
    </div>
  </main>
  <footer>
    <p>© 2026 Claudeの使い方 | AI初心者ガイド</p>
  </footer>
</body>
</html>"""


# ==================== メイン ====================

def load_articles_data() -> list:
    """docs/articles.json から既存記事データを読み込む"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_articles_data(articles: list):
    """docs/articles.json に記事データを保存"""
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


def publish(config: dict, articles: list, dry_run: bool = False) -> list:
    """記事リストから静的HTMLを生成して docs/ に保存する"""
    results = []

    if dry_run:
        for article in articles:
            print(f"[StaticSite] DRY RUN: '{article.get('title')}'")
            results.append({"success": True, "dry_run": True, "title": article.get("title")})
        return results

    os.makedirs(DOCS_DIR, exist_ok=True)
    os.makedirs(ARTICLES_DIR, exist_ok=True)

    # CSSを出力
    with open(os.path.join(DOCS_DIR, "style.css"), "w", encoding="utf-8") as f:
        f.write(CSS)

    # 既存データ読み込み
    all_articles = load_articles_data()
    existing_ids = {a["id"] for a in all_articles}

    for article in articles:
        # 記事IDを生成（タイムスタンプ + タイトルから）
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe = re.sub(r'[^\w]', '_', article.get("title", "article"))[:20]
        article_id = f"{timestamp}_{safe}"
        article["id"] = article_id

        if article_id in existing_ids:
            print(f"[StaticSite] スキップ（重複）: '{article.get('title')}'")
            continue

        # 記事詳細HTMLを生成
        html = generate_article_page(article)
        filepath = os.path.join(ARTICLES_DIR, f"{article_id}.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        all_articles.append(article)
        print(f"[StaticSite] 生成: {filepath}")
        results.append({"success": True, "title": article.get("title"), "path": filepath, "id": article_id})

    # articles.json を更新
    save_articles_data(all_articles)

    # index.html を再生成
    index_html = generate_index_page(all_articles)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"[StaticSite] index.html 更新完了（全{len(all_articles)}記事）")
    return results
