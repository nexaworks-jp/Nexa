"""
案件スキャナー
CrowdWorksとLancersから自分でできそうな案件を自動で探す
"""
import requests
import json
import re
import time
from datetime import datetime
from html.parser import HTMLParser


# Claudeが得意な案件キーワード
TARGET_KEYWORDS = [
    "文章作成", "ライティング", "記事作成", "ブログ", "コピーライティング",
    "翻訳", "英語", "データ入力", "リサーチ", "調査", "まとめ",
    "シナリオ", "台本", "メール文", "LP制作", "ランディングページ",
    "SNS", "Instagram", "Twitter", "X投稿", "キャッチコピー",
    "商品説明", "マニュアル", "説明文", "プロフィール文", "自己PR",
    "ChatGPT", "AI", "プロンプト"
]

# 避けるキーワード（Claudeが苦手なもの）
AVOID_KEYWORDS = [
    "電話", "テレアポ", "訪問", "対面", "出勤", "常駐", "資格必須",
    "経験必須", "実績必須", "会社員限定"
]


class SimpleHTMLStripper(HTMLParser):
    """HTMLタグを除去するシンプルなパーサー"""
    def __init__(self):
        super().__init__()
        self.text_parts = []

    def handle_data(self, data):
        self.text_parts.append(data)

    def get_text(self):
        return " ".join(self.text_parts)


def strip_html(html: str) -> str:
    parser = SimpleHTMLStripper()
    parser.feed(html)
    return parser.get_text()


def search_crowdworks() -> list[dict]:
    """CrowdWorksの公開案件を検索"""
    jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ja,en-US;q=0.9"
    }

    # ライティング・翻訳カテゴリを検索
    search_terms = ["文章作成", "ライティング", "記事作成", "AI"]
    for term in search_terms:
        try:
            url = f"https://crowdworks.jp/public/jobs/search?term={requests.utils.quote(term)}&order=new"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue

            # 簡易HTML解析でジョブを抽出
            content = resp.text
            # job IDとタイトルを抽出（CrowdWorksのURL構造から）
            job_urls = re.findall(r'/public/jobs/(\d+)', content)
            titles = re.findall(r'class="job_title[^"]*"[^>]*>([^<]+)<', content)

            for i, job_id in enumerate(job_urls[:5]):
                title = titles[i] if i < len(titles) else f"案件#{job_id}"
                jobs.append({
                    "platform": "crowdworks",
                    "job_id": job_id,
                    "title": strip_html(title).strip(),
                    "url": f"https://crowdworks.jp/public/jobs/{job_id}",
                    "search_term": term,
                    "found_at": datetime.now().isoformat()
                })

            time.sleep(2)  # レート制限対策

        except Exception as e:
            print(f"[OpportunityScanner] CrowdWorks検索エラー ({term}): {e}")

    return jobs


def get_job_detail(platform: str, job_id: str, url: str) -> dict:
    """案件の詳細情報を取得"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return {}

        content = resp.text

        # 予算を抽出
        budget_match = re.search(r'(\d[\d,]+)\s*円', content)
        budget = budget_match.group(0) if budget_match else "要相談"

        # 説明文を抽出（簡易）
        desc_match = re.search(r'<div[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</div>',
                               content, re.DOTALL)
        description = strip_html(desc_match.group(1))[:500] if desc_match else ""

        return {
            "budget": budget,
            "description": description,
            "url": url
        }
    except Exception as e:
        return {}


def filter_suitable_jobs(jobs: list[dict]) -> list[dict]:
    """Claudeが対応できる案件をフィルタリング"""
    suitable = []
    for job in jobs:
        title = job.get("title", "").lower()
        desc = job.get("description", "").lower()
        text = title + " " + desc

        # 除外キーワードチェック
        if any(kw in text for kw in AVOID_KEYWORDS):
            continue

        # 対象キーワードチェック
        score = sum(1 for kw in TARGET_KEYWORDS if kw in text)
        if score > 0 or any(kw in title for kw in TARGET_KEYWORDS):
            job["match_score"] = score
            suitable.append(job)

    # スコア順にソート
    suitable.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return suitable[:10]


def scan(config: dict, already_applied: list) -> dict:
    """
    案件スキャンのメイン関数
    """
    print("[OpportunityScanner] 案件スキャン開始...")

    all_jobs = []

    # CrowdWorks検索
    cw_jobs = search_crowdworks()
    all_jobs.extend(cw_jobs)
    print(f"[OpportunityScanner] CrowdWorks: {len(cw_jobs)}件発見")

    # 既に応募済みの案件を除外
    applied_ids = [j.get("job_id") for j in already_applied]
    new_jobs = [j for j in all_jobs if j.get("job_id") not in applied_ids]

    # 適合する案件をフィルタリング
    suitable = filter_suitable_jobs(new_jobs)
    print(f"[OpportunityScanner] 適合案件: {len(suitable)}件")

    return {
        "total_found": len(all_jobs),
        "suitable": suitable,
        "scanned_at": datetime.now().isoformat()
    }
