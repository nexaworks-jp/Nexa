"""
トレンド分析ワーカー
Google TrendsとXトレンドから今日の旬なトピックを取得する
"""
import json
import time
import random
from datetime import datetime


def get_google_trends_jp() -> list[str]:
    """Google Trendsから日本のトレンドキーワードを取得"""
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl='ja-JP', tz=540, timeout=(10, 25))
        trending = pytrends.trending_searches(pn='japan')
        keywords = trending[0].tolist()[:10]
        return keywords
    except Exception as e:
        print(f"[TrendAnalyzer] Google Trends取得エラー: {e}")
        return []


def get_base_topics(niche: str) -> list[str]:
    """ニッチに基づくベーストピック（APIが失敗した時のフォールバック）"""
    base = {
        "AI活用術": [
            "ChatGPT 使い方", "Claude AI 活用", "AI副業 稼ぎ方",
            "Midjourney プロンプト", "AI画像生成", "生成AI 仕事",
            "ノーコード AI", "AIツール 無料", "プロンプトエンジニアリング"
        ],
        "副業": [
            "在宅副業 初心者", "クラウドワークス 稼ぐ", "ブログ 収益化",
            "YouTube 副業", "アフィリエイト 始め方", "Webライター 単価",
            "フリーランス 案件", "スキマ時間 副業"
        ],
        "節約": [
            "電気代 節約 2024", "食費 節約 一人暮らし", "格安SIM 比較",
            "ふるさと納税 おすすめ", "楽天経済圏", "ポイ活 稼ぎ方",
            "新NISA 始め方", "積立NISA おすすめ"
        ]
    }
    results = []
    for key in base:
        if any(word in niche for word in key.split("・")):
            results.extend(base[key])
    if not results:
        for v in base.values():
            results.extend(v)
    return results[:10]


def analyze(config: dict) -> dict:
    """
    トレンド分析のメイン関数
    戻り値: { "topics": [...], "source": "google|fallback", "analyzed_at": "..." }
    """
    niche = config.get("settings", {}).get("primary_niche", "AI活用術・副業・節約")

    print("[TrendAnalyzer] トレンド分析開始...")
    topics = get_google_trends_jp()

    if len(topics) >= 5:
        source = "google_trends"
        print(f"[TrendAnalyzer] Google Trendsから{len(topics)}件取得")
    else:
        topics = get_base_topics(niche)
        source = "base_topics"
        print(f"[TrendAnalyzer] ベーストピックを使用: {len(topics)}件")

    # ニッチ関連キーワードを追加
    niche_keywords = [k.strip() for k in niche.split("・")]
    combined = niche_keywords + topics
    # 重複除去
    seen = set()
    unique_topics = []
    for t in combined:
        if t not in seen:
            seen.add(t)
            unique_topics.append(t)

    return {
        "topics": unique_topics[:15],
        "source": source,
        "niche": niche,
        "analyzed_at": datetime.now().isoformat()
    }
