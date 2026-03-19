"""
ソフィアのエンゲージメント処理
自分のツイートへのリプライを自動いいね。
「返事を読んでいる」感を出すことでフォロワーの親近感を高める。
X API無料枠で動作。Claude API不使用。
"""
import os
import json
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def auto_like_replies(config: dict):
    """直近24時間にソフィアへのリプライをいいね＋メンション記憶"""
    try:
        import tweepy
        from workers import memory_manager

        x_cfg = config.get("x_twitter", {})
        bearer = x_cfg.get("bearer_token", "")
        api_key = x_cfg.get("api_key", "")
        api_secret = x_cfg.get("api_secret", "")
        access_token = x_cfg.get("access_token", "")
        access_token_secret = x_cfg.get("access_token_secret", "")

        if not all([bearer, api_key, access_token]):
            print("[EngagementWorker] X API未設定。スキップ。")
            return

        client = tweepy.Client(
            bearer_token=bearer,
            consumer_key=api_key, consumer_secret=api_secret,
            access_token=access_token, access_token_secret=access_token_secret
        )

        # 自分のユーザーIDを取得
        me = client.get_me()
        if not me or not me.data:
            return
        my_id = me.data.id

        # 直近24時間のメンションを取得
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        resp = client.search_recent_tweets(
            query="@selfcomestomine -is:retweet",
            max_results=10,
            tweet_fields=["created_at", "author_id"],
            expansions=["author_id"],
            start_time=since
        )

        if not resp.data:
            print("[EngagementWorker] いいねするリプライなし")
            return

        # author_id → username マッピング
        user_map = {}
        if resp.includes and "users" in resp.includes:
            for u in resp.includes["users"]:
                user_map[str(u.id)] = u.username

        liked = 0
        for tweet in resp.data:
            # 自分自身のツイートはいいねしない
            if str(tweet.id) == str(my_id):
                continue
            try:
                client.like(my_id, tweet.id)
                liked += 1
            except Exception as e:
                # すでにいいね済み等のエラーは無視
                if "already" not in str(e).lower():
                    print(f"[EngagementWorker] いいねエラー: {e}")

            # メンション内容を記憶に保存
            try:
                username = user_map.get(str(tweet.author_id), "unknown")
                memory_manager.store_mention(str(tweet.id), username, tweet.text)
            except Exception as e:
                print(f"[EngagementWorker] メンション保存エラー: {e}")

        print(f"[EngagementWorker] {liked}件にいいね完了")

    except ImportError:
        print("[EngagementWorker] tweepy未インストール")
    except Exception as e:
        print(f"[EngagementWorker] エラー: {e}")


def track_followers(config: dict):
    """フォロワー数を取得し follower_log.json に記録"""
    try:
        import tweepy

        x_cfg = config.get("x_twitter", {})
        bearer = x_cfg.get("bearer_token", "")
        api_key = x_cfg.get("api_key", "")
        api_secret = x_cfg.get("api_secret", "")
        access_token = x_cfg.get("access_token", "")
        access_token_secret = x_cfg.get("access_token_secret", "")

        if not all([bearer, api_key, access_token]):
            return

        client = tweepy.Client(
            bearer_token=bearer,
            consumer_key=api_key, consumer_secret=api_secret,
            access_token=access_token, access_token_secret=access_token_secret
        )

        me = client.get_me(user_fields=["public_metrics"])
        if not me or not me.data:
            return

        count = me.data.public_metrics.get("followers_count", 0)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        log_path = os.path.join(BASE_DIR, "memory", "follower_log.json")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                log = json.load(f)
        else:
            log = []

        # 同日エントリがあれば更新、なければ追加
        prev_count = log[-1]["count"] if log else count
        if log and log[-1]["date"] == today:
            log[-1]["count"] = count
            log[-1]["diff"] = count - (log[-2]["count"] if len(log) >= 2 else count)
        else:
            diff = count - prev_count
            log.append({"date": today, "count": count, "diff": diff})

        # 最大365件保持
        if len(log) > 365:
            log = log[-365:]

        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

        print(f"[EngagementWorker] フォロワー数: {count} (diff: {log[-1]['diff']:+d})")

    except ImportError:
        print("[EngagementWorker] tweepy未インストール")
    except Exception as e:
        print(f"[EngagementWorker] フォロワー追跡エラー: {e}")


def run(config: dict):
    """エンゲージメント処理のエントリーポイント"""
    auto_like_replies(config)
    track_followers(config)
