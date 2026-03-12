"""
ソフィアのエンゲージメント処理
自分のツイートへのリプライを自動いいね。
「返事を読んでいる」感を出すことでフォロワーの親近感を高める。
X API無料枠で動作。Claude API不使用。
"""
import os
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def auto_like_replies(config: dict):
    """直近24時間にソフィアへのリプライをいいね"""
    try:
        import tweepy
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
            tweet_fields=["created_at"],
            start_time=since
        )

        if not resp.data:
            print("[EngagementWorker] いいねするリプライなし")
            return

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

        print(f"[EngagementWorker] {liked}件にいいね完了")

    except ImportError:
        print("[EngagementWorker] tweepy未インストール")
    except Exception as e:
        print(f"[EngagementWorker] エラー: {e}")
