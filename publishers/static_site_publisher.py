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

# サイトのベースURL（カスタムドメイン設定後に変更する）
SITE_URL = "https://nexa.nexaworks-jp.workers.dev"


def load_seo_settings() -> dict:
    """memory/seo_settings.json を読み込む"""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "seo_settings.json")
    default = {
        "meta_keywords_base": ["AI初心者", "人工知能 使い方", "Claude", "ChatGPT", "生成AI", "AI活用術"],
        "title_templates": [],
        "description_template": ""
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return {**default, **json.load(f)}
        except Exception:
            pass
    return default


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
.tag { cursor: pointer; }
.tag:hover { opacity: .75; }
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

/* Nexaバナー */
.nexa-banner {
  background: #1a1a2e;
  color: #a0a8c0;
  text-align: center;
  font-size: 11px;
  padding: 5px;
  letter-spacing: .08em;
}
.nexa-banner strong { color: #fff; }

/* 難易度 */
.difficulty { display: flex; align-items: center; gap: 4px; }
.difficulty-stars { color: #f5a623; font-size: 13px; letter-spacing: -1px; }
.difficulty-label { font-size: 11px; color: var(--text-sub); }

/* フィルターバー */
.filter-bar {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.filter-bar label { font-size: 12px; font-weight: 700; color: var(--text-sub); white-space: nowrap; }
.filter-group { display: flex; flex-wrap: wrap; gap: 6px; }
.filter-btn {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 99px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-sub);
  cursor: pointer;
  transition: all .15s;
}
.filter-btn:hover, .filter-btn.active {
  background: var(--tag-bg);
  color: var(--tag-color);
  border-color: #b8e6c8;
}
.article-card.hidden { display: none; }

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

/* 内部リンクカード */
.related-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #f6fff0;
  border: 1px solid #b8e6c8;
  border-left: 4px solid var(--green);
  border-radius: 8px;
  padding: 14px 18px;
  margin: 28px 0;
  text-decoration: none;
  transition: box-shadow .15s;
}
.related-card:hover { box-shadow: 0 4px 12px rgba(85,197,0,.15); }
.related-card-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--green-dark);
  white-space: nowrap;
}
.related-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
}
.related-card-arrow { margin-left: auto; color: var(--green); font-size: 18px; flex-shrink: 0; }

/* コードブロック */
.code-wrapper { position: relative; margin-bottom: 20px; }
.code-wrapper pre { margin-bottom: 0; }
.copy-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  background: rgba(255,255,255,.12);
  border: 1px solid rgba(255,255,255,.2);
  color: #cdd6f4;
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  transition: background .15s;
  font-family: sans-serif;
}
.copy-btn:hover { background: rgba(255,255,255,.22); }
.copy-btn.copied { color: #a6e3a1; border-color: #a6e3a1; }
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

NOTE_CREATOR_URL = "https://note.com/youth_waster"

HEADER_HTML = """<div class="nexa-banner"><strong>【Nexa】</strong> 自律型AIが毎日更新する、AI初心者のための解説サイト</div>
<header>
  <div class="header-inner">
    <a class="logo" href="{root}index.html">AI初心者ガイド</a>
    <nav class="header-nav">
      <a href="{root}index.html">記事一覧</a>
      <a href="{note_url}" target="_blank" rel="noopener">note</a>
    </nav>
  </div>
</header>"""


def build_sidebar_html(tags: list = None) -> str:
    """サイドバーHTMLを生成。tagsを渡すとフィルター連携タグを生成する。"""
    if tags:
        tag_items = "".join(
            f'<button class="sidebar-tag filter-btn" data-tag="{t}">{t}</button>'
            for t in tags[:12]
        )
    else:
        tag_items = "".join(
            f'<span class="sidebar-tag">{t}</span>'
            for t in ["Claude", "AI入門", "ChatGPT", "副業", "使い方", "初心者"]
        )
    return f"""<aside class="sidebar">
  <div class="sidebar-box">
    <h3>このサイトについて</h3>
    <p class="about-text">
      <strong>パソコンを買ったばかりの方でも大丈夫。</strong><br>
      AIツールの使い方・活用術を、専門用語なしでわかりやすく解説します。
    </p>
    <a class="btn-note" href="{NOTE_CREATOR_URL}" target="_blank" rel="noopener">noteで記事を読む →</a>
  </div>
  <div class="sidebar-box">
    <h3>タグ</h3>
    <div class="sidebar-tags" id="sidebar-tag-filters">
      {tag_items}
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
    related_articles = article.get("related_articles", [])

    try:
        date_display = datetime.fromisoformat(date_str).strftime("%Y年%m月%d日")
    except Exception:
        date_display = ""

    # リンクパターン読み込み
    patterns_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "link_patterns.json")
    link_patterns = {"prerequisite": ["📖 まずこちらをお読みください"], "related": ["👉 あわせて読みたい"], "next": ["🚀 次のステップはこちら"]}
    if os.path.exists(patterns_path):
        try:
            with open(patterns_path, "r", encoding="utf-8") as f:
                link_patterns = json.load(f)
        except Exception:
            pass

    free_html = markdown_to_html(content)

    # 関連記事カードHTMLを生成
    def make_related_card(rel: dict) -> str:
        rel_id = rel.get("id", "")
        rel_title = rel.get("title", "")
        rel_type = rel.get("type", "related")
        import random as _random
        patterns_list = link_patterns.get(rel_type, ["👉 あわせて読みたい"])
        label = _random.choice(patterns_list)
        return f'''<a class="related-card" href="../articles/{rel_id}.html">
  <span class="related-card-label">{label}</span>
  <span class="related-card-title">{rel_title}</span>
  <span class="related-card-arrow">›</span>
</a>'''

    # prerequisiteは記事冒頭に、related/nextは記事末尾に挿入
    prereq_cards = "".join(make_related_card(r) for r in related_articles if r.get("type") == "prerequisite")
    other_cards = "".join(make_related_card(r) for r in related_articles if r.get("type") in ("related", "next"))

    # コンテンツの前後に挿入
    if prereq_cards:
        free_html = prereq_cards + free_html
    if other_cards:
        free_html = free_html + other_cards
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
    header = HEADER_HTML.format(root="../", note_url=NOTE_CREATOR_URL)
    sidebar = build_sidebar_html()

    article_id = article.get("id", "")
    canonical_url = f"{SITE_URL}/articles/{article_id}.html"
    description = article.get('summary', title)[:160]
    seo = load_seo_settings()
    all_keywords = list(dict.fromkeys(hashtags + seo.get("meta_keywords_base", [])))
    keywords = ", ".join(all_keywords[:15])
    iso_date = date_str[:10] if date_str else ""

    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": title,
                "description": description,
                "keywords": keywords,
                "datePublished": iso_date,
                "dateModified": iso_date,
                "author": {"@type": "Organization", "name": "AI初心者ガイド"},
                "publisher": {
                    "@type": "Organization",
                    "name": "AI初心者ガイド",
                    "url": SITE_URL
                },
                "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url}
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "トップ", "item": f"{SITE_URL}/index.html"},
                    {"@type": "ListItem", "position": 2, "name": title, "item": canonical_url}
                ]
            }
        ]
    }, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | AI初心者ガイド</title>
  <meta name="description" content="{description}">
  <meta name="keywords" content="{keywords}">
  <link rel="canonical" href="{canonical_url}">
  <!-- OGP -->
  <meta property="og:type" content="article">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:url" content="{canonical_url}">
  <meta property="og:site_name" content="AI初心者ガイド">
  <meta property="og:locale" content="ja_JP">
  <meta property="article:published_time" content="{iso_date}">
  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <!-- JSON-LD -->
  <script type="application/ld+json">{json_ld}</script>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  {header}
  <div class="article-detail-layout">
    <main>
      <nav class="breadcrumb" aria-label="パンくずリスト">
        <a href="../index.html">トップ</a> &rsaquo; {title}
      </nav>
      <div class="article-header-card">
        <div class="card-tags">{tags_html}</div>
        <h1>{title}</h1>
        <div class="card-meta">
          <time class="date" datetime="{iso_date}">{date_display}</time>
          {price_badge}
        </div>
      </div>
      <article class="article-body">
        {free_html}
        {paid_wall_html}
      </article>
      <div class="back-link">
        <a href="../index.html">← 記事一覧に戻る</a>
      </div>
    </main>
    {sidebar}
  </div>
  <footer><p>© 2026 AI初心者ガイド</p></footer>
  <script>
document.querySelectorAll('pre').forEach(function(pre) {{
  var wrapper = document.createElement('div');
  wrapper.className = 'code-wrapper';
  pre.parentNode.insertBefore(wrapper, pre);
  wrapper.appendChild(pre);
  var btn = document.createElement('button');
  btn.className = 'copy-btn';
  btn.textContent = 'コピー';
  wrapper.appendChild(btn);
  btn.addEventListener('click', function() {{
    var code = pre.querySelector('code') ? pre.querySelector('code').innerText : pre.innerText;
    navigator.clipboard.writeText(code).then(function() {{
      btn.textContent = 'コピー済み';
      btn.classList.add('copied');
      setTimeout(function() {{ btn.textContent = 'コピー'; btn.classList.remove('copied'); }}, 2000);
    }});
  }});
}});
var activeDiff = 0, activeTag = '';
function applyFilter() {{
  document.querySelectorAll('#article-list .article-card').forEach(function(card) {{
    var diff = parseInt(card.dataset.difficulty || '1');
    var tags = card.dataset.tags || '';
    var diffOk = activeDiff === 0 || diff === activeDiff;
    var tagOk = activeTag === '' || tags.split(' ').indexOf(activeTag) >= 0;
    card.classList.toggle('hidden', !(diffOk && tagOk));
  }});
}}
function setTagFilter(tag) {{
  activeTag = tag;
  document.querySelectorAll('#tag-filters .filter-btn, #sidebar-tag-filters .filter-btn').forEach(function(b) {{
    b.classList.toggle('active', b.dataset.tag === tag);
  }});
  var allBtn = document.querySelector('#tag-filters .filter-btn[data-tag=""]');
  if (allBtn) allBtn.classList.toggle('active', tag === '');
  applyFilter();
}}
document.querySelectorAll('#diff-filters .filter-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    activeDiff = parseInt(this.dataset.diff);
    document.querySelectorAll('#diff-filters .filter-btn').forEach(function(b) {{ b.classList.remove('active'); }});
    this.classList.add('active');
    applyFilter();
  }});
}});
document.querySelectorAll('#tag-filters .filter-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{ setTagFilter(this.dataset.tag); }});
}});
document.querySelectorAll('#sidebar-tag-filters .filter-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{ setTagFilter(this.dataset.tag); }});
}});
document.querySelectorAll('#article-list .tag').forEach(function(tag) {{
  tag.addEventListener('click', function() {{ setTagFilter(this.dataset.tag); }});
}});
</script>
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

        difficulty = article.get("difficulty", 1)
        difficulty = max(1, min(5, int(difficulty) if str(difficulty).isdigit() else 1))
        stars_filled = "★" * difficulty
        stars_empty = "☆" * (5 - difficulty)
        diff_labels = {1: "入門", 2: "初級", 3: "中級", 4: "上級", 5: "発展"}
        diff_label = diff_labels.get(difficulty, "入門")

        tags_html = "".join([f'<span class="tag" data-tag="{t}">#{t}</span>' for t in hashtags[:4]])
        price_badge = f'<span class="price-badge">¥{price}</span>' if price > 0 else '<span class="free-badge">無料</span>'
        summary_html = f'<p class="article-summary">{summary}</p>' if summary else ""
        tags_data = " ".join(hashtags)

        char_count = len(article.get("content", ""))
        read_min = max(1, char_count // 400)

        cards_html += f"""
<div class="article-card" data-difficulty="{difficulty}" data-tags="{tags_data}">
  <div class="card-tags">{tags_html}</div>
  <h2><a href="articles/{article_id}.html">{title}</a></h2>
  {summary_html}
  <div class="card-footer">
    <div class="card-meta">
      <span class="date">{date_display}</span>
      <span class="date">約{read_min}分で読めます</span>
      <span class="difficulty"><span class="difficulty-stars">{stars_filled}{stars_empty}</span><span class="difficulty-label">{diff_label}</span></span>
    </div>
    <div class="card-stats">
      {price_badge}
    </div>
  </div>
</div>"""

    if not cards_html:
        cards_html = '<div class="empty-state"><p>記事を準備中です。しばらくお待ちください。</p></div>'

    # タグ一覧を全記事から収集（フィルター用）
    all_tags = []
    for a in articles:
        for t in a.get("hashtags", []):
            if t not in all_tags:
                all_tags.append(t)
    tag_filter_btns = "".join(f'<button class="filter-btn" data-tag="{t}">#{t}</button>' for t in all_tags[:12])

    header = HEADER_HTML.format(root="", note_url=NOTE_CREATOR_URL)
    sidebar = build_sidebar_html(tags=all_tags)

    index_url = f"{SITE_URL}/index.html"
    index_description = "パソコンを買ったばかりの方でもわかる。Claude・ChatGPT・GeminiなどのAIツールの使い方をわかりやすく解説します。"
    seo_idx = load_seo_settings()
    index_keywords = ", ".join(seo_idx.get("meta_keywords_base", ["AI初心者", "Claude", "ChatGPT", "生成AI"]))
    index_json_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "AI初心者ガイド",
        "url": SITE_URL,
        "description": index_description,
        "inLanguage": "ja",
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{SITE_URL}/index.html?q={{search_term_string}}",
            "query-input": "required name=search_term_string"
        }
    }, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI初心者ガイド | AIツールの使い方をわかりやすく解説</title>
  <meta name="description" content="{index_description}">
  <meta name="keywords" content="{index_keywords}">
  <link rel="canonical" href="{index_url}">
  <!-- OGP -->
  <meta property="og:type" content="website">
  <meta property="og:title" content="AI初心者ガイド | AIツールの使い方をわかりやすく解説">
  <meta property="og:description" content="{index_description}">
  <meta property="og:url" content="{index_url}">
  <meta property="og:site_name" content="AI初心者ガイド">
  <meta property="og:locale" content="ja_JP">
  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="AI初心者ガイド">
  <meta name="twitter:description" content="{index_description}">
  <!-- JSON-LD -->
  <script type="application/ld+json">{index_json_ld}</script>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  {header}
  <div class="layout">
    <main>
      <div class="filter-bar">
        <label>難易度：</label>
        <div class="filter-group" id="diff-filters">
          <button class="filter-btn active" data-diff="0">すべて</button>
          <button class="filter-btn" data-diff="1">★入門</button>
          <button class="filter-btn" data-diff="2">★★初級</button>
          <button class="filter-btn" data-diff="3">★★★中級</button>
          <button class="filter-btn" data-diff="4">★★★★上級</button>
          <button class="filter-btn" data-diff="5">★★★★★発展</button>
        </div>
        <label>タグ：</label>
        <div class="filter-group" id="tag-filters">
          <button class="filter-btn active" data-tag="">すべて</button>
          {tag_filter_btns}
        </div>
      </div>
      <div class="article-list" id="article-list">
        {cards_html}
      </div>
    </main>
    {sidebar}
  </div>
  <footer><p>© 2026 AI初心者ガイド</p></footer>
  <script>
document.querySelectorAll('pre').forEach(function(pre) {{
  var wrapper = document.createElement('div');
  wrapper.className = 'code-wrapper';
  pre.parentNode.insertBefore(wrapper, pre);
  wrapper.appendChild(pre);
  var btn = document.createElement('button');
  btn.className = 'copy-btn';
  btn.textContent = 'コピー';
  wrapper.appendChild(btn);
  btn.addEventListener('click', function() {{
    var code = pre.querySelector('code') ? pre.querySelector('code').innerText : pre.innerText;
    navigator.clipboard.writeText(code).then(function() {{
      btn.textContent = 'コピー済み';
      btn.classList.add('copied');
      setTimeout(function() {{ btn.textContent = 'コピー'; btn.classList.remove('copied'); }}, 2000);
    }});
  }});
}});
var activeDiff = 0, activeTag = '';
function applyFilter() {{
  document.querySelectorAll('#article-list .article-card').forEach(function(card) {{
    var diff = parseInt(card.dataset.difficulty || '1');
    var tags = card.dataset.tags || '';
    var diffOk = activeDiff === 0 || diff === activeDiff;
    var tagOk = activeTag === '' || tags.split(' ').indexOf(activeTag) >= 0;
    card.classList.toggle('hidden', !(diffOk && tagOk));
  }});
}}
function setTagFilter(tag) {{
  activeTag = tag;
  document.querySelectorAll('#tag-filters .filter-btn, #sidebar-tag-filters .filter-btn').forEach(function(b) {{
    b.classList.toggle('active', b.dataset.tag === tag);
  }});
  var allBtn = document.querySelector('#tag-filters .filter-btn[data-tag=""]');
  if (allBtn) allBtn.classList.toggle('active', tag === '');
  applyFilter();
}}
document.querySelectorAll('#diff-filters .filter-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    activeDiff = parseInt(this.dataset.diff);
    document.querySelectorAll('#diff-filters .filter-btn').forEach(function(b) {{ b.classList.remove('active'); }});
    this.classList.add('active');
    applyFilter();
  }});
}});
document.querySelectorAll('#tag-filters .filter-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{ setTagFilter(this.dataset.tag); }});
}});
document.querySelectorAll('#sidebar-tag-filters .filter-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{ setTagFilter(this.dataset.tag); }});
}});
document.querySelectorAll('#article-list .tag').forEach(function(tag) {{
  tag.addEventListener('click', function() {{ setTagFilter(this.dataset.tag); }});
}});
</script>
</body>
</html>"""


# ==================== メイン ====================

def generate_sitemap(articles: list):
    """sitemap.xml を生成して docs/ に保存する"""
    urls = [f"""  <url>
    <loc>{SITE_URL}/index.html</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>"""]
    for a in articles:
        aid = a.get("id", "")
        date_str = a.get("created_at", "")[:10]
        if not aid:
            continue
        urls.append(f"""  <url>
    <loc>{SITE_URL}/articles/{aid}.html</loc>
    <lastmod>{date_str}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>""")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls)
    xml += "\n</urlset>"
    with open(os.path.join(DOCS_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"[StaticSite] sitemap.xml 更新（{len(articles)}件）")


def generate_robots_txt():
    """robots.txt を生成して docs/ に保存する（既存なら上書きしない）"""
    path = os.path.join(DOCS_DIR, "robots.txt")
    if os.path.exists(path):
        return
    content = f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[StaticSite] robots.txt 生成")


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

    # sitemap.xml / robots.txt を更新
    generate_sitemap(all_articles)
    generate_robots_txt()

    return results
