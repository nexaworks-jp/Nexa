"""
サイトアナリティクス取得モジュール
nexa-analytics Workerからアクセスデータを取得し memory/site_analytics.json に保存する
"""
import requests
import json
import os
from datetime import datetime

ANALYTICS_URL = "https://nexa-analytics.nexaworks-jp.workers.dev/stats"


def fetch_site_analytics() -> dict:
    """nexa-analytics WorkerからアクセスデータをGETして返す"""
    try:
        resp = requests.get(ANALYTICS_URL, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        print(f"[Analytics] 取得失敗: {resp.status_code}")
    except Exception as e:
        print(f"[Analytics] 取得エラー: {e}")
    return {}


def save_analytics(data: dict, memory_dir: str):
    """analytics dataをmemory/site_analytics.jsonに保存"""
    path = os.path.join(memory_dir, "site_analytics.json")
    data["fetched_at"] = datetime.now().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[Analytics] 保存完了: {path}")


def get_top_articles(memory_dir: str, n: int = 10) -> list[dict]:
    """上位n件の記事アクセスデータを返す（/articles/を含むパスのみ）"""
    path = os.path.join(memory_dir, "site_analytics.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        pages = data.get("pages", [])
        article_pages = [p for p in pages if "/articles/" in p.get("path", "")]
        return article_pages[:n]
    except Exception:
        return []


def get_analytics_summary(memory_dir: str) -> dict:
    """自己改善エンジン向けのサマリーを返す"""
    path = os.path.join(memory_dir, "site_analytics.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        pages = data.get("pages", [])
        daily = data.get("daily", {})
        referrers = data.get("referrers", [])

        # 記事ページのみ
        article_pages = [p for p in pages if "/articles/" in p.get("path", "")]

        # 直近7日・30日のPV
        daily_values = list(daily.values())
        pv_7d = sum(daily_values[:7])
        pv_30d = sum(daily_values[:30])

        # 平均滞在時間（全記事）
        avg_times = [p["avg_seconds"] for p in article_pages if p.get("avg_seconds", 0) > 0]
        overall_avg_sec = int(sum(avg_times) / len(avg_times)) if avg_times else 0

        # トップ記事（パス → 記事IDだけ抜き出す）
        top_articles = []
        for p in article_pages[:5]:
            path_str = p.get("path", "")
            article_id = path_str.replace("/articles/", "").replace(".html", "")
            top_articles.append({
                "id": article_id,
                "views": p.get("views", 0),
                "avg_seconds": p.get("avg_seconds", 0),
            })

        return {
            "pv_7d": pv_7d,
            "pv_30d": pv_30d,
            "total_article_pages": len(article_pages),
            "avg_time_on_page_sec": overall_avg_sec,
            "top_articles": top_articles,
            "top_referrers": referrers[:5],
            "fetched_at": data.get("fetched_at", ""),
        }
    except Exception as e:
        print(f"[Analytics] サマリー生成エラー: {e}")
        return {}


def run(memory_dir: str):
    """アナリティクス取得・保存を実行"""
    print("[Analytics] サイトアクセスデータを取得中...")
    data = fetch_site_analytics()
    if data:
        save_analytics(data, memory_dir)
        pages = data.get("pages", [])
        daily = data.get("daily", {})
        today_pv = list(daily.values())[0] if daily else 0
        print(f"[Analytics] 本日PV: {today_pv}  記録ページ数: {len(pages)}")
    else:
        print("[Analytics] データなし（analytics-workerが未デプロイの可能性あり）")
