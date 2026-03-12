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
:root {
  --green: #55c500;
  --green-dark: #3d9400;
  --text: #2d2d2d;
  --text-sub: #6f7b8b;
  --border: #e4e9f0;
  --bg: #f4f6f8;
  --white: #fff;
  --tag-bg: #e9f7e0;
  --tag-color: #3d9400;
}
body {
  font-family: "Hiragino Sans", "Noto Sans JP", "Helvetica Neue", sans-serif;
  font-size: 15px;
  line-height: 1.75;
  color: var(--text);
  background: var(--bg);
}
a { text-decoration: none; color: inherit; }

/* ヘッダー */
header {
  background: var(--white);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 1px 4px rgba(0,0,0,.05);
}
.header-inner {
  max-width: 1040px;
  margin: 0 auto;
  padding: 0 20px;
  height: 56px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.logo {
  font-size: 20px;
  font-weight: 700;
  color: var(--green);
  letter-spacing: -.5px;
  white-space: nowrap;
}
.logo span { color: var(--text); font-weight: 400; font-size: 13px; margin-left: 8px; }
.header-nav { margin-left: auto; display: flex; gap: 8px; align-items: center; }
.header-nav a {
  font-size: 13px;
  color: var(--text-sub);
  padding: 6px 12px;
  border-radius: 4px;
  transition: background .15s;
}
.header-nav a:hover { background: var(--bg); color: var(--text); }

/* レイアウト */
.layout {
  max-width: 1040px;
  margin: 32px auto;
  padding: 0 20px;
  display: grid;
  grid-template-columns: 1fr 260px;
  gap: 24px;
  align-items: start;
}
@media (max-width: 768px) {
  .layout { grid-template-columns: 1fr; }
  .sidebar { display: none; }
}

/* 記事カード */
.article-list { display: flex; flex-direction: column; gap: 12px; }
.article-card {
  background: var(--white);
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 20px 24px;
  transition: box-shadow .15s;
}
.article-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.08); }
.card-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.tag {
  font-size: 11px;
  background: var(--tag-bg);
  color: var(--tag-color);
  padding: 2px 10px;
  border-radius: 99px;
  font-weight: 600;
  letter-spacing: .02em;
}
.article-card h2 { font-size: 17px; font-weight: 700; line-height: 1.5; margin-bottom: 8px; }
.article-card h2 a:hover { color: var(--green); }
.article-summary { font-size: 13px; color: var(--text-sub); line-height: 1.7; margin-bottom: 14px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-footer { display: flex; align-items: center; justify-content: space-between; }
.card-meta { display: flex; align-items: center; gap: 12px; }
.date { font-size: 12px; color: #b0b8c1; }
.card-stats { display: flex; gap: 12px; }
.stat { font-size: 12px; color: var(--text-sub); display: flex; align-items: center; gap: 4px; }
.stat svg { width: 14px; height: 14px; fill: currentColor; opacity: .6; }
.price-badge {
  font-size: 11px; font-weight: 700;
  background: #fff3f0; color: #e05a00;
  padding: 3px 10px; border-radius: 4px;
  border: 1px solid #ffd4bc;
}
.free-badge {
  font-size: 11px; font-weight: 700;
  background: #f0fbf5; color: var(--green-dark);
  padding: 3px 10px; border-radius: 4px;
  border: 1px solid #b8e6c8;
}

/* サイドバー */
.sidebar { position: sticky; top: 76px; }
.sidebar-box {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 16px;
}
.sidebar-box h3 { font-size: 13px; font-weight: 700; color: var(--text-sub); margin-bottom: 12px; text-transform: uppercase; letter-spacing: .05em; }
.sidebar-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.sidebar-tag {
  font-size: 12px;
  background: var(--bg);
  color: var(--text-sub);
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--border);
  transition: all .15s;
}
.sidebar-tag:hover { background: var(--tag-bg); color: var(--tag-color); border-color: #b8e6c8; }
.about-text { font-size: 13px; color: var(--text-sub); line-height: 1.7; }
.about-text strong { color: var(--text); }
.btn-note {
  display: block;
  text-align: center;
  background: var(--green);
  color: #fff;
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
  margin-top: 14px;
  transition: background .15s;
}
.btn-note:hover { background: var(--green-dark); }

/* 記事詳細 */
.article-detail-layout {
  max-width: 1040px;
  margin: 32px auto;
  padding: 0 20px;
  display: grid;
  grid-template-columns: 1fr 260px;
  gap: 24px;
  align-items: start;
}
@media (max-width: 768px) { .article-detail-layout { grid-template-columns: 1fr; } }
.article-detail-main {}
.article-header-card {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 32px 40px 24px;
  margin-bottom: 16px;
}
.article-header-card .card-tags { margin-bottom: 14px; }
.article-header-card h1 { font-size: 26px; font-weight: 700; line-height: 1.5; margin-bottom: 16px; }
.article-header-card .card-meta { display: flex; gap: 16px; align-items: center; }
.article-body {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 40px;
}
.article-body h2 { font-size: 20px; font-weight: 700; margin: 36px 0 14px; padding: 12px 16px; background: #f6fff0; border-left: 4px solid var(--green); border-radius: 0 4px 4px 0; }
.article-body h3 { font-size: 17px; font-weight: 700; margin: 28px 0 10px; color: var(--text); }
.article-body p { margin-bottom: 18px; }
.article-body ul, .article-body ol { padding-left: 24px; margin-bottom: 18px; }
.article-body li { margin-bottom: 8px; }
.article-body strong { font-weight: 700; color: #1a1a1a; }
.article-body code { background: #f0f4f8; padding: 2px 7px; border-radius: 4px; font-family: "SFMono-Regular", Consolas, monospace; font-size: 13px; color: #d6336c; }
.article-body pre { background: #1e2433; border-radius: 8px; padding: 20px 24px; margin-bottom: 18px; overflow-x: auto; }
.article-body pre code { background: none; color: #e2e8f0; font-size: 13px; padding: 0; }
.paid-wall {
  background: linear-gradient(135deg, #f6fff0, #e9f7e0);
  border: 1px solid #b8e6c8;
  border-radius: 8px;
  padding: 48px 40px;
  text-align: center;
  margin-top: 48px;
}
.paid-wall h3 { font-size: 20px; font-weight: 700; margin-bottom: 10px; }
.paid-wall p { color: var(--text-sub); font-size: 14px; margin-bottom: 24px; }

/* フッター */
footer { text-align: center; padding: 40px 0; color: #b0b8c1; font-size: 12px; border-top: 1px solid var(--border); background: var(--white); margin-top: 40px; }

/* パンくず */
.breadcrumb { font-size: 13px; color: var(--text-sub); margin-bottom: 20px; }
.breadcrumb a { color: var(--green-dark); }
.breadcrumb a:hover { text-decoration: underline; }
.back-link { margin-top: 24px; }
.back-link a { color: var(--green-dark); font-size: 14px; display: inline-flex; align-items: center; gap: 4px; }
.back-link a:hover { text-decoration: underline; }

/* 空状態 */
.empty-state { text-align: center; padding: 80px 0; color: #b0b8c1; }
.empty-state p { font-size: 15px; }
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

HEADER_HTML = """<header>
  <div class="header-inner">
    <a class="logo" href="{root}index.html">AI初心者ガイド<span>Claudeの使い方</span></a>
    <nav class="header-nav">
      <a href="{root}index.html">記事一覧</a>
      <a href="https://note.com" target="_blank" rel="noopener">note</a>
    </nav>
  </div>
</header>"""

SIDEBAR_HTML = """<aside class="sidebar">
  <div class="sidebar-box">
    <h3>このサイトについて</h3>
    <p class="about-text">
      <strong>パソコンを買ったばかりの方でも大丈夫。</strong><br>
      ClaudeなどAIツールの使い方を、専門用語なしでわかりやすく解説します。
    </p>
    <a class="btn-note" href="https://note.com" target="_blank" rel="noopener">noteで記事を読む →</a>
  </div>
  <div class="sidebar-box">
    <h3>タグ</h3>
    <div class="sidebar-tags">
      <a class="sidebar-tag" href="#">Claude</a>
      <a class="sidebar-tag" href="#">AI入門</a>
      <a class="sidebar-tag" href="#">ChatGPT</a>
      <a class="sidebar-tag" href="#">副業</a>
      <a class="sidebar-tag" href="#">使い方</a>
      <a class="sidebar-tag" href="#">初心者</a>
    </div>
  </div>
</aside>"""


def generate_article_page(article: dict) -> str:
    """記事詳細ページのHTMLを生成"""
    title = article.get("title", "")
    content = article.get("content", "")
    price = article.get("price", 0)
    hashtags = article.get("hashtags", [])
    date_str = article.get("created_at", "")
    note_url = article.get("note_url", "https://note.com")

    try:
        date_display = datetime.fromisoformat(date_str).strftime("%Y年%m月%d日")
    except Exception:
        date_display = ""

    free_html = markdown_to_html(content)
    paid_wall_html = ""
    if price > 0:
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
    header = HEADER_HTML.format(root="../")
    sidebar = SIDEBAR_HTML

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | AI初心者ガイド</title>
  <meta name="description" content="{article.get('summary', title)}">
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  {header}
  <div class="article-detail-layout">
    <main>
      <div class="breadcrumb">
        <a href="../index.html">トップ</a> &rsaquo; {title}
      </div>
      <div class="article-header-card">
        <div class="card-tags">{tags_html}</div>
        <h1>{title}</h1>
        <div class="card-meta">
          <span class="date">{date_display}</span>
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
    </main>
    {sidebar}
  </div>
  <footer><p>© 2026 AI初心者ガイド | Claudeの使い方</p></footer>
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

        tags_html = "".join([f'<span class="tag">#{t}</span>' for t in hashtags[:4]])
        price_badge = f'<span class="price-badge">¥{price}</span>' if price > 0 else '<span class="free-badge">無料</span>'
        summary_html = f'<p class="article-summary">{summary}</p>' if summary else ""

        # 文字数から読了時間を計算
        char_count = len(article.get("content", ""))
        read_min = max(1, char_count // 400)

        cards_html += f"""
<div class="article-card">
  <div class="card-tags">{tags_html}</div>
  <h2><a href="articles/{article_id}.html">{title}</a></h2>
  {summary_html}
  <div class="card-footer">
    <div class="card-meta">
      <span class="date">{date_display}</span>
      <span class="date">約{read_min}分で読めます</span>
    </div>
    <div class="card-stats">
      {price_badge}
    </div>
  </div>
</div>"""

    if not cards_html:
        cards_html = '<div class="empty-state"><p>記事を準備中です。しばらくお待ちください。</p></div>'

    header = HEADER_HTML.format(root="")
    sidebar = SIDEBAR_HTML

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI初心者ガイド | Claudeの使い方</title>
  <meta name="description" content="パソコンを買ったばかりの方でもわかる。ClaudeなどAIツールの使い方を解説します。">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  {header}
  <div class="layout">
    <main>
      <div class="article-list">
        {cards_html}
      </div>
    </main>
    {sidebar}
  </div>
  <footer><p>© 2026 AI初心者ガイド | Claudeの使い方</p></footer>
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
