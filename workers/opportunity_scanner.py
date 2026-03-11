"""
案件スキャナー
PlaywrightでCrowdWorksから案件を自動取得する
"""
import json
import re
import time
from datetime import datetime


# 対象キーワード
TARGET_KEYWORDS = [
    "文章作成", "ライティング", "記事作成", "ブログ", "コピーライティング",
    "翻訳", "英語", "データ入力", "リサーチ", "調査", "まとめ",
    "シナリオ", "台本", "メール文", "LP制作", "ランディングページ",
    "SNS", "Instagram", "Twitter", "X投稿", "キャッチコピー",
    "商品説明", "マニュアル", "説明文", "プロフィール文", "自己PR",
    "ChatGPT", "AI", "プロンプト",
    "WordPress", "HTML", "CSS", "Python", "スクレイピング",
    "心理学", "行動科学", "進化", "人間心理", "マーケティング", "行動経済学"
]

# 避けるキーワード
AVOID_KEYWORDS = [
    "電話", "テレアポ", "訪問", "対面", "出勤", "常駐", "資格必須",
    "経験必須", "実績必須", "会社員限定"
]

# 検索する仕事カテゴリURL
SEARCH_URLS = [
    "https://crowdworks.jp/public/jobs/search?term=ライティング&order=new&job_type=fixed_fee",
    "https://crowdworks.jp/public/jobs/search?term=記事作成&order=new&job_type=fixed_fee",
    "https://crowdworks.jp/public/jobs/search?term=WordPress&order=new&job_type=fixed_fee",
    "https://crowdworks.jp/public/jobs/search?term=リサーチ&order=new&job_type=fixed_fee",
    "https://crowdworks.jp/public/jobs/search?term=Python&order=new&job_type=fixed_fee",
]


def search_crowdworks_playwright() -> list:
    """Playwrightを使ってCrowdWorksの案件を取得"""
    jobs = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[OpportunityScanner] Playwrightが未インストールです")
        return []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()

            for url in SEARCH_URLS:
                try:
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)  # JS描画待ち

                    # 案件リストを取得
                    job_elements = page.query_selector_all("li.job_list_item, article.job, .job-item, [data-job-id]")

                    if not job_elements:
                        # セレクタが合わない場合はテキストから抽出
                        content = page.content()
                        job_urls = re.findall(r'href="(/public/jobs/(\d+))"', content)
                        titles = re.findall(r'class="[^"]*job_title[^"]*"[^>]*>([^<]+)<', content)

                        for i, (path, job_id) in enumerate(job_urls[:10]):
                            if job_id in [j.get("job_id") for j in jobs]:
                                continue
                            title = titles[i].strip() if i < len(titles) else f"案件#{job_id}"
                            jobs.append({
                                "platform": "crowdworks",
                                "job_id": job_id,
                                "title": title,
                                "url": f"https://crowdworks.jp/public/jobs/{job_id}",
                                "found_at": datetime.now().isoformat()
                            })
                    else:
                        for el in job_elements[:10]:
                            try:
                                title_el = el.query_selector(".job_title, h2, h3, .title")
                                title = title_el.inner_text().strip() if title_el else ""
                                link_el = el.query_selector("a[href*='/public/jobs/']")
                                href = link_el.get_attribute("href") if link_el else ""
                                job_id_match = re.search(r'/public/jobs/(\d+)', href or "")
                                job_id = job_id_match.group(1) if job_id_match else ""

                                if job_id and title and job_id not in [j.get("job_id") for j in jobs]:
                                    jobs.append({
                                        "platform": "crowdworks",
                                        "job_id": job_id,
                                        "title": title,
                                        "url": f"https://crowdworks.jp/public/jobs/{job_id}",
                                        "found_at": datetime.now().isoformat()
                                    })
                            except Exception:
                                continue

                    print(f"[OpportunityScanner] {url.split('term=')[1].split('&')[0]}: {len(jobs)}件累計")
                    time.sleep(2)

                except Exception as e:
                    print(f"[OpportunityScanner] URL取得エラー: {e}")
                    continue

            browser.close()

    except Exception as e:
        print(f"[OpportunityScanner] Playwrightエラー: {e}")

    return jobs


def get_job_detail_playwright(url: str) -> dict:
    """案件詳細をPlaywrightで取得"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            content = page.content()

            # 予算を抽出
            budget_match = re.search(r'(\d[\d,]+)\s*円', content)
            budget = budget_match.group(0) if budget_match else "要相談"

            # 説明文を抽出
            desc_match = re.search(r'<div[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</div>',
                                   content, re.DOTALL)
            description = re.sub(r'<[^>]+>', '', desc_match.group(1))[:500] if desc_match else ""

            browser.close()
            return {"budget": budget, "description": description, "url": url}
    except Exception as e:
        return {}


def filter_suitable_jobs(jobs: list) -> list:
    """対応できる案件をフィルタリング"""
    suitable = []
    for job in jobs:
        title = job.get("title", "").lower()
        desc = job.get("description", "").lower()
        text = title + " " + desc

        if any(kw in text for kw in AVOID_KEYWORDS):
            continue

        score = sum(1 for kw in TARGET_KEYWORDS if kw in text)
        if score > 0 or any(kw in title for kw in TARGET_KEYWORDS):
            job["match_score"] = score
            suitable.append(job)

    suitable.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return suitable[:10]


def scan(config: dict, already_applied: list) -> dict:
    """案件スキャンのメイン関数"""
    print("[OpportunityScanner] 案件スキャン開始...")

    jobs = search_crowdworks_playwright()
    print(f"[OpportunityScanner] CrowdWorks: {len(jobs)}件発見")

    # 応募済み除外
    applied_ids = [j.get("job_id") for j in already_applied]
    new_jobs = [j for j in jobs if j.get("job_id") not in applied_ids]

    suitable = filter_suitable_jobs(new_jobs)
    print(f"[OpportunityScanner] 適合案件: {len(suitable)}件")

    return {
        "total_found": len(jobs),
        "suitable": suitable,
        "scanned_at": datetime.now().isoformat()
    }
